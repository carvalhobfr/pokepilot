"""Collision learned while playing, plus breadth-first search over it.

The cartridge never tells us where the walls are: reading ``wTilesetCollisionPtr``
would mean dealing with ROM bank switching, and probing walls by branching save
states (``blue-agents/tools/probe_route.py``) is far too slow to run per step.

But the agent already produces the information and used to throw it away: it
pressed a direction from a tile and did not move, so that edge is blocked. This
module stores those edges per ``(map, x, y, direction)``, persists them next to
the rest of the trainer journey and plans routes over them, treating every
unknown edge as free. The knowledge is therefore optimistic at first and gets
better on every run.
"""

from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path

# Screen coordinates grow right and down, like the RAM values at 0xD362/0xD361.
DIRECTIONS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}

# Expansion order for ties. "Down last" is deliberate: several Kanto routes are
# entered from a warp tile on the south edge, and preferring south there walked
# bots straight back into the map they had just left.
EXPANSION_ORDER = ("U", "R", "L", "D")

# A Gen I map fits well inside this; the bound only guards against planning off
# into coordinates the game can never produce.
COORDINATE_LIMIT = 255


class CollisionMemory:
    """Blocked edges observed in game, optionally persisted as JSON."""

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.blocked = set()
        # Doors crossed by accident. Kept apart from walls on purpose: the
        # rules that forget a contradictory tile exist because a wall can be
        # learned wrong, but a door is not a wall — it is a hazard that keeps
        # working. Mixing them let two bots bounce in and out of a Pewter
        # building forever, relearning and forgetting the same doorway.
        self.warps = set()
        # Edges this session proved walkable. Kept so a merge with the file on
        # disk cannot resurrect a wall that turned out to be an NPC.
        self.cleared = set()
        self._load()

    def _load(self):
        blocked, warps = self._read_file(with_warps=True)
        self.blocked |= blocked
        self.warps |= warps
        self.sanitize()

    def _read_file(self, with_warps=False):
        """Edges currently on disk, so concurrent trainers pool instead of
        overwriting each other. Map geometry does not depend on who walks it."""
        empty = (set(), set()) if with_warps else set()
        if self.path is None or not self.path.exists():
            return empty
        try:
            with self.path.open("r") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            # A truncated file is not worth crashing a journey over; the agent
            # relearns the edges as it walks.
            return empty
        edges = self._parse_edges(payload.get("blocked") or {})
        if with_warps:
            return edges, self._parse_edges(payload.get("warps") or {})
        return edges

    @staticmethod
    def _parse_edges(grouped):
        edges = set()
        for map_key, entries in grouped.items():
            try:
                map_id = int(map_key)
            except (TypeError, ValueError):
                continue
            for entry in entries:
                parts = str(entry).split(",")
                if len(parts) != 3 or parts[2] not in DIRECTIONS:
                    continue
                try:
                    x, y = int(parts[0]), int(parts[1])
                except ValueError:
                    continue
                edges.add((map_id, x, y, parts[2]))
        return edges

    def save(self):
        if self.path is None:
            return
        # Read-modify-write: two trainers walk at the same time and a plain
        # overwrite would throw away whatever the other one just learned.
        stored_blocked, stored_warps = self._read_file(with_warps=True)
        self.blocked |= stored_blocked - self.cleared
        self.warps |= stored_warps
        grouped = {}
        for map_id, x, y, direction in sorted(self.blocked):
            grouped.setdefault(str(map_id), []).append(f"{x},{y},{direction}")
        warps = {}
        for map_id, x, y, direction in sorted(self.warps):
            warps.setdefault(str(map_id), []).append(f"{x},{y},{direction}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: the supervisor can be killed between blocks, and a
        # half-written file would be dropped on the next load.
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w") as handle:
            json.dump(
                {"version": 1, "blocked": grouped, "warps": warps}, handle, indent=2
            )
        os.replace(temporary, self.path)

    def is_blocked(self, map_id, x, y, direction):
        return (int(map_id), int(x), int(y), direction) in self.blocked

    def mark_blocked(self, map_id, x, y, direction):
        """Record that walking ``direction`` from this tile produced no move."""
        edge = (int(map_id), int(x), int(y), direction)
        if edge in self.blocked:
            return False
        # A tile with no way out cannot be true: the bot is standing on it, so
        # it walked in through one of these sides. One of the four beliefs is
        # wrong, and there is no way to tell which — so drop all of them and
        # let the bot find out by walking.
        #
        # Merely refusing the fourth edge was worse than useless: it left one
        # phantom exit that the search picked every single time, and four bots
        # spent a night pressing D into a wall on Route 2 because the real way
        # out, north, had been recorded as blocked.
        if self._would_seal_tile(int(map_id), int(x), int(y), direction):
            self.forget_tile(map_id, x, y)
            return False
        self.blocked.add(edge)
        self.cleared.discard(edge)
        self.save()
        return True

    def mark_warp(self, map_id, x, y, direction):
        """Record a doorway crossed by accident, never to be planned through.

        Unlike a wall, this is never forgotten by the contradiction rules: a
        door that took the bot somewhere it did not mean to go will do it again
        every single time.
        """
        edge = (int(map_id), int(x), int(y), direction)
        if edge in self.warps:
            return False
        self.warps.add(edge)
        self.save()
        return True

    def mark_open(self, map_id, x, y, direction):
        """Forget a blocked edge that was just walked through.

        An NPC standing on the path looks exactly like a wall. When the tile is
        crossed later, the wall was never there and the memory must not keep
        planning around a person who has already moved.
        """
        edge = (int(map_id), int(x), int(y), direction)
        self.cleared.add(edge)
        if edge not in self.blocked:
            return False
        self.blocked.discard(edge)
        self.save()
        return True

    def forget_tile(self, map_id, x, y):
        """Discard everything believed about the sides of one tile."""
        edges = {
            (int(map_id), int(x), int(y), label) for label in DIRECTIONS
        } & self.blocked
        if not edges:
            return set()
        self.blocked -= edges
        self.cleared |= edges
        self.save()
        return edges

    def _would_seal_tile(self, map_id, x, y, direction):
        exits = {
            label for label in DIRECTIONS
            if (map_id, x, y, label) not in self.blocked
        }
        return exits == {direction}

    def sanitize(self):
        """Drop edges that leave a tile with no way out.

        Older files were written before the rule existed, and a sealed tile in
        shared knowledge strands every trainer that steps on it.
        """
        removed = set()
        tiles = {(map_id, x, y) for map_id, x, y, _ in self.blocked}
        for map_id, x, y in tiles:
            sides = {
                label for label in DIRECTIONS
                if (map_id, x, y, label) in self.blocked
            }
            if len(sides) >= len(DIRECTIONS) - 1:
                # Three sides is already a contradiction in practice: the exit
                # that remains is the one the search will pick forever, and if
                # it is a wall the run has no way to discover it.
                for label in sides:
                    removed.add((map_id, x, y, label))
        if removed:
            self.blocked -= removed
            self.cleared |= removed
            self.save()
        return removed

    def find_path(
        self, map_id, start, goal, margin=15, node_limit=6000, avoid=(), relax=False
    ):
        """Shortest known-free path from ``start`` to ``goal`` as direction labels.

        Unknown edges count as free, so the first plan on a fresh map is the
        straight line and every collision narrows it. Returns ``None`` when the
        goal is unreachable inside the search box, which lets the caller fall
        back to the old axis-by-axis walk.
        """
        map_id = int(map_id)
        start = (int(start[0]), int(start[1]))
        goal = (int(goal[0]), int(goal[1]))
        if start == goal:
            return []

        min_x = max(0, min(start[0], goal[0]) - margin)
        max_x = min(COORDINATE_LIMIT, max(start[0], goal[0]) + margin)
        min_y = max(0, min(start[1], goal[1]) - margin)
        max_y = min(COORDINATE_LIMIT, max(start[1], goal[1]) + margin)

        queue = deque([start])
        came_from = {start: None}
        while queue and len(came_from) < node_limit:
            current = queue.popleft()
            if current == goal:
                return self._reconstruct(came_from, goal)
            for direction in EXPANSION_ORDER:
                edge = (map_id, current[0], current[1], direction)
                # `avoid` holds edges that failed under ambiguous conditions —
                # a text box eats the D-pad exactly like a wall does. Those are
                # worth stepping around right now and never worth writing down.
                if edge in avoid or edge in self.warps:
                    continue
                if edge in self.blocked and not relax:
                    continue
                delta = DIRECTIONS[direction]
                candidate = (current[0] + delta[0], current[1] + delta[1])
                if not (min_x <= candidate[0] <= max_x):
                    continue
                if not (min_y <= candidate[1] <= max_y):
                    continue
                if candidate in came_from:
                    continue
                came_from[candidate] = (current, direction)
                queue.append(candidate)
        return None

    @staticmethod
    def _reconstruct(came_from, goal):
        path = []
        node = goal
        while came_from[node] is not None:
            previous, direction = came_from[node]
            path.append(direction)
            node = previous
        path.reverse()
        return path
