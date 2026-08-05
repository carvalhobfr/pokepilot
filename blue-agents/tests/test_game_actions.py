import unittest

from pyboy.utils import WindowEvent

from game_actions import GameAction, event_to_action, name_to_action


class GameActionTests(unittest.TestCase):
    def test_script_events_match_environment_order(self):
        self.assertEqual(GameAction.DOWN, event_to_action(WindowEvent.PRESS_ARROW_DOWN))
        self.assertEqual(GameAction.LEFT, event_to_action(WindowEvent.PRESS_ARROW_LEFT))
        self.assertEqual(GameAction.RIGHT, event_to_action(WindowEvent.PRESS_ARROW_RIGHT))
        self.assertEqual(GameAction.UP, event_to_action(WindowEvent.PRESS_ARROW_UP))
        self.assertEqual(GameAction.A, event_to_action(WindowEvent.PRESS_BUTTON_A))
        self.assertEqual(GameAction.B, event_to_action(WindowEvent.PRESS_BUTTON_B))
        self.assertEqual(GameAction.START, event_to_action(WindowEvent.PRESS_BUTTON_START))

    def test_release_and_none_are_real_noops(self):
        self.assertEqual(GameAction.NOOP, event_to_action(None))
        self.assertEqual(GameAction.NOOP, event_to_action(WindowEvent.RELEASE_BUTTON_A))

    def test_manual_names_share_the_same_mapping(self):
        for action in GameAction:
            self.assertEqual(action, name_to_action(action.name))


if __name__ == "__main__":
    unittest.main()
