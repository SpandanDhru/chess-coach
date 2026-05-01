"""Game ingestion from Chess.com and Lichess."""

from .base import GameIngester
from .chesscom import ChessComIngester
from .lichess import LichessIngester

__all__ = ["GameIngester", "ChessComIngester", "LichessIngester"]
