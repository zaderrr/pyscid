"""
PGN file parser.

Parses PGN (Portable Game Notation) files into Game objects.
This is a simple recursive descent parser that handles the standard PGN format.

Reference: http://www.saremba.de/chessgml/standards/pgn/pgn-complete.htm
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Iterator, Tuple

from .types import Color, Piece, Result, Square, RatingType
from .game import Game, Move
from .date import string_to_date, date_to_python
from .board import Board


# Regex patterns for PGN parsing
TAG_PATTERN = re.compile(r'\[(\w+)\s+"([^"]*)"\]')
MOVE_NUMBER_PATTERN = re.compile(r"(\d+)\s*\.+")
MOVE_PATTERN = re.compile(
    r"([KQRBN])?([a-h])?([1-8])?(x)?([a-h])([1-8])(=[QRBN])?(\+|#)?|O-O-O|O-O|0-0-0|0-0"
)
NAG_PATTERN = re.compile(r"\$(\d+)")
RESULT_PATTERN = re.compile(r"1-0|0-1|1/2-1/2|\*")
COMMENT_START = "{"
COMMENT_END = "}"
VARIATION_START = "("
VARIATION_END = ")"


class PgnParser:
    """Simple PGN parser"""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def skip_whitespace(self):
        """Skip whitespace and comments outside of moves"""
        while self.pos < self.length:
            ch = self.text[self.pos]
            if ch in " \t\n\r":
                self.pos += 1
            elif ch == ";":
                # Skip to end of line
                while self.pos < self.length and self.text[self.pos] != "\n":
                    self.pos += 1
            elif ch == "%":
                # Skip to end of line (escape)
                while self.pos < self.length and self.text[self.pos] != "\n":
                    self.pos += 1
            else:
                break

    def parse_tag(self) -> Optional[Tuple[str, str]]:
        """Parse a single tag pair like [Event "Name"]"""
        self.skip_whitespace()

        if self.pos >= self.length or self.text[self.pos] != "[":
            return None

        # Find the closing bracket
        end = self.text.find("]", self.pos)
        if end == -1:
            return None

        tag_text = self.text[self.pos : end + 1]
        match = TAG_PATTERN.match(tag_text)

        if match:
            self.pos = end + 1
            return match.group(1), match.group(2)

        return None

    def parse_tags(self) -> Dict[str, str]:
        """Parse all tag pairs at current position"""
        tags = {}

        while True:
            tag = self.parse_tag()
            if tag is None:
                break
            tags[tag[0]] = tag[1]

        return tags

    def parse_comment(self) -> Optional[str]:
        """Parse a { comment }"""
        if self.pos >= self.length or self.text[self.pos] != COMMENT_START:
            return None

        self.pos += 1
        start = self.pos
        depth = 1

        while self.pos < self.length and depth > 0:
            if self.text[self.pos] == COMMENT_START:
                depth += 1
            elif self.text[self.pos] == COMMENT_END:
                depth -= 1
            self.pos += 1

        return self.text[start : self.pos - 1].strip()

    def skip_variation(self):
        """Skip a ( variation )"""
        if self.pos >= self.length or self.text[self.pos] != VARIATION_START:
            return

        self.pos += 1
        depth = 1

        while self.pos < self.length and depth > 0:
            ch = self.text[self.pos]
            if ch == VARIATION_START:
                depth += 1
            elif ch == VARIATION_END:
                depth -= 1
            elif ch == COMMENT_START:
                self.parse_comment()
                continue
            self.pos += 1

    def parse_nag(self) -> Optional[int]:
        """Parse a $nn NAG"""
        self.skip_whitespace()

        if self.pos >= self.length or self.text[self.pos] != "$":
            return None

        match = NAG_PATTERN.match(self.text, self.pos)
        if match:
            self.pos = match.end()
            return int(match.group(1))

        return None

    def parse_move_san(self, board: Board) -> Optional[Move]:
        """Parse a single SAN move and return a Move object"""
        self.skip_whitespace()

        if self.pos >= self.length:
            return None

        # Skip move numbers
        match = MOVE_NUMBER_PATTERN.match(self.text, self.pos)
        if match:
            self.pos = match.end()
            self.skip_whitespace()

        if self.pos >= self.length:
            return None

        # Check for result
        result_match = RESULT_PATTERN.match(self.text, self.pos)
        if result_match:
            return None

        # Check for variation or comment
        if self.text[self.pos] in "({":
            return None

        # Parse the move
        match = MOVE_PATTERN.match(self.text, self.pos)
        if not match:
            return None

        self.pos = match.end()
        move_text = match.group(0)

        # Parse the SAN move
        return self._san_to_move(move_text, board)

    def _san_to_move(self, san: str, board: Board) -> Optional[Move]:
        """Convert SAN notation to Move object"""
        color = board.to_move

        # Handle castling
        if san in ("O-O", "0-0"):
            king = board.get_piece(color, 0)
            if king is None:
                return None
            from_sq = king.square
            to_sq = from_sq + 2
            return Move(from_sq, to_sq, is_castle_kingside=True)

        if san in ("O-O-O", "0-0-0"):
            king = board.get_piece(color, 0)
            if king is None:
                return None
            from_sq = king.square
            to_sq = from_sq - 2
            return Move(from_sq, to_sq, is_castle_queenside=True)

        # Parse regular move
        match = MOVE_PATTERN.match(san)
        if not match:
            return None

        piece_char = match.group(1)
        from_file = match.group(2)
        from_rank = match.group(3)
        # is_capture = match.group(4)
        to_file = match.group(5)
        to_rank = match.group(6)
        promotion = match.group(7)

        # Determine piece type
        if piece_char:
            piece_type = Piece.from_char(piece_char)
        else:
            piece_type = Piece.PAWN

        # Determine destination square
        to_sq = Square.from_name(to_file + to_rank)
        if to_sq is None:
            return None

        # Find the piece that can make this move
        from_sq = self._find_piece_for_move(
            board, color, piece_type, to_sq, from_file, from_rank
        )
        if from_sq is None:
            return None

        # Handle promotion
        promo_piece = None
        if promotion:
            promo_piece = Piece.from_char(promotion[1])

        return Move(from_sq, to_sq, promotion=promo_piece)

    def _find_piece_for_move(
        self,
        board: Board,
        color: Color,
        piece_type: Piece,
        to_sq: int,
        from_file: Optional[str],
        from_rank: Optional[str],
    ) -> Optional[int]:
        """Find which piece can make the given move"""
        candidates = []

        # Search all pieces of the given color and type
        for idx in range(16):
            piece = board.get_piece(color, idx)
            if piece is None or piece.captured:
                continue
            if piece.piece_type != piece_type:
                continue

            # Check disambiguation
            if from_file and Square.file_char(piece.square) != from_file:
                continue
            if from_rank and Square.rank_char(piece.square) != from_rank:
                continue

            # Check if this piece can reach the destination
            if self._can_reach(board, piece.square, to_sq, piece_type, color):
                candidates.append(piece.square)

        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) > 1:
            # Should not happen with proper disambiguation, return first
            return candidates[0]

        return None

    def _can_reach(
        self, board: Board, from_sq: int, to_sq: int, piece_type: Piece, color: Color
    ) -> bool:
        """Check if a piece can reach the destination (simplified check)"""
        diff = to_sq - from_sq
        from_file = Square.file(from_sq)
        from_rank = Square.rank(from_sq)
        to_file = Square.file(to_sq)
        to_rank = Square.rank(to_sq)
        file_diff = abs(to_file - from_file)
        rank_diff = abs(to_rank - from_rank)

        if piece_type == Piece.PAWN:
            direction = 1 if color == Color.WHITE else -1
            # Forward move
            if diff == 8 * direction and file_diff == 0:
                return board.get_piece_at(to_sq) is None
            # Double move from start
            if diff == 16 * direction and file_diff == 0:
                start_rank = 1 if color == Color.WHITE else 6
                if from_rank == start_rank:
                    middle = from_sq + 8 * direction
                    return (
                        board.get_piece_at(middle) is None
                        and board.get_piece_at(to_sq) is None
                    )
            # Capture
            if abs(diff) in (7, 9) and file_diff == 1:
                if diff * direction > 0:
                    target = board.get_piece_at(to_sq)
                    if target is not None:
                        return True
                    # En passant
                    if to_sq == board.ep_square:
                        return True
            return False

        elif piece_type == Piece.KNIGHT:
            return (file_diff, rank_diff) in [(1, 2), (2, 1)]

        elif piece_type == Piece.BISHOP:
            return file_diff == rank_diff and file_diff > 0

        elif piece_type == Piece.ROOK:
            return (file_diff == 0 or rank_diff == 0) and (
                file_diff > 0 or rank_diff > 0
            )

        elif piece_type == Piece.QUEEN:
            return (file_diff == rank_diff or file_diff == 0 or rank_diff == 0) and (
                file_diff > 0 or rank_diff > 0
            )

        elif piece_type == Piece.KING:
            return (
                file_diff <= 1 and rank_diff <= 1 and (file_diff > 0 or rank_diff > 0)
            )

        return False

    def parse_movetext(self, board: Board) -> List[Move]:
        """Parse the movetext section and return list of moves"""
        moves = []

        while self.pos < self.length:
            self.skip_whitespace()

            if self.pos >= self.length:
                break

            ch = self.text[self.pos]

            # Check for result
            result_match = RESULT_PATTERN.match(self.text, self.pos)
            if result_match:
                self.pos = result_match.end()
                break

            # Skip comments
            if ch == COMMENT_START:
                self.parse_comment()
                continue

            # Skip variations
            if ch == VARIATION_START:
                self.skip_variation()
                continue

            # Skip NAGs
            if ch == "$":
                self.parse_nag()
                continue

            # Skip annotation symbols (!!, !?, etc.)
            if ch in "!?":
                while self.pos < self.length and self.text[self.pos] in "!?":
                    self.pos += 1
                continue

            # Try to parse a move
            move = self.parse_move_san(board)
            if move:
                moves.append(move)
                board.make_move(move.from_square, move.to_square, move.promotion)
            else:
                # Skip unknown token
                while (
                    self.pos < self.length and self.text[self.pos] not in " \t\n\r[{("
                ):
                    self.pos += 1

        return moves

    def parse_result(self) -> Result:
        """Parse game result"""
        self.skip_whitespace()

        match = RESULT_PATTERN.match(self.text, self.pos)
        if match:
            self.pos = match.end()
            return Result.from_string(match.group(0))

        return Result.NONE

    def parse_game(self) -> Optional[Game]:
        """Parse a single game from the current position"""
        self.skip_whitespace()

        if self.pos >= self.length:
            return None

        # Parse tags
        tags = self.parse_tags()

        if not tags:
            return None

        # Create game from tags
        game = Game()

        # Standard seven tag roster
        game.white = tags.get("White", "?")
        game.black = tags.get("Black", "?")
        game.event = tags.get("Event", "?")
        game.site = tags.get("Site", "?")
        game.round = tags.get("Round", "?")

        # Parse date
        date_str = tags.get("Date", "")
        game.date_raw = string_to_date(date_str)
        game.date = date_to_python(game.date_raw)

        # Parse event date
        event_date_str = tags.get("EventDate", "")
        game.event_date_raw = string_to_date(event_date_str)
        game.event_date = date_to_python(game.event_date_raw)

        # Result
        result_str = tags.get("Result", "*")
        game.result = Result.from_string(result_str)

        # Ratings
        try:
            game.white_elo = int(tags.get("WhiteElo", "0"))
        except ValueError:
            game.white_elo = 0

        try:
            game.black_elo = int(tags.get("BlackElo", "0"))
        except ValueError:
            game.black_elo = 0

        # ECO
        game.eco = tags.get("ECO", "")

        # FEN for non-standard start position
        if tags.get("SetUp") == "1" or tags.get("Setup") == "1":
            game.fen = tags.get("FEN")

        # Extra tags
        standard_tags = {
            "Event",
            "Site",
            "Date",
            "Round",
            "White",
            "Black",
            "Result",
            "WhiteElo",
            "BlackElo",
            "ECO",
            "FEN",
            "SetUp",
            "Setup",
            "EventDate",
        }
        game.extra_tags = {k: v for k, v in tags.items() if k not in standard_tags}

        # Set up board and parse moves
        board = Board()
        if game.fen:
            board.setup_from_fen(game.fen)
        else:
            board.setup_standard()

        game.moves = self.parse_movetext(board)
        game.num_half_moves = len(game.moves)

        return game


class PgnDatabase:
    """
    PGN file database reader.

    Usage:
        db = PgnDatabase.open("games.pgn")
        for game in db:
            print(game.white, "vs", game.black)
    """

    def __init__(self):
        self._filepath: str = ""
        self._games: List[Game] = []
        self._loaded: bool = False

    @staticmethod
    def open(filepath: str) -> "PgnDatabase":
        """
        Open a PGN file.

        Note: The entire file is parsed on open. For large files,
        consider using an iterator approach.
        """
        db = PgnDatabase()
        db._filepath = filepath
        db._load()
        return db

    def _load(self):
        """Load and parse all games from the PGN file"""
        with open(self._filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        parser = PgnParser(content)

        while True:
            game = parser.parse_game()
            if game is None:
                break
            self._games.append(game)

        self._loaded = True

    def close(self):
        """No resources to close for PGN"""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __len__(self) -> int:
        return len(self._games)

    def __iter__(self) -> Iterator[Game]:
        return iter(self._games)

    def __getitem__(self, index: int) -> Game:
        return self._games[index]

    @property
    def description(self) -> str:
        """PGN files don't have a description"""
        return Path(self._filepath).stem
