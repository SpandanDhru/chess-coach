"""Chess.com game ingester using their public API.

The public Published-Data API is unauthenticated for reads. Games are exposed as
monthly archives:

    GET /pub/player/{username}/games/archives   -> list of monthly archive URLs
    GET {archive_url}                            -> {"games": [ {...}, ... ]}

Chess.com requires a descriptive ``User-Agent`` header; requests without one are
frequently rejected with HTTP 403, so we always set one.
"""

import io
from datetime import datetime, timezone
from typing import List, Optional

import chess.pgn
import httpx

from .base import GameIngester, GameMetadata


class IngestionError(Exception):
    """Raised when Chess.com data cannot be fetched or parsed.

    Messages are written to be actionable and shown directly to the user.
    """


# A descriptive User-Agent is required by the Chess.com API (missing UA -> 403).
_USER_AGENT = "chess-coach/1.0 (personal game analysis tool)"


class ChessComIngester(GameIngester):
    """Ingest games from Chess.com public API."""

    BASE_URL = "https://api.chess.com/pub"

    def __init__(self, db_connection=None):
        """
        Initialize Chess.com ingester.

        Args:
            db_connection: Database connection for tracking sync state
        """
        self.db = db_connection
        self.client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )

    # -- Public API --------------------------------------------------------

    def fetch_games(
        self,
        username: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[GameMetadata]:
        """
        Fetch games from Chess.com, newest first.

        Walks the monthly archives from newest to oldest, stopping as soon as
        ``limit`` games have been collected. ``since`` / ``until`` filter by the
        time the game ended.
        """
        archives = self._get_archive_urls(username)
        since = _as_utc(since)
        until = _as_utc(until)

        games: List[GameMetadata] = []
        # Archives come oldest-first; walk newest-first so `limit` returns the
        # most recent games.
        for archive_url in reversed(archives):
            month_games = self._get_archive(archive_url)
            for raw in reversed(month_games):
                metadata = self._parse_game(raw, username)
                if metadata is None:
                    continue
                if since and metadata.played_at < since:
                    # Archives (and games within) are chronological; everything
                    # further back is older still, so we can stop entirely.
                    return games
                if until and metadata.played_at > until:
                    continue
                games.append(metadata)
                if limit is not None and len(games) >= limit:
                    return games
        return games

    def get_last_synced(self, username: str) -> Optional[datetime]:
        """Query the database for the last sync timestamp."""
        if self.db is None:
            return None
        return self.db.get_last_sync("chesscom", username)

    def update_last_synced(self, username: str, timestamp: datetime) -> None:
        """Update the database with a new sync timestamp."""
        if self.db is None:
            return
        self.db.update_last_sync("chesscom", username, timestamp)

    # -- HTTP helpers ------------------------------------------------------

    def _get_archive_urls(self, username: str) -> List[str]:
        url = f"{self.BASE_URL}/player/{username.lower()}/games/archives"
        data = self._get_json(url, context=f"archive list for '{username}'")
        archives = data.get("archives", [])
        if not archives:
            raise IngestionError(
                f"Chess.com has no game archives for '{username}'. Check the "
                "handle is spelled correctly and has played games."
            )
        return archives

    def _get_archive(self, archive_url: str) -> List[dict]:
        data = self._get_json(archive_url, context=f"games from {archive_url}")
        return data.get("games", [])

    def _get_json(self, url: str, context: str) -> dict:
        try:
            response = self.client.get(url)
        except httpx.RequestError as exc:
            raise IngestionError(
                f"Network error fetching {context} ({url}): {exc}"
            ) from exc

        if response.status_code == 404:
            raise IngestionError(
                f"Chess.com returned 404 for {url} — the username likely does "
                "not exist. Double-check CHESS_COM_USERNAME."
            )
        if response.status_code == 403:
            raise IngestionError(
                f"Chess.com returned 403 for {url} — the request was blocked "
                "(often a missing/invalid User-Agent or rate limiting). Try again "
                "in a moment."
            )
        if response.status_code != 200:
            raise IngestionError(
                f"Chess.com returned HTTP {response.status_code} for {url} "
                f"while fetching {context}."
            )
        try:
            return response.json()
        except ValueError as exc:
            raise IngestionError(
                f"Chess.com returned a non-JSON response for {url} while "
                f"fetching {context}."
            ) from exc

    # -- Parsing / normalization ------------------------------------------

    def _parse_game(self, raw: dict, username: str) -> Optional[GameMetadata]:
        """Normalize a single Chess.com game JSON object into GameMetadata.

        Returns None for games that cannot be analyzed (non-standard variants,
        or games missing a PGN).
        """
        # Only standard chess is analyzable by Stockfish; skip variants.
        if raw.get("rules", "chess") != "chess":
            return None

        pgn = raw.get("pgn")
        if not pgn:
            return None

        white = raw.get("white", {})
        black = raw.get("black", {})
        white_user = (white.get("username") or "").lower()
        black_user = (black.get("username") or "").lower()
        me = username.lower()

        if me == white_user:
            color = "white"
            opponent = black
        elif me == black_user:
            color = "black"
            opponent = white
        else:
            # Username not found in this game (shouldn't happen); skip.
            return None

        result = _normalize_result(white.get("result"), black.get("result"))

        end_time = raw.get("end_time")
        played_at = (
            datetime.utcfromtimestamp(end_time)
            if end_time
            else datetime.utcnow()
        )

        eco, opening_name = _parse_opening(pgn)

        return GameMetadata(
            platform="chesscom",
            game_id=_game_id_from_url(raw.get("url", "")),
            username=username,
            color=color,
            result=result,
            time_control=str(raw.get("time_control", "")),
            played_at=played_at,
            opponent_username=opponent.get("username", ""),
            opponent_rating=opponent.get("rating"),
            user_rating=(white if color == "white" else black).get("rating"),
            opening_eco=eco,
            opening_name=opening_name,
            pgn=pgn,
        )


# -- Module-level helpers --------------------------------------------------


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Drop tzinfo so comparisons match our naive UTC played_at values."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _normalize_result(white_result: Optional[str], black_result: Optional[str]) -> str:
    """Map Chess.com per-side result codes to a PGN result string.

    Exactly one side is "win" in a decisive game; anything else is a draw code
    (agreed, repetition, stalemate, insufficient, 50move, timevsinsufficient).
    """
    if white_result == "win":
        return "1-0"
    if black_result == "win":
        return "0-1"
    return "1/2-1/2"


def _game_id_from_url(url: str) -> str:
    """Derive a stable game id from a Chess.com game URL.

    e.g. https://www.chess.com/game/live/12345678 -> "12345678".
    Falls back to the full URL if no slug is present.
    """
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return slug or url


def _parse_opening(pgn: str) -> tuple[Optional[str], Optional[str]]:
    """Extract (ECO code, opening name) from PGN headers.

    Chess.com PGNs include an ``ECO`` header and an ``ECOUrl`` (from which a
    human-readable name can be derived); the ``Opening`` header is used first
    when present.
    """
    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except Exception:
        return None, None
    if game is None:
        return None, None

    headers = game.headers
    eco = headers.get("ECO") or None

    name = headers.get("Opening")
    if not name:
        eco_url = headers.get("ECOUrl", "")
        if eco_url:
            slug = eco_url.rstrip("/").rsplit("/", 1)[-1]
            name = slug.replace("-", " ") or None
    return eco, name
