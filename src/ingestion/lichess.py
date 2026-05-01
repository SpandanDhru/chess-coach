"""Lichess game ingester using their public API."""

from typing import List, Optional
from datetime import datetime
import httpx

from .base import GameIngester, GameMetadata


class LichessIngester(GameIngester):
    """Ingest games from Lichess API."""
    
    BASE_URL = "https://lichess.org/api"
    
    def __init__(self, api_token: Optional[str] = None, db_connection=None):
        """
        Initialize Lichess ingester.
        
        Args:
            api_token: Optional Lichess API token for higher rate limits
            db_connection: Database connection for tracking sync state
        """
        self.api_token = api_token
        self.db = db_connection
        
        headers = {}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        
        self.client = httpx.Client(
            headers=headers,
            timeout=30.0,
        )
    
    def fetch_games(
        self,
        username: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[GameMetadata]:
        """
        Fetch games from Lichess.
        
        Uses the /api/games/user/{username} endpoint with NDJSON streaming.
        """
        # TODO: Implement
        # 1. Build query parameters (since timestamp, until, max games)
        # 2. Stream NDJSON response
        # 3. Parse and normalize to GameMetadata
        raise NotImplementedError("Lichess ingestion not yet implemented")
    
    def get_last_synced(self, username: str) -> Optional[datetime]:
        """Query database for last sync timestamp."""
        # TODO: Implement database query
        raise NotImplementedError()
    
    def update_last_synced(self, username: str, timestamp: datetime) -> None:
        """Update database with new sync timestamp."""
        # TODO: Implement database update
        raise NotImplementedError()
    
    def _parse_lichess_game(self, game_json: dict) -> GameMetadata:
        """Parse Lichess JSON game object into normalized metadata."""
        # TODO: Implement JSON parsing
        raise NotImplementedError()
