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
from typing import List, Dict, Optional, Iterator, BinaryIO

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

    Usage:
        db = Scid5Database.open("games.si5")
        for game in db:
            print(game.white, "vs", game.black)
    """

    def __init__(self):
        self.namebase: Optional[NameBase5] = None
        self.index_entries: List[IndexEntry] = []
        self._index_file: Optional[BinaryIO] = None
        self._game_file: Optional[BinaryIO] = None
        self._game_mmap: Optional[mmap.mmap] = None
        self._base_path: str = ""

    @property
    def description(self) -> str:
        """Get database description"""
        if self.namebase:
            return self.namebase.db_info.get("description", "")
        return ""

    @staticmethod
    def open(filepath: str) -> "Scid5Database":
        """
        Open a SCID5 database.

        Args:
            filepath: Path to .si5 file (or base name without extension)

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
        namebase_path = str(base_path) + ".sn5"
        game_path = str(base_path) + ".sg5"

        # Read namebase
        db.namebase = NameBase5.read_from_file(namebase_path)

        # Open and read index file
        db._index_file = open(index_path, "rb")

        # Get file size to determine number of games
        db._index_file.seek(0, 2)  # Seek to end
        file_size = db._index_file.tell()
        db._index_file.seek(0)  # Seek back to start

        if file_size % INDEX_ENTRY_SIZE != 0:
            raise ValueError(f"Invalid index file size: {file_size}")

        num_games = file_size // INDEX_ENTRY_SIZE

        # Read all index entries
        for _ in range(num_games):
            entry_data = db._index_file.read(INDEX_ENTRY_SIZE)
            if len(entry_data) < INDEX_ENTRY_SIZE:
                break
            ie = decode_index_entry_v5(entry_data)
            db.index_entries.append(ie)

        # Open game file for reading game data
        db._game_file = open(game_path, "rb")
        try:
            db._game_mmap = mmap.mmap(
                db._game_file.fileno(), 0, access=mmap.ACCESS_READ
            )
        except ValueError:
            db._game_mmap = None

        return db

    def close(self):
        """Close all open files"""
        if self._game_mmap:
            self._game_mmap.close()
            self._game_mmap = None
        if self._game_file:
            self._game_file.close()
            self._game_file = None
        if self._index_file:
            self._index_file.close()
            self._index_file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __len__(self) -> int:
        return len(self.index_entries)

    def __iter__(self) -> Iterator[Game]:
        for i in range(len(self)):
            yield self[i]

    def __getitem__(self, index: int) -> Game:
        if index < 0 or index >= len(self.index_entries):
            raise IndexError(f"Game index {index} out of range")
        return self.get_game(index)

    def get_index_entry(self, game_num: int) -> IndexEntry:
        """Get raw index entry for a game"""
        return self.index_entries[game_num]

    def get_game_data(self, ie: IndexEntry) -> bytes:
        """Get raw game data bytes for an index entry"""
        if self._game_mmap:
            return bytes(self._game_mmap[ie.offset : ie.offset + ie.length])
        elif self._game_file:
            self._game_file.seek(ie.offset)
            return self._game_file.read(ie.length)
        return b""

    def get_game(self, game_num: int) -> Game:
        """
        Get a fully decoded Game object.
        """
        ie = self.index_entries[game_num]

        nb = self.namebase
        if nb is None:
            raise RuntimeError("Database not properly initialized")

        game = Game(
            white=nb.get_player(ie.white_id),
            black=nb.get_player(ie.black_id),
            event=nb.get_event(ie.event_id),
            site=nb.get_site(ie.site_id),
            round=nb.get_round(ie.round_id),
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
