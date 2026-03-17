"""
Basic tests for pyscid library.
"""

import tempfile
import os
import pytest

from pyscid import Database, Game, Move, Color, Piece, Result, Square
from pyscid.date import encode_date, decode_date, date_to_string, string_to_date


class TestTypes:
    """Test basic type definitions"""

    def test_color(self):
        assert Color.WHITE == 0
        assert Color.BLACK == 1
        assert Color.WHITE.flip() == Color.BLACK
        assert Color.BLACK.flip() == Color.WHITE

    def test_piece(self):
        assert Piece.KING == 1
        assert Piece.QUEEN == 2
        assert Piece.PAWN == 6
        assert Piece.KING.char() == "K"
        assert Piece.from_char("Q") == Piece.QUEEN
        assert Piece.from_char("n") == Piece.KNIGHT

    def test_result(self):
        assert str(Result.WHITE_WINS) == "1-0"
        assert str(Result.BLACK_WINS) == "0-1"
        assert str(Result.DRAW) == "1/2-1/2"
        assert str(Result.NONE) == "*"
        assert Result.from_string("1-0") == Result.WHITE_WINS
        assert Result.from_string("1/2-1/2") == Result.DRAW

    def test_square(self):
        assert Square.E4 == 28
        assert Square.make(4, 3) == 28  # e4
        assert Square.file(28) == 4
        assert Square.rank(28) == 3
        assert Square.name(28) == "e4"
        assert Square.from_name("e4") == 28
        assert Square.from_name("a1") == 0
        assert Square.from_name("h8") == 63


class TestDate:
    """Test date encoding/decoding"""

    def test_encode_decode(self):
        packed = encode_date(2024, 3, 15)
        year, month, day = decode_date(packed)
        assert year == 2024
        assert month == 3
        assert day == 15

    def test_partial_date(self):
        packed = encode_date(2024, None, None)
        year, month, day = decode_date(packed)
        assert year == 2024
        assert month is None
        assert day is None

    def test_date_string(self):
        packed = encode_date(2024, 3, 15)
        assert date_to_string(packed) == "2024.03.15"

        packed = encode_date(2024, None, None)
        assert date_to_string(packed) == "2024.??.??"

    def test_string_to_date(self):
        packed = string_to_date("2024.03.15")
        year, month, day = decode_date(packed)
        assert year == 2024
        assert month == 3
        assert day == 15


class TestMove:
    """Test Move class"""

    def test_uci(self):
        move = Move(from_square=Square.E2, to_square=Square.E4)
        assert move.uci() == "e2e4"

    def test_promotion(self):
        move = Move(from_square=Square.E7, to_square=Square.E8, promotion=Piece.QUEEN)
        assert move.uci() == "e7e8q"

    def test_castle(self):
        move = Move(from_square=Square.E1, to_square=Square.G1, is_castle_kingside=True)
        assert str(move) == "O-O"

        move = Move(
            from_square=Square.E1, to_square=Square.C1, is_castle_queenside=True
        )
        assert str(move) == "O-O-O"

    def test_null_move(self):
        move = Move(from_square=0, to_square=0, is_null_move=True)
        assert move.uci() == "0000"
        assert str(move) == "--"


class TestMoveDecoding:
    """Test internal move decoding functions"""

    def test_bishop_move_decode_main_diagonal(self):
        """Test bishop move decoding for main diagonal (move_code 0-7)."""
        from pyscid.gamedata import _decode_bishop_move

        # Bishop on e4 (square 28, file 4, rank 3)
        from_sq = Square.E4

        # Up-right along main diagonal: e4 to h7 (move_code = 7 for h-file)
        to_sq = _decode_bishop_move(from_sq, 7, Color.WHITE)
        assert to_sq == Square.H7, f"Expected h7, got {Square.name(to_sq)}"

        # Down-left along main diagonal: e4 to b1 (move_code = 1 for b-file)
        to_sq = _decode_bishop_move(from_sq, 1, Color.WHITE)
        assert to_sq == Square.B1, f"Expected b1, got {Square.name(to_sq)}"

        # Single step up-right: e4 to f5 (move_code = 5 for f-file)
        to_sq = _decode_bishop_move(from_sq, 5, Color.WHITE)
        assert to_sq == Square.F5, f"Expected f5, got {Square.name(to_sq)}"

    def test_bishop_move_decode_anti_diagonal(self):
        """Test bishop move decoding for anti-diagonal (move_code 8-15)."""
        from pyscid.gamedata import _decode_bishop_move

        # Bishop on e4 (square 28, file 4, rank 3)
        from_sq = Square.E4

        # Down-right along anti-diagonal: e4 to h1 (move_code = 8+7 = 15)
        to_sq = _decode_bishop_move(from_sq, 15, Color.WHITE)
        assert to_sq == Square.H1, f"Expected h1, got {Square.name(to_sq)}"

        # Up-left along anti-diagonal: e4 to b7 (move_code = 8+1 = 9)
        to_sq = _decode_bishop_move(from_sq, 9, Color.WHITE)
        assert to_sq == Square.B7, f"Expected b7, got {Square.name(to_sq)}"

        # Single step down-right: e4 to f3 (move_code = 8+5 = 13)
        to_sq = _decode_bishop_move(from_sq, 13, Color.WHITE)
        assert to_sq == Square.F3, f"Expected f3, got {Square.name(to_sq)}"

    def test_bishop_move_same_file_stays_put(self):
        """Test bishop with same file destination returns correct square"""
        from pyscid.gamedata import _decode_bishop_move

        # Bishop on d4, move_code = 3 (d-file) means no movement on main diagonal
        # This should return d4 itself
        from_sq = Square.D4
        to_sq = _decode_bishop_move(from_sq, 3, Color.WHITE)
        assert to_sq == Square.D4

    def test_knight_move_decode_all_directions(self):
        """Test knight move decoding for all 8 directions"""
        from pyscid.gamedata import _decode_knight_move

        # Knight on e4 (square 28, file 4, rank 3)
        from_sq = Square.E4

        # Test all 8 knight moves from e4
        expected = [
            (1, Square.D2),  # -1 file, -2 rank
            (2, Square.F2),  # +1 file, -2 rank
            (3, Square.C3),  # -2 file, -1 rank
            (4, Square.G3),  # +2 file, -1 rank
            (5, Square.C5),  # -2 file, +1 rank
            (6, Square.G5),  # +2 file, +1 rank
            (7, Square.D6),  # -1 file, +2 rank
            (8, Square.F6),  # +1 file, +2 rank
        ]

        for move_code, expected_sq in expected:
            to_sq = _decode_knight_move(from_sq, move_code)
            assert to_sq == expected_sq, (
                f"move_code {move_code}: expected {Square.name(expected_sq)}, got {Square.name(to_sq)}"
            )

    def test_knight_move_edge_detection(self):
        """Test knight moves that would go off the board return invalid"""
        from pyscid.gamedata import _decode_knight_move

        # Knight on a1 - only 2 valid knight moves
        from_sq = Square.A1
        valid_moves = 0
        for move_code in range(1, 9):
            to_sq = _decode_knight_move(from_sq, move_code)
            if Square.is_valid(to_sq):
                valid_moves += 1
        # From a1, knight can only go to b3 or c2
        assert valid_moves == 2, f"Expected 2 valid moves from a1, got {valid_moves}"

        # Knight on h8 - only 2 valid knight moves
        from_sq = Square.H8
        valid_moves = 0
        for move_code in range(1, 9):
            to_sq = _decode_knight_move(from_sq, move_code)
            if Square.is_valid(to_sq):
                valid_moves += 1
        assert valid_moves == 2, f"Expected 2 valid moves from h8, got {valid_moves}"

    def test_rook_move_decode(self):
        """Test rook move decoding"""
        from pyscid.gamedata import _decode_rook_move

        # Rook on e4
        from_sq = Square.E4

        # Horizontal to a4 (move_code = 0 for a-file)
        to_sq = _decode_rook_move(from_sq, 0)
        assert to_sq == Square.A4

        # Horizontal to h4 (move_code = 7 for h-file)
        to_sq = _decode_rook_move(from_sq, 7)
        assert to_sq == Square.H4

        # Vertical to e1 (move_code = 8 + 0 = 8 for rank 1)
        to_sq = _decode_rook_move(from_sq, 8)
        assert to_sq == Square.E1

        # Vertical to e8 (move_code = 8 + 7 = 15 for rank 8)
        to_sq = _decode_rook_move(from_sq, 15)
        assert to_sq == Square.E8


class TestPgnParsing:
    """Test PGN parsing"""

    SAMPLE_PGN = """
[Event "Test Event"]
[Site "Test Site"]
[Date "2024.01.15"]
[Round "1"]
[White "Player A"]
[Black "Player B"]
[Result "1-0"]
[WhiteElo "2400"]
[BlackElo "2300"]
[ECO "C50"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 1-0
"""

    @pytest.fixture
    def pgn_file(self):
        """Create a temporary PGN file"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pgn", delete=False) as f:
            f.write(self.SAMPLE_PGN)
            path = f.name
        yield path
        os.unlink(path)

    def test_open_pgn(self, pgn_file):
        db = Database.open(pgn_file)
        assert db.format == "pgn"
        assert len(db) == 1
        db.close()

    def test_game_metadata(self, pgn_file):
        with Database.open(pgn_file) as db:
            game = db[0]
            assert game.white == "Player A"
            assert game.black == "Player B"
            assert game.event == "Test Event"
            assert game.site == "Test Site"
            assert game.result == Result.WHITE_WINS
            assert game.white_elo == 2400
            assert game.black_elo == 2300
            assert game.eco == "C50"

    def test_moves(self, pgn_file):
        with Database.open(pgn_file) as db:
            game = db[0]
            assert len(game.moves) == 6

            # Check first move: e4
            assert game.moves[0].uci() == "e2e4"

            # Check second move: e5
            assert game.moves[1].uci() == "e7e5"

    def test_iteration(self, pgn_file):
        with Database.open(pgn_file) as db:
            games = list(db)
            assert len(games) == 1

    def test_to_pgn(self, pgn_file):
        with Database.open(pgn_file) as db:
            game = db[0]
            pgn = game.to_pgn()
            assert '[White "Player A"]' in pgn
            assert '[Black "Player B"]' in pgn
            assert '[Result "1-0"]' in pgn


class TestSearch:
    """Test search functionality"""

    MULTI_GAME_PGN = """
[Event "Tournament A"]
[White "Carlsen, Magnus"]
[Black "Nakamura, Hikaru"]
[Result "1-0"]
[Date "2024.01.01"]

1. e4 e5 1-0

[Event "Tournament B"]
[White "Nakamura, Hikaru"]
[Black "So, Wesley"]
[Result "0-1"]
[Date "2023.06.15"]

1. d4 d5 0-1

[Event "Tournament A"]
[White "Caruana, Fabiano"]
[Black "Carlsen, Magnus"]
[Result "1/2-1/2"]
[Date "2024.02.01"]

1. c4 e5 1/2-1/2
"""

    @pytest.fixture
    def multi_pgn_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pgn", delete=False) as f:
            f.write(self.MULTI_GAME_PGN)
            path = f.name
        yield path
        os.unlink(path)

    def test_search_by_player(self, multi_pgn_file):
        with Database.open(multi_pgn_file) as db:
            results = list(db.search(player="Carlsen"))
            assert len(results) == 2

    def test_search_by_white(self, multi_pgn_file):
        with Database.open(multi_pgn_file) as db:
            results = list(db.search(white="Nakamura"))
            assert len(results) == 1

    def test_search_by_event(self, multi_pgn_file):
        with Database.open(multi_pgn_file) as db:
            results = list(db.search(event="Tournament A"))
            assert len(results) == 2

    def test_search_by_year(self, multi_pgn_file):
        with Database.open(multi_pgn_file) as db:
            results = list(db.search(year=2024))
            assert len(results) == 2

    def test_search_by_result(self, multi_pgn_file):
        with Database.open(multi_pgn_file) as db:
            results = list(db.search(result=Result.DRAW))
            assert len(results) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
