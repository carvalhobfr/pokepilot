"""Real walkability, read from the cartridge instead of learned by bumping.

The project navigated by memory of its own failures: press a direction, fail to
move, write that edge down as a wall. It worked, and it was fragile in one very
specific way — an NPC standing still is indistinguishable from a wall for that
one step, so people got recorded as geometry and never forgiven. A trainer spent
a night beside a Route 3 tile whose only obstacle had walked away hours before.

The cartridge knows better, and it turns out to be cheap to ask:

* ``wTilesetCollisionPtr`` (0xD530) points at the list of walkable tile ids for
  the current tileset. It lives in bank 0, so no bank switching is needed —
  which is what made this look expensive before.
* the visible tile map (0xC3A0, 20x18) says which tile is where on screen.
* the sprite table (0xC100, 16 bytes per sprite) says where the people are, and
  it is read fresh every step, so somebody walking away stops blocking.

Terrain is permanent truth; sprites are true right now. Neither has to be
remembered, and neither can be learned wrong.
"""

from __future__ import annotations

# Screen geometry: the player is drawn at a fixed spot and the world scrolls
# under it. Everything else is measured from there, in 16-pixel tiles.
PLAYER_SCREEN_X = 64
PLAYER_SCREEN_Y = 60
TILE_PIXELS = 16

TILEMAP_ADDRESS = 0xC3A0
TILEMAP_COLUMNS = 20
TILEMAP_ROWS = 18
# The player stands on this cell of the tile map; a map tile is 2x2 of these.
PLAYER_TILEMAP_COLUMN = 8
PLAYER_TILEMAP_ROW = 9

COLLISION_POINTER_ADDRESS = 0xD530
SPRITE_TABLE_ADDRESS = 0xC100
SPRITE_ENTRY_SIZE = 0x10
SPRITE_SLOTS = 16

DIRECTION_STEPS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}


class TileCollision:
    """Walkability around the player, straight from the running cartridge."""

    def __init__(self, emulator):
        self.emulator = emulator

    def _byte(self, address):
        return int(self.emulator.memory[address])

    def _rom_byte(self, address):
        # Bank 0 is always mapped, so this needs no bank switching.
        return int(self.emulator.memory[0, address])

    def walkable_tiles(self):
        """Tile ids the current tileset lets the player stand on."""
        pointer = self._byte(COLLISION_POINTER_ADDRESS) + (
            self._byte(COLLISION_POINTER_ADDRESS + 1) << 8
        )
        tiles = set()
        for offset in range(256):
            value = self._rom_byte(pointer + offset)
            if value == 0xFF:
                break
            tiles.add(value)
        return tiles

    def occupied_offsets(self):
        """Tile offsets, relative to the player, where a sprite is standing."""
        occupied = set()
        for slot in range(1, SPRITE_SLOTS):
            base = SPRITE_TABLE_ADDRESS + slot * SPRITE_ENTRY_SIZE
            if self._byte(base) == 0:
                continue
            screen_y = self._byte(base + 4)
            screen_x = self._byte(base + 6)
            dx, remainder_x = divmod(screen_x - PLAYER_SCREEN_X, TILE_PIXELS)
            dy, remainder_y = divmod(screen_y - PLAYER_SCREEN_Y, TILE_PIXELS)
            if remainder_x or remainder_y:
                # Mid-step: the sprite is between tiles and will settle on one
                # of them. Rounding here would invent an obstacle.
                continue
            occupied.add((dx, dy))
        return occupied

    def blocked_directions(self):
        """Which of the four steps the game would refuse right now, and why."""
        try:
            walkable = self.walkable_tiles()
            occupied = self.occupied_offsets()
        except Exception:
            # Anything unreadable means "no opinion"; the caller keeps its own
            # learned map rather than inventing walls.
            return {}
        blocked = {}
        for direction, (dx, dy) in DIRECTION_STEPS.items():
            if (dx, dy) in occupied:
                blocked[direction] = "sprite"
                continue
            column = PLAYER_TILEMAP_COLUMN + dx * 2
            row = PLAYER_TILEMAP_ROW + dy * 2
            if not (0 <= column < TILEMAP_COLUMNS and 0 <= row < TILEMAP_ROWS):
                continue
            tile = self._byte(TILEMAP_ADDRESS + row * TILEMAP_COLUMNS + column)
            if tile not in walkable:
                blocked[direction] = "terrain"
        return blocked
