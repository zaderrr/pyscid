"""
Game and Move data structures for SCID database.

These structures mirror the data stored in SCID's IndexEntry and Game classes.
Reference: scid/src/indexentry.h, scid/src/game.h
"""

from dataclasses import dataclass, field
from datetime import date as Date
from typing import Optional, List, Dict, Tuple

from .types import Color, Piece, Result, RatingType, Square, IndexFlag
from .date import decode_date, date_to_python, date_to_string


@dataclass
class Move:
    """
    Represents a single chess move.

    This is a simplified representation - SCID stores moves in a more compact
    binary format internally.
    """

    from_square: int
    to_square: int
    promotion: Optional[Piece] = None

    # Special move flags
    is_castle_kingside: bool = False
    is_castle_queenside: bool = False
    is_null_move: bool = False

    def uci(self) -> str:
        """
        Return move in UCI format (e.g., 'e2e4', 'e7e8q').
        """
        if self.is_null_move:
            return "0000"

        from_name = Square.name(self.from_square)
        to_name = Square.name(self.to_square)

        promo = ""
        if self.promotion is not None and self.promotion != Piece.EMPTY:
            promo = self.promotion.char().lower()

        return f"{from_name}{to_name}{promo}"

    def __str__(self) -> str:
        if self.is_null_move:
            return "--"
        if self.is_castle_kingside:
            return "O-O"
        if self.is_castle_queenside:
            return "O-O-O"
        return self.uci()


@dataclass
class IndexEntry:
    """
    Index entry containing game metadata.

    This directly mirrors SCID's IndexEntry class (scid/src/indexentry.h).
    The IndexEntry is a 47-byte (SCID4) or 56-byte (SCID5) fixed-size record
    stored in the index file (.si4/.si5).

    All IDs (white_id, black_id, etc.) reference entries in the NameBase.
    """

    # Game data location in .sg4/.sg5 file
    offset: int = 0
    length: int = 0

    # Name IDs (references to NameBase)
    white_id: int = 0
    black_id: int = 0
    event_id: int = 0
    site_id: int = 0
    round_id: int = 0

    # Dates (packed 20-bit format)
    date: int = 0
    event_date: int = 0

    # Ratings
    white_elo: int = 0
    black_elo: int = 0
    white_rating_type: RatingType = RatingType.ELO
    black_rating_type: RatingType = RatingType.ELO

    # Game result
    result: Result = Result.NONE

    # ECO code (16-bit encoded)
    eco_code: int = 0

    # Game statistics
    num_half_moves: int = 0

    # Annotation counts (4-bit each, 0-15 representing approximate counts)
    # Raw values: 0-10 = exact, 11=15, 12=20, 13=30, 14=40, 15=50+
    variation_count: int = 0
    comment_count: int = 0
    nag_count: int = 0

    # Flags (22 bits)
    flags: int = 0

    # Material signature of final position (24-bit)
    final_mat_sig: int = 0

    # Stored line code for opening classification
    stored_line_code: int = 0

    # Home pawn data for position search (9 bytes)
    home_pawn_data: bytes = field(default_factory=lambda: bytes(9))

    # Chess variant (0 = standard, 1 = Chess960)
    is_chess960: bool = False

    def get_flag(self, flag: IndexFlag) -> bool:
        """Check if a specific flag is set"""
        return bool(self.flags & (1 << flag.value))

    def has_custom_start(self) -> bool:
        """Check if game has non-standard starting position"""
        return self.get_flag(IndexFlag.START)

    def has_promotions(self) -> bool:
        """Check if game contains promotions"""
        return self.get_flag(IndexFlag.PROMO)

    def has_underpromotions(self) -> bool:
        """Check if game contains underpromotions"""
        return self.get_flag(IndexFlag.UPROMO)

    def is_deleted(self) -> bool:
        """Check if game is marked for deletion"""
        return self.get_flag(IndexFlag.DELETE)

    def has_variations(self) -> bool:
        """Check if game has variations"""
        return self.variation_count > 0

    def has_comments(self) -> bool:
        """Check if game has comments"""
        return self.comment_count > 0

    def has_nags(self) -> bool:
        """Check if game has NAGs"""
        return self.nag_count > 0

    @property
    def year(self) -> Optional[int]:
        """Get year from date"""
        y, _, _ = decode_date(self.date)
        return y

    @property
    def month(self) -> Optional[int]:
        """Get month from date"""
        _, m, _ = decode_date(self.date)
        return m

    @property
    def day(self) -> Optional[int]:
        """Get day from date"""
        _, _, d = decode_date(self.date)
        return d

    def get_eco_string(self) -> str:
        """
        Decode ECO code to string (e.g., 'A00', 'B99').

        SCID ECO encoding:
        - 0 = no ECO
        - Otherwise: ((letter - 'A') * 100 + number) * 4 + subcode
        """
        if self.eco_code == 0:
            return ""

        # Decode: letter is in high bits, number and subcode in low
        val = self.eco_code
        subcode = val & 0x03
        val >>= 2
        number = val % 100
        letter_idx = val // 100

        if letter_idx > 4:  # A-E only
            return ""

        letter = chr(ord("A") + letter_idx)

        # Subcode is optional suffix (a-d)
        suffix = ""
        if subcode > 0:
            suffix = chr(ord("a") + subcode - 1)

        return f"{letter}{number:02d}{suffix}"


@dataclass
class Game:
    """
    Full game data including moves and metadata.

    This combines data from IndexEntry (metadata) with decoded game data
    from the .sg4/.sg5 file (moves, comments, variations).
    """

    # Player names (resolved from NameBase)
    white: str = ""
    black: str = ""

    # Event info (resolved from NameBase)
    event: str = ""
    site: str = ""
    round: str = ""

    # Dates
    date: Optional[Date] = None
    event_date: Optional[Date] = None

    # For partial dates, keep the raw packed values
    date_raw: int = 0
    event_date_raw: int = 0

    # Result
    result: Result = Result.NONE

    # Ratings
    white_elo: int = 0
    black_elo: int = 0
    white_rating_type: RatingType = RatingType.ELO
    black_rating_type: RatingType = RatingType.ELO

    # ECO
    eco: str = ""

    # Game length
    num_half_moves: int = 0

    # Extra PGN tags not in standard set
    extra_tags: Dict[str, str] = field(default_factory=dict)

    # Starting position (None = standard, otherwise FEN string)
    fen: Optional[str] = None

    # Is this Chess960?
    is_chess960: bool = False

    # Main line moves
    moves: List[Move] = field(default_factory=list)

    # Index entry reference (for raw access)
    _index_entry: Optional[IndexEntry] = None

    @property
    def date_string(self) -> str:
        """Get date in PGN format (YYYY.MM.DD)"""
        return date_to_string(self.date_raw)

    @property
    def event_date_string(self) -> str:
        """Get event date in PGN format (YYYY.MM.DD)"""
        return date_to_string(self.event_date_raw)

    def __str__(self) -> str:
        return f"{self.white} vs {self.black} ({self.result}) - {self.event}, {self.date_string}"

    def to_pgn(self) -> str:
        """
        Export game to PGN format string.
        """
        lines = []

        # Standard seven tag roster
        lines.append(f'[Event "{self.event}"]')
        lines.append(f'[Site "{self.site}"]')
        lines.append(f'[Date "{self.date_string}"]')
        lines.append(f'[Round "{self.round}"]')
        lines.append(f'[White "{self.white}"]')
        lines.append(f'[Black "{self.black}"]')
        lines.append(f'[Result "{self.result}"]')

        # Optional tags
        if self.white_elo > 0:
            lines.append(f'[WhiteElo "{self.white_elo}"]')
        if self.black_elo > 0:
            lines.append(f'[BlackElo "{self.black_elo}"]')
        if self.eco:
            lines.append(f'[ECO "{self.eco}"]')
        if self.fen:
            lines.append(f'[FEN "{self.fen}"]')
            lines.append('[SetUp "1"]')

        # Extra tags
        for tag, value in self.extra_tags.items():
            lines.append(f'[{tag} "{value}"]')

        lines.append("")  # Empty line before moves

        # Moves
        move_text = []
        for i, move in enumerate(self.moves):
            move_num = i // 2 + 1
            if i % 2 == 0:
                move_text.append(f"{move_num}.")
            move_text.append(move.uci())

        move_text.append(str(self.result))

        # Wrap lines at ~80 chars
        current_line = []
        current_len = 0
        for token in move_text:
            if current_len + len(token) + 1 > 80 and current_line:
                lines.append(" ".join(current_line))
                current_line = []
                current_len = 0
            current_line.append(token)
            current_len += len(token) + 1

        if current_line:
            lines.append(" ".join(current_line))

        return "\n".join(lines)
