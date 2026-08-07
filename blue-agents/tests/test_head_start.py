"""The head start ends when there is something to inherit, not on a count."""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from hybrid_agent import HybridGymEnv

from src.route_trails import TrailStore


class Node:
    def __init__(self, executor):
        self.executor = executor


class Graph:
    def __init__(self, nodes_by_id):
        self.nodes_by_id = nodes_by_id


class TrailToInheritTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = TrailStore(self.directory.name)

    def make_env(self, quest_id="viridian_forest_nav"):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.active_quest_id = quest_id
        env.quest_graph = Graph(
            {"viridian_forest_nav": Node("viridian_forest_nav")}
        )
        env.scripted_agent = type("FakeScripted", (), {})()
        env.scripted_agent.trail_store = self.store
        return env

    def test_nothing_published_means_keep_waiting(self):
        self.assertFalse(self.make_env()._trail_ready_to_inherit())

    def test_a_walked_crossing_ends_the_wait(self):
        self.store.publish(
            "viridian_forest_nav", "AARON",
            [{"map": 51, "points": [[15, 47], [15, 46]]}], dense=True,
        )
        self.assertTrue(self.make_env()._trail_ready_to_inherit())

    def test_mined_anchors_are_not_something_to_inherit(self):
        # The stumps already on disk would end every wait instantly and the
        # follower would start with nothing better than the drawn route.
        self.store.publish(
            "viridian_forest_nav", "minerada:AARON",
            [{"map": 51, "points": [[15, 47], [1, 18]]}],
        )
        self.assertFalse(self.make_env()._trail_ready_to_inherit())

    def test_a_trail_for_another_quest_does_not_count(self):
        self.store.publish(
            "parcel_event", "AARON",
            [{"map": 40, "points": [[5, 3], [5, 4]]}], dense=True,
        )
        self.assertFalse(self.make_env()._trail_ready_to_inherit())

    def test_no_objective_yet_keeps_waiting(self):
        self.assertFalse(self.make_env(quest_id=None)._trail_ready_to_inherit())


if __name__ == "__main__":
    unittest.main()
