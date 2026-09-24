"""Database wrapper for SQLAlchemy operations.

Read methods return plain dicts, never live ORM instances. Objects loaded inside
a ``with self.get_session()`` block become detached once the block exits; with
the default ``expire_on_commit=True`` any later attribute access would trigger a
reload on the closed session and raise ``DetachedInstanceError``. To avoid that
entirely we (a) build the sessionmaker with ``expire_on_commit=False`` and
(b) snapshot rows into dicts (via the ``_*_to_dict`` helpers) while the session
is still open. Callers work with dicts and never touch lazy relationships.
"""

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from typing import List, Optional
from datetime import datetime
from pathlib import Path

from ..ingestion.base import speed_bucket
from .models import Base, Game, Position, Opening, Pattern, SyncState, Embedding


def _phase_for_move(move_number: int) -> str:
    """Bucket a full-move number into opening / middlegame / endgame.

    Matches ``coach._phase_for_move``; duplicated here to avoid a storage ->
    coaching import cycle.
    """
    if move_number <= 15:
        return "opening"
    if move_number <= 40:
        return "middlegame"
    return "endgame"


def _game_outcome(result: str, color: str) -> str:
    """Return 'win' / 'draw' / 'loss' from the player's perspective."""
    if result == "1/2-1/2":
        return "draw"
    if (result == "1-0" and color == "white") or (
        result == "0-1" and color == "black"
    ):
        return "win"
    return "loss"


def _score_pct(wins: int, draws: int, games: int) -> float:
    """Chess score percentage: a win is 1, a draw 0.5."""
    return round(100.0 * (wins + 0.5 * draws) / games, 1) if games else 0.0


def _union(existing, new) -> list:
    """Order-preserving union of two lists (used to merge pattern examples)."""
    return list(dict.fromkeys(list(existing or []) + list(new or [])))


def _finalize_groups(groups: dict, key: str = "opening") -> List[dict]:
    """Turn accumulator dicts into public rows (compute score% / avg cp loss).

    Drops the internal running sums and sorts by games played (descending).
    """
    rows = []
    for grp in groups.values():
        positions = grp.pop("positions")
        cp_sum = grp.pop("cp_sum")
        grp["score_pct"] = _score_pct(grp["wins"], grp["draws"], grp["games"])
        grp["avg_cp_loss"] = round(cp_sum / positions, 1) if positions else None
        rows.append(grp)
    rows.sort(key=lambda r: r["games"], reverse=True)
    return rows


def _game_to_dict(game: Game) -> dict:
    """Snapshot a Game row into a plain dict (call while session is open)."""
    return {
        "id": game.id,
        "game_id": game.game_id,
        "platform": game.platform,
        "username": game.username,
        "color": game.color,
        "user_rating": game.user_rating,
        "opponent_username": game.opponent_username,
        "opponent_rating": game.opponent_rating,
        "result": game.result,
        "time_control": game.time_control,
        "played_at": game.played_at,
        "opening_eco": game.opening_eco,
        "opening_name": game.opening_name,
        "pgn": game.pgn,
        "analyzed_at": game.analyzed_at,
        "created_at": game.created_at,
    }


def _position_to_dict(position: Position) -> dict:
    """Snapshot a Position row into a plain dict (call while session is open)."""
    return {
        "id": position.id,
        "game_id": position.game_id,
        "move_number": position.move_number,
        "fen": position.fen,
        "move_played": position.move_played,
        "eval_before": position.eval_before,
        "eval_after": position.eval_after,
        "centipawn_loss": position.centipawn_loss,
        "depth": position.depth,
        "best_move": position.best_move,
        "best_move_eval": position.best_move_eval,
        "top_3_moves": position.top_3_moves,
        "classification": position.classification,
        "is_blunder": position.is_blunder,
        "is_missed_tactic": position.is_missed_tactic,
        "mate_in": position.mate_in,
        "explanation": position.explanation,
    }


def _opening_to_dict(opening: Opening) -> dict:
    """Snapshot an Opening row into a plain dict (call while session is open)."""
    return {
        "id": opening.id,
        "eco_code": opening.eco_code,
        "name": opening.name,
        "games_as_white": opening.games_as_white,
        "games_as_black": opening.games_as_black,
        "wins_as_white": opening.wins_as_white,
        "wins_as_black": opening.wins_as_black,
        "draws_as_white": opening.draws_as_white,
        "draws_as_black": opening.draws_as_black,
        "avg_cp_loss_white": opening.avg_cp_loss_white,
        "avg_cp_loss_black": opening.avg_cp_loss_black,
        "last_played": opening.last_played,
    }


def _pattern_to_dict(pattern: Pattern) -> dict:
    """Snapshot a Pattern row into a plain dict (call while session is open)."""
    return {
        "id": pattern.id,
        "pattern_type": pattern.pattern_type,
        "description": pattern.description,
        "occurrence_count": pattern.occurrence_count,
        "severity": pattern.severity,
        "phase": pattern.phase,
        "associated_openings": pattern.associated_openings,
        "example_game_ids": pattern.example_game_ids,
        "coaching_advice": pattern.coaching_advice,
    }


class Database:
    """Database interface for chess coach."""
    
    def __init__(self, db_path: str = "data/chess_coach.db"):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        # Ensure directory exists
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.engine = create_engine(f"sqlite:///{db_path}")
        # expire_on_commit=False so snapshotting rows into dicts after commit
        # does not trigger a reload on the (soon to be closed) session.
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        
        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.Session()
    
    # Game operations
    
    def save_game(self, game_data: dict) -> dict:
        """Save a game to the database. Returns a detached-safe dict."""
        with self.get_session() as session:
            game = Game(
                game_id=game_data["game_id"],
                platform=game_data["platform"],
                username=game_data["username"],
                color=game_data["color"],
                user_rating=game_data.get("user_rating"),
                opponent_username=game_data.get("opponent_username"),
                opponent_rating=game_data.get("opponent_rating"),
                result=game_data["result"],
                time_control=game_data.get("time_control"),
                played_at=game_data["played_at"],
                opening_eco=game_data.get("opening_eco"),
                opening_name=game_data.get("opening_name"),
                pgn=game_data["pgn"],
                analyzed_at=game_data.get("analyzed_at"),
            )
            session.add(game)
            session.commit()
            session.refresh(game)
            return _game_to_dict(game)

    def get_game(self, game_id: str) -> Optional[dict]:
        """Retrieve a game by ID as a detached-safe dict."""
        with self.get_session() as session:
            game = session.query(Game).filter_by(game_id=game_id).first()
            return _game_to_dict(game) if game else None

    def get_recent_games(
        self,
        limit: int = 10,
        username: Optional[str] = None,
    ) -> List[dict]:
        """Get most recently played games as detached-safe dicts.

        If ``username`` is given, only that player's games are returned
        (case-insensitive match).
        """
        with self.get_session() as session:
            query = session.query(Game)
            if username:
                query = query.filter(func.lower(Game.username) == username.lower())
            games = (
                query.order_by(Game.played_at.desc())
                .limit(limit)
                .all()
            )
            return [_game_to_dict(g) for g in games]

    def list_usernames(self) -> List[str]:
        """List distinct player handles that have games stored."""
        with self.get_session() as session:
            rows = (
                session.query(Game.username)
                .distinct()
                .order_by(Game.username)
                .all()
            )
            return [r[0] for r in rows]
    
    def game_exists(self, game_id: str) -> bool:
        """Check if a game already exists in the database."""
        with self.get_session() as session:
            return session.query(Game).filter_by(game_id=game_id).first() is not None
    
    # Position operations
    
    def save_analysis(self, game_id: str, positions: List[dict]) -> None:
        """Save position analyses for a game."""
        with self.get_session() as session:
            game = session.query(Game).filter_by(game_id=game_id).first()
            if not game:
                raise ValueError(f"Game {game_id} not found")
            for pos_data in positions:
                position = Position(
                    game_id=game.id,
                    move_number=pos_data["move_number"],
                    fen=pos_data["fen"],
                    move_played=pos_data["move_played"],
                    eval_before=pos_data.get("eval_before"),
                    eval_after=pos_data.get("eval_after"),
                    centipawn_loss=pos_data.get("centipawn_loss"),
                    depth=pos_data.get("depth", 20),
                    best_move=pos_data.get("best_move"),
                    best_move_eval=pos_data.get("best_move_eval"),
                    top_3_moves=pos_data.get("top_3_moves"),
                    classification=pos_data.get("classification"),
                    is_blunder=pos_data.get("is_blunder", False),
                    is_missed_tactic=pos_data.get("is_missed_tactic", False),
                    mate_in=pos_data.get("mate_in"),
                    explanation=pos_data.get("explanation"),
                )
                session.add(position)
            game.analyzed_at = datetime.utcnow()
            session.commit()

    def get_game_analysis(self, game_id: str) -> List[dict]:
        """Get all position analyses for a game as detached-safe dicts."""
        with self.get_session() as session:
            game = session.query(Game).filter_by(game_id=game_id).first()
            if not game:
                return []
            positions = (
                session.query(Position)
                .filter_by(game_id=game.id)
                .order_by(Position.move_number)
                .all()
            )
            return [_position_to_dict(p) for p in positions]

    def save_position_explanation(self, position_id: int, explanation: str) -> None:
        """Persist an LLM explanation for a single analyzed position (cache)."""
        with self.get_session() as session:
            position = session.query(Position).filter_by(id=position_id).first()
            if position is None:
                raise ValueError(f"Position {position_id} not found")
            position.explanation = explanation
            session.commit()

    def get_position(self, position_id: int) -> Optional[dict]:
        """Fetch a single analyzed position by its id as a detached-safe dict."""
        with self.get_session() as session:
            position = session.query(Position).filter_by(id=position_id).first()
            return _position_to_dict(position) if position else None

    def get_blunders(self, limit: int = 20) -> List[dict]:
        """Get recent blunder positions for review as detached-safe dicts."""
        with self.get_session() as session:
            positions = (
                session.query(Position)
                .filter_by(is_blunder=True)
                .order_by(Position.created_at.desc())
                .limit(limit)
                .all()
            )
            return [_position_to_dict(p) for p in positions]

    # Aggregation / analytics (feeds pattern detection and RAG documents)

    def _analyzed_position_rows(self, username: Optional[str] = None) -> List[dict]:
        """Flat list of analyzed positions joined to their game's string id.

        One query (Position JOIN Game) instead of per-game lookups, so the
        aggregations below scale to hundreds of games. Optionally scoped to one
        player (case-insensitive).
        """
        with self.get_session() as session:
            query = (
                session.query(
                    Game.game_id,
                    Position.move_number,
                    Position.centipawn_loss,
                    Position.is_blunder,
                )
                .join(Position, Position.game_id == Game.id)
            )
            if username:
                query = query.filter(func.lower(Game.username) == username.lower())
            return [
                {
                    "game_id": gid,
                    "move_number": move_number,
                    "centipawn_loss": cp or 0.0,
                    "is_blunder": bool(is_blunder),
                }
                for gid, move_number, cp, is_blunder in query.all()
            ]

    def _per_game_cp_stats(self, username: Optional[str] = None) -> dict:
        """Map game_id -> {cp_sum, positions, blunders} from analyzed positions."""
        stats: dict = {}
        for row in self._analyzed_position_rows(username):
            s = stats.setdefault(
                row["game_id"], {"cp_sum": 0.0, "positions": 0, "blunders": 0}
            )
            s["cp_sum"] += row["centipawn_loss"]
            s["positions"] += 1
            s["blunders"] += 1 if row["is_blunder"] else 0
        return stats

    def get_critical_mistake_contexts(
        self, username: Optional[str] = None
    ) -> List[dict]:
        """Blunders + mistakes joined to game context, for pattern detection.

        Each row carries the string ``game_id`` and opening so patterns can be
        attributed to phases and openings and cite example games.
        """
        with self.get_session() as session:
            query = (
                session.query(
                    Game.game_id,
                    Game.opening_name,
                    Game.opening_eco,
                    Position.move_number,
                    Position.is_missed_tactic,
                    Position.is_blunder,
                    Position.classification,
                )
                .join(Position, Position.game_id == Game.id)
                .filter(
                    (Position.is_blunder.is_(True))
                    | (Position.classification == "mistake")
                )
            )
            if username:
                query = query.filter(func.lower(Game.username) == username.lower())
            return [
                {
                    "game_id": gid,
                    "opening_name": oname,
                    "opening_eco": eco,
                    "move_number": move_number,
                    "is_missed_tactic": bool(missed),
                    "is_blunder": bool(is_blunder),
                    "classification": classification,
                }
                for (
                    gid, oname, eco, move_number, missed, is_blunder, classification
                ) in query.all()
            ]

    def aggregate_by_opening(self, username: Optional[str] = None) -> List[dict]:
        """Per-opening rollup: games, W/D/L, score%, avg cp loss, blunders."""
        games = self.get_recent_games(limit=10_000_000, username=username)
        cp_stats = self._per_game_cp_stats(username)
        groups: dict = {}
        for g in games:
            key = g["opening_name"] or g["opening_eco"] or "Unknown opening"
            grp = groups.setdefault(
                key,
                {
                    "opening": key,
                    "eco": g["opening_eco"],
                    "games": 0, "wins": 0, "draws": 0, "losses": 0,
                    "as_white": 0, "as_black": 0,
                    "cp_sum": 0.0, "positions": 0, "blunders": 0,
                },
            )
            grp["games"] += 1
            grp["as_white" if g["color"] == "white" else "as_black"] += 1
            outcome = _game_outcome(g["result"], g["color"])
            grp[{"win": "wins", "draw": "draws", "loss": "losses"}[outcome]] += 1
            s = cp_stats.get(g["game_id"])
            if s:
                grp["cp_sum"] += s["cp_sum"]
                grp["positions"] += s["positions"]
                grp["blunders"] += s["blunders"]
        return _finalize_groups(groups)

    def aggregate_by_time_control(self, username: Optional[str] = None) -> List[dict]:
        """Per-speed-bucket rollup (bullet/blitz/rapid/...): games, score%, cp."""
        games = self.get_recent_games(limit=10_000_000, username=username)
        cp_stats = self._per_game_cp_stats(username)
        groups: dict = {}
        for g in games:
            key = speed_bucket(g["time_control"], g["platform"])
            grp = groups.setdefault(
                key,
                {
                    "time_control": key,
                    "games": 0, "wins": 0, "draws": 0, "losses": 0,
                    "as_white": 0, "as_black": 0,
                    "cp_sum": 0.0, "positions": 0, "blunders": 0,
                },
            )
            grp["games"] += 1
            grp["as_white" if g["color"] == "white" else "as_black"] += 1
            outcome = _game_outcome(g["result"], g["color"])
            grp[{"win": "wins", "draw": "draws", "loss": "losses"}[outcome]] += 1
            s = cp_stats.get(g["game_id"])
            if s:
                grp["cp_sum"] += s["cp_sum"]
                grp["positions"] += s["positions"]
                grp["blunders"] += s["blunders"]
        return _finalize_groups(groups, key="time_control")

    def aggregate_by_phase(self, username: Optional[str] = None) -> List[dict]:
        """Per-phase rollup: moves, avg cp loss, blunder count and rate."""
        buckets = {
            p: {"phase": p, "moves": 0, "cp_sum": 0.0, "blunders": 0}
            for p in ("opening", "middlegame", "endgame")
        }
        for row in self._analyzed_position_rows(username):
            b = buckets[_phase_for_move(row["move_number"])]
            b["moves"] += 1
            b["cp_sum"] += row["centipawn_loss"]
            b["blunders"] += 1 if row["is_blunder"] else 0
        result = []
        for p in ("opening", "middlegame", "endgame"):
            b = buckets[p]
            moves = b["moves"]
            result.append(
                {
                    "phase": p,
                    "moves": moves,
                    "avg_cp_loss": round(b["cp_sum"] / moves, 1) if moves else 0.0,
                    "blunders": b["blunders"],
                    "blunder_rate": round(b["blunders"] / moves, 3) if moves else 0.0,
                }
            )
        return result

    # Opening operations
    
    def update_opening_stats(self, eco_code: str, game_result: dict) -> None:
        """Update statistics for an opening."""
        with self.get_session() as session:
            opening = session.query(Opening).filter_by(eco_code=eco_code).first()
            if not opening:
                opening = Opening(eco_code=eco_code, name=game_result.get("opening_name", ""))
                session.add(opening)

            color = game_result.get("color")
            result = game_result.get("result")
            cp_loss = game_result.get("avg_cp_loss")

            if color == "white":
                opening.games_as_white = (opening.games_as_white or 0) + 1
                if result == "1-0":
                    opening.wins_as_white = (opening.wins_as_white or 0) + 1
                elif result == "1/2-1/2":
                    opening.draws_as_white = (opening.draws_as_white or 0) + 1
                if cp_loss is not None:
                    n = opening.games_as_white
                    opening.avg_cp_loss_white = ((opening.avg_cp_loss_white or 0) * (n - 1) + cp_loss) / n
            elif color == "black":
                opening.games_as_black = (opening.games_as_black or 0) + 1
                if result == "0-1":
                    opening.wins_as_black = (opening.wins_as_black or 0) + 1
                elif result == "1/2-1/2":
                    opening.draws_as_black = (opening.draws_as_black or 0) + 1
                if cp_loss is not None:
                    n = opening.games_as_black
                    opening.avg_cp_loss_black = ((opening.avg_cp_loss_black or 0) * (n - 1) + cp_loss) / n

            opening.last_played = game_result.get("played_at", datetime.utcnow())
            session.commit()

    def get_opening_stats(self, eco_code: Optional[str] = None) -> List[dict]:
        """Get opening statistics as detached-safe dicts, optionally filtered."""
        with self.get_session() as session:
            query = session.query(Opening)
            if eco_code:
                query = query.filter_by(eco_code=eco_code)
            openings = query.order_by(Opening.last_played.desc()).all()
            return [_opening_to_dict(o) for o in openings]
    
    # Pattern operations
    
    def save_pattern(self, pattern_data: dict) -> dict:
        """Upsert a recurring pattern keyed on (pattern_type, phase, description).

        On a repeat sighting we accumulate rather than duplicate: bump
        ``occurrence_count``, union the example game ids / associated openings,
        and refresh ``last_seen`` — so the Pattern table becomes a persistent
        model of the player's habits across many sync/analyze runs.
        """
        with self.get_session() as session:
            pattern = (
                session.query(Pattern)
                .filter_by(
                    pattern_type=pattern_data["pattern_type"],
                    phase=pattern_data.get("phase"),
                    description=pattern_data["description"],
                )
                .first()
            )
            inc = pattern_data.get("occurrence_count", 1)
            new_games = pattern_data.get("example_game_ids") or []
            new_openings = pattern_data.get("associated_openings") or []

            if pattern is None:
                pattern = Pattern(
                    pattern_type=pattern_data["pattern_type"],
                    description=pattern_data["description"],
                    occurrence_count=inc,
                    severity=pattern_data.get("severity"),
                    phase=pattern_data.get("phase"),
                    associated_openings=list(dict.fromkeys(new_openings)),
                    example_game_ids=list(dict.fromkeys(new_games)),
                    coaching_advice=pattern_data.get("coaching_advice"),
                )
                session.add(pattern)
            else:
                pattern.occurrence_count = (pattern.occurrence_count or 0) + inc
                pattern.example_game_ids = _union(
                    pattern.example_game_ids, new_games
                )
                pattern.associated_openings = _union(
                    pattern.associated_openings, new_openings
                )
                pattern.last_seen = datetime.utcnow()
                if pattern_data.get("severity"):
                    pattern.severity = pattern_data["severity"]
                if pattern_data.get("coaching_advice"):
                    pattern.coaching_advice = pattern_data["coaching_advice"]

            session.commit()
            session.refresh(pattern)
            return _pattern_to_dict(pattern)

    def get_patterns(
        self,
        pattern_type: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> List[dict]:
        """Get patterns as detached-safe dicts, optionally filtered."""
        with self.get_session() as session:
            query = session.query(Pattern)
            if pattern_type:
                query = query.filter_by(pattern_type=pattern_type)
            if phase:
                query = query.filter_by(phase=phase)
            patterns = query.order_by(Pattern.occurrence_count.desc()).all()
            return [_pattern_to_dict(p) for p in patterns]
    
    # Embedding / knowledge-base operations (RAG)

    def clear_embeddings(self, username: Optional[str] = None) -> None:
        """Delete stored embeddings (optionally only for one player's scope)."""
        with self.get_session() as session:
            query = session.query(Embedding)
            if username is not None:
                query = query.filter(func.lower(Embedding.username) == username.lower())
            query.delete(synchronize_session=False)
            session.commit()

    def save_embeddings(self, rows: List[dict]) -> None:
        """Persist a batch of RAG documents + their vectors."""
        with self.get_session() as session:
            for row in rows:
                session.add(
                    Embedding(
                        doc_id=row["doc_id"],
                        source_type=row["source_type"],
                        username=row.get("username"),
                        text=row["text"],
                        vector=row["vector"],
                    )
                )
            session.commit()

    def get_embeddings(self, username: Optional[str] = None) -> List[dict]:
        """Load stored RAG documents + vectors as detached-safe dicts."""
        with self.get_session() as session:
            query = session.query(Embedding)
            if username is not None:
                query = query.filter(func.lower(Embedding.username) == username.lower())
            return [
                {
                    "doc_id": e.doc_id,
                    "source_type": e.source_type,
                    "username": e.username,
                    "text": e.text,
                    "vector": e.vector,
                }
                for e in query.all()
            ]

    # Sync state operations

    def get_last_sync(self, platform: str, username: str) -> Optional[datetime]:
        """Get last sync timestamp for a platform/username."""
        with self.get_session() as session:
            state = session.query(SyncState).filter_by(
                platform=platform,
                username=username,
            ).first()
            return state.last_synced_at if state else None
    
    def update_last_sync(
        self,
        platform: str,
        username: str,
        timestamp: datetime,
    ) -> None:
        """Update last sync timestamp."""
        with self.get_session() as session:
            state = session.query(SyncState).filter_by(
                platform=platform,
                username=username,
            ).first()
            
            if state:
                state.last_synced_at = timestamp
            else:
                state = SyncState(
                    platform=platform,
                    username=username,
                    last_synced_at=timestamp,
                )
                session.add(state)
            
            session.commit()
