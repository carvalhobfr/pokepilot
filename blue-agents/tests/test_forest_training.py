"""Train before the Forest, because the bug catchers are what kill.

Both trainers walked into the same one ten steps in, lost the whole party, and
walked back from Pallet to do it again. The wild Pokémon in that grass are
level 3 Caterpie; the levels are there for the taking.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.scripted_agent import (
    FOREST_MIN_LEVEL,
    FOREST_TRAINING_STEPS,
    ScriptedAgent,
)


class PartyMemory:
    """Levels and HP where the cartridge keeps them."""

    def __init__(self, party, position=(20, 43), map_id=51):
        self.party = party
        self.position = position
        self.map_id = map_id

    def get_party_count(self):
        return len(self.party)

    def get_player_pos(self):
        return self.position

    def get_map_id(self):
        return self.map_id

    def read_byte(self, address):
        index, offset = divmod(address - 0xD16B, 44)
        if not 0 <= index < len(self.party):
            return 0
        level, hp, max_hp = self.party[index]
        if offset == 33:
            return level
        if offset == 1:
            return hp >> 8
        if offset == 2:
            return hp & 0xFF
        if offset == 34:
            return max_hp >> 8
        if offset == 35:
            return max_hp & 0xFF
        return 0


def agent_with(party, position=(20, 43)):
    agent = ScriptedAgent.__new__(ScriptedAgent)
    memory = PartyMemory(party, position=position)
    agent.emulator = type("FakeEmulator", (), {"memory": memory})()
    agent.memory_probe = memory
    return agent


class TrainingGateTests(unittest.TestCase):
    def setUp(self):
        # The gate is off by default: every version of *where* to grind was
        # wrong on the cartridge, so shipping it on would be a regression.
        ligado = mock.patch.dict(os.environ, {"POKEAI_FOREST_TRAINING": "1"})
        ligado.start()
        self.addCleanup(ligado.stop)

    def test_it_is_off_unless_the_operator_asks_for_it(self):
        with mock.patch.dict(os.environ, {"POKEAI_FOREST_TRAINING": "0"}):
            self.assertFalse(agent_with([(4, 20, 20)])._needs_forest_training())

    def test_an_under_levelled_party_trains_first(self):
        agent = agent_with([(8, 26, 26), (5, 20, 20)])
        self.assertTrue(agent._needs_forest_training())

    def test_a_party_at_the_target_crosses(self):
        agent = agent_with([(FOREST_MIN_LEVEL, 30, 30)])
        self.assertFalse(agent._needs_forest_training())

    def test_the_highest_level_is_what_counts(self):
        # A level 4 Caterpie in the back does not make the lead too weak.
        agent = agent_with([(FOREST_MIN_LEVEL + 2, 40, 40), (4, 18, 18)])
        self.assertEqual(FOREST_MIN_LEVEL + 2, agent._party_max_level())
        self.assertFalse(agent._needs_forest_training())

    def test_training_gives_up_rather_than_pacing_forever(self):
        # A gate with no way out is worse than a death. If the grass will not
        # deliver the levels, the crossing is attempted anyway.
        agent = agent_with([(8, 26, 26)])
        agent.forest_training_steps = FOREST_TRAINING_STEPS
        self.assertFalse(agent._needs_forest_training())

    def test_reaching_the_target_clears_the_budget(self):
        # So a second stretch of training later starts with a full budget.
        agent = agent_with([(FOREST_MIN_LEVEL, 30, 30)])
        agent.forest_training_steps = 500
        agent._needs_forest_training()
        self.assertEqual(0, agent.forest_training_steps)


class TrainingWalkTests(unittest.TestCase):
    """The screen says where the grass is; nothing here is a hand-picked line."""

    def trainee(self, grass, position=(31, 24), warps=()):
        agent = agent_with([(8, 26, 26)], position=position)
        agent._tile_reader = lambda: type("FakeReader", (), {
            "grass_offsets": staticmethod(lambda: list(grass)),
            "warp_tiles": staticmethod(lambda: set(warps)),
        })()
        agent.seen = {}
        agent._follow_route = lambda route_id, waypoints: agent.seen.update(
            {"route": route_id, "waypoints": waypoints}
        )
        return agent

    def test_grass_beside_the_trainer_is_a_step(self):
        agent = self.trainee([(-1, 0)])
        agent._train_in_forest_entrance()
        self.assertEqual("forest-training", agent.seen["route"])
        self.assertEqual([(30, 24)], agent.seen["waypoints"])

    def test_grass_it_would_have_to_walk_to_is_left_alone(self):
        # Every version that walked somewhere walked into the bug catcher:
        # aiming at the farthest patch went north, and the fallback search
        # detoured north around the trees to the same place.
        agent = self.trainee([(-3, -3), (-4, 0), (0, 2)])
        self.assertIsNone(agent._train_in_forest_entrance())
        self.assertEqual({}, agent.seen)

    def test_no_grass_at_all_hands_the_step_back_to_the_crossing(self):
        agent = self.trainee([])
        self.assertIsNone(agent._train_in_forest_entrance())

    def test_the_tile_underfoot_is_not_a_step(self):
        # Standing still rolls no encounter.
        agent = self.trainee([(0, 0)])
        self.assertIsNone(agent._train_in_forest_entrance())

    def test_the_pair_is_kept_instead_of_re_picked_every_step(self):
        # Re-picking every step is how a plan starts bouncing between tiles.
        agent = self.trainee([(-1, 0), (0, -1)])
        agent._train_in_forest_entrance()
        first = agent.seen["waypoints"]
        agent._train_in_forest_entrance()
        self.assertEqual(first, agent.seen["waypoints"])

    def test_it_steps_back_where_it_came_from(self):
        # "Nearest grass" picks the same corner of the patch every time, which
        # is a fixed heading: the trainer walked fourteen tiles up the grass
        # column doing that and arrived at the bug catcher. A pair cannot drift.
        agent = self.trainee([(-1, 0)])
        agent._train_in_forest_entrance()
        self.assertEqual([(30, 24)], agent.seen["waypoints"])
        agent.memory_probe.position = (30, 24)
        agent._train_in_forest_entrance()
        self.assertEqual([(31, 24)], agent.seen["waypoints"])

    def test_a_pair_it_is_no_longer_standing_in_is_rebuilt(self):
        # A whiteout drops the party somewhere else entirely.
        agent = self.trainee([(-1, 0)])
        agent._train_in_forest_entrance()
        agent.forest_training_pair = ((90, 90), (91, 90))
        agent._train_in_forest_entrance()
        self.assertEqual([(30, 24)], agent.seen["waypoints"])

    def test_only_one_of_the_pair_has_to_be_grass(self):
        # The other is simply where it came from. Requiring both broke the
        # pair on arrival every time, which is the drift under another name.
        agent = self.trainee([(-1, 0)])
        agent._train_in_forest_entrance()
        agent.memory_probe.position = (30, 24)
        agent._train_in_forest_entrance()
        agent.memory_probe.position = (31, 24)
        agent._train_in_forest_entrance()
        self.assertEqual([(30, 24)], agent.seen["waypoints"])

    def test_only_real_steps_spend_the_budget(self):
        # A step not taken is not a step paid for; otherwise the budget runs
        # out while crossing and the gate turns itself off for nothing.
        agent = self.trainee([])
        agent._train_in_forest_entrance()
        agent._train_in_forest_entrance()
        self.assertEqual(0, getattr(agent, "forest_training_steps", 0))

    def test_a_doorway_is_never_stepped_into_for_grass(self):
        # `_follow_route` only blocks warp steps while it is not aiming at its
        # last waypoint, and a training target is always the last one — so on
        # the Forest entrance the step back through the door was wide open,
        # and BARON crossed gate to Forest and back every single frame.
        agent = self.trainee([(-1, 0)], position=(17, 47), warps=[(16, 47)])
        self.assertIsNone(agent._train_in_forest_entrance())


if __name__ == "__main__":
    unittest.main()
