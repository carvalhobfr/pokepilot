"""The nearest Center and the nearest Mart, found by asking the map.

Every route to a Center or a Mart in this project was measured by hand for one
city. `buy_pokeballs` only knows the way back to Viridian's Mart, so AARON spent
its last Poké Ball on Route 1 and had no way to buy another — the capture policy
kept correctly answering "defeat, no_pokeballs" for the rest of the run.

The warp table already answered this. Its fourth byte per entry says which map
each door leads to; only the first two, the door's position, were ever read.
"""

import sys
import unittest
from pathlib import Path

from pyboy.utils import WindowEvent

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.scripted_agent import (
    POKEMON_CENTER_MAP_IDS,
    POKE_MART_MAP_IDS,
    SHOP_COUNTER_TILE,
    ScriptedAgent,
)

from tests.test_route_following import FakeMemory


class DoorFindingTests(unittest.TestCase):
    # Viridian's shape: the Center and the Mart are two of the city's doors.
    CITY_DOORS = {(23, 25): 41, (33, 19): 42, (17, 27): 39}

    def agent_at(self, position, map_id=1, doors=None):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.memory_probe = FakeMemory(position, map_id)
        agent.emulator = type("FakeEmulator", (), {"memory": agent.memory_probe})()
        agent._tile_reader = lambda: type("FakeReader", (), {
            "warp_destinations": staticmethod(
                lambda: dict(self.CITY_DOORS if doors is None else doors)
            ),
        })()
        agent.seen = {}
        agent._follow_route = lambda route_id, waypoints: agent.seen.update(
            {"route": route_id, "waypoints": waypoints}
        )
        return agent

    def test_the_center_door_is_read_from_the_map(self):
        agent = self.agent_at((23, 30))
        self.assertEqual((23, 25), agent._door_to(POKEMON_CENTER_MAP_IDS))

    def test_the_mart_door_is_read_from_the_map(self):
        agent = self.agent_at((23, 30))
        self.assertEqual((33, 19), agent._door_to(POKE_MART_MAP_IDS))

    def test_the_nearest_of_several_wins(self):
        doors = {(5, 5): 41, (30, 30): 58}
        self.assertEqual(
            (30, 30), self.agent_at((28, 30), doors=doors)._door_to(POKEMON_CENTER_MAP_IDS)
        )

    def test_a_map_with_no_such_door_says_so(self):
        # The Forest has two doors and neither is a shop.
        agent = self.agent_at((17, 40), map_id=51, doors={(17, 47): 50, (1, 0): 47})
        self.assertIsNone(agent._door_to(POKEMON_CENTER_MAP_IDS))
        self.assertIsNone(agent._door_to(POKE_MART_MAP_IDS))

    def test_walking_there_aims_at_the_door(self):
        agent = self.agent_at((23, 30))
        agent._run_nearest_center()
        self.assertEqual([(23, 25)], agent.seen["waypoints"])

    def test_a_door_carries_its_own_route_id(self):
        # Two different doors must not share a stale waypoint index.
        first = self.agent_at((23, 30))
        first._run_nearest_center()
        second = self.agent_at((5, 5), doors={(5, 1): 58})
        second._run_nearest_center()
        self.assertNotEqual(first.seen["route"], second.seen["route"])

    def test_no_door_and_no_route_rather_than_a_wrong_one(self):
        agent = self.agent_at((17, 40), map_id=51, doors={(17, 47): 50})
        self.assertIsNone(agent._run_nearest_mart())
        self.assertEqual({}, agent.seen)


class ShopCounterTests(unittest.TestCase):
    """Inside a Mart. Gen I builds the same shop in every city."""

    class ShopMemory(FakeMemory):
        def __init__(self, position, facing=0):
            super().__init__(position, 42)
            self.facing = facing

        def read_byte(self, address):
            if address == 0xD52A:
                return self.facing
            return super().read_byte(address)

    def agent_at(self, position, facing=0):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        memory = self.ShopMemory(position, facing)
        agent.emulator = type("FakeEmulator", (), {"memory": memory})()
        agent.memory_probe = memory
        agent.seen = {}
        agent._follow_route = lambda route_id, waypoints: agent.seen.update(
            {"route": route_id, "waypoints": waypoints}
        )
        agent._buy_first_shop_item = lambda: "BOUGHT"
        return agent

    def test_it_walks_to_the_counter_first(self):
        agent = self.agent_at((3, 7))
        agent._run_shop_counter()
        self.assertEqual(SHOP_COUNTER_TILE, agent.seen["waypoints"][-1])

    def test_at_the_counter_it_turns_to_the_clerk(self):
        agent = self.agent_at(SHOP_COUNTER_TILE, facing=0)
        self.assertEqual(
            WindowEvent.PRESS_ARROW_LEFT, agent._run_shop_counter()
        )

    def test_facing_the_clerk_it_buys(self):
        agent = self.agent_at(SHOP_COUNTER_TILE, facing=2)
        self.assertEqual("BOUGHT", agent._run_shop_counter())

    def test_inside_a_mart_the_controller_goes_straight_to_the_counter(self):
        agent = self.agent_at((3, 7))
        agent._run_nearest_mart()
        self.assertEqual(SHOP_COUNTER_TILE, agent.seen["waypoints"][-1])


class KnownShopTests(unittest.TestCase):
    def test_only_measured_mart_ids_are_claimed(self):
        # A wrong id sends a trainer through the wrong door. Viridian's is the
        # one this project has walked into and bought from; the set grows by
        # measurement, never by memory.
        self.assertEqual({42}, POKE_MART_MAP_IDS)

    def test_the_center_set_is_shared_rather_than_copied(self):
        from hybrid_agent import POKEMON_CENTER_MAP_IDS as from_env

        self.assertIs(POKEMON_CENTER_MAP_IDS, from_env)


if __name__ == "__main__":
    unittest.main()
