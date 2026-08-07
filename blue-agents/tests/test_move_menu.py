"""Choosing a move from the list the screen is really showing.

AARON pressed DOWN for two minutes against a level 2 Rattata, holding a
full-PP Tackle in slot 0. Slot 0 wants row 1, the cursor byte read 0, and 0 is
below 1 — so "walk down to the row you want" answered DOWN, the press changed
nothing, and the next step read 0 again.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.simple_battle import SimpleBattleAgent

MOVE_LIST_OPEN = 106
BATTLE_SELECTOR = 94


class MoveMenuMemory:
    """Only the bytes the move chooser reads."""

    def __init__(self, *, battle_menu, row, column=5, text=0, enemy_hp=20):
        self.values = {
            0xCC50: battle_menu,
            0xCC25: column,
            0xCC26: row,
            0xD125: text,
            0xCFE6: enemy_hp >> 8,
            0xCFE7: enemy_hp & 0xFF,
        }

    def read_byte(self, address):
        return self.values.get(address, 0)


class MoveListTests(unittest.TestCase):
    MOVES = [(33, 35), (45, 40), (73, 10)]

    def choose(self, slot, **memory):
        return SimpleBattleAgent()._select_move_from_live_menu(
            MoveMenuMemory(**memory), slot, self.MOVES
        )

    def test_a_row_below_the_one_wanted_walks_down(self):
        self.assertEqual(
            "DOWN", self.choose(2, battle_menu=MOVE_LIST_OPEN, row=1)
        )

    def test_a_row_above_the_one_wanted_walks_up(self):
        self.assertEqual(
            "UP", self.choose(0, battle_menu=MOVE_LIST_OPEN, row=3)
        )

    def test_the_row_wanted_is_confirmed(self):
        self.assertEqual("A", self.choose(0, battle_menu=MOVE_LIST_OPEN, row=1))

    def test_row_zero_is_not_a_row(self):
        # The list is one-based. Read literally, zero is below every desired
        # row, so the naive comparison answers DOWN forever.
        self.assertNotEqual(
            "DOWN", self.choose(0, battle_menu=MOVE_LIST_OPEN, row=0)
        )

    def test_a_menu_that_is_not_there_gets_text_advanced(self):
        # B advances text and can never pick a move by accident.
        self.assertIn(
            self.choose(0, battle_menu=MOVE_LIST_OPEN, row=0), {"A", "B"}
        )

    def test_a_row_past_the_last_move_is_not_a_row_either(self):
        self.assertNotIn(
            self.choose(0, battle_menu=MOVE_LIST_OPEN, row=9), {"UP", "DOWN"}
        )

    def test_the_same_rule_on_the_column_five_variant(self):
        self.assertNotEqual(
            "DOWN",
            self.choose(0, battle_menu=BATTLE_SELECTOR, row=0, column=5),
        )

    def test_a_fainted_opponent_is_not_a_menu_problem(self):
        # Nothing to choose; the post-battle handler owns this.
        self.assertIsNotNone(
            self.choose(0, battle_menu=MOVE_LIST_OPEN, row=0, enemy_hp=0)
        )


if __name__ == "__main__":
    unittest.main()
