import unittest

from area_knowledge import (
    AREA_TARGET_EARLY,
    AREA_TARGET_POSTGAME,
    area_coverage,
    area_key,
    area_species,
    area_target,
)
from archetypes import get_archetype
from hybrid_agent import GOT_POKEDEX_ADDRESS, GOT_POKEDEX_MASK, HybridGymEnv


class AreaKnowledgeTests(unittest.TestCase):
    def test_ram_map_names_resolve_to_pokeapi_areas(self):
        self.assertEqual("viridian-forest-area", area_key("Viridian Forest"))
        self.assertEqual("kanto-route-1-area", area_key("Route 1"))
        self.assertEqual("mt-moon-b2f", area_key("Mt Moon B2F"))
        self.assertEqual("pallet-town-area", area_key("Pallet Town"))

    def test_a_map_with_no_encounter_table_is_not_a_failure(self):
        self.assertIsNone(area_key("Pewter Gym"))
        self.assertIsNone(area_coverage("Pewter Gym", {1, 2, 3}))

    def test_viridian_forest_knows_its_five_species(self):
        # Caterpie, Metapod, Weedle, Kakuna, Pikachu.
        self.assertEqual(5, len(area_species("Viridian Forest")))

    def test_coverage_counts_only_what_lives_there(self):
        forest = area_species("Viridian Forest")
        owned = set(list(forest)[:2]) | {143}  # Snorlax não é da Floresta
        coverage = area_coverage("Viridian Forest", owned)
        self.assertEqual(2, coverage["owned"])
        self.assertEqual(5, coverage["total"])
        self.assertAlmostEqual(0.4, coverage["fraction"])

    def test_the_target_only_becomes_literal_after_the_league(self):
        # Surf and the fishing rods gate whole encounter tables; demanding 100%
        # on Route 1 would park a bot there forever.
        self.assertEqual(AREA_TARGET_EARLY, area_target(0))
        self.assertEqual(AREA_TARGET_EARLY, area_target(7))
        self.assertEqual(AREA_TARGET_POSTGAME, area_target(8))


class CompletionistCoverageTests(unittest.TestCase):
    def make_env(self, *, coverage, badges, party):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.collector = 95
        env.meta_score = 60
        env.capture_enabled = True
        env.last_battle_is_trainer = False
        env.capture_stance = get_archetype("completionist")["capture_stance"]
        env.get_party_info = lambda: list(party)
        ram = {GOT_POKEDEX_ADDRESS: GOT_POKEDEX_MASK}
        env.read_m = lambda address: ram.get(address, 0)
        env._poke_ball_count = lambda: 5
        env._select_capture_ball = lambda shiny_candidate=False: {"item_id": 4, "slot": 0}
        env._area_coverage = lambda: coverage
        env._badge_count = lambda: badges
        return env

    @staticmethod
    def encounter():
        return {
            "enemy_species_id": 41,
            "enemy_level": 8,
            "shiny_candidate": False,
            "enemy_hp": 2,
            "enemy_max_hp": 25,
            "active_pokemon": {"hp": 40, "max_hp": 40, "level": 12},
        }

    def full_party(self):
        return [{"species_id": 100 + index, "level": 30} for index in range(6)]

    def test_below_the_area_target_it_keeps_catching(self):
        env = self.make_env(
            coverage={"owned": 1, "total": 5, "fraction": 0.2},
            badges=1, party=self.full_party(),
        )
        decision = env._capture_policy(self.encounter())
        self.assertEqual("capture", decision["choice"])
        self.assertEqual("completionist_new_species", decision["reason_code"])

    def test_above_the_early_target_it_moves_on(self):
        env = self.make_env(
            coverage={"owned": 4, "total": 5, "fraction": 0.8},
            badges=1, party=self.full_party(),
        )
        decision = env._capture_policy(self.encounter())
        self.assertEqual("defeat", decision["choice"])
        self.assertEqual("completionist_area_satisfied", decision["reason_code"])

    def test_after_the_league_the_same_area_is_worth_finishing(self):
        env = self.make_env(
            coverage={"owned": 4, "total": 5, "fraction": 0.8},
            badges=8, party=self.full_party(),
        )
        decision = env._capture_policy(self.encounter())
        self.assertEqual("capture", decision["choice"])

    def test_a_free_party_slot_still_wins_over_a_finished_area(self):
        env = self.make_env(
            coverage={"owned": 5, "total": 5, "fraction": 1.0},
            badges=1, party=[{"species_id": 1, "level": 20}],
        )
        decision = env._capture_policy(self.encounter())
        self.assertEqual("capture", decision["choice"])


if __name__ == "__main__":
    unittest.main()
