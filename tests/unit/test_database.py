"""Tests that database reads are detached-safe (no DetachedInstanceError)."""

from datetime import datetime

import pytest

from src.storage.database import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def _game_data(game_id="g1"):
    return {
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
        "opening_eco": "C20",
        "opening_name": "Kings Pawn",
        "time_control": "600",
    }


def test_save_and_get_game_returns_dict(db):
    saved = db.save_game(_game_data())
    assert isinstance(saved, dict)
    assert saved["game_id"] == "g1"

    fetched = db.get_game("g1")
    # Accessing attributes AFTER the session closed must not raise.
    assert fetched["game_id"] == "g1"
    assert fetched["opponent_username"] == "bob"
    assert fetched["analyzed_at"] is None


def test_get_game_missing_returns_none(db):
    assert db.get_game("nope") is None


def test_get_recent_games_filters_by_username(db):
    db.save_game(_game_data("a1"))  # username="alice"
    bob = dict(_game_data("b1"), username="bob")
    db.save_game(bob)

    alice_games = db.get_recent_games(username="alice")
    assert [g["game_id"] for g in alice_games] == ["a1"]

    # Case-insensitive match.
    assert len(db.get_recent_games(username="ALICE")) == 1

    assert {g["game_id"] for g in db.get_recent_games()} == {"a1", "b1"}
    assert set(db.list_usernames()) == {"alice", "bob"}


def test_save_and_get_analysis_detached_safe(db):
    db.save_game(_game_data())
    positions = [
        {
            "move_number": 1,
            "fen": "startpos",
            "move_played": "e2e4",
            "eval_before": 20.0,
            "eval_after": 25.0,
            "centipawn_loss": 5.0,
            "classification": "best",
            "is_blunder": False,
        },
        {
            "move_number": 5,
            "fen": "somefen",
            "move_played": "g7g6",
            "eval_before": 50.0,
            "eval_after": 900.0,
            "centipawn_loss": 850.0,
            "classification": "blunder",
            "is_blunder": True,
        },
    ]
    db.save_analysis("g1", positions)

    analysis = db.get_game_analysis("g1")
    assert len(analysis) == 2
    # Detached-safe access after session close.
    assert analysis[0]["move_played"] == "e2e4"
    assert analysis[1]["is_blunder"] is True

    blunders = db.get_blunders()
    assert len(blunders) == 1
    assert blunders[0]["centipawn_loss"] == 850.0

    # The game should now be flagged analyzed.
    assert db.get_game("g1")["analyzed_at"] is not None
