"""Dying is a cycle, not a stumble: attempt 1 and attempt 2 are told apart."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from hybrid_agent import HybridGymEnv

from src.route_trails import TrailRecorder


class DeathCycleTests(unittest.TestCase):
    def make_env(self, walked=()):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.logged = []
        env._log_event = lambda kind, data, live=True: env.logged.append((kind, data))
        env.agent_name = "AARON"
        env.deaths = 1
        env.death_cycle = 0
        env.active_quest_id = "viridian_forest_nav"
        env.persisted = 0
        env._persist_journey_memory = lambda: setattr(
            env, "persisted", env.persisted + 1
        )

        agent = type("FakeScripted", (), {})()
        agent.trail_recorder = TrailRecorder()
        agent.begin_death_cycle = agent.trail_recorder.restart
        for x, y in walked:
            agent.trail_recorder.record("viridian_forest_nav", 51, x, y)
        env.scripted_agent = agent
        return env

    def test_the_cycle_is_numbered_and_reported(self):
        env = self.make_env(walked=[(15, 47), (15, 46), (15, 45)])
        facts = env._close_death_cycle()
        self.assertEqual(1, facts["death_cycle"])
        self.assertEqual(3, facts["steps_in_cycle"])
        self.assertEqual("viridian_forest_nav", facts["quest_id"])

    def test_a_second_death_is_a_second_cycle(self):
        env = self.make_env(walked=[(15, 47)])
        env._close_death_cycle()
        env.scripted_agent.trail_recorder.record("viridian_forest_nav", 51, 17, 47)
        facts = env._close_death_cycle()
        self.assertEqual(2, facts["death_cycle"])
        self.assertEqual(1, facts["steps_in_cycle"])

    def test_the_attempt_that_died_is_dropped_from_the_trail(self):
        env = self.make_env(walked=[(15, 47), (15, 46)])
        env._close_death_cycle()
        self.assertEqual([], env.scripted_agent.trail_recorder.legs())

    def test_a_trail_failure_never_takes_the_journey_down(self):
        # The recorder is bookkeeping. A death is already the bad news.
        env = self.make_env()
        env.scripted_agent.begin_death_cycle = lambda cycle: 1 / 0
        facts = env._close_death_cycle()
        self.assertEqual(1, facts["death_cycle"])
        self.assertEqual(0, facts["steps_in_cycle"])

    def test_an_agent_without_a_recorder_is_not_an_error(self):
        env = self.make_env()
        env.scripted_agent = object()
        self.assertEqual(0, env._close_death_cycle()["steps_in_cycle"])

    def test_the_count_is_written_down_so_it_outlives_the_process(self):
        # A chunk is a fresh env with the counter back at zero. Without this,
        # every whiteout logged itself as cycle 1 — four in a row did — and
        # "attempt 1 versus attempt 2" was never measurable.
        env = self.make_env()
        env._close_death_cycle()
        self.assertEqual(1, env.persisted)


if __name__ == "__main__":
    unittest.main()
