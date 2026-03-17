"""
Unified database interface for reading chess game databases.

Provides a single Database class that can open SCID4, SCID5, and PGN files,
automatically detecting the format based on file extension.
"""

from pathlib import Path
from typing import Iterator, Union, Optional

from .game import Game, IndexEntry
from .scid4 import Scid4Database
from .scid5 import Scid5Database
from .pgn import PgnDatabase


class Database:
    """
    Unified chess database reader.

    Supports:
    - SCID4 format (.si4)
    - SCID5 format (.si5)
    - PGN format (.pgn)

    Usage:
        # Open any supported format
        db = Database.open("games.si4")

        # Or use auto-detection
        db = Database.open("games")  # Will try .si4, .si5, .pgn

        # Iterate through games
        for game in db:
            print(f"{game.white} vs {game.black}")

        # Random access
        game = db[42]

        # Get number of games
        print(f"Total games: {len(db)}")

        # Use as context manager
        with Database.open("games.si4") as db:
            for game in db:
                print(game)
    """

    def __init__(self, backend: Union[Scid4Database, Scid5Database, PgnDatabase]):
        self._backend = backend
        self._format: str = ""

        if isinstance(backend, Scid4Database):
            self._format = "scid4"
        elif isinstance(backend, Scid5Database):
            self._format = "scid5"
        elif isinstance(backend, PgnDatabase):
            self._format = "pgn"

    @staticmethod
    def open(filepath: str) -> "Database":
        """
        Open a chess database file.

        The format is auto-detected based on file extension:
        - .si4 -> SCID4
        - .si5 -> SCID5
        - .pgn -> PGN

        If no extension is provided, tries each format in order.

        Args:
            filepath: Path to database file (with or without extension)

        Returns:
            Database instance

        Raises:
            FileNotFoundError: If the database files cannot be found
            ValueError: If the format cannot be determined or file is invalid
        """
        path = Path(filepath)

        # Check explicit extension
        suffix = path.suffix.lower()

        if suffix == ".si4":
            return Database._open_scid4(filepath)
        elif suffix == ".si5":
            return Database._open_scid5(filepath)
        elif suffix == ".pgn":
            return Database._open_pgn(filepath)

        # Try to auto-detect by checking which files exist
        base = str(path)

        # Try SCID4
        if Path(base + ".si4").exists():
            return Database._open_scid4(base + ".si4")

        # Try SCID5
        if Path(base + ".si5").exists():
            return Database._open_scid5(base + ".si5")

        # Try PGN
        if Path(base + ".pgn").exists():
            return Database._open_pgn(base + ".pgn")

        # Try without modifying path (maybe it's a full path already)
        if path.exists():
            # Try to detect from content
            with open(filepath, "rb") as f:
                magic = f.read(8)

            if magic.startswith(b"Scid.si"):
                # It's a SCID index file - check version
                if b"4" in magic or magic == b"Scid.si\x00":
                    return Database._open_scid4(filepath)
            elif magic.startswith(b"["):
                # Looks like PGN
                return Database._open_pgn(filepath)

        raise FileNotFoundError(
            f"Could not find database files for: {filepath}\n"
            f"Tried: {base}.si4, {base}.si5, {base}.pgn"
        )

    @staticmethod
    def _open_scid4(filepath: str) -> "Database":
        """Open a SCID4 database"""
        backend = Scid4Database.open(filepath)
        return Database(backend)

    @staticmethod
    def _open_scid5(filepath: str) -> "Database":
        """Open a SCID5 database"""
        backend = Scid5Database.open(filepath)
        return Database(backend)

    @staticmethod
    def _open_pgn(filepath: str) -> "Database":
        """Open a PGN file"""
        backend = PgnDatabase.open(filepath)
        return Database(backend)

    def close(self):
        """Close the database and release resources"""
        self._backend.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __len__(self) -> int:
        """Return the number of games in the database"""
        return len(self._backend)

    def __iter__(self) -> Iterator[Game]:
        """Iterate over all games in the database"""
        return iter(self._backend)

    def __getitem__(self, index: int) -> Game:
        """Get a game by index (0-based)"""
        return self._backend[index]

    @property
    def format(self) -> str:
        """Return the format of the database ('scid4', 'scid5', or 'pgn')"""
        return self._format

    @property
    def num_games(self) -> int:
        """Return the number of games in the database"""
        return len(self)

    @property
    def description(self) -> str:
        """Return the database description (if available)"""
        if isinstance(self._backend, Scid4Database):
            if self._backend.header:
                return self._backend.header.description
        elif isinstance(self._backend, Scid5Database):
            return self._backend.description
        elif isinstance(self._backend, PgnDatabase):
            return self._backend.description
        return ""

    def get_game(self, index: int) -> Game:
        """
        Get a game by index.

        Args:
            index: 0-based game index

        Returns:
            Game object with all metadata and moves
        """
        return self[index]

    def get_index_entry(self, index: int) -> Optional[IndexEntry]:
        """
        Get the raw index entry for a game (SCID formats only).

        Args:
            index: 0-based game index

        Returns:
            IndexEntry object or None for PGN format
        """
        if isinstance(self._backend, (Scid4Database, Scid5Database)):
            return self._backend.get_index_entry(index)
        return None

    def search(self, **criteria) -> Iterator[Game]:
        """
        Search for games matching the given criteria.

        Supported criteria:
            white: str - Player name (partial match)
            black: str - Player name (partial match)
            player: str - Either player (partial match)
            event: str - Event name (partial match)
            site: str - Site name (partial match)
            year: int - Game year
            year_min: int - Minimum year
            year_max: int - Maximum year
            result: Result - Game result
            eco: str - ECO code prefix
            min_elo: int - Minimum rating for either player

        Yields:
            Game objects matching all criteria
        """
        white = criteria.get("white", "").lower()
        black = criteria.get("black", "").lower()
        player = criteria.get("player", "").lower()
        event = criteria.get("event", "").lower()
        site = criteria.get("site", "").lower()
        year = criteria.get("year")
        year_min = criteria.get("year_min")
        year_max = criteria.get("year_max")
        result = criteria.get("result")
        eco = criteria.get("eco", "").upper()
        min_elo = criteria.get("min_elo", 0)

        for game in self:
            # Check player names
            if white and white not in game.white.lower():
                continue
            if black and black not in game.black.lower():
                continue
            if player:
                if (
                    player not in game.white.lower()
                    and player not in game.black.lower()
                ):
                    continue

            # Check event/site
            if event and event not in game.event.lower():
                continue
            if site and site not in game.site.lower():
                continue

            # Check year
            game_year = game.date.year if game.date else None
            if year and game_year != year:
                continue
            if year_min and (game_year is None or game_year < year_min):
                continue
            if year_max and (game_year is None or game_year > year_max):
                continue

            # Check result
            if result is not None and game.result != result:
                continue

            # Check ECO
            if eco and not game.eco.upper().startswith(eco):
                continue

            # Check ratings
            if min_elo > 0:
                if game.white_elo < min_elo and game.black_elo < min_elo:
                    continue

            yield game
