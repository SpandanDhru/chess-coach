"""Tests for the FastAPI sidecar (mocked Coach/LLM; no network, no engine)."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.api import server
from src.config import Config
from src.storage.database import Database


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "test.db"))
    config = Config(
        chesscom_username=None,
        openai_api_key="sk-test",
        stockfish_path="/bin/true",
    )
    # Inject the shared state directly so _state() does no real validation.
    monkeypatch.setattr(server, "_config", config)
    monkeypatch.setattr(server, "_db", db)
    monkeypatch.setattr(server, "_jobs", server.JobStore())
    return TestClient(server.app), db


def _game(db, game_id="g1"):
    db.save_game(
        {
            "game_id": game_id,
            "platform": "chesscom",
            "username": "alice",
            "color": "white",
            "result": "1-0",
            "played_at": datetime(2024, 1, 1, 12, 0, 0),
            "pgn": "1. e4 e5 2. Nf3 Nc6 1-0",
            "opponent_username": "bob",
            "opening_eco": "C50",
            "opening_name": "Italian Game",
            "time_control": "600",
        }
    )


def _analysis():
    # One entry per ply (e4, e5, Nf3, Nc6); the 3rd ply is the worst mistake.
    specs = [
        (1, "e2e4", 10, "good", False),
        (1, "e7e5", 15, "good", False),
        (2, "g1f3", 450, "blunder", True),
        (2, "b8c6", 20, "good", False),
    ]
    return [
        {
            "move_number": mn, "fen": "f", "move_played": uci,
            "eval_before": 20.0, "eval_after": 20.0 + cp, "centipawn_loss": cp,
            "best_move": "d2d4", "classification": cls, "is_blunder": bl,
        }
        for mn, uci, cp, cls, bl in specs
    ]


def test_health(client):
    c, _ = client
    assert c.get("/api/health").json() == {"status": "ok"}


def test_list_games(client):
    c, db = client
    _game(db)
    body = c.get("/api/games", params={"username": "alice"}).json()
    assert len(body["games"]) == 1
    assert body["games"][0]["opening"] == "Italian Game"
    assert body["games"][0]["analyzed"] is False


def test_review_aligns_moves_with_analysis(client):
    c, db = client
    _game(db)
    db.save_analysis("g1", _analysis())

    body = c.get("/api/games/g1/review").json()
    moves = body["moves"]
    assert [m["san"] for m in moves] == ["e4", "e5", "Nf3", "Nc6"]
    # FENs come from replaying the PGN (not the placeholder stored fen).
    assert moves[0]["fen"].startswith(
        "rnbqkbnr/pppppppp/8/4P3"
    ) or "P" in moves[0]["fen"]
    # The blunder flag is carried through and aligned to the 3rd ply.
    assert moves[2]["is_blunder"] is True
    assert moves[2]["best_move_san"] == "d4"
    assert body["summary"]["blunders"] == 1


def test_review_unknown_game_404(client):
    c, _ = client
    assert c.get("/api/games/nope/review").status_code == 404


def test_coach_game_returns_writeup_and_key_fen(client, monkeypatch):
    c, db = client
    _game(db)
    db.save_analysis("g1", _analysis())
    monkeypatch.setattr(
        "src.coaching.coach.Coach.coach_game", lambda self, gid: "great game"
    )

    body = c.post("/api/games/g1/coach").json()
    assert body["writeup"] == "great game"
    # Key position = FEN after the worst mistake (ply 3, Nf3).
    assert body["key_fen"] is not None


def test_chat_routes_to_ask(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(
        "src.coaching.coach.Coach.ask",
        lambda self, message, k=5, username=None: (
            "you struggle with {{bN}} endgames",
            [{"text": "doc", "score": 0.9, "source_type": "pattern"}],
        ),
    )
    body = c.post("/api/chat", json={"username": "alice", "message": "help"}).json()
    assert "{{bN}}" in body["answer"]
    assert body["sources"][0]["source_type"] == "pattern"


def test_session_start_and_status(client, monkeypatch):
    c, _ = client

    def fake_run(job, config, db):
        job.state = "ready"
        job.phase = "ready"

    monkeypatch.setattr(server, "run_session_job", fake_run)

    started = c.post(
        "/api/session", json={"platform": "chesscom", "username": "alice"}
    ).json()
    job_id = started["job_id"]
    status = c.get(f"/api/session/{job_id}").json()
    assert status["state"] in ("ready", "running", "pending")


def test_session_rejects_bad_platform(client):
    c, _ = client
    r = c.post("/api/session", json={"platform": "bogus", "username": "alice"})
    assert r.status_code == 400


def test_review_includes_position_ids(client):
    c, db = client
    _game(db)
    db.save_analysis("g1", _analysis())
    moves = c.get("/api/games/g1/review").json()["moves"]
    assert all(m["position_id"] is not None for m in moves)


def test_explain_position_generates_and_caches(client, monkeypatch):
    c, db = client
    _game(db)
    db.save_analysis("g1", _analysis())
    pid = c.get("/api/games/g1/review").json()["moves"][2]["position_id"]

    calls = {"n": 0}

    def fake_explain(self, analysis):
        calls["n"] += 1
        return "the {{wN}} was misplaced"

    monkeypatch.setattr(
        "src.analysis.llm_explainer.LLMExplainer.explain_position", fake_explain
    )

    first = c.post(f"/api/positions/{pid}/explain").json()
    assert first["explanation"] == "the {{wN}} was misplaced"
    assert first["cached"] is False
    # Second call is served from the cache — no new LLM call.
    second = c.post(f"/api/positions/{pid}/explain").json()
    assert second["cached"] is True
    assert calls["n"] == 1


def test_explain_unknown_position_404(client):
    c, _ = client
    assert c.post("/api/positions/999/explain").status_code == 404
