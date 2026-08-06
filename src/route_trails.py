"""Routes drawn by whoever walked them, kept for whoever comes next.

Two trainers run the same story with different jobs. AARON walks the route
written in the graph and nothing else — no trail from anybody, no local detour,
no replanning. When he is wrong, he stops being wrong quietly: he gets stuck,
and a stuck guide is the signal that the drawn route is wrong.

BARON is allowed everything AARON is not, and he starts from what AARON proved.
A quest only publishes its trail once the cartridge confirms the quest's own
predicate, so a follower never inherits a path that arrived nowhere.

The trail is stored per quest, split into legs by map, because a waypoint only
means something inside the map it was measured in:

    {"quest": "parcel_event", "recorded_by": "AARON",
     "legs": [{"map": 40, "points": [[5, 3], [5, 11]]}, ...]}

Joining is by nearest point, every step, over every leg of the current map.
That is also the whole answer to dying: a whiteout drops the run somewhere
behind, the nearest point is now an earlier one, and the follower walks forward
from there without anybody writing a recovery route.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

TRAIL_DIRECTORY = (
    Path(__file__).resolve().parent.parent
    / "blue-agents" / "knowledge" / "routes"
)


def _corner_points(points):
    """Keep the ends and the turns; a straight run needs no waypoints."""
    if len(points) <= 2:
        return list(points)
    kept = [points[0]]
    for previous, current, following in zip(points, points[1:], points[2:]):
        before = (current[0] - previous[0], current[1] - previous[1])
        after = (following[0] - current[0], following[1] - current[1])
        if before != after:
            kept.append(current)
    kept.append(points[-1])
    return kept


class TrailStore:
    """Read and write the shared per-quest trails."""

    def __init__(self, directory=TRAIL_DIRECTORY):
        self.directory = Path(directory)
        self._cache = {}

    def _path(self, quest_id):
        return self.directory / f"{quest_id}.json"

    def load(self, quest_id):
        """Trail legs for a quest, or ``[]`` when nobody has finished it yet."""
        path = self._path(quest_id)
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            self._cache.pop(quest_id, None)
            return []
        cached = self._cache.get(quest_id)
        if cached and cached[0] == stamp:
            return cached[1]
        try:
            with path.open(encoding="utf-8") as handle:
                legs = json.load(handle).get("legs", [])
        except (OSError, ValueError):
            # A half-written or corrupt trail is not worth a crashed journey;
            # the follower simply falls back to the route in the graph.
            return []
        self._cache[quest_id] = (stamp, legs)
        return legs

    def publish(self, quest_id, agent_name, legs, force=False):
        """Store a finished trail, keeping the shortest one ever confirmed.

        ``force`` exists for trails chosen deliberately — the miner picks by
        coverage first and length second, and a trail that crosses four maps
        must win over a two-point stump that happens to be shorter.
        """
        if not legs:
            return False
        length = sum(len(leg["points"]) for leg in legs)
        existing = self.load(quest_id)
        if not force and existing and sum(len(leg["points"]) for leg in existing) <= length:
            return False
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "quest": quest_id,
            "recorded_by": agent_name,
            "recorded_at": time.time(),
            "waypoints": length,
            "legs": legs,
        }
        path = self._path(quest_id)
        temporary = path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
        self._cache.pop(quest_id, None)
        return True


class TrailRecorder:
    """Collect where a trainer actually walked during one quest."""

    def __init__(self):
        self.quest_id = None
        self.points = []

    def record(self, quest_id, map_id, x, y):
        if quest_id != self.quest_id:
            self.quest_id = quest_id
            self.points = []
        position = (int(map_id), int(x), int(y))
        if not self.points or self.points[-1] != position:
            self.points.append(position)

    def legs(self):
        """Walked positions as per-map legs of turning points."""
        legs = []
        current_map = None
        run = []
        for map_id, x, y in self.points:
            if map_id != current_map:
                if run:
                    legs.append({"map": current_map, "points": _corner_points(run)})
                current_map = map_id
                run = []
            run.append([x, y])
        if run:
            legs.append({"map": current_map, "points": _corner_points(run)})
        return legs

    def clear(self):
        self.quest_id = None
        self.points = []


def waypoints_from(legs, map_id, x, y):
    """The rest of the trail, starting at the point nearest to where we are.

    Every leg of this map is a candidate, so a trainer thrown backwards by a
    whiteout rejoins behind where it was instead of walking to a door it can no
    longer reach. Ties go to the later leg: the same tile can be crossed on the
    way out and on the way back, and the way back is the one still owed.
    """
    best = None
    for order, leg in enumerate(legs):
        if int(leg.get("map", -1)) != int(map_id):
            continue
        points = [tuple(point) for point in leg.get("points", [])]
        for index, point in enumerate(points):
            distance = abs(point[0] - x) + abs(point[1] - y)
            key = (distance, -order, index)
            if best is None or key < best[0]:
                best = (key, points, index)
    if best is None:
        return []
    _, points, index = best
    if points[index] == (x, y) and index + 1 < len(points):
        index += 1
    return points[index:]
