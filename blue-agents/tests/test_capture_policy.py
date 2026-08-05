import unittest

from hybrid_agent import (
    GOT_POKEDEX_ADDRESS,
    GOT_POKEDEX_MASK,
    HybridGymEnv,
    POKEDEX_OWNED_START,
)


class CapturePolicyTests(unittest.TestCase):
    def make_env(self, *, collector=50, meta=50, balls=5, party=None, memory=None):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.collector = collector
        env.meta_score = meta
        env.capture_enabled = True
        env.last_battle_is_trainer = False
        env.get_party_info = lambda: list(party or [])
        ram = dict(memory or {})
        env.read_m = lambda address: ram.get(address, 0)
        env._poke_ball_count = lambda: balls
        env._select_capture_ball = lambda shiny_candidate=False: (
            {"item_id": 4, "slot": 0} if balls else None
        )
        return env, ram

    @staticmethod
    def encounter(species=25, level=5, shiny=False):
        return {
            "enemy_species_id": species,
            "enemy_level": level,
            "shiny_candidate": shiny,
        }

    def test_picking_up_parcel_does_not_unlock_capture(self):
        env, _ = self.make_env(
            collector=100,
            memory={0xD74E: 1 << 1},
        )

        decision = env._capture_policy(self.encounter())

        self.assertEqual("defeat", decision["choice"])
        self.assertEqual("story_locked", decision["reason_code"])

    def test_oak_pokedex_flag_unlocks_capture_story(self):
        env, _ = self.make_env(memory={GOT_POKEDEX_ADDRESS: GOT_POKEDEX_MASK})

        self.assertTrue(env._capture_story_complete())

    def test_shiny_compatible_encounter_has_absolute_priority(self):
        env, _ = self.make_env(
            collector=0,
            meta=0,
            memory={GOT_POKEDEX_ADDRESS: GOT_POKEDEX_MASK},
        )

        decision = env._capture_policy(self.encounter(shiny=True))

        self.assertEqual("capture", decision["choice"])
        self.assertEqual("shiny_priority", decision["reason_code"])

    @staticmethod
    def owned(*species):
        """RAM fragment marking these national ids as already registered."""
        memory = {}
        for national_id in species:
            address = POKEDEX_OWNED_START + (national_id - 1) // 8
            memory[address] = memory.get(address, 0) | 1 << ((national_id - 1) % 8)
        return memory

    def full_party(self, species_id=1):
        return [{"species_id": species_id + index, "level": 20} for index in range(6)]

    def test_lone_starter_captures_a_new_species_despite_low_personality(self):
        # The reported bug: both live trainers rolled collector < 55, so the
        # collector branch never fired and their team stayed at one Pokémon.
        env, _ = self.make_env(
            collector=10,
            meta=10,
            party=[{"species_id": 7, "level": 9}],
            memory={GOT_POKEDEX_ADDRESS: GOT_POKEDEX_MASK},
        )

        decision = env._capture_policy(self.encounter(species=16, level=4))

        self.assertEqual("capture", decision["choice"])
        self.assertEqual("party_slot_new_species", decision["reason_code"])

    def test_weak_form_of_a_strong_line_is_worth_a_slot(self):
        # Metapod is a bad Pokémon and a good catch: Butterfree carries Kanto's
        # opening hours.
        env, _ = self.make_env(
            collector=0,
            meta=0,
            party=[{"species_id": 7, "level": 9}],
            memory={GOT_POKEDEX_ADDRESS: GOT_POKEDEX_MASK},
        )

        decision = env._capture_policy(self.encounter(species=11, level=7))

        self.assertEqual("capture", decision["choice"])
        self.assertGreaterEqual(decision["strategic_value"], 70)

    def test_duplicate_species_is_never_captured(self):
        species = 10  # Caterpie already registered
        env, _ = self.make_env(
            collector=100,
            meta=100,
            party=[{"species_id": 7, "level": 9}],
            memory={GOT_POKEDEX_ADDRESS: GOT_POKEDEX_MASK, **self.owned(species)},
        )

        decision = env._capture_policy(self.encounter(species=species, level=6))

        self.assertEqual("defeat", decision["choice"])
        self.assertEqual("duplicate_species", decision["reason_code"])

    def test_duplicate_rule_holds_even_with_free_party_slots(self):
        species = 10
        env, _ = self.make_env(
            collector=100,
            party=[],
            memory={GOT_POKEDEX_ADDRESS: GOT_POKEDEX_MASK, **self.owned(species)},
        )

        decision = env._capture_policy(self.encounter(species=species, level=6))

        self.assertEqual("defeat", decision["choice"])
        self.assertEqual("duplicate_species", decision["reason_code"])

    def test_collector_captures_new_species_with_a_full_party(self):
        env, _ = self.make_env(
            collector=80,
            party=self.full_party(),
            memory={GOT_POKEDEX_ADDRESS: GOT_POKEDEX_MASK},
        )

        decision = env._capture_policy(self.encounter(species=16, level=4))

        self.assertEqual("capture", decision["choice"])
        self.assertEqual("collector_new_species", decision["reason_code"])

    def test_strategist_captures_team_upgrade_with_a_full_party(self):
        env, _ = self.make_env(
            collector=0,
            meta=80,
            party=self.full_party(),
            memory={GOT_POKEDEX_ADDRESS: GOT_POKEDEX_MASK},
        )

        decision = env._capture_policy(self.encounter(species=143, level=30))

        self.assertEqual("capture", decision["choice"])
        self.assertEqual("team_upgrade", decision["reason_code"])

    def test_uninteresting_encounter_is_defeated_for_training(self):
        env, _ = self.make_env(
            collector=0,
            meta=0,
            party=self.full_party(),
            memory={GOT_POKEDEX_ADDRESS: GOT_POKEDEX_MASK},
        )

        decision = env._capture_policy(self.encounter(species=21, level=3))

        self.assertEqual("defeat", decision["choice"])
        self.assertEqual("training_value", decision["reason_code"])

    def test_pokedex_counter_counts_bits_not_byte_values(self):
        env, ram = self.make_env()
        ram[POKEDEX_OWNED_START] = 0xFF
        ram[POKEDEX_OWNED_START + 18] = 0x80  # invalid species bit 152

        self.assertEqual(8, env._pokedex_owned_count())

    def test_gen_two_shiny_dv_pattern(self):
        env, ram = self.make_env()
        ram[0xCFF1] = 0x2A  # attack 2, defense 10
        ram[0xCFF2] = 0xAA  # speed 10, special 10

        shiny = env._enemy_shiny_info()

        self.assertTrue(shiny["shiny_candidate"])


if __name__ == "__main__":
    unittest.main()
