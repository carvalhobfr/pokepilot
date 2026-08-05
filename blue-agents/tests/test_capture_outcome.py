import unittest

from hybrid_agent import HybridGymEnv


class CaptureOutcomeTests(unittest.TestCase):
    """A capture decision without an outcome cannot be read.

    The feed used to say "decidiu capturar" and then go quiet: whether that
    Pokémon ended up in the team, on the floor, or gone was nowhere.
    """

    def end_of_wild_battle(self, *, party, balls_before, balls_now,
                           pokedex_owned_before=1, pokedex_owned=1,
                           party_count_before=1, capture_attempts=1,
                           enemy_hp=0, player_hp=20):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.logged = []
        env._log_event = lambda kind, data, live=True: env.logged.append((kind, data))
        env.read_m = lambda address: 0  # out of battle
        env.get_party_info = lambda: list(party)
        env._poke_ball_count = lambda: balls_now
        env._pokedex_owned_count = lambda: pokedex_owned

        env.in_battle = True
        env.last_battle_is_trainer = False
        env.last_battle_enemy_id = 41
        env.last_battle_enemy_hp = enemy_hp
        env.last_battle_player_hp = player_hp
        env.last_battle_map_id = 59
        env.last_active_internal_id = 7
        env.battle_party_count_before = party_count_before
        env.battle_pokedex_owned_before = pokedex_owned_before
        env.capture_attempts = capture_attempts
        env.trainer_battles_won = 0
        env.wild_battles_won = 0
        env.deaths = 0
        env.last_hp_check = False
        env.current_task = "QUEST: MT_MOON_NAV"
        env.capture_count = 0
        env.last_party_info = list(party)
        env.last_pokedex_owned = pokedex_owned

        env.battle_balls_before = balls_before
        env.battle_capture_intent = {
            "choice": "capture",
            "reason_code": "party_slot_new_species",
            "reason": "vaga livre e espécie nova",
            "enemy_species_id": 41,
            "enemy_level": 8,
        }
        env.last_capture_policy = {}
        env.updated_panel = False
        env._update_agent_state = lambda: setattr(env, "updated_panel", True)

        env._track_battles_and_deaths()
        outcomes = [data for kind, data in env.logged if kind == "capture_outcome"]
        self.assertEqual(1, len(outcomes), "todo encontro selvagem fecha com um desfecho")
        return env, outcomes[0]

    def test_a_capture_decision_that_worked_reports_the_new_team(self):
        env, data = self.end_of_wild_battle(
            party=[{"species_id": 7, "level": 18, "hp": 20},
                   {"species_id": 41, "level": 8, "hp": 12}],
            balls_before=9, balls_now=8,
            pokedex_owned_before=1, pokedex_owned=2, party_count_before=1,
        )
        self.assertEqual("capture", data["intent"])
        self.assertEqual("captured", data["outcome"])
        self.assertEqual(1, data["balls_thrown"])
        self.assertEqual(2, data["party_size"])
        self.assertTrue(
            env.updated_panel,
            "um time novo é exatamente quando alguém está olhando o painel",
        )

    def test_a_capture_decision_that_ended_in_a_knockout_says_so(self):
        env, data = self.end_of_wild_battle(
            party=[{"species_id": 7, "level": 18, "hp": 20}],
            balls_before=9, balls_now=8,
            pokedex_owned_before=1, pokedex_owned=1, party_count_before=1,
        )
        self.assertEqual("capture", data["intent"])
        self.assertEqual("defeated", data["outcome"])
        self.assertEqual(1, data["balls_thrown"])
        self.assertFalse(env.updated_panel)

    def test_a_wild_pokemon_that_ran_is_reported_as_fled(self):
        env, data = self.end_of_wild_battle(
            party=[{"species_id": 7, "level": 18, "hp": 20}],
            balls_before=9, balls_now=9,
            enemy_hp=14, capture_attempts=0,
        )
        self.assertEqual("fled", data["outcome"])
        self.assertEqual(0, data["balls_thrown"])


class CaptureExecutionTests(unittest.TestCase):
    """Deciding to capture is not throwing a ball.

    The four trainers decided to capture 83 times and threw zero balls: the
    battle-start bookkeeping marked every fight as already planned, so the menu
    controller never built the plan that opens the bag.
    """

    def make_env(self, *, in_battle=True, plan_battle=None):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.logged = []
        env._log_event = lambda kind, data, live=True: env.logged.append((kind, data))
        env.in_battle = in_battle
        env.battle_sequence = 4
        env.capture_plan = []
        env.capture_plan_battle = plan_battle
        env.capture_in_flight = False
        env.capture_attempts = 0
        env.capture_result_steps = 0
        env.capture_balls_before_attempt = None
        env.battle_action_mode = "attack"
        env._poke_ball_count = lambda: 5
        env._battle_menu_path_to_item = lambda: ["RIGHT", "DOWN"]
        env._get_battle_info = lambda: {
            "is_battle": True, "enemy_id": 41, "enemy_species_id": 41,
            "enemy_level": 8,
        }
        env._capture_policy = lambda info: {
            "choice": "capture", "reason": "espécie nova", "reason_code": "party_slot_new_species",
            "motivation": "team_building", "shiny_candidate": False,
            "ball_item_id": 4, "ball_slot": 0,
        }
        return env

    def test_a_fresh_battle_builds_the_plan_that_opens_the_bag(self):
        env = self.make_env()
        action = env._next_capture_action()
        self.assertIsNotNone(action, "a captura precisa produzir entrada de menu")
        self.assertEqual("capture", env.battle_action_mode)
        self.assertIn(
            "capture_intent", [kind for kind, _ in env.logged],
            "a intenção de captura tem que ficar registrada",
        )

    def test_the_cursor_walks_to_the_ball_and_only_then_confirms(self):
        # Blind presses reported "menu não confirmou o uso da Poké Bola" over
        # and over: the ball count never dropped because the cursor was never
        # where the script assumed. The bag row is readable, so read it.
        env = self.make_env(plan_battle=4)
        env.capture_bag_open = True
        env.read_m = lambda address: {0xCC26: 0, 0xCC36: 0}.get(address, 0)
        env._capture_policy = lambda info: {
            "choice": "capture", "reason": "espécie nova", "reason_code": "x",
            "motivation": "team_building", "shiny_candidate": False,
            "ball_item_id": 4, "ball_slot": 2,
        }
        self.assertEqual("DOWN", env._next_capture_action(), "linha 0, bola no índice 2")

        env.read_m = lambda address: {0xCC26: 3, 0xCC36: 0}.get(address, 0)
        self.assertEqual("UP", env._next_capture_action(), "passou da bola")

        env.read_m = lambda address: {0xCC26: 1, 0xCC36: 1}.get(address, 0)
        self.assertEqual("A", env._next_capture_action(), "em cima da bola: usar")
        self.assertTrue(env.capture_in_flight)
        self.assertFalse(env.capture_bag_open)

    def test_a_battle_already_planned_does_not_plan_again(self):
        env = self.make_env(plan_battle=4)
        env._next_capture_action()
        self.assertEqual([], env.logged, "um plano por batalha, não um por passo")


if __name__ == "__main__":
    unittest.main()
