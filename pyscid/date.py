"""
Date encoding/decoding for SCID database format.

SCID stores dates in a 20-bit packed format:
- Bits 0-4: Day (1-31, 0 = unknown)
- Bits 5-8: Month (1-12, 0 = unknown)
- Bits 9-19: Year (0-2047, 0 = unknown)

Formula: date = (year << 9) | (month << 5) | day

Reference: scid/src/date.h
"""

from datetime import date as Date
from typing import Optional, Tuple

# Bit shift constants (from date.h)
YEAR_SHIFT = 9
MONTH_SHIFT = 5
DAY_SHIFT = 0

YEAR_MAX = 2047  # 2^11 - 1

ZERO_DATE = 0


def decode_date(packed: int) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """
    Decode a packed SCID date into (year, month, day) tuple.

    Returns None for unknown components (stored as 0 in SCID).

    Args:
        packed: 20-bit packed date value

    Returns:
        Tuple of (year, month, day) where None indicates unknown
    """
    year = (packed >> YEAR_SHIFT) & 0x7FF  # 11 bits
    month = (packed >> MONTH_SHIFT) & 0x0F  # 4 bits
    day = packed & 0x1F  # 5 bits

    return (
        year if year != 0 else None,
        month if month != 0 else None,
        day if day != 0 else None,
    )


def encode_date(
    year: Optional[int] = None, month: Optional[int] = None, day: Optional[int] = None
) -> int:
    """
    Encode a date into SCID's packed 20-bit format.

    Args:
        year: Year (0-2047) or None for unknown
        month: Month (1-12) or None for unknown
        day: Day (1-31) or None for unknown

    Returns:
        20-bit packed date value
    """
    y = 0 if year is None else min(max(0, year), YEAR_MAX)
    m = 0 if month is None else min(max(0, month), 12)
    d = 0 if day is None else min(max(0, day), 31)

    return (y << YEAR_SHIFT) | (m << MONTH_SHIFT) | d


def date_to_python(packed: int) -> Optional[Date]:
    """
    Convert a packed SCID date to a Python date object.

    Returns None if any component is unknown or invalid.

    Args:
        packed: 20-bit packed date value

    Returns:
        Python date object or None if date is incomplete/invalid
    """
    year, month, day = decode_date(packed)

    if year is None or month is None or day is None:
        return None

    try:
        return Date(year, month, day)
    except ValueError:
        return None


def python_to_date(d: Optional[Date]) -> int:
    """
    Convert a Python date object to SCID's packed format.

    Args:
        d: Python date object or None

    Returns:
        20-bit packed date value (ZERO_DATE if None)
    """
    if d is None:
        return ZERO_DATE
    return encode_date(d.year, d.month, d.day)


def date_to_string(packed: int) -> str:
    """
    Convert a packed date to PGN format string (YYYY.MM.DD).

    Unknown components are replaced with '??' (matches SCID's date_DecodeToString).

    Args:
        packed: 20-bit packed date value

    Returns:
        String in format "YYYY.MM.DD" with ?? for unknown parts
    """
    year, month, day = decode_date(packed)

    year_str = f"{year:04d}" if year is not None else "????"
    month_str = f"{month:02d}" if month is not None else "??"
    day_str = f"{day:02d}" if day is not None else "??"

    return f"{year_str}.{month_str}.{day_str}"


def string_to_date(s: str) -> int:
    """
    Parse a PGN date string to SCID's packed format.

    Accepts formats like "YYYY.MM.DD", "YYYY.M.D", with '?' for unknowns.

    Args:
        s: Date string in PGN format

    Returns:
        20-bit packed date value
    """
    if not s:
        return ZERO_DATE

    parts = s.split(".")

    def parse_part(part: str, max_val: int) -> Optional[int]:
        if not part or "?" in part:
            return None
        try:
            val = int(part)
            return val if 0 < val <= max_val else None
        except ValueError:
            return None

    year = None
    month = None
    day = None

    if len(parts) >= 1:
        try:
            y = int(parts[0])
            if 0 < y <= YEAR_MAX:
                year = y
        except ValueError:
            pass

    if len(parts) >= 2:
        month = parse_part(parts[1], 12)

    if len(parts) >= 3:
        day = parse_part(parts[2], 31)

    return encode_date(year, month, day)


def is_partial_date(packed: int) -> bool:
    """
    Check if a date has any unknown components.

    Args:
        packed: 20-bit packed date value

    Returns:
        True if year, month, or day is unknown
    """
    year, month, day = decode_date(packed)
    return year is None or month is None or day is None
