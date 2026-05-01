"""Chess.com game ingester using their public API."""

from typing import List, Optional
from datetime import datetime
import httpx

from .base import GameIngester, GameMetadata


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
        self.client = httpx.Client(timeout=30.0)
    
    def fetch_games(
        self,
        username: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[GameMetadata]:
        """
        Fetch games from Chess.com.
        
        Uses the /pub/player/{username}/games/{YYYY}/{MM} endpoint.
        """
        # TODO: Implement
        # 1. Get list of archive URLs
        # 2. Filter by date range
        # 3. Fetch PGN archives
        # 4. Parse and normalize to GameMetadata
        raise NotImplementedError("Chess.com ingestion not yet implemented")
    
    def get_last_synced(self, username: str) -> Optional[datetime]:
        """Query database for last sync timestamp."""
        # TODO: Implement database query
        raise NotImplementedError()
    
    def update_last_synced(self, username: str, timestamp: datetime) -> None:
        """Update database with new sync timestamp."""
        # TODO: Implement database update
        raise NotImplementedError()
    
    def _parse_chesscom_pgn(self, pgn_text: str) -> List[GameMetadata]:
        """Parse Chess.com PGN format into normalized metadata."""
        # TODO: Implement PGN parsing
        raise NotImplementedError()
