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
