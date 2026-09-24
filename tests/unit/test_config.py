"""Tests for configuration loading and fail-fast validation."""

import os
import stat

import pytest

from src.config import Config, ConfigError

_REQUIRED_VARS = [
    "CHESS_COM_USERNAME",
    "OPENAI_API_KEY",
    "STOCKFISH_PATH",
    "OPENAI_MODEL",
    "STOCKFISH_DEPTH",
    "STOCKFISH_THREADS",
    "USER_RATING",
    "DB_PATH",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Start each test from a known-empty environment."""
    for var in _REQUIRED_VARS:
        monkeypatch.delenv(var, raising=False)
    # Neutralize any real .env in the repo root during tests.
    monkeypatch.setattr("src.config.load_dotenv", lambda *a, **k: None)


@pytest.fixture
def fake_stockfish(tmp_path):
    """Create a fake executable to satisfy the STOCKFISH_PATH check."""
    binary = tmp_path / "stockfish"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(binary)


def test_missing_username_is_optional(monkeypatch, fake_stockfish):
    # Username is optional now (supplied per-command via --username).
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")
    monkeypatch.setenv("STOCKFISH_PATH", fake_stockfish)
    config = Config.load_and_validate()
    assert config.chesscom_username is None


def test_placeholder_username_becomes_none(monkeypatch, fake_stockfish):
    monkeypatch.setenv("CHESS_COM_USERNAME", "your_chesscom_handle")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")
    monkeypatch.setenv("STOCKFISH_PATH", fake_stockfish)
    config = Config.load_and_validate()
    assert config.chesscom_username is None


def test_bad_api_key_fails(monkeypatch, fake_stockfish):
    monkeypatch.setenv("CHESS_COM_USERNAME", "alice")
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-key")
    monkeypatch.setenv("STOCKFISH_PATH", fake_stockfish)
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        Config.load_and_validate()


def test_missing_stockfish_fails(monkeypatch):
    monkeypatch.setenv("CHESS_COM_USERNAME", "alice")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")
    monkeypatch.setenv("STOCKFISH_PATH", "/nonexistent/stockfish")
    with pytest.raises(ConfigError, match="STOCKFISH_PATH|Stockfish"):
        Config.load_and_validate()


def test_valid_config_resolves(monkeypatch, fake_stockfish):
    monkeypatch.setenv("CHESS_COM_USERNAME", "Alice")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc123")
    monkeypatch.setenv("STOCKFISH_PATH", fake_stockfish)
    monkeypatch.setenv("STOCKFISH_DEPTH", "15")
    monkeypatch.setenv("USER_RATING", "1600")

    config = Config.load_and_validate()
    assert config.chesscom_username == "Alice"
    assert config.openai_api_key == "sk-abc123"
    assert config.stockfish_path == fake_stockfish
    assert config.stockfish_depth == 15
    assert config.user_rating == 1600
    assert config.openai_model == "gpt-4o-mini"  # default


def test_stockfish_autodetect(monkeypatch, fake_stockfish):
    monkeypatch.setenv("CHESS_COM_USERNAME", "alice")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")
    monkeypatch.setenv("STOCKFISH_PATH", "")  # blank -> auto-detect
    monkeypatch.setattr("src.config.shutil.which", lambda name: fake_stockfish)

    config = Config.load_and_validate()
    assert config.stockfish_path == fake_stockfish


def test_bad_int_override_fails(monkeypatch, fake_stockfish):
    monkeypatch.setenv("CHESS_COM_USERNAME", "alice")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")
    monkeypatch.setenv("STOCKFISH_PATH", fake_stockfish)
    monkeypatch.setenv("STOCKFISH_DEPTH", "deep")
    with pytest.raises(ConfigError, match="STOCKFISH_DEPTH"):
        Config.load_and_validate()
