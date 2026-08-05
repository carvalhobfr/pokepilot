"""
Shared Strategy Library - Allows agents to learn from each other's AI strategies
Saves money by reusing strategies for similar situations
"""
import json
from pathlib import Path
import hashlib

class SharedStrategyLibrary:
    """
    Manages a shared library of AI-generated strategies
    Agents can query and reuse strategies from similar situations
    """
    
    def __init__(self):
        self.library_dir = Path(__file__).parent.parent / "tasks" / "strategy_library"
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.library_dir / "index.json"
        self._load_index()
    
    def _load_index(self):
        """Load the strategy index"""
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                self.index = json.load(f)
        else:
            self.index = {"strategies": []}
    
    def _save_index(self):
        """Save the strategy index"""
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2)
    
    def _situation_hash(self, agent_state):
        """Create a hash to identify similar situations"""
        # Use badges, map_id, and party size as situation signature
        situation = {
            "badges": agent_state.get('badges', 0),
            "map_id": agent_state.get('map_id', 0),
            "party_count": len(agent_state.get('party', [])),
            "pokedex_owned": agent_state.get('pokedex_owned', 0)
        }
        situation_str = json.dumps(situation, sort_keys=True)
        return hashlib.md5(situation_str.encode()).hexdigest()[:8]
    
    def save_strategy(self, agent_name, agent_state, strategy_json):
        """
        Save a strategy to the shared library
        
        Args:
            agent_name: Name of agent who got this strategy
            agent_state: Game state when strategy was generated
            strategy_json: The AI-generated strategy (dict)
        """
        situation_hash = self._situation_hash(agent_state)
        
        # Create strategy entry
        entry = {
            "situation_hash": situation_hash,
            "agent": agent_name,
            "badges": agent_state.get('badges', 0),
            "map_id": agent_state.get('map_id', 0),
            "pokedex_owned": agent_state.get('pokedex_owned', 0),
            "party_count": len(agent_state.get('party', [])),
            "strategy": strategy_json,
            "timestamp": __import__('time').time()
        }
        
        # Save individual strategy file
        strategy_file = self.library_dir / f"strategy_{situation_hash}.json"
        with open(strategy_file, 'w') as f:
            json.dump(entry, f, indent=2)
        
        # Update index
        # Remove old entry for same situation if exists
        self.index["strategies"] = [s for s in self.index["strategies"] 
                                     if s.get("situation_hash") != situation_hash]
        
        # Add new entry
        self.index["strategies"].append({
            "situation_hash": situation_hash,
            "badges": entry["badges"],
            "map_id": entry["map_id"],
            "pokedex_owned": entry["pokedex_owned"],
            "file": f"strategy_{situation_hash}.json"
        })
        
        self._save_index()
        print(f"💾 Strategy saved to library: {situation_hash} (badges={entry['badges']}, map={entry['map_id']})")
    
    def find_similar_strategy(self, agent_state):
        """
        Find a strategy for a similar situation
        
        Returns:
            Strategy JSON if found, None otherwise
        """
        situation_hash = self._situation_hash(agent_state)
        
        # Look for exact match first
        for entry in self.index["strategies"]:
            if entry["situation_hash"] == situation_hash:
                strategy_file = self.library_dir / entry["file"]
                if strategy_file.exists():
                    with open(strategy_file, 'r') as f:
                        data = json.load(f)
                        print(f"♻️ Reusing strategy from library: {situation_hash}")
                        return data["strategy"]
        
        # Look for similar situation (same badges + pokedex status)
        badges = agent_state.get('badges', 0)
        pokedex = agent_state.get('pokedex_owned', 0)
        
        for entry in self.index["strategies"]:
            if (entry.get("badges") == badges and 
                entry.get("pokedex_owned", 0) == pokedex):
                strategy_file = self.library_dir / entry["file"]
                if strategy_file.exists():
                    with open(strategy_file, 'r') as f:
                        data = json.load(f)
                        print(f"♻️ Reusing similar strategy: badges={badges}, pokedex={pokedex > 0}")
                        return data["strategy"]
        
        return None  # No similar strategy found
    
    def get_all_strategies(self):
        """Get all strategies in the library"""
        strategies = []
        for entry in self.index["strategies"]:
            strategy_file = self.library_dir / entry["file"]
            if strategy_file.exists():
                with open(strategy_file, 'r') as f:
                    strategies.append(json.load(f))
        return strategies

if __name__ == "__main__":
    # Test
    library = SharedStrategyLibrary()
    
    # Simulate agent state
    test_state = {
        "badges": 0,
        "map_id": 40,
        "party": [{"species_id": 1, "level": 5}],
        "pokedex_owned": 0
    }
    
    # Try to find similar strategy
    strategy = library.find_similar_strategy(test_state)
    if strategy:
        print("Found strategy:", strategy.get("current_objective"))
    else:
        print("No similar strategy found")
