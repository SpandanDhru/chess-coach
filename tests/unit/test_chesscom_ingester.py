"""Tests for the Chess.com ingester normalization (no network)."""

from datetime import datetime

import pytest

from src.ingestion.base import GameMetadata
from src.ingestion.chesscom import (
    ChessComIngester,
    _game_id_from_url,
    _normalize_result,
)

_PGN = (
    '[Event "Live Chess"]\n'
    '[Site "Chess.com"]\n'
    '[White "alice"]\n'
    '[Black "bob"]\n'
    '[Result "1-0"]\n'
    '[ECO "C20"]\n'
    '[ECOUrl "https://www.chess.com/openings/Kings-Pawn-Opening"]\n'
    "\n"
    "1. e4 e5 2. Qh5 Nc6 3. Bc4 g6 4. Qf3 1-0\n"
)

_GAME_JSON = {
    "url": "https://www.chess.com/game/live/12345",
    "pgn": _PGN,
    "time_control": "600",
    "end_time": 1_700_000_000,
    "rules": "chess",
    "white": {"username": "alice", "rating": 1500, "result": "win"},
    "black": {"username": "bob", "rating": 1480, "result": "resigned"},
}


def test_normalize_result():
    assert _normalize_result("win", "resigned") == "1-0"
    assert _normalize_result("resigned", "win") == "0-1"
    assert _normalize_result("agreed", "agreed") == "1/2-1/2"
    assert _normalize_result("stalemate", "stalemate") == "1/2-1/2"


def test_game_id_from_url():
    assert _game_id_from_url("https://www.chess.com/game/live/12345") == "12345"
    assert _game_id_from_url("https://www.chess.com/game/live/12345/") == "12345"


def test_parse_game_as_white():
    ing = ChessComIngester(db_connection=None)
    md = ing._parse_game(_GAME_JSON, "Alice")  # case-insensitive match
    assert isinstance(md, GameMetadata)
    assert md.platform == "chesscom"
    assert md.game_id == "12345"
    assert md.color == "white"
    assert md.result == "1-0"
    assert md.opponent_username == "bob"
    assert md.opponent_rating == 1480
    assert md.user_rating == 1500
    assert md.opening_eco == "C20"
    assert md.opening_name == "Kings Pawn Opening"
    assert md.played_at == datetime.utcfromtimestamp(1_700_000_000)


def test_parse_game_as_black():
    ing = ChessComIngester(db_connection=None)
    md = ing._parse_game(_GAME_JSON, "bob")
    assert md.color == "black"
    assert md.result == "1-0"
    assert md.opponent_username == "alice"
    assert md.user_rating == 1480


def test_parse_game_skips_variants():
    ing = ChessComIngester(db_connection=None)
    variant = dict(_GAME_JSON, rules="bughouse")
    assert ing._parse_game(variant, "alice") is None


def test_fetch_games_walks_archives_newest_first(monkeypatch):
    ing = ChessComIngester(db_connection=None)

    older = dict(_GAME_JSON, url="https://www.chess.com/game/live/1", end_time=1_600_000_000)
    newer = dict(_GAME_JSON, url="https://www.chess.com/game/live/2", end_time=1_700_000_000)

    monkeypatch.setattr(
        ing, "_get_archive_urls", lambda u: ["archiveA", "archiveB"]
    )
    # archiveB is the newest month; each archive is chronological within itself.
    monkeypatch.setattr(
        ing,
        "_get_archive",
        lambda url: [older] if url == "archiveA" else [newer],
    )

    games = ing.fetch_games("alice", limit=1)
    assert len(games) == 1
    assert games[0].game_id == "2"  # newest returned first


def test_fetch_games_respects_limit(monkeypatch):
    ing = ChessComIngester(db_connection=None)
    many = [
        dict(_GAME_JSON, url=f"https://www.chess.com/game/live/{i}", end_time=1_700_000_000 + i)
        for i in range(10)
    ]
    monkeypatch.setattr(ing, "_get_archive_urls", lambda u: ["archiveA"])
    monkeypatch.setattr(ing, "_get_archive", lambda url: many)

    games = ing.fetch_games("alice", limit=3)
    assert len(games) == 3
