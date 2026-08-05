"""Doors, learned by walking through them.

`knowledge/maps/warps.json` already had the right shape — for each map, which
tile leads to which other map — but only the free-exploration mode ever wrote to
it, and the scripted journey never read it. So every executor carried
hand-measured coordinates for doors the bots walk through dozens of times a day,
and a bot that lost its route circled a building whose entrance it had used an
hour earlier.

A door is the cheapest fact in this project to collect: the tile the bot stood
on when the map id changed. Shared between trainers, like the collision map,
because a door does not belong to whoever opened it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class WarpMemory:
    """Tile → destination map, per map, persisted as JSON."""

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.doors = {}
        self._load()

    def _load(self):
        self.doors = self._read_file()

    def _read_file(self):
        if self.path is None or not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return {}
        doors = {}
        for map_key, tiles in (payload or {}).items():
            if not isinstance(tiles, dict):
                continue
            doors[str(map_key)] = {
                str(tile): int(destination)
                for tile, destination in tiles.items()
                if str(destination).lstrip("-").isdigit()
            }
        return doors

    def save(self):
        if self.path is None:
            return
        merged = self._read_file()
        for map_key, tiles in self.doors.items():
            merged.setdefault(map_key, {}).update(tiles)
        self.doors = merged
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(merged, handle, indent=2)
        os.replace(temporary, self.path)

    def record(self, map_id, x, y, destination_map):
        """Remember that leaving this tile lands on that map."""
        map_key, tile = str(int(map_id)), f"{int(x)},{int(y)}"
        destination = int(destination_map)
        if self.doors.get(map_key, {}).get(tile) == destination:
            return False
        self.doors.setdefault(map_key, {})[tile] = destination
        self.save()
        return True

    def doors_from(self, map_id):
        """Every known door of this map, as {(x, y): destination}."""
        tiles = self.doors.get(str(int(map_id)), {})
        doors = {}
        for tile, destination in tiles.items():
            try:
                x, y = (int(part) for part in tile.split(","))
            except ValueError:
                continue
            doors[(x, y)] = int(destination)
        return doors

    def door_to(self, map_id, destination_map, near=None):
        """Tile of this map that leads to that one, nearest to ``near``."""
        candidates = [
            tile for tile, destination in self.doors_from(map_id).items()
            if destination == int(destination_map)
        ]
        if not candidates:
            return None
        if near is None:
            return sorted(candidates)[0]
        return min(
            candidates,
            key=lambda tile: abs(tile[0] - near[0]) + abs(tile[1] - near[1]),
        )
