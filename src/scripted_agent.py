import json
import time
from pathlib import Path
from pyboy.utils import WindowEvent
from src.agent import BaseAgent
import os
from datetime import datetime

from src.llm_agent import LLMAgent

from src.navigation import Navigation
from src.exploration_tracker import ExplorationTracker
from src.warp_memory import WarpMemory
from src.map_memory import MapMemory
from src.tile_collision import TileCollision
from src.route_trails import TrailRecorder, TrailStore, waypoints_from

# How many A presses a route spends on a dialogue before it walks anyway. The
# menu flag at 0xCFC4 has been observed stuck at 1 with no text on screen.
MENU_PRESS_LIMIT = 12

# Fração do HP total do time abaixo da qual a viagem até o Centro vale a pena.
# Regra por Pokémon mandava voltar cedo demais: 29/30 atravessava a cidade.
HEAL_HP_FRACTION = 0.20

# The north street in Viridian has a scripted NPC on the approach tile. The
# route must reach that tile before leaving so a blocking sprite can be talked
# to instead of being treated as ordinary geometry.
# Every Pokémon Center in Gen I is the same building inside: nurse at (3,3),
# doormat at (3,7). Every Mart likewise, clerk behind the top-left counter. That
# is what makes "the nearest one" a real controller instead of one more route
# measured by hand for one city.
# Onde o cartucho devolve o treinador depois de um apagão. Guarda o mapa de
# **fora** do último Centro usado — 1 para Viridian, 15 para a Rota 4.
LAST_BLACKOUT_MAP_ADDRESS = 0xD719

# Os Centros vêm do cartucho, não da memória de ninguém: tileset 6, 4×7, e o
# ponteiro de texto seis bytes depois do de script. Ver
# `blue-agents/tools/extract_centers.py`, que gera o arquivo abaixo.
#
# A lista escrita à mão errava dos dois lados. Faltava o 81, o Centro da Rota
# 10 antes do Túnel da Rocha. E sobrava o 174, o saguão do Indigo, que tem
# outro tileset e é 6×8 — o controlador genérico procuraria uma enfermeira em
# (3,3) e um capacho em (3,7) que não existem lá. O 140 parece Centro e não é:
# é o Hotel de Celadon, mesma casca e outro roteiro.
_CENTERS_PATH = (
    Path(__file__).resolve().parents[1]
    / "blue-agents" / "knowledge" / "maps" / "pokemon_centers.json"
)


def _load_centers():
    """Centros, mapa de fora de cada um, e a porta vista de fora."""
    try:
        with open(_CENTERS_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return set(), {}, {}
    centers = {int(map_id) for map_id in payload.get("centers", [])}
    outdoor, doors = {}, {}
    for center, entries in (payload.get("doors") or {}).items():
        for entry in entries:
            outdoor.setdefault(int(center), int(entry["map"]))
            doors.setdefault(int(entry["map"]), []).append(
                (int(entry["x"]), int(entry["y"]))
            )
    return centers, outdoor, doors


POKEMON_CENTER_MAP_IDS, CENTER_OUTDOOR_MAP, CENTER_DOOR_BY_OUTDOOR_MAP = _load_centers()
VIRIDIAN_CENTER_MAP_ID = 41
# Only Viridian's is proven — it is the one this project has actually walked
# into and bought from. A Mart id that is wrong here sends a trainer through
# the wrong door, so this set grows by measurement, never by memory. Until
# then `_run_nearest_mart` simply finds no door in other cities and the caller
# falls back to what it did before.
POKE_MART_MAP_IDS = {42}
SHOP_COUNTER_TILE = (2, 5)

# The hand-drawn route is the path that finishes the game, so it drives.
# Trails keep being recorded and published — they are the measurement of what a
# crossing cost — but *following* one is opt-in. Exploration is optional; the
# route is not.
FOLLOW_TRAILS = os.getenv("POKEAI_FOLLOW_TRAILS", "0") == "1"

VIRIDIAN_CITY_MAP_ID = 1
VIRIDIAN_OLD_MAN_APPROACH = (17, 4)
VIRIDIAN_NORTH_EXIT = (17, 0)
VIRIDIAN_OLD_MAN_DIALOG_LIMIT = 48

# Level is what separates crossing the Forest from dying in it. The wild
# Caterpie are harmless; the bug catchers on the way north are not, and a party
# whose best is level 8 loses to the first one — measured, twice, ten steps in.
VIRIDIAN_FOREST_MAP_ID = 51
FOREST_MIN_LEVEL = 12
# A gate with no way out is worse than a death: if the grass will not deliver
# the levels, cross anyway rather than pace forever.
FOREST_TRAINING_STEPS = 4000

# Steps spent waiting for a person to move before walking around them. People
# in Gen I pace on their own; walls do not.
SPRITE_PATIENCE_STEPS = 6

# Steps spent unable to get any closer before the route gives up on this anchor
# and backs up to the previous one.
UNREACHABLE_PATIENCE_STEPS = 8

# How far south to aim when leaving a map whose door was never observed. Kanto
# interiors are small; this clears any of them.
BLIND_EXIT_REACH = 10

# Failed cycles on the same tile before the route stops believing anything it
# knows about that tile. Each cycle is four steps plus a text attempt.
STUCK_TILE_AMNESTY_CYCLES = 6

# Tiles remembered to notice pacing. Two visits to the same tile inside this
# window is a bot going back and forth, not a bot walking a corridor. Eight
# covers the four-step cycle that kept a trainer between (6,30) and (8,30) in
# the Forest; three would only have caught the two-tile version.
ROUTE_MEMORY_TILES = 8

ROUTE_STEP_OFFSETS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}

# Learned walls live with the rest of the map knowledge, not inside a trainer:
# geometry is the same for everyone who walks it.
# Doors already had a home in the knowledge directory; only free exploration
# ever wrote to it, and the scripted journey never read it.
SHARED_TERRAIN_PATH = (
    Path(__file__).resolve().parents[1]
    / "blue-agents" / "knowledge" / "maps" / "terrain.json"
)

# Writing a few thousand tiles every step is pointless; the map is only useful
# across runs, and a crash costs at most this many steps of looking.
TERRAIN_SAVE_INTERVAL = 200

# How far from its own plan a trainer has to be before the trail is joined
# again. Short enough to recover from a whiteout, long enough that a detour
# around one tree is not a reason to start over.
TRAIL_REJOIN_DISTANCE = 12

# Passos em que a volta pela fronteira recém-atravessada fica retida. Só vale
# parado no tile de chegada: sair dele e voltar continua permitido.
ENTRY_BLOCK_STEPS = 4

# Só vale procurar o desconhecido quando o alvo ainda está longe. Perto dele,
# "explorar" é dar as costas para a porta em que já se está encostado.
FRONTIER_MIN_DISTANCE = 3

# Passos sem encurtar a distância até o alvo antes de aceitar que o caminho
# está fechado. Menos que isso confunde batalha no mato com estar preso: o
# encontro congela o bot no lugar e o tile se repete sozinho.
NO_PROGRESS_STEPS = 15

# Passos sem progresso antes de aceitar que o waypoint está errado para onde o
# bot está, e mirar numa porta do mapa em vez de insistir.
STUCK_GIVE_UP_STEPS = 40

# Passos que uma parede descoberta na marra vale. Curto de propósito: gente
# some, e a leitura do cartucho continua sendo a fonte principal.
BUMP_MEMORY_STEPS = 8

# Passos parado no mesmo tile antes de gravar um relatório de travamento. O
# segundo relatório do mesmo tile sai no dobro, o terceiro no triplo: quem trava
# de verdade fica registrado, e quem só esperou um NPC não polui o arquivo.
STUCK_REPORT_STEPS = 30

# Janela olhada para decidir se ele está preso, e quantos lugares diferentes
# dentro dela ainda contam como parado. Dois tiles alternados são parados.
STUCK_WINDOW_TILES = 12
# Quatro, não três: entrar e sair de uma porta muda o mapa e conta como lugar
# novo, e era assim que o vaivém na porta do Centro escapava do gatilho.
STUCK_DISTINCT_TILES = 4
# Quantas trocas de mapa seguidas entre os mesmos dois mapas já contam como
# vaivém. Seis é curto o bastante para pegar o ciclo em segundos e longo o
# bastante para não acusar quem entra numa porta e sai porque terminou ali.
STUCK_MAP_CROSSINGS = 6

# A âncora de aproximação da boca de Mt. Moon, na Rota 4. Quem já está em x=11
# ou mais a leste passou dela; voltar para trás é o que fechava o ciclo com a
# caverna.
MT_MOON_APPROACH_X = 11

# Mapas onde um Centro fica no caminho e a próxima etapa não tem nenhum.
# Viridian antes da Floresta, Pewter antes da Rota 3.
CENTER_ON_THE_WAY = {1, 2, 15}

# Abaixo disso vale parar no Centro que já está no caminho. Bem acima do
# limite de emergência: entrar na Floresta pela metade é morrer no meio dela.
TOP_UP_HP_FRACTION = 0.7

# A Floresta é atravessada de sul para norte. Passando da metade, o Centro mais
# perto é o de Pewter, e ele fica no caminho — voltar custa a travessia inteira.
FOREST_MIDPOINT_Y = 24
ROUTE_2_NORTH_Y = 20

SHARED_WARP_PATH = (
    Path(__file__).resolve().parents[1]
    / "blue-agents" / "knowledge" / "maps" / "warps.json"
)

OPPOSITE_DIRECTIONS = {"U": "D", "D": "U", "L": "R", "R": "L"}

ROUTE_EVENTS = {
    "U": WindowEvent.PRESS_ARROW_UP,
    "D": WindowEvent.PRESS_ARROW_DOWN,
    "L": WindowEvent.PRESS_ARROW_LEFT,
    "R": WindowEvent.PRESS_ARROW_RIGHT,
}

class ScriptedAgent(BaseAgent):
    def __init__(self, walkthrough_path, emulator=None, player_name="AARON", save_dir=".", starter_choice=None, route_role="follower"):
        with open(walkthrough_path, 'r') as f:
            self.walkthrough = json.load(f)
            
        # Load extra knowledge (Brock Guide)
        try:
            guide_candidates = [
                Path(walkthrough_path).resolve().parent / "docs/cidades/1/brock.json",
                Path(__file__).resolve().parents[1] / "docs/cidades/1/brock.json",
            ]
            brock_guide_path = next(
                (candidate for candidate in guide_candidates if candidate.exists()),
                None,
            )
            if brock_guide_path is None:
                raise FileNotFoundError("Pokemon Blue detonado not found")
            with open(brock_guide_path, 'r') as f:
                self.brock_guide = json.load(f)
        except FileNotFoundError:
            print("Warning: brock.json not found.")
            self.brock_guide = {}
        
        self.emulator = emulator
        self.llm_agent = LLMAgent(knowledge=self.brock_guide) # Pass knowledge to LLM
        self.navigation = Navigation(emulator) if emulator else None
        self.exploration = ExplorationTracker(save_dir=save_dir)  # NEW
        self.player_name = player_name
        self.save_dir = save_dir
        self.starter_choice = starter_choice
        # The guide walks the route as drawn and nothing else, so that getting
        # stuck stays a readable verdict on the route instead of being papered
        # over. The follower inherits whatever the guide has already proved.
        self.route_role = route_role
        self.trail_store = TrailStore()
        self.trail_recorder = TrailRecorder()
        self.current_step = 0
        self.steps = self._flatten_actions(self.walkthrough)
        
    def step(self, task_name=None):
        """
        Executes the next step for the given task.
        If task_name is provided and different from current, switches context.
        """
        if task_name:
            # Normalize task name
            task_name = task_name.lower()
            if task_name == "brock":
                task_name = "brock_quest"
            
            # Check if we need to switch tasks
            if not hasattr(self, 'current_task_name') or self.current_task_name != task_name:
                native_controller = hasattr(self, f"_run_{task_name}")
                if (
                    "game_flow" in self.walkthrough
                    and task_name in self.walkthrough["game_flow"]
                ) or native_controller:
                    self.steps = (
                        self.walkthrough["game_flow"][task_name]["actions"]
                        if task_name in self.walkthrough.get("game_flow", {})
                        else []
                    )
                    self.current_step = 0
                    self.current_task_name = task_name
                    # Reset internal state variables for new task
                    if hasattr(self, 'tick_counter'): del self.tick_counter
                    if hasattr(self, 'seq_index'): del self.seq_index
                    if hasattr(self, 'seq_timer'): del self.seq_timer
                    if hasattr(self, 'route_id'): del self.route_id
                    if hasattr(self, 'route_index'): del self.route_index
                    print(f"[{self.player_name}] Switched to task: {task_name}")
                else:
                    # print(f"[{self.player_name}] Warning: Task '{task_name}' not found in walkthrough.")
                    pass

        if getattr(self, "current_task_name", None) == "start" and self.emulator:
            return self._run_start_deterministic()
        return self.get_action(None)

    def _run_start_deterministic(self):
        """Complete the opening walk without the legacy timed action list."""
        map_id = int(self.emulator.memory.get_map_id())
        position = self.emulator.memory.get_player_pos()
        if map_id == 38:
            return self._follow_route("start-bedroom", [(5, 6), (5, 1), (7, 1)])
        if map_id == 37:
            return self._follow_route("start-house-1f", [(7, 6), (3, 6), (3, 8)])
        if map_id == 0:
            oak_appeared = bool(self.emulator.memory.read_byte(0xD74B) & 0x80)
            if oak_appeared or position[1] <= 1:
                return WindowEvent.PRESS_BUTTON_A
            return self._follow_route("start-pallet", [(10, 6), (10, 1)])
        if map_id == 40:
            if self._menu_is_open():
                # Oak's starter description uses consecutive confirmations;
                # alternating B here leaves CC50/CFC4 open forever.
                return WindowEvent.PRESS_BUTTON_A
            if self.emulator.memory.get_party_count() == 0:
                return self._choose_starter_verified()
            return self._complete_oak_rival_event()
        return None

    def get_current_task_name(self):
        return getattr(self, 'current_task_name', 'start')

    def _flatten_actions(self, walkthrough):
        """
        Flattens the hierarchical JSON into a linear list of actions.
        This is a simplification. A real implementation would need a state machine.
        """
        actions = []
        # Default to "start" if available
        if "game_flow" in walkthrough and "start" in walkthrough["game_flow"]:
            actions.extend(walkthrough["game_flow"]["start"]["actions"])
            self.current_task_name = "start"
        return actions

    def get_action(self, state):
        """
        Decides the next action based on the current step and game state.
        """
        if self.current_step >= len(self.steps):
            # Script finished. If we have LLM, ask for guidance instead of giving up.
            if self.llm_agent:
                # Fallthrough to LLM logic below
                pass
            else:
                return None # Done
        
        # Track exploration (update visited tiles)
        if self.emulator:
            map_id = self.emulator.memory.get_map_id()
            pos = self.emulator.memory.get_player_pos()
            if pos != (0, 0):  # Only track if position is valid
                self.exploration.update(map_id, pos[0], pos[1])
        
        # Auto-detect step from checkpoint (first time only)
        if not hasattr(self, 'checkpoint_step_detected'):
            self._detect_checkpoint_step()
            self.checkpoint_step_detected = True
            
        # Stuck Detection
        if not hasattr(self, 'last_step_change_frame'):
            self.last_step_change_frame = 0
            self.last_step_index = 0
            self.last_progress_position = None

        # Native quest executors intentionally keep ``current_step`` fixed.
        # Treat real movement as progress too, otherwise the legacy watchdog
        # eventually injects random directions while a route is working.
        if self.emulator:
            progress_position = (
                int(self.emulator.memory.get_map_id()),
                tuple(self.emulator.memory.get_player_pos()),
            )
            if progress_position != self.last_progress_position:
                self.last_progress_position = progress_position
                self.last_step_change_frame = self.emulator.pyboy.frame_count
            
        if self.current_step != self.last_step_index:
            self.last_step_index = self.current_step
            if self.emulator:
                self.last_step_change_frame = self.emulator.pyboy.frame_count
        
        # If stuck for 100000 frames (approx 30 mins at 60fps, but faster in headless), save and exit
        # In headless, this might be ~1-2 minutes depending on speed
        if self.emulator and (self.emulator.pyboy.frame_count - self.last_step_change_frame > 100000):
            print(f"Stuck detected! No progress for 100000 frames. Resetting navigation state...")
            # Save with timestamp and name just for debugging
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.save_dir}/stuck_{self.player_name}_{timestamp}.state"
            self.emulator.save_state(filename)
            
            # Reset internal state to try again or unstuck
            if hasattr(self, 'nav_timer'): del self.nav_timer
            if hasattr(self, 'tick_counter'): del self.tick_counter
            
            # Update last change frame to avoid spamming
            self.last_step_change_frame = self.emulator.pyboy.frame_count
            
            # Return random action to try to unstuck
            import random
            return random.choice([
                WindowEvent.PRESS_ARROW_UP, WindowEvent.PRESS_ARROW_DOWN, 
                WindowEvent.PRESS_ARROW_LEFT, WindowEvent.PRESS_ARROW_RIGHT
            ])

        # Check for battle
        is_battle = False
        if self.emulator:
            battle_status = self.emulator.memory.read_byte(0xD057)
            is_battle = battle_status != 0
        if is_battle:
            self.was_in_battle = True
            # print("Battle detected! Using simple battle logic (No LLM)...")
            
            # Simple Battle Strategy: Spam A to attack/advance text
            # This is much faster and saves LLM for story decisions
            return WindowEvent.PRESS_BUTTON_A
            
            # OLD LLM LOGIC (Disabled per user request)
            # battle_state = self.emulator.memory.get_battle_state()
            # action = self.llm_agent.get_battle_action(battle_state)
            # if action:
            #     return action
            # return WindowEvent.PRESS_BUTTON_A
        
        # Check if we just finished a battle
        if hasattr(self, 'was_in_battle') and self.was_in_battle and not is_battle:
            print("Battle finished!")
            self.was_in_battle = False
            self.battle_finished = True

        if self.current_step < len(self.steps):
            action_desc = self.steps[self.current_step]
            if not hasattr(self, 'last_printed_objective') or self.last_printed_objective != action_desc:
                print(f"Current Objective: {action_desc}")
                self.last_printed_objective = action_desc
        else:
            action_desc = "Explore and advance story"
            if not hasattr(self, 'last_printed_objective') or self.last_printed_objective != action_desc:
                print(f"Current Objective: {action_desc} (LLM Autopilot)")
                self.last_printed_objective = action_desc
        
        # Simple state machine for "Start -> New Game"
        # This is hardcoded for demo purposes. 
        # Real implementation needs a proper sequence manager.
        
        if self.emulator:
            pos = self.emulator.memory.get_player_pos()
            map_id = self.emulator.memory.get_map_id()
            
            # Cutscene Detection: Check if player moved without our input
            if hasattr(self, 'last_pos') and hasattr(self, 'last_action_was_move'):
                if pos != self.last_pos and not self.last_action_was_move:
                    print(f"[CUTSCENE] Player moving automatically! Waiting...")
                    self.last_pos = pos
                    return None # Wait/PASS
            
            self.last_pos = pos
            self.last_action_was_move = False # Reset flag, will be set if we return a move action

            if self.emulator.pyboy.frame_count % 60 == 0:
                # print(f"Debug - Step: {action_desc}, Map: {map_id}, Pos: {pos}")
                pass

            # Self-Correction: If in Bedroom (Map 38) but step is "Start" or "Intro" or "Naming" (steps 0, 1, 2)
            # We should be at least at step 3 "Leave house"
            if map_id == 38 and self.current_task_name == "start" and self.current_step < 3:
                 print(f"[CORRECTION] In Bedroom but at step {self.current_step}. Jumping to Step 3 (Leave House).")
                 self.current_step = 3
                 return None # Skip this frame to let loop update action_desc

        center_action = self._center_first_action()
        if center_action is not None:
            return center_action

        if getattr(self, "current_task_name", None) == "parcel_event":
            return self._run_parcel_event()
        if getattr(self, "current_task_name", None) == "buy_pokeballs":
            return self._run_buy_pokeballs()
        if getattr(self, "current_task_name", None) == "route_2_nav":
            return self._run_route_2_nav()
        if getattr(self, "current_task_name", None) == "viridian_forest_nav":
            return self._run_viridian_forest_nav()
        if getattr(self, "current_task_name", None) == "pewter_city_nav":
            return self._run_pewter_city_nav()
        if getattr(self, "current_task_name", None) == "brock_quest":
            return self._run_brock_quest()
        if getattr(self, "current_task_name", None) == "mt_moon_nav":
            return self._run_mt_moon_nav()
        if getattr(self, "current_task_name", None) == "bill_quest":
            return self._run_bill_quest()
        if getattr(self, "current_task_name", None) == "cerulean_gym_quest":
            return self._run_cerulean_gym_quest()

        if action_desc == "Start -> New Game":
            # Sequence: Press Start -> Wait -> Press A (New Game) -> Wait
            # We need to maintain internal state to know where we are in this sequence
            
            # Hacky implementation using static counter for now
            if not hasattr(self, 'tick_counter'):
                self.tick_counter = 0
            
            self.tick_counter += 1
            
            # Slower sequence to ensure we hit the menu
            if self.tick_counter == 60:
                return WindowEvent.PRESS_BUTTON_START
            elif self.tick_counter == 65:
                return WindowEvent.RELEASE_BUTTON_START
            elif self.tick_counter == 180: # Wait 2s
                return WindowEvent.PRESS_BUTTON_START # Press Start again just in case
            elif self.tick_counter == 185:
                return WindowEvent.RELEASE_BUTTON_START
            elif self.tick_counter == 300: # Wait more
                return WindowEvent.PRESS_BUTTON_A # Select New Game / Continue
            elif self.tick_counter == 305:
                return WindowEvent.RELEASE_BUTTON_A
            elif self.tick_counter == 360:
                return WindowEvent.PRESS_BUTTON_A # Confirm New Game
            elif self.tick_counter == 365:
                return WindowEvent.RELEASE_BUTTON_A
            elif self.tick_counter > 420:
                # Done with this step, move to next
                self.current_step += 1
                self.tick_counter = 0
                return None
            
            return None

        if action_desc == "Complete Oak introduction":
            # Just spam A for a while to get through text
            # In a real implementation, we would check memory for text state
            
            if not hasattr(self, 'tick_counter'):
                self.tick_counter = 0
            
            self.tick_counter += 1
            
            # Press A every 30 frames (0.5s)
            if self.tick_counter % 30 == 0:
                return WindowEvent.PRESS_BUTTON_A
            elif self.tick_counter % 30 == 1:
                return WindowEvent.RELEASE_BUTTON_A
            
            # Assume it takes about 60 seconds (3600 frames) to get through intro
            if self.tick_counter > 3600:
                 self.current_step += 1
                 self.tick_counter = 0
                 
            return None

        if action_desc == "Set player name and rival name":
            # Select "NEW NAME" (Top option) -> Type Name -> Start
            # Then "NEW NAME" (Top option) -> Type Rival Name -> Start
            
            # Default names
            p_name = self.player_name
            r_name = "GARY"
            
            # Sequence:
            # 1. Press A (Select NEW NAME for Player)
            # 2. Type Player Name
            # 3. Press START (Finish Player)
            # 4. Wait for Rival screen (long wait)
            # 5. Press A (Select NEW NAME for Rival)
            # 6. Type Rival Name
            # 7. Press START (Finish Rival)
            # 8. Wait for game to start
            
            if not hasattr(self, 'naming_sequence'):
                self.naming_sequence = []
                
                # Player Name
                self.naming_sequence.append((WindowEvent.PRESS_BUTTON_A, 30))
                self.naming_sequence.append((WindowEvent.RELEASE_BUTTON_A, 30))
                self.naming_sequence.extend(self._get_typing_sequence(p_name))
                self.naming_sequence.append((WindowEvent.PRESS_BUTTON_START, 30))
                self.naming_sequence.append((WindowEvent.RELEASE_BUTTON_START, 200)) # Wait for Rival text
                
                # Navigate through Rival text (Spam A a bit)
                for _ in range(5):
                    self.naming_sequence.append((WindowEvent.PRESS_BUTTON_A, 30))
                    self.naming_sequence.append((WindowEvent.RELEASE_BUTTON_A, 30))
                
                # Rival Name
                self.naming_sequence.append((WindowEvent.PRESS_BUTTON_A, 30))
                self.naming_sequence.append((WindowEvent.RELEASE_BUTTON_A, 30))
                self.naming_sequence.extend(self._get_typing_sequence(r_name))
                self.naming_sequence.append((WindowEvent.PRESS_BUTTON_START, 30))
                self.naming_sequence.append((WindowEvent.RELEASE_BUTTON_START, 200)) # Wait for game start
                
            # Execute sequence
            action = self._execute_timed_sequence(self.naming_sequence)
            
            # If sequence just finished (action is None and we were at last step)
            if action is None and not hasattr(self, 'naming_checkpoint_saved'):
                # Save checkpoint after naming
                if self.emulator:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    checkpoint_file = f"{self.save_dir}/checkpoint_naming_done_{self.player_name}_{timestamp}.state"
                    self.emulator.save_state(checkpoint_file)
                    self.naming_checkpoint_saved = True
                    print(f"✓ Checkpoint saved: Naming complete!")
            
            return action

        if action_desc == "Leave house and try to go to Route 1":
            # Wait for memory to stabilize after checkpoint load
            if not hasattr(self, 'stabilization_frames'):
                self.stabilization_frames = 0
            
            if self.stabilization_frames < 60:
                self.stabilization_frames += 1
                return None  # Do nothing while stabilizing
            
            # Robust navigation using Map ID
            if not self.emulator:
                return None
                
            map_id = self.emulator.memory.get_map_id()
            pos = self.emulator.memory.get_player_pos()
            
            # Debug every 60 frames
            if not hasattr(self, 'nav_debug_counter'):
                self.nav_debug_counter = 0
            self.nav_debug_counter += 1
            
            if self.nav_debug_counter % 60 == 0:
                print(f"[NAV] Map {map_id}, Pos {pos}")
            
            if map_id == 38:  # Bedroom
                # Collision-safe route around the PC/furniture to the stairs.
                return self._follow_route(
                    "start-bedroom",
                    [(5, 6), (5, 1), (7, 1)],
                )
                
            elif map_id == 37:  # Living Room
                # The door transition occurs when walking from y=7 to y=8.
                return self._follow_route(
                    "start-house-1f",
                    [(7, 6), (3, 6), (3, 8)],
                )


                
            elif map_id == 0:  # Pallet Town
                # Debug event flags every 120 frames
                if not hasattr(self, 'pallet_debug_counter'):
                    self.pallet_debug_counter = 0
                self.pallet_debug_counter += 1
                
                if self.pallet_debug_counter % 120 == 0:
                    # Check key event flags
                    from src.memory_map import FOLLOWED_OAK_INTO_LAB, OAK_ASKED_TO_CHOOSE_MON
                    followed_oak = self.emulator.memory.read_event_flag(*FOLLOWED_OAK_INTO_LAB)
                    oak_asked = self.emulator.memory.read_event_flag(*OAK_ASKED_TO_CHOOSE_MON)
                    
                    print(f"[EVENT FLAGS] Followed Oak: {followed_oak}, Oak Asked: {oak_asked}")
                    print(f"[PALLET TOWN] Pos: {pos}, trying to trigger Oak...")
                
                # At the north grass edge Oak interrupts movement and opens a
                # dialogue. Once that flag appears, A advances the real
                # cutscene until the game moves us into the laboratory.
                oak_appeared = bool(self.emulator.memory.read_byte(0xD74B) & 0x80)
                if oak_appeared or pos[1] <= 1:
                    return WindowEvent.PRESS_BUTTON_A
                return self._follow_route(
                    "start-pallet",
                    [(10, 6), (10, 1)],
                )

            elif map_id == 40:  # Oak's Lab cutscene/text
                return WindowEvent.PRESS_BUTTON_A
                
            else:
                # Unknown map (might be Oak's Lab after event)
                print(f"[UNKNOWN MAP {map_id}] Pos {pos}")
                return WindowEvent.PRESS_ARROW_UP

        if action_desc == "Choose starter: Bulbasaur, Charmander or Squirtle":
            return self._choose_starter_verified()

            # Legacy timed implementation retained below temporarily as
            # reference while later routes are migrated to RAM predicates.
            # Oak takes us to lab. We need to walk to the table.
            # Assuming we are at door of lab after Oak drags us.
            
            if not hasattr(self, 'starter_state'):
                self.starter_state = "APPROACH_TABLE"
                self.starter_target = None # 0=Bulbasaur, 1=Squirtle, 2=Charmander
                self.starter_attempts = 0
                
            # State Machine for Starter Choice
            if self.starter_state == "APPROACH_TABLE":
                # Walk UP to the table area
                if not hasattr(self, 'approach_seq'):
                    self.approach_seq = [
                        (WindowEvent.PRESS_ARROW_UP, 180), (WindowEvent.RELEASE_ARROW_UP, 5)
                    ]
                action = self._execute_timed_sequence(self.approach_seq)
                if action is None:
                    # Done approaching
                    self.starter_state = "PICK_STARTER"
                    # Reset seq index for next sequence
                    if hasattr(self, 'seq_index'): del self.seq_index
                return action
                
            elif self.starter_state == "PICK_STARTER":
                import random
                # RNG Choice
                if self.starter_choice is not None:
                    self.starter_target = self.starter_choice
                else:
                    self.starter_target = random.choice([0, 1, 2])
                # Canonical product order: Bulbasaur, Charmander, Squirtle.
                # Oak's physical table order is handled below and must not leak
                # into the profile/config index used by the rest of the app.
                starters = ["BULBASAUR", "CHARMANDER", "SQUIRTLE"]
                choice = starters[self.starter_target]
                
                print(f"[{self.player_name}] 🤔 Considering {choice}...")
                if choice == "BULBASAUR":
                    print(f"[{self.player_name}] 🍃 Bulbasaur: Strong vs Brock/Misty. Good for beginners.")
                elif choice == "SQUIRTLE":
                    print(f"[{self.player_name}] 💧 Squirtle: Strong vs Brock. Balanced choice.")
                elif choice == "CHARMANDER":
                    print(f"[{self.player_name}] 🔥 Charmander: Weak vs Brock/Misty. For experts/hard mode!")
                
                self.starter_state = "NAVIGATE_TO_BALL"
                return None
                
            elif self.starter_state == "NAVIGATE_TO_BALL":
                # We are roughly at the table center.
                # Bulbasaur (Left), Squirtle (Middle), Charmander (Right)
                # Adjust position based on target
                
                if not hasattr(self, 'nav_ball_seq'):
                    seq = []
                    # Reset position (move right then left to align? Hard to know exact pos)
                    # Let's assume we are centered below Squirtle after APPROACH_TABLE
                    
                    if self.starter_target == 0: # Bulbasaur (Left)
                        seq.append((WindowEvent.PRESS_ARROW_LEFT, 20))
                        seq.append((WindowEvent.RELEASE_ARROW_LEFT, 5))
                    elif self.starter_target == 1: # Charmander (Right)
                        seq.append((WindowEvent.PRESS_ARROW_RIGHT, 20))
                        seq.append((WindowEvent.RELEASE_ARROW_RIGHT, 5))
                    # Squirtle (2) is middle, no move needed if aligned
                    
                    # Face UP
                    seq.append((WindowEvent.PRESS_ARROW_UP, 5))
                    seq.append((WindowEvent.RELEASE_ARROW_UP, 5))
                    
                    self.nav_ball_seq = seq
                    
                action = self._execute_timed_sequence(self.nav_ball_seq)
                if action is None:
                    self.starter_state = "INTERACT"
                    if hasattr(self, 'seq_index'): del self.seq_index
                    if hasattr(self, 'nav_ball_seq'): del self.nav_ball_seq
                return action
                
            elif self.starter_state == "INTERACT":
                # Press A to open menu
                if not hasattr(self, 'interact_seq'):
                    self.interact_seq = [
                        (WindowEvent.PRESS_BUTTON_A, 10), (WindowEvent.RELEASE_BUTTON_A, 60) # Wait for text
                    ]
                action = self._execute_timed_sequence(self.interact_seq)
                if action is None:
                    self.starter_state = "DECIDE"
                    if hasattr(self, 'seq_index'): del self.seq_index
                    if hasattr(self, 'interact_seq'): del self.interact_seq
                return action
                
            elif self.starter_state == "DECIDE":
                # A configured trainer preference is a decision, not a random
                # retry loop. Future personality logic may deliberately compare
                # starters before this state, but confirmation stays reliable.
                print(f"[{self.player_name}] Confirming configured starter choice. ✅")
                self.starter_state = "CONFIRM"
                return None
                
            elif self.starter_state == "CONFIRM":
                party_count = self.emulator.memory.get_party_count()
                first_species = self.emulator.memory.read_byte(0xD16B)
                first_level = self.emulator.memory.read_byte(0xD18C)
                starter_materialized = (
                    party_count > 0
                    and first_species not in (0, 0xFF)
                    and first_level > 0
                )
                if starter_materialized:
                    if self.emulator and not hasattr(self, 'starter_checkpoint_saved'):
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        checkpoint_file = f"{self.save_dir}/checkpoint_starter_chosen_{self.player_name}_{timestamp}.state"
                        self.emulator.save_state(checkpoint_file)
                        self.starter_checkpoint_saved = True
                        print(f"✓ Checkpoint saved: Starter chosen!")
                    self.current_step += 1
                    return None

                # Confirm the selected ball once. B then advances received
                # text and answers the nickname prompt with No. The script
                # advances only after the complete party struct exists in RAM.
                if not hasattr(self, "starter_confirmation_sent"):
                    self.starter_confirmation_sent = True
                    return WindowEvent.PRESS_BUTTON_A
                return WindowEvent.PRESS_BUTTON_B
                
            elif self.starter_state == "CANCEL":
                if not hasattr(self, 'cancel_seq'):
                    self.cancel_seq = [
                        (WindowEvent.PRESS_BUTTON_B, 10), (WindowEvent.RELEASE_BUTTON_B, 30)
                    ]
                action = self._execute_timed_sequence(self.cancel_seq)
                if action is None:
                    # Go back to picking
                    self.starter_state = "PICK_STARTER"
                    if hasattr(self, 'seq_index'): del self.seq_index
                    if hasattr(self, 'cancel_seq'): del self.cancel_seq
                    
                    # Move back to center to reset position for next pick
                    # This is tricky without knowing where we are.
                    # Best guess: Inverse of previous move
                    if self.starter_target == 0: # Was Left
                        self.reset_move = [(WindowEvent.PRESS_ARROW_RIGHT, 20), (WindowEvent.RELEASE_ARROW_RIGHT, 5)]
                    elif self.starter_target == 2: # Was Right
                        self.reset_move = [(WindowEvent.PRESS_ARROW_LEFT, 20), (WindowEvent.RELEASE_ARROW_LEFT, 5)]
                    else:
                        self.reset_move = []
                        
                    self.starter_state = "RESET_POS"
                return action
                
            elif self.starter_state == "RESET_POS":
                if not hasattr(self, 'reset_seq'):
                    self.reset_seq = getattr(self, 'reset_move', [])
                
                action = self._execute_timed_sequence(self.reset_seq)
                if action is None:
                    self.starter_state = "PICK_STARTER"
                    if hasattr(self, 'seq_index'): del self.seq_index
                    if hasattr(self, 'reset_seq'): del self.reset_seq
                return action
            
            return None
            
        if action_desc == "Accept or reject optional rival fight":
            return self._complete_oak_rival_event()

            # Legacy timed implementation retained temporarily as reference.
            # Rival challenges us when we try to leave.
            # We need to walk down to trigger it.
            
            # After battle, we save
            if hasattr(self, 'battle_finished') and self.battle_finished:
                 if self.emulator:
                     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                     filename = f"{self.save_dir}/rival_defeated_{self.player_name}_{timestamp}.state"
                     self.emulator.save_state(filename)
                 self.current_step += 1
                 self.tick_counter = 0
                 return None
            
            # If we haven't triggered battle yet, walk down then spam A
            if not hasattr(self, 'rival_trigger_sequence'):
                self.rival_trigger_sequence = [
                    (WindowEvent.PRESS_ARROW_DOWN, 200), (WindowEvent.RELEASE_ARROW_DOWN, 5)
                ]
                # Then spam A forever (handled by returning PRESS_BUTTON_A below)
            
            # We use a separate sequence for walking down
            if not hasattr(self, 'rival_walk_done'):
                action = self._execute_timed_sequence(self.rival_trigger_sequence)
                if action is None:
                    self.rival_walk_done = True
                    # Reset seq_index for future sequences? 
                    # _execute_timed_sequence resets it when done, but we are reusing the method.
                    # Actually, _execute_timed_sequence increments current_step when done!
                    # We DON'T want to increment current_step yet.
                    # We want to stay on this step until battle finishes.
                    # So we should NOT use _execute_timed_sequence for this sub-task if it increments step.
                    # Or we decrement it back.
                    self.current_step -= 1 
                return action

            return WindowEvent.PRESS_BUTTON_A

            return WindowEvent.PRESS_BUTTON_A
            
        # Fallback to LLM for unknown steps
        if self.llm_agent:
            # Rate limit LLM calls (e.g., once every 60 frames)
            if not hasattr(self, 'llm_cooldown'):
                self.llm_cooldown = 0
                
            if self.llm_cooldown > 0:
                self.llm_cooldown -= 1
                # Continue holding previous action if it was a move
                if hasattr(self, 'last_llm_action') and self.last_llm_action:
                     # Only hold moves, not A/B/Start to avoid spamming interactions
                     if self.last_llm_action in [WindowEvent.PRESS_ARROW_UP, WindowEvent.PRESS_ARROW_DOWN, WindowEvent.PRESS_ARROW_LEFT, WindowEvent.PRESS_ARROW_RIGHT]:
                         return self.last_llm_action
                return None
                
            # Prepare state for LLM
            state = {
                "map_id": self.emulator.memory.get_map_id() if self.emulator else "Unknown",
                "pos": self.emulator.memory.get_player_pos() if self.emulator else "Unknown",
                "party_count": self.emulator.memory.get_party_count() if self.emulator else 0
            }
            
            # If action_desc is a list (from walkthrough), take the first item or join them
            if isinstance(action_desc, list):
                action_desc = " ".join(action_desc)
            
            action = self.llm_agent.get_navigation_action(str(action_desc), state)
            
            if action:
                self.last_llm_action = action
                self.llm_cooldown = 60 # Wait 1 second before asking again
                return action
            else:
                self.llm_cooldown = 60 # Wait even if failed
                
        return None

    def _execute_timed_sequence(self, sequence):
        """
        Executes a list of (Action, Duration) tuples.
        """
        if not hasattr(self, 'seq_index'):
            self.seq_index = 0
            self.seq_timer = 0
            
        if self.seq_index >= len(sequence):
            self.current_step += 1
            self.seq_index = 0
            self.seq_timer = 0
            return None
            
        action, duration = sequence[self.seq_index]
        
        self.seq_timer += 1
        if self.seq_timer >= duration:
            self.seq_index += 1
            self.seq_timer = 0
            return None
            
        # Update move flag
        if action in [WindowEvent.PRESS_ARROW_UP, WindowEvent.PRESS_ARROW_DOWN, WindowEvent.PRESS_ARROW_LEFT, WindowEvent.PRESS_ARROW_RIGHT]:
            self.last_action_was_move = True
            
        return action

    def _detect_checkpoint_step(self):
        """
        Auto-detect which step we should be on based on game state.
        Useful when loading from checkpoint.
        """
        if not self.emulator:
            return
            
        map_id = self.emulator.memory.get_map_id()
        pos = self.emulator.memory.get_player_pos()
        party_count = self.emulator.memory.get_party_count()
        
        print(f"[CHECKPOINT DETECT] Map: {map_id}, Pos: {pos}, Party: {party_count}")
        
        # Logic to detect step:
        # - If in bedroom (Map 38), we completed naming → step 3 (Leave house)
        # - If in Pallet Town (Map 0) with no party, still leaving house
        # - If in Oak's Lab and no party → step 4 (Choose starter)
        # - If party_count > 0 → step 5 (Rival fight)
        
        if map_id == 38:  # Bedroom after naming
            print("[CHECKPOINT] Detected: In bedroom after naming. Skipping to 'Leave house'")
            # Ensure we are in 'start' task
            if "game_flow" in self.walkthrough and "start" in self.walkthrough["game_flow"]:
                self.steps = self.walkthrough["game_flow"]["start"]["actions"]
                self.current_task_name = "start"
            self.current_step = 3  # "Leave house and try to go to Route 1"
            
        elif map_id == 37:  # Living room
            print("[CHECKPOINT] Detected: In living room. Continuing 'Leave house'")
            if "game_flow" in self.walkthrough and "start" in self.walkthrough["game_flow"]:
                self.steps = self.walkthrough["game_flow"]["start"]["actions"]
                self.current_task_name = "start"
            self.current_step = 3
            
        elif map_id == 0 and party_count == 0:  # Pallet Town, no Pokemon
            print("[CHECKPOINT] Detected: Outside, no Pokemon. Continuing 'Leave house'")
            if "game_flow" in self.walkthrough and "start" in self.walkthrough["game_flow"]:
                self.steps = self.walkthrough["game_flow"]["start"]["actions"]
                self.current_task_name = "start"
            self.current_step = 3
            
        elif party_count > 0:  # Have Pokemon
            print("[CHECKPOINT] Detected: Have Pokemon. Starting 'Rival fight'")
            # This corresponds to 'oak_event' task usually
            if "game_flow" in self.walkthrough and "oak_event" in self.walkthrough["game_flow"]:
                self.steps = self.walkthrough["game_flow"]["oak_event"]["actions"]
                self.current_task_name = "oak_event"
                self.current_step = 1 # "Accept or reject optional rival fight" (Index 1 in oak_event)
            else:
                 # Fallback if oak_event not found
                 self.current_step = 5  # "Accept or reject optional rival fight" (if using flattened list, but we are not)
        # else: keep current_step as is (probably fine)

    def _navigate_to(self, target_x, target_y):
        """
        Uses Navigation class to move to target.
        Holds buttons long enough to actually move character.
        """
        if not self.navigation:
            return None
        
        # Initialize navigation state
        if not hasattr(self, 'nav_timer'):
            self.nav_timer = 999  # Force immediate recalc
            self.nav_action = None
            
        # If we don't have a direction yet or timer expired, get new direction
        if self.nav_timer >= 1:  # Check every step. The env handles the actual button press duration.
            self.nav_action = self.navigation.get_path_to(target_x, target_y)
            self.nav_timer = 0
            
            if self.nav_action is None:
                # Reached target
                # print(f"[NAV] Reached target ({target_x}, {target_y})!")
                return None
            
            # print(f"[NAV] New action: {self.nav_action}")
        
        # Hold the button
        self.nav_timer += 1
        self.last_action_was_move = True
        return self.nav_action

    def _choose_starter_verified(self):
        """Choose the configured starter and wait for a complete party struct."""
        party_count = int(self.emulator.memory.get_party_count())
        first_species = int(self.emulator.memory.read_byte(0xD16B))
        first_level = int(self.emulator.memory.read_byte(0xD18C))
        if party_count > 0 and first_species not in (0, 0xFF) and first_level > 0:
            if not hasattr(self, "starter_checkpoint_saved"):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                checkpoint_file = f"{self.save_dir}/checkpoint_starter_chosen_{self.player_name}_{timestamp}.state"
                self.emulator.save_state(checkpoint_file)
                self.starter_checkpoint_saved = True
                print("✓ Checkpoint saved: Starter chosen!")
            self.current_step += 1
            return None

        # During the nickname prompt party_count is already one, but the party
        # struct is still zero-filled. B declines the nickname and lets the
        # game finalize the real starter data.
        if party_count > 0:
            return WindowEvent.PRESS_BUTTON_B

        # Verified Blue table order at y=3, approached from y=4:
        # x=6 Charmander, x=7 Squirtle, x=8 Bulbasaur.
        target_x = {0: 8, 1: 6, 2: 7}[int(self.starter_choice or 0)]
        current_x, current_y = self.emulator.memory.get_player_pos()
        if current_y < 4:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_DOWN
        if current_y > 4:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_UP
        if current_x < target_x:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_RIGHT
        if current_x > target_x:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_LEFT
        if not hasattr(self, "starter_faced_ball"):
            self.starter_faced_ball = True
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_UP

        # Advances species description, confirmation and received text. The
        # party-count branch above switches to B exactly at nickname handling.
        return WindowEvent.PRESS_BUTTON_A

    def _complete_oak_rival_event(self):
        """Clear post-starter text, trigger the rival and verify its event flag."""
        battled_rival = bool(self.emulator.memory.read_byte(0xD74B) & (1 << 3))
        if battled_rival or (hasattr(self, "battle_finished") and self.battle_finished):
            self.battle_finished = False
            self.current_step += 1
            return None

        # (6,4) is occupied once the rival has taken his starter, so the row in
        # front of the table is not a through path. Drop to y=5 first; the exit
        # corridor is reached from there.
        return self._follow_route(
            "oak-rival-trigger",
            [(7, 5), (5, 5), (5, 10), (5, 12)],
        )

    def _run_parcel_event(self):
        """Fetch and deliver Oak's Parcel using the verified speedrun route."""
        map_id = int(self.emulator.memory.get_map_id())
        position = self.emulator.memory.get_player_pos()
        event_byte = int(self.emulator.memory.read_byte(0xD74E))
        has_parcel = bool(event_byte & (1 << 1))
        got_pokedex = bool(self.emulator.memory.read_byte(0xD74B) & (1 << 5))

        if got_pokedex:
            return None

        if map_id == 40:
            if not has_parcel:
                return self._follow_route("parcel-leave-lab", [(5, 12)])

            # Approach Oak from above exactly as the reference route does.
            if position != (5, 1):
                return self._follow_route(
                    "parcel-deliver-oak",
                    [(5, 3), (4, 3), (4, 1), (5, 1)],
                )
            if not getattr(self, "parcel_faced_oak", False):
                self.parcel_faced_oak = True
                self.last_action_was_move = True
                return WindowEvent.PRESS_ARROW_DOWN
            return WindowEvent.PRESS_BUTTON_A

        if map_id == 42 and not has_parcel:
            # The parcel clerk is immediately left of the entrance tile. The
            # flag at D74E is the only completion signal; keep confirming the
            # real dialogue until the cartridge records the parcel.
            if position != (2, 5):
                return self._follow_route(
                    "parcel-get-mart", [(3, 7), (3, 5), (2, 5)]
                )
            if self.emulator.memory.read_byte(0xD52A) != 2:
                self.last_action_was_move = True
                return WindowEvent.PRESS_ARROW_LEFT
            return WindowEvent.PRESS_BUTTON_A

        if not has_parcel:
            routes = {
                # Antes do primeiro Centro Pokémon, o whiteout devolve o bot
                # para a casa da mãe. Nenhum executor conhecia esses dois
                # mapas, e três treinadores ficaram parados na sala apertando A.
                38: [(7, 1), (7, 7), (2, 7), (2, 8)],
                37: [(2, 7), (2, 8)],
                0: [(9, 12), (9, 2), (10, 2), (10, -1)],
                12: [
                    (10, 30), (8, 30), (8, 24), (12, 24), (12, 20),
                    (9, 20), (9, 14), (14, 14), (14, 2), (10, 2), (10, -1),
                ],
                1: [(20, 28), (19, 28), (19, 20), (29, 20), (29, 19)],
                42: [(3, 5), (3, 8)],
            }
            route = routes.get(map_id)
            if route:
                return self._follow_route(f"parcel-outbound-{map_id}", route)
        else:
            routes = {
                38: [(7, 1), (7, 7), (2, 7), (2, 8)],
                37: [(2, 7), (2, 8)],
                42: [(3, 5), (3, 8)],
                # The intermediate waypoints at (26,21)/(26,30) create a
                # false two-tile loop when resumed at the Viridian barrier.
                # One real south-exit anchor lets collision-aware steering
                # choose the currently open contour — but a single anchor is
                # also a route with no next step: standing exactly on (20,35),
                # a trainer had nothing left to want and sidestepped forever
                # with Oak's parcel in the bag. The tile past the border is
                # what turns "arrived" into "leave".
                1: [(20, 35), (20, 36)],
                12: [
                    (10, 3), (8, 3), (8, 18), (9, 18), (9, 21),
                    (12, 21), (12, 24), (10, 24), (10, 36),
                ],
                0: [(10, 7), (9, 7), (9, 12), (12, 12), (12, 11)],
            }
            route = routes.get(map_id)
            if route:
                return self._follow_route(f"parcel-return-{map_id}", route)

        # A transition or story textbox can temporarily expose a map before its
        # coordinates settle, and a whiteout can drop the run into a map this
        # quest never planned for. Walking out beats pressing A forever.
        return self._leave_unknown_map()

    # One ball is enough to satisfy the story predicate but not enough to build
    # a team: the first failed throw leaves the bot unable to catch anything for
    # the rest of the route. The quantity selector debits money without adding
    # stock on this cartridge, so the reliable path is repeating the validated
    # single purchase and re-reading the bag between each one.
    POKEBALL_TARGET = int(os.getenv("POKEAI_POKEBALL_TARGET", "8"))

    def _run_buy_pokeballs(self):
        """Return to Viridian and stock Poké Balls, one verified buy at a time.

        The story predicate remains the source of truth: this controller only
        stops once item id 4 is present in the real Gen I bag.  Menu addresses
        and cursor handling mirror the reference PokeBot shop transaction.
        """
        map_id = int(self.emulator.memory.get_map_id())

        if self._bag_item_count(4) >= self.POKEBALL_TARGET or (
            self._bag_item_count(4) > 0 and not self._can_afford_another_ball()
        ):
            # Close any remaining shop textbox before handing control to the
            # next quest. The QuestGraph has already verified the purchase.
            if map_id == 42 and self._menu_is_open():
                return WindowEvent.PRESS_BUTTON_B
            return None

        routes = {
            38: [(7, 1), (7, 7), (2, 7), (2, 8)],
            37: [(2, 7), (2, 8)],
            # After delivering the parcel the player is above Oak at (5, 1).
            # Walk around him; moving straight down only reopens his dialogue.
            40: [(4, 1), (4, 3), (5, 3), (5, 12)],
            0: [(9, 12), (9, 2), (10, 2), (10, -1)],
            12: [
                (10, 30), (8, 30), (8, 24), (12, 24), (12, 20),
                (9, 20), (9, 14), (14, 14), (14, 2), (10, 2), (10, -1),
            ],
            1: [(20, 28), (19, 28), (19, 20), (29, 20), (29, 19)],
        }
        if map_id in routes:
            return self._follow_route(f"buy-balls-{map_id}", routes[map_id])

        if map_id not in POKE_MART_MAP_IDS:
            # The hand-measured routes above only know the way back to
            # Viridian's Mart. Before giving up, ask this map whether it has a
            # Mart door of its own — a trainer that spends its last ball north
            # of Route 2 has no way home and never buys another one.
            nearest = self._run_nearest_mart("buy-balls-nearest")
            if nearest is not None:
                return nearest
            # A whiteout before the first Pokémon Center sends the run back to
            # its mother's house, a map this quest never planned for. Three
            # trainers stood in that living room pressing A while the fourth
            # walked to Pewter.
            return self._leave_unknown_map()

        return self._run_shop_counter()

    def _can_afford_another_ball(self):
        """Money is BCD across 0xD347..0xD349; a Poké Ball costs 200."""
        try:
            digits = 0
            for offset in range(3):
                byte = int(self.emulator.memory.read_byte(0xD347 + offset))
                digits = digits * 100 + (byte >> 4) * 10 + (byte & 0x0F)
            return digits >= 200
        except Exception:
            return False

    def _buy_first_shop_item(self):
        """Navigate Blue's shop menus and buy one Poké Ball."""
        if not self._menu_is_open():
            return WindowEvent.PRESS_BUTTON_A

        shop_menu = int(self.emulator.memory.read_byte(0xCC52))
        transaction_menu = int(self.emulator.memory.read_byte(0xCF8B))
        menu_row = int(self.emulator.memory.read_byte(0xCC26))
        menu_column = int(self.emulator.memory.read_byte(0xCC25))

        # BUY/SELL menu. BUY is row zero.
        if shop_menu == 32:
            return (
                WindowEvent.PRESS_ARROW_UP
                if menu_row > 0
                else WindowEvent.PRESS_BUTTON_A
            )

        # Yes/no confirmation column used by the shop dialogue.
        if menu_column == 15:
            return WindowEvent.PRESS_BUTTON_A

        # Poké Ball is item zero in Viridian. While its transaction list is
        # active, shop_menu 161 denotes the quantity selector. Buy one here:
        # the controller accepts stock only after the bag itself confirms it.
        # Replenishment is a separate repeatable objective later in the route.
        if transaction_menu == 123:
            selected_item = menu_row + int(self.emulator.memory.read_byte(0xCC36))
            if selected_item > 0:
                return WindowEvent.PRESS_ARROW_UP
            if shop_menu == 161:
                amount = int(self.emulator.memory.read_byte(0xCF96))
                if amount > 1:
                    return WindowEvent.PRESS_ARROW_DOWN
                if amount < 1:
                    return WindowEvent.PRESS_ARROW_UP
            return WindowEvent.PRESS_BUTTON_A

        # Advance clerk text or back out of an unrelated menu state. Repeated
        # calls re-read RAM, so this cannot declare a purchase by timing alone.
        return WindowEvent.PRESS_BUTTON_B

    def _run_route_2_nav(self):
        """Leave Viridian through the north gate and enter the forest.

        A whiteout before the player has registered a Pokémon Center returns
        the save to Pallet.  The objective is sticky, so this route must also
        know how to rebuild the complete Pallet -> Viridian leg.
        """
        map_id = int(self.emulator.memory.get_map_id())
        if map_id == 51:
            return None

        if map_id == 42:
            if self._menu_is_open():
                return WindowEvent.PRESS_BUTTON_B
            return self._follow_route(
                "route2-leave-mart", [(2, 5), (3, 5), (3, 8)]
            )

        routes = {
            0: [(9, 6), (9, 2), (10, 2), (10, -1)],
            12: [
                (10, 35), (10, 30), (8, 30), (8, 24), (12, 24),
                (12, 20), (9, 20), (9, 14), (14, 14), (14, 2),
                (10, 2), (10, -1),
            ],
            13: [
                (7, 71), (7, 57), (4, 57), (4, 52), (10, 52),
                (10, 44), (3, 44), (3, 43),
            ],
            50: [(4, 7), (4, 1), (5, 1), (5, 0)],
        }
        if map_id == 1:
            _, y = self.emulator.memory.get_player_pos()
            # A route resumed at (17,3) used to select (17,4) as its nearest
            # point and walk back south forever. From the upper half of the
            # city, the only useful objective is the north exit itself. Keep a
            # separate route id so a stale index from the southern leg cannot
            # be reused after a whiteout or process restart.
            routes[1] = (
                [
                    (20, 35), (20, 28), (19, 28), (19, 20),
                    (16, 20), (16, 16), (18, 16), (18, 6),
                    (17, 4), (17, 0), (17, -1),
                ]
                if y > 25
                else [
                    (17, 4), VIRIDIAN_NORTH_EXIT, (17, -1),
                ]
            )
            route_id_suffix = "-south" if y > 25 else "-north"
        else:
            route_id_suffix = ""
        if map_id == VIRIDIAN_CITY_MAP_ID:
            old_man_action = self._viridian_old_man_action()
            if old_man_action is not None:
                return old_man_action
        route = routes.get(map_id)
        if route:
            return self._follow_route(f"route2-{map_id}{route_id_suffix}", route)
        return self._leave_unknown_map()

    def _viridian_old_man_action(self):
        """Talk to the north-exit NPC when the cartridge says he is in front.

        A failed movement is not enough evidence to call a sprite the tutorial
        NPC. The route only enables this small interaction state machine on the
        measured approach tile and only when live collision identifies a
        sprite. Dialog progress is observed through the menu flag; completion
        is not declared from the number of button presses.
        """
        position = self.emulator.memory.get_player_pos()
        if tuple(position) != VIRIDIAN_OLD_MAN_APPROACH:
            return None

        blocked = self._tile_truth()
        active = getattr(self, "viridian_old_man_dialog_active", False)
        if active:
            direction = getattr(self, "viridian_old_man_direction", None)
            if (
                not getattr(self, "viridian_old_man_dialog_seen", False)
                and blocked.get(direction) != "sprite"
            ):
                # The NPC can walk away between the facing press and the next
                # controller tick. Do not press A into empty ground or keep a
                # stale dialog latch alive.
                self.viridian_old_man_dialog_active = False
                return None
            self.viridian_old_man_dialog_steps = (
                getattr(self, "viridian_old_man_dialog_steps", 0) + 1
            )
            if self._menu_is_open():
                self.viridian_old_man_dialog_seen = True
                if self.viridian_old_man_dialog_steps <= VIRIDIAN_OLD_MAN_DIALOG_LIMIT:
                    return WindowEvent.PRESS_BUTTON_A
                # A stuck text flag is not a route wall. B is the safe input
                # that advances or closes Gen I text without choosing a move.
                self.viridian_old_man_dialog_active = False
                return WindowEvent.PRESS_BUTTON_B
            if not getattr(self, "viridian_old_man_dialog_seen", False):
                return WindowEvent.PRESS_BUTTON_A

            if blocked.get(direction) == "sprite":
                # CFC4 briefly drops while a page is being rendered. Keep
                # confirming until the sprite is no longer the live blocker.
                if self.viridian_old_man_dialog_steps <= VIRIDIAN_OLD_MAN_DIALOG_LIMIT:
                    return WindowEvent.PRESS_BUTTON_A
                self.viridian_old_man_dialog_active = False
                return None

            # The dialog ended and the obstacle moved or stopped blocking the
            # approach. The next route call may now head for the exit.
            self.viridian_old_man_dialog_active = False
            self.viridian_old_man_interaction_confirmed = True
            return None

        direction = next(
            (
                candidate
                for candidate in ("U", "D")
                if blocked.get(candidate) == "sprite"
            ),
            None,
        )
        if direction is None:
            return None

        self.viridian_old_man_dialog_active = True
        self.viridian_old_man_dialog_seen = False
        self.viridian_old_man_dialog_steps = 0
        self.viridian_old_man_direction = direction
        self.route_last_issue = "old_man_dialog"
        self.last_action_was_move = True
        return ROUTE_EVENTS[direction]

    def _run_viridian_forest_nav(self):
        """Cross Viridian Forest and reach Pewter using collision-safe paths."""
        map_id = int(self.emulator.memory.get_map_id())
        if map_id in (2, 54):
            return None

        # Aqui havia a viagem de volta ao Centro por HP baixo, com um ramo
        # medido à mão para Viridian e um "meia travessia atrás, meia à
        # frente" para decidir qual Centro. Saiu inteira: sem cura automática,
        # HP baixo não interrompe mais a travessia. Estar dentro de um Centro
        # continua valendo checkpoint, e isso é tratado antes de todo executor,
        # na regra no topo de `step`.

        if map_id in (0, 12, 1, 50) or (
            map_id == 13 and self.emulator.memory.get_player_pos()[1] > 20
        ):
            return self._run_route_2_nav()

        # Level is the whole difference between crossing the Forest and dying
        # in it. The wild Caterpie are harmless; the bug catchers on the way
        # north are not, and both trainers walked into the same one ten steps
        # in and lost the whole party — then walked back from Pallet to do it
        # again. Grinding first is cheaper than that trip, every time.
        if map_id == 51 and self._needs_forest_training():
            step = self._train_in_forest_entrance()
            if step is not None:
                return step

        routes = {
            51: [
                (17, 47), (17, 43), (26, 43), (26, 34), (25, 34),
                (25, 32), (27, 32), (27, 20), (25, 20), (25, 12),
                (25, 9), (17, 9), (17, 16), (13, 16), (13, 3),
                (7, 3), (7, 22), (1, 22), (1, 19), (1, 18),
                (1, 16), (1, 5), (1, -1),
            ],
            47: [(4, 7), (4, 1), (5, 1), (5, 0)],
            13: [(3, 11), (3, 8), (8, 8), (8, -1)],
        }
        route = routes.get(map_id)
        if route:
            return self._follow_route(f"forest-{map_id}", route)
        return self._leave_unknown_map()

    def _party_max_level(self):
        """Highest level in the party, read from the cartridge."""
        count = min(int(self.emulator.memory.get_party_count()), 6)
        read = self.emulator.memory.read_byte
        # Offset 33 of the party struct is the live level; offset 3 only stays
        # in sync for boxed Pokémon.
        return max(
            (int(read(0xD16B + index * 44 + 33)) for index in range(count)),
            default=0,
        )

    def _needs_forest_training(self):
        """Too weak for the bug catchers, and still allowed to do something.

        Off unless `POKEAI_FOREST_TRAINING=1`. The gate itself is sound — a
        party whose best is level 8 loses to the first bug catcher, measured
        twice — but every version of *where to grind* has been wrong on the
        cartridge, and each wrong one cost a real run:

        | where                        | result                      |
        |------------------------------|-----------------------------|
        | line at y=43                 | 1 encounter / 225 steps     |
        | crossing's southern legs     | 1 / 3765                    |
        | farthest grass in sight      | walked into the bug catcher |
        | nearest grass within 3 tiles | detoured north, same        |
        | two-tile shuffle in place    | 0 / 1200, stuck on 8 tiles  |

        What is proven and worth keeping: `wGrassTile` (`0xD535`) says which
        tile rolls encounters, and `TileCollision.grass_offsets()` finds them
        on screen. What is missing is a patch of grass known to be reachable
        and clear of trainers — and five guesses say that has to be measured
        from a save, not assumed from the route.
        """
        if os.getenv("POKEAI_FOREST_TRAINING", "0") != "1":
            return False
        if self._party_max_level() >= FOREST_MIN_LEVEL:
            self.forest_training_steps = 0
            return False
        # A budget, because a gate with no way out is worse than a death. If
        # the grass will not deliver the levels — no encounters here, PP gone,
        # anything — the crossing is attempted anyway rather than the trainer
        # standing in a patch of grass forever.
        return getattr(self, "forest_training_steps", 0) < FOREST_TRAINING_STEPS

    def _train_in_forest_entrance(self):
        """Step into the grass beside the trainer, or hand the step back.

        Four attempts at this went wrong the same way, and every one of them
        was me deciding where the grass is instead of asking:

        1. a nine-tile line at y=43 — one encounter in three thousand steps;
        2. the crossing's own southern legs — one in three thousand seven
           hundred. Both are the dirt path, which is why the route follows
           them;
        3. `wGrassTile` read properly at last, but aiming at the **farthest**
           grass in sight, which from (31,24) is north — and north is where the
           bug catcher stands. The loop walked the party into the fight the
           levels were being collected to survive;
        4. nearest grass within three tiles, falling back to a search route
           when none was in reach. The way west is behind trees, so the search
           detoured north, into the same trainer.

        So this plans nothing at all. Grass **adjacent** to where the trainer
        already stands is a step; anything else is `None`, and the crossing
        route gets the step back. An encounter is rolled per step taken in
        grass, so a one-tile shuffle earns exactly what a hike earns, and it
        cannot walk into a trainer, a door, or a tree — because it never walks
        anywhere. Whatever grass the crossing passes through is grass this
        trains in.

        The cost is honest: this no longer guarantees level `FOREST_MIN_LEVEL`
        before the bug catchers, it only takes every free encounter on the way.
        Guaranteeing it needs to know where a safe patch is, and four guesses
        say that has to be measured rather than assumed.
        """
        position = tuple(self.emulator.memory.get_player_pos())
        reader = self._tile_reader()
        if reader is None:
            return None
        # A door is a destination, never a shortcut. `_follow_route` only
        # blocks warp steps while it is not aiming at its last waypoint, and a
        # training target is always the last waypoint — so on the Forest
        # entrance the step back through the door was wide open, and BARON
        # crossed gate to Forest and back every single frame.
        warps = reader.warp_tiles()
        beside = {
            (position[0] + dx, position[1] + dy)
            for dx, dy in reader.grass_offsets()
            if abs(dx) + abs(dy) == 1
        } - warps
        if not beside:
            return None
        self.forest_training_steps = getattr(self, "forest_training_steps", 0) + 1

        # Two tiles, back and forth, and nothing else. "Step onto the nearest
        # grass" sounds local and is not: picking the same corner of the patch
        # every time is a fixed heading, and the trainer walked fourteen tiles
        # up the grass column doing exactly that — arriving, as every other
        # version did, at the bug catcher. A pair cannot drift.
        # Only one of the two has to be grass — the other is simply where it
        # came from. Requiring both broke the pair on arrival every time, and a
        # pair rebuilt every step is the drift again under another name.
        pair = getattr(self, "forest_training_pair", None)
        if not pair or position not in pair:
            pair = (position, min(beside))
            self.forest_training_pair = pair
        home, away = pair
        return self._follow_route(
            "forest-training", [away if position == home else home]
        )

    def _run_pewter_city_nav(self):
        """Walk to Pewter's Gym, rebuilding the route after a whiteout."""
        map_id = int(self.emulator.memory.get_map_id())
        if map_id == 54:
            return None
        # O desvio para o Centro de Pewter saiu com a cura automática. Dentro
        # do 58 o registro do Centro é feito antes do executor, na regra do
        # topo de `step`.
        if map_id == 2:
            return self._follow_route(
                "pewter-to-gym",
                [
                    (18, 35), (18, 22), (19, 22), (19, 13),
                    (10, 13), (10, 18), (16, 18), (16, 17),
                ],
            )

        # Until a Pokémon Center has been registered, a poison faint or
        # whiteout returns this early journey to Pallet. Reconstruct the path
        # instead of leaving the bot pressing A in an unrelated map.
        recovery_routes = {
            0: [(9, 6), (9, 2), (10, 2), (10, -1)],
            12: [
                (10, 35), (10, 30), (8, 30), (8, 24), (12, 24),
                (12, 20), (9, 20), (9, 14), (14, 14), (14, 2),
                (10, 2), (10, -1),
            ],
            1: [
                (20, 35), (20, 28), (19, 28), (19, 20), (16, 20),
                (16, 16), (18, 16), (18, 6), (17, 4), (17, -1),
            ],
            50: [(4, 7), (4, 1), (5, 1), (5, 0)],
            51: [
                (17, 47), (17, 43), (26, 43), (26, 34), (25, 34),
                (25, 32), (27, 32), (27, 20), (25, 20), (25, 12),
                (25, 9), (17, 9), (17, 16), (13, 16), (13, 3),
                (7, 3), (7, 22), (1, 22), (1, 19), (1, 18),
                (1, 16), (1, 5), (1, -1),
            ],
            47: [(4, 7), (4, 1), (5, 1), (5, 0)],
        }
        if map_id == 13:
            _, y = self.emulator.memory.get_player_pos()
            recovery_routes[13] = (
                [
                    (7, 71), (7, 57), (4, 57), (4, 52), (10, 52),
                    (10, 44), (3, 44), (3, 43),
                ]
                if y > 20
                else [(3, 11), (3, 8), (8, 8), (8, -1)]
            )
        route = recovery_routes.get(map_id)
        if route:
            return self._follow_route(f"pewter-recovery-{map_id}", route)
        return self._leave_unknown_map()

    def _run_brock_quest(self):
        """Approach Brock; battle inputs are owned by the battle controller."""
        if int(self.emulator.memory.read_byte(0xD356)) & 0x01:
            return None
        map_id = int(self.emulator.memory.get_map_id())
        if map_id != 54:
            return self._run_pewter_city_nav()
        if map_id == 54:
            position = self.emulator.memory.get_player_pos()
            if position != (4, 2):
                return self._follow_route(
                    "brock-approach",
                    [(4, 13), (4, 8), (1, 8), (1, 4), (4, 4), (4, 2)],
                )
            if int(self.emulator.memory.read_byte(0xD52A)) != 8:
                self.last_action_was_move = True
                return WindowEvent.PRESS_ARROW_UP
            return WindowEvent.PRESS_BUTTON_A
        return WindowEvent.PRESS_BUTTON_A

    def _run_mt_moon_nav(self):
        """Cross Route 3 and Mt. Moon, then enter Cerulean City.

        The coordinates are the collision-safe Pokémon Red/Blue route from
        the local PokeBot walkthrough. Trainer and fossil interactions are
        deliberately reached as physical obstacles; `_follow_route` advances
        their dialogue when movement is blocked, while the battle controller
        owns every actual fight.
        """
        map_id = int(self.emulator.memory.get_map_id())
        if map_id in (3, 65):
            return None

        # Leave Brock's room after the badge dialogue finishes.
        if map_id == 54:
            return self._follow_route(
                "mt-moon-leave-gym",
                [(4, 2), (4, 4), (1, 4), (1, 8), (4, 8), (4, 14)],
            )

        # A loss before registering the Route 4 Center can still return the
        # run to Pallet. Rebuild the complete early route without regressing
        # the sticky quest graph.
        recovery_routes = {
            0: [(9, 6), (9, 2), (10, 2), (10, -1)],
            12: [
                (10, 35), (10, 30), (8, 30), (8, 24), (12, 24),
                (12, 20), (9, 20), (9, 14), (14, 14), (14, 2),
                (10, 2), (10, -1),
            ],
            50: [(4, 7), (4, 1), (5, 1), (5, 0)],
            51: [
                (17, 47), (17, 43), (26, 43), (26, 34), (25, 34),
                (25, 32), (27, 32), (27, 20), (25, 20), (25, 12),
                (25, 9), (17, 9), (17, 16), (13, 16), (13, 3),
                (7, 3), (7, 22), (1, 22), (1, 19), (1, 18),
                (1, 16), (1, 5), (1, -1),
            ],
            47: [(4, 7), (4, 1), (5, 1), (5, 0)],
        }
        if map_id == 1:
            _, y = self.emulator.memory.get_player_pos()
            recovery_routes[1] = (
                [
                    (20, 35), (20, 28), (19, 28), (19, 20),
                    (16, 20), (16, 16), (18, 16), (18, 6),
                    (17, 4), (17, -1),
                ]
                if y > 25
                else [
                    (29, 20), (19, 20), (16, 20), (16, 16),
                    (18, 16), (18, 6), (17, 4), (17, -1),
                ]
            )
        if map_id == 13:
            _, y = self.emulator.memory.get_player_pos()
            recovery_routes[13] = (
                [
                    (7, 71), (7, 57), (4, 57), (4, 52), (10, 52),
                    (10, 44), (3, 44), (3, 43),
                ]
                if y > 20
                else [(3, 11), (3, 8), (8, 8), (8, -1)]
            )
        route = recovery_routes.get(map_id)
        if route:
            return self._follow_route(f"mt-moon-recovery-{map_id}", route)

        if map_id == 2:
            x, y = self.emulator.memory.get_player_pos()
            if not hasattr(self, "mt_moon_pewter_origin"):
                if y >= 22:
                    self.mt_moon_pewter_origin = "south"
                    south_start = (18, y) if x == 18 and 22 <= y <= 35 else (18, 35)
                    self.mt_moon_pewter_route = [
                        south_start, (18, 22), (19, 22), (19, 13),
                        (21, 13), (21, 18), (23, 18), (40, 18),
                    ]
                elif x >= 21:
                    self.mt_moon_pewter_origin = "east"
                    self.mt_moon_pewter_route = [
                        (x, y), (21, 13), (21, 18), (23, 18), (40, 18)
                    ]
                else:
                    self.mt_moon_pewter_origin = "gym"
                    self.mt_moon_pewter_route = [
                        (16, 18), (10, 18), (10, 13), (21, 13),
                        (21, 18), (23, 18), (40, 18),
                    ]

            return self._follow_route(
                f"mt-moon-2-{self.mt_moon_pewter_origin}",
                self.mt_moon_pewter_route,
            )

        routes = {
            14: [
                (0, 10), (8, 10), (8, 8), (11, 8), (11, 6),
                (11, 4), (12, 4), (13, 4), (13, 5), (18, 5),
                (18, 6), (22, 6), (22, 5), (23, 5), (24, 5),
                (27, 5), (27, 9), (37, 8), (37, 5), (49, 5),
                (49, 10), (57, 10), (57, 8), (59, 8), (59, -1),
            ],
            59: [
                (14, 35), (14, 22), (21, 22), (21, 15), (24, 15),
                (24, 27), (25, 27), (25, 31), (25, 32), (33, 32),
                (33, 31), (34, 31), (35, 31), (35, 23), (35, 7),
                (30, 7), (28, 7), (16, 7), (16, 17), (2, 17),
                (2, 3), (5, 3), (5, 5),
            ],
            61: [
                (21, 17), (22, 17), (23, 17), (23, 14), (27, 14),
                (27, 16), (33, 16), (33, 14), (36, 14), (36, 24),
                (32, 24), (32, 31), (10, 31), (10, 18), (10, 17),
                (12, 17), (12, 9), (13, 9), (13, 7), (13, 5),
                (12, 5), (12, 4), (3, 4), (3, 7), (5, 7),
            ],
        }
        if map_id in routes:
            return self._follow_route(f"mt-moon-{map_id}", routes[map_id])

        # Map 68 is the Route 4 Center and is handled before every executor,
        # like every other one. It used to have its own copy of the nurse dance
        # here — and that copy was the whole reason Mt. Moon never produced a
        # checkpoint: it healed the party but never set
        # `last_center_healed_map_id`, which is what the checkpoint writer
        # waits for. Its `mt_moon_center_healed` flag was written and never
        # read by anything.

        if map_id == 60:
            x, y = self.emulator.memory.get_player_pos()
            route = (
                [(5, 5), (5, 17), (21, 17)]
                if x < 20 or y > 4
                else [(23, 3), (27, 3)]
            )
            return self._follow_route("mt-moon-60", route)

        if map_id == 15:
            x, _ = self.emulator.memory.get_player_pos()
            # "Já curei aqui" era mais um trinco de processo: reiniciado, ele
            # voltava ao Centro da Rota 4 com o time inteiro e ficava indo e
            # vindo entre (12,6) e (13,6). Quem responde é a party na RAM.
            # O desvio para o Centro da Rota 4 saiu junto com a cura
            # automática. Quem estiver a oeste segue direto para a caverna.
            if x < 20:
                # (11,6) é âncora de aproximação para quem chega **do oeste** —
                # do Centro ou da Rota 3. Para quem já está a leste dela, ela
                # fica atrás, e o ciclo que ela cria é fechado: sai da caverna
                # em (18,5), o índice é recalculado para o ponto "mais
                # próximo", volta a andar oeste até (11,6), leste até (18,6),
                # entra na caverna em (18,5), sai, recomeça. Medido: 400
                # travessias em 300 segundos.
                #
                # Mesmo padrão da porta do Centro de Viridian, já registrado no
                # handoff: âncora de aproximação atrás do bot é âncora gasta.
                aproximacao = [] if x >= MT_MOON_APPROACH_X else [(11, 6)]
                return self._follow_route(
                    "mt-moon-enter-cave", aproximacao + [(18, 6), (18, 5)]
                )
            return self._follow_route(
                "mt-moon-to-cerulean",
                [
                    (24, 6), (24, 8), (35, 8), (35, 10), (61, 10),
                    (61, 8), (79, 8), (79, 10), (90, 10),
                ],
            )

        return self._leave_unknown_map()

    def _center_first_action(self):
        """A Center on this map outranks whatever the executor wanted to do.

        The prize is not the HP, it is the **checkpoint**. Entering a Center is
        the only thing in this project that writes a resume point, so walking
        past one is throwing away the only defence a whiteout has: with a
        checkpoint a death costs the stretch, without one it costs the run back
        to Pallet.

        A viagem até um Centro por causa de HP foi cancelada pelo operador:
        ficar até morrer é aceitável, e a cura automática travava o
        personagem. Sobrou a metade que importa — um Centro **neste mapa**
        vira ponto de retomada, e o executor espera.

        It also closes a hole every executor shared. AARON reached Pewter,
        walked into its Center at 53% with a fainted Caterpie, and stopped:
        `_run_pewter_city_nav` only enters its Center branch when the 20% gate
        says yes, so nothing matched and it fell through to the unknown-map
        fallback.
        """
        if getattr(self, "emulator", None) is None:
            return None
        map_id = int(self.emulator.memory.get_map_id())
        if map_id in POKEMON_CENTER_MAP_IDS:
            # Standing inside one hands over unconditionally, healed or not:
            # this controller owns **both** halves, healing what is missing and
            # walking back out. Gating it on "is anything missing" left AARON
            # healed on Pewter's doormat with nothing to press — the executor
            # has no branch for a whole party in a Center either, so the step
            # fell through to the unknown-map fallback and stopped.
            #
            # Viridian keeps its own names: `viridian_center_healed` is read
            # outside this class as the story milestone for the first Center.
            prefix, healed = (
                ("viridian-center", "viridian_center_healed")
                if map_id == VIRIDIAN_CENTER_MAP_ID
                else (f"center-{map_id}", f"center_{map_id}_healed")
            )
            return self._run_pokemon_center(prefix, healed)
        # HP não desvia mais nada. O que desvia é cidade nova: se este mapa tem
        # porta de Centro e `wLastBlackoutMap` ainda não aponta para cá, o
        # apagão devolveria a corrida a Pallet. Registrar custa a caminhada até
        # a porta; não registrar custa tudo desde a última cidade.
        if (
            map_id in CENTER_DOOR_BY_OUTDOOR_MAP
            and self._blackout_map() != map_id
        ):
            return self._walk_to_door("center-door", POKEMON_CENTER_MAP_IDS)
        return None

    def _select_route_index(self, route_id, waypoints, position):
        """Qual waypoint mirar agora, sem nunca andar para trás.

        Ao trocar de rota o índice ia para o waypoint **mais próximo**, e é aí
        que nascia o vaivém: BARON e CARON entravam em Mt. Moon, andavam até o
        meio, saíam para a Rota 4 por qualquer motivo, e ao reentrar o "mais
        próximo" era um ponto perto da boca da caverna — atrás de tudo que já
        tinham andado. Dezoito travessias, nenhum progresso.

        Waypoint já passado é waypoint gasto. É a mesma regra que a âncora de
        aproximação de Mt. Moon e a da porta do Centro de Viridian já seguem,
        aplicada ao índice da rota inteira. Estar fisicamente à frente do
        lembrado ainda vale: o que não vale é retroceder.

        O avanço é por `route_id`, e morre no apagão — o cartucho devolveu o
        treinador a um Centro, então mirar o meio da caverna a partir da porta
        seria planejar por cima de terreno que esta tentativa não andou.
        """
        x, y = position
        limite = len(waypoints) - 1
        progress = getattr(self, "route_progress", None)
        if progress is None:
            progress = self.route_progress = {}

        if getattr(self, "route_id", None) != route_id:
            self.route_id = route_id
            nearest = min(
                range(len(waypoints)),
                key=lambda i: abs(x - waypoints[i][0]) + abs(y - waypoints[i][1]),
            )
            self.route_index = max(nearest, min(progress.get(route_id, 0), limite))

        index = getattr(self, "route_index", 0)
        while index < limite and (x, y) == tuple(waypoints[index]):
            index += 1
        # A mesma rota pode receber uma lista mais curta que da última vez — o
        # executor da Rota 2 troca os waypoints depois que o Centro é
        # registrado. O índice velho estourava a lista, o IndexError era
        # engolido pelo chamador e virava NOOP: um bot congelado no meio da
        # cidade sem mensagem nenhuma.
        index = min(index, limite)
        if index > progress.get(route_id, -1):
            progress[route_id] = index
        return index

    def _door_to(self, destinations):
        """Nearest door on this map leading into one of these maps, or None.

        Every route to a Center or a Mart in this project was measured by hand,
        for one city, from a handful of starting maps — `buy_pokeballs` only
        knows the way back to Viridian's Mart, so a trainer that spends its last
        Poké Ball north of Route 2 never buys another one.

        The warp table answers this. It was already being read for *where* the
        doors are; the fourth byte of each entry says where each one goes.
        """
        reader = self._tile_reader()
        if reader is None:
            return None
        x, y = self.emulator.memory.get_player_pos()
        doors = [
            tile for tile, destination in reader.warp_destinations().items()
            if destination in destinations
        ]
        if not doors:
            return None
        return min(doors, key=lambda tile: abs(tile[0] - x) + abs(tile[1] - y))

    def _walk_to_door(self, route_prefix, destinations):
        """Head for that door, or None when this map has none of them."""
        door = self._door_to(destinations)
        if door is None:
            return None
        # The route id carries the door so a different one, on a different map,
        # cannot inherit a stale waypoint index.
        return self._follow_route(f"{route_prefix}-{door[0]}-{door[1]}", [door])

    def _run_nearest_center(self, route_prefix="nearest-center"):
        """Heal at whatever Center this city has, with no route measured by hand.

        Works anywhere because both halves are general: the door comes from the
        map's own warp table, and every Pokémon Center in Gen I is the same
        building inside — nurse at (3,3), doormat at (3,7).
        """
        map_id = int(self.emulator.memory.get_map_id())
        if map_id in POKEMON_CENTER_MAP_IDS:
            return self._run_pokemon_center(route_prefix, f"{route_prefix}_healed")
        return self._walk_to_door(route_prefix, POKEMON_CENTER_MAP_IDS)

    def _run_nearest_mart(self, route_prefix="nearest-mart"):
        """Restock at whatever Mart this city has. Same two halves as above."""
        map_id = int(self.emulator.memory.get_map_id())
        if map_id in POKE_MART_MAP_IDS:
            return self._run_shop_counter()
        return self._walk_to_door(route_prefix, POKE_MART_MAP_IDS)

    def _run_shop_counter(self):
        """Reach the clerk and buy, from inside any Mart.

        Lifted out of `buy_pokeballs`, where it was written for map 42 and read
        as if the coordinates were Viridian's. They are not: a Gen I Mart is the
        same building in every city, clerk behind the top-left counter.
        """
        if tuple(self.emulator.memory.get_player_pos()) != SHOP_COUNTER_TILE:
            return self._follow_route(
                "shop-counter", [(3, 7), (3, 5), SHOP_COUNTER_TILE]
            )
        if self.emulator.memory.read_byte(0xD52A) != 2:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_LEFT
        return self._buy_first_shop_item()

    def _blackout_map(self):
        """Para onde o cartucho manda o treinador depois de um apagão.

        `wLastBlackoutMap` guarda o **mapa de fora** do último Centro usado — 1
        para Viridian, 15 para a Rota 4. Enquanto ele não avança, todo apagão
        devolve o jogo a Pallet e a corrida vira roguelite.
        """
        try:
            return int(self.emulator.memory.read_byte(LAST_BLACKOUT_MAP_ADDRESS))
        except Exception:
            return None

    def _respawn_is_registered(self, center_map_id):
        """Este Centro já é o ponto de renascimento?

        Medido no cartucho em 2026-08-07: entrar **não** basta. O endereço só
        muda quando a enfermeira termina a cura — entrei no Centro de Viridian
        com o valor em 0 e ele continuou em 0; virou 1 depois de curar.
        """
        outdoor = CENTER_OUTDOOR_MAP.get(int(center_map_id))
        if outdoor is None:
            return True
        return self._blackout_map() == outdoor

    def _run_pokemon_center(self, route_prefix, healed_attribute):
        """Registrar o Centro como ponto de renascimento e sair.

        A cura por HP baixo foi cancelada pelo operador e não volta: nada aqui
        olha para HP. O que traz o treinador até este balcão é outra coisa —
        `wLastBlackoutMap` ainda não aponta para esta cidade, e só a enfermeira
        move esse endereço. A cura é efeito colateral da única interação que
        grava o checkpoint interno do jogo.

        Quem decide se já acabou é o cartucho, não um flag: enquanto o endereço
        não apontar para cá, a conversa continua. Foi assim que a versão
        anterior entrava em ciclo — "já curei" era um flag de processo que
        sumia no reinício.
        """
        position = self.emulator.memory.get_player_pos()
        map_id = int(self.emulator.memory.get_map_id())

        if not self._respawn_is_registered(map_id):
            if tuple(position) != (3, 3):
                return self._follow_route(f"{route_prefix}-nurse", [(3, 7), (3, 3)])
            if int(self.emulator.memory.read_byte(0xD52A)) != 8:
                self.last_action_was_move = True
                return WindowEvent.PRESS_ARROW_UP
            # Falar, confirmar o SIM e atravessar a animação são todos A. O fim
            # da conversa é o endereço de renascimento apontando para cá.
            return WindowEvent.PRESS_BUTTON_A

        setattr(self, healed_attribute, True)
        setattr(
            self,
            f"{healed_attribute.replace('_healed', '')}_checkpoint_confirmed",
            True,
        )
        self.last_center_visited_map_id = int(self.emulator.memory.get_map_id())
        # Leaving used to be a measured D-pad sequence, played once. When any
        # press was eaten — by the nurse's last text box, by a step that landed
        # a tile off — the sequence ran out and the controller returned None
        # forever: a trainer stood on the Center's own doormat, healthy, unable
        # to walk out. Walking to the door and pressing into it repeats until
        # the cartridge actually changes map.
        if tuple(position) not in ((3, 7), (4, 7)):
            return self._follow_route(f"{route_prefix}-exit", [(3, 7)])
        self.last_action_was_move = True
        return WindowEvent.PRESS_ARROW_DOWN

    def _party_health_fraction(self):
        """Combined party HP over combined maximum, 1.0 when whole."""
        party_count = min(int(self.emulator.memory.get_party_count()), 6)
        total_hp = 0
        total_max = 0
        for index in range(party_count):
            struct_start = 0xD16B + index * 44
            total_hp += (
                int(self.emulator.memory.read_byte(struct_start + 1)) << 8
            ) + int(self.emulator.memory.read_byte(struct_start + 2))
            total_max += (
                int(self.emulator.memory.read_byte(struct_start + 34)) << 8
            ) + int(self.emulator.memory.read_byte(struct_start + 35))
        if total_max <= 0:
            return 1.0
        return total_hp / total_max

    def _should_top_up_before(self, map_id):
        """Whether to heal now because the Center is on the way and the next
        stretch has none.

        Twenty per cent is an emergency rule, and emergencies are the wrong
        moment to walk across a city: a team at half health entered the Forest,
        died in the middle of it, whited out back to Viridian and started the
        same walk again. A Center passed on the route is nearly free, so the
        bar to stop there is much higher than the bar to turn around.
        """
        if map_id not in CENTER_ON_THE_WAY:
            return False
        return self._party_health_fraction() < TOP_UP_HP_FRACTION

    def _party_needs_healing(self):
        """True only when the team's combined HP is below one fifth.

        Per-Pokémon rules kept sending the trip back too early: at 29/30 a
        trainer walked the whole city to the Center, healed, took one scratch
        on the way out and turned around. Exhausted PP is handled by battle
        control; it is not a second reason to start a healing trip.
        """
        party_count = min(int(self.emulator.memory.get_party_count()), 6)
        if party_count <= 0:
            return False
        total_hp = 0
        total_max = 0
        for index in range(party_count):
            struct_start = 0xD16B + index * 44
            current_hp = (
                int(self.emulator.memory.read_byte(struct_start + 1)) << 8
            ) + int(self.emulator.memory.read_byte(struct_start + 2))
            max_hp = (
                int(self.emulator.memory.read_byte(struct_start + 34)) << 8
            ) + int(self.emulator.memory.read_byte(struct_start + 35))
            total_hp += current_hp
            total_max += max_hp
        return bool(total_max and total_hp < total_max * HEAL_HP_FRACTION)

    def _run_bill_quest(self):
        """Heal, clear the Cerulean rival/bridge and obtain the S.S. Ticket."""
        if self._bag_item_count(0x3F) > 0:
            return None

        map_id = int(self.emulator.memory.get_map_id())
        if map_id == 64:
            return self._run_pokemon_center(
                "cerulean-center",
                "cerulean_center_healed",
            )

        if map_id == 3:
            # A parada de cura em Cerulean saiu; o Centro só entra na rota se
            # o caminho passar por cima dele.
            return self._follow_route(
                "cerulean-to-rival",
                [
                    # The buildings occupy every direct north line near the
                    # Center. The cartridge's open street is at x=8; use it to
                    # reach y=12, then cross back to Nugget Bridge.
                    (19, 18), (8, 18), (8, 12), (20, 12),
                    (20, 8), (20, 6), (20, -1),
                ],
            )

        if map_id == 35:
            # Nugget Bridge trainers occupy alternating x=10/x=11 tiles.
            # Walking the centre line triggers every required fight and the
            # Rocket recruiter before bending east into Route 25.
            return self._follow_route(
                "route-24-bill",
                [
                    (10, 35), (10, 32), (10, 29),
                    # Two trainers remain on x=10 after their battles. The
                    # bridge's x=9 side is fenced, so bypass them on x=11.
                    (11, 29), (11, 27), (10, 27), (10, 23),
                    (11, 23), (11, 21), (10, 21),
                    (10, 20), (10, 17), (10, 14),
                    # The east turn is above the corner fence, not through it.
                    (10, 10), (11, 10), (11, 8), (15, 8), (19, 8), (20, 8),
                ],
            )

        if map_id == 36:
            # Route 25 is a hedge corridor. These first waypoints are kept
            # explicit so trainer collisions are handled as dialogue/battles;
            # the route is validated incrementally against the cartridge.
            return self._follow_route(
                "route-25-bill",
                [
                    # The upper branch leads to the optional TM19 enclosure
                    # and two one-way traps. The story-safe path zigzags below
                    # the ledges and approaches the Hiker at (13,7) from his
                    # right, making him walk out of the corridor before battle.
                    (0, 8), (9, 8), (9, 7), (11, 7),
                    (11, 9), (15, 9), (15, 7), (15, 4),
                    # Approach the Lass at (18,8) from the open east side,
                    # then continue through the corridor she vacates.
                    (17, 4), (17, 7), (20, 7), (20, 8),
                    (22, 8), (22, 6), (23, 6), (23, 5), (24, 5),
                    # The Jr. Trainer opens the long lower corridor. Approach
                    # the final Lass from below so she does not block it.
                    (24, 6), (36, 6), (36, 5), (37, 5),
                    (45, 5), (45, 3),
                ],
            )

        if map_id == 88:
            bill_flags = int(self.emulator.memory.read_byte(0xD7F2))
            said_use_separator = bool(bill_flags & (1 << 6))
            used_separator = bool(bill_flags & (1 << 3))
            met_human_bill = bool(
                int(self.emulator.memory.read_byte(0xD7F1)) & 0x01
            )

            if not said_use_separator:
                # Bill begins as the Pokémon at (6,5). Walking into the
                # occupied tile and advancing the YES prompt starts his walk
                # into the separation machine.
                return self._follow_route(
                    "bill-lab-introduction",
                    [(3, 7), (3, 6), (5, 6), (5, 5), (6, 5)],
                )

            if not used_separator:
                # The PC keyboard is the blocked background tile at (1,4).
                # Interact from below; RAM bit D7F2.3 verifies activation.
                return self._follow_route(
                    "bill-lab-separator",
                    [(6, 5), (1, 5), (1, 4)],
                )

            if not met_human_bill:
                # Bill's exit from the machine is an autonomous cutscene.
                # A advances any text while ordinary ticks advance movement.
                return WindowEvent.PRESS_BUTTON_A

            # Human Bill waits at (4,4). Talk from below to receive the ticket;
            # item 0x3f and D7F2.4 independently verify completion.
            return self._follow_route(
                "bill-lab-ticket",
                [(1, 5), (4, 5), (4, 4)],
            )

        # A whiteout can return to Cerulean Center, and a bot can wander into
        # any house on the way. An unknown map is not a cutscene to press
        # through: walk back out of it and let the route resume outside.
        return self._leave_unknown_map()

    def _run_cerulean_gym_quest(self):
        """Enter Cerulean Gym and defeat Misty after Bill is complete."""
        if int(self.emulator.memory.read_byte(0xD356)) & 0x02:
            return None
        map_id = int(self.emulator.memory.get_map_id())
        if map_id == 88:
            # Finish Bill's post-ticket text, then leave through the south door.
            return self._follow_route(
                "bill-house-exit",
                [(4, 5), (3, 5), (3, 7)],
            )
        if map_id == 36:
            # Reverse the cleared Route 25 maze. This uses the southern return
            # bends opened by trainer movement and ends at the Route 24 seam.
            return self._follow_route(
                "route-25-return",
                [
                    (45, 4), (38, 4), (38, 5), (32, 5), (32, 6),
                    (22, 6), (22, 8), (19, 8), (19, 7), (17, 7),
                    (17, 4), (15, 4), (15, 6), (14, 6), (14, 9),
                    (11, 9), (11, 7), (9, 7), (9, 8), (0, 8),
                ],
            )
        if map_id == 35:
            return self._follow_route(
                "route-24-return",
                [
                    (19, 8), (10, 8), (10, 20), (11, 20),
                    (11, 23), (10, 23), (10, 26), (11, 26),
                    (11, 29), (10, 29), (10, 35),
                ],
            )
        if map_id == 64:
            return self._run_pokemon_center(
                "cerulean-gym-center",
                "cerulean_gym_center_healed",
            )
        if map_id == 3:
            # Sem parada de cura: direto para a porta do ginásio.
            return self._follow_route(
                "cerulean-gym-door",
                [(19, 18), (19, 20), (30, 20), (30, 19)],
            )
        if map_id == 65:
            return self._follow_route(
                "misty-approach",
                [
                    (4, 12), (4, 8), (2, 8), (2, 5),
                    (7, 5), (7, 3), (5, 3), (5, 2), (4, 2),
                ],
            )
        return WindowEvent.PRESS_BUTTON_A

    def _menu_is_open(self):
        return int(self.emulator.memory.read_byte(0xCFC4)) == 1

    def _bag_item_count(self, item_id):
        item_count = min(int(self.emulator.memory.read_byte(0xD31D)), 20)
        for index in range(item_count):
            address = 0xD31E + index * 2
            if int(self.emulator.memory.read_byte(address)) == int(item_id):
                return int(self.emulator.memory.read_byte(address + 1))
        return 0

    def _follow_route(self, route_id, waypoints):
        """Walk the route the way it was actually walking before.

        There were two of these in this class, and Python kept the last one:
        the short one. Everything that ever worked on a cartridge worked with
        the short one. Deleting the "dead" duplicate was not a cleanup, it
        swapped the pilot mid-flight — measured from the same save, the long
        version covered 11 tiles in 400 steps and then sat still, where this
        one covered 26 in 77.

        So this is the short one, with two things kept because they are read
        from the cartridge rather than guessed: the published trail, and the
        two-tile pacing guard.
        """
        if not waypoints:
            return None
        if self._menu_is_open():
            presses = getattr(self, "route_menu_presses", 0) + 1
            self.route_menu_presses = presses
            # `MENU_PRESS_LIMIT` was written for this and then stopped being
            # read: the flag at 0xCFC4 can stay up with nothing on screen that
            # a button will clear, and an unbounded B/A alternation is a bot
            # that never walks again. CAARON stood at (5,1) in Oak's Lab for
            # thousands of steps this way, and left no stuck report either,
            # because this return happens before the report is written.
            #
            # So press, then walk anyway, then press again. The D-pad is
            # ignored while real text is up, which makes walking free to try;
            # what must never happen is reading the failed step as a wall, and
            # the bump memory below already refuses to while the flag is up.
            if (presses - 1) % (MENU_PRESS_LIMIT * 2) < MENU_PRESS_LIMIT:
                return self._route_text()
        else:
            self.route_menu_presses = 0

        x, y = self.emulator.memory.get_player_pos()
        map_id = int(self.emulator.memory.get_map_id())
        previous = getattr(self, "route_last_position", None)
        direction = getattr(self, "route_last_direction", None)
        if previous is not None and direction and previous[0] != map_id:
            self.route_entry_map = previous[0]
            self._warp_memory().record(previous[0], previous[1], previous[2], map_id)
            # The tile just arrived on, and how it was entered. `_leave_unknown_map`
            # has always read this and nothing has ever written it, so its first
            # and best way out of a map no executor knows — leave by the door you
            # came in through — was dead code.
            entry_tiles = getattr(self, "map_entry_tiles", None)
            if entry_tiles is None:
                entry_tiles = self.map_entry_tiles = {}
            entry_tiles[map_id] = (x, y, direction)
            # The edge between two outdoor maps is a connection, not a warp:
            # it is in no warp table, so "a door is only ever a destination"
            # never covered it. Standing on the tile you just arrived on, the
            # step back across is the one step that cannot be progress —
            # BARON crossed Viridian/Route 2 twenty-one hundred times in five
            # minutes doing exactly that.
            self.route_entry_block = (
                map_id, x, y, OPPOSITE_DIRECTIONS[direction], 0,
            )
        self.route_last_position = (map_id, x, y)

        # Bumping into something the tileset called walkable. In Mt. Moon the
        # screen stores metatiles and the cave misreads: from (21,25) the game
        # refuses DOWN, the reading calls it free, and the bot pressed into the
        # rock 1813 times. A press that produced no movement is a wall right
        # now — remembered for a handful of steps, never written down. People
        # move away, and so does whatever this was.
        bumped = getattr(self, "route_bumped", {})
        for key in [key for key, age in bumped.items() if age <= 0]:
            del bumped[key]
        for key in list(bumped):
            bumped[key] -= 1
        last_move = getattr(self, "route_last_issue", None) == "move"
        last_direction_taken = getattr(self, "route_last_direction", None)
        if (
            last_move
            and last_direction_taken
            and previous is not None
            and previous == (map_id, x, y)
            and not self._menu_is_open()
        ):
            bumped[(map_id, x, y, last_direction_taken)] = BUMP_MEMORY_STEPS
        self.route_bumped = bumped

        entry_block = getattr(self, "route_entry_block", None)
        blocked_entry = None
        if entry_block:
            entry_map, entry_x, entry_y, back, age = entry_block
            if (map_id, x, y) != (entry_map, entry_x, entry_y) or age >= ENTRY_BLOCK_STEPS:
                self.route_entry_block = None
            else:
                self.route_entry_block = (entry_map, entry_x, entry_y, back, age + 1)
                blocked_entry = back

        # The guide writes the trail down; the follower walks the one that was
        # already confirmed on RAM. Neither changes how a step is chosen.
        # Both trainers are doing the same job now: find the way through and
        # write it down. Whoever confirms a quest first publishes the trail,
        # and the other one joins it — the roles were about styles of play, and
        # what is missing is the map, not variety.
        quest_id = getattr(self, "current_task_name", None)
        recorder = getattr(self, "trail_recorder", None)
        store = getattr(self, "trail_store", None)
        using_trail = False
        if quest_id and recorder is not None:
            recorder.record(quest_id, map_id, x, y)
        # The drawn route is the one that finishes the game, so it is the one
        # that drives. A trail is a measurement of a crossing that worked, and
        # it stays being recorded and published — but following one is opt-in
        # (`POKEAI_FOLLOW_TRAILS=1`), because a trail that overrides the route
        # only has to be wrong once: a single mined point on Route 4, at
        # (27,3), pointed east, which made the sidestep axis vertical, and
        # south from that tile is Route 3. AARON crossed that border every 0.6
        # seconds for an hour, following a "shortcut" over a route that was
        # right the whole time.
        if quest_id and store is not None and FOLLOW_TRAILS:
            # Recomputing the join every step is what made the trail bounce:
            # from (28,20) the nearest point was (29,20), and from (29,20) it
            # was (28,20) — the trail crosses both on the way out and on the
            # way back. The plan is kept and walked forward like any route;
            # it is only rebuilt when the bot is nowhere near it any more,
            # which is exactly what a whiteout does.
            key = (quest_id, map_id)
            cached = getattr(self, "trail_plan", None)
            trail = cached[1] if cached and cached[0] == key else None
            if trail:
                nearest = min(
                    abs(int(px) - x) + abs(int(py) - y) for px, py in trail
                )
                if nearest > TRAIL_REJOIN_DISTANCE:
                    trail = None
            if trail is None:
                trail = waypoints_from(store.load(quest_id), map_id, x, y)
                # Rejoining by "nearest point" can rejoin *behind*: one step
                # past the tile where the leg begins, the nearest point is that
                # beginning, so the trail pulled the bot back onto the map
                # border it had just crossed — six hundred times. Points just
                # walked are points already spent.
                recent = set(getattr(self, "route_recent_tiles", []))
                while trail and (map_id, int(trail[0][0]), int(trail[0][1])) in recent:
                    trail = trail[1:]
                self.trail_plan = (key, trail)
            if trail and not (len(trail) == 1 and (x, y) == tuple(trail[0])):
                waypoints = trail
                route_id = f"trail-{quest_id}-{map_id}"
                using_trail = True
            elif trail:
                # The leg ends on the doorway to the next map, and a trail says
                # nothing about how to cross it — the next leg is measured in
                # another map's coordinates. Standing on the last point, hand
                # the step back to the route the quest drew, whose final
                # waypoint is deliberately one tile past the border.
                self.trail_plan = None

        self.route_index = self._select_route_index(route_id, waypoints, (x, y))
        target_x, target_y = waypoints[self.route_index]
        blocked = self._tile_truth()
        for (bumped_map, bumped_x, bumped_y, direction) in getattr(self, "route_bumped", {}):
            if (bumped_map, bumped_x, bumped_y) == (map_id, x, y):
                blocked.setdefault(direction, "bumped")
        if blocked_entry:
            blocked[blocked_entry] = "map_edge"
        # Collision calls a doorway walkable, which is true and useless: with
        # the Mart door one tile north, "walk north" put the bot inside the
        # shop, out on the mat, and north again — the flashing at the door.
        # A door is only ever somewhere to arrive at.
        if self.route_index < len(waypoints) - 1:
            # Only mid-route. A route's last waypoint is how it leaves the map,
            # and the tile before it is usually the doorway itself.
            blocked.update(self._warp_steps(x, y, (target_x, target_y)))
        wanted = []
        if abs(target_x - x) >= abs(target_y - y):
            wanted += self._axis_steps(x, target_x, "R", "L")
            wanted += self._axis_steps(y, target_y, "D", "U")
        else:
            wanted += self._axis_steps(y, target_y, "D", "U")
            wanted += self._axis_steps(x, target_x, "R", "L")

        if self.route_index == len(waypoints) - 1 and abs(target_x - x) + abs(
            target_y - y
        ) == 1:
            wanted = [
                "R" if target_x > x else
                "L" if target_x < x else
                "D" if target_y > y else "U"
            ]

        if not wanted:
            # Standing exactly on the last anchor, a route has nothing left to
            # want. With Oak's parcel in the bag a trainer sat on (20,35) doing
            # sidesteps until the watchdog restarted the mission, which put it
            # back on the same tile, which restarted it again — the journey
            # looked like it was rebooting in a loop. Keep heading the way it
            # came in, so "arrived" still means "leave".
            last_direction = getattr(self, "route_last_direction", None)
            if last_direction:
                wanted = [last_direction]

        # Where it has just been. Not learned geometry — a memory eight tiles
        # long, thrown away as it goes.
        stale = self._recently_walked_steps(map_id, x, y)

        # Progress toward this target, measured. Repeating a tile is not
        # evidence of being stuck in tall grass: an encounter freezes the bot
        # where it stands, so the same tile comes up again and again while the
        # route is working perfectly. What being stuck actually looks like is
        # distance to the target that stops falling.
        distance = abs(target_x - x) + abs(target_y - y)
        progress_key = (map_id, target_x, target_y)
        if getattr(self, "route_progress_key", None) != progress_key:
            self.route_progress_key = progress_key
            self.route_best_distance = distance
            self.route_no_progress = 0
        elif distance < getattr(self, "route_best_distance", distance):
            self.route_best_distance = distance
            self.route_no_progress = 0
        else:
            self.route_no_progress = getattr(self, "route_no_progress", 0) + 1

        # A freeze has to leave a trace. Without one, every investigation
        # starts over: load the save, reproduce, guess. This writes down what
        # was decided and why, at the moment the walking stopped.
        self._report_if_stuck(
            map_id, x, y, target_x, target_y, blocked, waypoints, route_id
        )

        # What the screen has already shown of this map, kept. A screenful is
        # enough to step around a tree and nowhere near enough to leave a
        # pocket whose exit is off screen — which is why two trainers spent an
        # afternoon in the Forest, each tile looking like the best way to a
        # waypoint neither could reach. Terrain does not change, so remembering
        # it is not a guess; people are left out of it on purpose.
        # One tile away, there is nothing to plan: step onto it. Planning here
        # is how the gate door was missed — the bot had crossed (3,44) often
        # enough for the frontier rule to take over, and it walked away from
        # the doorway it was standing next to, over and over.
        if abs(target_x - x) + abs(target_y - y) == 1:
            step = (
                "R" if target_x > x else
                "L" if target_x < x else
                "D" if target_y > y else "U"
            )
            if step not in blocked:
                return self._route_move(step)

        # The plan outranks the eight-tile memory: that memory exists for when
        # there is nothing better than a guess, and a committed path is better.
        planned = self._planned_step(map_id, x, y, target_x, target_y)
        if planned is not None and planned not in blocked:
            return self._route_move(planned)

        for step in wanted:
            if step not in blocked and step not in stale:
                return self._route_move(step)

        if wanted and all(blocked.get(step) == "sprite" for step in wanted):
            self.route_blocked_steps = getattr(self, "route_blocked_steps", 0) + 1
            if self.route_blocked_steps <= SPRITE_PATIENCE_STEPS:
                return None

        # Both axes are walls. A sidestep chosen blindly is what parked two
        # trainers against the Forest's y=30 wall — one paced between (6,30)
        # and (8,30) for half an hour while the grass fed it battles, the other
        # simply stopped at (18,32). The screen knows the way around: the tile
        # map says which of the visible tiles are walkable, so ask it instead
        # of guessing left or right.
        step = self._visible_step(target_x - x, target_y - y)
        if step is not None and step not in blocked and step not in stale:
            return self._route_move(step)

        detours = ("U", "D") if wanted and wanted[0] in ("L", "R") else ("L", "R")
        for candidate in detours:
            if candidate not in blocked and candidate not in stale:
                return self._route_move(candidate)
        # Everything ahead is either a wall or somewhere we just came from.
        # Going back is worse than standing still only while there is another
        # option; now there is not.
        if step is not None and step not in blocked:
            return self._route_move(step)
        for candidate in wanted + list(detours):
            if candidate not in blocked:
                return self._route_move(candidate)
        return None

    def _route_role(self):
        """Guide or follower; tests build agents without going through init."""
        return getattr(self, "route_role", "follower")

    def publish_trail(self, quest_id):
        """Hand the walked path to the followers, once the cartridge agrees.

        Called only when a quest predicate is confirmed on real RAM, so a
        published trail is by construction a path that arrived — and, since a
        whiteout restarts the recording, one that arrived without dying.

        Returns what the crossing cost, or ``False`` when nothing was stored.
        """
        recorder = self.trail_recorder
        if recorder.quest_id != quest_id:
            return False
        legs = recorder.legs()
        cost = {
            "points": sum(len(leg["points"]) for leg in legs),
            "maps": [leg["map"] for leg in legs],
            "death_cycle": recorder.cycle,
            "steps": recorder.steps,
        }
        published = self.trail_store.publish(
            quest_id, self.player_name, legs,
            dense=True, cycle=recorder.cycle, steps=recorder.steps,
        )
        recorder.clear()
        return cost if published else False

    def begin_death_cycle(self, cycle):
        """A whiteout closes the attempt; report what it cost before dropping it."""
        # O avanço de rota morre com a tentativa. O cartucho levou o treinador
        # de volta a um Centro, então "já passei por aqui" deixou de valer: a
        # travessia recomeça, e mirar o waypoint do meio a partir da porta é
        # planejar por cima de terreno que esta tentativa não andou.
        self.route_progress = {}
        recorder = getattr(self, "trail_recorder", None)
        if recorder is None:
            return 0
        self.trail_plan = None
        return recorder.restart(cycle)

    def _recently_walked_steps(self, map_id, x, y):
        """Directions that lead back into the last few tiles walked.

        Pacing is not a wall and not a person: it is the route and the detour
        disagreeing. Two tiles were not enough to see it. BARON walked between
        (6,30) and (8,30) in the Forest for half an hour — a four-step cycle,
        invisible to a memory that only looked two steps back — while the grass
        kept handing him battles, so from outside it looked like training.

        So the memory is the last eight tiles, and it only has an opinion when
        the bot is standing somewhere it has already been in that window: then
        every step that leads back into the window is discouraged. Discouraged,
        not forbidden — the caller falls back to them when nothing else is
        open. Nothing is written down, nothing is learned, nothing outlives
        eight steps.
        """
        history = list(getattr(self, "route_recent_tiles", []))
        history.append((map_id, x, y))
        history = history[-ROUTE_MEMORY_TILES:]
        self.route_recent_tiles = history
        if history.count((map_id, x, y)) < 2:
            return set()
        visited = set(history)
        stale = set()
        for direction, (dx, dy) in ROUTE_STEP_OFFSETS.items():
            if (map_id, x + dx, y + dy) in visited:
                stale.add(direction)
        return stale

    def _report_if_stuck(self, map_id, x, y, target_x, target_y, blocked,
                         waypoints, route_id):
        """Write one line explaining a freeze, the moment it becomes one.

        Everything here is read, never inferred: where the bot is, where the
        route wants it, which directions the cartridge refuses and for what
        reason, what the accumulated map thinks, and how long it has been
        getting no closer. Read it later with `tools/stuck_report.py`.
        """
        # Travar nem sempre é ficar no mesmo tile: dois tiles alternados são
        # igualmente parados, e foi assim que a Rota 4 escapou do primeiro
        # gatilho. O que conta é quantos lugares diferentes ele viu por último.
        window = (getattr(self, "stuck_report_window", []) + [(map_id, x, y)])[-STUCK_WINDOW_TILES:]
        self.stuck_report_window = window

        # Trocar de mapa também é ficar parado, e esse jeito de travar escapava
        # do gatilho acima duas vezes: cada travessia pisa tiles diferentes dos
        # dois lados, então a janela enche de posições distintas; e a chave de
        # progresso inclui o mapa, então "passos sem encurtar a distância"
        # zera a cada ida. AARON cruzou Rota 4 e Mt. Moon **400 vezes em 300
        # segundos** sem produzir uma linha de relatório, e foi a terceira vez
        # no mesmo dia que um vaivém entre mapas precisou ser descoberto na mão.
        crossings = getattr(self, "stuck_map_window", [])
        if not crossings or crossings[-1] != map_id:
            crossings = (crossings + [map_id])[-STUCK_MAP_CROSSINGS:]
            self.stuck_map_window = crossings
        bouncing = (
            len(crossings) >= STUCK_MAP_CROSSINGS and len(set(crossings)) <= 2
        )

        if not bouncing and (
            len(window) < STUCK_WINDOW_TILES
            or len(set(window)) > STUCK_DISTINCT_TILES
        ):
            self.stuck_report_steps = 0
            self.stuck_report_written = 0
            return
        self.stuck_report_steps = getattr(self, "stuck_report_steps", 0) + 1
        written = getattr(self, "stuck_report_written", 0)
        if self.stuck_report_steps < STUCK_REPORT_STEPS * (written + 1):
            return
        self.stuck_report_written = written + 1

        memory = self._map_memory()
        try:
            reachable = memory.find_path(map_id, (x, y), (target_x, target_y))
        except Exception:
            reachable = None
        try:
            frontier = memory.nearest_frontier(map_id, (x, y))
        except Exception:
            frontier = None
        try:
            warps = sorted(self._tile_reader().warp_tiles())
        except Exception:
            warps = []
        party = []
        try:
            for index in range(min(int(self.emulator.memory.get_party_count()), 6)):
                start = 0xD16B + index * 44
                read = self.emulator.memory.read_byte
                party.append({
                    "species": int(read(start)),
                    "hp": (int(read(start + 1)) << 8) + int(read(start + 2)),
                    "max_hp": (int(read(start + 34)) << 8) + int(read(start + 35)),
                    "pp": [int(read(start + 29 + slot)) & 0x3F for slot in range(4)],
                })
        except Exception:
            pass

        report = {
            "at": time.time(),
            "agent": getattr(self, "player_name", "?"),
            "quest": getattr(self, "current_task_name", None),
            "map": map_id,
            "position": [x, y],
            "target": [target_x, target_y],
            "route_id": route_id,
            "route_index": getattr(self, "route_index", None),
            "bouncing_between_maps": (
                sorted(set(getattr(self, "stuck_map_window", []))) if bouncing else None
            ),
            "waypoints": [list(point) for point in waypoints[:8]],
            "blocked": dict(blocked),
            "bumped": [
                list(key) for key in getattr(self, "route_bumped", {})
                if key[:3] == (map_id, x, y)
            ],
            "steps_on_this_tile": self.stuck_report_steps,
            "steps_without_progress": getattr(self, "route_no_progress", 0),
            "closest_it_got": getattr(self, "route_best_distance", None),
            "path_to_target": "".join(reachable) if reachable else None,
            "nearest_unexplored": list(frontier) if frontier else None,
            "map_warps": [list(warp) for warp in warps],
            "terrain_known": {
                "walkable": len(memory.walkable.get(int(map_id), ())),
                "solid": len(memory.solid.get(int(map_id), ())),
            },
            "in_battle": int(self.emulator.memory.read_byte(0xD057)),
            "textbox": int(self.emulator.memory.read_byte(0xCFC4)),
            "party": party,
        }
        try:
            path = Path(self.save_dir) / "logs" / "stuck.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(report, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _nearest_useful_warp(self, x, y):
        """Closest door on this map that is not the one just used."""
        reader = self._tile_reader()
        if reader is None:
            return None
        try:
            warps = reader.warp_tiles()
        except Exception:
            return None
        entry = getattr(self, "route_entry_block", None)
        recent = {(int(a), int(b)) for _, a, b in getattr(self, "route_recent_tiles", [])}
        if entry:
            recent.add((entry[1], entry[2]))
        candidates = [tile for tile in warps if tile not in recent]
        if not candidates:
            candidates = list(warps)
        if not candidates:
            return None
        return min(candidates, key=lambda t: abs(t[0] - x) + abs(t[1] - y))

    def _warp_steps(self, x, y, goal):
        """Directions that step onto a door which is not where we are going."""
        reader = self._tile_reader()
        if reader is None:
            return {}
        try:
            warps = reader.warp_tiles()
        except Exception:
            return {}
        return {
            direction: "warp"
            for direction, (dx, dy) in ROUTE_STEP_OFFSETS.items()
            if (x + dx, y + dy) in warps and (x + dx, y + dy) != tuple(goal)
        }

    def _map_memory(self):
        """Terrain seen so far, shared by every trainer who walks the same map."""
        memory = getattr(self, "map_memory", None)
        if memory is None:
            memory = MapMemory(SHARED_TERRAIN_PATH)
            self.map_memory = memory
        return memory

    def _tile_reader(self):
        reader = getattr(self, "tile_collision", None)
        if reader is None:
            pyboy = getattr(self.emulator, "pyboy", None)
            if pyboy is None:
                return None
            reader = TileCollision(pyboy)
            self.tile_collision = reader
        return reader

    def _planned_step(self, map_id, x, y, target_x, target_y):
        """First step of a path across everything seen of this map, or None.

        Unseen tiles are treated as worth trying, so the plan happily walks off
        the edge of what has been looked at; every step replaces that optimism
        with a reading. People are avoided as of right now, never remembered.
        """
        reader = self._tile_reader()
        if reader is None:
            return None
        memory = self._map_memory()
        try:
            # Only read terrain from a screen that is showing the map. In a
            # battle the tile map holds the battle graphics, and every tile
            # reads as a wall: those readings were stored as permanent
            # geometry, and after a few fights in tall grass the Forest was
            # remembered as a closed pocket — from (6,30) the map offered no
            # path to any waypoint, not even to the edge of what was known.
            if (
                int(self.emulator.memory.read_byte(0xD057)) == 0
                and not self._menu_is_open()
            ):
                memory.observe(map_id, (x, y), reader.terrain_grid())
                memory.forget_solid(map_id, (x, y))
            occupied = {
                (x + dx, y + dy) for dx, dy in reader.occupied_offsets()
            }
            # A door is walkable and it is also a trapdoor. Planning *through*
            # one is what made the Mart feel like it had gravity: the path to a
            # waypoint two tiles away crossed the doorway, the bot stepped in,
            # came out on the mat, and planned the same path again. Doors are
            # only ever a destination, never a shortcut.
            goal = (target_x, target_y)
            occupied |= {
                tile for tile in reader.warp_tiles()
                if tile != goal and tile != (x, y)
            }
            # Walls found by bumping belong in the plan, not only in the last
            # choice of step. Without this the planner kept proposing the same
            # impossible first move: the report read "caminho até o alvo:
            # DRRRUU" while D was the very wall the bot had just hit.
            occupied |= {
                (key[1] + dx, key[2] + dy)
                for key in getattr(self, "route_bumped", {})
                if key[0] == map_id
                for dx, dy in [ROUTE_STEP_OFFSETS[key[3]]]
            }
        except Exception:
            return None
        self.map_memory_steps = getattr(self, "map_memory_steps", 0) + 1
        if self.map_memory_steps % TERRAIN_SAVE_INTERVAL == 0:
            try:
                memory.save()
            except OSError:
                pass
        # A plan is followed, not recomputed. Replanning every step is what the
        # y=30 tree line in the Forest turned into pacing: the way around is
        # long and mostly unseen, so each fresh search picked a different side
        # and the bot alternated between (6,30) and (8,30) forever, learning a
        # screenful each time and never committing to either. Now the path is
        # kept until it is spent, until the goal changes, or until the very
        # tile it wants to step on turns out to be a wall.
        # Repeating a tile means the goal is behind something the map does not
        # know yet. Aim at the edge of the known instead: walking there is the
        # only move that turns unknown into map, and it always ends the loop.
        if (
            getattr(self, "route_no_progress", 0) > NO_PROGRESS_STEPS
            and abs(target_x - x) + abs(target_y - y) > FRONTIER_MIN_DISTANCE
        ):
            frontier = memory.nearest_frontier(map_id, (x, y), blocked=occupied)
            if frontier and frontier != (x, y):
                target_x, target_y = frontier
            elif getattr(self, "route_no_progress", 0) > STUCK_GIVE_UP_STEPS:
                # Nothing to explore and nowhere to get to: the waypoint is
                # wrong for where this bot actually is. The map's own doors are
                # the one thing here that is not a guess — a cave has no other
                # way on — so head for the nearest one that is not the way in.
                door = self._nearest_useful_warp(x, y)
                if door:
                    target_x, target_y = door

        plan = getattr(self, "terrain_plan", None)
        goal_key = (map_id, (target_x, target_y))
        if plan and plan["key"] == goal_key and plan["steps"]:
            step = plan["steps"][0]
            dx, dy = ROUTE_STEP_OFFSETS[step]
            destination = (x + dx, y + dy)
            if (
                plan["from"] == (x, y)
                and destination not in occupied
                and not memory.is_solid(map_id, destination)
            ):
                plan["steps"] = plan["steps"][1:]
                plan["from"] = destination
                return step
        try:
            path = memory.find_path(
                map_id, (x, y), (target_x, target_y), blocked=occupied
            )
            if not path:
                # No route through what is known. The notes are a hint, never
                # an authority: live collision refuses a real wall at the
                # moment of the step, so trying is cheap and standing still is
                # not. Without this the bot sat inside a pocket its own map had
                # invented and had nothing left to explore.
                path = memory.find_path(
                    map_id, (x, y), (target_x, target_y),
                    blocked=occupied, ignore_solid=True,
                )
        except Exception:
            self.terrain_plan = None
            return None
        if not path:
            self.terrain_plan = None
            return None
        first_dx, first_dy = ROUTE_STEP_OFFSETS[path[0]]
        self.terrain_plan = {
            "key": goal_key,
            "steps": path[1:],
            "from": (x + first_dx, y + first_dy),
        }
        return path[0]

    def _visible_step(self, target_dx, target_dy):
        """Find one local step around visible terrain and sprites."""
        reader = getattr(self, "tile_collision", None)
        if reader is None:
            pyboy = getattr(self.emulator, "pyboy", None)
            if pyboy is None:
                return None
            reader = TileCollision(pyboy)
            self.tile_collision = reader
        try:
            return reader.path_step(target_dx, target_dy)
        except Exception:
            return None

    @staticmethod
    def _axis_steps(current, target, positive, negative):
        if target > current:
            return [positive]
        if target < current:
            return [negative]
        return []

    def _leave_unknown_map(self):
        """Walk back out of a map no executor has a route for.

        Wandering into an interior used to be terminal: with no route for that
        map the executor pressed A forever, and both bots sat inside the Mt.
        Moon trader's house until someone noticed. The door is known, though —
        the tile the bot appeared on when the map changed, exited by the
        opposite of the direction that walked in.
        """
        map_id = int(self.emulator.memory.get_map_id())
        position = self.emulator.memory.get_player_pos()

        entry = getattr(self, "map_entry_tiles", {}).get(map_id)
        if entry is None:
            # No transition seen this session, so fall back to a door somebody
            # has already walked through. Ranked below the entry tile on
            # purpose: the nearest door may well be the one just entered, and
            # aiming at it walks the bot straight back where it came from.
            # A porta debaixo dos próprios pés não serve de destino: andar até
            # onde já se está não é andar. BARON foi retomado exatamente em
            # cima da porta do Centro da Rota 4, a porta foi descartada por
            # isso, e ele caiu no passeio cego abaixo — dez tiles ao sul e de
            # volta, para sempre. Descartar o tile atual e usar a próxima porta
            # mantém o fallback com uma saída de verdade.
            known = [
                tile for tile in self._warp_memory().doors_from(map_id)
                if tuple(tile) != tuple(position)
            ]
            if known:
                door = min(
                    known,
                    key=lambda tile: (
                        abs(tile[0] - position[0]) + abs(tile[1] - position[1])
                    ),
                )
                return self._follow_route(f"door-{map_id}", [door])
        if entry is None:
            # Never saw the transition — a resumed save, or the whiteout warp
            # that drops a run at its mother's house. Head for the south edge,
            # where interior doors are, but through the route machinery: a
            # blind DOWN press against a wall repeats forever and teaches
            # nothing, while a route learns the wall and plans around it.
            x, y = self.emulator.memory.get_player_pos()
            return self._follow_route(f"exit-{map_id}", [(x, y + BLIND_EXIT_REACH)])

        entry_x, entry_y, entry_direction = entry
        if (self.emulator.memory.get_player_pos()) != (entry_x, entry_y):
            return self._follow_route(f"leave-{map_id}", [(entry_x, entry_y)])
        self.last_action_was_move = True
        return ROUTE_EVENTS[OPPOSITE_DIRECTIONS[entry_direction]]

    def _tile_truth(self):
        """Blocked directions read from the cartridge, or {} if unreadable."""
        reader = getattr(self, "tile_collision", None)
        if reader is None:
            pyboy = getattr(self.emulator, "pyboy", None)
            if pyboy is None:
                return {}
            reader = TileCollision(pyboy)
            self.tile_collision = reader
        try:
            return reader.blocked_directions()
        except Exception:
            return {}

    def _warp_memory(self):
        """Doors shared by every trainer, beside the learned collision map."""
        memory = getattr(self, "warp_memory", None)
        if memory is None:
            memory = WarpMemory(SHARED_WARP_PATH)
            self.warp_memory = memory
        return memory



    def _route_move(self, direction):
        """Issue a D-pad press and remember it, so a failure can be attributed."""
        self.last_action_was_move = True
        self.route_last_direction = direction
        self.route_last_issue = "move"
        return ROUTE_EVENTS[direction]

    def _fixed_route(self, route_id, actions):
        """Replay a measured D-pad segment without inventing collision facts."""
        if getattr(self, "fixed_route_id", None) != route_id:
            self.fixed_route_id = route_id
            self.fixed_route_index = 0
        index = getattr(self, "fixed_route_index", 0)
        if index >= len(actions):
            return None
        direction = actions[index]
        self.fixed_route_index = index + 1
        return self._route_move(direction)

    def _route_text(self):
        """Clear whatever is holding the input, alternating B and A.

        A advances dialogue; it does **not** close a menu — on the START menu
        it opens a submenu instead, so the box never goes away. Two trainers
        stood on Route 1 and Route 3 for thousands of steps in front of a menu
        that only B could close, while the route pressed A forever. B also
        advances text in Gen I, so leading with it is safe; A still gets its
        turn for the prompts that need a confirmation.

        Whatever it presses, the failure must not be read as a wall: text and
        walls look identical from outside, and guessing wrong writes a
        permanent lie into knowledge every trainer shares.
        """
        self.route_last_issue = "text"
        presses = getattr(self, "route_menu_presses", 0)
        return (
            WindowEvent.PRESS_BUTTON_B if presses % 2 == 0
            else WindowEvent.PRESS_BUTTON_A
        )

    def _get_typing_sequence(self, name):
        """
        Generates a sequence of inputs to type the given name on the Gen 1 keyboard.
        Assumes starting position is 'A' (0,0).
        Layout (9 cols):
        A B C D E F G H I
        J K L M N O P Q R
        S T U V W X Y Z
        """
        seq = []
        curr_x, curr_y = 0, 0
        
        grid = {
            'A':(0,0), 'B':(1,0), 'C':(2,0), 'D':(3,0), 'E':(4,0), 'F':(5,0), 'G':(6,0), 'H':(7,0), 'I':(8,0),
            'J':(0,1), 'K':(1,1), 'L':(2,1), 'M':(3,1), 'N':(4,1), 'O':(5,1), 'P':(6,1), 'Q':(7,1), 'R':(8,1),
            'S':(0,2), 'T':(1,2), 'U':(2,2), 'V':(3,2), 'W':(4,2), 'X':(5,2), 'Y':(6,2), 'Z':(7,2)
        }
        
        for char in name.upper():
            if char not in grid:
                continue
                
            target_x, target_y = grid[char]
            
            # Move Y
            dy = target_y - curr_y
            if dy > 0:
                for _ in range(dy):
                    seq.append((WindowEvent.PRESS_ARROW_DOWN, 10))
                    seq.append((WindowEvent.RELEASE_ARROW_DOWN, 10))
            elif dy < 0:
                for _ in range(abs(dy)):
                    seq.append((WindowEvent.PRESS_ARROW_UP, 10))
                    seq.append((WindowEvent.RELEASE_ARROW_UP, 10))
            
            # Move X
            dx = target_x - curr_x
            if dx > 0:
                for _ in range(dx):
                    seq.append((WindowEvent.PRESS_ARROW_RIGHT, 10))
                    seq.append((WindowEvent.RELEASE_ARROW_RIGHT, 10))
            elif dx < 0:
                for _ in range(abs(dx)):
                    seq.append((WindowEvent.PRESS_ARROW_LEFT, 10))
                    seq.append((WindowEvent.RELEASE_ARROW_LEFT, 10))
            
            # Press A
            seq.append((WindowEvent.PRESS_BUTTON_A, 10))
            seq.append((WindowEvent.RELEASE_BUTTON_A, 10))
            
            curr_x, curr_y = target_x, target_y
            
        return seq
