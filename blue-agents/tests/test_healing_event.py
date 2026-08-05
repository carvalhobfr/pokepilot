import unittest

from hybrid_agent import HybridGymEnv


class HealingEventTests(unittest.TestCase):
    """Walking into a Center proves nothing; HP in RAM does.

    The pair walked into the Cerulean Center and came out, and the feed had
    nothing either way — the nurse dialogue can be skipped entirely, and an
    earlier crossing was made at 1 HP with no record of it.
    """

    def make_env(self, before, after, *, map_id=64, in_battle=False):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.logged = []
        env._log_event = lambda kind, data, live=True: env.logged.append((kind, data))
        env.read_m = lambda address: map_id if address == 0xD35E else 0
        env._map_name = lambda value: {
            64: "Cerulean Pokemon Center", 59: "Mt Moon",
        }.get(value, f"Map {value}")
        env.in_battle = in_battle
        env.last_party_info = before
        env.updated_panel = False
        env._update_agent_state = lambda: setattr(env, "updated_panel", True)
        env._track_healing(after)
        return env

    @staticmethod
    def mon(hp, max_hp=50, species=7):
        return {"species_id": species, "level": 20, "hp": hp, "max_hp": max_hp}

    def test_a_real_heal_is_confirmed_by_hp_and_publishes_the_party(self):
        env = self.make_env([self.mon(3)], [self.mon(50)])
        kinds = [kind for kind, _ in env.logged]
        self.assertEqual(["healed"], kinds)
        data = env.logged[0][1]
        self.assertEqual(47, data["hp_restored"])
        self.assertEqual("pokemon_center", data["source"])
        self.assertTrue(env.updated_panel)

    def test_a_party_already_at_full_health_reports_nothing(self):
        env = self.make_env([self.mon(50)], [self.mon(50)])
        self.assertEqual([], env.logged)

    def test_a_partial_heal_is_not_announced_as_a_heal(self):
        env = self.make_env([self.mon(3)], [self.mon(20)])
        self.assertEqual([], env.logged)

    def test_a_whiteout_is_a_death_not_a_heal(self):
        # A whiteout also restores full HP. It is a defeat, and `death` already
        # owns that story.
        env = self.make_env([self.mon(0)], [self.mon(50)])
        self.assertEqual([], env.logged)

    def test_healing_outside_a_center_is_labelled_as_item_or_event(self):
        env = self.make_env([self.mon(3)], [self.mon(50)], map_id=59)
        self.assertEqual("item_or_event", env.logged[0][1]["source"])


if __name__ == "__main__":
    unittest.main()
