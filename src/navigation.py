from pyboy.utils import WindowEvent

class Navigation:
    def __init__(self, emulator):
        self.emulator = emulator
        self.memory = emulator.memory

    def get_path_to(self, target_x, target_y):
        """
        Simple heuristic pathfinding.
        Returns the next action to take to get closer to target.
        """
        current_x, current_y = self.memory.get_player_pos()
        
        dx = target_x - current_x
        dy = target_y - current_y
        
        if dx == 0 and dy == 0:
            return None
            
        # Simple Manhattan movement
        if abs(dx) > abs(dy):
            if dx > 0:
                return WindowEvent.PRESS_ARROW_RIGHT
            else:
                return WindowEvent.PRESS_ARROW_LEFT
        else:
            if dy > 0:
                return WindowEvent.PRESS_ARROW_DOWN
            else:
                return WindowEvent.PRESS_ARROW_UP
