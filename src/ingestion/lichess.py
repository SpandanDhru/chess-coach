"""Lichess game ingester using their public games-export API.

Lichess exposes a user's games as a newline-delimited JSON (NDJSON) stream:

    GET https://lichess.org/api/games/user/{username}
        ?opening=true&pgnInJson=true&clocks=false&evals=false&max=...&since=...&until=...
    Accept: application/x-ndjson    -> one JSON game object per line

Reads work anonymously but are rate-limited; an optional bearer token (a free
personal access token) lifts those limits when pulling large histories. ``since``
and ``until`` are milliseconds since the Unix epoch.
"""

import io
import json
from datetime import datetime, timezone
from typing import List, Optional

import chess.pgn
import httpx

from .base import GameIngester, GameMetadata


class IngestionError(Exception):
    """Raised when Lichess data cannot be fetched or parsed.

    Messages are written to be actionable and shown directly to the user.
    """


# A descriptive User-Agent is good API citizenship; Lichess also keys some
# rate-limit heuristics off it.
_USER_AGENT = "chess-coach/1.0 (personal game analysis tool)"


class LichessIngester(GameIngester):
    """Ingest games from the Lichess public API."""

    BASE_URL = "https://lichess.org/api"

    def __init__(self, db_connection=None, token: Optional[str] = None):
        """
        Initialize the Lichess ingester.

        Args:
            db_connection: Database connection for tracking sync state.
            token: Optional Lichess personal access token (raises rate limits).
        """
        self.db = db_connection
        self.token = token
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/x-ndjson",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(timeout=60.0, headers=headers)

    # -- Public API --------------------------------------------------------

    def fetch_games(
        self,
        username: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[GameMetadata]:
        """
        Fetch games from Lichess, newest first.

        The API returns games newest-first by default. ``since`` / ``until``
        filter by the time the game finished; ``limit`` maps to ``max``.
        """
        params = {
            "opening": "true",
            "pgnInJson": "true",
            "clocks": "false",
            "evals": "false",
        }
        if limit is not None:
            params["max"] = limit
        since_ms = _to_epoch_ms(since)
        until_ms = _to_epoch_ms(until)
        if since_ms is not None:
            params["since"] = since_ms
        if until_ms is not None:
            params["until"] = until_ms

        url = f"{self.BASE_URL}/games/user/{username.lower()}"
        games: List[GameMetadata] = []
        for raw in self._stream_ndjson(url, params, username):
            metadata = self._parse_game(raw, username)
            if metadata is not None:
                games.append(metadata)
        return games

    def get_last_synced(self, username: str) -> Optional[datetime]:
        """Query the database for the last sync timestamp."""
        if self.db is None:
            return None
        return self.db.get_last_sync("lichess", username)

    def update_last_synced(self, username: str, timestamp: datetime) -> None:
        """Update the database with a new sync timestamp."""
        if self.db is None:
            return
        self.db.update_last_sync("lichess", username, timestamp)

    # -- HTTP helpers ------------------------------------------------------

    def _stream_ndjson(self, url: str, params: dict, username: str) -> List[dict]:
        """Fetch the NDJSON stream and parse it into a list of game dicts."""
        try:
            response = self.client.get(url, params=params)
        except httpx.RequestError as exc:
            raise IngestionError(
                f"Network error fetching Lichess games for '{username}' "
                f"({url}): {exc}"
            ) from exc

        if response.status_code == 404:
            raise IngestionError(
                f"Lichess returned 404 for '{username}' — the account likely does "
                "not exist. Double-check the handle."
            )
        if response.status_code == 429:
            raise IngestionError(
                "Lichess rate-limited the request (HTTP 429). Wait a minute and "
                "retry, or set LICHESS_TOKEN in .env (a free personal access token) "
                "to raise the limits for large syncs."
            )
        if response.status_code != 200:
            raise IngestionError(
                f"Lichess returned HTTP {response.status_code} for {url} while "
                f"fetching games for '{username}'."
            )

        games: List[dict] = []
        for line in response.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                games.append(json.loads(line))
            except ValueError as exc:
                raise IngestionError(
                    f"Lichess returned a non-JSON line while fetching games for "
                    f"'{username}': {line[:80]!r}"
                ) from exc
        return games

    # -- Parsing / normalization ------------------------------------------

    def _parse_game(self, raw: dict, username: str) -> Optional[GameMetadata]:
        """Normalize a single Lichess game object into GameMetadata.

        Returns None for games that cannot be analyzed (non-standard variants,
        or games we cannot turn into a PGN).
        """
        # Only standard chess is analyzable by Stockfish; skip variants.
        if raw.get("variant", "standard") != "standard":
            return None

        players = raw.get("players", {})
        white = players.get("white", {})
        black = players.get("black", {})
        white_user = ((white.get("user") or {}).get("name") or "").lower()
        black_user = ((black.get("user") or {}).get("name") or "").lower()
        me = username.lower()

        if me == white_user:
            color, opponent = "white", black
        elif me == black_user:
            color, opponent = "black", white
        else:
            # Username not found in this game (shouldn't happen); skip.
            return None

        pgn = _pgn_for(raw)
        if not pgn:
            return None

        winner = raw.get("winner")
        result = (
            "1-0" if winner == "white" else "0-1" if winner == "black" else "1/2-1/2"
        )

        end_ms = raw.get("lastMoveAt") or raw.get("createdAt")
        played_at = (
            datetime.utcfromtimestamp(end_ms / 1000) if end_ms else datetime.utcnow()
        )

        opening = raw.get("opening", {}) or {}
        opponent_user = (opponent.get("user") or {}).get("name") or ""

        return GameMetadata(
            platform="lichess",
            game_id=raw.get("id", ""),
            username=username,
            color=color,
            result=result,
            # Store the Lichess speed bucket directly (bullet/blitz/rapid/...).
            time_control=str(raw.get("speed", "")),
            played_at=played_at,
            opponent_username=opponent_user,
            opponent_rating=opponent.get("rating"),
            user_rating=(white if color == "white" else black).get("rating"),
            opening_eco=opening.get("eco"),
            opening_name=opening.get("name"),
            pgn=pgn,
        )


# -- Module-level helpers --------------------------------------------------


def _to_epoch_ms(dt: Optional[datetime]) -> Optional[int]:
    """Convert a datetime to milliseconds since the Unix epoch (UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _pgn_for(raw: dict) -> Optional[str]:
    """Return a parseable PGN for a Lichess game.

    Prefers the ``pgn`` field (present when ``pgnInJson=true``); otherwise builds
    a minimal PGN from the SAN ``moves`` string so Stockfish can still analyze it.
    """
    pgn = raw.get("pgn")
    if pgn:
        return pgn

    moves = raw.get("moves")
    if not moves:
        return None

    winner = raw.get("winner")
    result = (
        "1-0" if winner == "white" else "0-1" if winner == "black" else "1/2-1/2"
    )
    minimal = f'[Event "?"]\n[Result "{result}"]\n\n{moves} {result}\n'
    # Validate it parses before handing it downstream.
    try:
        if chess.pgn.read_game(io.StringIO(minimal)) is None:
            return None
    except Exception:
        return None
    return minimal
