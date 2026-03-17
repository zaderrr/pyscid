"""
Game data decoding for SCID format.

The .sg4/.sg5 file contains encoded game data consisting of:
1. Extra tags section (non-standard PGN tags)
2. Start position flags + optional FEN
3. Encoded moves

Reference: scid/src/bytebuf.h, scid/src/game.cpp
"""

from typing import List, Dict, Optional, Tuple
from .types import Color, Piece, Square
from .game import Game, Move, IndexEntry
from .board import Board


# Common tag names encoded as single bytes (241-250)
# From bytebuf.h
COMMON_TAGS = [
    "WhiteCountry",  # 241
    "BlackCountry",  # 242
    "Annotator",  # 243
    "PlyCount",  # 244
    "EventDate",  # 245 (plain text encoding)
    "Opening",  # 246
    "Variation",  # 247
    "Setup",  # 248
    "Source",  # 249
    "SetUp",  # 250
]

MAX_TAG_LEN = 240


# Move encoding constants (from bytebuf.h)
class MoveMarker:
    """Special move byte markers when piece index is 0 (King)"""

    NULL_MOVE = 0
    # 1-8: King moves (SW, S, SE, W, E, NW, N, NE)
    CASTLE_QUEENSIDE = 9
    CASTLE_KINGSIDE = 10
    NAG = 11
    COMMENT = 12
    START_VARIATION = 13
    END_VARIATION = 14
    END_GAME = 15


# King move direction offsets (for move codes 1-8)
KING_MOVE_OFFSETS = [0, -9, -8, -7, -1, 1, 7, 8, 9]


def decode_game_data(game: Game, data: bytes, ie: IndexEntry):
    """
    Decode game data from .sg4/.sg5 file into a Game object.

    Args:
        game: Game object to populate
        data: Raw game data bytes
        ie: IndexEntry with metadata
    """
    if len(data) == 0:
        return

    pos = 0

    # 1. Decode extra tags
    pos, extra_tags = _decode_tags(data, pos)
    game.extra_tags = extra_tags

    # 2. Decode start position
    if pos < len(data):
        pos, fen = _decode_start_position(data, pos)
        game.fen = fen

    # 3. Set up board and decode moves
    board = Board()
    if game.fen:
        board.setup_from_fen(game.fen)
    else:
        board.setup_standard()

    # 4. Decode moves
    game.moves = _decode_moves(data, pos, board)


def _decode_tags(data: bytes, pos: int) -> Tuple[int, Dict[str, str]]:
    """
    Decode extra tags section.

    Format:
    - tag_length: 1 byte (0 = end of tags)
    - if length > 240: common tag code, no name follows
    - if length <= 240: tag name follows (length bytes)
    - value_length: 1 byte
    - value: value_length bytes

    Returns:
        (new_position, dict of tag_name -> tag_value)
    """
    tags = {}

    while pos < len(data):
        tag_len = data[pos]
        pos += 1

        if tag_len == 0:
            # End of tags section
            break

        # Get tag name
        if tag_len > MAX_TAG_LEN:
            # Common tag encoded as single byte
            tag_idx = tag_len - MAX_TAG_LEN - 1
            if tag_idx < len(COMMON_TAGS):
                tag_name = COMMON_TAGS[tag_idx]
            else:
                tag_name = f"Unknown_{tag_len}"
        else:
            # Tag name is explicit
            if pos + tag_len > len(data):
                break
            tag_name = data[pos : pos + tag_len].decode("latin-1", errors="replace")
            pos += tag_len

        # Special case: 255 was a 3-byte EventDate encoding in SCID2
        if tag_len == 255:
            value_len = 3
        else:
            if pos >= len(data):
                break
            value_len = data[pos]
            pos += 1

        # Get tag value
        if pos + value_len > len(data):
            break
        tag_value = data[pos : pos + value_len].decode("latin-1", errors="replace")
        pos += value_len

        tags[tag_name] = tag_value

    return pos, tags


def _decode_start_position(data: bytes, pos: int) -> Tuple[int, Optional[str]]:
    """
    Decode start position section.

    Format:
    - flags: 1 byte
      - bit 0: has custom start position
      - bit 1: has pawn promotions
      - bit 2: has underpromotions
    - if bit 0 set: FEN string (null-terminated)

    Returns:
        (new_position, FEN string or None for standard position)
    """
    if pos >= len(data):
        return pos, None

    flags = data[pos]
    pos += 1

    has_custom_start = bool(flags & 1)
    # has_promotions = bool(flags & 2)
    # has_underpromotions = bool(flags & 4)

    fen = None
    if has_custom_start:
        # Read null-terminated FEN string
        fen_end = data.find(b"\x00", pos)
        if fen_end == -1:
            fen_end = len(data)
        fen = data[pos:fen_end].decode("latin-1", errors="replace")
        pos = fen_end + 1

    return pos, fen


def _decode_moves(data: bytes, pos: int, board: Board) -> List[Move]:
    """
    Decode the moves section.

    Each move is encoded as 1-2 bytes:
    - High nibble (bits 4-7): piece index (0-15)
    - Low nibble (bits 0-3): move code

    Piece index 0 is always the King, and move codes 11-15 are special markers.

    Returns:
        List of Move objects for the main line
    """
    moves = []
    var_depth = 0

    while pos < len(data):
        move_byte = data[pos]
        pos += 1

        piece_index = (move_byte >> 4) & 0x0F
        move_code = move_byte & 0x0F

        # Check for special markers (only when piece_index is 0 = King)
        if piece_index == 0:
            if move_code == MoveMarker.END_GAME:
                break
            elif move_code == MoveMarker.NAG:
                # Skip NAG byte
                if pos < len(data):
                    pos += 1
                continue
            elif move_code == MoveMarker.COMMENT:
                # Comment placeholder (actual comments stored elsewhere)
                continue
            elif move_code == MoveMarker.START_VARIATION:
                var_depth += 1
                continue
            elif move_code == MoveMarker.END_VARIATION:
                var_depth -= 1
                continue
            elif move_code == MoveMarker.NULL_MOVE:
                if var_depth == 0:
                    moves.append(Move(from_square=0, to_square=0, is_null_move=True))
                    board.to_move = board.to_move.flip()
                continue

        # Skip moves in variations (we only decode main line)
        if var_depth > 0:
            # Still need to handle 2-byte queen moves
            if piece_index > 0:
                piece = board.get_piece(board.to_move, piece_index)
                if piece and piece.piece_type == Piece.QUEEN:
                    if move_code == Square.file(piece.square):
                        # 2-byte queen move
                        if pos < len(data):
                            pos += 1
            continue

        # Decode the move
        move, pos = _decode_single_move(data, pos, board, piece_index, move_code)

        if move:
            moves.append(move)
            # Update board state
            board.make_move(move.from_square, move.to_square, move.promotion)

    return moves


def _decode_single_move(
    data: bytes, pos: int, board: Board, piece_index: int, move_code: int
) -> Tuple[Optional[Move], int]:
    """
    Decode a single move from piece index and move code.

    Returns:
        (Move object or None, updated position)
    """
    color = board.to_move
    piece = board.get_piece(color, piece_index)

    if piece is None or piece.captured:
        return None, pos

    from_sq = piece.square
    piece_type = piece.piece_type

    to_sq = -1
    promotion = None
    is_castle_kingside = False
    is_castle_queenside = False

    if piece_type == Piece.KING:
        # King moves use move_code 1-8 for directions, 9-10 for castling
        if move_code == MoveMarker.CASTLE_QUEENSIDE:
            # Queenside castle
            to_sq = from_sq - 2
            is_castle_queenside = True
        elif move_code == MoveMarker.CASTLE_KINGSIDE:
            # Kingside castle
            to_sq = from_sq + 2
            is_castle_kingside = True
        elif 1 <= move_code <= 8:
            to_sq = from_sq + KING_MOVE_OFFSETS[move_code]
        else:
            return None, pos

    elif piece_type == Piece.QUEEN:
        # Queens can need 2 bytes when destination is ambiguous
        # If move_code equals the queen's current file, it's a 2-byte move
        if move_code == Square.file(from_sq):
            # 2-byte move: second byte is (64 + destination square)
            if pos < len(data):
                second_byte = data[pos]
                pos += 1
                to_sq = second_byte - 64
            else:
                return None, pos
        else:
            # 1-byte move: same encoding as rook
            to_sq = _decode_rook_move(from_sq, move_code)

    elif piece_type == Piece.ROOK:
        to_sq = _decode_rook_move(from_sq, move_code)

    elif piece_type == Piece.BISHOP:
        to_sq = _decode_bishop_move(from_sq, move_code, color)

    elif piece_type == Piece.KNIGHT:
        to_sq = _decode_knight_move(from_sq, move_code)

    elif piece_type == Piece.PAWN:
        to_sq, promotion = _decode_pawn_move(from_sq, move_code, color)

    if not Square.is_valid(to_sq):
        return None, pos

    move = Move(
        from_square=from_sq,
        to_square=to_sq,
        promotion=promotion,
        is_castle_kingside=is_castle_kingside,
        is_castle_queenside=is_castle_queenside,
    )

    return move, pos


def _decode_rook_move(from_sq: int, move_code: int) -> int:
    """
    Decode rook/queen 1-byte move.

    move_code 0-7: horizontal move to file move_code
    move_code 8-15: vertical move to rank (move_code - 8)
    """
    if move_code >= 8:
        # Vertical move: same file, different rank
        return Square.make(Square.file(from_sq), move_code - 8)
    else:
        # Horizontal move: same rank, different file
        return Square.make(move_code, Square.rank(from_sq))


def _decode_bishop_move(from_sq: int, move_code: int, color: Color) -> int:
    """
    Decode bishop move.

    The move_code encodes the destination file.
    move_code 0-7: main diagonal (rank changes same direction as file)
    move_code 8-15: anti-diagonal (rank changes opposite direction to file)
    """
    from_file = Square.file(from_sq)
    from_rank = Square.rank(from_sq)

    if move_code >= 8:
        # Anti-diagonal
        dest_file = move_code - 8
        file_diff = dest_file - from_file
        # Anti-diagonal: rank changes opposite to file
        dest_rank = from_rank - file_diff
    else:
        # Main diagonal
        dest_file = move_code
        file_diff = dest_file - from_file
        # Main diagonal: rank changes same as file
        dest_rank = from_rank + file_diff

    if not (0 <= dest_rank <= 7):
        return -1  # Invalid square

    return Square.make(dest_file, dest_rank)


def _decode_knight_move(from_sq: int, move_code: int) -> int:
    """
    Decode knight move.

    move_code 1-8 encodes the 8 possible knight destinations.
    The offsets are ordered by destination square value.
    """
    # Knight move deltas: (file_delta, rank_delta) for move codes 1-8
    # Ordered by resulting square offset: -17, -15, -10, -6, +6, +10, +15, +17
    knight_deltas = [
        (0, 0),  # 0: unused
        (-1, -2),  # 1: offset -17
        (1, -2),  # 2: offset -15
        (-2, -1),  # 3: offset -10
        (2, -1),  # 4: offset -6
        (-2, 1),  # 5: offset +6
        (2, 1),  # 6: offset +10
        (-1, 2),  # 7: offset +15
        (1, 2),  # 8: offset +17
    ]

    if 1 <= move_code <= 8:
        from_file = Square.file(from_sq)
        from_rank = Square.rank(from_sq)
        file_delta, rank_delta = knight_deltas[move_code]
        dest_file = from_file + file_delta
        dest_rank = from_rank + rank_delta

        if 0 <= dest_file <= 7 and 0 <= dest_rank <= 7:
            return Square.make(dest_file, dest_rank)

    return -1  # Invalid move


def _decode_pawn_move(
    from_sq: int, move_code: int, color: Color
) -> Tuple[int, Optional[Piece]]:
    """
    Decode pawn move.

    move_code encodes direction and optional promotion:
    0-2: captures left, forward, captures right (no promo or push 2 for code 15)
    3-5: same directions, promote to queen
    6-8: same directions, promote to rook
    9-11: same directions, promote to bishop
    12-14: same directions, promote to knight
    15: double pawn push

    Returns:
        (to_square, promotion_piece or None)
    """
    # Direction offsets: [left capture, forward, right capture]
    # Repeated for different promotions, then double push
    direction_offsets = [7, 8, 9, 7, 8, 9, 7, 8, 9, 7, 8, 9, 7, 8, 9, 16]

    # Promotion pieces for each group of 3
    promo_pieces = [
        None,
        None,
        None,  # 0-2: no promotion
        Piece.QUEEN,
        Piece.QUEEN,
        Piece.QUEEN,  # 3-5
        Piece.ROOK,
        Piece.ROOK,
        Piece.ROOK,  # 6-8
        Piece.BISHOP,
        Piece.BISHOP,
        Piece.BISHOP,  # 9-11
        Piece.KNIGHT,
        Piece.KNIGHT,
        Piece.KNIGHT,  # 12-14
        None,  # 15: double push
    ]

    if move_code > 15:
        return from_sq, None

    offset = direction_offsets[move_code]
    promotion = promo_pieces[move_code]

    if color == Color.WHITE:
        to_sq = from_sq + offset
    else:
        to_sq = from_sq - offset

    return to_sq, promotion
