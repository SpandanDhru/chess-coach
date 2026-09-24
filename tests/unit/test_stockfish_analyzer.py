"""Tests for Stockfish analyzer."""

import shutil

import pytest

from src.analysis import MoveClassification, StockfishAnalyzer

_STOCKFISH = shutil.which("stockfish")


def test_move_classification():
    """Test move classification logic (no engine needed)."""
    analyzer = StockfishAnalyzer()

    assert analyzer._classify_move(5, None, None) == MoveClassification.BEST
    assert analyzer._classify_move(30, None, None) == MoveClassification.GOOD
    assert analyzer._classify_move(75, None, None) == MoveClassification.INACCURACY
    assert analyzer._classify_move(150, None, None) == MoveClassification.MISTAKE
    assert analyzer._classify_move(350, None, None) == MoveClassification.BLUNDER


def test_classify_move_mate_disruption():
    """Throwing away a forced mate is a blunder regardless of centipawn loss."""
    analyzer = StockfishAnalyzer()
    assert analyzer._classify_move(0, 2, None) == MoveClassification.BLUNDER


@pytest.mark.skipif(_STOCKFISH is None, reason="Requires Stockfish installation")
def test_analyze_game_live():
    """End-to-end analysis of a short game using a real engine."""
    pgn = (
        '[Event "Test"]\n[White "a"]\n[Black "b"]\n[Result "1-0"]\n\n'
        "1. e4 e5 2. Qh5 Nc6 3. Bc4 g6 4. Qf3 Nd4 5. Qxf7# 1-0\n"
    )
    # Shallow depth keeps the test fast.
    with StockfishAnalyzer(_STOCKFISH, depth=8, threads=1) as analyzer:
        analyses = analyzer.analyze_game(pgn, "test-game")

    assert len(analyses) == 9  # 9 plies
    for a in analyses:
        assert a.game_id == "test-game"
        assert a.centipawn_loss >= 0
        assert a.best_move  # UCI string populated
        assert isinstance(a.classification, MoveClassification)
