import sys
from pathlib import Path
import unittest

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.simple_battle import SimpleBattleAgent


class FakeMemory:
    def __init__(self, values):
        self.values = values

    def read_byte(self, address):
        return self.values.get(address, 0)


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


if __name__ == "__main__":
    unittest.main()
