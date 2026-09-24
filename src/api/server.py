"""FastAPI app exposing the chess coach to the desktop UI.

Thin HTTP adapter over the existing modules. Build the shared Config + Database
once at import; construct the (cheap) explainer/coach per request. Piece-markup
is enabled on the API's explainer so coach prose carries ``{{wN}}`` tokens the
renderer turns into pixel icons — the CLI is unaffected.
"""

from __future__ import annotations

import io
import threading
from typing import Optional

import chess
import chess.pgn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..analysis.llm_explainer import LLMError, LLMExplainer
from ..coaching.coach import Coach, CoachError, build_game_summary
from ..coaching.knowledge import KnowledgeError
from ..config import Config, ConfigError
from ..storage.database import Database
from .jobs import JobStore, run_session_job

app = FastAPI(title="Chess Coach API")

# The renderer runs from the Vite dev server or an Electron file:// origin; allow
# both by permitting any local origin (the server binds to 127.0.0.1 only).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_jobs = JobStore()
_state_lock = threading.Lock()
_config: Optional[Config] = None
_db: Optional[Database] = None


def _state():
    """Lazily build and cache the shared Config + Database."""
    global _config, _db
    with _state_lock:
        if _config is None:
            try:
                _config = Config.load_and_validate()
            except ConfigError as exc:
                raise HTTPException(status_code=500, detail=str(exc))
            _db = Database(_config.db_path)
        return _config, _db


def _explainer(config: Config, piece_markup: bool = True) -> LLMExplainer:
    return LLMExplainer(
        config.openai_api_key,
        model=config.openai_model,
        user_rating=config.user_rating,
        embedding_model=config.embedding_model,
        piece_markup=piece_markup,
    )


# -- Schemas ---------------------------------------------------------------


class SessionRequest(BaseModel):
    platform: str = "chesscom"
    username: str


class ChatRequest(BaseModel):
    username: Optional[str] = None
    message: str


# -- Endpoints -------------------------------------------------------------


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/session")
def start_session(req: SessionRequest):
    """Kick off the sync+analyze+index pipeline in a worker thread."""
    if req.platform not in ("chesscom", "lichess"):
        raise HTTPException(status_code=400, detail=f"Unknown platform '{req.platform}'.")
    if not req.username.strip():
        raise HTTPException(status_code=400, detail="A username is required.")

    config, db = _state()
    job = _jobs.create(req.platform, req.username.strip())
    threading.Thread(
        target=run_session_job, args=(job, config, db), daemon=True
    ).start()
    return {"job_id": job.id}


@app.get("/api/session/{job_id}")
def session_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job.")
    return job.to_dict()


@app.get("/api/games")
def list_games(username: Optional[str] = None, limit: int = 50):
    _, db = _state()
    games = db.get_recent_games(limit=limit, username=username)
    return {
        "games": [
            {
                "game_id": g["game_id"],
                "platform": g["platform"],
                "color": g["color"],
                "result": g["result"],
                "opponent": g["opponent_username"],
                "opening": g["opening_name"],
                "played_at": g["played_at"],
                "analyzed": g["analyzed_at"] is not None,
            }
            for g in games
        ]
    }


@app.get("/api/games/{game_id}/review")
def game_review(game_id: str):
    """Per-ply positions (FEN + annotation) for the board + review pane."""
    _, db = _state()
    game = db.get_game(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail=f"No game '{game_id}'.")

    moves = _review_moves(game["pgn"], db.get_game_analysis(game_id))
    summary = None
    analysis = db.get_game_analysis(game_id)
    if analysis:
        from ..coaching.coach import _position_from_dict

        parsed = [_position_from_dict(p, game_id) for p in analysis]
        s = build_game_summary(game_id, parsed)
        summary = {
            "total_moves": s.total_moves,
            "blunders": s.blunders,
            "mistakes": s.mistakes,
            "inaccuracies": s.inaccuracies,
            "avg_centipawn_loss": s.avg_centipawn_loss,
        }
    return {
        "game_id": game_id,
        "color": game["color"],
        "result": game["result"],
        "opening": game["opening_name"],
        "summary": summary,
        "moves": moves,
    }


@app.post("/api/games/{game_id}/coach")
def coach_game(game_id: str):
    """Coaching writeup for a game + the key blunder position for the board."""
    config, db = _state()
    coach = Coach(db, _explainer(config))
    try:
        writeup = coach.coach_game(game_id)
    except CoachError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    key_fen = _key_position_fen(db.get_game(game_id)["pgn"], db.get_game_analysis(game_id))
    return {"writeup": writeup, "key_fen": key_fen}


@app.post("/api/positions/{position_id}/explain")
def explain_position(position_id: int):
    """Explain one move on demand (cached in Position.explanation after first call)."""
    config, db = _state()
    pos = db.get_position(position_id)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"No position {position_id}.")
    if pos.get("explanation"):
        return {"explanation": pos["explanation"], "cached": True}

    from ..coaching.coach import _position_from_dict

    analysis = _position_from_dict(pos, "")  # game_id only stamps the object; unused here
    try:
        text = _explainer(config).explain_position(analysis)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    db.save_position_explanation(position_id, text)
    return {"explanation": text, "cached": False}


@app.post("/api/chat")
def chat(req: ChatRequest):
    """Answer a natural-language question via RAG (1 embedding + 1 completion)."""
    config, db = _state()
    coach = Coach(db, _explainer(config))
    try:
        answer, docs = coach.ask(
            req.message, k=config.rag_top_k, username=req.username
        )
    except KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "answer": answer,
        "sources": [
            {"text": d["text"], "score": d["score"], "source_type": d["source_type"]}
            for d in docs
        ],
    }


# -- Helpers ---------------------------------------------------------------


def _review_moves(pgn: str, analysis: list) -> list:
    """Zip PGN mainline moves with stored analysis into per-ply records.

    Analysis is sorted by insertion id (== ply order) so half-moves that share a
    full-move number stay correctly aligned.
    """
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return []
    ann = sorted(analysis, key=lambda a: a.get("id", 0))

    board = game.board()
    out = []
    for i, move in enumerate(game.mainline_moves()):
        a = ann[i] if i < len(ann) else {}
        san = board.san(move)
        best_san = None
        best_uci = a.get("best_move")
        if best_uci:
            try:
                best_san = board.san(chess.Move.from_uci(best_uci))
            except (ValueError, chess.IllegalMoveError):
                best_san = best_uci
        board.push(move)
        out.append(
            {
                "ply": i + 1,
                "move_number": (i // 2) + 1,
                "san": san,
                "fen": board.fen(),
                "classification": a.get("classification"),
                "centipawn_loss": a.get("centipawn_loss"),
                "best_move_san": best_san,
                "is_blunder": bool(a.get("is_blunder")),
                "position_id": a.get("id"),
                "explanation": a.get("explanation"),
            }
        )
    return out


def _key_position_fen(pgn: str, analysis: list) -> Optional[str]:
    """FEN of the position after the single most costly mistake (for the board)."""
    moves = _review_moves(pgn, analysis)
    critical = [m for m in moves if m["centipawn_loss"] is not None]
    if not critical:
        return None
    worst = max(critical, key=lambda m: m["centipawn_loss"])
    return worst["fen"]
