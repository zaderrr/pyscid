"""
NameBase interface for browsing database names.

Provides convenient access to all unique names (players, events, sites, rounds)
stored in the SCID namebase without requiring game loading.
"""

from dataclasses import dataclass
from typing import List, TYPE_CHECKING

from .types import NameType

if TYPE_CHECKING:
    from .scid4 import Scid4Database
    from .scid5 import Scid5Database


@dataclass
class NameEntry:
    """
    A single name entry from the NameBase.

    Attributes:
        id: The name ID (index in namebase) - use for fast ID-based searches
        name: The actual name string
    """

    id: int
    name: str


class NameBaseInterface:
    """
    Interface for browsing database names.

    Provides access to all unique names stored in the SCID namebase:
    - players: All player names (typically 100K-500K+ entries)
    - events: All event names
    - sites: All site names
    - rounds: All round names

    Each entry includes an ID that can be used for fast ID-based searches.

    Usage:
        # Browse all players
        for player in db.namebase.players:
            print(f"ID {player.id}: {player.name}")

        # Find specific player
        magnus = [p for p in db.namebase.players if "Carlsen, Magnus" in p.name][0]

        # Fast search by ID
        games = list(db.search(white_id=magnus.id))

    Note: Only available for SCID4 and SCID5 formats (not PGN).
    """

    def __init__(self, backend: "Scid4Database | Scid5Database"):
        """
        Initialize namebase interface.

        Args:
            backend: The SCID database backend (Scid4Database or Scid5Database)
        """
        self._backend = backend

    @property
    def players(self) -> List[NameEntry]:
        """
        Get all player names from the namebase.

        Returns:
            List of NameEntry objects with id and name for each player.
            Names are stored in sorted order from the namebase.
        """
        self._backend._ensure_namebase_loaded()
        if self._backend.namebase is None:
            return []
        names = self._backend.namebase.names[NameType.PLAYER]
        return [NameEntry(id=i, name=name) for i, name in enumerate(names)]

    @property
    def events(self) -> List[NameEntry]:
        """
        Get all event names from the namebase.

        Returns:
            List of NameEntry objects with id and name for each event.
        """
        self._backend._ensure_namebase_loaded()
        if self._backend.namebase is None:
            return []
        names = self._backend.namebase.names[NameType.EVENT]
        return [NameEntry(id=i, name=name) for i, name in enumerate(names)]

    @property
    def sites(self) -> List[NameEntry]:
        """
        Get all site names from the namebase.

        Returns:
            List of NameEntry objects with id and name for each site.
        """
        self._backend._ensure_namebase_loaded()
        if self._backend.namebase is None:
            return []
        names = self._backend.namebase.names[NameType.SITE]
        return [NameEntry(id=i, name=name) for i, name in enumerate(names)]

    @property
    def rounds(self) -> List[NameEntry]:
        """
        Get all round names from the namebase.

        Returns:
            List of NameEntry objects with id and name for each round.
        """
        self._backend._ensure_namebase_loaded()
        if self._backend.namebase is None:
            return []
        names = self._backend.namebase.names[NameType.ROUND]
        return [NameEntry(id=i, name=name) for i, name in enumerate(names)]
