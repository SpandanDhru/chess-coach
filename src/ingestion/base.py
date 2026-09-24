"""Base ingester interface for game platforms."""

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass


def speed_bucket(time_control: Optional[str], platform: str) -> str:
    """Normalize a game's time control into a speed bucket.

    Both platforms are collapsed onto Lichess-style buckets so aggregation can
    group across sources. Lichess already stores the bucket name in
    ``time_control`` (we set it from the game's ``speed``); Chess.com stores the
    base time in seconds (e.g. "600", or "180+2"), which we bucket by the FIDE-ish
    thresholds Lichess uses (estimated seconds = base + 40 * increment).
    """
    if not time_control:
        return "unknown"
    tc = time_control.strip().lower()

    # Lichess (or an already-bucketed value): pass known names straight through.
    known = {"ultrabullet", "bullet", "blitz", "rapid", "classical", "correspondence"}
    if tc in known:
        return "ultrabullet" if tc == "ultrabullet" else tc

    # Chess.com: "600" or "180+2" (seconds), or "1/259200" for daily/correspondence.
    if tc.startswith("1/"):
        return "correspondence"
    base, _, inc = tc.partition("+")
    try:
        estimated = int(base) + 40 * int(inc or 0)
    except ValueError:
        return "unknown"
    if estimated < 29:
        return "ultrabullet"
    if estimated < 179:
        return "bullet"
    if estimated < 479:
        return "blitz"
    if estimated < 1499:
        return "rapid"
    return "classical"


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
