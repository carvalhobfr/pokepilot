"""
Hive Mind - Shared Intelligence System
Manages collective knowledge about maps, quests, and survival.
"""
import json
import os
from pathlib import Path
import time

class HiveMind:
    def __init__(self, knowledge_root=None):
        if knowledge_root:
            self.root = Path(knowledge_root)
        else:
            self.root = Path(__file__).parent.parent / "knowledge"
            
        self.maps_dir = self.root / "maps"
        self.quests_dir = self.root / "quests"
        self.walkthrough_file = self.root / "walkthrough" / "game_walkthrough.json"
        
        # Load static knowledge
        self.walkthrough = self._load_json(self.walkthrough_file)
        
        # In-memory cache of dynamic knowledge
        self.known_warps = {} # {from_map: { (x,y): to_map }}
        self._load_warps()

    def _load_json(self, path):
        if path.exists():
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_json(self, path, data):
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"HiveMind Save Error: {e}")

    # --- WARP SYSTEM (Strategy #1) ---
    def _load_warps(self):
        warp_file = self.maps_dir / "warps.json"
        self.known_warps = self._load_json(warp_file)

    def register_warp(self, from_map, x, y, to_map):
        """Register a discovered portal/warp"""
        from_map = str(from_map)
        key = f"{x},{y}"
        
        if from_map not in self.known_warps:
            self.known_warps[from_map] = {}
            
        if key not in self.known_warps[from_map]:
            self.known_warps[from_map][key] = to_map
            print(f"🌀 HIVE MIND: New Warp Discovered! Map {from_map} ({x},{y}) -> Map {to_map}")
            self._save_json(self.maps_dir / "warps.json", self.known_warps)

    def get_warp_to(self, current_map, target_zone_maps):
        """Find a warp in current map that leads to a target zone"""
        current_map = str(current_map)
        if current_map not in self.known_warps:
            return None
            
        for pos_key, dest_map in self.known_warps[current_map].items():
            if dest_map in target_zone_maps:
                x, y = map(int, pos_key.split(','))
                return (x, y)
        return None

    # --- QUEST SYSTEM (Strategy #3) ---
    def get_active_quest(self, state):
        """Determine active quest based on game state"""
        if not self.walkthrough: return None
        
        for quest in self.walkthrough.get("quests", []):
            cond = quest["condition"]
            
            # Check conditions
            if "badges" in cond and state["badges"] != cond["badges"]: continue
            if "pokedex" in cond and state["has_pokedex"] != cond["pokedex"]: continue
            if "item_missing" in cond and cond["item_missing"] in state["items"]: continue
            if "item_present" in cond and cond["item_present"] not in state["items"]: continue
            
            return quest # Found matching quest
            
        return None

    # --- SURVIVAL SYSTEM (Strategy #2) ---
    def get_safe_spot(self, current_map):
        """Find nearest safe spot (Poke Center/House)"""
        if not self.walkthrough: return None
        
        # Find which zone we are in
        current_zone = None
        for zone_id, zone_data in self.walkthrough.get("zones", {}).items():
            if current_map in zone_data["map_ids"]:
                current_zone = zone_data
                break
        
        if current_zone and "safe_spots" in current_zone:
            # Return first safe spot in zone (simplified)
            return current_zone["safe_spots"][0]
            
        return None
