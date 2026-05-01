"""Base ingester interface for game platforms."""

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class GameMetadata:
    """Normalized game metadata across platforms."""
    
    platform: str
    game_id: str
    username: str
    color: str  # 'white' or 'black'
    result: str  # '1-0', '0-1', '1/2-1/2'
    time_control: str
    played_at: datetime
    opponent_username: str
    opponent_rating: Optional[int]
    user_rating: Optional[int]
    opening_eco: Optional[str]
    opening_name: Optional[str]
    pgn: str


class GameIngester(ABC):
    """Abstract base class for platform-specific game ingesters."""
    
    @abstractmethod
    def fetch_games(
        self,
        username: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[GameMetadata]:
        """
        Fetch games for a user within a time range.
        
        Args:
            username: Platform username
            since: Only fetch games played after this date
            until: Only fetch games played before this date
            limit: Maximum number of games to fetch
            
        Returns:
            List of normalized game metadata
        """
        pass
    
    @abstractmethod
    def get_last_synced(self, username: str) -> Optional[datetime]:
        """Get the timestamp of the last synced game for this user."""
        pass
    
    @abstractmethod
    def update_last_synced(self, username: str, timestamp: datetime) -> None:
        """Update the last synced timestamp for this user."""
        pass
