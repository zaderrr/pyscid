"""
Simple board state for move decoding.

SCID encodes moves using piece indices (0-15) rather than squares. To decode
moves, we need to track which piece is at which index and where it currently is.

The piece index assignment:
- Index 0 is always the King
- Other pieces are assigned indices 1-15 from left to right on the starting position
- For non-standard positions, pieces are assigned left-to-right, but King swaps with
  whoever had index 0.

Reference: scid/src/bytebuf.h, scid/src/position.cpp
"""

from typing import List, Optional, Tuple
from .types import Color, Piece, Square


# Starting position piece layout
# Index: square (0-63), Value: (color, piece_type) or None for empty
STANDARD_BOARD = [
    # Rank 1 (White)
    (Color.WHITE, Piece.ROOK),
    (Color.WHITE, Piece.KNIGHT),
    (Color.WHITE, Piece.BISHOP),
    (Color.WHITE, Piece.QUEEN),
    (Color.WHITE, Piece.KING),
    (Color.WHITE, Piece.BISHOP),
    (Color.WHITE, Piece.KNIGHT),
    (Color.WHITE, Piece.ROOK),
    # Rank 2 (White pawns)
    (Color.WHITE, Piece.PAWN),
    (Color.WHITE, Piece.PAWN),
    (Color.WHITE, Piece.PAWN),
    (Color.WHITE, Piece.PAWN),
    (Color.WHITE, Piece.PAWN),
    (Color.WHITE, Piece.PAWN),
    (Color.WHITE, Piece.PAWN),
    (Color.WHITE, Piece.PAWN),
    # Ranks 3-6 (empty)
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    # Rank 7 (Black pawns)
    (Color.BLACK, Piece.PAWN),
    (Color.BLACK, Piece.PAWN),
    (Color.BLACK, Piece.PAWN),
    (Color.BLACK, Piece.PAWN),
    (Color.BLACK, Piece.PAWN),
    (Color.BLACK, Piece.PAWN),
    (Color.BLACK, Piece.PAWN),
    (Color.BLACK, Piece.PAWN),
    # Rank 8 (Black)
    (Color.BLACK, Piece.ROOK),
    (Color.BLACK, Piece.KNIGHT),
    (Color.BLACK, Piece.BISHOP),
    (Color.BLACK, Piece.QUEEN),
    (Color.BLACK, Piece.KING),
    (Color.BLACK, Piece.BISHOP),
    (Color.BLACK, Piece.KNIGHT),
    (Color.BLACK, Piece.ROOK),
]


class PieceInfo:
    """Track a piece's current position and type"""

    __slots__ = ["square", "piece_type", "color", "captured"]

    def __init__(self, square: int, piece_type: Piece, color: Color):
        self.square = square
        self.piece_type = piece_type
        self.color = color
        self.captured = False


class Board:
    """
    Board state for decoding SCID moves.

    SCID assigns each piece an index (0-15) per color. The King always has index 0.
    Moves are encoded as (piece_index, move_code) pairs.

    IMPORTANT: When a piece is captured, the LAST active piece in the list
    is swapped into the captured piece's index slot. This means piece indices
    can change during the game!
    """

    def __init__(self):
        # pieces[color][index] = PieceInfo
        self.pieces: List[List[Optional[PieceInfo]]] = [
            [None] * 16,  # White pieces
            [None] * 16,  # Black pieces
        ]

        # board[square] = (color, piece_index) or None
        self.board: List[Optional[Tuple[Color, int]]] = [None] * 64

        # Side to move
        self.to_move: Color = Color.WHITE

        # Castling rights
        self.can_castle_kingside: List[bool] = [True, True]
        self.can_castle_queenside: List[bool] = [True, True]

        # En passant square (or None)
        self.ep_square: Optional[int] = None

        # Number of active pieces per color (for SCID index swapping on capture)
        self.piece_count: List[int] = [16, 16]

    @staticmethod
    def standard() -> "Board":
        """Create board with standard starting position"""
        board = Board()
        board.setup_standard()
        return board

    def setup_standard(self):
        """Set up standard starting position with correct piece indices"""
        # Clear board
        self.pieces = [[None] * 16, [None] * 16]
        self.board = [None] * 64
        self.to_move = Color.WHITE
        self.can_castle_kingside = [True, True]
        self.can_castle_queenside = [True, True]
        self.ep_square = None
        self.piece_count = [16, 16]

        # White pieces (index 0 = King, then left-to-right excluding king)
        # Standard order: Ra1=1, Nb1=2, Bc1=3, Qd1=4, Ke1=0, Bf1=5, Ng1=6, Rh1=7
        # Pawns: a2=8, b2=9, c2=10, d2=11, e2=12, f2=13, g2=14, h2=15
        white_assignments = [
            (Square.E1, Piece.KING, 0),
            (Square.A1, Piece.ROOK, 1),
            (Square.B1, Piece.KNIGHT, 2),
            (Square.C1, Piece.BISHOP, 3),
            (Square.D1, Piece.QUEEN, 4),
            (Square.F1, Piece.BISHOP, 5),
            (Square.G1, Piece.KNIGHT, 6),
            (Square.H1, Piece.ROOK, 7),
            (Square.A2, Piece.PAWN, 8),
            (Square.B2, Piece.PAWN, 9),
            (Square.C2, Piece.PAWN, 10),
            (Square.D2, Piece.PAWN, 11),
            (Square.E2, Piece.PAWN, 12),
            (Square.F2, Piece.PAWN, 13),
            (Square.G2, Piece.PAWN, 14),
            (Square.H2, Piece.PAWN, 15),
        ]

        for sq, piece_type, idx in white_assignments:
            self._place_piece(Color.WHITE, idx, sq, piece_type)

        # Black pieces (same indices, mirrored)
        black_assignments = [
            (Square.E8, Piece.KING, 0),
            (Square.A8, Piece.ROOK, 1),
            (Square.B8, Piece.KNIGHT, 2),
            (Square.C8, Piece.BISHOP, 3),
            (Square.D8, Piece.QUEEN, 4),
            (Square.F8, Piece.BISHOP, 5),
            (Square.G8, Piece.KNIGHT, 6),
            (Square.H8, Piece.ROOK, 7),
            (Square.A7, Piece.PAWN, 8),
            (Square.B7, Piece.PAWN, 9),
            (Square.C7, Piece.PAWN, 10),
            (Square.D7, Piece.PAWN, 11),
            (Square.E7, Piece.PAWN, 12),
            (Square.F7, Piece.PAWN, 13),
            (Square.G7, Piece.PAWN, 14),
            (Square.H7, Piece.PAWN, 15),
        ]

        for sq, piece_type, idx in black_assignments:
            self._place_piece(Color.BLACK, idx, sq, piece_type)

    def _place_piece(self, color: Color, index: int, square: int, piece_type: Piece):
        """Place a piece on the board"""
        self.pieces[color][index] = PieceInfo(square, piece_type, color)
        self.board[square] = (color, index)

    def setup_from_fen(self, fen: str):
        """
        Set up position from FEN string.

        Pieces are assigned indices left-to-right per rank, top-to-bottom.
        The King is swapped to index 0.
        """
        # Clear board
        self.pieces = [[None] * 16, [None] * 16]
        self.board = [None] * 64
        self.can_castle_kingside = [False, False]
        self.can_castle_queenside = [False, False]
        self.ep_square = None
        self.piece_count = [0, 0]

        parts = fen.split()
        if len(parts) < 1:
            return

        board_part = parts[0]

        # Parse board position
        piece_indices: List[int] = [0, 0]  # Next index to assign for [WHITE, BLACK]
        king_at_index: List[Optional[int]] = [
            None,
            None,
        ]  # Where did we put the king initially?

        ranks = board_part.split("/")
        for rank_idx, rank_str in enumerate(reversed(ranks)):
            file_idx = 0
            for ch in rank_str:
                if ch.isdigit():
                    file_idx += int(ch)
                elif ch.isalpha():
                    color = Color.WHITE if ch.isupper() else Color.BLACK
                    piece_type = Piece.from_char(ch)
                    square = Square.make(file_idx, rank_idx)

                    idx = piece_indices[color]
                    piece_indices[color] += 1

                    self._place_piece(color, idx, square, piece_type)

                    if piece_type == Piece.KING:
                        king_at_index[color] = idx

                    file_idx += 1

        # Set piece counts
        self.piece_count = [piece_indices[Color.WHITE], piece_indices[Color.BLACK]]

        # Swap king to index 0 if not already there
        for color in [Color.WHITE, Color.BLACK]:
            king_idx = king_at_index[color]
            if king_idx is not None and king_idx != 0:
                # Swap pieces at index 0 and king_idx
                p0 = self.pieces[color][0]
                pk = self.pieces[color][king_idx]

                self.pieces[color][0] = pk
                self.pieces[color][king_idx] = p0

                # Update board references
                if pk:
                    self.board[pk.square] = (color, 0)
                if p0:
                    self.board[p0.square] = (color, king_idx)

        # Parse side to move
        if len(parts) >= 2:
            self.to_move = Color.WHITE if parts[1] == "w" else Color.BLACK
        else:
            self.to_move = Color.WHITE

        # Parse castling rights
        if len(parts) >= 3:
            castling = parts[2]
            self.can_castle_kingside[Color.WHITE] = "K" in castling
            self.can_castle_queenside[Color.WHITE] = "Q" in castling
            self.can_castle_kingside[Color.BLACK] = "k" in castling
            self.can_castle_queenside[Color.BLACK] = "q" in castling

        # Parse en passant square
        if len(parts) >= 4 and parts[3] != "-":
            self.ep_square = Square.from_name(parts[3])

    def get_piece(self, color: Color, index: int) -> Optional[PieceInfo]:
        """Get piece by color and index"""
        return self.pieces[color][index]

    def get_piece_at(self, square: int) -> Optional[Tuple[Color, int, Piece]]:
        """Get piece at a square: (color, index, piece_type) or None"""
        occupant = self.board[square]
        if occupant is None:
            return None
        color, index = occupant
        piece = self.pieces[color][index]
        if piece is None or piece.captured:
            return None
        return (color, index, piece.piece_type)

    def _handle_capture(self, cap_color: Color, cap_index: int):
        """
        Handle a piece capture by swapping indices.

        SCID maintains a compact list of active pieces. When a piece is captured,
        the LAST active piece is moved into the captured piece's index slot.
        This keeps indices 0..count-1 always valid.
        """
        cap_piece = self.pieces[cap_color][cap_index]
        if cap_piece is None:
            return

        cap_piece.captured = True

        # Decrease the piece count
        self.piece_count[cap_color] -= 1
        last_index = self.piece_count[cap_color]

        # If the captured piece wasn't the last one, swap
        if cap_index != last_index:
            last_piece = self.pieces[cap_color][last_index]
            if last_piece and not last_piece.captured:
                # Move last piece to captured index
                self.pieces[cap_color][cap_index] = last_piece
                self.pieces[cap_color][last_index] = cap_piece  # Move captured to end

                # Update board reference for the swapped piece
                self.board[last_piece.square] = (cap_color, cap_index)

    def make_move(self, from_sq: int, to_sq: int, promotion: Optional[Piece] = None):
        """
        Make a move on the board, updating piece positions.
        """
        occupant = self.board[from_sq]
        if occupant is None:
            return

        color, index = occupant
        piece = self.pieces[color][index]
        if piece is None:
            return

        # Handle capture - SCID swaps the last active piece into the captured index
        target = self.board[to_sq]
        if target is not None:
            cap_color, cap_index = target
            self._handle_capture(cap_color, cap_index)
            self.board[to_sq] = None

        # Handle en passant capture
        if piece.piece_type == Piece.PAWN and to_sq == self.ep_square:
            # Capture the pawn that moved two squares
            ep_capture_sq = to_sq + (-8 if color == Color.WHITE else 8)
            ep_target = self.board[ep_capture_sq]
            if ep_target is not None:
                ep_color, ep_index = ep_target
                self._handle_capture(ep_color, ep_index)
                self.board[ep_capture_sq] = None

        # Clear en passant
        self.ep_square = None

        # Set en passant square if pawn moved two squares
        if piece.piece_type == Piece.PAWN:
            if abs(to_sq - from_sq) == 16:
                self.ep_square = (from_sq + to_sq) // 2

        # Move the piece
        self.board[from_sq] = None
        self.board[to_sq] = (color, index)
        piece.square = to_sq

        # Handle promotion
        if promotion is not None and promotion != Piece.EMPTY:
            piece.piece_type = promotion

        # Handle castling - move the rook
        if piece.piece_type == Piece.KING:
            if to_sq - from_sq == 2:  # Kingside castle
                rook_from = from_sq + 3
                rook_to = from_sq + 1
                # Only move rook if squares are valid
                if Square.is_valid(rook_from) and Square.is_valid(rook_to):
                    self._move_rook_for_castle(color, rook_from, rook_to)
            elif from_sq - to_sq == 2:  # Queenside castle
                rook_from = from_sq - 4
                rook_to = from_sq - 1
                # Only move rook if squares are valid
                if Square.is_valid(rook_from) and Square.is_valid(rook_to):
                    self._move_rook_for_castle(color, rook_from, rook_to)

            # King moved, lose castling rights
            self.can_castle_kingside[color] = False
            self.can_castle_queenside[color] = False

        # Rook moved, lose that side's castling rights
        if piece.piece_type == Piece.ROOK:
            if from_sq == Square.A1 or from_sq == Square.A8:
                self.can_castle_queenside[color] = False
            elif from_sq == Square.H1 or from_sq == Square.H8:
                self.can_castle_kingside[color] = False

        # Switch side to move
        self.to_move = self.to_move.flip()

    def _move_rook_for_castle(self, color: Color, from_sq: int, to_sq: int):
        """Move a rook during castling"""
        # Safety check for invalid squares
        if not Square.is_valid(from_sq) or not Square.is_valid(to_sq):
            return

        occupant = self.board[from_sq]
        if occupant is None:
            return

        rook_color, rook_index = occupant
        rook = self.pieces[rook_color][rook_index]
        if rook is None:
            return

        self.board[from_sq] = None
        self.board[to_sq] = (rook_color, rook_index)
        rook.square = to_sq
