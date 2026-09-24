"""Chess coaching agent that provides personalized insights."""

from typing import Dict, List, Optional

from ..analysis.llm_explainer import LLMExplainer
from ..analysis.models import (
    GameAnalysisSummary,
    MoveClassification,
    PositionAnalysis,
)
from ..storage.database import Database


class CoachError(Exception):
    """Raised when a coaching request cannot be fulfilled (e.g. no analysis)."""


class Coach:
    """High-level coaching interface combining analysis and insights."""

    def __init__(self, db: Database, explainer: LLMExplainer):
        """
        Initialize coach.

        Args:
            db: Database instance
            explainer: LLM explainer for generating insights
        """
        self.db = db
        self.explainer = explainer

    # -- Primary path (coach --game-id) -----------------------------------

    def coach_game(self, game_id: str) -> str:
        """Produce a coaching writeup for a single analyzed game (1 LLM call).

        Raises:
            CoachError: if the game is unknown or has not been analyzed yet.
        """
        game = self.db.get_game(game_id)
        if game is None:
            raise CoachError(
                f"No game with id '{game_id}' in the database. Run `sync` first, "
                "or check the id with `stats`."
            )

        position_dicts = self.db.get_game_analysis(game_id)
        if not position_dicts:
            raise CoachError(
                f"Game '{game_id}' has not been analyzed yet. Run "
                f"`analyze --game-id {game_id}` first."
            )

        analyses = [_position_from_dict(p, game_id) for p in position_dicts]
        summary = build_game_summary(game_id, analyses)
        game_context = {
            "color": game.get("color"),
            "result": game.get("result"),
            "opponent_username": game.get("opponent_username"),
            "opening_name": game.get("opening_name"),
        }
        return self.explainer.summarize_game(summary, analyses, game_context)

    def ask(
        self,
        question: str,
        k: int = 5,
        username: Optional[str] = None,
    ):
        """Answer a natural-language question via RAG (1 embedding + 1 completion).

        Returns (answer, retrieved_docs). Delegates to the Knowledge layer.
        """
        from .knowledge import Knowledge  # local import avoids an import cycle

        knowledge = Knowledge(self.db, self.explainer)
        return knowledge.answer(question, k=k, username=username)

    # -- Secondary helpers (no extra LLM cost unless noted) ---------------

    def review_recent_games(
        self,
        count: int = 5,
        username: Optional[str] = None,
    ) -> List[Dict]:
        """Quick, LLM-free review of recent games with key numbers.

        Optionally scoped to a single player's games via ``username``.
        """
        reviews: List[Dict] = []
        for game in self.db.get_recent_games(limit=count, username=username):
            analyses = [
                _position_from_dict(p, game["game_id"])
                for p in self.db.get_game_analysis(game["game_id"])
            ]
            summary = build_game_summary(game["game_id"], analyses) if analyses else None
            reviews.append(
                {
                    "game_id": game["game_id"],
                    "color": game["color"],
                    "result": game["result"],
                    "opponent": game["opponent_username"],
                    "opening": game["opening_name"],
                    "analyzed": summary is not None,
                    "blunders": summary.blunders if summary else None,
                    "mistakes": summary.mistakes if summary else None,
                    "avg_cp_loss": summary.avg_centipawn_loss if summary else None,
                }
            )
        return reviews

    def analyze_opening(
        self,
        opening_name: Optional[str] = None,
        eco_code: Optional[str] = None,
    ) -> str:
        """Coaching report for an opening from aggregate stats (1 LLM call)."""
        stats = self.db.get_opening_stats(eco_code=eco_code)
        if opening_name and not eco_code:
            stats = [s for s in stats if opening_name.lower() in (s["name"] or "").lower()]
        if not stats:
            raise CoachError(
                "No opening statistics found for that filter. Sync and analyze "
                "some games first."
            )
        return self.explainer.generate_coaching_report(
            opening=opening_name or (stats[0]["name"] if stats else None),
            games_data={"openings": stats},
        )

    def get_improvement_areas(self, days: int = 30) -> Dict[str, object]:
        """LLM-free rollup of recent blunders/mistakes as improvement signals."""
        blunders = self.db.get_blunders(limit=100)
        by_phase: Dict[str, int] = {"opening": 0, "middlegame": 0, "endgame": 0}
        for pos in blunders:
            by_phase[_phase_for_move(pos["move_number"])] += 1
        return {
            "total_blunders": len(blunders),
            "blunders_by_phase": by_phase,
        }

    def explain_critical_mistakes(
        self,
        game_id: str,
        max_explanations: int = 3,
    ) -> List[Dict]:
        """Explain a game's worst mistakes (the two-tier LLM layer).

        Stockfish does all the evaluation; the LLM is spent only on the few most
        costly moments. Explanations are capped at ``max_explanations``, cached in
        ``Position.explanation``, and reused on re-runs (no repeat LLM calls).

        Returns a list of {move_number, played, best, centipawn_loss, explanation}.
        """
        positions = self.db.get_game_analysis(game_id)
        if not positions:
            raise CoachError(
                f"Game '{game_id}' has not been analyzed yet. Run "
                f"`analyze --game-id {game_id}` first."
            )

        # Worst first: blunders and mistakes ranked by centipawn loss.
        critical = [
            p for p in positions
            if p.get("is_blunder") or p.get("classification") in ("blunder", "mistake")
        ]
        critical.sort(key=lambda p: p.get("centipawn_loss") or 0.0, reverse=True)

        results: List[Dict] = []
        for pos in critical[:max_explanations]:
            explanation = pos.get("explanation")
            if not explanation:  # generate + cache only when missing
                analysis = _position_from_dict(pos, game_id)
                explanation = self.explainer.explain_position(analysis)
                self.db.save_position_explanation(pos["id"], explanation)
            results.append(
                {
                    "move_number": pos["move_number"],
                    "move_played": pos["move_played"],
                    "best_move": pos.get("best_move"),
                    "centipawn_loss": pos.get("centipawn_loss"),
                    "explanation": explanation,
                }
            )
        return results

    def get_position_explanation(self, game_id: str, move_number: int) -> str:
        """Explain a specific position; returns cached text if already present."""
        for pos in self.db.get_game_analysis(game_id):
            if pos["move_number"] == move_number:
                if pos.get("explanation"):
                    return pos["explanation"]
                analysis = _position_from_dict(pos, game_id)
                return self.explainer.explain_position(analysis)
        raise CoachError(
            f"No analyzed position at move {move_number} in game '{game_id}'."
        )

    def detect_and_persist_patterns(
        self,
        username: Optional[str] = None,
        min_occurrences: int = 3,
    ) -> List[Dict]:
        """Detect recurring mistake patterns and persist them (LLM-free).

        Scans every analyzed game's blunders/mistakes and derives three families
        of pattern — by phase, by opening, and missed tactics — then upserts each
        into the ``patterns`` table so the model accumulates across runs. Only
        example games not already recorded add to a pattern's count, so re-running
        after new games is additive rather than double-counting.

        Returns the persisted pattern rows (as dicts).
        """
        rows = self.db.get_critical_mistake_contexts(username)
        candidates = _build_pattern_candidates(rows, min_occurrences)

        # Pre-read existing example sets so repeat detection is idempotent.
        existing = {
            _pattern_signature(p): set(p.get("example_game_ids") or [])
            for p in self.db.get_patterns()
        }

        persisted: List[Dict] = []
        for cand in candidates:
            sig = _pattern_signature(cand)
            already = existing.get(sig, set())
            new_games = [g for g in cand["example_game_ids"] if g not in already]
            # First sighting: count everything. Later: only the new games.
            cand["occurrence_count"] = (
                cand["occurrence_count"] if not already else len(new_games)
            )
            persisted.append(self.db.save_pattern(cand))
        return persisted


# -- Module-level helpers --------------------------------------------------


def _pattern_signature(pattern: dict) -> tuple:
    """Stable identity for a pattern: (type, phase, description)."""
    return (
        pattern.get("pattern_type"),
        pattern.get("phase"),
        pattern.get("description"),
    )


def _severity_for(count: int) -> str:
    """Map an occurrence count to a coarse severity label."""
    if count >= 10:
        return "high"
    if count >= 5:
        return "medium"
    return "low"


def _build_pattern_candidates(rows: List[dict], min_occurrences: int) -> List[Dict]:
    """Derive pattern candidates from critical-mistake rows.

    Three families:
      - phase weakness: mistakes concentrated in opening/middlegame/endgame
      - opening weakness: mistakes recurring in a specific opening
      - missed tactics: positions where a tactic was available and not taken
    Only families meeting ``min_occurrences`` are returned.
    """
    by_phase: Dict[str, list] = {}
    by_opening: Dict[str, list] = {}
    missed_tactic_games: list = []

    for r in rows:
        phase = _phase_for_move(r["move_number"])
        by_phase.setdefault(phase, []).append(r)
        opening = r.get("opening_name") or r.get("opening_eco")
        if opening:
            by_opening.setdefault(opening, []).append(r)
        if r.get("is_missed_tactic"):
            missed_tactic_games.append(r["game_id"])

    candidates: List[Dict] = []

    for phase, items in by_phase.items():
        if len(items) < min_occurrences:
            continue
        games = list(dict.fromkeys(i["game_id"] for i in items))
        ecos = list(dict.fromkeys(i["opening_eco"] for i in items if i["opening_eco"]))
        candidates.append(
            {
                "pattern_type": "phase_weakness",
                "phase": phase,
                "description": f"Recurring mistakes in the {phase}",
                "occurrence_count": len(items),
                "severity": _severity_for(len(items)),
                "associated_openings": ecos,
                "example_game_ids": games[:10],
                "coaching_advice": (
                    f"Slow down in the {phase}: {len(items)} blunders/mistakes "
                    f"across {len(games)} games cluster here."
                ),
            }
        )

    for opening, items in by_opening.items():
        if len(items) < min_occurrences:
            continue
        games = list(dict.fromkeys(i["game_id"] for i in items))
        eco = next((i["opening_eco"] for i in items if i["opening_eco"]), None)
        candidates.append(
            {
                "pattern_type": "opening_weakness",
                "phase": "all",
                "description": f"Mistakes recurring in {opening}",
                "occurrence_count": len(items),
                "severity": _severity_for(len(items)),
                "associated_openings": [eco] if eco else [],
                "example_game_ids": games[:10],
                "coaching_advice": (
                    f"Review your lines in {opening}: {len(items)} mistakes across "
                    f"{len(games)} games."
                ),
            }
        )

    unique_missed_games = list(dict.fromkeys(missed_tactic_games))
    if len(unique_missed_games) >= min_occurrences:
        candidates.append(
            {
                "pattern_type": "missed_tactics",
                "phase": "all",
                "description": "Missed tactical opportunities",
                "occurrence_count": len(missed_tactic_games),
                "severity": _severity_for(len(missed_tactic_games)),
                "associated_openings": [],
                "example_game_ids": unique_missed_games[:10],
                "coaching_advice": (
                    "Work on tactics: forcing moves (checks, captures, threats) "
                    "were available and missed in several games."
                ),
            }
        )

    return candidates


def _phase_for_move(move_number: int) -> str:
    """Bucket a full-move number into opening / middlegame / endgame."""
    if move_number <= 15:
        return "opening"
    if move_number <= 40:
        return "middlegame"
    return "endgame"


def _position_from_dict(pos: dict, game_id: str) -> PositionAnalysis:
    """Reconstruct a PositionAnalysis from a stored position dict."""
    classification = (
        MoveClassification(pos["classification"])
        if pos.get("classification")
        else MoveClassification.GOOD
    )
    analysis = PositionAnalysis(
        game_id=game_id,
        move_number=pos["move_number"],
        fen=pos["fen"],
        move_played=pos["move_played"],
        eval_before=pos.get("eval_before") or 0.0,
        eval_after=pos.get("eval_after") or 0.0,
        centipawn_loss=pos.get("centipawn_loss") or 0.0,
        best_move=pos.get("best_move") or "",
        best_move_eval=pos.get("best_move_eval") or 0.0,
        top_3_moves=pos.get("top_3_moves") or [],
        classification=classification,
        depth=pos.get("depth") or 20,
        mate_in=pos.get("mate_in"),
    )
    # __post_init__ recomputes centipawn_loss/is_blunder; restore stored flags.
    analysis.is_missed_tactic = bool(pos.get("is_missed_tactic"))
    analysis.explanation = pos.get("explanation")
    return analysis


def build_game_summary(
    game_id: str,
    analyses: List[PositionAnalysis],
) -> GameAnalysisSummary:
    """Aggregate per-position analyses into a GameAnalysisSummary."""
    counts = {c: 0 for c in MoveClassification}
    for a in analyses:
        counts[a.classification] += 1

    total = len(analyses)
    avg_cp = (
        sum(a.centipawn_loss for a in analyses) / total if total else 0.0
    )

    def phase_avg(predicate) -> float:
        vals = [a.centipawn_loss for a in analyses if predicate(a.move_number)]
        return sum(vals) / len(vals) if vals else 0.0

    return GameAnalysisSummary(
        game_id=game_id,
        total_moves=total,
        best_moves=counts[MoveClassification.BEST] + counts[MoveClassification.EXCELLENT],
        good_moves=counts[MoveClassification.GOOD],
        inaccuracies=counts[MoveClassification.INACCURACY],
        mistakes=counts[MoveClassification.MISTAKE],
        blunders=counts[MoveClassification.BLUNDER],
        avg_centipawn_loss=avg_cp,
        blunder_positions=[a for a in analyses if a.is_blunder],
        missed_tactics=[a for a in analyses if a.is_missed_tactic],
        opening_accuracy=phase_avg(lambda m: m <= 15),
        middlegame_accuracy=phase_avg(lambda m: 15 < m <= 40),
        endgame_accuracy=phase_avg(lambda m: m > 40),
    )
