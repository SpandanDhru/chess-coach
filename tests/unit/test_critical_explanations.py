"""Tests for the two-tier critical-mistake explanation layer."""

from datetime import datetime

import pytest

from src.coaching.coach import Coach, CoachError
from src.storage.database import Database


class CountingExplainer:
    """Counts explain_position calls; returns a canned string."""

    def __init__(self):
        self.calls = 0

    def explain_position(self, analysis):
        self.calls += 1
        return f"explanation for move {analysis.move_number}"


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def _game(game_id="g1"):
    return {
        "game_id": game_id,
        "platform": "chesscom",
        "username": "alice",
        "color": "white",
        "result": "1-0",
        "played_at": datetime(2024, 1, 1),
        "pgn": "1. e4 e5 1-0",
        "opponent_username": "bob",
        "opening_eco": "C50",
        "opening_name": "Italian Game",
        "time_control": "600",
    }


def _pos(move_number, cp, classification="good", blunder=False):
    return {
        "move_number": move_number,
        "fen": "f",
        "move_played": "e2e4",
        "best_move": "d2d4",
        "eval_before": 20.0,
        "eval_after": 20.0 + cp,
        "centipawn_loss": cp,
        "classification": classification,
        "is_blunder": blunder,
    }


def test_explain_requires_analysis(db):
    db.save_game(_game())
    coach = Coach(db, CountingExplainer())
    with pytest.raises(CoachError, match="not been analyzed"):
        coach.explain_critical_mistakes("g1")


def test_explains_worst_first_and_respects_cap(db):
    db.save_game(_game())
    db.save_analysis(
        "g1",
        [
            _pos(5, 30),  # good, not critical
            _pos(10, 150, "mistake"),
            _pos(20, 800, "blunder", blunder=True),
            _pos(30, 400, "blunder", blunder=True),
        ],
    )
    explainer = CountingExplainer()
    coach = Coach(db, explainer)

    results = coach.explain_critical_mistakes("g1", max_explanations=2)
    assert explainer.calls == 2  # capped
    # Worst first: 800cp then 400cp.
    assert [r["centipawn_loss"] for r in results] == [800, 400]


def test_cached_explanations_are_reused(db):
    db.save_game(_game())
    db.save_analysis(
        "g1",
        [_pos(20, 800, "blunder", blunder=True)],
    )
    explainer = CountingExplainer()
    coach = Coach(db, explainer)

    coach.explain_critical_mistakes("g1")
    assert explainer.calls == 1
    # The explanation is now persisted; a second run makes no new LLM calls.
    second = coach.explain_critical_mistakes("g1")
    assert explainer.calls == 1
    assert "explanation for move 20" in second[0]["explanation"]
