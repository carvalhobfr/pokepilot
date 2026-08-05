import unittest

from area_knowledge import (
    AREA_TARGET,
    area_coverage,
    area_key,
    area_species,
    area_target,
    encounter_chance,
    is_rare_here,
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

    def test_the_target_is_everything_reachable_at_any_stage(self):
        # A fração era só um substituto para "a área guarda coisas que não
        # alcanço"; com o método do encontro respondendo isso, o alvo honesto é
        # tudo. Quem cresce com as insígnias é o conjunto alcançável.
        self.assertEqual(AREA_TARGET, area_target(0))
        self.assertEqual(AREA_TARGET, area_target(8))
        self.assertEqual(1.0, AREA_TARGET)


class ReachabilityTests(unittest.TestCase):
    """Raro e impossível são coisas diferentes.

    Uma espécie que só aparece surfando não existe para quem ainda não tem
    Surf, e contá-la deixaria o completista perseguindo uma área que ele não
    tem como fechar.
    """

    def test_a_lake_species_does_not_exist_without_a_rod(self):
        # Rota 12: Bellsprout na grama, Krabby só na super vara.
        walking = area_species("Route 12", badges=1)
        self.assertIn(69, walking, "Bellsprout é da grama")
        self.assertNotIn(98, walking, "Krabby exige super vara")

    def test_the_same_area_grows_when_the_rods_arrive(self):
        early = area_species("Route 12", badges=1)
        late = area_species("Route 12", badges=8)
        self.assertLess(len(early), len(late))
        self.assertIn(98, late)

    def test_an_area_that_is_all_water_is_no_target_at_all_yet(self):
        self.assertIsNone(area_coverage("Sea Route 19", set(), badges=1))

    def test_coverage_ignores_what_cannot_be_met_yet(self):
        coverage = area_coverage("Route 12", set(), badges=1)
        self.assertEqual(coverage["total"], len(area_species("Route 12", badges=1)))


class RarityTests(unittest.TestCase):
    def test_pikachu_is_the_rarity_of_viridian_forest(self):
        # 5% contra 45% de Caterpie. Confirmado na PokéAPI, versão blue.
        self.assertEqual(5, encounter_chance("Viridian Forest", 25))
        self.assertEqual(45, encounter_chance("Viridian Forest", 10))
        self.assertTrue(is_rare_here("Viridian Forest", 25))
        self.assertFalse(is_rare_here("Viridian Forest", 10))

    def test_a_species_that_does_not_live_here_is_not_rare_here(self):
        self.assertFalse(is_rare_here("Viridian Forest", 143))


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
        env._map_name = lambda map_id=None: "Pewter Gym"
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

    def test_one_missing_species_still_counts_as_unfinished(self):
        env = self.make_env(
            coverage={"owned": 4, "total": 5, "fraction": 0.8},
            badges=1, party=self.full_party(),
        )
        decision = env._capture_policy(self.encounter())
        self.assertEqual("capture", decision["choice"])
        self.assertEqual("completionist_new_species", decision["reason_code"])

    def test_only_a_complete_reachable_area_lets_it_move_on(self):
        env = self.make_env(
            coverage={"owned": 5, "total": 5, "fraction": 1.0},
            badges=1, party=self.full_party(),
        )
        decision = env._capture_policy(self.encounter())
        self.assertEqual("defeat", decision["choice"])
        self.assertEqual("completionist_area_satisfied", decision["reason_code"])

    def test_the_area_rarity_is_never_skipped_by_a_met_quota(self):
        # A área já bateu a meta, mas um Pikachu de 5% na Floresta não é o
        # mesmo encontro que um Caterpie de 45%.
        env = self.make_env(
            coverage={"owned": 5, "total": 5, "fraction": 1.0},
            badges=1, party=self.full_party(),
        )
        env._map_name = lambda map_id=None: "Viridian Forest"
        encounter = self.encounter()
        encounter["enemy_species_id"] = 25  # Pikachu
        decision = env._capture_policy(encounter)
        self.assertEqual("capture", decision["choice"])
        self.assertEqual("rare_for_this_area", decision["reason_code"])

    def test_the_common_species_of_a_finished_area_is_still_skipped(self):
        env = self.make_env(
            coverage={"owned": 5, "total": 5, "fraction": 1.0},
            badges=1, party=self.full_party(),
        )
        env._map_name = lambda map_id=None: "Viridian Forest"
        encounter = self.encounter()
        encounter["enemy_species_id"] = 10  # Caterpie, 45%
        decision = env._capture_policy(encounter)
        self.assertEqual("defeat", decision["choice"])

    def test_a_free_party_slot_still_wins_over_a_finished_area(self):
        env = self.make_env(
            coverage={"owned": 5, "total": 5, "fraction": 1.0},
            badges=1, party=[{"species_id": 1, "level": 20}],
        )
        decision = env._capture_policy(self.encounter())
        self.assertEqual("capture", decision["choice"])


if __name__ == "__main__":
    unittest.main()
