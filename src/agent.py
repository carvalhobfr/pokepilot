import random
import random
from pyboy.utils import WindowEvent

class BaseAgent:
    def get_action(self, state):
        raise NotImplementedError

class RandomAgent(BaseAgent):
    def __init__(self):
        self.valid_actions = [
            WindowEvent.PRESS_ARROW_UP,
            WindowEvent.PRESS_ARROW_DOWN,
            WindowEvent.PRESS_ARROW_LEFT,
            WindowEvent.PRESS_ARROW_RIGHT,
            WindowEvent.PRESS_BUTTON_A,
            WindowEvent.PRESS_BUTTON_B,
            WindowEvent.PRESS_BUTTON_START,
            WindowEvent.PRESS_BUTTON_SELECT,
            WindowEvent.RELEASE_ARROW_UP,
            WindowEvent.RELEASE_ARROW_DOWN,
            WindowEvent.RELEASE_ARROW_LEFT,
            WindowEvent.RELEASE_ARROW_RIGHT,
            WindowEvent.RELEASE_BUTTON_A,
            WindowEvent.RELEASE_BUTTON_B,
            WindowEvent.RELEASE_BUTTON_START,
            WindowEvent.RELEASE_BUTTON_SELECT
        ]

    def get_action(self, state):
        # Simple random action
        # 10% chance to press a button, otherwise do nothing (wait)
        if random.random() < 0.1:
            return random.choice(self.valid_actions)
        return None
