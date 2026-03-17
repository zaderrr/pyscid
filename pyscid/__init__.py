"""
pyscid - A Python library for reading SCID chess database files

Supports:
- SI4 format (.si4, .sn4, .sg4)
- SI5 format (.si5, .sn5, .sg5)
- PGN format (.pgn)

Usage:
    from pyscid import Database

    db = Database.open("games.si4")
    for game in db:
        print(f"{game.white} vs {game.black}: {game.result}")
"""

from .types import Color, Piece, Result, Square, RatingType
from .date import decode_date, encode_date
from .game import Game, Move, IndexEntry
from .database import Database

__version__ = "0.1.0"
__all__ = [
    "Database",
    "Game",
    "Move",
    "IndexEntry",
    "Color",
    "Piece",
    "Result",
    "Square",
    "RatingType",
    "decode_date",
    "encode_date",
]
