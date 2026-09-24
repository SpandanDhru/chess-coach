"""Tests for the LLM explainer (OpenAI client fully mocked, no network)."""

from types import SimpleNamespace

import pytest

from src.analysis.llm_explainer import LLMExplainer
from src.analysis.models import (
    GameAnalysisSummary,
    MoveClassification,
    PositionAnalysis,
)


class _FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


def _make_explainer(content="Great game, but watch move 12."):
    explainer = LLMExplainer(api_key="sk-test", model="gpt-4o-mini", user_rating=1400)
    fake = _FakeCompletions(content)
    explainer.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return explainer, fake


def _blunder_position():
    return PositionAnalysis(
        game_id="g1",
        move_number=12,
        # position after 1.e4 e5 2.Qh5 Nc6 3.Bc4 g6?? (before the blunder is fine)
        fen="r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3",
        move_played="g7g6",
        eval_before=50.0,
        eval_after=900.0,
        centipawn_loss=850.0,
        best_move="d8e7",
        best_move_eval=50.0,
        top_3_moves=[("d8e7", 50.0)],
        classification=MoveClassification.BLUNDER,
    )


def test_summarize_game_single_call_and_returns_content():
    explainer, fake = _make_explainer("Coaching writeup here.")
    pos = _blunder_position()
    summary = GameAnalysisSummary(
        game_id="g1",
        total_moves=20,
        best_moves=10,
        good_moves=5,
        inaccuracies=2,
        mistakes=2,
        blunders=1,
        avg_centipawn_loss=45.0,
        blunder_positions=[pos],
        missed_tactics=[],
        opening_accuracy=20.0,
        middlegame_accuracy=60.0,
        endgame_accuracy=30.0,
    )

    result = explainer.summarize_game(summary, [pos], game_context={"color": "black"})

    assert result == "Coaching writeup here."
    # Exactly one OpenAI call for a per-game writeup (cost discipline).
    assert len(fake.calls) == 1
    # The prompt should reference the worst move in readable SAN.
    user_msg = fake.calls[0]["messages"][1]["content"]
    assert "Move 12" in user_msg
    assert fake.calls[0]["model"] == "gpt-4o-mini"


def test_explain_position_returns_content():
    explainer, fake = _make_explainer("You dropped a pawn.")
    result = explainer.explain_position(_blunder_position())
    assert result == "You dropped a pawn."
    assert len(fake.calls) == 1
