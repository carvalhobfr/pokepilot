import time
import unittest

from hybrid_agent import HybridGymEnv


class PlaybackThrottleTests(unittest.TestCase):
    """The throttle exists so a human can follow the arena.

    With every dashboard closed it buys nothing and costs everything: the same
    binary went from 4 to 446 PPO steps/s on an M1 with it removed.
    """

    def make_env(self, *, speed, viewers, agent_count=1, act_freq=24):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.playback_speed = speed
        env.viewer_count = viewers
        env.agent_count = agent_count
        env.act_freq = act_freq
        return env

    def elapsed(self, env):
        started = time.monotonic()
        env._apply_playback_throttle(started)
        return time.monotonic() - started

    def test_nobody_watching_means_no_sleep_at_all(self):
        env = self.make_env(speed=1.0, viewers=0)
        self.assertLess(self.elapsed(env), 0.02)

    def test_an_open_dashboard_gets_the_watchable_pace_back(self):
        env = self.make_env(speed=1.0, viewers=1)
        # 24 frames at 60 fps is 0.4s of Game Boy time for a single agent.
        self.assertGreater(self.elapsed(env), 0.2)

    def test_explicit_training_speed_still_wins_over_an_audience(self):
        env = self.make_env(speed=0.0, viewers=3)
        self.assertLess(self.elapsed(env), 0.02)

    def test_more_agents_share_one_vector_step(self):
        # DummyVecEnv steps agents in sequence, so each one only owes its share
        # of the wall-clock budget.
        alone = self.make_env(speed=1.0, viewers=1, agent_count=1)
        crowded = self.make_env(speed=1.0, viewers=1, agent_count=8)
        self.assertGreater(self.elapsed(alone), self.elapsed(crowded))


if __name__ == "__main__":
    unittest.main()
