from pyboy import PyBoy
from pyboy.utils import WindowEvent

from src.memory import Memory

class Emulator:
    def __init__(self, rom_path, headless=False):
        self.pyboy = PyBoy(
            rom_path,
            window="headless" if headless else "SDL2",
            sound=False
        )
        self.pyboy.set_emulation_speed(0) # Unlimited speed
        self.memory = Memory(self.pyboy)
        
    def step(self, action):
        """
        Executes an action for one frame.
        Action is a WindowEvent to send.
        """
        # Track current button to keep it held
        if not hasattr(self, 'current_button'):
            self.current_button = None
        
        # If we get a new PRESS action, update current_button
        if action and 'PRESS' in str(action):
            self.current_button = action
        # If we get a RELEASE action, clear current_button
        elif action and 'RELEASE' in str(action):
            self.current_button = None
        
        # Always send current button state (keeps it held)
        if self.current_button:
            self.pyboy.send_input(self.current_button)
            
        return self.pyboy.tick()
        
    def get_state(self):
        """
        Returns the current state of the game.
        """
        return {
            "screen": self.pyboy.screen.image,
            "memory": self.pyboy.memory,
            "game_state": {
                "pos": self.memory.get_player_pos(),
                "map_id": self.memory.get_map_id(),
                "party_count": self.memory.get_party_count()
            }
        }
        
    def save_state(self, filename):
        """
        Saves the current emulator state to a file.
        """
        with open(filename, "wb") as f:
            self.pyboy.save_state(f)
        print(f"State saved to {filename}")
    
    def load_state(self, filename):
        """
        Loads emulator state from a file.
        """
        with open(filename, "rb") as f:
            self.pyboy.load_state(f)
        print(f"State loaded from {filename}")

    def stop(self):
        self.pyboy.stop()
