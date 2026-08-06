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

# Warps are invisible to the tileset: a door tile is not in the walkable list,
# yet stepping onto (or off of) it is exactly how you leave the building. The
# map's own warp table says where they are.
PLAYER_X_ADDRESS = 0xD362
PLAYER_Y_ADDRESS = 0xD361
WARP_COUNT_ADDRESS = 0xD3AE
WARP_TABLE_ADDRESS = 0xD3AF
WARP_ENTRY_SIZE = 4

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

    def warp_offsets(self):
        """Tile offsets, relative to the player, that hold a warp."""
        offsets = set()
        player_x = self._byte(PLAYER_X_ADDRESS)
        player_y = self._byte(PLAYER_Y_ADDRESS)
        for slot in range(self._byte(WARP_COUNT_ADDRESS)):
            base = WARP_TABLE_ADDRESS + slot * WARP_ENTRY_SIZE
            offsets.add((self._byte(base + 1) - player_x, self._byte(base) - player_y))
        return offsets

    def warp_tiles(self):
        """Every warp on this map, in map coordinates."""
        tiles = set()
        for slot in range(self._byte(WARP_COUNT_ADDRESS)):
            base = WARP_TABLE_ADDRESS + slot * WARP_ENTRY_SIZE
            tiles.add((self._byte(base + 1), self._byte(base)))
        return tiles

    def on_warp(self):
        """True when the player is standing on a warp tile."""
        return (0, 0) in self.warp_offsets()

    def terrain_grid(self):
        """Walkability of the visible tiles, ignoring who is standing on them.

        This is the version worth remembering. People move, so recording them
        would rebuild the exact disease this module was written to cure: an NPC
        turned into permanent geometry.
        """
        walkable = self.walkable_tiles()
        warps = self.warp_offsets()
        grid = {}
        for dy in range(-(PLAYER_TILEMAP_ROW // 2), (TILEMAP_ROWS - PLAYER_TILEMAP_ROW) // 2):
            for dx in range(
                -(PLAYER_TILEMAP_COLUMN // 2),
                (TILEMAP_COLUMNS - PLAYER_TILEMAP_COLUMN) // 2,
            ):
                column = PLAYER_TILEMAP_COLUMN + dx * 2
                row = PLAYER_TILEMAP_ROW + dy * 2
                if not (0 <= column < TILEMAP_COLUMNS and 0 <= row < TILEMAP_ROWS):
                    continue
                tile = self._byte(TILEMAP_ADDRESS + row * TILEMAP_COLUMNS + column)
                grid[(dx, dy)] = tile in walkable or (dx, dy) in warps
        grid[(0, 0)] = True
        return grid

    def local_grid(self):
        """Walkability of every tile visible on screen, relative to the player.

        The four adjacent tiles are enough to avoid walking into a wall, and
        not enough to walk *around* one: a bot whose waypoint sat north of a
        cliff paced between two tiles forever, because each single step looked
        equally good. The screen shows about ten by nine map tiles — enough to
        find the way around what is in front.
        """
        walkable = self.walkable_tiles()
        occupied = self.occupied_offsets()
        warps = self.warp_offsets()
        grid = {}
        for dy in range(-(PLAYER_TILEMAP_ROW // 2), (TILEMAP_ROWS - PLAYER_TILEMAP_ROW) // 2):
            for dx in range(
                -(PLAYER_TILEMAP_COLUMN // 2),
                (TILEMAP_COLUMNS - PLAYER_TILEMAP_COLUMN) // 2,
            ):
                column = PLAYER_TILEMAP_COLUMN + dx * 2
                row = PLAYER_TILEMAP_ROW + dy * 2
                if not (0 <= column < TILEMAP_COLUMNS and 0 <= row < TILEMAP_ROWS):
                    continue
                tile = self._byte(TILEMAP_ADDRESS + row * TILEMAP_COLUMNS + column)
                walkable_here = tile in walkable or (dx, dy) in warps
                grid[(dx, dy)] = walkable_here and (dx, dy) not in occupied
        grid[(0, 0)] = True
        return grid

    def path_step(self, target_dx, target_dy):
        """First direction of the shortest visible path toward that offset.

        Only the screen is considered, so this never pretends to know the map.
        When the target is off screen it walks to the visible tile closest to
        it, which is the same thing a person does.
        """
        try:
            grid = self.local_grid()
        except Exception:
            return None
        if not grid:
            return None
        from collections import deque

        came = {(0, 0): None}
        queue = deque([(0, 0)])
        while queue:
            tile = queue.popleft()
            for direction, (dx, dy) in DIRECTION_STEPS.items():
                neighbour = (tile[0] + dx, tile[1] + dy)
                if neighbour in came or not grid.get(neighbour, False):
                    continue
                came[neighbour] = (tile, direction)
                queue.append(neighbour)

        reachable = [tile for tile in came if tile != (0, 0)]
        if not reachable:
            return None

        def rank(tile):
            return (
                abs(tile[0] - target_dx) + abs(tile[1] - target_dy),
                abs(tile[0]) + abs(tile[1]),
            )

        goal = min(reachable, key=rank)
        if rank(goal)[0] >= abs(target_dx) + abs(target_dy):
            # Nothing visible gets closer and nowhere new to try; let the
            # caller decide.
            return None
        node = goal
        while came[node][0] != (0, 0):
            node = came[node][0]
        return came[node][1]

    def blocked_directions(self):
        """Which of the four steps the game would refuse right now, and why."""
        try:
            walkable = self.walkable_tiles()
            occupied = self.occupied_offsets()
            warps = self.warp_offsets()
        except Exception:
            # Anything unreadable means "no opinion"; the caller keeps its own
            # learned map rather than inventing walls.
            return {}
        # Standing on a door, the way out is the step the tileset calls a wall:
        # the lab exit reads as blocked terrain and four trainers sat on it.
        # On a warp tile, terrain has no say — only people can still be in front.
        on_warp = (0, 0) in warps
        blocked = {}
        for direction, (dx, dy) in DIRECTION_STEPS.items():
            if (dx, dy) in occupied:
                blocked[direction] = "sprite"
                continue
            if on_warp or (dx, dy) in warps:
                continue
            column = PLAYER_TILEMAP_COLUMN + dx * 2
            row = PLAYER_TILEMAP_ROW + dy * 2
            if not (0 <= column < TILEMAP_COLUMNS and 0 <= row < TILEMAP_ROWS):
                continue
            tile = self._byte(TILEMAP_ADDRESS + row * TILEMAP_COLUMNS + column)
            if tile not in walkable:
                blocked[direction] = "terrain"
        return blocked
