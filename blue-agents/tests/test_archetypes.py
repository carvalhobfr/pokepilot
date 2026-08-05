import unittest

from archetypes import ARCHETYPES, archetype_for_slot, get_archetype
from hybrid_agent import GOT_POKEDEX_ADDRESS, GOT_POKEDEX_MASK, HybridGymEnv


class ArchetypeSelectionTests(unittest.TestCase):
    def test_a_declared_archetype_wins(self):
        self.assertEqual(
            "speedrunner", archetype_for_slot({"slot": 0, "archetype": "speedrunner"})
        )

    def test_a_roster_written_before_archetypes_spreads_the_styles(self):
        chosen = [archetype_for_slot({"slot": index}) for index in range(3)]
        self.assertEqual(len(set(chosen)), 3, "dois slots não podem jogar igual por acaso")

    def test_an_unknown_name_falls_back_instead_of_crashing_a_journey(self):
        self.assertIn(get_archetype("nao-existe"), ARCHETYPES.values())

    def test_traits_are_fixed_not_rolled(self):
        # A ±10 roll once pushed a trainer below every capture threshold and
        # the run finished with a single Pokémon; it looked like a policy bug.
        first = get_archetype("completionist")["traits"]
        second = get_archetype("completionist")["traits"]
        self.assertEqual(first, second)


class ArchetypeCaptureStanceTests(unittest.TestCase):
    def make_env(self, stance, *, party, collector=50, meta=50):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.collector = collector
        env.meta_score = meta
        env.capture_enabled = True
        env.last_battle_is_trainer = False
        env.capture_stance = stance
        env.get_party_info = lambda: list(party)
        ram = {GOT_POKEDEX_ADDRESS: GOT_POKEDEX_MASK}
        env.read_m = lambda address: ram.get(address, 0)
        env._poke_ball_count = lambda: 5
        env._select_capture_ball = lambda shiny_candidate=False: {"item_id": 4, "slot": 0}
        return env

    @staticmethod
    def weakened_new_species():
        return {
            "enemy_species_id": 41,
            "enemy_level": 8,
            "shiny_candidate": False,
            "enemy_hp": 2,
            "enemy_max_hp": 25,
            "active_pokemon": {"hp": 40, "max_hp": 40, "level": 12},
        }

    def full_party(self):
        return [{"species_id": 10 + index, "level": 20} for index in range(6)]

    def test_the_completionist_catches_a_new_species_with_a_full_party(self):
        env = self.make_env("every_new_species", party=self.full_party(), collector=95)
        decision = env._capture_policy(self.weakened_new_species())
        self.assertEqual("capture", decision["choice"])
        self.assertEqual("completionist_new_species", decision["reason_code"])

    def test_the_speedrunner_skips_a_catch_once_it_has_a_backup(self):
        env = self.make_env(
            "only_when_needed",
            party=[{"species_id": 4, "level": 20}, {"species_id": 16, "level": 12}],
            collector=15,
        )
        decision = env._capture_policy(self.weakened_new_species())
        self.assertEqual("defeat", decision["choice"])
        self.assertEqual("rush_skips_capture", decision["reason_code"])

    def test_even_the_speedrunner_catches_a_spare_while_alone(self):
        # A whiteout costs far more than a Poké Ball, and a lone starter is one
        # bad battle away from restarting the whole crossing.
        env = self.make_env(
            "only_when_needed", party=[{"species_id": 4, "level": 20}], collector=15
        )
        decision = env._capture_policy(self.weakened_new_species())
        self.assertEqual("capture", decision["choice"])

    def test_the_team_builder_keeps_the_old_team_value_rules(self):
        env = self.make_env(
            "team_value_only", party=self.full_party(), collector=65, meta=95
        )
        decision = env._capture_policy(self.weakened_new_species())
        self.assertNotEqual("completionist_new_species", decision["reason_code"])


if __name__ == "__main__":
    unittest.main()
