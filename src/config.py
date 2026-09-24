"""Application configuration loaded from environment (.env).

The entire setup surface for v1 is three values in a ``.env`` file:

    CHESS_COM_USERNAME   Chess.com handle to pull games for (public API, no key)
    OPENAI_API_KEY       OpenAI API key for coaching writeups
    STOCKFISH_PATH       Path to the local Stockfish binary (auto-detected if blank)

Everything else has a sensible default and can optionally be overridden via
environment variables. Validation happens eagerly at CLI startup
(``Config.load_and_validate``) so problems surface as a single clear message
rather than a cryptic failure three layers deep at first use.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid.

    The message is written to be actionable and shown directly to the user.
    """


# Placeholder values shipped in .env.example — treated as "not configured".
_PLACEHOLDERS = {
    "",
    "your_chesscom_handle",
    "your_chesscom_username",
    "sk-...",
    "sk-your-api-key-here",
}

# Common install locations checked when STOCKFISH_PATH is not set.
_STOCKFISH_CANDIDATES = (
    "/usr/games/stockfish",
    "/usr/bin/stockfish",
    "/usr/local/bin/stockfish",
    "/opt/homebrew/bin/stockfish",
)


@dataclass
class Config:
    """Resolved, validated application configuration."""

    # Optional default handle. Any username can be supplied per-command via
    # --username; this is just the fallback used when the flag is omitted.
    chesscom_username: Optional[str]
    openai_api_key: str
    stockfish_path: str

    # Optional Lichess defaults. Reads work anonymously; a token (free personal
    # access token) lifts rate limits when pulling toward a large game corpus.
    lichess_username: Optional[str] = None
    lichess_token: Optional[str] = None

    # Optional overrides (with defaults tuned for interactive testing).
    openai_model: str = "gpt-4o-mini"
    stockfish_depth: int = 18
    # Lower depth used for large `analyze --all` batches (500+ games); the
    # interactive depth is too slow at that scale.
    bulk_stockfish_depth: int = 14
    stockfish_threads: int = 1
    user_rating: Optional[int] = None
    db_path: str = "data/chess_coach.db"

    # RAG / embeddings (Phase 3) and critical-mistake explanations (Phase 4).
    embedding_model: str = "text-embedding-3-small"
    rag_top_k: int = 5
    critical_explanations: int = 3

    # Desktop-app FastAPI sidecar bind address (Electron main + sidecar agree here).
    api_host: str = "127.0.0.1"
    api_port: int = 8765

    @classmethod
    def load_and_validate(cls) -> "Config":
        """Load config from the environment and validate it, failing fast.

        Raises:
            ConfigError: with an actionable message if anything required is
                missing, still a placeholder, or (for Stockfish) not executable.
        """
        # Load .env from the current working directory / project root if present.
        load_dotenv()

        # Username is optional: it's only a default for `sync` when --username
        # is not supplied. Any handle can be analyzed by passing --username.
        username = (os.getenv("CHESS_COM_USERNAME") or "").strip()
        if username in _PLACEHOLDERS:
            username = None

        lichess_username = (os.getenv("LICHESS_USERNAME") or "").strip()
        if lichess_username in _PLACEHOLDERS:
            lichess_username = None

        lichess_token = (os.getenv("LICHESS_TOKEN") or "").strip()
        if lichess_token in _PLACEHOLDERS:
            lichess_token = None

        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if api_key in _PLACEHOLDERS:
            raise ConfigError(
                "OPENAI_API_KEY is not set. Add your OpenAI API key to .env "
                "(copy .env.example to .env and fill it in)."
            )
        if not api_key.startswith("sk-"):
            raise ConfigError(
                "OPENAI_API_KEY does not look like a valid key (expected it to start "
                "with 'sk-'). Double-check the value in your .env file."
            )

        stockfish_path = cls._resolve_stockfish_path(
            (os.getenv("STOCKFISH_PATH") or "").strip()
        )

        return cls(
            chesscom_username=username,
            openai_api_key=api_key,
            stockfish_path=stockfish_path,
            lichess_username=lichess_username,
            lichess_token=lichess_token,
            openai_model=os.getenv("OPENAI_MODEL", cls.openai_model).strip()
            or cls.openai_model,
            stockfish_depth=_int_env("STOCKFISH_DEPTH", cls.stockfish_depth),
            bulk_stockfish_depth=_int_env(
                "BULK_STOCKFISH_DEPTH", cls.bulk_stockfish_depth
            ),
            stockfish_threads=_int_env("STOCKFISH_THREADS", cls.stockfish_threads),
            user_rating=_optional_int_env("USER_RATING"),
            db_path=(os.getenv("DB_PATH") or cls.db_path).strip() or cls.db_path,
            embedding_model=os.getenv("EMBEDDING_MODEL", cls.embedding_model).strip()
            or cls.embedding_model,
            rag_top_k=_int_env("RAG_TOP_K", cls.rag_top_k),
            critical_explanations=_int_env(
                "CRITICAL_EXPLANATIONS", cls.critical_explanations
            ),
            api_host=(os.getenv("API_HOST") or cls.api_host).strip() or cls.api_host,
            api_port=_int_env("API_PORT", cls.api_port),
        )

    @staticmethod
    def _resolve_stockfish_path(configured: str) -> str:
        """Resolve and validate the Stockfish binary path.

        If ``configured`` is empty, auto-detect via PATH and common locations.
        Always verifies the final path exists and is executable.
        """
        path = configured
        if not path:
            path = shutil.which("stockfish") or ""
            if not path:
                for candidate in _STOCKFISH_CANDIDATES:
                    if os.access(candidate, os.X_OK):
                        path = candidate
                        break

        if not path:
            raise ConfigError(
                "Stockfish binary not found. Install it (e.g. 'sudo apt install "
                "stockfish' or 'brew install stockfish') and/or set STOCKFISH_PATH "
                "in .env to the binary's location."
            )

        p = Path(path)
        if not p.exists():
            raise ConfigError(
                f"STOCKFISH_PATH points to '{path}' but no file exists there. "
                "Fix the path in .env or install Stockfish."
            )
        if not os.access(path, os.X_OK):
            raise ConfigError(
                f"Stockfish at '{path}' is not executable. Check the file "
                "permissions (chmod +x) or point STOCKFISH_PATH at the real binary."
            )
        return path


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got '{raw}'.") from exc


def _optional_int_env(name: str) -> Optional[int]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got '{raw}'.") from exc
