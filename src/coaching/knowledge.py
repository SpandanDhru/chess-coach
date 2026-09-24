"""Semantic-embeddings RAG over a player's aggregated game data.

This is deliberately a *transparent* RAG implementation so every stage is
visible:

    1. build_documents  — turn structured aggregates + patterns into text docs
    2. index            — embed those docs (one batched call) and store vectors
    3. retrieve         — embed the question, rank docs by cosine similarity
    4. answer           — feed the top-k docs to the LLM as the only ground truth

The vector store is just a SQLite table (`embeddings`) and similarity is plain
numpy — no vector database, nothing hidden. Swap in FAISS later if the corpus
ever outgrows an in-memory scan.
"""

from typing import List, Optional, Tuple

import numpy as np

from ..analysis.llm_explainer import LLMExplainer
from ..storage.database import Database


class Knowledge:
    """Builds, indexes, and queries the RAG knowledge base."""

    def __init__(self, db: Database, explainer: LLMExplainer):
        self.db = db
        self.explainer = explainer

    # -- 1. Document building ---------------------------------------------

    def build_documents(self, username: Optional[str] = None) -> List[dict]:
        """Turn aggregates + persisted patterns into retrievable text documents.

        Each document is a self-contained natural-language statement so it reads
        well both to the embedding model and, once retrieved, to the LLM.
        """
        docs: List[dict] = []

        for o in self.db.aggregate_by_opening(username):
            cp = o["avg_cp_loss"]
            cp_txt = f"average centipawn loss {cp}" if cp is not None else "not yet analyzed"
            docs.append(
                {
                    "doc_id": f"opening:{o['opening']}",
                    "source_type": "opening",
                    "text": (
                        f"Opening '{o['opening']}': {o['games']} games "
                        f"({o['as_white']} as White, {o['as_black']} as Black), "
                        f"record {o['wins']}W/{o['draws']}D/{o['losses']}L "
                        f"(score {o['score_pct']}%), {cp_txt}, "
                        f"{o['blunders']} blunders."
                    ),
                }
            )

        for p in self.db.aggregate_by_phase(username):
            docs.append(
                {
                    "doc_id": f"phase:{p['phase']}",
                    "source_type": "phase",
                    "text": (
                        f"Game phase '{p['phase']}': {p['moves']} analyzed moves, "
                        f"average centipawn loss {p['avg_cp_loss']}, "
                        f"{p['blunders']} blunders "
                        f"(blunder rate {p['blunder_rate']} per move)."
                    ),
                }
            )

        for t in self.db.aggregate_by_time_control(username):
            cp = t["avg_cp_loss"]
            cp_txt = f"average centipawn loss {cp}" if cp is not None else "not yet analyzed"
            docs.append(
                {
                    "doc_id": f"time_control:{t['time_control']}",
                    "source_type": "time_control",
                    "text": (
                        f"Time control '{t['time_control']}': {t['games']} games, "
                        f"record {t['wins']}W/{t['draws']}D/{t['losses']}L "
                        f"(score {t['score_pct']}%), {cp_txt}, "
                        f"{t['blunders']} blunders."
                    ),
                }
            )

        for pat in self.db.get_patterns():
            docs.append(
                {
                    "doc_id": f"pattern:{pat['id']}",
                    "source_type": "pattern",
                    "text": (
                        f"Recurring pattern ({pat['severity']} severity): "
                        f"{pat['description']} — seen {pat['occurrence_count']} times "
                        f"in phase '{pat['phase']}'. {pat['coaching_advice'] or ''}"
                    ).strip(),
                }
            )

        return docs

    # -- 2. Indexing -------------------------------------------------------

    def index(self, username: Optional[str] = None) -> int:
        """(Re)build the knowledge base: embed all documents and store them.

        Returns the number of documents indexed. One batched embedding call.
        """
        docs = self.build_documents(username)
        if not docs:
            return 0

        vectors = self.explainer.embed_texts([d["text"] for d in docs])
        rows = [
            {
                "doc_id": d["doc_id"],
                "source_type": d["source_type"],
                "username": username,
                "text": d["text"],
                "vector": vec,
            }
            for d, vec in zip(docs, vectors)
        ]
        # Replace the previous index for this scope so it stays in sync.
        self.db.clear_embeddings(username)
        self.db.save_embeddings(rows)
        return len(rows)

    # -- 3. Retrieval ------------------------------------------------------

    def retrieve(
        self,
        question: str,
        k: int = 5,
        username: Optional[str] = None,
    ) -> List[dict]:
        """Return the top-k stored documents most similar to the question.

        Each returned dict is the stored document plus a ``score`` (cosine
        similarity in [-1, 1]).
        """
        stored = self.db.get_embeddings(username)
        if not stored:
            return []

        matrix = np.array([row["vector"] for row in stored], dtype=float)
        query_vec = np.array(
            self.explainer.embed_texts([question])[0], dtype=float
        )
        scores = _cosine_similarity(query_vec, matrix)

        ranked = sorted(
            zip(stored, scores), key=lambda pair: pair[1], reverse=True
        )
        results = []
        for doc, score in ranked[:k]:
            results.append({**doc, "score": float(score)})
        return results

    # -- 4. Answer ---------------------------------------------------------

    def answer(
        self,
        question: str,
        k: int = 5,
        username: Optional[str] = None,
    ) -> Tuple[str, List[dict]]:
        """Retrieve then generate. Returns (answer, retrieved_docs).

        Raises ``KnowledgeError`` if the knowledge base is empty.
        """
        docs = self.retrieve(question, k=k, username=username)
        if not docs:
            raise KnowledgeError(
                "The knowledge base is empty. Run `index` first (after syncing "
                "and analyzing some games)."
            )
        answer = self.explainer.answer_question(question, docs)
        return answer, docs


class KnowledgeError(Exception):
    """Raised when a RAG query cannot be answered (e.g. empty index)."""


# -- Module-level helpers --------------------------------------------------


def _cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between a query vector and each row of a matrix."""
    query_norm = np.linalg.norm(query)
    row_norms = np.linalg.norm(matrix, axis=1)
    # Guard against zero vectors to avoid division-by-zero warnings.
    denom = np.where(row_norms == 0, 1.0, row_norms) * (query_norm or 1.0)
    return matrix.dot(query) / denom
