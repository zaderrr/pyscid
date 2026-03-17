#!/usr/bin/env python3
"""
Basic usage example for pyscid library.
"""

from pyscid import Database, Result

# Example PGN content for testing
SAMPLE_PGN = """
[Event "Test Tournament"]
[Site "Test City"]
[Date "2024.01.15"]
[Round "1"]
[White "Player One"]
[Black "Player Two"]
[Result "1-0"]
[WhiteElo "2400"]
[BlackElo "2350"]
[ECO "C50"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. O-O Nf6 5. d3 O-O 6. Nc3 d6 1-0

[Event "Test Tournament"]
[Site "Test City"]
[Date "2024.01.15"]
[Round "2"]
[White "Player Three"]
[Black "Player Four"]
[Result "1/2-1/2"]

1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Be7 5. e3 O-O 1/2-1/2
"""


def main():
    # Save sample PGN to a temp file
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(mode="w", suffix=".pgn", delete=False) as f:
        f.write(SAMPLE_PGN)
        pgn_path = f.name

    try:
        # Open the database
        print("Opening PGN database...")
        db = Database.open(pgn_path)

        print(f"Format: {db.format}")
        print(f"Number of games: {len(db)}")
        print()

        # Iterate through all games
        for i, game in enumerate(db):
            print(f"Game {i + 1}:")
            print(f"  Event: {game.event}")
            print(f"  White: {game.white} ({game.white_elo})")
            print(f"  Black: {game.black} ({game.black_elo})")
            print(f"  Date: {game.date_string}")
            print(f"  Result: {game.result}")
            print(f"  ECO: {game.eco}")
            print(f"  Moves: {len(game.moves)}")

            # Print first few moves
            move_strs = [move.uci() for move in game.moves[:6]]
            print(f"  Opening: {' '.join(move_strs)}")
            print()

        # Search example
        print("Searching for games with Player One...")
        for game in db.search(player="Player One"):
            print(f"  Found: {game.white} vs {game.black}")
        print()

        # Export to PGN
        print("Exporting first game to PGN:")
        print("-" * 40)
        print(db[0].to_pgn())
        print("-" * 40)

        db.close()

    finally:
        os.unlink(pgn_path)

    print("\nAll examples completed successfully!")


if __name__ == "__main__":
    main()
