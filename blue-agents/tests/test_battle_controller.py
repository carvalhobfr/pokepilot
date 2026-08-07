import sys
from pathlib import Path
import unittest

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.simple_battle import SimpleBattleAgent

from tests.rom_fixture import read_rom


class FakeMemory:
    def __init__(self, values):
        self.values = values

    def read_byte(self, address):
        return self.values.get(address, 0)

    def read_rom(self, bank, address):
        return read_rom(bank, address)


class BattleControllerTests(unittest.TestCase):
    def test_immunity_is_not_scored_as_neutral(self):
        agent = SimpleBattleAgent()
        self.assertEqual(0.0, agent.get_type_effectiveness("ELECTRIC", ["GROUND"]))

    def test_reads_moves_from_active_battle_pokemon(self):
        agent = SimpleBattleAgent()
        # Squirtle versus Geodude: active battle RAM has Water Gun, while the
        # first party struct deliberately contains an unrelated move.
        memory = FakeMemory({
            0xCFE5: 169,  # Geodude internal ID -> National #74
            0xCFE7: 20,
            0xCFEA: 5,    # Rock
            0xCFEB: 4,    # Ground
            0xD014: 177,  # Squirtle internal ID -> National #7
            0xD019: 21,   # Water
            0xD01A: 21,
            0xD01C: 55,   # Water Gun
            0xD02D: 25,   # Water Gun PP
            0xD173: 45,   # Growl in party slot 1; must be ignored
            0xCC50: 106,  # Move list open
            0xCC26: 1,
        })

        action = agent.get_action(memory)

        self.assertEqual("A", action)
        self.assertEqual(55, agent.last_decision["selected_move_id"])
        self.assertEqual(4.0, agent.last_decision["selected"]["effectiveness"])

    def test_squirtle_uses_bubble_instead_of_tail_whip_against_geodude(self):
        agent = SimpleBattleAgent()
        memory = FakeMemory({
            0xCFE5: 169,  # Geodude internal ID -> National #74
            0xCFE7: 20,
            0xCFEA: 5,    # Rock
            0xCFEB: 4,    # Ground
            0xD014: 177,  # Squirtle internal ID -> National #7
            0xD019: 21,   # Water
            0xD01A: 21,
            0xD01C: 33,   # Tackle
            0xD01D: 39,   # Tail Whip (status; must not be treated as power 50)
            0xD01E: 145,  # Bubble
            0xD02D: 30,
            0xD02E: 30,
            0xD02F: 30,
            0xCC50: 106,  # Move list open
            0xCC26: 1,
        })

        self.assertEqual("DOWN", agent.get_action(memory))
        memory.values[0xCC26] = 2
        self.assertEqual("DOWN", agent.get_action(memory))
        memory.values[0xCC26] = 3
        self.assertEqual("A", agent.get_action(memory))
        self.assertEqual(145, agent.last_decision["selected_move_id"])
        self.assertEqual(4.0, agent.last_decision["selected"]["effectiveness"])

    def test_reopens_fight_instead_of_trusting_previous_cursor(self):
        agent = SimpleBattleAgent()
        memory = FakeMemory({
            0xCFE5: 169,
            0xCFE7: 20,
            0xCFEA: 5,
            0xCFEB: 4,
            0xD014: 177,
            0xD019: 21,
            0xD01A: 21,
            0xD01C: 33,
            0xD01E: 145,
            0xD02D: 30,
            0xD02F: 30,
            0xCC50: 94,  # Main battle selector
            0xCC25: 9,   # Left column
            0xCC26: 0,   # FIGHT row
        })

        self.assertEqual("A", agent.get_action(memory))
        self.assertEqual(145, agent.last_decision["selected_move_id"])

    def test_never_selects_an_exhausted_move(self):
        agent = SimpleBattleAgent()
        memory = FakeMemory({
            0xCFE5: 13,   # Grimer
            0xCFE7: 6,
            0xCFEA: 3,    # Poison
            0xCFEB: 3,
            0xD014: 177,  # Squirtle
            0xD019: 21,   # Water
            0xD01A: 21,
            0xD01C: 33,   # Tackle
            0xD01E: 145,  # Bubble
            0xD01F: 55,   # Water Gun, but exhausted
            0xD02D: 26,
            0xD02F: 30,
            0xD030: 0,
            0xCC50: 106,
            0xCC26: 4,
        })

        self.assertEqual("UP", agent.get_action(memory))
        self.assertEqual(33, agent.last_decision["selected_move_id"])
        self.assertNotEqual(55, agent.last_decision["selected_move_id"])
        self.assertEqual(26, agent.last_decision["selected"]["pp"])

    def test_never_selects_a_disabled_move(self):
        agent = SimpleBattleAgent()
        memory = FakeMemory({
            0xCFE5: 13,
            0xCFE7: 6,
            0xCFEA: 3,
            0xCFEB: 3,
            0xD014: 177,
            0xD019: 21,
            0xD01A: 21,
            0xD01C: 33,   # Tackle is currently disabled
            0xD01E: 145,  # Bubble is the next usable attack
            0xD01F: 55,
            0xD02D: 26,
            0xD02F: 30,
            0xD030: 0,
            0xCCEE: 33,
            0xCC50: 106,
            0xCC26: 1,
        })

        self.assertEqual("DOWN", agent.get_action(memory))
        self.assertEqual(145, agent.last_decision["selected_move_id"])
        self.assertEqual(33, agent.last_decision["disabled_move_id"])

    def test_post_battle_text_alternates_and_evolution_never_presses_b(self):
        agent = SimpleBattleAgent()
        memory = FakeMemory({
            0xCFE7: 0,
            0xD01C: 44,
            0xD02D: 25,
        })

        self.assertEqual("A", agent.get_action(memory))
        self.assertEqual("B", agent.get_action(memory))
        memory.values[0xCC51] = 144
        self.assertEqual("A", agent.get_action(memory))

    def test_move_learning_replaces_status_move_instead_of_first_attack(self):
        agent = SimpleBattleAgent()
        memory = FakeMemory({
            0xCFE7: 0,
            0xD01C: 33,   # Tackle
            0xD01D: 39,   # Tail Whip: lowest-utility move
            0xD01E: 145,  # Bubble
            0xD01F: 55,   # Water Gun
            0xD02D: 30,
            0xD02E: 30,
            0xD02F: 30,
            0xD030: 6,
            0xCC50: 95,
            0xCC26: 0,
            0xD125: 20,   # TryingToLearn YES/NO prompt
        })

        self.assertEqual("A", agent.get_action(memory))  # YES
        memory.values[0xD125] = 1
        self.assertEqual("A", agent.get_action(memory))
        self.assertEqual("A", agent.get_action(memory))
        self.assertEqual("DOWN", agent.get_action(memory))  # open list safely

        memory.values[0xCC24] = 8
        memory.values[0xCC25] = 5
        self.assertEqual("DOWN", agent.get_action(memory))
        memory.values[0xCC26] = 1
        self.assertEqual("A", agent.get_action(memory))

        memory.values[0xD01D] = 44  # Bite confirmed in active battle RAM
        self.assertEqual("A", agent.get_action(memory))
        self.assertEqual("move_learned", agent.last_decision["kind"])
        self.assertEqual(39, agent.last_decision["replaced_move_id"])
        self.assertEqual(44, agent.last_decision["learned_move_id"])




class SwitchWhenOutOfPPTests(unittest.TestCase):
    """With every attack at zero PP the game forces Struggle, and Gen I Struggle
    recoils for half the damage dealt: the active Pokémon grinds itself down
    fighting something it cannot hurt. A teammate with PP costs nothing.
    """

    def make_env(self, party, active_slot=0):
        from hybrid_agent import HybridGymEnv
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.read_rom = read_rom
        env.get_party_info = lambda: list(party)
        env.read_m = lambda address: active_slot if address == 0xCC2F else 0
        env.capture_in_flight = False
        env.capture_plan = []
        env.capture_bag_open = False
        env.switch_plan = []
        env.switch_menu_open = False
        env.switch_steps = 0
        env.logged = []
        env._log_event = lambda kind, data, live=True: env.logged.append((kind, data))
        return env

    @staticmethod
    def mon(pp, hp=20, species=1):
        return {
            "species_id": species, "level": 12, "hp": hp, "max_hp": 20,
            "moves": [{"id": 33, "pp": pp}, {"id": 45, "pp": 30}],  # Tackle, Growl
        }

    def test_a_teammate_with_pp_is_chosen(self):
        env = self.make_env([self.mon(pp=0), self.mon(pp=15)])
        self.assertEqual(1, env._switch_target_slot())

    def test_nobody_is_swapped_while_the_active_can_still_attack(self):
        env = self.make_env([self.mon(pp=10), self.mon(pp=15)])
        self.assertIsNone(env._switch_target_slot())
        self.assertIsNone(env._next_switch_action())

    def test_a_fainted_teammate_is_not_a_target(self):
        env = self.make_env([self.mon(pp=0), self.mon(pp=15, hp=0)])
        self.assertIsNone(env._switch_target_slot())

    def test_a_fainted_lead_is_replaced_by_whoever_is_standing(self):
        # The game will not continue until someone is sent out, so here the
        # choice is not about damage — it is about the battle ending at all.
        env = self.make_env([self.mon(pp=10, hp=0), self.mon(pp=0, hp=18)])
        self.assertEqual(1, env._switch_target_slot())

    def test_the_use_next_pokemon_prompt_is_answered_before_the_list(self):
        # A faint does not open the battle menu: the game asks first. Walking
        # the 2x2 cursor there does nothing at all.
        env = self.make_env([self.mon(pp=10, hp=0), self.mon(pp=12, hp=18)])
        env.read_m = lambda address: 1 if address == 0xCFC4 else 0
        self.assertEqual("A", env._next_switch_action(), "responde ao aviso")
        self.assertTrue(env.switch_menu_open)

    def test_a_lone_pokemon_has_nobody_to_switch_to(self):
        env = self.make_env([self.mon(pp=0)])
        self.assertIsNone(env._switch_target_slot())

    def test_the_switch_waits_for_the_menu_instead_of_walking_into_run(self):
        # RUN sits one tile from PKMN. With battle text still up the cursor
        # bytes are not menu coordinates, and a blind press ran away instead of
        # switching: 62 escapes in ten minutes.
        env = self.make_env([self.mon(pp=0), self.mon(pp=15)])
        env.read_m = lambda address: 5 if address == 0xCC25 else 0
        self.assertEqual("B", env._next_switch_action(), "avança o texto")
        self.assertFalse(env.switch_menu_open)

    def test_the_menu_is_driven_by_the_highlighted_row(self):
        env = self.make_env([self.mon(pp=0), self.mon(pp=15)])
        # Menu drawn, cursor on FIGHT: row 0, left column.
        env.read_m = lambda address: 9 if address == 0xCC25 else 0
        first = env._next_switch_action()
        self.assertEqual("RIGHT", first, "do FIGHT para o PKMN")
        env.read_m = lambda address: 15 if address == 0xCC25 else 0
        self.assertEqual("A", env._next_switch_action(), "abre a lista da equipe")
        self.assertTrue(env.switch_menu_open)
        self.assertIn("switch_intent", [kind for kind, _ in env.logged])

        env.read_m = lambda address: 0  # cursor na linha 0, alvo é a 1
        self.assertEqual("DOWN", env._next_switch_action())
        env.read_m = lambda address: 1 if address == 0xCC26 else 0
        self.assertEqual("A", env._next_switch_action(), "escolhe o Pokémon")
        self.assertEqual("A", env._next_switch_action(), "confirma SWITCH")

    def test_a_menu_that_does_not_behave_is_abandoned_not_mashed(self):
        env = self.make_env([self.mon(pp=0), self.mon(pp=15)])
        env.switch_menu_open = True
        env.read_m = lambda address: 0  # cursor nunca chega no alvo
        actions = [env._next_switch_action() for _ in range(14)]
        self.assertIn("B", actions, "sai do menu em vez de martelar botão")


class MissionRestartTests(unittest.TestCase):
    """Whatever traps a bot on one tile, the mission starts over from there.

    Every freeze in this project had its own cause and its own fix. This one
    removes the class instead of another instance.
    """

    def make_env(self, position, *, in_battle=False):
        from hybrid_agent import HybridGymEnv, MISSION_RESTART_STEPS
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.read_rom = read_rom
        env.logged = []
        env._log_event = lambda kind, data, live=True: env.logged.append((kind, data))
        env.current_task = "QUEST: MT_MOON_NAV"
        env.stagnant_position = None
        env.stagnant_steps = 0
        state = {0xD35E: position[0], 0xD362: position[1], 0xD361: position[2],
                 0xD057: 1 if in_battle else 0}
        env.read_m = lambda address: state.get(address, 0)
        env.state = state
        env.limit = MISSION_RESTART_STEPS
        agent = type("FakeScripted", (), {})()
        agent.route_id = "mt-moon-14"
        agent.route_plan = {"directions": ["R"]}
        agent.current_task_name = "mt_moon_nav"
        env.scripted_agent = agent
        return env

    def test_story_route_is_not_restarted_by_a_timer(self):
        env = self.make_env((14, 19, 4))
        for _ in range(env.limit + 1):
            env._watch_for_stagnation()
        self.assertEqual([], env.logged, "quest real não perde a rota por timeout")
        self.assertTrue(hasattr(env.scripted_agent, "route_id"), "rota é preservada")

    def test_moving_resets_the_count(self):
        env = self.make_env((14, 19, 4))
        for _ in range(env.limit - 1):
            env._watch_for_stagnation()
        env.state[0xD362] = 18
        env._watch_for_stagnation()
        for _ in range(env.limit - 1):
            env._watch_for_stagnation()
        self.assertEqual([], env.logged, "quem anda não precisa de reinício")

    def test_a_long_battle_is_not_a_freeze(self):
        env = self.make_env((14, 19, 4), in_battle=True)
        for _ in range(env.limit * 2):
            env._watch_for_stagnation()
        self.assertEqual([], env.logged)


class ExhaustedPPTests(unittest.TestCase):
    """Damage moves at 0 PP must not deadlock the move menu."""

    def test_falls_back_to_a_move_that_still_has_pp(self):
        # CARON's real state in Viridian Forest: Tackle and Bubble spent,
        # only Tail Whip left. Selecting slot 0 reopened the "no PP" textbox
        # forever instead of taking a turn.
        memory = {
            0xD057: 1,
            0xCFE5: 11,
            0xD014: 11,
            0xD01C: 33, 0xD01D: 39, 0xD01E: 145, 0xD01F: 0,
            0xD02D: 0, 0xD02E: 30, 0xD02F: 0, 0xD030: 0,
            0xCCEE: 0,
        }
        agent = SimpleBattleAgent()
        emulator = FakeMemory(memory)
        decision = None
        for _ in range(60):
            agent.get_action(emulator)
            candidate = getattr(agent, "last_decision", None)
            if candidate and candidate.get("selected_move_slot") is not None:
                decision = candidate
                break
        self.assertIsNotNone(decision, "o controlador precisa escolher algum golpe")
        self.assertEqual(
            1, decision["selected_move_slot"],
            "só o slot 1 (Tail Whip) ainda tem PP; slot 0 trava o menu",
        )


class FaintedLeadTests(unittest.TestCase):
    """A faint is a question the game asks, and it waits for the answer."""

    def make_env(self, party, prompt_open=True, active_slot=0):
        from hybrid_agent import HybridGymEnv
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.read_rom = read_rom
        env.get_party_info = lambda: list(party)
        env.read_m = lambda address: (
            active_slot if address == 0xCC2F
            else 1 if (address == 0xCFC4 and prompt_open)
            else 0
        )
        env.in_battle = True
        env.capture_forced = False
        env.capture_in_flight = False
        env.capture_plan = []
        env.capture_bag_open = False
        env.switch_plan = []
        env.switch_menu_open = False
        env.switch_steps = 0
        env.logged = []
        env._log_event = lambda kind, data, live=True: env.logged.append((kind, data))
        return env

    @staticmethod
    def mon(hp, pp=0):
        return {
            "species_id": 1, "level": 10, "hp": hp, "max_hp": 20,
            "moves": [{"id": 33, "pp": pp}, {"id": 45, "pp": 30}],
        }

    def test_the_prompt_is_answered_instead_of_run_from(self):
        # Lead down, nobody with a damaging move: escaping used to win the
        # ordering and press B at "Use next POKéMON?" forever.
        env = self.make_env([self.mon(hp=0, pp=0), self.mon(hp=18, pp=0)])
        self.assertIsNone(env._next_escape_action(), "não se foge de um pedido")
        self.assertEqual("A", env._next_switch_action(), "responde ao aviso")
        self.assertTrue(env.switch_menu_open)

    def test_a_worn_out_team_runs_from_wild_fights_on_the_way(self):
        # Two Pokémon, half the pool gone: fighting the next Caterpie costs
        # more than the turn it takes to leave. Four round trips to Viridian
        # in twelve minutes came from fighting these.
        env = self.make_env([self.mon(hp=5, pp=20), self.mon(hp=6, pp=20)],
                            prompt_open=False)
        env._switch_target_slot = lambda: None
        self.assertTrue(env._party_is_worn_out())
        self.assertIsNotNone(env._next_escape_action())

    def test_a_healthy_team_still_fights(self):
        env = self.make_env([self.mon(hp=20, pp=20), self.mon(hp=18, pp=20)],
                            prompt_open=False)
        env._switch_target_slot = lambda: None
        self.assertFalse(env._party_is_worn_out())
        self.assertIsNone(env._next_escape_action())

    def test_with_everyone_standing_escape_is_still_allowed(self):
        env = self.make_env([self.mon(hp=20, pp=0), self.mon(hp=18, pp=0)],
                            prompt_open=False)
        env._switch_target_slot = lambda: None
        self.assertIsNotNone(env._next_escape_action())


if __name__ == "__main__":
    unittest.main()
