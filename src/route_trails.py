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

    {"quest": "parcel_event", "recorded_by": "AARON", "dense": true,
     "legs": [{"map": 40, "points": [[5, 3], [5, 4], [5, 5], ...]}, ...]}

A trail recorded while walking is **dense**: one point per tile actually
stepped on. Sparse anchors are what the log-mined trails can offer — the log
only writes a coordinate when something happens, so four to fifteen points have
to stand in for a whole crossing — and a follower handed those has to rediscover
everything between them. Density is therefore part of how a trail is ranked,
right after coverage: a trail that crosses more maps still wins, but a walked
path beats a mined stump of the same reach, and among equals the shorter one
wins, because fewer steps per quest is the point.

Joining is by nearest point, every step, over every leg of the current map.
That is also the whole answer to dying: a whiteout drops the run somewhere
behind, the nearest point is now an earlier one, and the follower walks forward
from there without anybody writing a recovery route.

Dying also ends the recording. A whiteout is not a stumble in the middle of a
route, it is attempt N+1 starting from the Center: publishing the walk that
ended in defeat together with the walk back would teach the detour as if it were
the way through, and the mistake would become the rule.
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


def _without_loops(positions):
    """Drop every excursion that came back to where it started.

    Walking away and returning is how a bot pushes at a wall, waits out an NPC
    or paces between two tiles. None of it is the way through, and a follower
    handed the loop would walk it again on purpose.
    """
    kept = []
    index_of = {}
    for position in positions:
        previous = index_of.get(position)
        if previous is None:
            index_of[position] = len(kept)
            kept.append(position)
            continue
        for undone in kept[previous + 1:]:
            index_of.pop(undone, None)
        del kept[previous + 1:]
    return kept


def _quality(legs, dense):
    """How good a trail is, biggest wins: reach, then density, then brevity.

    Reach counts only the maps the trail says something about. A leg holding a
    single point is a stamp — the trainer was here once — and the follower can
    do nothing with it but hand the step straight back to the drawn route. Every
    trail published so far is mostly stamps: `viridian_forest_nav` had nine legs
    and not one with two points in it, and under a ranking that counted them it
    would have outranked a crossing that knew every tile.
    """
    if not legs:
        return None
    points = sum(len(leg["points"]) for leg in legs)
    maps = len({leg.get("map") for leg in legs if len(leg["points"]) >= 2})
    return (maps, 1 if dense else 0, -points)


class TrailStore:
    """Read and write the shared per-quest trails."""

    def __init__(self, directory=TRAIL_DIRECTORY):
        self.directory = Path(directory)
        self._cache = {}

    def _path(self, quest_id):
        return self.directory / f"{quest_id}.json"

    def read(self, quest_id):
        """The stored trail with its provenance, or ``{}`` when there is none."""
        path = self._path(quest_id)
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            self._cache.pop(quest_id, None)
            return {}
        cached = self._cache.get(quest_id)
        if cached and cached[0] == stamp:
            return cached[1]
        try:
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            # A half-written or corrupt trail is not worth a crashed journey;
            # the follower simply falls back to the route in the graph.
            return {}
        if not isinstance(payload, dict):
            return {}
        self._cache[quest_id] = (stamp, payload)
        return payload

    def load(self, quest_id):
        """Trail legs for a quest, or ``[]`` when nobody has finished it yet."""
        return self.read(quest_id).get("legs", [])

    def publish(self, quest_id, agent_name, legs, force=False, dense=False,
                cycle=None, steps=None):
        """Store a finished trail, keeping the best one ever confirmed.

        Best is reach first, density second, brevity last. Brevity alone was
        the old rule and it locked the sparse trails in: a four-point stump
        mined from an event log can never be beaten by the fifty tiles somebody
        actually walked, so the crossing that knows every step could not
        replace the one that knows four.

        ``force`` stays for a trail chosen deliberately outside that ranking.
        """
        if not legs:
            return False
        quality = _quality(legs, dense)
        stored = self.read(quest_id)
        previous = _quality(stored.get("legs", []), bool(stored.get("dense")))
        if not force and previous is not None and previous >= quality:
            return False
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "quest": quest_id,
            "recorded_by": agent_name,
            "recorded_at": time.time(),
            "waypoints": sum(len(leg["points"]) for leg in legs),
            "dense": bool(dense),
            # What the winning attempt cost: which try after how many deaths,
            # and how many tiles it walked before the cartridge confirmed it.
            "death_cycle": cycle,
            "steps": steps,
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
    """Collect where a trainer actually walked during one attempt at a quest."""

    def __init__(self):
        self.quest_id = None
        self.points = []
        self.cycle = 0

    def record(self, quest_id, map_id, x, y):
        if quest_id != self.quest_id:
            self.quest_id = quest_id
            self.points = []
        position = (int(map_id), int(x), int(y))
        if not self.points or self.points[-1] != position:
            self.points.append(position)

    @property
    def steps(self):
        """Tiles walked in this attempt — what the attempt has cost so far."""
        return len(self.points)

    def restart(self, cycle):
        """Start attempt ``cycle``, and return what the last one cost.

        Called on a confirmed whiteout. Everything walked up to here belongs to
        the attempt that died: the approach that lost the fight and, before it,
        whatever route led there. The cartridge has already put the trainer back
        at the Center, so the next tile is the first tile of a new crossing.
        """
        walked = len(self.points)
        self.cycle = int(cycle)
        self.points = []
        return walked

    def legs(self, dense=True):
        """Walked positions as per-map legs, loops undone.

        Dense keeps every tile, which is a closed path. ``dense=False`` keeps
        only the turns — enough to redraw the same path while a step is a
        single tile, and all a log-mined trail can honestly claim.
        """
        legs = []
        current_map = None
        run = []
        for map_id, x, y in _without_loops(self.points):
            if map_id != current_map:
                if run:
                    legs.append({"map": current_map, "points": run})
                current_map = map_id
                run = []
            run.append([x, y])
        if run:
            legs.append({"map": current_map, "points": run})
        if not dense:
            for leg in legs:
                leg["points"] = _corner_points(leg["points"])
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

    A leg holding a single point is skipped. It is a stamp — the log recorded a
    coordinate because something happened there — and handing it over as a
    waypoint is worse than having no trail at all: it outranks the route the
    quest drew, and one tile far away is enough to flip which axis the follower
    treats as the long one, which flips which axis it sidesteps on. That is how
    AARON crossed the Route 3/Route 4 border every 0.6 seconds for an hour: the
    mined `mt_moon_nav` trail had one point on Route 4, at (27,3), so east
    became the main direction, the sidestep became north/south, and south is
    the way back to Route 3.
    """
    best = None
    for order, leg in enumerate(legs):
        if int(leg.get("map", -1)) != int(map_id):
            continue
        if len(leg.get("points", [])) < 2:
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
