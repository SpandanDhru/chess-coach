"""Database wrapper for SQLAlchemy operations."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import List, Optional
from datetime import datetime
from pathlib import Path

from .models import Base, Game, Position, Opening, Pattern, SyncState


class Database:
    """Database interface for chess coach."""
    
    def __init__(self, db_path: str = "data/chess_coach.db"):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        # Ensure directory exists
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.Session = sessionmaker(bind=self.engine)
        
        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.Session()
    
    # Game operations
    
    def save_game(self, game_data: dict) -> Game:
        """Save a game to the database."""
        # TODO: Implement
        raise NotImplementedError()
    
    def get_game(self, game_id: str) -> Optional[Game]:
        """Retrieve a game by ID."""
        # TODO: Implement
        raise NotImplementedError()
    
    def get_recent_games(self, limit: int = 10) -> List[Game]:
        """Get most recently played games."""
        # TODO: Implement
        raise NotImplementedError()
    
    def game_exists(self, game_id: str) -> bool:
        """Check if a game already exists in the database."""
        with self.get_session() as session:
            return session.query(Game).filter_by(game_id=game_id).first() is not None
    
    # Position operations
    
    def save_analysis(self, game_id: str, positions: List[dict]) -> None:
        """Save position analyses for a game."""
        # TODO: Implement
        raise NotImplementedError()
    
    def get_game_analysis(self, game_id: str) -> List[Position]:
        """Get all position analyses for a game."""
        # TODO: Implement
        raise NotImplementedError()
    
    def get_blunders(self, limit: int = 20) -> List[Position]:
        """Get recent blunder positions for review."""
        # TODO: Implement
        raise NotImplementedError()
    
    # Opening operations
    
    def update_opening_stats(self, eco_code: str, game_result: dict) -> None:
        """Update statistics for an opening."""
        # TODO: Implement
        raise NotImplementedError()
    
    def get_opening_stats(self, eco_code: Optional[str] = None) -> List[Opening]:
        """Get opening statistics, optionally filtered by ECO code."""
        # TODO: Implement
        raise NotImplementedError()
    
    # Pattern operations
    
    def save_pattern(self, pattern_data: dict) -> Pattern:
        """Save or update a recurring pattern."""
        # TODO: Implement
        raise NotImplementedError()
    
    def get_patterns(
        self,
        pattern_type: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> List[Pattern]:
        """Get patterns, optionally filtered."""
        # TODO: Implement
        raise NotImplementedError()
    
    # Sync state operations
    
    def get_last_sync(self, platform: str, username: str) -> Optional[datetime]:
        """Get last sync timestamp for a platform/username."""
        with self.get_session() as session:
            state = session.query(SyncState).filter_by(
                platform=platform,
                username=username,
            ).first()
            return state.last_synced_at if state else None
    
    def update_last_sync(
        self,
        platform: str,
        username: str,
        timestamp: datetime,
    ) -> None:
        """Update last sync timestamp."""
        with self.get_session() as session:
            state = session.query(SyncState).filter_by(
                platform=platform,
                username=username,
            ).first()
            
            if state:
                state.last_synced_at = timestamp
            else:
                state = SyncState(
                    platform=platform,
                    username=username,
                    last_synced_at=timestamp,
                )
                session.add(state)
            
            session.commit()
