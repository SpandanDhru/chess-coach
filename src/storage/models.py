"""SQLAlchemy models for the chess coach database."""

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON, Text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class Game(Base):
    """Chess game record."""
    
    __tablename__ = "games"
    
    id = Column(Integer, primary_key=True)
    game_id = Column(String, unique=True, nullable=False, index=True)
    platform = Column(String, nullable=False)  # 'lichess' or 'chesscom'
    
    # Player info
    username = Column(String, nullable=False)
    color = Column(String, nullable=False)  # 'white' or 'black'
    user_rating = Column(Integer)
    
    # Opponent info
    opponent_username = Column(String)
    opponent_rating = Column(Integer)
    
    # Game metadata
    result = Column(String, nullable=False)  # '1-0', '0-1', '1/2-1/2'
    time_control = Column(String)
    played_at = Column(DateTime, nullable=False, index=True)
    
    # Opening
    opening_eco = Column(String, index=True)
    opening_name = Column(String)
    
    # Raw PGN
    pgn = Column(Text, nullable=False)
    
    # Analysis metadata
    analyzed_at = Column(DateTime)
    
    # Relationships
    positions = relationship("Position", back_populates="game", cascade="all, delete-orphan")
    
    created_at = Column(DateTime, default=datetime.utcnow)


class Position(Base):
    """Analysis of a single position in a game."""
    
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    
    move_number = Column(Integer, nullable=False)
    fen = Column(String, nullable=False)
    move_played = Column(String, nullable=False)  # UCI notation
    
    # Stockfish evaluation
    eval_before = Column(Float)
    eval_after = Column(Float)
    centipawn_loss = Column(Float)
    depth = Column(Integer, default=20)
    
    # Best moves
    best_move = Column(String)
    best_move_eval = Column(Float)
    top_3_moves = Column(JSON)  # [{"move": "e2e4", "eval": 0.3}, ...]
    
    # Classification
    classification = Column(String)  # MoveClassification enum value
    is_blunder = Column(Boolean, default=False, index=True)
    is_missed_tactic = Column(Boolean, default=False)
    mate_in = Column(Integer)  # Mate in N, if applicable
    
    # LLM explanation
    explanation = Column(Text)
    
    # Relationship
    game = relationship("Game", back_populates="positions")
    
    created_at = Column(DateTime, default=datetime.utcnow)


class Opening(Base):
    """Aggregate statistics for openings played."""
    
    __tablename__ = "openings"
    
    id = Column(Integer, primary_key=True)
    eco_code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    
    # Statistics (as white and black)
    games_as_white = Column(Integer, default=0)
    games_as_black = Column(Integer, default=0)
    
    wins_as_white = Column(Integer, default=0)
    wins_as_black = Column(Integer, default=0)
    
    draws_as_white = Column(Integer, default=0)
    draws_as_black = Column(Integer, default=0)
    
    # Average accuracy in first 15 moves
    avg_cp_loss_white = Column(Float)
    avg_cp_loss_black = Column(Float)
    
    # Last played
    last_played = Column(DateTime)
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Pattern(Base):
    """Recurring patterns in user's play (weaknesses, habits)."""
    
    __tablename__ = "patterns"
    
    id = Column(Integer, primary_key=True)
    pattern_type = Column(String, nullable=False, index=True)  # 'tactical', 'positional', 'time_management', etc.
    description = Column(String, nullable=False)
    
    # Frequency and severity
    occurrence_count = Column(Integer, default=1)
    severity = Column(String)  # 'low', 'medium', 'high'
    
    # Context
    phase = Column(String)  # 'opening', 'middlegame', 'endgame', 'all'
    associated_openings = Column(JSON)  # List of ECO codes where this appears
    
    # Examples
    example_game_ids = Column(JSON)  # List of game IDs demonstrating this pattern
    
    # Coaching notes
    coaching_advice = Column(Text)
    
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SyncState(Base):
    """Track last sync timestamp per platform and username."""
    
    __tablename__ = "sync_state"
    
    id = Column(Integer, primary_key=True)
    platform = Column(String, nullable=False)
    username = Column(String, nullable=False)
    last_synced_at = Column(DateTime)
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        # Unique constraint on platform + username
        {"sqlite_autoincrement": True},
    )
