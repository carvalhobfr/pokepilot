"""Inside a Center, heal — before any executor gets a say.

AARON crossed the Forest, reached Pewter, walked into its Center at 53% with a
fainted Caterpie, and stopped. `_run_pewter_city_nav` only enters the Center
branch when `_party_needs_healing()` says yes, and that gate is 20%. Nothing
matched, so it fell through to the unknown-map fallback and stood still.

Every executor that can end up in a Center has the same hole, so the rule lives
ahead of all of them.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.scripted_agent import (
    POKEMON_CENTER_MAP_IDS,
    VIRIDIAN_CENTER_MAP_ID,
    ScriptedAgent,
)


class CenterMemory:
    def __init__(self, map_id, party):
        self.map_id = map_id
        self.party = party

    def get_map_id(self):
        return self.map_id

    def get_player_pos(self):
        return (11, 5)

    def get_party_count(self):
        return len(self.party)

    def read_byte(self, address):
        index, offset = divmod(address - 0xD16B, 44)
        if not 0 <= index < len(self.party):
            return 0
        hp, max_hp = self.party[index]
        if offset == 1:
            return hp >> 8
        if offset == 2:
            return hp & 0xFF
        if offset == 34:
            return max_hp >> 8
        if offset == 35:
            return max_hp & 0xFF
        return 0


class HealBeforeAnythingElseTests(unittest.TestCase):
    # AARON's real party, read from the panel while it was frozen.
    HURT = [(11, 37), (0, 18), (18, 18), (20, 20)]
    WHOLE = [(37, 37), (18, 18), (18, 18), (20, 20)]

    def agent_in(self, map_id, party, doors=None):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        memory = CenterMemory(map_id, party)
        agent.emulator = type("FakeEmulator", (), {"memory": memory})()
        agent.called = []
        agent.walked = []
        agent._run_pokemon_center = lambda prefix, healed: agent.called.append(
            (prefix, healed)
        ) or "HEALING"
        agent._tile_reader = lambda: type("FakeReader", (), {
            "warp_destinations": staticmethod(lambda: dict(doors or {})),
        })()
        agent._follow_route = lambda route_id, waypoints: agent.walked.append(
            (route_id, waypoints)
        ) or "WALKING"
        return agent

    def step(self, agent):
        return agent._center_first_action()

    def test_a_hurt_party_in_pewters_center_heals(self):
        agent = self.agent_in(58, self.HURT)
        self.assertEqual("HEALING", self.step(agent))
        self.assertEqual([("center-58", "center_58_healed")], agent.called)

    def test_fifty_three_percent_is_enough_to_heal_once_inside(self):
        # The emergency gate is 20% and stays 20% for travelling. Inside, the
        # trip is already paid for.
        agent = self.agent_in(58, self.HURT)
        self.assertLess(agent._party_health_fraction(), 1.0)
        self.assertGreater(agent._party_health_fraction(), 0.2)
        self.assertEqual("HEALING", self.step(agent))

    def test_a_healed_party_inside_still_gets_the_center_controller(self):
        # It owns leaving, not just healing. Gating the whole controller on
        # "is anything missing" left AARON healed on Pewter's doormat with
        # nothing left to press it, and the executor has no branch for a whole
        # party in a Center either.
        agent = self.agent_in(58, self.WHOLE)
        self.assertEqual("HEALING", self.step(agent))
        self.assertEqual([("center-58", "center_58_healed")], agent.called)

    def test_a_center_door_on_this_map_is_worth_the_detour(self):
        # Not for the HP: a confirmed heal is the only thing that writes a
        # checkpoint, and a checkpoint is what makes a whiteout cost the
        # stretch instead of the run.
        agent = self.agent_in(2, self.HURT, doors={(13, 25): 58, (16, 17): 54})
        self.assertEqual("WALKING", self.step(agent))
        self.assertEqual([("center-door-13-25", [(13, 25)])], agent.walked)

    def test_a_whole_party_walks_straight_past_it(self):
        agent = self.agent_in(2, self.WHOLE, doors={(13, 25): 58})
        self.assertIsNone(self.step(agent))
        self.assertEqual([], agent.walked)

    def test_entering_and_healing_use_the_same_threshold(self):
        # Two different numbers — one deciding to enter, another refusing to
        # heal — is what turned the door into a revolving one.
        outside = self.agent_in(2, self.HURT, doors={(13, 25): 58})
        inside = self.agent_in(58, self.HURT)
        self.assertIsNotNone(self.step(outside))
        self.assertIsNotNone(self.step(inside))

    def test_viridian_keeps_its_own_milestone_name(self):
        # `viridian_center_healed` is read outside this class as the story
        # milestone for the first Center.
        agent = self.agent_in(VIRIDIAN_CENTER_MAP_ID, self.HURT)
        self.step(agent)
        self.assertEqual(
            [("viridian-center", "viridian_center_healed")], agent.called
        )

    def test_a_city_without_a_center_door_is_left_to_the_executor(self):
        # A Center a city away is a trip, and trips still belong to the routes.
        agent = self.agent_in(14, self.HURT, doors={})
        self.assertIsNone(self.step(agent))
        self.assertEqual([], agent.called)

    def test_the_rule_covers_every_known_center(self):
        for map_id in POKEMON_CENTER_MAP_IDS:
            agent = self.agent_in(map_id, self.HURT)
            self.assertEqual("HEALING", self.step(agent), f"mapa {map_id}")


if __name__ == "__main__":
    unittest.main()
