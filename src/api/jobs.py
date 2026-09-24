"""Background session jobs (sync → analyze → index) + a thread-safe registry.

The gate screen's "syncing…" bar is driven by one of these jobs. The heavy work
(network sync, Stockfish analysis, embedding) runs in a worker thread so the
FastAPI event loop stays responsive; the job object is updated in place and the
renderer polls ``GET /api/session/{job_id}`` for progress.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, Optional

from ..analysis import StockfishAnalyzer
from ..analysis.llm_explainer import LLMExplainer
from ..coaching.coach import Coach, build_game_summary
from ..coaching.knowledge import Knowledge
from ..config import Config
from ..ingestion.chesscom import ChessComIngester
from ..ingestion.chesscom import IngestionError as ChessComIngestionError
from ..ingestion.lichess import IngestionError as LichessIngestionError
from ..ingestion.lichess import LichessIngester
from ..storage.database import Database

_INGESTION_ERRORS = (ChessComIngestionError, LichessIngestionError)

# How many recent games the gate flow pulls + analyzes on first submit.
_DEFAULT_SYNC_LIMIT = 20


@dataclass
class Job:
    """Progress record for one sync+analyze+index run."""

    id: str
    platform: str
    username: str
    state: str = "pending"  # pending | running | ready | error
    phase: str = "queued"   # validating | syncing | analyzing | indexing | ready
    done: int = 0
    total: int = 0
    message: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class JobStore:
    """Thread-safe in-memory registry of jobs."""

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, platform: str, username: str) -> Job:
        job = Job(id=uuid.uuid4().hex, platform=platform, username=username)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)


def _ingester_for(platform: str, config: Config, db: Database):
    if platform == "chesscom":
        return ChessComIngester(db)
    return LichessIngester(db, token=config.lichess_token)


def run_session_job(job: Job, config: Config, db: Database) -> None:
    """Execute the full gate pipeline, updating ``job`` in place.

    Phases: validate the handle → sync recent games → analyze the unanalyzed ones
    with Stockfish → detect patterns + build the RAG index → ready.
    """
    job.state = "running"
    try:
        ingester = _ingester_for(job.platform, config, db)

        # -- validate + sync -------------------------------------------------
        job.phase = "syncing"
        job.message = f"Fetching games for {job.username}…"
        since = ingester.get_last_synced(job.username)
        try:
            games = ingester.fetch_games(
                job.username, since=since, limit=_DEFAULT_SYNC_LIMIT
            )
        except _INGESTION_ERRORS as exc:
            job.state = "error"
            job.error = str(exc)
            return

        newest = since
        for game in games:
            if not db.game_exists(game.game_id):
                db.save_game(asdict(game))
            if newest is None or game.played_at > newest:
                newest = game.played_at
        if newest is not None:
            ingester.update_last_synced(job.username, newest)

        # -- analyze ---------------------------------------------------------
        targets = [
            g for g in db.get_recent_games(limit=10_000_000, username=job.username)
            if g["analyzed_at"] is None
        ]
        job.phase = "analyzing"
        job.total = len(targets)
        job.done = 0
        if targets:
            with StockfishAnalyzer(
                config.stockfish_path,
                depth=config.bulk_stockfish_depth,
                threads=config.stockfish_threads,
            ) as analyzer:
                for g in targets:
                    gid = g["game_id"]
                    job.message = f"Analyzing {gid}…"
                    analyses = analyzer.analyze_game(g["pgn"], gid)
                    db.save_analysis(gid, [_analysis_to_dict(a) for a in analyses])
                    job.done += 1

        # -- patterns + index ------------------------------------------------
        job.phase = "indexing"
        job.message = "Detecting patterns and building the knowledge base…"
        explainer = LLMExplainer(
            config.openai_api_key,
            model=config.openai_model,
            user_rating=config.user_rating,
            embedding_model=config.embedding_model,
        )
        Coach(db, explainer).detect_and_persist_patterns(username=job.username)
        Knowledge(db, explainer).index(username=job.username)

        job.phase = "ready"
        job.state = "ready"
        job.message = "Ready."
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        job.state = "error"
        job.error = f"{type(exc).__name__}: {exc}"


def _analysis_to_dict(analysis) -> dict:
    """Convert a PositionAnalysis into the dict shape save_analysis expects."""
    return {
        "move_number": analysis.move_number,
        "fen": analysis.fen,
        "move_played": analysis.move_played,
        "eval_before": analysis.eval_before,
        "eval_after": analysis.eval_after,
        "centipawn_loss": analysis.centipawn_loss,
        "depth": analysis.depth,
        "best_move": analysis.best_move,
        "best_move_eval": analysis.best_move_eval,
        "top_3_moves": [list(m) for m in analysis.top_3_moves],
        "classification": analysis.classification.value,
        "is_blunder": analysis.is_blunder,
        "is_missed_tactic": analysis.is_missed_tactic,
        "mate_in": analysis.mate_in,
        "explanation": analysis.explanation,
    }
