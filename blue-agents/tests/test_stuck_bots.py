"""Three freezes seen running, and what each one turned out to be.

AARON crossed the Route 3/Route 4 border every 0.6s for an hour. CAARON stood
at (5,1) in Oak's Lab for thousands of steps. Neither wrote a stuck report:
one changes map constantly, so progress never stalls against a single target;
the other returns before the report is written.
"""

import sys
import unittest
from pathlib import Path

from pyboy.utils import WindowEvent

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.route_trails import waypoints_from
from src.scripted_agent import MENU_PRESS_LIMIT, ScriptedAgent
from src.warp_memory import WarpMemory

from tests.test_route_following import FakeMemory


class StampsAreNotTrailsTests(unittest.TestCase):
    """A leg with one point steered the bot; it should say nothing at all."""

    # The shape mined from `mt_moon_nav`: one coordinate per map, because the
    # log only writes one when something happens.
    STAMPS = [
        {"map": 61, "points": [[16, 4]]},
        {"map": 15, "points": [[27, 3]]},
    ]

    def test_a_single_point_leg_is_ignored(self):
        self.assertEqual([], waypoints_from(self.STAMPS, 15, 10, 17))

    def test_a_real_leg_on_the_same_map_still_answers(self):
        legs = self.STAMPS + [{"map": 15, "points": [[10, 16], [10, 6]]}]
        self.assertEqual([(10, 16), (10, 6)], waypoints_from(legs, 15, 10, 17))

    def test_the_border_crossing_is_no_longer_a_candidate(self):
        # With the stamp in play the target was east, so the sidestep axis was
        # north/south — and south is the step back to Route 3. Without it the
        # target is north and the sidestep axis is east/west.
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.memory_probe = FakeMemory((10, 17), 15)
        agent.emulator = type("FakeEmulator", (), {"memory": agent.memory_probe})()
        agent._tile_truth = lambda: {"U": "terrain", "R": "terrain"}
        agent._visible_step = lambda dx, dy: None
        agent._planned_step = lambda *a: None
        agent.warp_memory = WarpMemory()
        action = agent._follow_route("mt-moon-enter-cave", [(11, 6), (18, 6)])
        self.assertNotEqual(WindowEvent.PRESS_ARROW_DOWN, action)


class TextLoopTests(unittest.TestCase):
    """The menu flag can stay up with nothing a button will clear."""

    def make_agent(self):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.memory_probe = FakeMemory((5, 1), 40)
        agent.memory_probe.menu = 1
        agent.emulator = type("FakeEmulator", (), {"memory": agent.memory_probe})()
        agent._tile_truth = lambda: {}
        agent._visible_step = lambda dx, dy: None
        agent._planned_step = lambda *a: None
        agent.warp_memory = WarpMemory()
        return agent

    def actions(self, agent, count):
        return [agent._follow_route("door-40", [(5, 11)]) for _ in range(count)]

    def test_it_presses_to_clear_the_box_first(self):
        agent = self.make_agent()
        pressed = self.actions(agent, MENU_PRESS_LIMIT)
        self.assertTrue(all(
            action in (WindowEvent.PRESS_BUTTON_A, WindowEvent.PRESS_BUTTON_B)
            for action in pressed
        ), pressed)

    def test_it_walks_once_pressing_has_not_worked(self):
        agent = self.make_agent()
        actions = self.actions(agent, MENU_PRESS_LIMIT * 2)
        self.assertIn(WindowEvent.PRESS_ARROW_DOWN, actions)

    def test_it_goes_back_to_pressing_if_walking_did_not_free_it_either(self):
        agent = self.make_agent()
        actions = self.actions(agent, MENU_PRESS_LIMIT * 3)
        self.assertIn(WindowEvent.PRESS_ARROW_DOWN, actions)
        self.assertIn(
            actions[-1], (WindowEvent.PRESS_BUTTON_A, WindowEvent.PRESS_BUTTON_B)
        )

    def test_a_closed_box_resets_the_count(self):
        agent = self.make_agent()
        self.actions(agent, MENU_PRESS_LIMIT)
        agent.memory_probe.menu = 0
        agent._follow_route("door-40", [(5, 11)])
        self.assertEqual(0, agent.route_menu_presses)


class EntryTileTests(unittest.TestCase):
    """Leaving a map nobody has a route for, by the door walked in through."""

    def make_agent(self, position, map_id):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.memory_probe = FakeMemory(position, map_id)
        agent.emulator = type("FakeEmulator", (), {"memory": agent.memory_probe})()
        agent._tile_truth = lambda: {}
        agent._visible_step = lambda dx, dy: None
        agent._planned_step = lambda *a: None
        agent.warp_memory = WarpMemory()
        return agent

    def test_the_arrival_tile_is_written_down(self):
        agent = self.make_agent((5, 11), 40)
        agent._follow_route("into-lab", [(5, 3)])
        agent.route_last_direction = "U"
        agent.memory_probe.position = (5, 10)
        agent._follow_route("into-lab", [(5, 3)])
        agent.memory_probe.map_id = 40
        agent.memory_probe.position = (5, 11)
        agent.route_last_position = (0, 12, 12)
        agent.route_last_direction = "U"
        agent._follow_route("into-lab", [(5, 3)])
        self.assertEqual((5, 11, "U"), agent.map_entry_tiles[40])

    def test_leaving_heads_for_that_tile(self):
        agent = self.make_agent((5, 1), 40)
        agent.map_entry_tiles = {40: (5, 11, "U")}
        self.assertEqual(
            WindowEvent.PRESS_ARROW_DOWN, agent._leave_unknown_map()
        )

    def test_standing_on_it_steps_back_out(self):
        agent = self.make_agent((5, 11), 40)
        agent.map_entry_tiles = {40: (5, 11, "U")}
        self.assertEqual(
            WindowEvent.PRESS_ARROW_DOWN, agent._leave_unknown_map()
        )


if __name__ == "__main__":
    unittest.main()
