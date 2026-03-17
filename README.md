# pyscid

A pure Python library for reading SCID chess database files (.si4, .si5).

This is pretty much all vibecoded.. use with caution. 

## Features

- Read **SI4** databases (`.si4`, `.sn4`, `.sg4`)
- Read **SI5** databases (`.si5`, `.sn5`, `.sg5`)
- Read **PGN** files (`.pgn`)
- Unified `Database` interface with automatic format detection
- **Lazy loading** - instant database open, data loaded on demand
- **Fast search** - optimized index-based filtering
- Extract game metadata (players, ratings, dates, results, ECO codes)
- Decode moves from the compact binary format
- Export games to PGN format

## Performance

Benchmarks on a 10 million game database:

| Operation | Time |
|-----------|------|
| Open database | **0.1 ms** |
| Load namebase (580K players) | **0.5 seconds** |
| Search by name (first time) | **11 seconds** (builds index) |
| Search by name (cached) | **0.5 - 1.5 seconds** |
| Search by ID (first time) | **11 seconds** (builds index) |
| Search by ID (cached) | **0.001 - 0.01 seconds** |
| Combined search (ID + year) | **0.007 seconds** |
| Access single game | **0.1 ms** |
| Iterate 10,000 games | **1.4 seconds** |

The library uses:
- **Lazy loading** - instant database open, data loaded on demand
- **Memory-mapped files** - efficient access without loading entire files
- **Player-game index** - built on first search, enables instant subsequent lookups
- **Index-based filtering** - avoids decoding games that don't match

## Installation

```bash
pip install pyscid
```

Or install from source:

```bash
git clone https://github.com/yourusername/pyscid.git
cd pyscid
pip install -e .
```

## Quick Start

```python
from pyscid import Database

# Open any supported format (auto-detected)
# This is instant - data is loaded lazily on demand
db = Database.open("games.si4")

# Get basic info
print(f"Number of games: {len(db)}")
print(f"Format: {db.format}")

# Random access - only this game is loaded
game = db[42]
print(f"{game.white} vs {game.black}: {game.result}")

# Browse the namebase to see what's in the database
players = db.namebase.players
print(f"Total players: {len(players)}")

# Find a specific player
magnus = [p for p in players if "Carlsen, Magnus" in p.name][0]
print(f"Found: {magnus.name} (ID {magnus.id})")

# Fast ID-based search (recommended)
for game in db.search(player_id=magnus.id, year_min=2020):
    print(f"{game.white} vs {game.black}")
    print(f"  Date: {game.date_string}")
    print(f"  ECO: {game.eco}")

# Get moves
for move in game.moves[:10]:
    print(f"  {move.uci()}")

# Export to PGN
print(game.to_pgn())

# Close when done
db.close()

# Or use as context manager
with Database.open("games.pgn") as db:
    for game in db:
        print(game)
```

### Loading Options

```python
# Default: lazy loading (instant open)
db = Database.open("games.si4")

# Preload everything (slower open, faster iteration)
db = Database.open("games.si4", preload=True)

# Preload just names (good for metadata browsing)
db = Database.open("games.si4", preload_names=True)

# Enable LRU cache for repeated random access
db = Database.open("games.si4", cache_size=10000)
```

## Supported Data

### Game Metadata

- Player names (White, Black)
- Event and site
- Date and event date
- Result
- Ratings (ELO) with rating type
- ECO opening code
- Number of half-moves (ply count)
- Extra PGN tags

### Index Entry Data (SI format only)

- Game flags (deleted, user flags, etc.)
- Annotation counts (comments, variations, NAGs)
- Material signature
- Home pawn data (for position search)
- Chess960 indicator

## Format Details

### SI4 Format

The original format using three files:
- `.si4` - Index file with 47-byte records per game
- `.sn4` - Namebase with front-coded strings
- `.sg4` - Game data with encoded moves

### SI5 Format

The newer format with larger limits:
- `.si5` - Index file with 56-byte records (little-endian)
- `.sn5` - Namebase with varint-encoded strings
- `.sg5` - Game data (same format as SI4)

### PGN Format

Standard Portable Game Notation text format.

## API Reference

### Database

```python
Database.open(
    filepath: str,
    preload: bool = False,       # Load all data upfront
    preload_names: bool = False, # Load player/event names only
    cache_size: int = 0          # LRU cache size for index entries
) -> Database

len(db) -> int
    # Number of games

db[index] -> Game
    # Get game by index (0-based)

for game in db:
    # Iterate through games

db.search(**criteria) -> Iterator[Game]
    # Search with criteria (see below)

db.format -> str
    # 'si4', 'si5', or 'pgn'

db.description -> str
    # Database description (SI format only)

db.preload_all()
    # Explicitly load all data

db.preload_namebase()
    # Explicitly load name data

db.close()
    # Release resources

db.namebase
    # Access namebase for browsing names (SI4/SI5 only)
```

### NameBase Interface

Browse all unique names in the database without loading games. Only available for SCID4/SCID5 formats.

```python
# Access the namebase
players = db.namebase.players   # All player names
events = db.namebase.events     # All event names
sites = db.namebase.sites       # All site names
rounds = db.namebase.rounds     # All round names

# Each entry has an ID and name
print(f"Total players: {len(players)}")
for player in players[:10]:
    print(f"ID {player.id}: {player.name}")

# Find specific names
magnus = [p for p in players if "Carlsen, Magnus" in p.name][0]
print(f"Found: {magnus.name} (ID {magnus.id})")

# Use ID for fast searches (much faster than name search)
games = list(db.search(white_id=magnus.id))
print(f"Found {len(games)} games")

# ID-based searches work with all name types
event = [e for e in events if "World Championship" in e.name][0]
games = list(db.search(event_id=event.id))

# Combine ID search with other criteria (very fast!)
games = list(db.search(player_id=magnus.id, year=2020))
```

**Performance:** Browsing the namebase is fast because it only loads the compressed name file:
- 580K players loaded in ~0.5 seconds
- 237K events loaded in ~0.05 seconds
- 82K sites loaded in ~0.02 seconds

**ID-based searches are fastest:**
- First ID search: ~10 seconds (builds player-game index)
- Subsequent ID searches: 0.001-0.01 seconds (uses cached index)
- Name-based searches: 0.5-1.5 seconds (requires name lookup)

### Search Criteria

```python
db.search(
    # Name-based searches (slower, partial match, case-insensitive)
    white="Carlsen",      # White player name
    black="Nakamura",     # Black player name
    player="Carlsen",     # Either player name
    event="Tata Steel",   # Event name
    site="Wijk aan Zee",  # Site name
    
    # ID-based searches (fastest, exact match) - SI4/SI5 only
    white_id=1324,        # White player ID (from db.namebase.players)
    black_id=5678,        # Black player ID
    player_id=1324,       # Either player ID
    event_id=42,          # Event ID (from db.namebase.events)
    site_id=99,           # Site ID (from db.namebase.sites)
    
    # Other criteria
    year=2024,            # Exact year
    year_min=2020,        # Minimum year
    year_max=2024,        # Maximum year
    result=Result.DRAW,   # Game result
    eco="B90",            # ECO code prefix (e.g., "B", "B9", "B90")
    min_elo=2700          # Minimum rating for either player
)
```

All criteria are optional and combined with AND logic.

**Search performance tips:**
- Use ID-based searches when possible (10-100x faster than name searches)
- Browse `db.namebase` to get IDs for players/events/sites
- Combine ID searches with other criteria for maximum speed
- Name searches build indexes on first use, making subsequent searches faster

### Game

```python
game.white -> str           # White player name
game.black -> str           # Black player name
game.event -> str           # Event name
game.site -> str            # Site/location
game.round -> str           # Round
game.date -> datetime.date  # Game date (or None)
game.result -> Result       # Result enum
game.white_elo -> int       # White's rating
game.black_elo -> int       # Black's rating
game.eco -> str             # ECO code (e.g., "C50")
game.moves -> List[Move]    # List of moves
game.fen -> str             # Starting FEN (if non-standard)
game.extra_tags -> dict     # Additional PGN tags

game.to_pgn() -> str        # Export to PGN format
game.date_string -> str     # Date in PGN format
```

### Move

```python
move.from_square -> int     # Source square (0-63)
move.to_square -> int       # Destination square
move.promotion -> Piece     # Promotion piece (or None)
move.is_castle_kingside -> bool
move.is_castle_queenside -> bool
move.is_null_move -> bool

move.uci() -> str           # UCI format (e.g., "e2e4")
```

## License

This library is released under the GNU General Public License v2 (GPLv2).

See the [LICENSE](LICENSE) file for details.

## Acknowledgments

This library implements the SI database file format. The format specification
was derived from studying the SCID (Shane's Chess Information Database) source
code:

- **SCID** - Original software that created this format
- Original author: Shane Hudson (sgh@users.sourceforge.net)
- Contributors: Pascal Georges, Fulvio Benini, and others
- Website: https://scid.sourceforge.net/

This is a clean-room Python implementation - no source code was copied.
We only read the original C++ code to understand the binary file format
specifications, then wrote this library from scratch.

This library does NOT include any of the following restricted components:
- Book files (performance.bin, varied.bin, Elo2400.bin, gm2600.bin)
- Database files
- Crafty chess engine
- Endgame tablebase code
- Piece graphics
