"""Tests for the semantic-embeddings RAG layer (no network)."""

from datetime import datetime

import pytest

from src.coaching.knowledge import Knowledge, KnowledgeError, _cosine_similarity
from src.storage.database import Database


class FakeExplainer:
    """Stand-in for LLMExplainer: deterministic vectors, no OpenAI calls."""

    def __init__(self, vectors=None, query_vector=None):
        # Map exact text -> vector for embed_texts; fallback to a zero vector.
        self.vectors = vectors or {}
        self.query_vector = query_vector
        self.answered_with = None

    def embed_texts(self, texts):
        out = []
        for t in texts:
            if self.query_vector is not None and t == "__QUERY__":
                out.append(self.query_vector)
            else:
                out.append(self.vectors.get(t, [0.0, 0.0, 0.0]))
        return out

    def answer_question(self, question, context_docs):
        self.answered_with = context_docs
        return "grounded answer"


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def _game(game_id, **overrides):
    base = {
        "game_id": game_id,
        "platform": "chesscom",
        "username": "alice",
        "color": "white",
        "result": "1-0",
        "played_at": datetime(2024, 1, 1),
        "pgn": "1. e4 e5 1-0",
        "opponent_username": "bob",
        "opening_eco": "C50",
        "opening_name": "Italian Game",
        "time_control": "600",
    }
    base.update(overrides)
    return base


def test_cosine_similarity_ranks_direction():
    import numpy as np

    matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    scores = _cosine_similarity(np.array([1.0, 0.1, 0.0]), matrix)
    assert scores.argmax() == 0  # closest to the first row


def test_retrieve_returns_top_k_by_similarity(db):
    db.save_embeddings(
        [
            {"doc_id": "a", "source_type": "opening", "username": None,
             "text": "Italian Game stats", "vector": [1.0, 0.0, 0.0]},
            {"doc_id": "b", "source_type": "phase", "username": None,
             "text": "Endgame stats", "vector": [0.0, 1.0, 0.0]},
        ]
    )
    explainer = FakeExplainer(query_vector=[0.9, 0.1, 0.0])
    knowledge = Knowledge(db, explainer)

    results = knowledge.retrieve("__QUERY__", k=1)
    assert len(results) == 1
    assert results[0]["doc_id"] == "a"
    assert results[0]["score"] > 0.9


def test_answer_raises_when_index_empty(db):
    knowledge = Knowledge(db, FakeExplainer(query_vector=[1.0, 0.0, 0.0]))
    with pytest.raises(KnowledgeError, match="knowledge base is empty"):
        knowledge.answer("__QUERY__")


def test_answer_grounds_on_retrieved_docs(db):
    db.save_embeddings(
        [
            {"doc_id": "a", "source_type": "opening", "username": None,
             "text": "Italian Game stats", "vector": [1.0, 0.0, 0.0]},
        ]
    )
    explainer = FakeExplainer(query_vector=[1.0, 0.0, 0.0])
    knowledge = Knowledge(db, explainer)

    answer, docs = knowledge.answer("__QUERY__", k=1)
    assert answer == "grounded answer"
    assert docs[0]["doc_id"] == "a"
    # The completion was handed the retrieved doc as its only context.
    assert explainer.answered_with[0]["doc_id"] == "a"


def test_build_documents_covers_all_sources(db):
    db.save_game(_game("g1"))
    db.save_analysis(
        "g1",
        [
            {"move_number": 5, "fen": "f", "move_played": "e2e4",
             "eval_before": 20.0, "eval_after": 25.0, "centipawn_loss": 5.0,
             "classification": "good", "is_blunder": False},
        ],
    )
    knowledge = Knowledge(db, FakeExplainer())
    docs = knowledge.build_documents("alice")
    source_types = {d["source_type"] for d in docs}
    assert {"opening", "phase", "time_control"} <= source_types
    assert any("Italian Game" in d["text"] for d in docs)


def test_index_embeds_and_stores(db):
    db.save_game(_game("g1"))
    db.save_analysis(
        "g1",
        [
            {"move_number": 5, "fen": "f", "move_played": "e2e4",
             "eval_before": 20.0, "eval_after": 25.0, "centipawn_loss": 5.0,
             "classification": "good", "is_blunder": False},
        ],
    )
    # Every doc embeds to the same 2-vector; we only assert count + storage here.
    knowledge = Knowledge(db, FakeExplainer())

    # Patch embed_texts to return one vector per document.
    def embed(texts):
        return [[float(i), 1.0] for i, _ in enumerate(texts)]

    knowledge.explainer.embed_texts = embed

    count = knowledge.index("alice")
    assert count > 0
    stored = db.get_embeddings("alice")
    assert len(stored) == count
    assert all(len(row["vector"]) == 2 for row in stored)


def test_index_replaces_previous_scope(db):
    db.save_game(_game("g1"))
    db.save_analysis(
        "g1",
        [{"move_number": 5, "fen": "f", "move_played": "e2e4",
          "eval_before": 20.0, "eval_after": 25.0, "centipawn_loss": 5.0,
          "classification": "good", "is_blunder": False}],
    )
    knowledge = Knowledge(db, FakeExplainer())
    knowledge.explainer.embed_texts = lambda texts: [[1.0, 0.0] for _ in texts]

    first = knowledge.index("alice")
    second = knowledge.index("alice")  # rebuild, not append
    assert len(db.get_embeddings("alice")) == second == first
