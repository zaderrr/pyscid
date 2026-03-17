"""
Core type definitions for SCID database format.

These types mirror the C++ definitions in scid/src/common.h and scid/src/board_def.h
"""

from enum import IntEnum
from typing import Optional


class Color(IntEnum):
    """Chess piece colors (matches scid WHITE=0, BLACK=1)"""

    WHITE = 0
    BLACK = 1

    def flip(self) -> "Color":
        return Color(1 - self.value)

    def __str__(self) -> str:
        return "w" if self == Color.WHITE else "b"


class Piece(IntEnum):
    """
    Chess piece types (matches scid piece_Type values).

    Note: In SCID, piece values include color in high bit:
    - White pieces: 1-6 (WK, WQ, WR, WB, WN, WP)
    - Black pieces: 9-14 (BK, BQ, BR, BB, BN, BP)
    - EMPTY = 7
    """

    KING = 1
    QUEEN = 2
    ROOK = 3
    BISHOP = 4
    KNIGHT = 5
    PAWN = 6
    EMPTY = 7

    def char(self) -> str:
        """Return the character representation (uppercase)"""
        chars = {
            Piece.KING: "K",
            Piece.QUEEN: "Q",
            Piece.ROOK: "R",
            Piece.BISHOP: "B",
            Piece.KNIGHT: "N",
            Piece.PAWN: "P",
            Piece.EMPTY: ".",
        }
        return chars.get(self, "?")

    @classmethod
    def from_char(cls, ch: str) -> "Piece":
        """Create piece from character (case insensitive)"""
        mapping = {
            "K": cls.KING,
            "Q": cls.QUEEN,
            "R": cls.ROOK,
            "B": cls.BISHOP,
            "N": cls.KNIGHT,
            "P": cls.PAWN,
        }
        return mapping.get(ch.upper(), cls.EMPTY)


class Result(IntEnum):
    """
    Game result (matches scid resultT values).

    From common.h:
    - RESULT_None = 0  -> "*"
    - RESULT_White = 1 -> "1-0"
    - RESULT_Black = 2 -> "0-1"
    - RESULT_Draw = 3  -> "1/2-1/2"
    """

    NONE = 0
    WHITE_WINS = 1
    BLACK_WINS = 2
    DRAW = 3

    def __str__(self) -> str:
        strings = {
            Result.NONE: "*",
            Result.WHITE_WINS: "1-0",
            Result.BLACK_WINS: "0-1",
            Result.DRAW: "1/2-1/2",
        }
        return strings[self]

    @classmethod
    def from_string(cls, s: str) -> "Result":
        mapping = {
            "*": cls.NONE,
            "1-0": cls.WHITE_WINS,
            "0-1": cls.BLACK_WINS,
            "1/2-1/2": cls.DRAW,
            "=-=": cls.DRAW,
        }
        return mapping.get(s, cls.NONE)


class RatingType(IntEnum):
    """
    Rating type (matches scid rating types from common.h).
    """

    ELO = 0
    RATING = 1
    RAPID = 2
    ICCF = 3
    USCF = 4
    DWZ = 5
    BCF = 6

    def __str__(self) -> str:
        names = ["Elo", "Rating", "Rapid", "ICCF", "USCF", "DWZ", "BCF"]
        return names[self.value] if self.value < len(names) else "Unknown"


class Square:
    """
    Chess square representation.

    SCID uses 0-63 where:
    - A1=0, B1=1, ..., H1=7
    - A2=8, B2=9, ..., H2=15
    - ...
    - A8=56, B8=57, ..., H8=63

    So: square = rank * 8 + file
    where file: a=0, b=1, ..., h=7
    and rank: 1=0, 2=1, ..., 8=7
    """

    # Special squares
    NULL_SQUARE = 65

    # Named squares for convenience
    A1, B1, C1, D1, E1, F1, G1, H1 = range(0, 8)
    A2, B2, C2, D2, E2, F2, G2, H2 = range(8, 16)
    A3, B3, C3, D3, E3, F3, G3, H3 = range(16, 24)
    A4, B4, C4, D4, E4, F4, G4, H4 = range(24, 32)
    A5, B5, C5, D5, E5, F5, G5, H5 = range(32, 40)
    A6, B6, C6, D6, E6, F6, G6, H6 = range(40, 48)
    A7, B7, C7, D7, E7, F7, G7, H7 = range(48, 56)
    A8, B8, C8, D8, E8, F8, G8, H8 = range(56, 64)

    @staticmethod
    def make(file: int, rank: int) -> int:
        """Create square from file (0-7) and rank (0-7)"""
        return (rank << 3) | file

    @staticmethod
    def file(sq: int) -> int:
        """Get file (0-7) from square"""
        return sq & 7

    @staticmethod
    def rank(sq: int) -> int:
        """Get rank (0-7) from square"""
        return (sq >> 3) & 7

    @staticmethod
    def file_char(sq: int) -> str:
        """Get file character ('a'-'h')"""
        return chr(ord("a") + Square.file(sq))

    @staticmethod
    def rank_char(sq: int) -> str:
        """Get rank character ('1'-'8')"""
        return chr(ord("1") + Square.rank(sq))

    @staticmethod
    def name(sq: int) -> str:
        """Get algebraic name of square (e.g., 'e4')"""
        if sq < 0 or sq > 63:
            return "??"
        return Square.file_char(sq) + Square.rank_char(sq)

    @staticmethod
    def from_name(name: str) -> Optional[int]:
        """Parse algebraic square name (e.g., 'e4' -> 28)"""
        if len(name) != 2:
            return None
        file = ord(name[0].lower()) - ord("a")
        rank = ord(name[1]) - ord("1")
        if not (0 <= file <= 7 and 0 <= rank <= 7):
            return None
        return Square.make(file, rank)

    @staticmethod
    def is_valid(sq: int) -> bool:
        """Check if square is valid (0-63)"""
        return 0 <= sq <= 63

    @staticmethod
    def flip_rank(sq: int) -> int:
        """Flip square vertically (a1 <-> a8)"""
        return Square.make(Square.file(sq), 7 - Square.rank(sq))

    @staticmethod
    def relative(sq: int, color: Color) -> int:
        """Get square relative to color (flips for black)"""
        return sq ^ (color.value * 56)


# Flag constants from IndexEntry (matches indexentry.h IDX_FLAG_* values)
class IndexFlag(IntEnum):
    """Game flags stored in IndexEntry"""

    START = 0  # Game has custom start position
    PROMO = 1  # Game contains promotion(s)
    UPROMO = 2  # Game contains underpromotion(s)
    DELETE = 3  # Game marked for deletion
    WHITE_OP = 4  # White openings flag
    BLACK_OP = 5  # Black openings flag
    MIDDLEGAME = 6  # Middlegames flag
    ENDGAME = 7  # Endgames flag
    NOVELTY = 8  # Novelty flag
    PAWN = 9  # Pawn structure flag
    TACTICS = 10  # Tactics flag
    KSIDE = 11  # Kingside play flag
    QSIDE = 12  # Queenside play flag
    BRILLIANCY = 13  # Brilliancy or good play
    BLUNDER = 14  # Blunder or bad play
    USER = 15  # User-defined flag
    CUSTOM1 = 16  # Custom flag 1
    CUSTOM2 = 17  # Custom flag 2
    CUSTOM3 = 18  # Custom flag 3
    CUSTOM4 = 19  # Custom flag 4
    CUSTOM5 = 20  # Custom flag 5
    CUSTOM6 = 21  # Custom flag 6


# Name types for NameBase (matches nameT in scid)
class NameType(IntEnum):
    """Types of names stored in NameBase"""

    PLAYER = 0
    EVENT = 1
    SITE = 2
    ROUND = 3
