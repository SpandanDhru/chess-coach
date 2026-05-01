"""Stockfish engine wrapper for position analysis."""

import chess
import chess.engine
from typing import List, Optional
from pathlib import Path

from .models import PositionAnalysis, MoveClassification


class StockfishAnalyzer:
    """Analyze chess positions using Stockfish engine."""
    
    def __init__(
        self,
        stockfish_path: str = "/usr/games/stockfish",
        depth: int = 20,
        threads: int = 1,
    ):
        """
        Initialize Stockfish analyzer.
        
        Args:
            stockfish_path: Path to Stockfish binary
            depth: Analysis depth (18-22 recommended)
            threads: Number of CPU threads to use
        """
        self.stockfish_path = Path(stockfish_path)
        self.depth = depth
        self.threads = threads
        self.engine: Optional[chess.engine.SimpleEngine] = None
    
    def __enter__(self):
        """Context manager entry - start engine."""
        self.engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path)
        self.engine.configure({"Threads": self.threads})
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close engine."""
        if self.engine:
            self.engine.quit()
    
    def analyze_position(
        self,
        board: chess.Board,
        move_played: chess.Move,
    ) -> PositionAnalysis:
        """
        Analyze a single position and the move played.
        
        Args:
            board: Board state before the move
            move_played: The move that was played
            
        Returns:
            PositionAnalysis with Stockfish evaluation
        """
        if not self.engine:
            raise RuntimeError("Engine not started. Use 'with' context manager.")
        
        # TODO: Implement
        # 1. Analyze position before move
        # 2. Get top 3 moves and evaluations
        # 3. Apply the move played
        # 4. Analyze position after move
        # 5. Calculate centipawn loss
        # 6. Classify move quality
        # 7. Check for missed tactics (mate in N)
        
        raise NotImplementedError("Position analysis not yet implemented")
    
    def analyze_game(
        self,
        pgn: str,
        game_id: str,
    ) -> List[PositionAnalysis]:
        """
        Analyze all positions in a game.
        
        Args:
            pgn: PGN string of the game
            game_id: Unique identifier for the game
            
        Returns:
            List of PositionAnalysis for each move
        """
        # TODO: Implement
        # 1. Parse PGN with python-chess
        # 2. Iterate through moves
        # 3. Analyze each position
        # 4. Return full analysis list
        
        raise NotImplementedError("Game analysis not yet implemented")
    
    def _classify_move(
        self,
        centipawn_loss: float,
        mate_before: Optional[int],
        mate_after: Optional[int],
    ) -> MoveClassification:
        """
        Classify move quality based on centipawn loss.
        
        Standard classification:
        - Best/Excellent: 0-10cp loss
        - Good: 10-50cp loss
        - Inaccuracy: 50-100cp loss
        - Mistake: 100-300cp loss
        - Blunder: 300+cp loss or mate disruption
        """
        # Handle mate disruptions
        if mate_before and not mate_after:
            return MoveClassification.BLUNDER
        
        # Standard centipawn classification
        if centipawn_loss <= 10:
            return MoveClassification.BEST
        elif centipawn_loss <= 50:
            return MoveClassification.GOOD
        elif centipawn_loss <= 100:
            return MoveClassification.INACCURACY
        elif centipawn_loss <= 300:
            return MoveClassification.MISTAKE
        else:
            return MoveClassification.BLUNDER
