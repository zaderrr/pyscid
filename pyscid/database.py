"""
Unified database interface for reading chess game databases.

Provides a single Database class that can open SCID4, SCID5, and PGN files,
automatically detecting the format based on file extension.

Supports lazy loading for fast database opening - by default only metadata
is loaded, with index entries and namebase loaded on demand.
"""

from pathlib import Path
from typing import Iterator, Union, Optional

from .game import Game, IndexEntry
from .scid4 import Scid4Database
from .scid5 import Scid5Database
from .pgn import PgnDatabase
from .namebase_interface import NameBaseInterface


class Database:
    """
    Unified chess database reader.

    Supports:
    - SCID4 format (.si4)
    - SCID5 format (.si5)
    - PGN format (.pgn)

    Loading modes (SCID formats only):
    - Default (lazy): Instant open, data loaded on demand
    - preload=True: Load everything upfront (like original behavior)
    - preload_names=True: Load namebase only, lazy index entries
    - cache_size=N: Enable LRU cache for repeated random access

    Usage:
        # Default: lazy loading (instant open)
        db = Database.open("games.si4")

        # Preload everything (for full iteration)
        db = Database.open("games.si4", preload=True)

        # Preload just namebase (fast metadata access)
        db = Database.open("games.si4", preload_names=True)

        # Enable LRU cache for repeated random access
        db = Database.open("games.si4", cache_size=10000)

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
        self._namebase_interface: Optional[NameBaseInterface] = None

        if isinstance(backend, Scid4Database):
            self._format = "scid4"
        elif isinstance(backend, Scid5Database):
            self._format = "scid5"
        elif isinstance(backend, PgnDatabase):
            self._format = "pgn"

    @staticmethod
    def open(
        filepath: str,
        preload: bool = False,
        preload_names: bool = False,
        cache_size: int = 0,
    ) -> "Database":
        """
        Open a chess database file.

        The format is auto-detected based on file extension:
        - .si4 -> SCID4
        - .si5 -> SCID5
        - .pgn -> PGN

        If no extension is provided, tries each format in order.

        Args:
            filepath: Path to database file (with or without extension)
            preload: If True, load all data upfront (SCID formats only).
                     Slower open but faster iteration.
            preload_names: If True, load namebase immediately (SCID formats only).
                           Useful for fast metadata access.
            cache_size: Size of LRU cache for index entries (SCID formats only).
                        0 = disabled. Useful for repeated random access.

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
            return Database._open_scid4(filepath, preload, preload_names, cache_size)
        elif suffix == ".si5":
            return Database._open_scid5(filepath, preload, preload_names, cache_size)
        elif suffix == ".pgn":
            return Database._open_pgn(filepath)

        # Try to auto-detect by checking which files exist
        base = str(path)

        # Try SCID4
        if Path(base + ".si4").exists():
            return Database._open_scid4(
                base + ".si4", preload, preload_names, cache_size
            )

        # Try SCID5
        if Path(base + ".si5").exists():
            return Database._open_scid5(
                base + ".si5", preload, preload_names, cache_size
            )

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
                    return Database._open_scid4(
                        filepath, preload, preload_names, cache_size
                    )
            elif magic.startswith(b"["):
                # Looks like PGN
                return Database._open_pgn(filepath)

        raise FileNotFoundError(
            f"Could not find database files for: {filepath}\n"
            f"Tried: {base}.si4, {base}.si5, {base}.pgn"
        )

    @staticmethod
    def _open_scid4(
        filepath: str,
        preload: bool = False,
        preload_names: bool = False,
        cache_size: int = 0,
    ) -> "Database":
        """Open a SCID4 database"""
        backend = Scid4Database.open(
            filepath,
            preload=preload,
            preload_names=preload_names,
            cache_size=cache_size,
        )
        return Database(backend)

    @staticmethod
    def _open_scid5(
        filepath: str,
        preload: bool = False,
        preload_names: bool = False,
        cache_size: int = 0,
    ) -> "Database":
        """Open a SCID5 database"""
        backend = Scid5Database.open(
            filepath,
            preload=preload,
            preload_names=preload_names,
            cache_size=cache_size,
        )
        return Database(backend)

    @staticmethod
    def _open_pgn(filepath: str) -> "Database":
        """Open a PGN file (always fully loaded)"""
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

    def preload_all(self):
        """
        Explicitly load all data (namebase + all index entries).

        Call this after opening with lazy loading if you want to
        preload everything for faster subsequent access.

        Only affects SCID formats; PGN is always fully loaded.
        """
        if isinstance(self._backend, (Scid4Database, Scid5Database)):
            self._backend.preload_all()

    def preload_namebase(self):
        """
        Explicitly load just the namebase.

        Useful if you want fast access to player/event/site names
        without loading all index entries.

        Only affects SCID formats; PGN is always fully loaded.
        """
        if isinstance(self._backend, (Scid4Database, Scid5Database)):
            self._backend.preload_namebase()

    def clear_cache(self):
        """
        Clear the index entry cache.

        Only has effect if cache_size > 0 was specified on open.
        """
        if isinstance(self._backend, (Scid4Database, Scid5Database)):
            self._backend.clear_cache()

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

    @property
    def namebase(self) -> NameBaseInterface:
        """
        Access the database namebase for browsing names.

        Provides access to all unique names stored in the database:
        - players: All player names with IDs
        - events: All event names with IDs
        - sites: All site names with IDs
        - rounds: All round names with IDs

        Each entry includes an ID that can be used for fast ID-based searches.

        Usage:
            # Browse all players
            for player in db.namebase.players:
                print(f"ID {player.id}: {player.name}")

            # Find specific player
            magnus = [p for p in db.namebase.players
                      if "Carlsen, Magnus" in p.name][0]

            # Fast search by ID
            games = list(db.search(white_id=magnus.id))

        Note: Only available for SCID4 and SCID5 formats.

        Returns:
            NameBaseInterface for browsing names

        Raises:
            NotImplementedError: If called on PGN format database
        """
        if isinstance(self._backend, PgnDatabase):
            raise NotImplementedError(
                "NameBase access is not available for PGN format. "
                "PGN databases do not have a separate namebase structure."
            )

        if self._namebase_interface is None:
            self._namebase_interface = NameBaseInterface(self._backend)

        return self._namebase_interface

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

        For SCID formats (.si4, .si5), this uses an optimized search that
        filters on index entries first, avoiding full game decoding until
        a match is found. Name indexes are built lazily on first search.

        For PGN format, falls back to iterating through all games.

        Supported criteria:
            white: str - Player name (partial match, case-insensitive)
            black: str - Player name (partial match, case-insensitive)
            player: str - Either player (partial match, case-insensitive)
            white_id: int - White player ID (exact match, fastest)
            black_id: int - Black player ID (exact match, fastest)
            player_id: int - Either player ID (exact match, fastest)
            event: str - Event name (partial match, case-insensitive)
            event_id: int - Event ID (exact match)
            site: str - Site name (partial match, case-insensitive)
            site_id: int - Site ID (exact match)
            year: int - Game year (exact match)
            year_min: int - Minimum year
            year_max: int - Maximum year
            result: Result - Game result
            eco: str - ECO code prefix
            min_elo: int - Minimum rating for either player

        Yields:
            Game objects matching all criteria
        """
        # Use optimized backend search for SCID formats
        if isinstance(self._backend, (Scid4Database, Scid5Database)):
            yield from self._backend.search(**criteria)
        else:
            # PGN fallback - iterate through all games
            yield from self._search_slow(**criteria)

    def _search_slow(self, **criteria) -> Iterator[Game]:
        """
        Slow search implementation for PGN databases.

        Iterates through all games and checks each criterion.
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
