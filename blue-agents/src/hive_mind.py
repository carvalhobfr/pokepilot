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
        """Gravar substituindo, nunca truncando o arquivo bom antes da hora.

        `open(path, 'w')` esvazia o arquivo no instante em que abre. Um
        `SIGKILL` no meio — e nesta máquina de 8 GB a falta de memória mata
        processo sem rastro — deixava `warps.json` vazio ou pela metade, e o
        conhecimento compartilhado de todas as corridas ia junto. Escrever num
        temporário e trocar por `os.replace` é atômico: ou o arquivo antigo
        inteiro, ou o novo inteiro.
        """
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            with open(temporary, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, path)
        except Exception as e:
            print(f"HiveMind Save Error: {e}")

    # --- WARP SYSTEM (Strategy #1) ---
    def _warp_memory(self):
        """O único escritor de `warps.json`.

        Havia dois, com garantias diferentes: `WarpMemory` relê o arquivo,
        funde e troca atomicamente; este aqui guardava a cópia carregada na
        partida e regravava tudo por cima. Com dois agentes no mesmo processo,
        cada um com a sua cópia velha, o segundo a gravar apagava as portas que
        o primeiro tinha descoberto. Delegar mata o segundo escritor.
        """
        from src.warp_memory import WarpMemory

        return WarpMemory(self.maps_dir / "warps.json")

    def _load_warps(self):
        warp_file = self.maps_dir / "warps.json"
        self.known_warps = self._load_json(warp_file)

    def register_warp(self, from_map, x, y, to_map):
        """Register a discovered portal/warp"""
        from_map = str(from_map)
        key = f"{x},{y}"

        if self.known_warps.get(from_map, {}).get(key) is not None:
            return

        memory = self._warp_memory()
        memory.record(from_map, x, y, to_map)
        # Reler o que ficou no disco depois da fusão: o que outro agente achou
        # entra aqui também, em vez de ficar só no arquivo.
        self.known_warps = self._load_json(self.maps_dir / "warps.json")
        print(f"🌀 HIVE MIND: New Warp Discovered! Map {from_map} ({x},{y}) -> Map {to_map}")

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
