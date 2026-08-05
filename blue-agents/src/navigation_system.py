"""
Navigation System & Map Knowledge
Manages exploration saturation and exit finding.
"""
import math

class NavigationSystem:
    def __init__(self):
        self.visited_tiles = {}  # {map_id: set((x, y))}
        self.map_saturation_threshold = 0.8  # 80% coverage triggers exit seeking
        
        # Known connections/exits for early game maps
        # Format: map_id: [(x, y, target_map_name)]
        self.known_exits = {
            # Pallet Town (Map 0)
            0: [
                (10, 0, "Route 1"),   # North Exit to Route 1
                (11, 0, "Route 1"),   # North Exit to Route 1
                (5, 5, "Red's House"), # Red's House
                (13, 5, "Blue's House"), # Blue's House
                (12, 11, "Oak's Lab")  # Oak's Lab
            ],
            # Route 1 (Map 12)
            12: [
                (10, 0, "Viridian City"), # North to Viridian
                (11, 0, "Viridian City"),
                (10, 35, "Pallet Town"),  # South to Pallet
                (11, 35, "Pallet Town")
            ],
            # Viridian City (Map 1)
            1: [
                (21, 35, "Route 1"), # South to Route 1
                (29, 19, "Poke Mart"), # Mart (CRITICAL)
                (32, 7, "Route 2"), # North to Route 2
                (23, 25, "Poke Center") # Center
            ],
            # Oak's Lab (Map 40)
            40: [
                (4, 11, "Pallet Town"), # Exit
                (5, 11, "Pallet Town")
            ]
        }
        
        # Approximate walkable tile counts for saturation calc
        self.map_sizes = {
            0: 60,   # Pallet Town
            12: 80,  # Route 1
            1: 150,  # Viridian City
            40: 30,  # Oak's Lab
        }

    def record_visit(self, map_id, x, y):
        """Record that an agent visited a tile"""
        if map_id not in self.visited_tiles:
            self.visited_tiles[map_id] = set()
        self.visited_tiles[map_id].add((x, y))

    def get_coverage(self, map_id):
        """Get exploration percentage for a map"""
        if map_id not in self.visited_tiles:
            return 0.0
        
        visited = len(self.visited_tiles[map_id])
        total = self.map_sizes.get(map_id, 100) # Default to 100 if unknown
        
        return min(1.0, visited / total)

    def is_zone_saturated(self, map_id):
        """Check if zone is fully explored"""
        return self.get_coverage(map_id) > self.map_saturation_threshold

    def get_nearest_exit(self, map_id, current_x, current_y, exclude_map_ids=None):
        """Find the nearest exit coordinate"""
        if map_id not in self.known_exits:
            return None, None
            
        exits = self.known_exits[map_id]
        nearest = None
        min_dist = float('inf')
        
        for ex, ey, name in exits:
            dist = math.sqrt((ex - current_x)**2 + (ey - current_y)**2)
            if dist < min_dist:
                min_dist = dist
                nearest = (ex, ey)
                
        return nearest
