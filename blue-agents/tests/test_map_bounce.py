"""Crossing a border back and forth is stuck, and the report has to say so.

AARON crossed Route 4 and Mt. Moon **400 times in 300 seconds** and produced
no stuck report at all. The tile trigger could not see it for two reasons at
once: each crossing steps on different tiles on both sides, so the window fills
with distinct positions; and the progress key includes the map, so "steps
without getting closer" resets on every trip.

It was the third map-boundary bounce in one day that had to be found by hand.
"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.scripted_agent import (
    STUCK_MAP_CROSSINGS,
    STUCK_WINDOW_TILES,
    ScriptedAgent,
)


class BounceReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def agent(self):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.save_dir = self.directory.name
        agent.player_name = "AARON"
        agent.current_task_name = "mt_moon_nav"
        agent._map_memory = lambda: type("M", (), {
            "find_path": staticmethod(lambda *a, **k: None),
            "nearest_frontier": staticmethod(lambda *a, **k: None),
            "walkable": {},
            "solid": {},
        })()
        agent._tile_reader = lambda: None
        agent.emulator = type("E", (), {"memory": type("M", (), {
            "get_party_count": staticmethod(lambda: 0),
            "read_byte": staticmethod(lambda address: 0),
        })()})()
        return agent

    def relatos(self):
        import json

        path = Path(self.directory.name) / "logs" / "stuck.jsonl"
        if not path.exists():
            return []
        return [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def cross(self, agent, times):
        """Alternate between two maps, stepping on different tiles each side."""
        for turn in range(times):
            for map_id, tile in ((15, (18, 5 + turn % 3)), (59, (14, 35 - turn % 3))):
                agent._report_if_stuck(
                    map_id, tile[0], tile[1], 21, 15, {}, [(21, 15)], f"rota-{map_id}"
                )

    def test_a_border_bounce_is_reported(self):
        agent = self.agent()
        self.cross(agent, STUCK_WINDOW_TILES * 4)
        self.assertTrue(self.relatos(), "vaivém entre mapas não gerou relatório")

    def test_the_report_names_both_maps(self):
        agent = self.agent()
        self.cross(agent, STUCK_WINDOW_TILES * 4)
        self.assertEqual([15, 59], self.relatos()[0]["bouncing_between_maps"])

    def test_walking_normally_through_maps_is_not_a_bounce(self):
        # A journey crosses borders all the time; only coming straight back
        # counts.
        agent = self.agent()
        for step, map_id in enumerate([0, 12, 1, 13, 50, 51, 47, 2, 54]):
            for _ in range(STUCK_WINDOW_TILES):
                agent._report_if_stuck(
                    map_id, step, step, 21, 15, {}, [(21, 15)], "andando"
                )
                step += 1
        self.assertEqual([], [r for r in self.relatos() if r["bouncing_between_maps"]])

    def test_two_crossings_are_not_enough_to_accuse_anyone(self):
        # Entering a door and coming out because the errand is done is normal.
        agent = self.agent()
        self.cross(agent, STUCK_MAP_CROSSINGS // 2 - 1)
        self.assertEqual([], self.relatos())


if __name__ == "__main__":
    unittest.main()


class MtMoonApproachTests(unittest.TestCase):
    """The anchor that a trainer has already walked past is a spent anchor."""

    def agent_on_route_4(self, x):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.emulator = type("E", (), {"memory": type("M", (), {
            "get_map_id": staticmethod(lambda: 15),
            "get_player_pos": staticmethod(lambda: (x, 6)),
            "get_party_count": staticmethod(lambda: 1),
            "read_byte": staticmethod(lambda address: 0),
        })()})()
        agent._party_needs_healing = lambda: False
        agent._should_top_up_before = lambda map_id: False
        agent._party_health_fraction = lambda: 1.0
        agent.seen = {}
        agent._follow_route = lambda route_id, waypoints: agent.seen.update(
            {"route": route_id, "waypoints": waypoints}
        )
        return agent

    def test_coming_from_the_west_still_uses_the_approach(self):
        agent = self.agent_on_route_4(9)
        agent._run_mt_moon_nav()
        self.assertEqual([(11, 6), (18, 6), (18, 5)], agent.seen["waypoints"])

    def test_already_past_it_heads_straight_for_the_cave(self):
        # Walking back west to (11,6), then east to the cave, then out of the
        # cave again is the loop: 400 crossings in 300 seconds.
        agent = self.agent_on_route_4(16)
        agent._run_mt_moon_nav()
        self.assertEqual([(18, 6), (18, 5)], agent.seen["waypoints"])

    def test_stepping_out_of_the_cave_does_not_send_it_west(self):
        agent = self.agent_on_route_4(18)
        agent._run_mt_moon_nav()
        self.assertNotIn((11, 6), agent.seen["waypoints"])
