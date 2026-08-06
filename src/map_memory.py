"""The map as the cartridge shows it, remembered while walking.

Reading the screen tells the truth about eighty tiles at a time, and that is
plenty to step around what is directly in front — but not to walk around a
building, or out of a pocket whose exit is off screen. That is what kept a bot
pacing two tiles: from each of them the other looked like the best way to a
waypoint neither could reach.

So the readings are kept. Every step reveals a screenful of terrain, and terrain
does not change: unlike the old learned collision, which inferred walls from
failed steps and turned people into permanent geometry, nothing here is ever a
guess. Sprites are deliberately left out — they move, and they are read live.
"""

from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path

DIRECTIONS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}


class MapMemory:
    """Walkable and solid tiles per map, as observed on screen."""

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.walkable = {}
        self.solid = {}
        self.dirty = False
        self._load()

    def _load(self):
        if self.path is None or not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return
        for key, maps in (("walkable", self.walkable), ("solid", self.solid)):
            for map_key, tiles in (payload.get(key) or {}).items():
                stored = set()
                for tile in tiles:
                    try:
                        x, y = (int(part) for part in str(tile).split(","))
                    except ValueError:
                        continue
                    stored.add((x, y))
                maps[int(map_key)] = stored

    def save(self):
        if self.path is None or not self.dirty:
            return
        payload = {"walkable": {}, "solid": {}}
        for key, maps in (("walkable", self.walkable), ("solid", self.solid)):
            for map_id, tiles in maps.items():
                payload[key][str(map_id)] = sorted(f"{x},{y}" for x, y in tiles)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(temporary, self.path)
        self.dirty = False

    def observe(self, map_id, origin, grid):
        """Store a screenful of terrain, given as offsets from ``origin``."""
        map_id = int(map_id)
        walkable = self.walkable.setdefault(map_id, set())
        solid = self.solid.setdefault(map_id, set())
        for (dx, dy), is_walkable in grid.items():
            tile = (origin[0] + dx, origin[1] + dy)
            target, other = (walkable, solid) if is_walkable else (solid, walkable)
            if tile in target:
                continue
            target.add(tile)
            other.discard(tile)
            self.dirty = True

    def is_solid(self, map_id, tile):
        return tuple(tile) in self.solid.get(int(map_id), ())

    def nearest_frontier(self, map_id, start, blocked=(), limit=4000):
        """Closest walkable tile that still touches something never seen.

        A goal behind a long wall turns optimistic planning into scraping: each
        search hops at the wall through a different unseen tile, learns one more
        stone, and tries the mirror image. Two trainers did that between (6,30)
        and (8,30) in the Forest for an afternoon.

        Frontier first, then. Walking to the edge of what is known is always
        progress, because it is the only thing that turns unknown into map.
        """
        map_id = int(map_id)
        start = tuple(start)
        solid = self.solid.get(map_id, set())
        walkable = self.walkable.get(map_id, set())
        avoid = {tuple(tile) for tile in blocked}
        seen = {start}
        queue = deque([start])
        while queue and len(seen) < limit:
            tile = queue.popleft()
            if tile != start and tile in walkable:
                for dx, dy in DIRECTIONS.values():
                    neighbour = (tile[0] + dx, tile[1] + dy)
                    if neighbour not in walkable and neighbour not in solid:
                        return tile
            for dx, dy in DIRECTIONS.values():
                neighbour = (tile[0] + dx, tile[1] + dy)
                if neighbour in seen or neighbour in solid or neighbour in avoid:
                    continue
                if neighbour not in walkable:
                    continue
                seen.add(neighbour)
                queue.append(neighbour)
        return None

    def find_path(self, map_id, start, goal, blocked=(), limit=4000):
        """Shortest known path, treating unseen tiles as worth trying.

        Optimism about the unseen is what lets a bot walk off the edge of what
        it has already looked at; every step it takes replaces that optimism
        with a reading.
        """
        map_id = int(map_id)
        start, goal = tuple(start), tuple(goal)
        if start == goal:
            return []
        solid = self.solid.get(map_id, set())
        avoid = {tuple(tile) for tile in blocked}
        came = {start: None}
        queue = deque([start])
        while queue and len(came) < limit:
            tile = queue.popleft()
            if tile == goal:
                break
            for direction, (dx, dy) in DIRECTIONS.items():
                neighbour = (tile[0] + dx, tile[1] + dy)
                if neighbour in came or neighbour in solid or neighbour in avoid:
                    continue
                if not (0 <= neighbour[0] <= 255 and 0 <= neighbour[1] <= 255):
                    continue
                came[neighbour] = (tile, direction)
                queue.append(neighbour)
        if goal not in came:
            return None
        path = []
        node = goal
        while came[node] is not None:
            previous, direction = came[node]
            path.append(direction)
            node = previous
        path.reverse()
        return path
