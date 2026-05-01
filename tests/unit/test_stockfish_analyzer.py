"""Tests for Stockfish analyzer."""

import pytest
from src.analysis import StockfishAnalyzer, MoveClassification


@pytest.fixture
def analyzer():
    """Create a StockfishAnalyzer instance for testing."""
    # This would need a valid stockfish path
    # return StockfishAnalyzer(stockfish_path="/usr/games/stockfish")
    pytest.skip("Requires Stockfish installation")


def test_move_classification():
    """Test move classification logic."""
    analyzer = StockfishAnalyzer()
    
    # Test best move
    assert analyzer._classify_move(5, None, None) == MoveClassification.BEST
    
    # Test good move
    assert analyzer._classify_move(30, None, None) == MoveClassification.GOOD
    
    # Test inaccuracy
    assert analyzer._classify_move(75, None, None) == MoveClassification.INACCURACY
    
    # Test mistake
    assert analyzer._classify_move(150, None, None) == MoveClassification.MISTAKE
    
    # Test blunder
    assert analyzer._classify_move(350, None, None) == MoveClassification.BLUNDER


# Add more tests as you implement functionality
