"""Canonical Game Boy actions shared by every PokeAI controller.

The emulator accepts seven buttons plus an explicit NOOP.  Keeping this order
in one module prevents story scripts, manual controls, battle rules and PPO
telemetry from silently disagreeing about which button was executed.
"""

from enum import IntEnum

from pyboy.utils import WindowEvent


class GameAction(IntEnum):
    DOWN = 0
    LEFT = 1
    RIGHT = 2
    UP = 3
    A = 4
    B = 5
    START = 6
    NOOP = 7


ACTION_COUNT = len(GameAction)
NOOP_ACTION = int(GameAction.NOOP)


PRESS_EVENT_TO_ACTION = {
    WindowEvent.PRESS_ARROW_DOWN: GameAction.DOWN,
    WindowEvent.PRESS_ARROW_LEFT: GameAction.LEFT,
    WindowEvent.PRESS_ARROW_RIGHT: GameAction.RIGHT,
    WindowEvent.PRESS_ARROW_UP: GameAction.UP,
    WindowEvent.PRESS_BUTTON_A: GameAction.A,
    WindowEvent.PRESS_BUTTON_B: GameAction.B,
    WindowEvent.PRESS_BUTTON_START: GameAction.START,
}

RELEASE_EVENTS = {
    WindowEvent.RELEASE_ARROW_DOWN,
    WindowEvent.RELEASE_ARROW_LEFT,
    WindowEvent.RELEASE_ARROW_RIGHT,
    WindowEvent.RELEASE_ARROW_UP,
    WindowEvent.RELEASE_BUTTON_A,
    WindowEvent.RELEASE_BUTTON_B,
    WindowEvent.RELEASE_BUTTON_START,
}


def event_to_action(event) -> int:
    """Translate a PyBoy script event into the canonical action index."""
    if event is None or event in RELEASE_EVENTS:
        return NOOP_ACTION
    return int(PRESS_EVENT_TO_ACTION.get(event, GameAction.NOOP))


def name_to_action(name, *, default=GameAction.NOOP) -> int:
    """Translate a command/battle action name into the canonical index."""
    if not isinstance(name, str):
        return int(default)
    normalized = name.strip().upper()
    aliases = {
        "WAIT": GameAction.NOOP,
        "PASS": GameAction.NOOP,
        "NONE": GameAction.NOOP,
        # SELECT is not currently exposed by RedGymEnv. Keep the historical
        # fallback explicit instead of allowing a different accidental button.
        "SELECT": GameAction.START,
    }
    return int(aliases.get(normalized, GameAction.__members__.get(normalized, default)))
