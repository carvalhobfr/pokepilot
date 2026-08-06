"""Reaching ITEM in the battle menu, decided by the screen and not by memory.

A blind press list lost a wild Pikachu and six more encounters: battle text ate
the DOWN, the plan ran out anyway, and the A meant for the Bag chose FIGHT. The
ball count never dropped, so every attempt was logged as "menu não confirmou o
uso da Poké Bola" while the trainer just attacked.
"""

import sys
import unittest
from pathlib import Path

AGENTS_ROOT = Path(__file__).resolve().parents[1]
if str(AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_ROOT))

from hybrid_agent import (
    BAG_FIRST_ITEM_ADDRESS,
    BAG_ITEM_COUNT_ADDRESS,
    BATTLE_MENU_COLUMN_ADDRESS,
    BATTLE_MENU_LEFT_COLUMN,
    BATTLE_MENU_RIGHT_COLUMN,
    BATTLE_MENU_ROW_ADDRESS,
    MENU_CURSOR_ADDRESS,
    MENU_SCROLL_OFFSET_ADDRESS,
    HybridGymEnv,
)


class MenuProbe:
    """Just the RAM the step function reads."""

    def __init__(self, row, column):
        self.values = {
            BATTLE_MENU_ROW_ADDRESS: row,
            BATTLE_MENU_COLUMN_ADDRESS: column,
        }

    def read_m(self, address):
        return self.values[address]

    _battle_menu_step = HybridGymEnv._battle_menu_step
    step = HybridGymEnv._battle_menu_step_to_item


class BattleMenuStepTests(unittest.TestCase):
    def test_battle_text_is_advanced_with_b_never_with_a(self):
        # During "Nothing happened!" the column byte is not a menu column at
        # all. A here would pick whatever the menu opens on — FIGHT.
        self.assertEqual("B", MenuProbe(row=1, column=5).step())

    def test_from_fight_it_goes_down(self):
        self.assertEqual(
            "DOWN", MenuProbe(row=0, column=BATTLE_MENU_LEFT_COLUMN).step()
        )

    def test_from_pkmn_it_goes_down_first(self):
        self.assertEqual(
            "DOWN", MenuProbe(row=0, column=BATTLE_MENU_RIGHT_COLUMN).step()
        )

    def test_a_submenu_is_backed_out_of_instead_of_pressed_into(self):
        # Inside the move list the column still looks like a menu column and
        # the row goes to 3. Pressing DOWN there did nothing, sixteen thousand
        # times, while every attack sat at zero PP.
        self.assertEqual("B", MenuProbe(row=3, column=15).step())

    def test_from_run_it_steps_left_onto_item(self):
        self.assertEqual(
            "LEFT", MenuProbe(row=1, column=BATTLE_MENU_RIGHT_COLUMN).step()
        )

    def test_a_is_pressed_only_with_item_under_the_cursor(self):
        self.assertEqual(
            "A", MenuProbe(row=1, column=BATTLE_MENU_LEFT_COLUMN).step()
        )

    def test_unreadable_ram_advances_text_instead_of_guessing(self):
        class Broken:
            def read_m(self, address):
                raise ValueError("no RAM")
            _battle_menu_step = HybridGymEnv._battle_menu_step
            step = HybridGymEnv._battle_menu_step_to_item

        self.assertEqual("B", Broken().step())


class BagProbe:
    """A real bag list, a scroll offset and a highlighted row."""

    def __init__(self, items, scroll=0, row=0):
        self.values = {
            BAG_ITEM_COUNT_ADDRESS: len(items),
            MENU_SCROLL_OFFSET_ADDRESS: scroll,
            MENU_CURSOR_ADDRESS: row,
        }
        for index, (item_id, quantity) in enumerate(items):
            self.values[BAG_FIRST_ITEM_ADDRESS + index * 2] = item_id
            self.values[BAG_FIRST_ITEM_ADDRESS + index * 2 + 1] = quantity

    def read_m(self, address):
        return self.values[address]

    bag_highlighted_slot = HybridGymEnv.bag_highlighted_slot
    bag_highlighted_item_id = HybridGymEnv.bag_highlighted_item_id


class BagHighlightTests(unittest.TestCase):
    """What is under the cursor, not what row we think we are on.

    The Poké Ball's slot moves whenever an item is picked up or runs out, so a
    remembered position is a guess about a list that changed.
    """

    def test_it_reads_the_item_actually_highlighted(self):
        bag = BagProbe([(4, 7), (20, 1)], row=1)
        self.assertEqual(20, bag.bag_highlighted_item_id())

    def test_a_scrolled_list_still_answers_correctly(self):
        bag = BagProbe([(20, 1), (11, 2), (4, 5)], scroll=2, row=0)
        self.assertEqual(4, bag.bag_highlighted_item_id())

    def test_the_cancel_row_past_the_last_item_is_not_an_item(self):
        # CANCEL sits one row below the list. Reading it as an item would
        # answer with whatever byte follows the bag in RAM.
        bag = BagProbe([(4, 7)], row=1)
        self.assertIsNone(bag.bag_highlighted_item_id())


if __name__ == "__main__":
    unittest.main()
