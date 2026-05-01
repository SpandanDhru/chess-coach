"""Data models for chess analysis."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List


class MoveClassification(Enum):
    """Classification of move quality based on centipawn loss."""
    
    BEST = "best"  # 0-10cp loss
    EXCELLENT = "excellent"  # Same as best
    GOOD = "good"  # 10-50cp loss
    INACCURACY = "inaccuracy"  # 50-100cp loss
    MISTAKE = "mistake"  # 100-300cp loss
    BLUNDER = "blunder"  # 300+cp loss or mate line disruption
    BOOK = "book"  # Opening book move
    FORCED = "forced"  # Only legal move


@dataclass
class PositionAnalysis:
    """Analysis of a single position in a game."""
    
    game_id: str
    move_number: int
    fen: str
    move_played: str  # UCI notation
    
    # Stockfish evaluation
    eval_before: float  # Centipawns (positive = white advantage)
    eval_after: float
    centipawn_loss: float
    
    # Best moves
    best_move: str  # UCI notation
    best_move_eval: float
    top_3_moves: List[tuple[str, float]]  # [(move, eval), ...]
    
    # Classification
    classification: MoveClassification
    
    # Optional fields
    depth: int = 20  # Stockfish analysis depth
    is_blunder: bool = False
    is_missed_tactic: bool = False
    mate_in: Optional[int] = None  # Mate in N moves (if applicable)
    
    # LLM explanation (populated later)
    explanation: Optional[str] = None
    
    def __post_init__(self):
        """Auto-calculate derived fields."""
        self.centipawn_loss = abs(self.eval_after - self.eval_before)
        self.is_blunder = self.classification == MoveClassification.BLUNDER


@dataclass
class GameAnalysisSummary:
    """Summary of full game analysis."""
    
    game_id: str
    total_moves: int
    
    # Move quality breakdown
    best_moves: int
    good_moves: int
    inaccuracies: int
    mistakes: int
    blunders: int
    
    # Average metrics
    avg_centipawn_loss: float
    
    # Critical moments
    blunder_positions: List[PositionAnalysis]
    missed_tactics: List[PositionAnalysis]
    
    # Phase breakdown
    opening_accuracy: float  # Moves 1-15
    middlegame_accuracy: float  # Moves 16-40
    endgame_accuracy: float  # Moves 41+
    
    # LLM-generated summary
    summary: Optional[str] = None
