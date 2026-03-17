"""
SCID5 format codec.

Handles reading of SCID version 5 databases consisting of:
- .si5 - Index file (56-byte records per game, no header, little-endian)
- .sn5 - NameBase file (varint-encoded strings)
- .sg5 - Game file (same format as SCID4)

SCID5 differences from SCID4:
- Index entries are 56 bytes (vs 47) with different packing
- Little-endian encoding (vs big-endian)
- No index header - just raw records
- NameBase uses varint encoding (vs front-coding)
- Larger limits for IDs and offsets

Reference: scid/src/codec_scid5.h
"""

import struct
import mmap
from pathlib import Path
from typing import List, Dict, Optional, Iterator, BinaryIO, Set, Tuple

from .types import Result, RatingType, NameType
from .game import IndexEntry, Game, Move
from .date import date_to_python


# Constants from codec_scid5.h
INDEX_ENTRY_SIZE = 56

# Limits
LIMIT_GAMEOFFSET = 1 << 47
LIMIT_GAMELEN = 1 << 17
LIMIT_NUMGAMES = (1 << 32) - 2
LIMIT_UNIQUENAMES_PLAYER_EVENT = 1 << 28
LIMIT_UNIQUENAMES_ROUND = 1 << 31
LIMIT_UNIQUENAMES_SITE = 1 << 32

# Name types (matches scid's enum, plus 4 for db info)
NAME_INFO = 4


class NameBase5:
    """
    NameBase for SCID5 format.

    In SCID5, names are stored as varint-encoded records:
    - varint: (length << 3) | name_type
    - data: length bytes

    The name type is stored in the lower 3 bits of the varint.
    """

    def __init__(self):
        self.names: Dict[NameType, List[str]] = {
            NameType.PLAYER: [],
            NameType.EVENT: [],
            NameType.SITE: [],
            NameType.ROUND: [],
        }
        self.db_info: Dict[str, str] = {}

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
    def read_from_file(filepath: str) -> "NameBase5":
        """
        Read a SCID5 NameBase file (.sn5).

        File format: sequence of varint-encoded records
        - varint: (length << 3) | type
        - data: length bytes (the name string)
        """
        nb = NameBase5()

        with open(filepath, "rb") as f:
            data = f.read()

        pos = 0
        while pos < len(data):
            # Read varint
            varint, pos = _read_varint(data, pos)
            if varint is None:
                break

            name_type = varint & 0x07
            length = varint >> 3

            if pos + length > len(data):
                break

            name = data[pos : pos + length].decode("utf-8", errors="replace")
            pos += length

            if name_type < 4:
                # Regular name type
                nt = NameType(name_type)
                nb.names[nt].append(name)
            elif name_type == NAME_INFO:
                # Database info (key-value in the string)
                # Format: "key" followed immediately by "value"
                # Common keys: type, description, autoload, flag1-6
                for key in [
                    "type",
                    "description",
                    "autoload",
                    "flag1",
                    "flag2",
                    "flag3",
                    "flag4",
                    "flag5",
                    "flag6",
                ]:
                    if name.startswith(key):
                        nb.db_info[key] = name[len(key) :]
                        break

        return nb


def _read_varint(data: bytes, pos: int) -> tuple:
    """
    Read a varint from data at position pos.

    Returns (value, new_position) or (None, pos) on error.
    """
    result = 0
    shift = 0

    while pos < len(data) and shift < 64:
        byte = data[pos]
        pos += 1

        result |= (byte & 0x7F) << shift

        if byte < 128:
            return result, pos

        shift += 7

    return None, pos


def extract_search_fields_v5(
    data: bytes,
) -> Tuple[int, int, int, int, int, int, int, int, int]:
    """
    Fast extraction of search-relevant fields from a SCID5 index entry.

    Returns:
        Tuple of (white_id, black_id, event_id, site_id, date, result, eco_code, white_elo, black_elo)

    This is faster than full decode_index_entry_v5() when you only need these fields.
    """
    # Word 0: nComments(4) + whiteID(28)
    val = struct.unpack_from("<I", data, 0)[0]
    white_id = val & 0x0FFFFFFF

    # Word 1: nVariations(4) + blackID(28)
    val = struct.unpack_from("<I", data, 4)[0]
    black_id = val & 0x0FFFFFFF

    # Word 2: nNags(4) + eventID(28)
    val = struct.unpack_from("<I", data, 8)[0]
    event_id = val & 0x0FFFFFFF

    # Word 3: siteID(32)
    site_id = struct.unpack_from("<I", data, 12)[0]

    # Word 5: whiteElo(12) + date(20)
    val = struct.unpack_from("<I", data, 20)[0]
    white_elo = val >> 20
    date = val & 0xFFFFF

    # Word 6: blackElo(12) + eventDate(20)
    val = struct.unpack_from("<I", data, 24)[0]
    black_elo = val >> 20

    # Word 11: (homePawnCount(8) + ratingTypes(6) + result(2))(16) + ecoCode(16)
    val = struct.unpack_from("<I", data, 44)[0]
    result = (val >> 16) & 0x03
    eco_code = val & 0xFFFF

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


def decode_index_entry_v5(data: bytes) -> IndexEntry:
    """
    Decode a 56-byte SCID5 index entry.

    SCID5 uses little-endian uint32_t values with bit-packed fields.

    Reference: scid/src/codec_scid5.h decode_IndexEntry()
    """
    ie = IndexEntry()

    # Helper to read little-endian uint32
    def u32(offset: int) -> int:
        return struct.unpack_from("<I", data, offset)[0]

    # Helper to unpack high bits and low bits from a uint32
    def unpack(val: int, high_bits: int):
        high = val >> (32 - high_bits)
        low = (val << high_bits) >> high_bits
        return high, low

    # Word 0: nComments(4) + whiteID(28)
    val = u32(0)
    comment_count, white_id = unpack(val, 4)
    ie.comment_count = _decode_count(comment_count)
    ie.white_id = white_id

    # Word 1: nVariations(4) + blackID(28)
    val = u32(4)
    variation_count, black_id = unpack(val, 4)
    ie.variation_count = _decode_count(variation_count)
    ie.black_id = black_id

    # Word 2: nNags(4) + eventID(28)
    val = u32(8)
    nag_count, event_id = unpack(val, 4)
    ie.nag_count = _decode_count(nag_count)
    ie.event_id = event_id

    # Word 3: siteID(32)
    ie.site_id = u32(12)

    # Word 4: chess960(1) + roundID(31)
    val = u32(16)
    chess960, round_id = unpack(val, 1)
    ie.is_chess960 = bool(chess960)
    ie.round_id = round_id

    # Word 5: whiteElo(12) + date(20)
    val = u32(20)
    white_elo, date = unpack(val, 12)
    ie.white_elo = white_elo
    ie.date = date

    # Word 6: blackElo(12) + eventDate(20)
    val = u32(24)
    black_elo, event_date = unpack(val, 12)
    ie.black_elo = black_elo
    ie.event_date = event_date

    # Word 7: numHalfMoves(10) + flags(22)
    val = u32(28)
    num_half_moves, flags = unpack(val, 10)
    ie.num_half_moves = num_half_moves
    ie.flags = flags

    # Word 8: gameDataSize(17) + offset_high(15)
    val = u32(32)
    game_data_size, offset_high = unpack(val, 17)
    ie.length = game_data_size

    # Word 9: offset_low(32)
    offset_low = u32(36)
    ie.offset = (offset_high << 32) | offset_low

    # Word 10: storedLineCode(8) + finalMatSig(24)
    val = u32(40)
    stored_line_code, final_mat_sig = unpack(val, 8)
    ie.stored_line_code = stored_line_code
    ie.final_mat_sig = final_mat_sig

    # Word 11: (homePawnCount(8) + ratingTypes(6) + result(2))(16) + ecoCode(16)
    val = u32(44)
    packed, eco_code = unpack(val, 16)
    home_pawn_count = packed >> 8
    ie.white_rating_type = RatingType((packed >> 5) & 0x07)
    ie.black_rating_type = RatingType((packed >> 2) & 0x07)
    ie.result = Result(packed & 0x03)
    ie.eco_code = eco_code

    # Bytes 48-55: home pawn data
    ie.home_pawn_data = bytes([home_pawn_count]) + data[48:56]

    return ie


def _decode_count(raw: int) -> int:
    """Decode annotation count from 4-bit raw value."""
    count_codes = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30, 40, 50]
    return count_codes[raw & 0x0F]


class Scid5Database:
    """
    SCID version 5 database reader.

    Supports lazy loading for fast database opening. By default, only the
    file size is checked on open. Index entries and namebase are loaded on demand.

    Usage:
        # Default: lazy loading (instant open)
        db = Scid5Database.open("games.si5")

        # Preload everything (for full iteration)
        db = Scid5Database.open("games.si5", preload=True)

        # Preload just namebase (fast metadata access)
        db = Scid5Database.open("games.si5", preload_names=True)

        # Enable LRU cache for repeated random access
        db = Scid5Database.open("games.si5", cache_size=10000)

        for game in db:
            print(game.white, "vs", game.black)
    """

    def __init__(self):
        self.namebase: Optional[NameBase5] = None
        self._index_file: Optional[BinaryIO] = None
        self._index_mmap: Optional[mmap.mmap] = None
        self._game_file: Optional[BinaryIO] = None
        self._game_mmap: Optional[mmap.mmap] = None
        self._base_path: str = ""
        self._namebase_path: str = ""
        self._num_games: int = 0
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

    @property
    def description(self) -> str:
        """Get database description"""
        self._ensure_namebase_loaded()
        if self.namebase:
            return self.namebase.db_info.get("description", "")
        return ""

    @staticmethod
    def open(
        filepath: str,
        preload: bool = False,
        preload_names: bool = False,
        cache_size: int = 0,
    ) -> "Scid5Database":
        """
        Open a SCID5 database.

        Args:
            filepath: Path to .si5 file (or base name without extension)
            preload: If True, load all index entries upfront (slower open, faster iteration)
            preload_names: If True, load namebase immediately (otherwise lazy-loaded)
            cache_size: Size of LRU cache for index entries (0 = disabled)

        Returns:
            Scid5Database instance ready for reading
        """
        db = Scid5Database()

        # Normalize path
        path = Path(filepath)
        if path.suffix == ".si5":
            base_path = path.with_suffix("")
        else:
            base_path = path

        db._base_path = str(base_path)

        index_path = str(base_path) + ".si5"
        db._namebase_path = str(base_path) + ".sn5"
        game_path = str(base_path) + ".sg5"

        # Open index file and get number of games from file size
        db._index_file = open(index_path, "rb")

        # Get file size to determine number of games
        db._index_file.seek(0, 2)  # Seek to end
        file_size = db._index_file.tell()
        db._index_file.seek(0)  # Seek back to start

        if file_size % INDEX_ENTRY_SIZE != 0:
            raise ValueError(f"Invalid index file size: {file_size}")

        db._num_games = file_size // INDEX_ENTRY_SIZE

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
            db._game_mmap = None

        return db

    def _ensure_namebase_loaded(self):
        """Load namebase on first access (lazy loading)"""
        if self.namebase is None:
            self.namebase = NameBase5.read_from_file(self._namebase_path)

    def _preload_index_entries(self):
        """Load all index entries into memory (for preload mode)"""
        if self._preloaded_entries is not None:
            return  # Already preloaded

        self._preloaded_entries = []
        if self._index_mmap is None:
            return

        for i in range(self._num_games):
            offset = i * INDEX_ENTRY_SIZE
            entry_data = self._index_mmap[offset : offset + INDEX_ENTRY_SIZE]
            ie = decode_index_entry_v5(bytes(entry_data))
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
        return self._num_games

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
        if self._index_mmap is None:
            raise RuntimeError("Database not properly initialized")

        offset = game_num * INDEX_ENTRY_SIZE
        entry_data = self._index_mmap[offset : offset + INDEX_ENTRY_SIZE]
        ie = decode_index_entry_v5(bytes(entry_data))

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

        # Decode game data
        if ie.length > 0:
            game_data = self.get_game_data(ie)
            from .gamedata import decode_game_data

            decode_game_data(game, game_data, ie)

        return game

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

        if self._index_mmap is None:
            return

        from collections import defaultdict

        player_games: Dict[int, List[int]] = defaultdict(list)

        num_games = len(self)
        index_mmap = self._index_mmap

        for game_num in range(num_games):
            offset = game_num * INDEX_ENTRY_SIZE
            data = index_mmap[offset : offset + INDEX_ENTRY_SIZE]

            # Extract just white_id and black_id
            fields = extract_search_fields_v5(data)
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
        if self._index_mmap is None:
            return

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
            offset = game_num * INDEX_ENTRY_SIZE
            data = index_mmap[offset : offset + INDEX_ENTRY_SIZE]

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
            ) = extract_search_fields_v5(data)

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
        """
        if not prefix:
            return (0, 2000)

        prefix = prefix.upper()
        letter = prefix[0]
        if letter < "A" or letter > "E":
            return (0, 2000)

        letter_val = ord(letter) - ord("A")

        if len(prefix) == 1:
            base_min = (letter_val * 100 + 0) * 4
            base_max = (letter_val * 100 + 99) * 4 + 3
            return (base_min, base_max)
        elif len(prefix) == 2:
            try:
                digit = int(prefix[1])
                base_min = (letter_val * 100 + digit * 10) * 4
                base_max = (letter_val * 100 + digit * 10 + 9) * 4 + 3
                return (base_min, base_max)
            except ValueError:
                return (0, 2000)
        else:
            try:
                num = int(prefix[1:3])
                base = (letter_val * 100 + num) * 4
                return (base, base + 3)
            except ValueError:
                return (0, 2000)
