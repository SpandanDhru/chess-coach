"""Stockfish engine wrapper for position analysis.

Engine process management: we keep a SINGLE long-lived Stockfish instance open
for the whole analyze invocation (one game or a --all batch), reused across every
position, rather than spawning a subprocess per position. The UCI handshake and
engine warmup are the expensive part, so amortizing one process over all
positions is the win; a pool buys nothing here because analysis is single-
threaded CLI work (Stockfish parallelizes internally via the `Threads` option).
Failure mode: if the engine dies mid-batch (chess.engine.EngineTerminatedError),
`_analyse` restarts it once transparently and retries the position; a second
consecutive failure propagates and `analyze_game` re-raises it naming the game
and move, so the batch fails loudly rather than silently corrupting analysis.
"""

import io
from typing import List, Optional

import chess
import chess.engine
import chess.pgn

from .models import PositionAnalysis, MoveClassification

# Mate scores are mapped to this many centipawns (minus distance) so evaluations
# stay numeric and comparable. Large enough to dominate material, bounded enough
# to keep centipawn-loss statistics from exploding.
_MATE_SCORE = 10000


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
        self.stockfish_path = str(stockfish_path)
        self.depth = depth
        self.threads = threads
        self.engine: Optional[chess.engine.SimpleEngine] = None

    def __enter__(self):
        """Context manager entry - start engine."""
        self._start_engine()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close engine."""
        if self.engine:
            try:
                self.engine.quit()
            except chess.engine.EngineError:
                pass
            self.engine = None

    # -- Engine lifecycle --------------------------------------------------

    def _start_engine(self) -> None:
        self.engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path)
        self.engine.configure({"Threads": self.threads})

    def _restart_engine(self) -> None:
        """Restart a dead engine process (used for transparent recovery)."""
        if self.engine:
            try:
                self.engine.quit()
            except chess.engine.EngineError:
                pass
        self._start_engine()

    def _analyse(self, board: chess.Board) -> dict:
        """Run a fixed-depth analysis, restarting the engine once on death."""
        limit = chess.engine.Limit(depth=self.depth)
        try:
            return self.engine.analyse(board, limit)
        except chess.engine.EngineTerminatedError:
            # Transparent restart-once, then retry. A second failure propagates.
            self._restart_engine()
            return self.engine.analyse(board, limit)

    # -- Analysis ----------------------------------------------------------

    def analyze_position(
        self,
        board: chess.Board,
        move_played: chess.Move,
        game_id: str = "",
    ) -> PositionAnalysis:
        """
        Analyze a single position and the move played.

        Args:
            board: Board state BEFORE the move
            move_played: The move that was played
            game_id: Owning game id (stamped onto the result)

        Returns:
            PositionAnalysis with Stockfish evaluation (evals in centipawns,
            positive = White advantage).
        """
        if not self.engine:
            raise RuntimeError("Engine not started. Use 'with' context manager.")

        mover = board.turn  # side to move = the side making move_played

        # Evaluate the position before the move (best play for the mover).
        info_before = self._analyse(board)
        score_before = info_before["score"]
        pv = info_before.get("pv") or []
        best_move = pv[0] if pv else move_played

        eval_before_white = score_before.white().score(mate_score=_MATE_SCORE)
        mate_before_mover = score_before.pov(mover).mate()

        # Evaluate the position AFTER the played move.
        board.push(move_played)
        info_after = self._analyse(board)
        score_after = info_after["score"]
        eval_after_white = score_after.white().score(mate_score=_MATE_SCORE)
        # After the push it's the opponent to move; mover POV is the flipped side.
        mate_after_mover = score_after.pov(mover).mate()
        board.pop()

        # Centipawn loss from the mover's perspective (>= 0).
        eval_before_mover = eval_before_white if mover == chess.WHITE else -eval_before_white
        eval_after_mover = eval_after_white if mover == chess.WHITE else -eval_after_white
        centipawn_loss = max(0.0, float(eval_before_mover - eval_after_mover))

        # Only treat a mate the MOVER could deliver as a "had mate" signal, so
        # escaping an opponent's mate is never misread as throwing one away.
        had_mate = mate_before_mover is not None and mate_before_mover > 0
        still_mate = mate_after_mover is not None and mate_after_mover > 0

        classification = self._classify_move(
            centipawn_loss,
            mate_before_mover if had_mate else None,
            mate_after_mover if still_mate else None,
        )

        return PositionAnalysis(
            game_id=game_id,
            move_number=board.fullmove_number,
            fen=board.fen(),
            move_played=move_played.uci(),
            eval_before=float(eval_before_white),
            eval_after=float(eval_after_white),
            centipawn_loss=centipawn_loss,
            best_move=best_move.uci(),
            best_move_eval=float(eval_before_white),
            # No multipv in v1: only the best line is available. Richer top-3
            # would require analyse(..., multipv=3) — deliberately out of scope.
            top_3_moves=[(best_move.uci(), float(eval_before_white))],
            classification=classification,
            depth=self.depth,
            is_missed_tactic=had_mate and not still_mate,
            mate_in=mate_before_mover if had_mate else None,
        )

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
            List of PositionAnalysis, one per move played.
        """
        game = chess.pgn.read_game(io.StringIO(pgn))
        if game is None:
            raise ValueError(f"Could not parse PGN for game {game_id}.")

        board = game.board()
        analyses: List[PositionAnalysis] = []
        for move in game.mainline_moves():
            try:
                analysis = self.analyze_position(board, move, game_id=game_id)
            except chess.engine.EngineTerminatedError as exc:
                raise RuntimeError(
                    f"Stockfish engine died while analyzing game {game_id} at "
                    f"move {board.fullmove_number} ({move.uci()}) and could not "
                    "be restarted. Check the Stockfish binary / system resources."
                ) from exc
            analyses.append(analysis)
            board.push(move)
        return analyses

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
