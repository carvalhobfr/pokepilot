import sys
from pathlib import Path
import unittest

from pyboy.utils import WindowEvent

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.scripted_agent import ScriptedAgent


MT_MOON_B2F_ROUTE = [
    (21, 17), (22, 17), (23, 17), (23, 14), (27, 14),
    (27, 16), (33, 16), (33, 14), (36, 14), (36, 24),
    (32, 24), (32, 31), (10, 31), (10, 18), (10, 17),
    (12, 17), (12, 9), (13, 9), (13, 7), (13, 5),
    (12, 5), (12, 4), (3, 4), (3, 7), (5, 7),
]


class FakeRouteMemory:
    def __init__(self, position, map_id=61):
        self.position = position
        self.map_id = map_id

    def get_player_pos(self):
        return self.position

    def get_map_id(self):
        return self.map_id

    def read_byte(self, _address):
        return 0


class ScriptedRouteTests(unittest.TestCase):
    def make_agent(self, position):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.emulator = type("FakeEmulator", (), {
            "memory": FakeRouteMemory(position),
        })()
        return agent

    def test_resumed_route_continues_after_exact_mid_route_waypoint(self):
        agent = self.make_agent((3, 4))
        action = agent._follow_route("mt-moon-61", MT_MOON_B2F_ROUTE)
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, action)

    def test_resumed_route_returns_to_closest_safe_waypoint(self):
        agent = self.make_agent((16, 4))
        action = agent._follow_route("mt-moon-61", MT_MOON_B2F_ROUTE)
        self.assertEqual(WindowEvent.PRESS_ARROW_LEFT, action)

    def test_blocked_route_advances_text_once_then_steps_aside(self):
        # An NPC standing on the path never clears with A. Before the sidestep,
        # a bot burned thousands of steps pressing A at an occupied tile.
        agent = self.make_agent((16, 4))
        actions = [
            agent._follow_route("mt-moon-61", MT_MOON_B2F_ROUTE)
            for _ in range(24)
        ]
        self.assertEqual(WindowEvent.PRESS_ARROW_LEFT, actions[0])
        self.assertIn(WindowEvent.PRESS_BUTTON_A, actions, "diálogo deve ser tentado")

        after_first_a = actions[actions.index(WindowEvent.PRESS_BUTTON_A) + 1:]
        self.assertTrue(
            any(
                action in (WindowEvent.PRESS_ARROW_DOWN, WindowEvent.PRESS_ARROW_UP)
                for action in after_first_a
            ),
            "rota travada precisa desviar no eixo livre, não repetir A",
        )

    def test_movement_resets_the_stuck_recovery(self):
        agent = self.make_agent((16, 4))
        for _ in range(6):
            agent._follow_route("mt-moon-61", MT_MOON_B2F_ROUTE)
        agent.emulator.memory.position = (15, 4)
        agent._follow_route("mt-moon-61", MT_MOON_B2F_ROUTE)
        self.assertEqual(0, agent.route_stuck_cycles)


if __name__ == "__main__":
    unittest.main()
