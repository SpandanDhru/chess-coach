"""Tests for the Lichess ingester normalization (no network)."""

from datetime import datetime, timezone

import pytest

from src.ingestion.base import GameMetadata, speed_bucket
from src.ingestion.lichess import LichessIngester, _pgn_for, _to_epoch_ms

_PGN = (
    '[Event "Rated Blitz game"]\n'
    '[White "alice"]\n'
    '[Black "bob"]\n'
    '[Result "1-0"]\n'
    "\n"
    "1. e4 e5 2. Nf3 Nc6 1-0\n"
)

_GAME_JSON = {
    "id": "abcd1234",
    "rated": True,
    "variant": "standard",
    "speed": "blitz",
    "createdAt": 1_699_999_000_000,
    "lastMoveAt": 1_700_000_000_000,
    "winner": "white",
    "players": {
        "white": {"user": {"name": "alice"}, "rating": 1500},
        "black": {"user": {"name": "bob"}, "rating": 1480},
    },
    "opening": {"eco": "C50", "name": "Italian Game"},
    "moves": "e4 e5 Nf3 Nc6",
    "pgn": _PGN,
}


def test_parse_game_as_white():
    ing = LichessIngester(db_connection=None)
    md = ing._parse_game(_GAME_JSON, "Alice")  # case-insensitive match
    assert isinstance(md, GameMetadata)
    assert md.platform == "lichess"
    assert md.game_id == "abcd1234"
    assert md.color == "white"
    assert md.result == "1-0"
    assert md.opponent_username == "bob"
    assert md.opponent_rating == 1480
    assert md.user_rating == 1500
    assert md.time_control == "blitz"
    assert md.opening_eco == "C50"
    assert md.opening_name == "Italian Game"
    assert md.played_at == datetime.utcfromtimestamp(1_700_000_000_000 / 1000)


def test_parse_game_as_black():
    ing = LichessIngester(db_connection=None)
    md = ing._parse_game(_GAME_JSON, "bob")
    assert md.color == "black"
    assert md.result == "1-0"
    assert md.opponent_username == "alice"
    assert md.user_rating == 1480


def test_parse_game_draw_when_no_winner():
    ing = LichessIngester(db_connection=None)
    draw = dict(_GAME_JSON)
    draw.pop("winner")
    md = ing._parse_game(draw, "alice")
    assert md.result == "1/2-1/2"


def test_parse_game_skips_variants():
    ing = LichessIngester(db_connection=None)
    variant = dict(_GAME_JSON, variant="crazyhouse")
    assert ing._parse_game(variant, "alice") is None


def test_pgn_fallback_from_moves():
    """A game without an explicit PGN is reconstructed from its SAN moves."""
    no_pgn = dict(_GAME_JSON)
    no_pgn.pop("pgn")
    pgn = _pgn_for(no_pgn)
    assert pgn is not None
    assert "e4 e5 Nf3 Nc6" in pgn
    md = LichessIngester(db_connection=None)._parse_game(no_pgn, "alice")
    assert md is not None and md.pgn == pgn


def test_to_epoch_ms_roundtrip():
    dt = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert _to_epoch_ms(dt) == int(dt.timestamp() * 1000)
    assert _to_epoch_ms(None) is None


def test_fetch_games_builds_params_and_parses(monkeypatch):
    ing = LichessIngester(db_connection=None)
    captured = {}

    def fake_stream(url, params, username):
        captured["url"] = url
        captured["params"] = params
        return [_GAME_JSON, dict(_GAME_JSON, id="second")]

    monkeypatch.setattr(ing, "_stream_ndjson", fake_stream)

    since = datetime(2023, 1, 1, tzinfo=timezone.utc)
    games = ing.fetch_games("Alice", since=since, limit=5)

    assert [g.game_id for g in games] == ["abcd1234", "second"]
    assert captured["url"].endswith("/games/user/alice")
    assert captured["params"]["max"] == 5
    assert captured["params"]["since"] == _to_epoch_ms(since)
    assert captured["params"]["pgnInJson"] == "true"


def test_speed_bucket_lichess_passthrough():
    assert speed_bucket("blitz", "lichess") == "blitz"
    assert speed_bucket("rapid", "lichess") == "rapid"


def test_speed_bucket_chesscom_from_seconds():
    assert speed_bucket("60", "chesscom") == "bullet"
    assert speed_bucket("300", "chesscom") == "blitz"
    assert speed_bucket("600", "chesscom") == "rapid"
    assert speed_bucket("180+2", "chesscom") == "blitz"  # 180 + 40*2 = 260
    assert speed_bucket("1/259200", "chesscom") == "correspondence"
    assert speed_bucket("", "chesscom") == "unknown"
