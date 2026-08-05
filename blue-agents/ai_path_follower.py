"""
AI Path Follower - Allows agents to follow AI-generated navigation paths
"""
import json
from pathlib import Path

class AIPathFollower:
    """Reads and executes AI-generated navigation instructions"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.instructions_dir = Path(__file__).parent.parent / "tasks" / "ai_instructions"
        self.path_file = self.instructions_dir / f"{agent_name.lower()}_path.json"
        self.current_path = None
        self.current_waypoint_index = 0
        self.last_mtime = 0
        
    def check_for_new_path(self):
        """Check if AI has provided a new path"""
        if not self.path_file.exists():
            return False
        
        # Check if file was modified
        mtime = self.path_file.stat().st_mtime
        if mtime > self.last_mtime:
            self.load_path()
            self.last_mtime = mtime
            return True
        return False
    
    def load_path(self):
        """Load the AI-generated path"""
        try:
            with open(self.path_file, 'r') as f:
                self.current_path = json.load(f)
            self.current_waypoint_index = 0
            print(f"🤖 [{self.agent_name}] AI Path loaded: {self.current_path.get('current_objective', 'Unknown')}")
            return True
        except Exception as e:
            print(f"⚠️ [{self.agent_name}] Failed to load AI path: {e}")
            return False
    
    def get_current_objective(self):
        """Get the current objective description"""
        if not self.current_path:
            return None
        return self.current_path.get('current_objective')
    
    def get_current_waypoint(self):
        """Get the current waypoint to execute"""
        if not self.current_path or not self.current_path.get('waypoints'):
            return None
        
        waypoints = self.current_path['waypoints']
        if self.current_waypoint_index >= len(waypoints):
            return None  # Path completed
        
        return waypoints[self.current_waypoint_index]
    
    def mark_waypoint_complete(self):
        """Move to next waypoint"""
        self.current_waypoint_index += 1
        waypoint = self.get_current_waypoint()
        if waypoint:
            print(f"📍 [{self.agent_name}] Next waypoint: {waypoint.get('description', 'Unknown')}")
        else:
            print(f"✅ [{self.agent_name}] AI Path completed!")
            self.clear_path()
    
    def clear_path(self):
        """Clear the current path"""
        self.current_path = None
        self.current_waypoint_index = 0
        # Optionally delete the file
        if self.path_file.exists():
            self.path_file.unlink()
    
    def get_target_map_id(self):
        """Get the target map ID from current path"""
        if not self.current_path:
            return None
        return self.current_path.get('target_map_id')
    
    def has_active_path(self):
        """Check if there's an active AI path"""
        return self.current_path is not None and self.get_current_waypoint() is not None

if __name__ == "__main__":
    # Test
    follower = AIPathFollower("TestAgent")
    print(f"Has active path: {follower.has_active_path()}")
