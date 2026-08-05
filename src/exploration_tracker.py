"""
Exploration tracking system adapted from PokemonRedExperiments.
Tracks visited coordinates and provides exploration rewards/statistics.
"""

import numpy as np
from pathlib import Path
import json


class ExplorationTracker:
    """
    Tracks which tiles the agent has visited across all maps.
    Provides exploration rewards and coverage statistics.
    
    Adapted from: https://github.com/PWhiddy/PokemonRedExperiments
    """
    
    def __init__(self, save_dir="runs"):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(exist_ok=True)
        
        # Track unique (map_id, x, y) coordinates visited
        self.seen_coords = set()
        
        # Track exploration per map for analytics
        self.map_exploration = {}  # {map_id: set((x, y))}
        
        # Base exploration count (for reward calculation)
        self.base_explore = 0
        
        # Stats
        self.total_tiles_visited = 0
        self.exploration_rewards = []
        
    def update(self, map_id, x, y):
        """
        Update exploration state with current position.
        Returns exploration reward for this step.
        """
        coord_key = (map_id, x, y)
        
        # Check if this is a new coordinate
        is_new = coord_key not in self.seen_coords
        
        if is_new:
            self.seen_coords.add(coord_key)
            self.total_tiles_visited += 1
            
            # Update per-map tracking
            if map_id not in self.map_exploration:
                self.map_exploration[map_id] = set()
            self.map_exploration[map_id].add((x, y))
            
            # Calculate reward (0.1 per new tile)
            reward = 0.1
            self.exploration_rewards.append(reward)
            return reward
        
        return 0.0  # No reward for revisiting
    
    def get_map_coverage(self, map_id):
        """Get number of unique tiles visited in a specific map."""
        return len(self.map_exploration.get(map_id, set()))
    
    def get_total_coverage(self):
        """Get total number of unique tiles visited across all maps."""
        return len(self.seen_coords)
    
    def get_map_coverage_percent(self, map_id, total_tiles=None):
        """
        Get coverage percentage for a map.
        If total_tiles not provided, returns tile count instead.
        """
        visited = self.get_map_coverage(map_id)
        if total_tiles:
            return (visited / total_tiles) * 100
        return visited
    
    def get_stats(self):
        """Get exploration statistics."""
        return {
            "total_tiles_visited": self.total_tiles_visited,
            "unique_maps_visited": len(self.map_exploration),
            "total_exploration_reward": sum(self.exploration_rewards),
            "maps_breakdown": {
                map_id: len(coords) 
                for map_id, coords in self.map_exploration.items()
            }
        }
    
    def save_stats(self, filename="exploration_stats.json"):
        """Save exploration stats to JSON."""
        stats = self.get_stats()
        filepath = self.save_dir / filename
        with open(filepath, 'w') as f:
            json.dump(stats, f, indent=2)
        print(f"Exploration stats saved to {filepath}")
    
    def reset(self):
        """Reset exploration tracking."""
        self.seen_coords.clear()
        self.map_exploration.clear()
        self.total_tiles_visited = 0
        self.exploration_rewards.clear()
    
    def has_visited(self, map_id, x, y):
        """Check if a specific coordinate has been visited."""
        return (map_id, x, y) in self.seen_coords
    
    def get_exploration_heatmap(self, map_id, map_width=None, map_height=None):
        """
        Generate a 2D heatmap of visited tiles for a specific map.
        Returns numpy array where 255 = visited, 0 = not visited.
        """
        if map_id not in self.map_exploration:
            return None
        
        coords = self.map_exploration[map_id]
        
        # Auto-detect dimensions if not provided
        if not map_width or not map_height:
            max_x = max(c[0] for c in coords) + 1
            max_y = max(c[1] for c in coords) + 1
            map_width = map_width or max_x
            map_height = map_height or max_y
        
        # Create heatmap
        heatmap = np.zeros((map_width, map_height), dtype=np.uint8)
        for x, y in coords:
            if x < map_width and y < map_height:
                heatmap[x, y] = 255
        
        return heatmap
    
    def print_summary(self):
        """Print exploration summary."""
        print("\n" + "="*50)
        print("EXPLORATION SUMMARY")
        print("="*50)
        print(f"Total Tiles Visited: {self.total_tiles_visited}")
        print(f"Unique Maps Explored: {len(self.map_exploration)}")
        print(f"Total Exploration Reward: {sum(self.exploration_rewards):.2f}")
        print("\nBreakdown by Map:")
        for map_id, coords in sorted(self.map_exploration.items()):
            print(f"  Map {map_id}: {len(coords)} tiles")
        print("="*50 + "\n")


# Example usage
if __name__ == "__main__":
    tracker = ExplorationTracker()
    
    # Simulate agent movement
    tracker.update(map_id=38, x=3, y=6)  # Bedroom
    tracker.update(map_id=38, x=4, y=6)  # Move right
    tracker.update(map_id=38, x=4, y=5)  # Move up
    tracker.update(map_id=37, x=7, y=1)  # Living room
    
    # Get stats
    tracker.print_summary()
    tracker.save_stats()
