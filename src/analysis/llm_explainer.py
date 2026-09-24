"""LLM-powered explanations for chess positions using OpenAI API.

Cost note: every method here makes a paid OpenAI call. `coach --game-id` uses
exactly one `summarize_game` call per game. Never call these in an unbounded
loop — the CLI guards any batch fan-out with a limit + confirmation.
"""

from typing import List, Optional

import chess
import openai

from .models import PositionAnalysis, GameAnalysisSummary


class LLMError(Exception):
    """Raised when an OpenAI call fails. Message is safe to show the user."""


class LLMExplainer:
    """Generate natural language explanations for chess positions."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        user_rating: Optional[int] = None,
        embedding_model: str = "text-embedding-3-small",
        piece_markup: bool = False,
    ):
        """
        Initialize LLM explainer.

        Args:
            api_key: OpenAI API key
            model: Model to use (gpt-4o-mini recommended for cost)
            user_rating: User's rating for explanation calibration
            embedding_model: Model used for RAG embeddings (index/ask)
            piece_markup: When True, the coach wraps piece references in
                ``{{wN}}``-style tokens so a UI can render piece icons. Off by
                default so CLI output stays clean plain text.
        """
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.embedding_model = embedding_model
        self.user_rating = user_rating or 1200  # Default to beginner
        self.piece_markup = piece_markup

    # -- Public API --------------------------------------------------------

    def explain_position(self, analysis: PositionAnalysis) -> str:
        """
        Generate a natural-language explanation for why a move was good/bad.

        Args:
            analysis: Position analysis from Stockfish

        Returns:
            Plain-English explanation tailored to the user's level.
        """
        prompt = self._build_position_prompt(analysis)
        return self._chat(
            system=self._coach_system_prompt(),
            user=prompt,
            # Generous cap: reasoning models spend part of this budget on
            # internal reasoning before emitting the answer.
            max_tokens=1000,
        )

    def summarize_game(
        self,
        summary: GameAnalysisSummary,
        all_analyses: List[PositionAnalysis],
        game_context: Optional[dict] = None,
    ) -> str:
        """
        Generate a coaching writeup for an entire game in a single API call.

        Args:
            summary: Aggregate game analysis statistics
            all_analyses: Full list of position analyses (used for context)
            game_context: Optional {color, result, opponent_username,
                opening_name} for a more grounded writeup.

        Returns:
            A coaching writeup naming the game's key moments and themes.
        """
        prompt = self._build_summary_prompt(summary, game_context)
        return self._chat(
            system=self._coach_system_prompt(),
            user=prompt,
            # Generous cap: reasoning models spend part of this budget on
            # internal reasoning before emitting the writeup.
            max_tokens=2000,
        )

    def generate_coaching_report(
        self,
        opening: Optional[str] = None,
        pattern_type: Optional[str] = None,
        games_data: Optional[dict] = None,
    ) -> str:
        """
        Generate a coaching report on specific aspects of play from aggregates.
        """
        lines = [
            "Write a short coaching report based on these aggregate statistics "
            "from the player's games.",
        ]
        if opening:
            lines.append(f"Focus opening: {opening}")
        if pattern_type:
            lines.append(f"Focus area: {pattern_type}")
        if games_data:
            lines.append(f"Data: {games_data}")
        return self._chat(
            system=self._coach_system_prompt(),
            user="\n".join(lines),
            max_tokens=1500,
        )

    # -- RAG: embeddings + grounded answering ------------------------------

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts in a single API call.

        Batching keeps cost predictable: indexing N documents is one request,
        and each `ask` embeds just the question. Returns vectors in input order.
        """
        if not texts:
            return []
        try:
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=texts,
            )
        except openai.AuthenticationError as exc:
            raise LLMError(
                "OpenAI rejected the API key while embedding. Check OPENAI_API_KEY."
            ) from exc
        except openai.RateLimitError as exc:
            raise LLMError(
                "OpenAI rate limit or insufficient quota hit while embedding."
            ) from exc
        except openai.APIError as exc:
            raise LLMError(f"OpenAI embedding error: {exc}") from exc
        # The API guarantees data is returned in the same order as the input.
        return [item.embedding for item in response.data]

    def answer_question(self, question: str, context_docs: List[dict]) -> str:
        """Answer a natural-language question grounded in retrieved documents.

        This is the "augmented generation" step: the retrieved context is the
        only ground truth the model should use, so it can't invent stats.
        """
        context = "\n".join(
            f"- {doc['text']}" for doc in context_docs
        )
        user = (
            "Answer the player's question using ONLY the retrieved statistics "
            "below. If they don't contain the answer, say so plainly rather than "
            "guessing. Be specific and cite the numbers.\n\n"
            f"Question: {question}\n\n"
            f"Retrieved statistics about this player's games:\n{context}"
        )
        return self._chat(
            system=self._coach_system_prompt(),
            user=user,
            max_tokens=1000,
        )

    # -- Prompt building ---------------------------------------------------

    def _coach_system_prompt(self) -> str:
        prompt = (
            "You are an experienced, encouraging chess coach. Explain clearly and "
            f"concretely for a player rated about {self.user_rating}. Avoid engine "
            "jargon; focus on ideas, plans, and practical takeaways. Be concise."
        )
        if self.piece_markup:
            prompt += (
                " Whenever you refer to a specific chess piece, wrap it in a token "
                "of the form {{<color><piece>}} where <color> is 'w' or 'b' and "
                "<piece> is one of K, Q, R, B, N, P (e.g. a white knight is {{wN}}, "
                "a black king is {{bK}}). Use the token in place of the piece word. "
                "Only tokenize actual chess pieces, nothing else."
            )
        return prompt

    def _build_position_prompt(self, analysis: PositionAnalysis) -> str:
        played_san, best_san = _readable_moves(
            analysis.fen, analysis.move_played, analysis.best_move
        )
        return (
            "Explain this single chess moment to the player.\n"
            f"Position (FEN): {analysis.fen}\n"
            f"Move played: {played_san}\n"
            f"Engine's best move: {best_san}\n"
            f"Evaluation before: {_pawns(analysis.eval_before)} (White's perspective)\n"
            f"Evaluation after: {_pawns(analysis.eval_after)} (White's perspective)\n"
            f"Centipawn loss: {analysis.centipawn_loss:.0f}\n"
            f"Classification: {analysis.classification.value}\n"
            "In 2-3 sentences, explain what was missed or what the better idea "
            "was, and the lesson to carry forward."
        )

    def _build_summary_prompt(
        self,
        summary: GameAnalysisSummary,
        game_context: Optional[dict],
    ) -> str:
        lines: List[str] = []
        if game_context:
            ctx_bits = []
            if game_context.get("color"):
                ctx_bits.append(f"played as {game_context['color']}")
            if game_context.get("result"):
                ctx_bits.append(f"result {game_context['result']}")
            if game_context.get("opponent_username"):
                ctx_bits.append(f"vs {game_context['opponent_username']}")
            if game_context.get("opening_name"):
                ctx_bits.append(f"opening: {game_context['opening_name']}")
            if ctx_bits:
                lines.append("Game: " + ", ".join(ctx_bits))

        lines.append(
            f"Move-quality breakdown over {summary.total_moves} moves — "
            f"best: {summary.best_moves}, good: {summary.good_moves}, "
            f"inaccuracies: {summary.inaccuracies}, mistakes: {summary.mistakes}, "
            f"blunders: {summary.blunders}. "
            f"Average centipawn loss: {summary.avg_centipawn_loss:.0f}."
        )
        lines.append(
            "Phase accuracy (avg centipawn loss, lower is better) — "
            f"opening: {summary.opening_accuracy:.0f}, "
            f"middlegame: {summary.middlegame_accuracy:.0f}, "
            f"endgame: {summary.endgame_accuracy:.0f}."
        )

        if summary.blunder_positions:
            lines.append("Worst moments:")
            for pos in summary.blunder_positions[:6]:
                played_san, best_san = _readable_moves(
                    pos.fen, pos.move_played, pos.best_move
                )
                lines.append(
                    f"- Move {pos.move_number}: played {played_san}, "
                    f"best was {best_san} "
                    f"(lost ~{pos.centipawn_loss:.0f} centipawns)."
                )
        else:
            lines.append("No outright blunders this game.")

        lines.append(
            "\nWrite a coaching writeup (about 150-200 words): summarize how the "
            "game went, describe the 1-3 most important mistakes and the better "
            "ideas, note any phase that needs work, and end with one concrete "
            "thing to practice."
        )
        return "\n".join(lines)

    # -- OpenAI call -------------------------------------------------------

    def _chat(self, system: str, user: str, max_tokens: int) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # Newer OpenAI models require `max_completion_tokens` (the old
                # `max_tokens` is rejected) and only accept the default
                # temperature, so we don't set one. `max_completion_tokens` also
                # works on older models like gpt-4o-mini, so this is portable.
                max_completion_tokens=max_tokens,
            )
        except openai.AuthenticationError as exc:
            raise LLMError(
                "OpenAI rejected the API key (authentication failed). Check "
                "OPENAI_API_KEY in your .env."
            ) from exc
        except openai.RateLimitError as exc:
            raise LLMError(
                "OpenAI rate limit or insufficient quota hit. Wait a moment and "
                "retry, or check your plan/billing."
            ) from exc
        except openai.APIConnectionError as exc:
            raise LLMError(
                f"Could not reach OpenAI (network error): {exc}"
            ) from exc
        except openai.APIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc

        content = response.choices[0].message.content
        return (content or "").strip()


# -- Module-level helpers --------------------------------------------------


def _pawns(centipawns: float) -> str:
    """Format a centipawn eval as a signed pawn value, e.g. '+1.3'."""
    return f"{centipawns / 100:+.1f}"


def _readable_moves(fen: str, played_uci: str, best_uci: str) -> tuple[str, str]:
    """Convert UCI moves to SAN using the pre-move position, best-effort."""
    try:
        board = chess.Board(fen)
        played = board.san(chess.Move.from_uci(played_uci)) if played_uci else played_uci
        best = board.san(chess.Move.from_uci(best_uci)) if best_uci else best_uci
        return played, best
    except Exception:
        return played_uci, best_uci
