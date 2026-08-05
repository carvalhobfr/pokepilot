import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.tile_collision import (
    PLAYER_SCREEN_X,
    PLAYER_SCREEN_Y,
    PLAYER_TILEMAP_COLUMN,
    PLAYER_TILEMAP_ROW,
    TILEMAP_ADDRESS,
    TILEMAP_COLUMNS,
    TileCollision,
)


class FakeMemory:
    """Enough of the cartridge to answer the walkability question."""

    def __init__(self, *, walkable_tiles, tiles, sprites=()):
        self.data = {0xD530: 0x00, 0xD531: 0x40}
        for index, tile in enumerate(walkable_tiles):
            self.data[("rom", 0x4000 + index)] = tile
        self.data[("rom", 0x4000 + len(walkable_tiles))] = 0xFF
        for (column, row), tile in tiles.items():
            self.data[TILEMAP_ADDRESS + row * TILEMAP_COLUMNS + column] = tile
        for slot, (dx, dy) in enumerate(sprites, start=1):
            base = 0xC100 + slot * 0x10
            self.data[base] = 1
            self.data[base + 4] = PLAYER_SCREEN_Y + dy * 16
            self.data[base + 6] = PLAYER_SCREEN_X + dx * 16

    def __getitem__(self, key):
        if isinstance(key, tuple):
            return self.data.get(("rom", key[1]), 0)
        return self.data.get(key, 0)


class FakeEmulator:
    def __init__(self, memory):
        self.memory = memory


def scene(*, walls=(), sprites=()):
    tiles = {}
    for direction, (dx, dy) in (
        ("U", (0, -1)), ("D", (0, 1)), ("L", (-1, 0)), ("R", (1, 0)),
    ):
        column = PLAYER_TILEMAP_COLUMN + dx * 2
        row = PLAYER_TILEMAP_ROW + dy * 2
        tiles[(column, row)] = 99 if direction in walls else 44
    return TileCollision(FakeEmulator(FakeMemory(
        walkable_tiles=[44], tiles=tiles, sprites=sprites,
    )))


class TileCollisionTests(unittest.TestCase):
    """Terrain is permanent truth, sprites are true right now, and neither has
    to be guessed from a failed step."""

    def test_open_ground_blocks_nothing(self):
        self.assertEqual({}, scene().blocked_directions())

    def test_a_wall_is_reported_as_terrain(self):
        self.assertEqual({"U": "terrain"}, scene(walls={"U"}).blocked_directions())

    def test_a_person_standing_there_is_reported_as_a_sprite(self):
        # The distinction the learned map could never make: an NPC and a wall
        # produce exactly the same failed step.
        self.assertEqual({"D": "sprite"}, scene(sprites=[(0, 1)]).blocked_directions())

    def test_the_route3_tile_that_trapped_a_trainer(self):
        # Measured on the real save: wall above, people below and to the right,
        # the way out to the left. The bot had recorded all three as geometry.
        self.assertEqual(
            {"U": "terrain", "D": "sprite", "R": "sprite"},
            scene(walls={"U"}, sprites=[(0, 1), (1, 0)]).blocked_directions(),
        )

    def test_a_sprite_between_tiles_is_not_an_obstacle_yet(self):
        # Mid-step the sprite belongs to neither tile; rounding it to one would
        # invent an obstacle that is about to not be there.
        reader = scene()
        memory = reader.emulator.memory
        base = 0xC100 + 0x10
        memory.data[base] = 1
        memory.data[base + 4] = PLAYER_SCREEN_Y + 8
        memory.data[base + 6] = PLAYER_SCREEN_X
        self.assertEqual({}, reader.blocked_directions())

    def test_an_unreadable_cartridge_has_no_opinion(self):
        class Broken:
            memory = None
        self.assertEqual({}, TileCollision(Broken()).blocked_directions())


if __name__ == "__main__":
    unittest.main()
