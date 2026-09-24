"""Tests for aggregation rollups and persistent pattern detection."""

from datetime import datetime

import pytest

from src.analysis.llm_explainer import LLMExplainer
from src.coaching.coach import Coach
from src.storage.database import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def _game(game_id, **overrides):
    base = {
        "game_id": game_id,
        "platform": "chesscom",
        "username": "alice",
        "color": "white",
        "result": "1-0",
        "played_at": datetime(2024, 1, 1, 12, 0, 0),
        "pgn": "1. e4 e5 1-0",
        "opponent_username": "bob",
        "opponent_rating": 1480,
        "user_rating": 1500,
        "opening_eco": "C50",
        "opening_name": "Italian Game",
        "time_control": "600",
    }
    base.update(overrides)
    return base


def _pos(move_number, cp, classification="good", blunder=False, missed=False):
    return {
        "move_number": move_number,
        "fen": "somefen",
        "move_played": "e2e4",
        "eval_before": 20.0,
        "eval_after": 20.0 + cp,
        "centipawn_loss": cp,
        "classification": classification,
        "is_blunder": blunder,
        "is_missed_tactic": missed,
    }


def test_aggregate_by_opening(db):
    db.save_game(_game("g1", result="1-0", color="white"))  # win
    db.save_game(_game("g2", result="0-1", color="white"))  # loss
    db.save_game(_game("g3", opening_name="Sicilian", opening_eco="B20", result="1/2-1/2"))
    db.save_analysis("g1", [_pos(5, 10), _pos(20, 400, "blunder", blunder=True)])
    db.save_analysis("g2", [_pos(5, 30)])

    rows = {r["opening"]: r for r in db.aggregate_by_opening("alice")}
    italian = rows["Italian Game"]
    assert italian["games"] == 2
    assert italian["wins"] == 1 and italian["losses"] == 1
    assert italian["score_pct"] == 50.0
    assert italian["blunders"] == 1
    # avg cp loss over 3 analyzed positions: (10 + 400 + 30) / 3
    assert italian["avg_cp_loss"] == round((10 + 400 + 30) / 3, 1)

    sicilian = rows["Sicilian"]
    assert sicilian["games"] == 1 and sicilian["draws"] == 1
    assert sicilian["avg_cp_loss"] is None  # no analysis


def test_aggregate_by_phase(db):
    db.save_game(_game("g1"))
    db.save_analysis(
        "g1",
        [
            _pos(5, 20),  # opening
            _pos(25, 500, "blunder", blunder=True),  # middlegame
            _pos(45, 60),  # endgame
        ],
    )
    rows = {r["phase"]: r for r in db.aggregate_by_phase("alice")}
    assert rows["opening"]["moves"] == 1
    assert rows["middlegame"]["blunders"] == 1
    assert rows["middlegame"]["avg_cp_loss"] == 500.0
    assert rows["endgame"]["blunder_rate"] == 0.0


def test_aggregate_by_time_control_buckets(db):
    db.save_game(_game("g1", time_control="600"))  # rapid
    db.save_game(_game("g2", time_control="60"))   # bullet
    db.save_game(_game("lc", platform="lichess", time_control="blitz"))
    buckets = {r["time_control"]: r for r in db.aggregate_by_time_control("alice")}
    assert buckets["rapid"]["games"] == 1
    assert buckets["bullet"]["games"] == 1
    assert buckets["blitz"]["games"] == 1


def _coach(db):
    # Explainer is unused by pattern detection (LLM-free), but Coach requires one.
    explainer = LLMExplainer.__new__(LLMExplainer)
    return Coach(db, explainer)


def test_detect_patterns_persists_and_is_idempotent(db):
    # Three games, each with a middlegame blunder -> a phase pattern (>=3).
    for i in range(3):
        gid = f"g{i}"
        db.save_game(_game(gid))
        db.save_analysis(gid, [_pos(22, 400, "blunder", blunder=True, missed=True)])

    coach = _coach(db)
    first = coach.detect_and_persist_patterns("alice", min_occurrences=3)
    descriptions = {p["description"] for p in first}
    assert "Recurring mistakes in the middlegame" in descriptions

    phase_pattern = next(
        p for p in db.get_patterns() if p["phase"] == "middlegame"
    )
    assert phase_pattern["occurrence_count"] == 3
    assert len(phase_pattern["example_game_ids"]) == 3

    # Re-running with no new games must not inflate counts.
    coach.detect_and_persist_patterns("alice", min_occurrences=3)
    phase_pattern = next(
        p for p in db.get_patterns() if p["phase"] == "middlegame"
    )
    assert phase_pattern["occurrence_count"] == 3

    # A new game adds exactly one to the count.
    db.save_game(_game("g_new"))
    db.save_analysis("g_new", [_pos(23, 400, "blunder", blunder=True)])
    coach.detect_and_persist_patterns("alice", min_occurrences=3)
    phase_pattern = next(
        p for p in db.get_patterns() if p["phase"] == "middlegame"
    )
    assert phase_pattern["occurrence_count"] == 4
    assert len(phase_pattern["example_game_ids"]) == 4
