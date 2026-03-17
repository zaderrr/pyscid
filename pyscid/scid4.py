"""
SCID4 format codec.

Handles reading of SCID version 4 databases consisting of:
- .si4 - Index file (header + 47-byte records per game)
- .sn4 - NameBase file (front-coded strings for players, events, sites, rounds)
- .sg4 - Game file (encoded game data: tags, start position, moves)

Reference: scid/src/codec_scid4.cpp, scid/src/codec_scid4.h
"""

import struct
import mmap
from pathlib import Path
from typing import List, Dict, Optional, Tuple, BinaryIO, Iterator, Set

from .types import Result, RatingType, NameType
from .game import IndexEntry, Game, Move
from .date import decode_date, date_to_python


# Constants from codec_scid4.cpp
INDEX_MAGIC = b"Scid.si\x00"
NAMEBASE_MAGIC = b"Scid.sn\x00"

SCID_VERSION = 400
SCID_OLDEST_VERSION = 300

INDEX_ENTRY_SIZE_V4 = 47
INDEX_ENTRY_SIZE_V3 = 46

# Index header size: magic(8) + version(2) + baseType(4) + numGames(3) +
#                    autoLoad(3) + description(108) + flagDescs(9*6)
INDEX_HEADER_SIZE = 182
SCID_DESC_LENGTH = 107
CUSTOM_FLAG_DESC_LENGTH = 8

# Limits
LIMIT_GAMEOFFSET = 1 << 32
LIMIT_GAMELEN = 1 << 17
LIMIT_NUMGAMES = 16777214
LIMIT_NAMELEN = 255


class NameBase:
    """
    NameBase stores unique strings for players, events, sites, and rounds.

    In SCID4 format, names are stored with front-coding compression (each name
    shares a prefix with the previous name in sorted order).

    Reference: scid/src/codec_scid4.cpp namefileRead()
    """

    def __init__(self):
        # names[NameType] = list of strings, indexed by ID
        self.names: Dict[NameType, List[str]] = {
            NameType.PLAYER: [],
            NameType.EVENT: [],
            NameType.SITE: [],
            NameType.ROUND: [],
        }

    def get_name(self, name_type: NameType, name_id: int) -> str:
        """Get a name by type and ID"""
        names = self.names.get(name_type, [])
        if 0 <= name_id < len(names):
            return names[name_id]
        return "?"

    def get_player(self, player_id: int) -> str:
        return self.get_name(NameType.PLAYER, player_id)

    def get_event(self, event_id: int) -> str:
        return self.get_name(NameType.EVENT, event_id)

    def get_site(self, site_id: int) -> str:
        return self.get_name(NameType.SITE, site_id)

    def get_round(self, round_id: int) -> str:
        return self.get_name(NameType.ROUND, round_id)

    @staticmethod
    def read_from_file(filepath: str) -> "NameBase":
        """
        Read a SCID4 NameBase file (.sn4).

        File format:
        - Header: magic(8) + unused(4) + numNames[4](3 each) + maxFreq[4](3 each)
        - Records: id(2-3) + freq(1-3) + length(1) + prefix(1) + name(0-255)
        """
        nb = NameBase()

        with open(filepath, "rb") as f:
            # Read magic
            magic = f.read(8)
            if magic != NAMEBASE_MAGIC:
                raise ValueError(f"Invalid namebase magic: {magic!r}")

            # Skip obsolete timestamp (4 bytes)
            f.read(4)

            # Read number of names for each type (3 bytes each)
            num_names = {}
            for nt in [NameType.PLAYER, NameType.EVENT, NameType.SITE, NameType.ROUND]:
                num_names[nt] = _read_three_bytes(f)

            # Read max frequencies (obsolete, but need to read for compatibility)
            max_freq = {}
            for nt in [NameType.PLAYER, NameType.EVENT, NameType.SITE, NameType.ROUND]:
                max_freq[nt] = _read_three_bytes(f)

            # Read names for each type
            for nt in [NameType.PLAYER, NameType.EVENT, NameType.SITE, NameType.ROUND]:
                names_list = [""] * num_names[nt]  # Pre-allocate with empty strings
                prev_name = ""

                for i in range(num_names[nt]):
                    # Read ID (2 or 3 bytes depending on count)
                    if num_names[nt] >= 65536:
                        name_id = _read_three_bytes(f)
                    else:
                        name_id = _read_two_bytes(f)

                    # Read frequency (obsolete, 1-3 bytes)
                    if max_freq[nt] >= 65536:
                        _read_three_bytes(f)
                    elif max_freq[nt] >= 256:
                        _read_two_bytes(f)
                    else:
                        f.read(1)

                    # Read name with front-coding
                    length = f.read(1)[0]
                    prefix = f.read(1)[0] if i > 0 else 0

                    if prefix > length:
                        raise ValueError(
                            f"Invalid front-coding: prefix {prefix} > length {length}"
                        )

                    new_chars = f.read(length - prefix)
                    name = prev_name[:prefix] + new_chars.decode("latin-1")
                    prev_name = name

                    if name_id < num_names[nt]:
                        names_list[name_id] = name

                nb.names[nt] = names_list

        return nb


class IndexHeader:
    """Header data from the index file (.si4)"""

    def __init__(self):
        self.version: int = SCID_VERSION
        self.base_type: int = 0
        self.num_games: int = 0
        self.auto_load: int = 1
        self.description: str = ""
        self.flag_descriptions: List[str] = [""] * 6


def read_index_header(f: BinaryIO) -> IndexHeader:
    """
    Read the index file header.

    Header format (182 bytes):
    - magic: 8 bytes "Scid.si\0"
    - version: 2 bytes (300 or 400)
    - baseType: 4 bytes
    - numGames: 3 bytes
    - autoLoad: 3 bytes
    - description: 108 bytes (null-terminated)
    - flagDesc[6]: 9 bytes each (null-terminated)
    """
    header = IndexHeader()

    # Read magic
    magic = f.read(8)
    if magic != INDEX_MAGIC:
        raise ValueError(f"Invalid index magic: {magic!r}")

    # Read version (2 bytes, big-endian)
    header.version = _read_two_bytes(f)

    # Read base type (4 bytes, big-endian)
    header.base_type = _read_four_bytes(f)

    # Read number of games (3 bytes)
    header.num_games = _read_three_bytes(f)

    # Read auto-load game number (3 bytes)
    header.auto_load = _read_three_bytes(f)

    # Read description (108 bytes, null-terminated)
    desc_bytes = f.read(SCID_DESC_LENGTH + 1)
    null_pos = desc_bytes.find(b"\x00")
    if null_pos >= 0:
        header.description = desc_bytes[:null_pos].decode("latin-1")
    else:
        header.description = desc_bytes.decode("latin-1")

    # Read custom flag descriptions (v4 only)
    if header.version >= 400:
        for i in range(6):
            flag_bytes = f.read(CUSTOM_FLAG_DESC_LENGTH + 1)
            null_pos = flag_bytes.find(b"\x00")
            if null_pos >= 0:
                header.flag_descriptions[i] = flag_bytes[:null_pos].decode("latin-1")
            else:
                header.flag_descriptions[i] = flag_bytes.decode("latin-1")

    return header


def extract_search_fields(
    data: bytes, version: int
) -> Tuple[int, int, int, int, int, int, int, int, int]:
    """
    Fast extraction of search-relevant fields from an index entry.

    Returns:
        Tuple of (white_id, black_id, event_id, site_id, date, result, eco_code, white_elo, black_elo)

    This is faster than full decode_index_entry() when you only need these fields.
    """
    # Skip offset (4 bytes), length (2-3 bytes), flags (2 bytes)
    # For v4: offset=4, len_low=2, len_flags=1, flags=2 = 9 bytes
    # For v3: offset=4, len_low=2, flags=2 = 8 bytes
    pos = 9 if version >= 400 else 8

    # WhiteID and BlackID (20-bit each, packed in 5 bytes)
    white_black_high = data[pos]
    white_id_low = (data[pos + 1] << 8) | data[pos + 2]
    white_id = ((white_black_high & 0xF0) << 12) | white_id_low
    black_id_low = (data[pos + 3] << 8) | data[pos + 4]
    black_id = ((white_black_high & 0x0F) << 16) | black_id_low
    pos += 5

    # EventID (19-bit), SiteID (19-bit), RoundID (18-bit) - 7 bytes
    event_site_rnd_high = data[pos]
    event_id_low = (data[pos + 1] << 8) | data[pos + 2]
    event_id = ((event_site_rnd_high & 0xE0) << 11) | event_id_low
    site_id_low = (data[pos + 3] << 8) | data[pos + 4]
    site_id = ((event_site_rnd_high & 0x1C) << 14) | site_id_low
    pos += 7  # Skip round_id too

    # Result (in var_counts, bits 12-15) - 2 bytes
    var_counts = (data[pos] << 8) | data[pos + 1]
    result = (var_counts >> 12) & 0x0F
    pos += 2

    # ECO code - 2 bytes
    eco_code = (data[pos] << 8) | data[pos + 1]
    pos += 2

    # Date (lower 20 bits of 4-byte packed date/eventdate)
    date = (
        (data[pos] << 24) | (data[pos + 1] << 16) | (data[pos + 2] << 8) | data[pos + 3]
    ) & 0xFFFFF
    pos += 4

    # White ELO (lower 12 bits) - 2 bytes
    white_elo = ((data[pos] << 8) | data[pos + 1]) & 0xFFF
    pos += 2

    # Black ELO (lower 12 bits) - 2 bytes
    black_elo = ((data[pos] << 8) | data[pos + 1]) & 0xFFF

    return (
        white_id,
        black_id,
        event_id,
        site_id,
        date,
        result,
        eco_code,
        white_elo,
        black_elo,
    )


def decode_index_entry(data: bytes, version: int) -> IndexEntry:
    """
    Decode a 47-byte (v4) or 46-byte (v3) index entry.

    Reference: scid/src/codec_scid4.cpp decodeIndexEntry()
    """
    ie = IndexEntry()
    pos = 0

    def read_one() -> int:
        nonlocal pos
        val = data[pos]
        pos += 1
        return val

    def read_two() -> int:
        nonlocal pos
        val = (data[pos] << 8) | data[pos + 1]
        pos += 2
        return val

    def read_four() -> int:
        nonlocal pos
        val = (
            (data[pos] << 24)
            | (data[pos + 1] << 16)
            | (data[pos + 2] << 8)
            | data[pos + 3]
        )
        pos += 4
        return val

    # Offset (4 bytes)
    ie.offset = read_four()

    # Length (2 bytes low + 1 byte with high bit and flags for v4)
    len_low = read_two()
    if version >= 400:
        len_flags = read_one()
        ie.length = ((len_flags & 0x80) << 9) | len_low
        custom_flags = (len_flags & 0x3F) << 16
    else:
        ie.length = len_low
        custom_flags = 0

    # Flags (2 bytes)
    flags = read_two()
    ie.flags = custom_flags | flags

    # WhiteID and BlackID (20-bit each, packed)
    white_black_high = read_one()
    white_id_low = read_two()
    ie.white_id = ((white_black_high & 0xF0) << 12) | white_id_low
    black_id_low = read_two()
    ie.black_id = ((white_black_high & 0x0F) << 16) | black_id_low

    # EventID (19-bit), SiteID (19-bit), RoundID (18-bit)
    event_site_rnd_high = read_one()
    event_id_low = read_two()
    ie.event_id = ((event_site_rnd_high & 0xE0) << 11) | event_id_low
    site_id_low = read_two()
    ie.site_id = ((event_site_rnd_high & 0x1C) << 14) | site_id_low
    round_id_low = read_two()
    ie.round_id = ((event_site_rnd_high & 0x03) << 16) | round_id_low

    # Variation/Comment/Nag counts + Result (2 bytes)
    var_counts = read_two()
    ie.variation_count = _decode_count(var_counts & 0x0F)
    ie.comment_count = _decode_count((var_counts >> 4) & 0x0F)
    ie.nag_count = _decode_count((var_counts >> 8) & 0x0F)
    ie.result = Result((var_counts >> 12) & 0x0F)

    # ECO code (2 bytes)
    ie.eco_code = read_two()

    # Date and EventDate (4 bytes packed)
    date_edate = read_four()
    ie.date = date_edate & 0xFFFFF

    # Event date is stored relative to game date
    edate_packed = date_edate >> 20
    eyear_offset = (edate_packed >> 9) & 0x07
    if eyear_offset == 0:
        ie.event_date = 0
    else:
        game_year = (ie.date >> 9) & 0x7FF
        event_year = game_year + eyear_offset - 4
        if event_year < 0:
            event_year = 0
        emonth = (edate_packed >> 5) & 0x0F
        eday = edate_packed & 0x1F
        ie.event_date = (event_year << 9) | (emonth << 5) | eday

    # White ELO + rating type (2 bytes)
    white_elo = read_two()
    ie.white_elo = white_elo & 0xFFF
    ie.white_rating_type = RatingType(white_elo >> 12)

    # Black ELO + rating type (2 bytes)
    black_elo = read_two()
    ie.black_elo = black_elo & 0xFFF
    ie.black_rating_type = RatingType(black_elo >> 12)

    # Final material signature + stored line code (4 bytes)
    final_mat = read_four()
    ie.final_mat_sig = final_mat & 0xFFFFFF
    ie.stored_line_code = final_mat >> 24

    # NumHalfMoves (8 bits) + HomePawnData[0] has high 2 bits of moves
    num_moves_low = read_one()
    pawn_data_0 = read_one()
    ie.num_half_moves = ((pawn_data_0 & 0xC0) << 2) | num_moves_low

    # HomePawnData (remaining 8 bytes)
    home_pawn = bytes([pawn_data_0 & 0x3F]) + data[pos : pos + 8]
    ie.home_pawn_data = home_pawn

    return ie


def _decode_count(raw: int) -> int:
    """
    Decode annotation count from 4-bit raw value.

    From indexentry.h DecodeCount():
    0-10 = exact, 11=15, 12=20, 13=30, 14=40, 15=50
    """
    count_codes = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30, 40, 50]
    return count_codes[raw & 0x0F]


class Scid4Database:
    """
    SCID version 4 database reader.

    Supports lazy loading for fast database opening. By default, only the header
    is read on open. Index entries and namebase are loaded on demand.

    Usage:
        # Default: lazy loading
        db = Scid4Database.open("games.si4")

        # Preload everything (current behavior, for full iteration)
        db = Scid4Database.open("games.si4", preload=True)

        # Preload just namebase (fast metadata access)
        db = Scid4Database.open("games.si4", preload_names=True)

        # Enable LRU cache for repeated random access
        db = Scid4Database.open("games.si4", cache_size=10000)

        for game in db:
            print(game.white, "vs", game.black)
    """

    def __init__(self):
        self.header: Optional[IndexHeader] = None
        self.namebase: Optional[NameBase] = None
        self._index_file: Optional[BinaryIO] = None
        self._index_mmap: Optional[mmap.mmap] = None
        self._game_file: Optional[BinaryIO] = None
        self._game_mmap: Optional[mmap.mmap] = None
        self._base_path: str = ""
        self._namebase_path: str = ""
        self._entry_size: int = INDEX_ENTRY_SIZE_V4
        # Cache for index entries (None = disabled, dict = LRU cache)
        self._index_cache: Optional[Dict[int, IndexEntry]] = None
        self._cache_size: int = 0
        # For preloaded mode: store all entries in a list
        self._preloaded_entries: Optional[List[IndexEntry]] = None
        # Lazy-built name indexes for fast search: name (lowercase) -> ID
        self._player_name_index: Optional[Dict[str, int]] = None
        self._event_name_index: Optional[Dict[str, int]] = None
        self._site_name_index: Optional[Dict[str, int]] = None
        # Cache for player ID -> game indices (built on first full scan)
        self._player_game_index: Optional[Dict[int, List[int]]] = None

    @staticmethod
    def open(
        filepath: str,
        preload: bool = False,
        preload_names: bool = False,
        cache_size: int = 0,
    ) -> "Scid4Database":
        """
        Open a SCID4 database.

        Args:
            filepath: Path to .si4 file (or base name without extension)
            preload: If True, load all index entries upfront (slower open, faster iteration)
            preload_names: If True, load namebase immediately (otherwise lazy-loaded)
            cache_size: Size of LRU cache for index entries (0 = disabled)

        Returns:
            Scid4Database instance ready for reading
        """
        db = Scid4Database()

        # Normalize path
        path = Path(filepath)
        if path.suffix == ".si4":
            base_path = path.with_suffix("")
        else:
            base_path = path

        db._base_path = str(base_path)

        index_path = str(base_path) + ".si4"
        db._namebase_path = str(base_path) + ".sn4"
        game_path = str(base_path) + ".sg4"

        # Open and read index header only
        db._index_file = open(index_path, "rb")
        db.header = read_index_header(db._index_file)

        # Validate version
        if db.header.version < SCID_OLDEST_VERSION or db.header.version > SCID_VERSION:
            raise ValueError(f"Unsupported SCID version: {db.header.version}")

        # Set entry size based on version
        db._entry_size = (
            INDEX_ENTRY_SIZE_V4 if db.header.version >= 400 else INDEX_ENTRY_SIZE_V3
        )

        # Memory-map the index file for lazy access
        try:
            db._index_mmap = mmap.mmap(
                db._index_file.fileno(), 0, access=mmap.ACCESS_READ
            )
        except ValueError:
            # Empty file - will handle in get_index_entry
            db._index_mmap = None

        # Set up caching if requested
        if cache_size > 0:
            db._cache_size = cache_size
            db._index_cache = {}

        # Preload namebase if requested
        if preload_names or preload:
            db._ensure_namebase_loaded()

        # Preload all index entries if requested
        if preload:
            db._preload_index_entries()

        # Open game file for reading game data
        db._game_file = open(game_path, "rb")
        try:
            db._game_mmap = mmap.mmap(
                db._game_file.fileno(), 0, access=mmap.ACCESS_READ
            )
        except ValueError:
            # Empty file or other issue - fall back to regular file access
            db._game_mmap = None

        return db

    def _ensure_namebase_loaded(self):
        """Load namebase on first access (lazy loading)"""
        if self.namebase is None:
            self.namebase = NameBase.read_from_file(self._namebase_path)

    def _preload_index_entries(self):
        """Load all index entries into memory (for preload mode)"""
        if self._preloaded_entries is not None:
            return  # Already preloaded

        self._preloaded_entries = []
        if self._index_mmap is None or self.header is None:
            return

        for i in range(self.header.num_games):
            offset = INDEX_HEADER_SIZE + (i * self._entry_size)
            entry_data = self._index_mmap[offset : offset + self._entry_size]
            ie = decode_index_entry(bytes(entry_data), self.header.version)
            self._preloaded_entries.append(ie)

    def preload_all(self):
        """Explicitly load all data after opening (namebase + all index entries)"""
        self._ensure_namebase_loaded()
        self._preload_index_entries()

    def preload_namebase(self):
        """Explicitly load just the namebase"""
        self._ensure_namebase_loaded()

    def clear_cache(self):
        """Clear the index entry cache"""
        if self._index_cache is not None:
            self._index_cache.clear()

    def close(self):
        """Close all open files"""
        if self._game_mmap:
            self._game_mmap.close()
            self._game_mmap = None
        if self._game_file:
            self._game_file.close()
            self._game_file = None
        if self._index_mmap:
            self._index_mmap.close()
            self._index_mmap = None
        if self._index_file:
            self._index_file.close()
            self._index_file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __len__(self) -> int:
        if self.header is None:
            return 0
        return self.header.num_games

    def __iter__(self) -> Iterator[Game]:
        """Iterate over all games with batch optimization"""
        # Use batch prefetching for efficient iteration
        BATCH_SIZE = 1000
        num_games = len(self)

        for batch_start in range(0, num_games, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, num_games)

            # Pre-fetch index entries for this batch
            entries = []
            for i in range(batch_start, batch_end):
                entries.append(self.get_index_entry(i))

            # Yield games from this batch
            for ie in entries:
                yield self._get_game_from_entry(ie)

    def __getitem__(self, index: int) -> Game:
        if index < 0 or index >= len(self):
            raise IndexError(f"Game index {index} out of range")
        return self.get_game(index)

    def get_index_entry(self, game_num: int) -> IndexEntry:
        """
        Get raw index entry for a game.

        Uses preloaded entries if available, otherwise decodes from mmap.
        Caches entries if cache_size > 0.
        """
        if game_num < 0 or game_num >= len(self):
            raise IndexError(f"Game index {game_num} out of range")

        # Check preloaded entries first
        if self._preloaded_entries is not None:
            return self._preloaded_entries[game_num]

        # Check cache
        if self._index_cache is not None and game_num in self._index_cache:
            return self._index_cache[game_num]

        # Decode from mmap
        if self._index_mmap is None or self.header is None:
            raise RuntimeError("Database not properly initialized")

        offset = INDEX_HEADER_SIZE + (game_num * self._entry_size)
        entry_data = self._index_mmap[offset : offset + self._entry_size]
        ie = decode_index_entry(bytes(entry_data), self.header.version)

        # Store in cache if enabled (simple LRU: evict oldest when full)
        if self._index_cache is not None:
            if len(self._index_cache) >= self._cache_size:
                # Remove oldest entry (first key in dict - Python 3.7+ preserves order)
                oldest_key = next(iter(self._index_cache))
                del self._index_cache[oldest_key]
            self._index_cache[game_num] = ie

        return ie

    def get_game_data(self, ie: IndexEntry) -> bytes:
        """Get raw game data bytes for an index entry"""
        if self._game_mmap:
            return bytes(self._game_mmap[ie.offset : ie.offset + ie.length])
        elif self._game_file:
            self._game_file.seek(ie.offset)
            return self._game_file.read(ie.length)
        return b""

    def _get_game_from_entry(self, ie: IndexEntry) -> Game:
        """
        Create a Game object from an IndexEntry.

        Internal method used by get_game and iteration.
        """
        # Ensure namebase is loaded before accessing names
        self._ensure_namebase_loaded()

        if self.namebase is None:
            raise RuntimeError("Failed to load namebase")

        # Create game with metadata from index entry
        game = Game(
            white=self.namebase.get_player(ie.white_id),
            black=self.namebase.get_player(ie.black_id),
            event=self.namebase.get_event(ie.event_id),
            site=self.namebase.get_site(ie.site_id),
            round=self.namebase.get_round(ie.round_id),
            date=date_to_python(ie.date),
            event_date=date_to_python(ie.event_date),
            date_raw=ie.date,
            event_date_raw=ie.event_date,
            result=ie.result,
            white_elo=ie.white_elo,
            black_elo=ie.black_elo,
            white_rating_type=ie.white_rating_type,
            black_rating_type=ie.black_rating_type,
            eco=ie.get_eco_string(),
            num_half_moves=ie.num_half_moves,
            is_chess960=ie.is_chess960,
            _index_entry=ie,
        )

        # Get and decode game data (tags, position, moves)
        if ie.length > 0:
            game_data = self.get_game_data(ie)
            self._decode_game_data(game, game_data, ie)

        return game

    def get_event(self, event_id):
        return self.get_event(event_id)

    def get_game(self, game_num: int) -> Game:
        """
        Get a fully decoded Game object.

        Args:
            game_num: 0-based game index

        Returns:
            Game object with all metadata and moves
        """
        ie = self.get_index_entry(game_num)
        return self._get_game_from_entry(ie)

    # -------------------------------------------------------------------------
    # Search optimization: name indexes
    # -------------------------------------------------------------------------

    def _ensure_player_index(self):
        """Build player name -> ID index on first use"""
        if self._player_name_index is not None:
            return
        self._ensure_namebase_loaded()
        if self.namebase is None:
            return
        self._player_name_index = {
            name.lower(): pid
            for pid, name in enumerate(self.namebase.names[NameType.PLAYER])
        }

    def _ensure_event_index(self):
        """Build event name -> ID index on first use"""
        if self._event_name_index is not None:
            return
        self._ensure_namebase_loaded()
        if self.namebase is None:
            return
        self._event_name_index = {
            name.lower(): eid
            for eid, name in enumerate(self.namebase.names[NameType.EVENT])
        }

    def _ensure_site_index(self):
        """Build site name -> ID index on first use"""
        if self._site_name_index is not None:
            return
        self._ensure_namebase_loaded()
        if self.namebase is None:
            return
        self._site_name_index = {
            name.lower(): sid
            for sid, name in enumerate(self.namebase.names[NameType.SITE])
        }

    def _find_matching_player_ids(self, search_term: str) -> Set[int]:
        """Find all player IDs where name contains search_term (case-insensitive)"""
        self._ensure_player_index()
        if self._player_name_index is None:
            return set()
        term = search_term.lower()
        return {pid for name, pid in self._player_name_index.items() if term in name}

    def _find_matching_event_ids(self, search_term: str) -> Set[int]:
        """Find all event IDs where name contains search_term (case-insensitive)"""
        self._ensure_event_index()
        if self._event_name_index is None:
            return set()
        term = search_term.lower()
        return {eid for name, eid in self._event_name_index.items() if term in name}

    def _find_matching_site_ids(self, search_term: str) -> Set[int]:
        """Find all site IDs where name contains search_term (case-insensitive)"""
        self._ensure_site_index()
        if self._site_name_index is None:
            return set()
        term = search_term.lower()
        return {sid for name, sid in self._site_name_index.items() if term in name}

    def _ensure_player_game_index(self):
        """
        Build player ID -> game indices mapping.

        This scans all games once and maps each player ID to the list of
        game indices where they played. Enables instant player lookups after
        the first scan.
        """
        if self._player_game_index is not None:
            return

        if self._index_mmap is None or self.header is None:
            return

        from collections import defaultdict

        player_games: Dict[int, List[int]] = defaultdict(list)

        version = self.header.version
        entry_size = self._entry_size
        header_size = INDEX_HEADER_SIZE
        num_games = len(self)
        index_mmap = self._index_mmap

        for game_num in range(num_games):
            offset = header_size + (game_num * entry_size)
            data = index_mmap[offset : offset + entry_size]

            # Extract just white_id and black_id (first two fields)
            fields = extract_search_fields(data, version)
            white_id, black_id = fields[0], fields[1]

            player_games[white_id].append(game_num)
            if black_id != white_id:
                player_games[black_id].append(game_num)

        self._player_game_index = dict(player_games)

    def _get_games_for_player_ids(self, player_ids: Set[int]) -> Set[int]:
        """Get all game indices where any of the player IDs played."""
        self._ensure_player_game_index()

        if self._player_game_index is None:
            return set()

        game_indices: Set[int] = set()
        for pid in player_ids:
            if pid in self._player_game_index:
                game_indices.update(self._player_game_index[pid])

        return game_indices

    def search(self, **criteria) -> Iterator[Game]:
        """
        Search for games matching the given criteria.

        This is an optimized search that filters on IndexEntry fields first
        (fast integer comparisons), then only decodes games that match.

        For player searches, builds a player->games index on first use for
        instant subsequent lookups.

        Supported criteria:
            white: str - White player name (partial match, case-insensitive)
            black: str - Black player name (partial match, case-insensitive)
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
            result: Result - Game result (exact match)
            eco: str - ECO code prefix
            min_elo: int - Minimum rating for either player

        Yields:
            Game objects matching all criteria
        """
        # Build ID sets for name-based criteria (only if that criterion is used)
        white_ids: Optional[Set[int]] = None
        black_ids: Optional[Set[int]] = None
        player_ids: Optional[Set[int]] = None
        event_ids: Optional[Set[int]] = None
        site_ids: Optional[Set[int]] = None

        # Handle name-based searches (slower - requires name index build)
        if criteria.get("white"):
            white_ids = self._find_matching_player_ids(criteria["white"])
            if not white_ids:
                return  # No matching players, no results

        if criteria.get("black"):
            black_ids = self._find_matching_player_ids(criteria["black"])
            if not black_ids:
                return

        if criteria.get("player"):
            player_ids = self._find_matching_player_ids(criteria["player"])
            if not player_ids:
                return

        if criteria.get("event"):
            event_ids = self._find_matching_event_ids(criteria["event"])
            if not event_ids:
                return

        if criteria.get("site"):
            site_ids = self._find_matching_site_ids(criteria["site"])
            if not site_ids:
                return

        # Handle ID-based searches (fastest - direct integer comparison)
        if "white_id" in criteria:
            white_id = criteria["white_id"]
            white_ids = {white_id} if white_ids is None else white_ids & {white_id}
            if not white_ids:
                return

        if "black_id" in criteria:
            black_id = criteria["black_id"]
            black_ids = {black_id} if black_ids is None else black_ids & {black_id}
            if not black_ids:
                return

        if "player_id" in criteria:
            pid = criteria["player_id"]
            player_ids = {pid} if player_ids is None else player_ids & {pid}
            if not player_ids:
                return

        if "event_id" in criteria:
            eid = criteria["event_id"]
            event_ids = {eid} if event_ids is None else event_ids & {eid}
            if not event_ids:
                return

        if "site_id" in criteria:
            sid = criteria["site_id"]
            site_ids = {sid} if site_ids is None else site_ids & {sid}
            if not site_ids:
                return

        # Direct IndexEntry filters (no name lookup needed)
        year = criteria.get("year")
        year_min = criteria.get("year_min")
        year_max = criteria.get("year_max")
        result_filter = criteria.get("result")
        eco_prefix = criteria.get("eco", "").upper()
        min_elo = criteria.get("min_elo", 0)

        # Check if we can use the fast player game index
        # Only use it for pure player searches (no other criteria)
        has_other_criteria = (
            year
            or year_min
            or year_max
            or result_filter
            or eco_prefix
            or min_elo
            or event_ids
            or site_ids
        )

        # Fast path: player-only search with cached index
        if (
            player_ids is not None
            and not has_other_criteria
            and white_ids is None
            and black_ids is None
        ):
            game_indices = self._get_games_for_player_ids(player_ids)
            for game_num in sorted(game_indices):
                yield self.get_game(game_num)
            return

        # Fast path: white-only search with cached index
        if (
            white_ids is not None
            and not has_other_criteria
            and player_ids is None
            and black_ids is None
        ):
            # Need to filter for white only, so we scan but use the index to limit candidates
            self._ensure_player_game_index()
            if self._player_game_index:
                candidate_games = self._get_games_for_player_ids(white_ids)
                for game_num in sorted(candidate_games):
                    ie = self.get_index_entry(game_num)
                    if ie.white_id in white_ids:
                        yield self._get_game_from_entry(ie)
                return

        # Convert result enum to int for fast comparison
        result_int = result_filter.value if result_filter is not None else None

        # Convert ECO prefix to numeric range for fast comparison
        eco_code_min = eco_code_max = None
        if eco_prefix:
            eco_code_min, eco_code_max = self._eco_prefix_to_range(eco_prefix)

        # Determine which games to scan
        if self._index_mmap is None or self.header is None:
            return

        version = self.header.version
        entry_size = self._entry_size
        header_size = INDEX_HEADER_SIZE
        index_mmap = self._index_mmap

        # If we have player criteria and the index is built, use it to narrow candidates
        candidate_games: Optional[Set[int]] = None
        if player_ids is not None and self._player_game_index is not None:
            candidate_games = self._get_games_for_player_ids(player_ids)
        elif white_ids is not None and self._player_game_index is not None:
            candidate_games = self._get_games_for_player_ids(white_ids)
        elif black_ids is not None and self._player_game_index is not None:
            candidate_games = self._get_games_for_player_ids(black_ids)

        # If no candidate narrowing, scan all games
        if candidate_games is None:
            games_to_scan = range(len(self))
        else:
            games_to_scan = sorted(candidate_games)

        for game_num in games_to_scan:
            offset = header_size + (game_num * entry_size)
            data = index_mmap[offset : offset + entry_size]

            # Fast extraction of search fields
            (
                white_id,
                black_id,
                event_id,
                site_id,
                date,
                result,
                eco_code,
                white_elo,
                black_elo,
            ) = extract_search_fields(data, version)

            # Filter on player IDs
            if white_ids is not None and white_id not in white_ids:
                continue
            if black_ids is not None and black_id not in black_ids:
                continue
            if player_ids is not None:
                if white_id not in player_ids and black_id not in player_ids:
                    continue

            # Filter on event/site IDs
            if event_ids is not None and event_id not in event_ids:
                continue
            if site_ids is not None and site_id not in site_ids:
                continue

            # Filter on date (extract year from packed date)
            if year or year_min or year_max:
                game_year = (date >> 9) & 0x7FF
                if year and game_year != year:
                    continue
                if year_min and game_year < year_min:
                    continue
                if year_max and game_year > year_max:
                    continue

            # Filter on result
            if result_int is not None and result != result_int:
                continue

            # Filter on ECO (numeric comparison)
            if eco_code_min is not None and eco_code_max is not None:
                if eco_code < eco_code_min or eco_code > eco_code_max:
                    continue

            # Filter on ELO
            if min_elo > 0:
                if white_elo < min_elo and black_elo < min_elo:
                    continue

            # Passed all filters - get full index entry and decode game
            ie = self.get_index_entry(game_num)
            yield self._get_game_from_entry(ie)

    def _eco_prefix_to_range(self, prefix: str) -> Tuple[int, int]:
        """
        Convert an ECO prefix (e.g., "B", "B9", "B90") to a numeric range.

        SCID ECO encoding: ((letter - 'A') * 100 + number) * 4 + subcode
        E.g., B90 = (1 * 100 + 90) * 4 = 760 (without subcode)
              B90a = 760 + 1 = 761
        """
        if not prefix:
            return (0, 2000)  # All ECO codes (E99d = 499*4+3 = 1999)

        prefix = prefix.upper()
        letter = prefix[0]
        if letter < "A" or letter > "E":
            return (0, 2000)

        letter_val = ord(letter) - ord("A")

        if len(prefix) == 1:
            # Just letter: e.g., "B" -> B00-B99 (all subcodes)
            base_min = (letter_val * 100 + 0) * 4
            base_max = (letter_val * 100 + 99) * 4 + 3
            return (base_min, base_max)
        elif len(prefix) == 2:
            # Letter + one digit: e.g., "B9" -> B90-B99 (all subcodes)
            try:
                digit = int(prefix[1])
                base_min = (letter_val * 100 + digit * 10) * 4
                base_max = (letter_val * 100 + digit * 10 + 9) * 4 + 3
                return (base_min, base_max)
            except ValueError:
                return (0, 2000)
        else:
            # Full code: e.g., "B90" -> B90 with all subcodes (B90, B90a, B90b, B90c, B90d)
            try:
                num = int(prefix[1:3])
                base = (letter_val * 100 + num) * 4
                return (base, base + 3)  # Include all subcodes
            except ValueError:
                return (0, 2000)

    def _decode_game_data(self, game: Game, data: bytes, ie: IndexEntry):
        """
        Decode game data from .sg4 file.

        Game data consists of:
        1. Extra tags section (terminated by 0x00)
        2. Start position flags + optional FEN
        3. Encoded moves

        Reference: scid/src/bytebuf.h
        """
        from .gamedata import decode_game_data

        decode_game_data(game, data, ie)


# Helper functions for reading big-endian integers
def _read_two_bytes(f: BinaryIO) -> int:
    """Read 2-byte big-endian integer"""
    data = f.read(2)
    return (data[0] << 8) | data[1]


def _read_three_bytes(f: BinaryIO) -> int:
    """Read 3-byte big-endian integer"""
    data = f.read(3)
    return (data[0] << 16) | (data[1] << 8) | data[2]


def _read_four_bytes(f: BinaryIO) -> int:
    """Read 4-byte big-endian integer"""
    data = f.read(4)
    return (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]
