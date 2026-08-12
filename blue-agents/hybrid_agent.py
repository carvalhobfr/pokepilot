"""
Hybrid Agent: Combines RL (from PokemonRedExperiments) with our LLM Battle System

Architecture:
- Use their RedGymEnv for exploration/navigation (RL-based)
- Intercept battles and delegate to LLMAgent  
- Use scripts for critical story moments
- Keep their streaming/visualization
"""

from red_gym_env_v2 import RedGymEnv
from stable_baselines3 import PPO
import sys
import numpy as np
from pathlib import Path
from io import BytesIO
import hashlib
import sqlite3
import math
import time
# Add project root to path so we can import src.llm_agent
project_root = str(Path(__file__).parent.parent.absolute())
if project_root not in sys.path:
    sys.path.append(project_root)

from src.simple_battle import SimpleBattleAgent
from src.scripted_agent import POKEMON_CENTER_MAP_IDS, ScriptedAgent
from src.knowledge_base import KnowledgeBase  # Import KnowledgeBase
from pyboy.utils import WindowEvent
import json
import os
from dotenv import load_dotenv
from ai_path_follower import AIPathFollower  # AI navigation system
from src.navigation_system import NavigationSystem  # Zone saturation logic
from src.hive_mind import HiveMind  # Shared Intelligence
from gymnasium import spaces
from collections import Counter
from event_stream import EventCollapser
from game_actions import GameAction, NOOP_ACTION, event_to_action, name_to_action
from quest_graph import LiveQuestState, QuestGraph
from src.move_data import MoveTable
from area_knowledge import (
    area_coverage,
    area_target,
    encounter_chance,
    is_rare_here,
    species_of_types,
    species_types,
)
from archetypes import (
    DEFAULT_ARCHETYPE,
    MINIMUM_BACKUP_PARTY,
    PROVISIONAL_VALUE,
    RUSH_POWER_VALUE,
    get_archetype,
)
from trainer_directives import (
    MAIN_QUEST_EXECUTOR,
    DirectiveError,
    load_directive,
    save_directive,
    story_is_needed,
    target_quest_ids,
)

POKEDEX_OWNED_START = 0xD2F7
POKEDEX_SEEN_START = 0xD30A
POKEDEX_BYTES = 19
GOT_POKEDEX_ADDRESS = 0xD74B
GOT_POKEDEX_MASK = 1 << 5
CAPTURE_BALL_IDS = (1, 2, 3, 4)  # Master, Ultra, Great, Poké Ball

# Gen I menu state: the bag index under the cursor is the list scroll offset
# plus the highlighted row. The shop controller already drives menus with the
# cursor address, so these are addresses this project has verified in game.
MENU_CURSOR_ADDRESS = 0xCC26
MENU_SCROLL_OFFSET_ADDRESS = 0xCC36
# Which party slot is currently out on the field.
ACTIVE_PARTY_SLOT_ADDRESS = 0xCC2F
# A switch that takes longer than this is not happening; back out instead of
# mashing inputs into a menu that is not the one we think it is.
SWITCH_MENU_STEP_LIMIT = 12

# Steps on the same tile, out of battle, before the mission is restarted from
# where the bot actually is. Long enough that a slow dialogue is not a restart,
# short enough that nobody spends a night on one square.
MISSION_RESTART_STEPS = 300
MAJOR_LOCATION_IDS = set(range(0, 11))
BATTLE_MENU_SAVED_ITEM_ADDRESS = 0xCC2D
# The battle menu is a 2x2 — FIGHT PKMN / ITEM RUN — and the cartridge stores
# it as two bytes, not one index: 0xCC26 is the row and 0xCC25 is the cursor's
# screen column, 9 on the left and 15 on the right. The column doubles as the
# only honest "the menu is really on screen" signal: while battle text is up it
# reads something else entirely (5 during "Nothing happened!").
BATTLE_MENU_COLUMN_ADDRESS = 0xCC25
BATTLE_MENU_ROW_ADDRESS = 0xCC26
BATTLE_MENU_LEFT_COLUMN = 9
BATTLE_MENU_RIGHT_COLUMN = 15
BATTLE_MENU_FIGHT_ROW = 0
BATTLE_MENU_ITEM_ROW = 1
# wMaxMenuItem: the last selectable row of whatever list is on screen.
BATTLE_MENU_LAST_ROW_ADDRESS = 0xCC28
# The bag is a flat list: a count, then id/quantity pairs.
BAG_ITEM_COUNT_ADDRESS = 0xD31D
BAG_FIRST_ITEM_ADDRESS = 0xD31E
BAG_CAPACITY = 20
# One operator order: throw a ball at whatever is on screen right now.
MANUAL_THROW_BALL_TASK = "MANUAL: THROW_BALL"

# Abaixo disso, um encontro selvagem no caminho não vale o turno durante uma
# travessia: fugir custa um turno, lutar até o fim drena o time inteiro.
FLEE_HP_FRACTION = 0.5
# Centres are the only rooms a run may ever be resumed into. The set lives with
# the route controller that walks to them; a second copy here would be a second
# thing to keep in step, and this session has already paid for that mistake
# twice — a counter kept in the process instead of the journey, once for the
# head start and once for the death cycle.
CURRENT_STATE_MANIFEST = "current.state.meta.json"

CAPTURE_RESULT_ADVANCE_STEPS = 18
# Reaching ITEM from anywhere in the 2x2 takes two presses. The rest of this
# budget is patience with battle text; past it, the screen is not the menu.
CAPTURE_MENU_STEP_LIMIT = 24

# Small, explicit Gen I strategy prior. Level still drives the general upgrade
# heuristic; these values cover species whose utility is not obvious from the
# encounter level alone (typing, evolution potential or rarity).
# A Gen I team is six. Below that, an empty slot is a weakness in itself.
PARTY_TARGET = 6

# Soften the target before spending a ball, and never keep throwing while the
# active Pokémon is about to faint.
# A panel entry nobody has rewritten for this long belongs to a trainer that is
# no longer running. Generous enough to survive a slow block boundary.
STALE_AGENT_SECONDS = 600

CAPTURE_HP_THRESHOLD = 0.5
SELF_PRESERVATION_HP = 0.35

# Above this gap the softening hit is a knockout, so softening never produces a
# capture — it produces a corpse. Both are required: +6 levels matters at level
# 10, the ratio is what still matters at level 30.
OVERKILL_LEVEL_GAP = 6
OVERKILL_LEVEL_RATIO = 1.6

# Value reflects what the line *becomes*, not the form met in the grass:
# Metapod is a bad Pokémon and a good catch because Butterfree carries Kanto's
# opening hours. Anything absent defaults to 50.
STRATEGIC_CAPTURE_VALUE = {
    10: 70, 11: 70, 12: 70,  # Caterpie -> Butterfree (Confusion, early sweeper)
    13: 58, 14: 58, 15: 58,  # Weedle -> Beedrill
    16: 60, 17: 60,          # Pidgey line: Fly user
    19: 55,   # Rattata
    21: 52,   # Spearow
    23: 58,   # Ekans
    27: 60,   # Sandshrew
    35: 62,   # Clefairy
    41: 56,   # Zubat -> Golbat
    43: 64,   # Oddish line
    46: 58,   # Paras
    54: 62,   # Psyduck
    56: 58,   # Mankey
    58: 68,   # Growlithe
    60: 60,   # Poliwag
    66: 62,   # Machop
    69: 64,   # Bellsprout line
    74: 60,   # Geodude
    81: 62,   # Magnemite
    25: 78,   # Pikachu
    29: 68, 32: 68,  # Nidoran lines
    50: 62,   # Diglett
    63: 86,   # Abra
    92: 80,   # Gastly
    113: 82,  # Chansey
    129: 72,  # Magikarp -> Gyarados
    131: 92,  # Lapras
    132: 76,  # Ditto
    133: 84,  # Eevee
    137: 72,  # Porygon
    143: 94,  # Snorlax
    144: 100, 145: 100, 146: 100, 150: 100, 151: 100,
    147: 88, 148: 92, 149: 96,  # Dratini line
}

# Load environment variables (for OpenAI API key)
load_dotenv(Path(__file__).parent.parent / '.env')

# Import LLM Agent
# Import LLM Agent
try:
    from src.llm_agent import LLMAgent as LLMPokemonAgent
    LLM_AVAILABLE = True
except ImportError as e:
    print(f"Warning: LLM Agent not available: {e}")
    LLM_AVAILABLE = False

class EmulatorAdapter:
    """
    Adapts RedGymEnv to the interface expected by ScriptedAgent.
    """
    def __init__(self, red_gym_env):
        self.env = red_gym_env
        self.memory = self
        self.pyboy = red_gym_env.pyboy
        
    def get_map_id(self):
        return self.env.read_m(0xD35E)
        
    def get_player_pos(self):
        y = self.env.read_m(0xD361)
        x = self.env.read_m(0xD362)
        return (x, y)
        
    def get_party_count(self):
        return self.env.read_m(0xD163)
        
    def read_byte(self, addr):
        return self.env.read_m(addr)

    def read_rom(self, bank, address):
        """Um byte de um banco da ROM, para as tabelas que o cartucho já traz.

        Sem isto o controlador de batalha recebia uma tabela de golpes vazia:
        toda potência vinha desconhecida, nenhum golpe passava pelo filtro de
        dano, e a escolha caía no desempate de status — onde Growl vale 9 e
        Tackle e Vine Whip caem no padrão 50, então Growl ganhava sempre.

        Medido no Brock: 203 decisões de batalha, **nenhuma** com dados de
        golpe, Vine Whip com os 10 PP intactos e o Geodude em 33/33. O bot
        tinha o golpe que resolve o ginásio e nunca o usou.
        """
        return self.env.read_rom(bank, address)
        
    def read_event_flag(self, byte_addr, bit_index):
        val = self.env.read_m(byte_addr)
        return (val >> bit_index) & 1
        
    def get_battle_state(self):
        # Return minimal state for now as we use SimpleBattleAgent separately
        return {}
        
    def get_is_in_battle(self):
        return self.env.read_m(0xD057) != 0
        
    def save_state(self, filename):
        with open(filename, "wb") as f:
            self.env.pyboy.save_state(f)

class HybridGymEnv(RedGymEnv):
    """
    Extends RedGymEnv to add Simple Battle Logic AND Scripted Navigation.
    """
    
    def __init__(self, config):
        # print(f"DEBUG: HybridGymEnv init. Config keys: {list(config.keys())}")
        super().__init__(config)
        self.battle_agent = SimpleBattleAgent()
        self.agent_name = config.get('agent_name', 'Unknown')
        self.route_role = config.get("route_role", "follower")
        self.trainer_dir = Path(
            config.get(
                "trainer_dir",
                Path(__file__).parent.parent / "trainers" / self.agent_name,
            )
        )
        self.trainer_dir.mkdir(parents=True, exist_ok=True)
        # print(f"DEBUG: Agent Name set to: {self.agent_name}")
        
        # Initialize Knowledge Base with correct relative path
        kb_path = Path(__file__).parent.parent / 'docs/knowledge'
        self.knowledge_base = KnowledgeBase(knowledge_dir=str(kb_path))
        
        # Initialize ScriptedAgent for story progression
        # We always use standard walkthrough.json for ScriptedAgent to avoid structure errors
        walkthrough_file = Path(__file__).parent.parent / 'walkthrough.json'
        # Load default walkthrough
        try:
            with open(walkthrough_file, 'r') as f:
                self.walkthrough = json.load(f)
        except Exception as e:
            print(f"[{self.agent_name}] ⚠️ Error loading walkthrough: {e}")
            self.walkthrough = {}
        
        # Create adapter
        self.emulator_adapter = EmulatorAdapter(self)
        
        # Get starter preference (0=Bulbasaur, 1=Charmander, 2=Squirtle)
        self.starter_preference = config.get('starter_preference', 0)
        starter_names = ["Bulbasaur", "Charmander", "Squirtle"]
        
        # Personality System (4 attributes, 0-100 each)
        self.meta_score = config.get('meta_score', 50)  # Strategic thinking
        self.exploration = config.get('exploration', 50)  # Map discovery drive
        self.collector = config.get('collector', 50)  # Pokemon catching desire
        self.mission_focus = config.get('mission_focus', 50)  # Story progression priority
        self.personality = config.get('personality', 'Balanced')
        self.archetype = config.get('archetype', DEFAULT_ARCHETYPE)
        self.capture_stance = config.get(
            'capture_stance', get_archetype(self.archetype)["capture_stance"]
        )
        self.personality_vector = np.array([
            self.meta_score,
            self.exploration,
            self.collector,
            self.mission_focus,
        ], dtype=np.float32) / 100.0

        # The old PPO policy could receive different rewards per personality,
        # but it could not observe which personality it was controlling. That
        # made the shared policy unable to learn conditional behaviour. Add the
        # profile to the observation so a new checkpoint can learn distinct
        # navigation policies from the same game state.
        self.observation_space = spaces.Dict({
            **self.observation_space.spaces,
            "personality": spaces.Box(
                low=0.0,
                high=1.0,
                shape=(4,),
                dtype=np.float32,
            ),
        })
        
        print(f"[{self.agent_name}] 🌟 Starter Pokemon: {starter_names[self.starter_preference]}")
        print(f"[{self.agent_name}] 🎭 Personality: {self.personality}")
        print(f"[{self.agent_name}]    📊 Meta: {self.meta_score} | 🗺️  Exploration: {self.exploration}")
        print(f"[{self.agent_name}]    🎯 Collector: {self.collector} | 🎖️  Mission: {self.mission_focus}")
        
        # Hard mode bonus (chaos agents with meta_score < 40)
        self.hard_mode_bonus = config.get('hard_mode_bonus', False)
        if self.hard_mode_bonus:
            print(f"[{self.agent_name}] 🔥 CHAOS MODE! Refuses easy strategies, seeks challenge!")
        
        # Legacy LLM logic removed - using on-demand AI Strategy instead
        self.llm_agent = None
        
        # Always create ScriptedAgent (for fallback)
        self.scripted_agent = ScriptedAgent(
            walkthrough_path=str(walkthrough_file), 
            emulator=self.emulator_adapter,
            player_name=self.agent_name,
            save_dir=str(self.trainer_dir),
            starter_choice=self.starter_preference,
            route_role=self.route_role,
        )
        
        # Initialize AI Path Follower (for AI-assisted navigation)
        self.ai_path_follower = AIPathFollower(self.agent_name)
        print(f"[{self.agent_name}] 🤖 AI Path Follower initialized")
        
        # Initialize Hive Mind (Shared Knowledge)
        self.hive_mind = HiveMind()
        
        # Initialize Navigation System (Zone Saturation)
        self.nav_system = NavigationSystem()
        self.exodus_mode = False # Flag to force exit seeking
        
        self.battle_mode_active = False
        
        # Warp Discovery State
        self.last_map_id = None
        self.last_pos = None
        
        # Task System
        self.agent_name = config.get('agent_name', 'Unknown')
        self.task_file = Path(f'tasks/{self.agent_name}.txt')
        self.control_poll_interval = max(
            int(config.get("control_poll_interval", 30)), 1
        )
        self.runtime_control_file = Path("tasks/runtime_controls.json")
        self.agent_paused = False
        self.playback_speed = 1.0
        self.viewer_count = 0
        self.last_route_replan_id = None
        self.pending_route_replan = None
        self.agent_count = max(int(config.get("agent_count", 1)), 1)
        self.state_update_interval = max(
            int(config.get("state_update_interval", 100)), 1
        )
        # A fresh real ROM starts before Oak's mission. The scripted agent can
        # advance this objective from START; claiming Brock here made the UI
        # contradict the emulator's actual story state.
        self.current_task = "QUEST: START"
        self.quest_graph = QuestGraph.load(
            Path(__file__).parent / "knowledge/quests/main_quest_graph.json"
        )
        self.quest_completed_ids = set()
        self.active_quest_id = None
        self.active_order_id = None
        self.run_complete = False

        # The directive says what this trainer is playing for: the whole story
        # by default, a bounded prefix via `stop_at`, or explicit custom orders.
        # A malformed file must stop this trainer instead of silently reverting
        # to "play everything", which would falsify an operator's instruction.
        quest_ids = [node.id for node in self.quest_graph.nodes]
        try:
            self.directive = load_directive(
                self.trainer_dir,
                quest_ids,
                available_executors=self._available_order_executors(),
            )
        except (DirectiveError, OSError, ValueError) as exc:
            raise DirectiveError(
                f"diretiva inválida para {self.agent_name}: {exc}"
            ) from exc
        if self.directive.stop_at:
            print(
                f"[{self.agent_name}] 🎯 Diretiva: {self.directive.mode}, "
                f"até '{self.directive.stop_at}'"
            )
        pending = self.directive.pending_orders()
        if pending:
            print(
                f"[{self.agent_name}] 📋 {len(pending)} ordem(ns) pendente(s): "
                + ", ".join(order.title for order in pending)
            )


        # COMPETITIVE MODE: Delayed Start
        self.delay_steps = config.get('delay_steps', 0)
        self.agent_index = config.get('agent_index', 0)
        self.steps_elapsed = 0
        # A head start is served once per journey, not once per chunk. Each
        # chunk is a new process with `steps_elapsed` back at zero, so without
        # remembering this the last slot would pay its delay again every time
        # and never catch up. Loaded from journey.json below.
        self.head_start_served = False
        if self.delay_steps > 0:
            print(f"[{self.agent_name}] ⏸️  Delayed start: {self.delay_steps} steps ({self.delay_steps/60:.0f}s)") 
        
        # Initialize checkpoint system
        self.checkpoint_dir = self.trainer_dir / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.current_milestone = "start"  # start, oak_done, parcel_delivered, pewter_reached, brock_defeated
        self.resume_state = config.get("resume_state", False)
        self.saved_checkpoint_milestones = (
            {checkpoint.stem for checkpoint in self.checkpoint_dir.glob("*.state")}
            if self.resume_state
            else set()
        )
        # Two clocks used to run apart: a quest was marked done the instant the
        # RAM confirmed it, while a state was only written after a heal in a
        # Center. Kill the process in between and the emulator came back before
        # Mt. Moon while journey.json still swore it had been crossed — the
        # graph then skipped straight to Bill with the trainer standing in
        # Pewter. The generation ties them together: a completion is only
        # trusted on resume if some checkpoint was written *after* it, which is
        # the only proof that the saved state actually contains it.
        self.checkpoint_generation = 0
        self.quest_generations = {}
        self._checkpoint_loaded_from_disk = False

        # Reward State
        self.last_event_count = 0
        self.last_pokedex_count = 0
        self.last_badges = 0
        self.left_pallet_town = False  # Track if agent left starting area
        self.visited_maps = {0, 37, 38}  # Start with Pallet Town maps (to not reward initial location)
        self.visited_major_locations = {0}
        self.announced_story_milestones = set()
        self.announced_capture_decisions = set()
        self.defeated_brock = False  # Track first gym victory (Boulder Badge)
        self.recent_events = []
        self.last_party_species = set()  # Track captured Pokemon for event feed
        self.delivered_parcel = False  # Track parcel delivery (critical mission)
        self.starter_chosen = False  # Track if starter was chosen (for punishment/reward)
        self.starter_choice_applied = False  # Ensure we only apply once
        
        # Battle tracking
        self.in_battle = False
        self.last_battle_enemy_id = None
        self.last_battle_is_trainer = False
        self.last_battle_enemy_hp = None
        self.last_battle_player_hp = None
        self.last_battle_map_id = None
        self.battle_party_count_before = 0
        self.battle_pokedex_owned_before = 0
        self.wild_battles_won = 0
        self.trainer_battles_won = 0
        self.deaths = 0
        # Which attempt this is. Zero is the first crossing, before any death.
        self.death_cycle = 0
        self.whiteout_pending = False
        self.last_hp_check = None  # Track HP to detect deaths
        
        # Periodic Auto-Save System (PRIORITÁRIO ao carregar)
        self.last_periodic_save_time = time.time()
        self.save_interval = max(float(config.get("save_interval", 180)), 30)
        try:
            self.last_manual_save_time = float(
                (Path(__file__).parent / "save_signal.txt").read_text().strip()
            )
        except (OSError, ValueError):
            self.last_manual_save_time = 0
        self.last_party_info = [] # Track party for level ups and swaps
        self.party_tracking_initialized = False
        self.last_pokedex_owned = 0
        self.last_logged_map_id = None
        self.last_logged_task = None
        self.last_active_internal_id = None
        self.last_battle_decision_key = None
        self.battle_sequence = 0
        self.stagnant_position = None
        self.stagnant_steps = 0
        self.capture_count = 0
        self.capture_enabled = bool(config.get("capture_enabled", True))
        self.capture_plan = []
        self.capture_plan_battle = None
        self.capture_in_flight = False
        self.capture_attempts = 0
        self.capture_forced = False
        self.capture_result_steps = 0
        self.capture_balls_before_attempt = None
        self.battle_action_mode = "attack"
        self.last_capture_policy = None
        self.last_battle_enemy_hp = None
        self.last_battle_player_hp = None
        self.last_battle_map_id = None
        self.battle_party_count_before = len(self.last_party_info)
        self.battle_pokedex_owned_before = self.last_pokedex_owned
        self.level_up_count = 0
        self.evolution_count = 0
        self.battle_decision_count = 0
        self.run_id = f"{self.agent_name}-{int(time.time())}"
        self.decision_log_dir = self.trainer_dir / "logs"
        self.decision_log_path = self.decision_log_dir / "decisions.jsonl"
        self.journey_memory_path = self.trainer_dir / "journey.json"
        if self.resume_state:
            self._load_journey_memory()
        self.scripted_agent.viridian_center_healed = (
            "viridian_center_healed" in self.announced_story_milestones
        )
        self.scripted_agent.pewter_center_healed = (
            "pewter_center_healed" in self.announced_story_milestones
        )
        # A PPO rollout boundary must not rewind a real journey.  Keep a
        # process-scoped PyBoy state so the next episode starts where this bot
        # actually stopped.  A new process gets a new path, so --state fresh
        # remains a genuine new run.
        self.persist_journey = bool(config.get("persist_journey", True))
        self.journey_state_path = (
            self.trainer_dir / "runtime" / f"{self.run_id}.state"
        )
        self._journey_episode_started = False
        self.journey_total_steps = 0
        
        # Shared Exploration System
        self.exploration_reward_accumulator = 0.0
        self.shared_db_path = Path("tasks/exploration.db")
        self._init_shared_db()
        
        # Specific Event Rewards
        self.got_pokedex_reward = False
        
        # Anti-Backtracking System (Penalizar repetição de tiles)
        from collections import deque
        self.recent_map_ids = deque(maxlen=20)
        self.recent_tiles = deque(maxlen=20)  # Track (map_id, x, y) tuples
        
    def _init_shared_db(self):
        """Initialize shared exploration database"""
        try:
            with sqlite3.connect(self.shared_db_path, timeout=10) as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS tiles "
                    "(id TEXT PRIMARY KEY, count INTEGER, is_golden INTEGER DEFAULT 0)"
                )
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(tiles)").fetchall()
                }
                if "is_golden" not in columns:
                    conn.execute(
                        "ALTER TABLE tiles ADD COLUMN is_golden INTEGER DEFAULT 0"
                    )
                conn.commit()
        except Exception as e:
            print(f"[{self.agent_name}] DB Init Warning: {e}")
        
        



    def _get_obs(self):
        observation = super()._get_obs()
        observation["personality"] = self.personality_vector.copy()
        return observation

    def reset(self, seed=None, options=None):
        """Reset environment and load best checkpoint if available"""
        carry_journey = (
            self.persist_journey
            and self._journey_episode_started
        )
        if carry_journey:
            try:
                self.journey_state_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.journey_state_path, "wb") as state_file:
                    self.pyboy.save_state(state_file)
            except Exception as exc:
                print(f"[{self.agent_name}] Journey carry-save failed: {exc}")

        obs, info = super().reset(seed=seed, options=options)

        if carry_journey:
            try:
                with open(self.journey_state_path, "rb") as state_file:
                    self.pyboy.load_state(state_file)
                obs = self.refresh_after_external_state_load()
            except Exception as exc:
                print(f"[{self.agent_name}] Journey carry-load failed: {exc}")
        self._journey_episode_started = True

        # `--resume` may restore only the explicitly recorded current
        # checkpoint. It never scans older Center files or arbitrary states.
        if self.resume_state and not carry_journey:
            if self._load_current_checkpoint():
                obs = self.refresh_after_external_state_load()
            else:
                # Retomada pedida e negada: o emulador ficou com o estado de
                # partida, que é o mais rebobinado que existe, e `journey.json`
                # continua alegando a jornada inteira. Este é o caso perigoso,
                # e era o único que escapava — a verificação só rodava quando um
                # checkpoint *tinha* sido carregado.
                #
                # Acontece de verdade: matar o processo entre gravar
                # `current.state` e gravar o manifesto deixa os dois sem bater,
                # o hash é recusado, e CARON acordou no quarto inicial com zero
                # insígnias enquanto o journey jurava Mt. Moon.
                self.checkpoint_generation = 0
                self._checkpoint_loaded_from_disk = True
                print(
                    f"[{self.agent_name}] ⚠️ Retomada recusada: "
                    "progresso será reconferido na RAM"
                )

        # Establish baselines only after every save-state load. This prevents
        # a resumed team from being announced as a fresh capture.
        self.last_party_info = self.get_party_info()
        self.party_tracking_initialized = True
        self.last_pokedex_owned = self._pokedex_owned_count()
        self.last_logged_map_id = None
        self.last_logged_task = None
        self.last_active_internal_id = None
        self.last_battle_decision_key = None
        self.capture_plan = []
        self.capture_plan_battle = None
        self.capture_in_flight = False
        self.capture_attempts = 0
        self.capture_forced = False
        self.capture_result_steps = 0
        self.capture_balls_before_attempt = None
        self.battle_action_mode = "attack"
        self.last_capture_policy = None

        # Recompute the active story node after every reset or external state
        # load. The save is the source of truth; scripts never advance the
        # story by elapsed time or by claiming that they are finished.
        self._sync_quest_objective()
            
        return obs, info

    def _drop_progress_the_cartridge_denies(self, state):
        """Forget remembered quests the loaded save cannot possibly have done.

        Completion is sticky on purpose — "crossed the Forest" stops being true
        the moment the bot leaves map 51. Sticky plus a rewound save is a trap:
        the resume rule refused a `current.state` that was not inside a Center,
        the run restarted in the bedroom with an empty party, and `journey.json`
        still claimed five quests. The Forest executor then ran upstairs at
        home, where it has no route and nothing to do, forever.

        The stamp decides who gets asked, not the predicate type. A quest
        observed while generation N was running is only inside a checkpoint
        numbered above N; below that it is a claim the loaded state cannot
        back, and it faces the RAM again whether it reads a badge or a map.
        Sealed quests stay sticky, the transient ones included — the checkpoint
        is the proof that the bot really did walk past there.

        Checking only once per process was its own trap: `reset` reloads from
        disk more than once, and a later rewind to an older Center found the
        latch already closed.
        """
        if not self._checkpoint_loaded_from_disk:
            return
        self._checkpoint_loaded_from_disk = False
        sealed = int(getattr(self, "checkpoint_generation", 0))
        denied = set()
        for quest_id in list(self.quest_completed_ids):
            node = self.quest_graph.nodes_by_id.get(quest_id)
            if node is None:
                continue
            observed_at = self.quest_generations.get(quest_id)
            if observed_at is not None and int(observed_at) < sealed:
                continue
            if not self.quest_graph.node_matches(node, state):
                denied.add(quest_id)
        if not denied:
            return
        self.quest_completed_ids -= denied
        for quest_id in denied:
            self.quest_generations.pop(quest_id, None)
        self._persist_journey_memory()
        self._log_event("progress_reset", {
            "dropped": sorted(denied),
            "checkpoint_generation": sealed,
            "reason": "save carregado não confirma estas quests na RAM",
        })

    def _sync_quest_objective(self):
        """Select the first incomplete quest using RAM plus sticky progress.

        Map predicates are transient: after crossing Viridian Forest the bot
        is no longer *in* map 51. Once a predicate is observed, completion is
        durable for this journey and is archived alongside the emulator state.

        The trainer's directive narrows this: ``stop_at`` bounds how far the
        story runs, and pending custom orders are checked first, because an
        explicit human order outranks the default background activity.
        """
        state = LiveQuestState(self)
        self._drop_progress_the_cartridge_denies(state)

        # A pending order is verified against the same RAM predicates the story
        # uses, so "ordem cumprida" can never be claimed by elapsed time.
        order = self._sync_directive_orders(state)
        if order is not None and order.executor != MAIN_QUEST_EXECUTOR:
            desired_task = f"ORDER: {order.executor.upper()}"
            if self.active_order_id != order.id or self.current_task != desired_task:
                previous = self.active_order_id
                self.active_order_id = order.id
                self.active_quest_id = None
                self.run_complete = False
                self.current_task = desired_task
                self.current_milestone = f"order:{order.id}"
                self._log_event("order_started", {
                    "from_order_id": previous,
                    "order_id": order.id,
                    "kind": order.kind,
                    "title": order.title,
                    "success": [dict(condition) for condition in order.success],
                    "reason": "ordem explícita do treinador tem prioridade sobre a história",
                })
            return
        self.active_order_id = None

        node = None
        progress_changed = False
        targets = self._directive_target_quest_ids()
        # Insígnia e bandeira de evento o jogo nunca desfaz: onde elas confirmam
        # um nó, tudo antes dele aconteceu. Sem esse piso, um save carregado com
        # a insígnia do Brock parava no nó de comprar Poké Bolas — predicado de
        # recurso, que volta a falhar assim que as bolas acabam — e o executor
        # daquele nó só conhece o caminho até o Mart de Viridian, então da Rota
        # 4 ele ficava indo e voltando na mesma casa.
        floor = self.quest_graph.achievement_floor(state)
        for index, candidate in enumerate(self.quest_graph.nodes):
            if index <= floor and candidate.id not in self.quest_completed_ids:
                self.quest_completed_ids.add(candidate.id)
                self.quest_generations[candidate.id] = int(
                    getattr(self, "checkpoint_generation", 0)
                )
                progress_changed = True
                continue
            if candidate.id in self.quest_completed_ids:
                continue
            if self.quest_graph.node_matches(candidate, state):
                if candidate.id not in self.quest_completed_ids:
                    # Confirmed on real RAM: only now is the walked path worth
                    # handing to the followers.
                    try:
                        # Keyed by executor, which is what the route follower
                        # knows itself as while it walks.
                        cost = self.scripted_agent.publish_trail(candidate.executor)
                        if cost:
                            # What it cost is the whole point of measuring: the
                            # published trail is one attempt out of however many
                            # the deaths made, and this says which one and how
                            # many tiles it walked.
                            self._log_event("trail_published", {
                                "quest_id": candidate.id,
                                **cost,
                                "reason": "predicado confirmado na RAM",
                            })
                    except Exception as error:
                        print(f"[{self.agent_name}] Trail Error: {error}")
                self.quest_completed_ids.add(candidate.id)
                # Observed now, under the generation currently loaded. It stops
                # being a mere observation once a checkpoint above this number
                # is written.
                self.quest_generations[candidate.id] = int(
                    getattr(self, "checkpoint_generation", 0)
                )
                progress_changed = True
                continue
            # `stop_at` bounds the story: nodes past the target are not this
            # trainer's job, so the run is finished rather than merely idle.
            if targets is not None and candidate.id not in targets:
                break
            node = candidate
            break
        if progress_changed:
            self._persist_journey_memory()

        completed_nodes = self.quest_graph.completed_nodes(
            state, self.quest_completed_ids
        )

        if node is None:
            if not self.run_complete:
                previous = self.active_quest_id
                self.active_quest_id = None
                self.run_complete = True
                self.current_task = "COMPLETE"
                self.current_milestone = "mewtwo_postgame_complete"
                self._log_event("run_completed", {
                    "from_quest_id": previous,
                    "completed_nodes": completed_nodes,
                    "reason": "todos os predicados do QuestGraph foram confirmados na RAM",
                })
                self._save_checkpoint(self.current_milestone)
            return

        desired_task = f"QUEST: {node.executor.upper()}"
        if self.active_quest_id == node.id and self.current_task == desired_task:
            return

        previous = self.active_quest_id
        self.active_quest_id = node.id
        self.run_complete = False
        self.current_task = desired_task
        self.current_milestone = node.id
        self._log_event("quest_advanced", {
            "from_quest_id": previous,
            "to_quest_id": node.id,
            "title": node.title,
            "completed_nodes": completed_nodes,
            "reason": "objetivo ativo calculado a partir do save real",
        })

    @staticmethod
    def _available_order_executors():
        """Order controllers that really exist, discovered the same way quests are.

        ScriptedAgent dispatches on ``_run_<executor>``, so this stays true
        automatically as new controllers are written.
        """
        return {
            name[len("_run_"):]
            for name in dir(ScriptedAgent)
            if name.startswith("_run_")
        }

    def _directive_target_quest_ids(self):
        """Story nodes this trainer is responsible for, or None for all of them."""
        if story_is_needed(self.directive):
            return None
        try:
            targets = target_quest_ids(
                self.directive,
                [node.id for node in self.quest_graph.nodes],
            )
        except DirectiveError:
            return None
        if len(targets) == len(self.quest_graph.nodes):
            return None
        return set(targets)

    def _sync_directive_orders(self, state):
        """Confirm finished orders against RAM and return the next pending one."""
        changed = False
        for order in self.directive.pending_orders():
            satisfied = all(
                self.quest_graph._matches(condition, state)
                for condition in order.success
            )
            if not satisfied:
                if changed:
                    self._persist_directive()
                return order
            self.directive = self.directive.with_completed(order.id)
            changed = True
            self._log_event("order_completed", {
                "order_id": order.id,
                "kind": order.kind,
                "title": order.title,
                "reason": "condição da ordem confirmada na RAM do cartucho",
            })
        if changed:
            self._persist_directive()
        return None

    def _persist_directive(self):
        try:
            save_directive(self.trainer_dir, self.directive)
        except OSError as exc:
            print(f"[{self.agent_name}] Falha ao persistir diretiva: {exc}")

    def _read_runtime_controls(self):
        """Read the small dashboard control snapshot without blocking PyBoy."""
        try:
            with open(self.runtime_control_file, "r", encoding="utf-8") as control_file:
                controls = json.load(control_file)
            global_control = controls.get("global", {})
            agent_control = controls.get("agents", {}).get(self.agent_name, {})
            requested_speed = float(global_control.get("speed", 1.0))
            self.playback_speed = requested_speed if requested_speed in (0.0, 0.5, 1.0, 2.0) else 1.0
            # The relay publishes how many dashboards are open. Missing means
            # no relay at all, which is training with nobody watching.
            self.viewer_count = max(int(global_control.get("viewers", 0) or 0), 0)
            self.agent_paused = bool(agent_control.get("paused", False))
            request = agent_control.get("replan")
            if isinstance(request, dict) and request.get("id") != self.last_route_replan_id:
                self.last_route_replan_id = request.get("id")
                self.pending_route_replan = request
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # The relay writes atomically, but keeping the previous state is
            # safer than changing speed due to a transient read failure.
            pass

    def _apply_route_replan(self):
        # Loop detection remains telemetry-only while route behavior is being
        # rebuilt. A browser observation must not mutate a live quest cache.
        self.pending_route_replan = None

    def _apply_playback_throttle(self, step_started_at):
        """Throttle the synchronous vector loop to Game Boy wall-clock speed.

        A Game Boy runs at about 60 frames/s. Each environment action advances
        `act_freq` frames. DummyVecEnv steps agents sequentially, so each agent
        contributes only its share of the target vector-step duration.
        Speed 0 means explicit uncapped training mode.

        The throttle exists so a human can follow the arena. With every
        dashboard closed it buys nothing and costs everything: the same binary
        went from 4 to 446 PPO steps/s on an M1 with it removed. So an empty
        audience is training mode, whatever the speed selector says.
        """
        if self.playback_speed <= 0 or getattr(self, "viewer_count", 0) <= 0:
            return
        target_seconds = (
            float(self.act_freq) / 60.0 / self.playback_speed / self.agent_count
        )
        remaining = target_seconds - (time.monotonic() - step_started_at)
        if remaining > 0:
            time.sleep(remaining)

    def step(self, action):
        step_started_at = time.monotonic()
        policy_action = int(action)
        action_source = "ppo"
        # 1. Check for Manual Task Override
        # These are human-control and persistence paths, not game logic. Poll
        # them a few times per second instead of performing filesystem checks
        # and JSON reads for every emulator step.
        poll_controls = (
            self.steps_elapsed == 0
            or self.steps_elapsed % self.control_poll_interval == 0
        )
        if poll_controls:
            self._read_runtime_controls()
            self._apply_route_replan()
            if self.task_file.exists():
                try:
                    with open(self.task_file, 'r') as f:
                        content = f.read().strip().upper()
                    # `MISSION: STORY|FARM|AUTO` troca o modo de farm pela
                    # UX (o mesmo arquivo das ordens MANUAL). Só a linha da
                    # missão no arquivo não muda a tarefa atual.
                    mission = next((
                        line.split(":", 1)[1].strip()
                        for line in content.splitlines()
                        if line.startswith("MISSION:")
                    ), None)
                    if mission in ("STORY", "FARM", "AUTO"):
                        self.scripted_agent.mission_type = mission
                    task = next((
                        line for line in content.splitlines()
                        if line.startswith(("QUEST", "MANUAL", "STOP", "EXPLORE"))
                    ), None)
                    if task is None and not (
                        mission and all(
                            not line or line.startswith("MISSION:")
                            for line in content.splitlines()
                        )
                    ):
                        task = content
                    if task and task != self.current_task:
                        self.current_task = task
                        # Check if it's a natural language query (not standard command)
                        if not any(task.startswith(prefix) for prefix in ["QUEST", "MANUAL", "STOP", "EXPLORE"]):
                            try:
                                print(f"[{self.agent_name}] Unknown command '{task}'. Consulting Knowledge Base...")
                                results = self.knowledge_base.search(task)
                                if results:
                                    print(f"[{self.agent_name}] Knowledge found: {results[0]['content']}")
                                    # TODO: Use LLM to convert this knowledge into a QUEST or Action
                                else:
                                    print(f"[{self.agent_name}] No knowledge found.")
                            except Exception as e:
                                print(f"[{self.agent_name}] Error consulting Knowledge Base: {e}")
                except Exception:
                    pass

            # Check for AI-generated path (from dashboard "Ask AI" button)
            if self.ai_path_follower.check_for_new_path():
                objective = self.ai_path_follower.get_current_objective()
                print(f"[{self.agent_name}] 🤖✨ NEW AI PATH RECEIVED: {objective}")

            # External save state signal (e.g., before server restart)
            save_signal = Path('tasks/save_state_signal')
            if save_signal.exists():
                self._save_checkpoint(self.current_milestone)
                try:
                    save_signal.unlink()
                except Exception:
                    pass

        # Per-agent pause keeps the emulator and journey counters still. The
        # global pause is handled by SIGSTOP in the relay and freezes PPO too.
        if self.agent_paused:
            self._apply_playback_throttle(step_started_at)
            return self._get_obs(), 0.0, False, False, {
                "paused": True,
                "playback_speed": self.playback_speed,
                "policy_action": policy_action,
                "executed_action": NOOP_ACTION,
                "action_source": "pause",
                "trainable_transition": False,
            }

        # step_count belongs to the current PPO rollout; this counter belongs
        # to the real journey and therefore survives rollout resets.
        self.journey_total_steps += 1
        
        # 2. Determine Action Source
        # Priority: Battle > Scripted Quest > Manual/Stop > Smart Explore > RL Policy
        
        # Initialize reward early
        reward = 0
        
        # COMPETITIVE MODE: Delayed Start
        # If agent hasn't reached delay_steps yet, just WAIT
        if self.steps_elapsed < self.delay_steps and not self._trail_ready_to_inherit():
            self.steps_elapsed += 1
            if self.steps_elapsed == self.delay_steps:
                print(f"[{self.agent_name}] 🏁 RACE START! Joining the competition!")
                # Paid in full, and written down so the next chunk does not
                # charge it again.
                self.head_start_served = True
                self._persist_journey_memory()
            elif self.steps_elapsed % 600 == 0:
                # In steps, not seconds. Dividing by 60 assumed the bot runs at
                # frame rate; a decision costs far more than a frame — measured
                # at 3.7 a second with two slots — so "15s remaining" was really
                # four minutes, and the wait looked like a freeze.
                remaining = self.delay_steps - self.steps_elapsed
                print(f"[{self.agent_name}] ⏳ Waiting... {remaining} steps remaining")
            # Execute an explicit NOOP in the parent env.
            action = NOOP_ACTION
            obs, reward, done, truncated, info = super().step(action)
            info.update({
                "policy_action": policy_action,
                "executed_action": int(action),
                "action_source": "delayed_start",
                "trainable_transition": False,
            })
            self._apply_playback_throttle(step_started_at)
            return obs, 0, done, truncated, info  # No reward during wait
        
        # Increment step counter
        self.steps_elapsed += 1

        # Story progress is inferred from verified RAM predicates. A script
        # returning None means "wait", never "quest complete".
        if self.read_m(0xD057) == 0 and self.current_task.startswith("QUEST"):
            self._sync_quest_objective()
        
        # Check for Battle
        if self.read_m(0xD057) != 0:
            # Initialize battle identity and policy before sending the first
            # menu input. Otherwise the post-step tracker would clear the first
            # capture action and move the cursor twice.
            if not self.in_battle:
                self.battle_agent.reset_battle()
                self._track_battles_and_deaths()
            if not self.battle_mode_active:
                # print(f"[{self.agent_name}] Battle Started!")
                self.battle_mode_active = True
            # Use the real capture controller for eligible wild encounters;
            # otherwise fall back to the move-selection battle controller.
            # `MANUAL: THROW_BALL` is one order, not a stream of button
            # presses: the operator says "throw a ball at this one" and the
            # capture controller works the real menus, picking the ball by id
            # from the live bag. It overrides the policy's judgement — that is
            # the whole point of asking by hand — but never the cartridge's.
            self.capture_forced = (
                self.current_task.strip().upper() == MANUAL_THROW_BALL_TASK
            )
            battle_action_str = self._next_capture_action()
            if battle_action_str is None:
                # Sending someone out comes first: a fainted lead is not a
                # battle you may leave, it is a battle waiting on an answer.
                battle_action_str = self._next_switch_action()
                if battle_action_str is not None:
                    self.battle_action_mode = "switch"
            if battle_action_str is None:
                self.battle_action_mode = "attack"
                battle_action_str = self.battle_agent.get_action(self.emulator_adapter)
            self._log_battle_decision(battle_action_str)
            action = self._str_to_action(battle_action_str)
            action_source = (
                "capture_controller"
                if self.battle_action_mode == "capture"
                else "battle_controller"
            )
        else:
            if self.battle_mode_active:
                self.battle_mode_active = False

            # Check if Khalliss is dynamically enabled (can change without restart)
            khalliss_enabled = True
            
            # --- NAVIGATION SYSTEM UPDATE ---
            # 1. Record current position
            map_id = self.read_m(0xD35E)
            x, y = self.read_m(0xD362), self.read_m(0xD361)
            self.nav_system.record_visit(map_id, x, y)
            
            party_count = self.read_m(0xD163)
            
            # --- HIVE MIND: WARP DISCOVERY ---
            if self.last_map_id is not None and self.last_map_id != map_id:
                # Map changed! The previous position was a warp.
                self.hive_mind.register_warp(self.last_map_id, self.last_pos[0], self.last_pos[1], map_id)
            
            self.last_map_id = map_id
            self.last_pos = (x, y)
            # ---------------------------------
            
            # Legacy free-exploration helpers must never pre-empt an
            # executable story objective. Previously HiveMind re-enabled
            # exodus every frame in the bedroom, so QUEST: START never reached
            # ScriptedAgent and PPO wandered randomly instead.
            free_exploration = self.current_task == "EXPLORE"

            # 2. Check Saturation
            if free_exploration and self.nav_system.is_zone_saturated(map_id) and not self.exodus_mode:
                # Only trigger exodus if we haven't met objective
                self.exodus_mode = True
                # print(f"[{self.agent_name}] ⚠️ ZONE SATURATED ({map_id})! Activating EXODUS MODE -> Seeking Exit")
            
            # --- HIVE MIND: QUEST & STRATEGY ---
            # Build simple state for HiveMind
            hm_state = {
                "badges": bin(self.read_m(0xD356)).count('1'),
                "has_pokedex": self._capture_story_complete(),
                "items": [], # TODO: Read items from memory
                "map_id": map_id
            }
            
            active_quest = self.hive_mind.get_active_quest(hm_state) if free_exploration else None
            
            if active_quest:
                # Check if we are in the right zone
                target_zone_name = active_quest["zone"]
                target_zone = self.hive_mind.walkthrough["zones"].get(target_zone_name)
                
                if target_zone and map_id not in target_zone["map_ids"]:
                    # WRONG ZONE! Force Exodus to find way to target zone
                    if not self.exodus_mode:
                        # print(f"[{self.agent_name}] 🧭 QUEST: {active_quest['description']}")
                        # print(f"[{self.agent_name}] ⚠️ WRONG ZONE! In {map_id}, need {target_zone_name}. Seeking path...")
                        self.exodus_mode = True
                        
                        # Future: Use HiveMind to find specific warp to target zone
                        # warp = self.hive_mind.get_warp_to(map_id, target_zone["map_ids"])
                        # if warp: set navigation target to warp
                
                elif target_zone and map_id in target_zone["map_ids"]:
                    # RIGHT ZONE! Disable exodus, focus on objective
                    if self.exodus_mode:
                        # print(f"[{self.agent_name}] ✅ Arrived in {target_zone_name}! Resuming exploration.")
                        self.exodus_mode = False
            # -----------------------------------
            
            # 3. Exodus Mode Override (Updated)
            if free_exploration and self.exodus_mode:
                # Try to find a smart warp first using HiveMind
                # For now, just check if we have ANY known warp out of here
                target_x, target_y = self.nav_system.get_nearest_exit(map_id, x, y)
                
                # If HiveMind knows a warp that isn't hardcoded, use it!
                # (Future improvement: prioritize warps leading to quest target)
                
                if target_x is not None:
                    action_source = "navigation_controller"
                    # Simple heuristic navigation toward target
                    # Actions: 0=Down, 1=Left, 2=Right, 3=Up
                    if x < target_x: action = 2 # Right
                    elif x > target_x: action = 1 # Left
                    elif y < target_y: action = 0 # Down
                    elif y > target_y: action = 3 # Up
                    
                    # If close to exit, disable exodus (assume map change will happen)
                    if abs(x - target_x) + abs(y - target_y) < 2:
                        self.exodus_mode = False
                else:
                    self.exodus_mode = False # No known exit, disable
            # --------------------------------
            
            # Legacy Khalliss logic removed
            
            elif self.current_task == "STOP":
                action = NOOP_ACTION
                action_source = "stop"

            elif self.current_task == "COMPLETE":
                action = NOOP_ACTION
                action_source = "complete"
                
            elif self.current_task.startswith("MANUAL"):
                cmd = self.current_task.split(" ")[-1]
                if cmd.upper() == "THROW_BALL":
                    # Outside a battle there is nothing to throw at. Waiting
                    # keeps the order standing for the next encounter instead
                    # of turning it into a stray button press.
                    action = NOOP_ACTION
                    action_source = "manual_throw_ball_idle"
                else:
                    action = name_to_action(cmd)
                    action_source = "manual"
            
            elif self.current_task.startswith("QUEST"):
                action_source = "quest_controller"
                script_action = None
                forced_quest_action = False
                if (
                    self.current_task == "QUEST: START"
                    and self.read_m(0xD35E) == 37
                    and self.read_m(0xD362) == 3
                    and self.read_m(0xD361) >= 7
                ):
                    action = GameAction.DOWN
                    action_source = "opening_exit"
                    forced_quest_action = True
                elif (
                    self.current_task == "QUEST: START"
                    and self.read_m(0xD35E) == 40
                    and self.read_m(0xD163) == 0
                ):
                    if self.read_m(0xCFC4) == 1:
                        action = GameAction.A
                    else:
                        target_x = {0: 8, 1: 6, 2: 7}.get(
                            int(getattr(self, "starter_preference", 0)), 8
                        )
                        x, y = self.read_m(0xD362), self.read_m(0xD361)
                        if y < 4:
                            action = GameAction.DOWN
                        elif y > 4:
                            action = GameAction.UP
                        elif x < target_x:
                            action = GameAction.RIGHT
                        elif x > target_x:
                            action = GameAction.LEFT
                        elif not getattr(self, "opening_starter_faced", False):
                            self.opening_starter_faced = True
                            action = GameAction.UP
                        else:
                            action = GameAction.A
                    action_source = "opening_starter"
                    forced_quest_action = True
                # Delegate to ScriptedAgent
                try:
                    # Extract quest name (e.g., "QUEST: OAK_EVENT")
                    quest_name = self.current_task.split(":")[1].strip().lower()
                    supported = (
                        quest_name in self.scripted_agent.walkthrough.get("game_flow", {})
                        or hasattr(self.scripted_agent, f"_run_{quest_name}")
                    )
                    if not forced_quest_action:
                        script_action = (
                            self.scripted_agent.step(quest_name)
                            if supported
                            else None
                        )
                    
                    if script_action is not None:
                        # Convert PyBoy WindowEvent to RL Action
                        action = self._convert_llm_to_rl_action(script_action)
                    elif not forced_quest_action:
                        # A quest with no executor must wait, never fall back
                        # to PPO roaming and destroy the deterministic route.
                        action = NOOP_ACTION
                        
                except Exception as e:
                    print(f"[{self.agent_name}] Script Error: {e}")
                    action = NOOP_ACTION
        
            elif self.current_task == "EXPLORE":
                map_id = self.read_m(0xD35E)
                party_count = self.read_m(0xD163)
                
                # Special case: If in Oak's Lab (Map 40) with Pokemon, force to EXPLORE
                # This prevents getting stuck after choosing starter
                if map_id == 40 and party_count > 0:
                    # Agent has Pokemon but is still in lab - just explore to find exit
                    # print(f"[{self.agent_name}] In Oak's Lab with Pokemon, exploring to exit...")
                    pass  # Let RL handle it
                
                elif (map_id == 0 or map_id == 37 or map_id == 38) and party_count == 0:
                    action_source = "quest_controller"
                    # Auto-switch to Scripted Agent for Oak Event
                    # All agents use scripted logic for early game
                    self.current_task = "start"  # Use plain start task
                    script_action = self.scripted_agent.step("start")  # Invoke scripted agent
                    
                    if script_action is not None:
                        action = self._convert_llm_to_rl_action(script_action)
                    else:
                        # If scripted agent returns None, it means the script is done or stuck.
                        # We should probably revert to explore or pass.
                        action = NOOP_ACTION
                    # If we have a parcel (Item ID 70? Need to check) but haven't delivered it...
                    # For now, let's stick to the starter event as the main blocker.
                # else: # EXPLORE / RL Mode - action is already the RL policy's action
            
        # 3. Execute Action
        obs, reward, done, truncated, info = super().step(action)
        
        # 🚫 ANTI-BACKTRACKING: Penalizar revisita de tiles recentes
        map_id = self.read_m(0xD35E)
        x, y = self.read_m(0xD362), self.read_m(0xD361)
        current_tile = (map_id, x, y)
        
        # Check if this tile was visited in last 20 steps
        if current_tile in self.recent_tiles:
            backtrack_penalty = -5.0  # FORTE penalidade
            reward += backtrack_penalty
            # if self.steps_elapsed % 60 == 0:  # Debug ocasional
            #     print(f"[{self.agent_name}] 🔄 Backtracking penalty: {backtrack_penalty}")
        
        # Add to recent tiles
        self.recent_tiles.append(current_tile)
        
        # Repetition Penalty (Map Loops) - já existente
        if not self.recent_map_ids or self.recent_map_ids[-1] != map_id:
             self.recent_map_ids.append(map_id)
        
        if len(self.recent_map_ids) == 20 and len(set(self.recent_map_ids)) <= 2:
             reward -= 1.0
        
        # 4. Calculate Custom Rewards (Checklist + Pokedex)
        # 4. Add Custom Rewards (Story Progression)
        # reward += self._calculate_progress_reward()
        
        # 5. Directional Hint (Route 1 is UP)
        # If in Pallet Town (0) or Route 1 (12), encourage moving UP (Y decreasing)
        map_id = self.read_m(0xD35E)
        if map_id in [0, 12]: 
            y_pos = self.read_m(0xD361)
            # Max Y in Pallet is ~18. Route 1 is long.
            # Reward = (MaxY - CurrentY) * Scale
            # This creates a gradient pulling them North
            reward += (20 - y_pos) * 0.01 
        
        # 6. Track Battles, Deaths, and Party Changes
        self._track_battles_and_deaths()
        self._track_party_changes()
        self._persist_center_checkpoints()
        self._watch_for_stagnation()
        self._track_journey()
        
        # 7. Check and save progress checkpoints
        if self.step_count % 50 == 0:
            self._check_milestones()
        
        # 8. Update Agent State for Command Center at dashboard cadence. The
        # stream wrapper reads emulator state directly, so this JSON is for
        # persistence/API consumers and does not need per-step freshness.
        if self.step_count % self.state_update_interval == 0:
            self._update_agent_state()
        
        # 9. Periodic Save (Every 5 minutes)
        if time.time() - self.last_periodic_save_time > self.save_interval:
            self._periodic_save()
            self.last_periodic_save_time = time.time()
            
        # 10. Check for Manual Save Signal
        if poll_controls:
            signal_path = Path(__file__).parent / "save_signal.txt"
            if signal_path.exists():
                try:
                    with open(signal_path, "r") as f:
                        timestamp = float(f.read().strip())

                    if timestamp > self.last_manual_save_time:
                        print(f"[{self.agent_name}] 💾 Manual Save Triggered!")
                        self._manual_save(timestamp)
                        self.last_manual_save_time = timestamp
                except Exception:
                    pass # File might be being written to, skip this frame
            
        self._apply_playback_throttle(step_started_at)
        info["paused"] = False
        info["playback_speed"] = self.playback_speed
        info["policy_action"] = policy_action
        info["executed_action"] = int(action)
        info["action_source"] = action_source
        info["trainable_transition"] = action_source == "ppo"
        return obs, reward, done, truncated, info
    
    def get_party_info(self):
        """
        Extracts party info for visualization.
        Returns list of dicts: [{'species': 'BULBASAUR', 'level': 5, 'hp': 20, 'max_hp': 20}, ...]
        """
        party = []
        party_count = min(int(self.read_m(0xD163)), 6)
        
        if party_count == 0:
            return []
            
        # Pokemon Names (Simplified list for Gen 1 starters/common)
        # Full list would be too long here, using IDs or placeholder
        # For now, just returning ID
        
        for i in range(party_count):
            # Struct start: 0xD16B + (i * 44)
            struct_start = 0xD16B + (i * 44)
            
            species_id = self.read_m(struct_start + 0)
            current_hp = (self.read_m(struct_start + 1) << 8) + self.read_m(struct_start + 2)
            level = self.read_m(struct_start + 33)
            max_hp = (self.read_m(struct_start + 34) << 8) + self.read_m(struct_start + 35)
            
            # Import ID conversion
            try:
                from pokemon_ids import get_national_id
                national_id = get_national_id(species_id)
            except ImportError:
                national_id = species_id # Fallback

            # Party count is written before the full Pokémon struct during
            # starter/capture animations. Do not publish or classify that
            # transient zero-filled slot as a Pokémon.
            if not national_id or species_id in (0, 0xFF) or level <= 0:
                continue
            
            party.append({
                "species_id": national_id,  # Used by frontend for sprites (National Dex)
                "internal_id": species_id,  # Keep internal ID just in case
                "id": national_id,          # Legacy support
                "level": level,
                "hp": current_hp,
                "max_hp": max_hp,
                "moves": [
                    {
                        "id": self.read_m(struct_start + 8 + move_index),
                        "pp": self.read_m(struct_start + 29 + move_index) & 0x3F,
                    }
                    for move_index in range(4)
                    if self.read_m(struct_start + 8 + move_index) > 0
                ],
            })
            
        return party

    def _convert_llm_to_rl_action(self, action_str):
        """
        Convert PyBoy WindowEvent (used by ScriptedAgent) to RL action space index.
        """
        return event_to_action(action_str)
    
    
    def update_seen_coords(self):
        # if not in battle
        if self.read_m(0xD057) == 0:
            x_pos, y_pos, map_n = self.get_game_coords()
            coord_string = f"x:{x_pos} y:{y_pos} m:{map_n}"
            
            if coord_string not in self.seen_coords:
                # New tile locally!
                self.seen_coords[coord_string] = 1
                
                # Check global count and calculate decayed reward
                try:
                    with sqlite3.connect(self.shared_db_path, timeout=5) as conn:
                        cursor = conn.cursor()
                        # Upsert: Insert or increment
                        cursor.execute("INSERT OR IGNORE INTO tiles (id, count) VALUES (?, 0)", (coord_string,))
                        cursor.execute("UPDATE tiles SET count = count + 1 WHERE id = ?", (coord_string,))
                        conn.commit()
                        
                        # Get current count
                        cursor.execute("SELECT count, is_golden FROM tiles WHERE id = ?", (coord_string,))
                        row = cursor.fetchone()
                        global_count = row[0] if row else 1
                        is_golden = row[1] if row and len(row) > 1 else 0
                        
                        # Calculate reward: Base 1.0 / (2^(count-1))
                        decay_factor = 0.5 ** (global_count - 1)
                        reward = 1.0 * decay_factor
                        
                        # Apply Golden Multiplier
                        if is_golden:
                            reward *= 3.0
                            if global_count == 1:
                                print(f"[{self.agent_name}] 🌟 GOLDEN TILE DISCOVERED! 3x Reward: +{reward:.2f}")
                        
                        self.exploration_reward_accumulator += reward
                        
                        if global_count == 1 and not is_golden:
                             print(f"[{self.agent_name}] 🌍 FIRST DISCOVERY: {coord_string} (+{reward:.2f})")
                             
                except Exception as e:
                    # Fallback if DB fails
                    self.exploration_reward_accumulator += 0.1
            else:
                self.seen_coords[coord_string] += 1

    # def get_game_state_reward(self, print_stats=False):
    #     # Call parent to get base rewards
    #     state_scores = super().get_game_state_reward(print_stats)
        
    #     # Override 'explore' with our shared accumulator
    #     badge_count = self.get_badges()
    #     party_count = self.read_m(0xD163)
        
    #     if party_count == 0:
    #         explore_mult = 3.0
    #     elif badge_count == 0:
    #         explore_mult = 2.5
    #     else:
    #         explore_mult = 1.5
            
    #     # Replace 'explore' score with decayed shared reward
    #     state_scores["explore"] = self.reward_scale * self.explore_weight * self.exploration_reward_accumulator * explore_mult
        
    #     return state_scores

    def _calculate_progress_reward(self):
        """
        Calculate rewards based on Story Events (Checklist) and Pokedex.
        Uses Curriculum Learning: Multipliers change based on game progress.
        """
        reward = 0.0
        # Count set bits in event flags range (0xD747 - 0xD7F6)
        current_event_count = 0
        for addr in range(0xD747, 0xD7F7):
            val = self.read_m(addr)
            current_event_count += bin(val).count('1')
            
        pokedex_count = self._pokedex_owned_count()
        
        # Badges (0xD356)
        badges_val = self.read_m(0xD356)
        badge_count = bin(badges_val).count('1')
        
        # Party Count
        party_count = self.read_m(0xD163)
        
        # Check current map
        map_id = self.read_m(0xD35E)
        
        # --- Curriculum Learning Multipliers ---
        # Phase 1: Early Game (No Pokemon) - Focus on Events (Oak) & Exploration
        if party_count == 0:
            explore_mult = 3.0
            event_mult = 100.0
            badge_mult = 1.0 # Irrelevant yet
        # Phase 2: Pre-Brock (0 Badges) - Balanced
        elif badge_count == 0:
            explore_mult = 2.5
            event_mult = 60.0
            badge_mult = 200.0 # Big reward for first badge
        # Phase 3: Post-Brock - Progression Focus
        else:
            explore_mult = 1.5
            event_mult = 50.0
            badge_mult = 300.0 # Increasing value for later badges

        # Personality-specific reward shaping. These multipliers are bounded
        # so personality changes preference without making one profile
        # impossible to train alongside another.
        explore_mult *= 0.60 + (self.exploration / 100.0) * 0.80
        event_mult *= 0.60 + (self.mission_focus / 100.0) * 0.80
        badge_mult *= 0.70 + (self.mission_focus / 100.0) * 0.60
            
        # reward already initialized earlier for Khalliss compatibility
        
        # 0. LEAVING PALLET TOWN - MASSIVE ONE-TIME REWARD!
        if not self.left_pallet_town and map_id not in [0, 37, 38]:
            reward += 200.0 * explore_mult
            print(f"[{self.agent_name}] 🎉 LEFT PALLET TOWN! +{200.0 * explore_mult}")
            self.left_pallet_town = True
        
        # 0.5. NEW MAP DISCOVERED
        if map_id not in self.visited_maps:
            r = 50.0 * explore_mult
            reward += r
            print(f"[{self.agent_name}] 🗺️  NEW MAP {map_id}! +{r}")
            self.visited_maps.add(map_id)
            
        # 0.8. PARCEL DELIVERED / POKEDEX OBTAINED
        has_pokedex = self._capture_story_complete()
        if has_pokedex and not self.got_pokedex_reward:
             reward += 2000.0  # Massive reward for getting Pokedex
             print(f"[{self.agent_name}] 📦 PARCEL DELIVERED! POKEDEX OBTAINED! +2000.0")
             self.got_pokedex_reward = True
        
        # 1. Story Events (Checklist)
        if current_event_count > self.last_event_count:
            diff = current_event_count - self.last_event_count
            r = diff * event_mult
            reward += r
            print(f"[{self.agent_name}] Event! +{r}")
            self.last_event_count = current_event_count
        
        # 1.2. STARTER CHOICE - PUNISHMENT/REWARD SYSTEM
        # Punish easy mode (Bulbasaur), reward hard mode (Charmander)
        party_count = self.read_m(0xD163)
        if party_count > 0 and not self.starter_choice_applied:
            party = self.get_party_info()
            if party and len(party) > 0:
                first_pokemon_id = party[0].get('species_id', 0)
                
                # Bulbasaur = 153, Charmander = 176, Squirtle = 177
                if first_pokemon_id == 153:  # Bulbasaur
                    punishment = -5000.0  # MASSIVE punishment to force diversity!
                    reward += punishment
                    print(f"[{self.agent_name}] ❌❌❌ BULBASAUR CHOSEN (Easy Mode)! MASSIVE Punishment: {punishment}")
                    self.starter_choice_applied = True
                elif first_pokemon_id == 176:  # Charmander
                    bonus = 1000.0  # Increased bonus for hard mode
                    reward += bonus
                    print(f"[{self.agent_name}] 🔥🔥🔥 CHARMANDER CHOSEN (Hard Mode)! BIG Bonus: +{bonus}")
                    self.starter_choice_applied = True
                elif first_pokemon_id == 177:  # Squirtle
                    bonus = 200.0  # Small bonus for balanced choice
                    reward += bonus
                    print(f"[{self.agent_name}] 💧 SQUIRTLE CHOSEN (Balanced)! Bonus: +{bonus}")
                    self.starter_choice_applied = True
        
        # 1.5. PARCEL DELIVERY - CRITICAL MISSION REWARD!
        # This is hard because agent needs to go to Viridian, get parcel, and RETURN to Pallet
        # Oak's Pokédex flag is set only after the parcel return sequence.
        has_pokedex = self._capture_story_complete()
        if has_pokedex and not self.delivered_parcel:
            parcel_reward = 300.0 * event_mult  # Huge reward for completing this round trip
            reward += parcel_reward
            print(f"[{self.agent_name}] 📦 DELIVERED OAK'S PARCEL! GOT POKEDEX! +{parcel_reward}")
            self.delivered_parcel = True
            # self._log_event("parcel", {"reward": parcel_reward})  # Disabled for cleaner feed
            
        # 2. Pokedex (Proporcional)
        # Use party count as fallback if pokedex not obtained yet
        display_count = pokedex_count if has_pokedex else party_count
        
        if pokedex_count > self.last_pokedex_count:
            diff = pokedex_count - self.last_pokedex_count
            capture_mult = 0.60 + (self.collector / 100.0) * 0.80
            r = diff * 30.0 * (1 + (pokedex_count * 0.1)) * capture_mult
            reward += r
            print(f"[{self.agent_name}] Caught Pokemon! +{r}")
            self.last_pokedex_count = pokedex_count
            # Confirmation is emitted by _track_party_changes with the actual
            # Pokémon and the policy reason; do not duplicate it here.
            
        # 3. New Badge
        if badge_count > self.last_badges:
            r = badge_mult
            reward += r
            print(f"[{self.agent_name}] 🏆 BADGE GET! +{r}")
            self.last_badges = badge_count
            self._log_event("badge", {"count": badge_count})
        
        # 3.5. BOULDER BADGE (BROCK) - MEGA REWARD!
        has_boulder_badge = (self.read_m(0xD356) & 0b00000001) != 0
        if has_boulder_badge and not self.defeated_brock:
            boulder_reward = 500.0 * (explore_mult) # Scale with phase
            
            # HARD MODE BONUS: AARON with Charmander gets MASSIVE extra reward
            # Charmander is weak to Rock types (Brock's specialty)
            if self.hard_mode_bonus:
                hard_mode_extra = 1000.0  # HUGE bonus for overcoming type disadvantage!
                boulder_reward += hard_mode_extra
                print(f"[{self.agent_name}] 🔥🔥🔥 HARD MODE VICTORY! Defeated Brock with type disadvantage! +{hard_mode_extra}")
            
            # BONUS: Check if team is strong
            party = self.get_party_info()
            if party:
                avg_level = sum(p['level'] for p in party) / len(party)
                if avg_level >= 12:
                    boulder_reward += 200.0
                    print(f"[{self.agent_name}] 💪 STRONG TEAM BONUS! Avg Level: {avg_level:.1f}")
            
            reward += boulder_reward
            print(f"[{self.agent_name}] ⭐ DEFEATED BROCK! BOULDER BADGE! +{boulder_reward}")
            self.defeated_brock = True
            # self._log_event("brock", {"reward": boulder_reward})  # Disabled for cleaner feed
        
        # 4. PENALIDADE POR INATIVIDADE
        # Detectar se o agente está parado sem estar em batalha ou diálogo
        current_pos = (self.read_m(0xD362), self.read_m(0xD361))
        in_battle = self.read_m(0xD057) != 0
        
        # Track position history
        if not hasattr(self, 'position_history'):
            self.position_history = []
            self.stuck_penalty_applied = 0
        
        self.position_history.append(current_pos)
        if len(self.position_history) > 60:  # Track last 60 frames (~2 seconds)
            self.position_history.pop(0)
        
        # Check if stuck (same position for 60 frames and not in battle)
        if len(self.position_history) >= 60:
            unique_positions = len(set(self.position_history))
            
            if unique_positions == 1 and not in_battle:
                # Agent is stuck! Apply penalty
                stuck_penalty = -0.5  # Small penalty per step stuck
                reward += stuck_penalty
                self.stuck_penalty_applied += 1
                
                # Log every 120 stuck frames
                if self.stuck_penalty_applied % 120 == 0:
                    print(f"[{self.agent_name}] ⚠️ STUCK at {current_pos}! Penalty: {stuck_penalty * 120}")
                    
                    # Extra diagnostic for CARON and HARON
                    if self.agent_name in ["CARON", "HARON"]:
                        map_id = self.read_m(0xD35E)
                        party_count = self.read_m(0xD163)
                        print(f"[{self.agent_name}] 🔍 DEBUG: Task={self.current_task}, Map={map_id}, Party={party_count}")
                        if hasattr(self.scripted_agent, 'current_task_name'):
                            print(f"[{self.agent_name}] 🔍 ScriptedAgent Task: {self.scripted_agent.current_task_name}")
                        if hasattr(self.scripted_agent, 'starter_state'):
                            print(f"[{self.agent_name}] 🔍 Starter State: {self.scripted_agent.starter_state}")
            else:
                # Agent is moving, reset counter
                if self.stuck_penalty_applied > 0:
                    print(f"[{self.agent_name}] ✅ Unstuck! Stopped penalties.")
                self.stuck_penalty_applied = 0
            
        return reward

    def _update_agent_state(self):
        """
        Write agent state (party, pokedex, badges) to shared JSON file for Command Center.
        """
        import json

        state_file = Path(__file__).parent / "tasks/agent_states.json"
        state_file.parent.mkdir(exist_ok=True)
        
        # Read current state
        all_states = {}
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    all_states = json.load(f)
            except:
                all_states = {}
        
        # Update this agent's state
        all_states[self.agent_name] = {
            "party": self.get_party_info(),
            "pokedex_seen": self._pokedex_seen_count(),
            "pokedex_owned": self._pokedex_owned_count(),
            "badges": bin(self.read_m(0xD356)).count('1'),  # Badge count
            "map_id": self.read_m(0xD35E),  # Current map ID
            "step_count": self.journey_total_steps,
            "battle_info": self._get_battle_info(),
            "recent_events": self.recent_events,
            "journey": self.get_journey_snapshot(),
            "decision_log": str(self.decision_log_path),
            "updated_at": time.time(),
        }

        # Retired trainers used to sit in the panel forever: BARON and CARON
        # were still shown frozen inside a house long after the roster had
        # moved on to other names. Nobody rewrites their entry, so nobody would
        # ever remove it either. A stale entry is one that stopped being
        # written, which is exactly what the timestamp measures.
        now = time.time()
        all_states = {
            name: state for name, state in all_states.items()
            if name == self.agent_name
            or now - float(state.get("updated_at") or now) < STALE_AGENT_SECONDS
        }

        # Write back atomically. The previous version used fcntl, which does
        # not exist on Windows and crashed the run there on the first state
        # update. Writing to a temporary file and replacing it is portable and
        # also removes the torn-read window a reader could hit mid-write.
        try:
            temporary = state_file.with_suffix(".json.tmp")
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump(all_states, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, state_file)
        except OSError:
            pass

    def _load_journey_memory(self):
        """Restore durable first-visit/story markers for this trainer."""
        try:
            with open(self.journey_memory_path, "r", encoding="utf-8") as memory_file:
                memory = json.load(memory_file)
            self.visited_major_locations.update(
                int(map_id) for map_id in memory.get("major_locations", [])
            )
            self.announced_story_milestones.update(
                str(milestone) for milestone in memory.get("story_milestones", [])
            )
            self.quest_completed_ids.update(
                str(quest_id) for quest_id in memory.get("completed_quests", [])
                if str(quest_id) in self.quest_graph.nodes_by_id
            )
            # A journey written before generations existed carries no proof that
            # any checkpoint contains these quests. Leaving them unstamped is
            # the conservative reading: they face the RAM again on the next
            # load, and only what the cartridge still confirms survives.
            self.quest_generations.update({
                str(quest_id): int(generation)
                for quest_id, generation in (
                    memory.get("quest_generations") or {}
                ).items()
                if str(quest_id) in self.quest_graph.nodes_by_id
            })
            if memory.get("head_start_served"):
                self.head_start_served = True
                self.delay_steps = 0
            # Última geração selada do journey: sem manifesto (Centro órfão),
            # é o melhor sinal de até onde o save chegou. Zerá-la reabria
            # quests que a RAM ainda prova (medido: FARON voltou ao
            # buy_pokeballs com a mochila gasta e quicou entre Pewter e a
            # Rota 2 indo comprar em Viridian).
            self.journey_checkpoint_generation = int(
                memory.get("checkpoint_generation", 0) or 0
            )
            # Deaths outlive the process. A chunk is a fresh env with the
            # counter back at zero, so without this every whiteout logged
            # itself as cycle 1 and "attempt 1 versus attempt 2" — the whole
            # point of numbering them — was never measurable.
            self.death_cycle = int(memory.get("death_cycle", 0))
            if "viridian_center_healed" not in self.announced_story_milestones:
                try:
                    with open(self.decision_log_path, "r", encoding="utf-8") as log_file:
                        for line in log_file:
                            event = json.loads(line)
                            data = event.get("data") or {}
                            if (
                                event.get("type") == "healed"
                                and data.get("source") == "pokemon_center"
                                and int(data.get("map_id", -1)) == 41
                            ):
                                self.announced_story_milestones.add(
                                    "viridian_center_healed"
                                )
                                break
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    pass
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    def _persist_journey_memory(self):
        """Persist only compact semantic memory, never emulator frames."""
        try:
            self.journey_memory_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.journey_memory_path.with_suffix(".tmp")
            with open(temporary, "w", encoding="utf-8") as memory_file:
                json.dump({
                    "major_locations": sorted(self.visited_major_locations),
                    "story_milestones": sorted(self.announced_story_milestones),
                    "completed_quests": [
                        node.id for node in self.quest_graph.nodes
                        if node.id in self.quest_completed_ids
                    ],
                    # Which checkpoint generation was running when each quest
                    # was observed. Read back on resume to tell a completion the
                    # saved state contains from one it does not.
                    "quest_generations": {
                        node.id: int(self.quest_generations[node.id])
                        for node in self.quest_graph.nodes
                        if node.id in self.quest_generations
                    },
                    "checkpoint_generation": int(
                        getattr(self, "checkpoint_generation", 0)
                    ),
                    "head_start_served": bool(
                        getattr(self, "head_start_served", False)
                    ),
                    "death_cycle": int(getattr(self, "death_cycle", 0)),
                }, memory_file, ensure_ascii=False, indent=2)
            os.replace(temporary, self.journey_memory_path)
        except OSError:
            pass

    def _pokedex_count(self, start_address):
        """Count Gen I Pokédex bit flags instead of treating one byte as a count."""
        try:
            total = sum(
                int(self.read_m(start_address + offset)).bit_count()
                for offset in range(POKEDEX_BYTES - 1)
            )
            # The final byte has seven valid species bits (145-151).
            total += (int(self.read_m(start_address + POKEDEX_BYTES - 1)) & 0x7F).bit_count()
            return total
        except Exception:
            return 0

    def _pokedex_owned_count(self):
        return self._pokedex_count(POKEDEX_OWNED_START)

    def _pokedex_seen_count(self):
        return self._pokedex_count(POKEDEX_SEEN_START)

    def _badge_count(self):
        try:
            return bin(int(self.read_m(0xD356))).count("1")
        except Exception:
            return 0

    def _owned_species(self):
        """Every species id registered as owned in the Pokédex."""
        return {
            national_id for national_id in range(1, 152)
            if self._pokedex_owns(national_id)
        }

    def _area_coverage(self):
        """How much of the current area is registered, or None if it has none."""
        try:
            return area_coverage(
                self._map_name(), self._owned_species(), self._badge_count()
            )
        except Exception:
            return None

    def _pokedex_owns(self, national_id):
        try:
            national_id = int(national_id)
            if not 1 <= national_id <= 151:
                return False
            bit_index = national_id - 1
            value = int(self.read_m(POKEDEX_OWNED_START + bit_index // 8))
            return bool(value & (1 << (bit_index % 8)))
        except Exception:
            return False

    def _capture_story_complete(self):
        """Return true only after Oak grants the real Pokédex story flag.

        0xD74E bit 1 means that the player picked up Oak's Parcel in Viridian;
        it is intentionally not enough. EVENT_GOT_POKEDEX is 0xD74B bit 5 and
        is set after returning the parcel and completing Oak's request.
        """
        try:
            return bool(int(self.read_m(GOT_POKEDEX_ADDRESS)) & GOT_POKEDEX_MASK)
        except Exception:
            return False

    def _capture_ball_inventory(self):
        return [
            item for item in self._read_bag_items()
            if item["item_id"] in CAPTURE_BALL_IDS
        ]

    def _ball_inventory_by_kind(self):
        """Balls in the bag, by kind, for the panel.

        A single total hides the decision: a run with one Master Ball and a run
        with one Poké Ball are not in the same situation, and the capture policy
        already spends them in different orders.
        """
        names = {1: "master", 2: "ultra", 3: "great", 4: "poke"}
        counts = {name: 0 for name in names.values()}
        for item in self._capture_ball_inventory():
            kind = names.get(int(item["item_id"]))
            if kind:
                counts[kind] += int(item.get("quantity") or 0)
        counts["total"] = sum(
            value for key, value in counts.items() if key != "total"
        )
        return counts

    def _select_capture_ball(self, shiny_candidate=False):
        inventory = self._capture_ball_inventory()
        priority = (1, 2, 3, 4) if shiny_candidate else (4, 3, 2, 1)
        return next(
            (item for item_id in priority for item in inventory if item["item_id"] == item_id),
            None,
        )

    def _battle_menu_step_to_item(self):
        """One step toward ITEM, decided by what is on screen right now."""
        return self._battle_menu_step(BATTLE_MENU_ITEM_ROW, BATTLE_MENU_LEFT_COLUMN)

    def _enemy_shiny_info(self):
        """Detect the Gen II shiny-compatible DV pattern in a Gen I encounter.

        Red/Blue has no visible shiny palette. A captured Pokémon with this DV
        pattern becomes shiny when transferred to Gen II, so it is the only
        faithful shiny signal available in the real Blue ROM.
        """
        try:
            attack_defense = int(self.read_m(0xCFF1))
            speed_special = int(self.read_m(0xCFF2))
            dvs = {
                "attack": attack_defense >> 4,
                "defense": attack_defense & 0x0F,
                "speed": speed_special >> 4,
                "special": speed_special & 0x0F,
            }
            shiny = (
                dvs["defense"] == 10
                and dvs["speed"] == 10
                and dvs["special"] == 10
                and dvs["attack"] in {2, 3, 6, 7, 10, 11, 14, 15}
            )
            return {"shiny_candidate": shiny, "dvs": dvs}
        except Exception:
            return {"shiny_candidate": False, "dvs": None}

    def _capture_quality(self, battle_info):
        party = self.get_party_info()
        enemy_level = int(battle_info.get("enemy_level") or 0)
        species_id = int(battle_info.get("enemy_species_id") or 0)
        levels = [int(mon.get("level") or 0) for mon in party if mon.get("level")]
        weakest_level = min(levels, default=0)
        strongest_level = max(levels, default=0)
        strategic_value = STRATEGIC_CAPTURE_VALUE.get(species_id, 50)
        new_species = not self._pokedex_owns(species_id)
        level_advantage = enemy_level - weakest_level if levels else enemy_level
        upgrade_candidate = bool(party) and (
            level_advantage >= 3
            or (new_species and strategic_value >= 75)
            or enemy_level > strongest_level
        )
        # Gen I catch rates scale with missing HP. Throwing at a full-health
        # target mostly fails, and each failed throw is a free turn for the
        # wild Pokémon — a bot did that until its own starter was at 2 HP.
        enemy_max_hp = int(battle_info.get("enemy_max_hp") or 0)
        enemy_hp = int(battle_info.get("enemy_hp") or 0)
        enemy_hp_fraction = (enemy_hp / enemy_max_hp) if enemy_max_hp else 1.0

        active = battle_info.get("active_pokemon") or {}
        own_max_hp = int(active.get("max_hp") or 0)
        own_hp = int(active.get("hp") or 0)
        own_hp_fraction = (own_hp / own_max_hp) if own_max_hp else 1.0

        # "Soften first" assumes a hit leaves the target alive. Against a wild
        # Pokémon far below the active's level it is a knockout, so the ball is
        # never thrown at all: two trainers walked from Pewter to Mt. Moon with
        # a single Pokémon and `soften_before_capture` on every encounter. When
        # the hit would end the battle, a throw at full health — poor odds and
        # all — is the only throw that will ever happen.
        active_level = int(active.get("level") or 0)

        # Two ways "soften first" becomes a trap. A status condition already
        # multiplies the catch rate, so waiting to chip HP afterwards is
        # backwards. And with no damaging PP left the HP will simply never
        # drop: a bot spent a night throwing Sleep Powder at a Metapod with
        # seven Poké Balls in the bag, because the rule kept saying "later".
        enemy_impaired = int(battle_info.get("enemy_status") or 0) != 0
        has_damage_left = self._has_damaging_pp(active)
        overkill_risk = bool(enemy_level) and active_level >= max(
            enemy_level + OVERKILL_LEVEL_GAP, int(enemy_level * OVERKILL_LEVEL_RATIO)
        )

        # An empty bench is itself a weakness. Judging every wild encounter only
        # by level made a single strong starter reject everything in the early
        # routes, so the team never grew past one Pokémon.
        party_size = len(party)
        party_species = {
            int(mon.get("species_id") or 0) for mon in party
        }
        return {
            "new_species": new_species,
            "upgrade_candidate": upgrade_candidate,
            "strategic_value": strategic_value,
            "enemy_level": enemy_level,
            "weakest_party_level": weakest_level,
            "strongest_party_level": strongest_level,
            "level_advantage": level_advantage,
            "party_size": party_size,
            "party_has_room": party_size < PARTY_TARGET,
            "party_slots_free": max(PARTY_TARGET - party_size, 0),
            "already_in_party": species_id in party_species,
            "enemy_hp_fraction": round(enemy_hp_fraction, 3),
            "own_hp_fraction": round(own_hp_fraction, 3),
            "active_level": active_level,
            "overkill_risk": overkill_risk,
            "enemy_impaired": enemy_impaired,
            "has_damage_left": has_damage_left,
        }

    def get_journey_snapshot(self):
        """Return a compact, real-emulator progress snapshot for UI/API use."""
        try:
            map_id = int(self.read_m(0xD35E))
            coords = [int(self.read_m(0xD362)), int(self.read_m(0xD361))]
            badges = int(bin(self.read_m(0xD356)).count("1"))
        except Exception:
            map_id = None
            coords = None
            badges = 0
        try:
            quest_state = LiveQuestState(self)
            completed_quests = self.quest_graph.completed_nodes(
                quest_state, self.quest_completed_ids
            )
        except Exception:
            completed_quests = []
        active_quest = self.quest_graph.nodes_by_id.get(self.active_quest_id)
        return {
            "steps": self.journey_total_steps,
            "map_id": map_id,
            "map_name": self._map_name(map_id),
            "coords": coords,
            "badges": badges,
            "task": getattr(self, "current_task", ""),
            "milestone": getattr(self, "current_milestone", "start"),
            "archetype": getattr(self, "archetype", DEFAULT_ARCHETYPE),
            "archetype_label": get_archetype(getattr(self, "archetype", None))["label"],
            "archetype_summary": get_archetype(getattr(self, "archetype", None))["summary"],
            "capture_stance": getattr(self, "capture_stance", None),
            "balls": self._ball_inventory_by_kind(),
            # The panel had no way to tell one trainer from another beyond the
            # name. The traits are what explain every capture decision below.
            "traits": {
                "meta_score": self.meta_score,
                "exploration": self.exploration,
                "collector": self.collector,
                "mission_focus": self.mission_focus,
            },
            "battles": self.wild_battles_won + self.trainer_battles_won,
            "wild_battles_won": self.wild_battles_won,
            "trainer_battles_won": self.trainer_battles_won,
            "captures": self.capture_count,
            "level_ups": self.level_up_count,
            "evolutions": self.evolution_count,
            "deaths": self.deaths,
            "decision_count": self.battle_decision_count,
            "pokeballs": self._poke_ball_count(),
            "capture_story_complete": self._capture_story_complete(),
            "capture_unlocked": self._capture_story_complete() and self._poke_ball_count() > 0,
            "quest_graph": {
                "active_id": self.active_quest_id,
                "active_title": active_quest.title if active_quest else None,
                "completed": completed_quests,
                "total": len(self.quest_graph.nodes),
                "run_complete": self.run_complete,
            },
            "decision_log": str(self.decision_log_path),
        }

    def _track_journey(self):
        """Persist raw transitions and publish only first visits/story beats."""
        try:
            map_id = int(self.read_m(0xD35E))
            task = getattr(self, "current_task", "")
            if self.last_logged_map_id is None:
                self.last_logged_map_id = map_id
            elif map_id != self.last_logged_map_id:
                previous_map = self.last_logged_map_id
                self.last_logged_map_id = map_id
                self._log_event("map_transition", {
                    "from_map_id": previous_map,
                    "from_map_name": self._map_name(previous_map),
                    "to_map_id": map_id,
                    "to_map_name": self._map_name(map_id),
                    "reason": "transição detectada na RAM do emulador",
                }, live=False)

            if map_id in MAJOR_LOCATION_IDS and map_id not in self.visited_major_locations:
                self.visited_major_locations.add(map_id)
                self._persist_journey_memory()
                self._log_event("location_discovered", {
                    "location_id": map_id,
                    "location_name": self._map_name(map_id),
                    "first_visit": True,
                    "reason": "primeira chegada desta jornada confirmada pelo mapa real",
                })

            story_complete = self._capture_story_complete()
            balls = self._poke_ball_count()
            if story_complete and "parcel_delivered" not in self.announced_story_milestones:
                self.announced_story_milestones.add("parcel_delivered")
                self._persist_journey_memory()
                self._log_event("story_milestone", {
                    "milestone": "parcel_delivered",
                    "title": "Encomenda entregue ao Professor Oak",
                    "reason": "Pokédex recebido; a compra e o uso de Poké Balls foram liberados",
                    "capture_unlocked": balls > 0,
                    "pokeballs": balls,
                })

            if (
                story_complete
                and balls > 0
                and "capture_unlocked" not in self.announced_story_milestones
            ):
                self.announced_story_milestones.add("capture_unlocked")
                self._persist_journey_memory()
                self._log_event("story_milestone", {
                    "milestone": "capture_unlocked",
                    "title": "Capturas liberadas",
                    "reason": "missão inicial concluída e Poké Balls confirmadas no inventário",
                    "capture_unlocked": True,
                    "pokeballs": balls,
                })

            badge_flags = int(self.read_m(0xD356))
            for badge_index in range(8):
                milestone = f"badge_{badge_index + 1}"
                if (
                    badge_flags & (1 << badge_index)
                    and milestone not in self.announced_story_milestones
                ):
                    self.announced_story_milestones.add(milestone)
                    self._persist_journey_memory()
                    self._log_event("badge", {
                        "count": badge_flags.bit_count(),
                        "badge_index": badge_index + 1,
                        "reason": "insígnia confirmada diretamente pelos bits de progresso da RAM",
                    })

            if self.last_logged_task is None:
                self.last_logged_task = task
            elif task != self.last_logged_task:
                previous_task = self.last_logged_task
                self.last_logged_task = task
                self._log_event("objective_changed", {
                    "from": previous_task,
                    "to": task,
                    "reason": "controlador mudou o objetivo da jornada",
                })
        except Exception as exc:
            self._log_event("telemetry_error", {
                "source": "journey_tracking",
                "error": str(exc),
            }, live=False)

    def _classify_encounter(self, battle_status, map_name):
        """Give the real battle a short, human-readable Arena category."""
        trainer_battle = (int(battle_status) & 0b10) != 0
        location = (map_name or "").lower()

        if not trainer_battle:
            if "safari" in location:
                return "wild_safari", "Encontro no Safari", "Pokémon selvagem"
            if any(word in location for word in ("cave", "mt moon", "rock tunnel")):
                return "wild_cave", "Encontro em caverna", "Pokémon selvagem"
            if "sea route" in location:
                return "wild_water", "Encontro aquático", "Pokémon selvagem"
            if "pokemon tower" in location:
                return "wild_special", "Encontro sobrenatural", "Pokémon selvagem"
            if "forest" in location or "route" in location:
                return "wild_grass", "Encontro no mato", "Pokémon selvagem"
            return "wild", "Encontro selvagem", "Pokémon selvagem"

        if "gym" in location:
            return "gym", "Desafio de ginásio", "Treinador"

        league_locations = (
            "indigo plateau", "loreleis room", "brunos room",
            "agathas room", "lances room", "champions room",
        )
        if any(place in location for place in league_locations):
            return "league", "Liga Pokémon", "Treinador de elite"

        story_locations = (
            "silph co", "rocket hideout", "rocket game corner",
            "ss anne", "pokemon tower",
        )
        if any(place in location for place in story_locations):
            return "story", "Duelo da jornada", "Treinador importante"
        if "forest" in location:
            return "trainer_forest", "Treinador da floresta", "Treinador"
        if "route" in location:
            return "trainer_route", "Treinador de rota", "Treinador"
        return "trainer", "Duelo de treinador", "Treinador"

    def _get_battle_info(self):
        """
        Extract basic battle info if in battle.
        """
        battle_status = int(self.read_m(0xD057))
        if battle_status == 0:
            return None
            
        # Enemy Species (0xCFE5)
        enemy_id = self.read_m(0xCFE5)
        # Enemy Level (0xCFF3)
        enemy_level = self.read_m(0xCFF3)
        # Enemy HP (0xCFE6, 2 bytes)
        enemy_hp = (self.read_m(0xCFE6) << 8) + self.read_m(0xCFE7)
        # Sleep, freeze, paralysis: in Gen I a status condition is the real
        # setup for a capture, worth more than chipping HP.
        enemy_status = int(self.read_m(0xCFE9))
        # Max HP follows the enemy level at 0xCFF3.
        enemy_max_hp = (self.read_m(0xCFF4) << 8) + self.read_m(0xCFF5)
        active_internal_id = self.read_m(0xD014)
        if active_internal_id in (0, 0xFF):
            active_internal_id = self.read_m(0xD16B)
        try:
            from pokemon_ids import get_national_id
            active_species_id = get_national_id(active_internal_id)
            enemy_species_id = get_national_id(enemy_id)
        except ImportError:
            active_species_id = active_internal_id
            enemy_species_id = enemy_id

        enemy_species_id = enemy_species_id or enemy_id
        map_id = int(self.read_m(0xD35E))
        map_name = self._map_name(map_id)
        encounter_type, encounter_label, encounter_group = self._classify_encounter(
            battle_status,
            map_name,
        )
        shiny_info = self._enemy_shiny_info()

        active_pokemon = {
            "species_id": active_species_id,
            "internal_id": active_internal_id,
            "level": self.read_m(0xD022),
            "hp": (self.read_m(0xD015) << 8) + self.read_m(0xD016),
            "max_hp": (self.read_m(0xD023) << 8) + self.read_m(0xD024),
            "moves": [
                {
                    "id": self.read_m(0xD01C + move_index),
                    "pp": self.read_m(0xD02D + move_index) & 0x3F,
                }
                for move_index in range(4)
                if self.read_m(0xD01C + move_index) > 0
            ],
            "selected_move_slot": getattr(self.battle_agent, "move_selection", 0),
        }
        
        return {
            "is_battle": True,
            "enemy_id": enemy_id,
            "enemy_internal_id": enemy_id,
            "enemy_species_id": enemy_species_id,
            "enemy_level": enemy_level,
            "enemy_hp": enemy_hp,
            "enemy_max_hp": enemy_max_hp,
            "enemy_status": enemy_status,
            "active_pokemon": active_pokemon,
            "battle_status": battle_status,
            "is_trainer": (battle_status & 0b10) != 0,
            "encounter_type": encounter_type,
            "encounter_label": encounter_label,
            "encounter_group": encounter_group,
            "shiny_candidate": shiny_info["shiny_candidate"],
            "dvs": shiny_info["dvs"],
            "shiny_note": (
                "DVs compatíveis com shiny ao transferir para a Geração II"
                if shiny_info["shiny_candidate"]
                else None
            ),
            "map_id": map_id,
            "map_name": map_name,
        }

    def _map_name(self, map_id=None):
        """Resolve a real RAM map id to the name used by the dashboard."""
        try:
            from global_map import MAP_DATA
            resolved_id = self.read_m(0xD35E) if map_id is None else int(map_id)
            return MAP_DATA.get(resolved_id, {}).get("name", f"Map {resolved_id}")
        except Exception:
            return f"Map {map_id if map_id is not None else '?'}"

    def _read_bag_items(self):
        """Read the Gen I bag as item id/quantity pairs from the real RAM."""
        items = []
        try:
            item_count = min(int(self.read_m(0xD31D)), 20)
            for index in range(item_count):
                item_id = int(self.read_m(0xD31E + index * 2))
                quantity = int(self.read_m(0xD31F + index * 2))
                if item_id and quantity:
                    items.append({"item_id": item_id, "quantity": quantity, "slot": index})
        except Exception:
            pass
        return items

    def _read_money(self):
        """Gen I money is three BCD bytes at 0xD347..0xD349."""
        try:
            total = 0
            for offset in range(3):
                byte = int(self.read_m(0xD347 + offset))
                total = total * 100 + (byte >> 4) * 10 + (byte & 0x0F)
            return total
        except Exception:
            return 0

    def _poke_ball_count(self):
        return sum(item["quantity"] for item in self._capture_ball_inventory())

    def _bag_item_count(self, item_id):
        return sum(
            item["quantity"]
            for item in self._read_bag_items()
            if int(item["item_id"]) == int(item_id)
        )

    def _capture_policy(self, battle_info):
        """Explain capture vs. defeat from story state, personality and team value."""
        try:
            trainer_battle = (int(self.read_m(0xD057)) & 0b10) != 0
        except Exception:
            trainer_battle = self.last_battle_is_trainer
        balls = self._poke_ball_count()
        story_complete = self._capture_story_complete()
        shiny_candidate = bool(battle_info.get("shiny_candidate"))
        quality = self._capture_quality(battle_info)
        quality_species_id = int(battle_info.get("enemy_species_id") or 0)
        selected_ball = self._select_capture_ball(shiny_candidate)

        common = {
            **quality,
            "pokeballs": balls,
            "collector": self.collector,
            "meta_score": self.meta_score,
            "story_complete": story_complete,
            "capture_unlocked": story_complete and balls > 0,
            "shiny_candidate": shiny_candidate,
            "ball_item_id": selected_ball.get("item_id") if selected_ball else None,
            "ball_slot": selected_ball.get("slot") if selected_ball else None,
        }

        def decision(choice, reason_code, motivation, reason):
            return {
                **common,
                "choice": choice,
                "reason_code": reason_code,
                "motivation": motivation,
                "reason": reason,
            }

        if trainer_battle:
            return decision(
                "defeat", "trainer_battle", "story_battle",
                "Pokémon de treinador não pode ser capturado",
            )
        if not self.capture_enabled:
            return decision(
                "defeat", "capture_disabled", "training",
                "controlador de captura desativado",
            )
        if not story_complete:
            return decision(
                "defeat", "story_locked", "story_progression",
                "captura ainda bloqueada: primeiro precisa entregar a encomenda ao Professor Oak e liberar as Poké Balls",
            )
        if balls <= 0:
            return decision(
                "defeat", "no_pokeballs", "resource_management",
                "missão inicial concluída, mas não há Poké Balls no inventário",
            )
        if shiny_candidate:
            return decision(
                "capture", "shiny_priority", "shiny_priority",
                "prioridade absoluta: DVs compatíveis com shiny da Geração II; sempre tentar capturar",
            )

        # Losing the battle costs more than missing one catch: a fainted party
        # means a whiteout and a wasted trip. Fight first, catch later.
        if quality["own_hp_fraction"] <= SELF_PRESERVATION_HP:
            return decision(
                "defeat", "self_preservation", "survival",
                (
                    f"Pokémon ativo com {int(quality['own_hp_fraction'] * 100)}% de HP; "
                    "vencer a batalha vem antes de tentar capturar"
                ),
            )

        # Gen I catch rates scale with missing HP. Throwing at full health is
        # close to a wasted ball and gives the wild Pokémon a free turn.
        if (
            quality["enemy_hp_fraction"] > CAPTURE_HP_THRESHOLD
            and not quality["overkill_risk"]
            and not quality["enemy_impaired"]
            and quality["has_damage_left"]
        ):
            return decision(
                "defeat", "soften_before_capture", "capture_setup",
                (
                    f"alvo com {int(quality['enemy_hp_fraction'] * 100)}% de HP; "
                    "reduzir a vida antes de gastar Poké Bola"
                ),
            )

        # Never spend a ball on a species already registered in the Pokédex.
        # Duplicates cost balls and a party slot without adding coverage; the
        # evolved form is reached by training the one already owned.
        if not quality["new_species"]:
            return decision(
                "defeat", "duplicate_species", "team_building",
                (
                    "espécie já registrada na Pokédex"
                    + (" e presente na equipe" if quality["already_in_party"] else "")
                    + "; capturar repetido não agrega ao time"
                ),
            )

        # The archetype answers the one question the traits never could: what
        # to do with a wild Pokémon you *could* catch. Three trainers with the
        # same map knowledge and different answers is the whole experiment.
        stance = getattr(self, "capture_stance", "team_value_only")
        if stance == "only_when_needed":
            # Focused is not stubborn. A run that skips every catch arrives at
            # the gyms with nothing but its starter, and a gym that walls a lone
            # starter costs more turns than the catch ever would.
            power_pick = (
                quality["strategic_value"] >= RUSH_POWER_VALUE
                or quality["enemy_level"] > quality["strongest_party_level"]
            )
            if power_pick:
                return decision(
                    "capture", "rush_power_pick", "team_upgrade",
                    (
                        f"corrida focada, mas este vale a parada: valor "
                        f"estratégico {quality['strategic_value']} e nível "
                        f"{quality['enemy_level']} contra o melhor do time "
                        f"({quality['strongest_party_level']})"
                    ),
                )
            if quality["party_size"] >= MINIMUM_BACKUP_PARTY:
                return decision(
                    "defeat", "rush_skips_capture", "story_progression",
                    (
                        "corrida focada na história: com reserva no time, um "
                        "Pokémon comum não paga os turnos da captura"
                    ),
                )
        if stance in ("every_new_species", "preferred_types"):
            # A 5% Pikachu is not the same encounter as a 45% Caterpie, and no
            # quota should be allowed to skip it. This is the rule that decides
            # whether a run ends with the Pokémon its areas are remembered for.
            if is_rare_here(
                self._map_name(), quality_species_id, badges=self._badge_count()
            ):
                return decision(
                    "capture", "rare_for_this_area", "collector",
                    (
                        f"encontro raro nesta área "
                        f"({encounter_chance(self._map_name(), quality_species_id, self._badge_count())}% "
                        "de chance); não passar batido"
                    ),
                )

        if stance == "preferred_types":
            # A themed team is a constraint, not a preference: anything off
            # theme is experience, never a party slot. Kanto punishes fire and
            # dragon early on purpose — Brock and Misty come first, and Dratini
            # is a long way off — which is exactly what makes it worth watching.
            archetype = get_archetype(getattr(self, "archetype", None))
            wanted = set(archetype.get("preferred_types", ()))
            types = species_types(quality_species_id)
            honorary = set(archetype.get("honorary_species", ()))
            if quality_species_id in honorary:
                return decision(
                    "capture", "honorary_theme_species", "team_building",
                    (
                        "espécie honorária do tema: a tabela da Geração I diz "
                        "outra coisa, mas ela pertence a este time"
                    ),
                )
            if wanted and types and not (types & wanted):
                # The theme is the final team, not a promise to refuse help on
                # the way there. Kanto offers almost no fire or dragon before
                # Route 7, so a themed run that never accepts a stand-in dies
                # at Brock and Misty — the two worst gyms for it — and the
                # character never gets to exist. The stand-in has to be worth
                # it, and it gives the slot back when the theme shows up.
                floor = int(archetype.get("provisional_team_floor", 0))
                theme_members = sum(
                    1 for mon in self.get_party_info()
                    if species_types(mon.get("species_id")) & wanted
                )
                provisional = (
                    floor
                    and len(self.get_party_info()) < floor
                    and theme_members < floor
                    and quality["strategic_value"] >= PROVISIONAL_VALUE
                )
                if provisional:
                    return decision(
                        "capture", "provisional_until_theme", "team_building",
                        (
                            f"reforço de passagem: {'/'.join(sorted(types))} não é "
                            f"{'/'.join(sorted(wanted))}, mas segura a corrida até "
                            "aparecer um do tema"
                        ),
                    )
                return decision(
                    "defeat", "off_theme_species", "team_building",
                    (
                        f"time temático de {'/'.join(sorted(wanted))}: "
                        f"{'/'.join(sorted(types))} não entra"
                    ),
                )
            if wanted and types:
                here = species_of_types(
                    self._map_name(), wanted, self._badge_count()
                )
                scarcity = f"; esta área tem {len(here)} do tema" if here else ""
                return decision(
                    "capture", "on_theme_species", "team_building",
                    (
                        f"{'/'.join(sorted(types))} serve ao time temático de "
                        f"{'/'.join(sorted(wanted))}{scarcity}"
                    ),
                )

        if stance == "every_new_species":
            # Everything the run can currently meet — the coverage above only
            # counts species whose encounter method is already unlocked, so
            # asking for all of it never demands a Pokémon that lives past a
            # rod or past Surf. The set grows on its own as badges arrive.
            coverage = self._area_coverage()
            target = area_target(self._badge_count())
            if coverage is None or coverage["fraction"] < target:
                progress = (
                    f"{coverage['owned']}/{coverage['total']} desta área"
                    if coverage else "área sem tabela de encontros"
                )
                return decision(
                    "capture", "completionist_new_species", "collector",
                    (
                        f"completista: {progress} alcançáveis; espécie nova "
                        "entra no registro mesmo sem vaga no time"
                    ),
                )
            # Area target met: stop spending balls here and judge like anyone
            # else, so the run keeps moving instead of farming a finished map.
            if not quality["party_has_room"] and not quality["upgrade_candidate"]:
                return decision(
                    "defeat", "completionist_area_satisfied", "collector",
                    (
                        f"completista: {coverage['owned']}/{coverage['total']} "
                        "alcançáveis desta área registrados; o resto exige "
                        "vara ou Surf, então seguir viagem"
                    ),
                )

        # Filling the team comes before personality preferences. A weak-looking
        # catch such as Metapod is still worth a free slot because its evolved
        # form carries the early game.
        if quality["party_has_room"]:
            return decision(
                "capture", "party_slot_new_species", "team_building",
                (
                    f"equipe com {quality['party_size']}/{PARTY_TARGET} e espécie nova "
                    f"(valor estratégico {quality['strategic_value']}); "
                    f"{quality['party_slots_free']} vaga(s) livre(s)"
                ),
            )

        collector_choice = quality["new_species"] and self.collector >= 55
        upgrade_choice = quality["upgrade_candidate"] and self.meta_score >= 45
        if collector_choice and upgrade_choice:
            return decision(
                "capture", "collector_and_upgrade", "collector_and_upgrade",
                "espécie nova para a coleção e melhoria estratégica para o time",
            )
        if collector_choice:
            return decision(
                "capture", "collector_new_species", "collector",
                f"personalidade colecionadora ({self.collector}/100) quer registrar uma espécie nova",
            )
        if upgrade_choice:
            return decision(
                "capture", "team_upgrade", "team_upgrade",
                (
                    "Pokémon avaliado como melhoria do time "
                    f"(nível {quality['enemy_level']}, vantagem {quality['level_advantage']:+d}, "
                    f"valor estratégico {quality['strategic_value']})"
                ),
            )
        return decision(
            "defeat", "training_value", "training",
            "não é espécie nova prioritária nem melhoria do time; derrotar para ganhar experiência",
        )

    def _consume_manual_throw_order(self, battle_info, remaining_balls):
        """Spend the operator's order once, not once per encounter.

        `MANUAL: THROW_BALL` means "throw one at this one". Left standing it
        would empty the bag across every battle that followed, so the ball
        leaving the bag is what closes the order and hands the trainer back to
        the story.
        """
        self.capture_forced = False
        try:
            if self.task_file.exists():
                self.task_file.unlink()
        except OSError:
            pass
        if self.active_quest_id:
            node = self.quest_graph.nodes_by_id.get(self.active_quest_id)
            if node is not None:
                self.current_task = f"QUEST: {node.executor.upper()}"
        self._log_event("manual_order_completed", {
            "order": MANUAL_THROW_BALL_TASK,
            "enemy_species_id": battle_info.get("enemy_species_id"),
            "pokeballs": remaining_balls,
            "reason": "bola lançada por ordem do operador; jornada retomada",
        })

    def _next_capture_action(self):
        """Operate the real Gen I menus for a guarded capture attempt.

        Normal personality/upgrade decisions spend at most one ball. A
        Gen-II-shiny-compatible encounter retries while the battle and ball
        inventory remain available. Every success still requires confirmation
        from party/Pokédex RAM; menu inputs alone never count as a capture.
        """
        battle_info = self._get_battle_info()
        if not battle_info or not self.in_battle:
            return None

        policy = self._capture_policy(battle_info)
        self.last_capture_policy = policy

        if self.capture_in_flight:
            # B advances capture-result text but cannot accidentally choose a
            # move from the battle menu. Repeating it also closes the Bag if a
            # delayed input left that submenu open.
            if self.capture_result_steps > 0:
                self.capture_result_steps -= 1
                self.battle_action_mode = "capture"
                return "B"

            self.capture_in_flight = False
            remaining_balls = self._poke_ball_count()
            ball_was_used = (
                self.capture_balls_before_attempt is not None
                and remaining_balls < self.capture_balls_before_attempt
            )
            self.capture_balls_before_attempt = None
            self.capture_plan = []
            if ball_was_used and self.capture_forced:
                self._consume_manual_throw_order(battle_info, remaining_balls)

            if policy.get("shiny_candidate") and remaining_balls > 0 and ball_was_used:
                self.capture_plan_battle = None
                self._log_event("capture_attempt", {
                    "result": "retrying_shiny",
                    "enemy_id": battle_info.get("enemy_id"),
                    "enemy_species_id": battle_info.get("enemy_species_id"),
                    "reason": "a captura falhou; encontro compatível com shiny mantém prioridade absoluta",
                    "pokeballs": remaining_balls,
                    "attempt": self.capture_attempts,
                    "motivation": "shiny_priority",
                    "shiny_candidate": True,
                })
            else:
                self.battle_action_mode = "attack"
                self._log_event("capture_attempt", {
                    "result": "failed_or_not_confirmed",
                    "enemy_id": battle_info.get("enemy_id"),
                    "enemy_species_id": battle_info.get("enemy_species_id"),
                    "reason": (
                        "Poké Bola usada, mas captura não confirmada; voltar para treino"
                        if ball_was_used
                        else "menu não confirmou o uso da Poké Bola; fallback seguro para ataque"
                    ),
                    "pokeballs": remaining_balls,
                    "motivation": policy.get("motivation"),
                    "shiny_candidate": policy.get("shiny_candidate", False),
                })
                # ITEM is remembered after returning from the Bag. Move back
                # toward FIGHT before SimpleBattleAgent presses A.
                return "UP"

        if policy["choice"] != "capture" and not self.capture_forced:
            return None

        # Once the bag is open the plan stops being a script and starts being a
        # loop with eyes: the highlighted row is readable in RAM, so the cursor
        # is moved until it is actually on the ball. Blind presses reported
        # "menu não confirmou o uso da Poké Bola" over and over — the ball
        # count never dropped, because the cursor was never where the script
        # assumed it was.
        if getattr(self, "capture_bag_open", False):
            self.battle_action_mode = "capture"
            ball_slot = policy.get("ball_slot")
            ball_item_id = policy.get("ball_item_id")
            if ball_slot is None:
                return "B"
            highlighted = self.bag_highlighted_slot()
            if highlighted is None:
                return "B"
            # The row is how to get there; the item id is what confirms
            # arriving. Bag positions shift with every item picked up or used
            # up, and an eaten press leaves the cursor one row off — pressing A
            # on the row alone is how a Poké Ball becomes an Antidote.
            highlighted_item = self.bag_highlighted_item_id()
            if highlighted_item is not None and highlighted_item == ball_item_id:
                pass
            elif highlighted < ball_slot:
                return "DOWN"
            elif highlighted > ball_slot:
                return "UP"
            elif highlighted_item is not None:
                # Right row, wrong item: the bag moved under us. Ask the policy
                # again next step instead of throwing whatever is there.
                self.capture_bag_open = False
                self.capture_plan_battle = None
                return "B"
            self.capture_plan = []
            self.capture_bag_open = False
            self.capture_in_flight = True
            self.capture_result_steps = CAPTURE_RESULT_ADVANCE_STEPS
            self.capture_balls_before_attempt = self._poke_ball_count()
            return "A"

        if self.capture_plan_battle != self.battle_sequence:
            ball_slot = policy.get("ball_slot")
            if ball_slot is None:
                return None
            self.capture_bag_open = False
            self.capture_menu_steps = 0
            self.capture_plan_battle = self.battle_sequence
            self.capture_attempts += 1
            self._log_event("capture_intent", {
                "enemy_id": battle_info.get("enemy_id"),
                "enemy_species_id": battle_info.get("enemy_species_id"),
                "enemy_level": battle_info.get("enemy_level"),
                "policy": policy,
                "attempt": self.capture_attempts,
                "max_attempts": "while_balls_remain" if policy.get("shiny_candidate") else 1,
                "reason": policy["reason"],
                "reason_code": policy.get("reason_code"),
                "motivation": policy.get("motivation"),
                "shiny_candidate": policy.get("shiny_candidate", False),
                "ball_item_id": policy.get("ball_item_id"),
            })

        # Walk the battle menu by what the cursor really says. A press eaten by
        # a text box simply repeats; the Bag is only entered from ITEM.
        self.battle_action_mode = "capture"
        self.capture_menu_steps = getattr(self, "capture_menu_steps", 0) + 1
        if self.capture_menu_steps > CAPTURE_MENU_STEP_LIMIT:
            # Something on screen is not the battle menu and is not going
            # away. Give the turn back to the battle controller rather than
            # pressing into the dark forever.
            self.capture_plan_battle = None
            self.capture_bag_open = False
            self.battle_action_mode = "attack"
            self._log_event("capture_attempt", {
                "result": "menu_unreachable",
                "enemy_id": battle_info.get("enemy_id"),
                "enemy_species_id": battle_info.get("enemy_species_id"),
                "reason": "o menu de batalha não respondeu; devolve o turno ao controlador de luta",
                "pokeballs": self._poke_ball_count(),
                "motivation": policy.get("motivation"),
                "shiny_candidate": policy.get("shiny_candidate", False),
            })
            return None
        action = self._battle_menu_step_to_item()
        if action == "A":
            # Confirmed on ITEM: this A opens the Bag, and the cursor loop
            # above takes over from the next step.
            self.capture_bag_open = True
        return action

    def _moves(self):
        """A tabela do cartucho, lida uma vez por ambiente."""
        table = getattr(self, "move_table", None)
        if table is None or not len(table):
            self.move_table = MoveTable.from_memory(self)
        return self.move_table

    def _has_damaging_pp(self, pokemon):
        moves = self._moves()
        return any(
            moves.is_damaging(int(move.get("id") or 0))
            and int(move.get("pp") or 0) > 0
            for move in pokemon.get("moves") or []
        )

    def _switch_target_slot(self):
        """Party slot of someone who can still deal damage, or None.

        With every attack at zero PP the game forces Struggle, which in Gen I
        recoils for half the damage dealt: the active Pokémon grinds itself
        down fighting something it cannot hurt. A teammate who still has PP is
        the cheapest answer available, and it needs no walking.
        """
        party = self.get_party_info()
        if len(party) < 2:
            return None
        try:
            active_slot = int(self.read_m(ACTIVE_PARTY_SLOT_ADDRESS))
        except Exception:
            active_slot = 0
        active = party[active_slot] if 0 <= active_slot < len(party) else None
        fainted = active is not None and int(active.get("hp") or 0) <= 0
        if fainted:
            # O slot ativo (0xCC2F) pode ler 0 durante uma transição de menu,
            # enquanto o Pokémon de pé lutando está em 0xD014. Se o ativo de
            # batalha real está de pé, não há troca a fazer — o "slot 0 caído"
            # é leitura desatualizada, não um desmaio. AARON ficava num loop
            # de switch contra o próprio Butterfree assim.
            try:
                battle_internal = int(self.read_m(0xD014))
                for index, mon in enumerate(party):
                    if int(mon.get("internal_id") or 0) == battle_internal:
                        if int(mon.get("hp") or 0) > 0:
                            return None
                        break
            except Exception:
                pass
        if active is not None and not fainted:
            # Só troca quem caiu. A troca voluntária — ativo de pé, mas sem PP
            # de dano — exige abrir o menu de batalha, ir até PKMN, escolher e
            # confirmar TROCAR, e é aí que ela emperrava: BARON pediu o slot 4
            # vinte vezes seguidas sem nunca completar, porque o caminho que
            # este controlador conhece começa no aviso "Use next POKéMON?", que
            # só aparece quando alguém desmaia.
            #
            # Lutar com o que tem na mão é pior turno e é saída: o de status
            # gasta PP, o Struggle machuca, e o apagão devolve o time inteiro
            # num Centro. Ficar preso no menu não é saída nenhuma.
            return None

        # A fainted lead has to be replaced by whoever is still standing, with
        # or without PP: the game will not continue until someone is sent out.
        # With PP left the choice is about damage; without it, it is about the
        # battle ending at all.
        alive = [
            slot for slot, pokemon in enumerate(party)
            if slot != active_slot and int(pokemon.get("hp") or 0) > 0
        ]
        with_damage = [slot for slot in alive if self._has_damaging_pp(party[slot])]
        if with_damage:
            return with_damage[0]
        if fainted and alive:
            return alive[0]
        return None

    def _party_is_worn_out(self, fraction=FLEE_HP_FRACTION):
        """Combined party HP under the travelling threshold."""
        party = self.get_party_info()
        total = sum(int(mon.get("max_hp") or 0) for mon in party)
        if total <= 0:
            return False
        current = sum(int(mon.get("hp") or 0) for mon in party)
        return current < total * fraction

    def _party_has_no_damage(self):
        """True when nobody standing has a damaging move with PP left."""
        for mon in self.get_party_info():
            if int(mon.get("hp") or 0) <= 0:
                continue
            if self._has_damaging_pp(mon):
                return False
        return True

    def _next_escape_action(self):
        """Run from a wild fight that is not worth the turn, during navigation.

        DESLIGADA por decisão do operador (2026-08-12): fuga em qualquer
        circunstância prende mais do que morrer. O whiteout é o mecanismo de
        cura projetado — o cartucho devolve o time inteiro, curado, ao Centro
        — e fugir o impede. Medido: FARON fugiu 2.196 de 2.224 batalhas do
        treino com o time machucado, nunca morreu, nunca curou, e o nível 6
        ficou parado para sempre. Morrer destrava; fugir empaca.
        """
        return None

    def _next_switch_action(self):
        """Send out a teammate that still has PP, driving the real menus."""
        if self.capture_in_flight or self.capture_plan or getattr(
            self, "capture_bag_open", False
        ):
            return None
        target = self._switch_target_slot()
        if target is None:
            self.switch_menu_open = False
            self.switch_plan = []
            return None

        # A faint does not open the battle menu: the game asks "Use next
        # POKéMON?" first, and only then shows the party list. Walking the 2x2
        # cursor there does nothing — the prompt has to be answered.
        if not getattr(self, "switch_menu_open", False) and self._battle_prompt_open():
            party = self.get_party_info()
            try:
                active_slot = int(self.read_m(ACTIVE_PARTY_SLOT_ADDRESS))
            except Exception:
                active_slot = 0
            active = party[active_slot] if 0 <= active_slot < len(party) else None
            if active is not None and int(active.get("hp") or 0) <= 0:
                self.switch_menu_open = True
                self.switch_steps = 0
                return "A"

        # The party list can appear without the prompt ever being seen — a
        # faint in a trainer battle opens it directly. Recognising the screen
        # matters more than remembering how we got here.
        if self._party_menu_open():
            self.switch_menu_open = True

        if getattr(self, "switch_menu_open", False):
            self.switch_steps = getattr(self, "switch_steps", 0) + 1
            if self.switch_steps > SWITCH_MENU_STEP_LIMIT:
                # The party menu is not where it was expected. Back out and let
                # the battle controller fight rather than mash inputs blindly.
                self.switch_menu_open = False
                self.switch_steps = 0
                return "B"
            # The affirmative answer can leave the faint prompt's text box
            # open for another frame before the party list is drawn. Cursor
            # coordinates are stale during that transition; advance the real
            # prompt first instead of sending D-pad input into it.
            if self._battle_prompt_open():
                return "A"
            # In Blue's forced-switch screen the text flag is already clear,
            # while CC50 remains 224 until the prompt's hidden cursor accepts
            # one navigation input. After that first DOWN/UP, A opens the
            # party list; reading CC26 before then causes an endless DOWN.
            if int(self.read_m(0xCC50)) == 224 and self.switch_steps > 1:
                return "A"
            highlighted = self.bag_highlighted_slot()
            if highlighted is None:
                self.switch_menu_open = False
                return "B"
            if highlighted < target:
                return "DOWN"
            if highlighted > target:
                return "UP"
            self.switch_menu_open = False
            self.switch_steps = 0
            # A on the chosen Pokémon, then A again on SWITCH, the first option
            # of the little menu that opens.
            self.switch_plan = ["A", "A"]
            return self.switch_plan.pop(0)

        if getattr(self, "switch_plan", None):
            action = self.switch_plan.pop(0)
            if not self.switch_plan and action == "A":
                # That A opened the party list; the cursor loop takes over.
                self.switch_menu_open = True
            return action

        self._log_event("switch_intent", {
            "reason": "sem PP de dano no ativo; trocar por quem ainda pode atacar",
            "target_slot": target,
            "party": self.get_party_info(),
        }, live=False)
        self.switch_steps = 0
        action = self._battle_menu_step_to_pokemon()
        if action == "A":
            # PKMN confirmed under the cursor: this A opens the party list.
            self.switch_menu_open = True
        return action

    def _restart_mission(self, reason):
        """Throw away the route state and let the quest plan again from here.

        Every freeze so far had its own cause, and each fix removed one. This
        removes the class: whatever traps a bot on a single tile, the mission
        starts over from where it actually stands. Route state is a cache of
        intentions, not progress — dropping it costs a few steps and never
        touches the save.

        The task itself is deliberately left alone. Clearing it made the agent
        re-run its checkpoint detection, which sees a Pokémon in the party and
        concludes the run is back at the rival fight in Oak's lab — an objective
        that finished long ago and has nothing left to do, so it returns no
        action at all and every bot freezes at once.
        """
        agent = getattr(self, "scripted_agent", None)
        for attribute in (
            "route_id", "route_index", "route_plan", "route_suspect",
            "route_last_position", "route_last_direction", "route_stuck_steps",
            "route_stuck_cycles", "route_menu_presses", "route_previous_tile",
            "route_target_was_final", "fixed_route_id", "fixed_route_index",
        ):
            if agent is not None and hasattr(agent, attribute):
                delattr(agent, attribute)
        self.stagnant_position = None
        self.stagnant_steps = 0
        self._log_event("mission_restarted", {
            "reason": reason,
            "task": getattr(self, "current_task", ""),
            "map_id": int(self.read_m(0xD35E)),
            "coords": [int(self.read_m(0xD362)), int(self.read_m(0xD361))],
        })

    def _watch_for_stagnation(self):
        """A bot that has not moved for this long is not making progress."""
        # Story routes own their recovery. Restarting the mission here erased
        # the measured segment every 300 PPO steps and recreated the same loop
        # at Viridian Forest's entrance. The dashboard loop detector can request
        # a replan explicitly; never discard a real quest route on a timer.
        if self.current_task.startswith("QUEST"):
            return
        if self.read_m(0xD057) != 0:
            self.stagnant_steps = 0
            return
        position = (
            int(self.read_m(0xD35E)),
            int(self.read_m(0xD362)),
            int(self.read_m(0xD361)),
        )
        if position != getattr(self, "stagnant_position", None):
            self.stagnant_position = position
            self.stagnant_steps = 0
            return
        self.stagnant_steps = getattr(self, "stagnant_steps", 0) + 1
        if self.stagnant_steps >= MISSION_RESTART_STEPS:
            self._restart_mission(
                f"parado em {position[1]},{position[2]} do mapa {position[0]} "
                f"por {self.stagnant_steps} passos"
            )

    def _battle_prompt_open(self):
        """Whether a text box or prompt is currently taking the input."""
        try:
            return int(self.read_m(0xCFC4)) == 1
        except Exception:
            return False

    def _party_menu_open(self):
        """True when the party list is the menu taking input.

        The 2x2 battle menu and the party list share the cursor bytes, so the
        only way to tell them apart is the list's own shape: the party screen
        sets the last selectable row to the last Pokémon, and its cursor sits
        in column zero. Without this the controller read the party list as a
        battle menu, decided it was not one, and pressed B — which does nothing
        at a forced switch. A trainer stood there with two healthy Pokémon and
        lost the battle.
        """
        try:
            party_count = int(self.read_m(0xD163))
            if party_count <= 1:
                return False
            return (
                int(self.read_m(BATTLE_MENU_LAST_ROW_ADDRESS)) == party_count - 1
                and int(self.read_m(BATTLE_MENU_COLUMN_ADDRESS)) == 0
            )
        except Exception:
            return False

    def _battle_menu_step(self, target_row, target_column):
        """One press toward a cell of the 2x2 battle menu, or B to get there.

        The column byte alone is not proof that the 2x2 is on screen: inside
        the move list it still reads like a menu column, and the row goes to 3.
        A trainer with every attack at zero PP sat there pressing DOWN into a
        submenu for sixteen thousand steps.

        So the check is behavioural, not structural: if a direction changed
        nothing, we are not where we thought, and B is the way back — it closes
        a submenu, it advances text, and it can never pick a move.
        """
        try:
            row = int(self.read_m(BATTLE_MENU_ROW_ADDRESS))
            column = int(self.read_m(BATTLE_MENU_COLUMN_ADDRESS))
        except Exception:
            return "B"
        previous = getattr(self, "battle_menu_probe", None)
        self.battle_menu_probe = (row, column)
        if column not in (BATTLE_MENU_LEFT_COLUMN, BATTLE_MENU_RIGHT_COLUMN):
            return "B"
        if row not in (BATTLE_MENU_FIGHT_ROW, BATTLE_MENU_ITEM_ROW):
            return "B"
        if row == target_row and column == target_column:
            self.battle_menu_probe = None
            return "A"
        step = (
            ("DOWN" if target_row > row else "UP") if row != target_row
            else ("RIGHT" if target_column > column else "LEFT")
        )
        if previous == (row, column):
            # The last press moved nothing at all: text is eating input, or
            # this is not the menu we think it is.
            return "B"
        return step

    def _battle_menu_step_to_pokemon(self):
        """One step toward PKMN. RUN sits next to it, so nothing is guessed."""
        return self._battle_menu_step(BATTLE_MENU_FIGHT_ROW, BATTLE_MENU_RIGHT_COLUMN)

    def bag_highlighted_slot(self):
        """Bag index under the cursor: scroll offset plus the highlighted row."""
        try:
            return int(self.read_m(MENU_SCROLL_OFFSET_ADDRESS)) + int(
                self.read_m(MENU_CURSOR_ADDRESS)
            )
        except Exception:
            return None

    def bag_highlighted_item_id(self):
        """The item id actually under the Bag cursor, read from the bag itself.

        Counting rows is not the same as knowing what is highlighted. The
        Poké Ball's slot moves every time an item is picked up or used up, and
        a press swallowed by text leaves the cursor one row from where the
        controller believes it is. Both mistakes look identical from outside —
        and both end with A pressed on the wrong item.

        The bag is a plain list in RAM, so the honest question is answerable:
        what is in the highlighted slot right now.
        """
        slot = self.bag_highlighted_slot()
        if slot is None:
            return None
        try:
            count = min(int(self.read_m(BAG_ITEM_COUNT_ADDRESS)), BAG_CAPACITY)
        except Exception:
            return None
        if not 0 <= slot < count:
            return None
        try:
            return int(self.read_m(BAG_FIRST_ITEM_ADDRESS + slot * 2))
        except Exception:
            return None

    def _log_battle_decision(self, action):
        """Log the real battle controller's choice without duplicating turns."""
        battle_info = self._get_battle_info()
        if not battle_info or not self.in_battle:
            return

        controller_decision = getattr(self.battle_agent, "last_decision", {}) or {}
        selected = controller_decision.get("selected") or {}
        action_kind = "attack" if action == "A" else "menu_navigation"
        wild_battle = (int(self.read_m(0xD057)) & 0b10) == 0
        balls = self._poke_ball_count()
        capture_policy = self._capture_policy(battle_info)
        self.last_capture_policy = capture_policy

        # The current real controller is intentionally explicit: it can attack
        # and navigate the fight menu, but it does not yet operate the Bag.
        # Keeping both policy_choice and executed_choice prevents the log from
        # claiming a capture happened when only an attack was sent to PyBoy.
        policy_choice = capture_policy["choice"]
        if self.battle_action_mode == "capture":
            executed_choice = "capture_attempt"
            execution_status = "executing_real_menu_sequence"
        else:
            executed_choice = "defeat" if action_kind == "attack" else "menu_navigation"
            execution_status = "executed" if policy_choice == "defeat" else "capture_fallback_to_attack"
        decision_key = (
            self.battle_sequence,
            battle_info.get("enemy_id"),
            selected.get("move_id"),
            policy_choice,
        )
        if decision_key == self.last_battle_decision_key:
            return
        self.last_battle_decision_key = decision_key
        self.battle_decision_count += 1

        self._log_event("battle_decision", {
            "battle": "wild" if wild_battle else "trainer",
            "enemy_id": battle_info.get("enemy_id"),
            "enemy_species_id": battle_info.get("enemy_species_id"),
            "enemy_level": battle_info.get("enemy_level"),
            "encounter_type": battle_info.get("encounter_type"),
            "encounter_label": battle_info.get("encounter_label"),
            "active_pokemon": battle_info.get("active_pokemon"),
            "policy_choice": policy_choice,
            "executed_choice": executed_choice,
            "execution_status": execution_status,
            "reason": capture_policy["reason"],
            "reason_code": capture_policy.get("reason_code"),
            "motivation": capture_policy.get("motivation"),
            "battle_action_reason": controller_decision.get(
                "reason", "controlador de batalha selecionou a ação disponível"
            ),
            "action": action,
            "move": selected,
            # The bytes the controller actually read to choose that key. AARON
            # pressed DOWN for two minutes straight and the event recorded the
            # press without the reason, so the freeze had to be reconstructed
            # from source instead of answering itself. Rule 6 of this project:
            # observable event, with the motive and the raw data.
            "menu": controller_decision.get("menu"),
            "pokeballs": balls,
            "collector": self.collector,
            "meta_score": self.meta_score,
            "new_species": capture_policy.get("new_species", False),
            "upgrade_candidate": capture_policy.get("upgrade_candidate", False),
            "shiny_candidate": capture_policy.get("shiny_candidate", False),
            "capture_unlocked": capture_policy.get("capture_unlocked", False),
            "controller": "SimpleBattleAgent",
            "capture_controller": self.battle_action_mode == "capture",
        }, live=False)

    def _log_training_target(self, battle_info):
        """Record who is actually receiving XP in the current real battle."""
        active = battle_info.get("active_pokemon") or {}
        active_internal_id = active.get("internal_id")
        if active_internal_id is None or active_internal_id == self.last_active_internal_id:
            return

        self.last_active_internal_id = active_internal_id
        party = self.get_party_info()
        recommended = min(
            (pokemon for pokemon in party if pokemon.get("hp", 0) > 0),
            key=lambda pokemon: pokemon.get("level", 0),
            default=None,
        )
        self._log_event("training_target", {
            "active_pokemon": active,
            "active_receives_xp": True,
            "recommended_lowest_level": recommended,
            "choice": "keep_active",
            "reason": "XP da Gen I vai para o Pokémon ativo; o controlador ainda não troca Pokémon automaticamente",
        })

    # Legacy _get_llm_action removed
    
    def _log_event(self, event_type, data, live=True):
        """Registrar um evento, colapsando repetição idêntica em sequência.

        O diário de uma corrida do AARON tinha 14.275 eventos e 11,8 MB, e
        2.093 deles eram o mesmo ciclo: encontrou Zubat, decidiu não capturar
        por falta de bola, terminou a batalha. Nenhum id duplicado — o bot
        estava mesmo repetindo, e o diário relatava com fidelidade. Fidelidade
        aqui é ruído: quem lê precisa ver "fugiu de Zubat ×1.643", não 1.643
        linhas iguais para rolar.

        A primeira ocorrência sai na hora, para o painel não ficar mudo. As
        seguintes são contadas, e quando a sequência quebra sai uma linha só
        com o total.
        """
        import json

        signature = (event_type, json.dumps(data, sort_keys=True, default=str))
        collapser = self._event_collapser()
        action, summary = collapser.observe(signature)
        if summary is not None:
            self._write_summary_event(summary)
        if action == "emit":
            self._write_event(event_type, data, live)

    def _event_collapser(self):
        collapser = getattr(self, "_collapser", None)
        if collapser is None:
            collapser = EventCollapser()
            self._collapser = collapser
        return collapser

    def _flush_repeated_event(self):
        """Fechar o que estiver em aberto — fim de sessão, por exemplo."""
        summary = self._event_collapser().flush()
        if summary is not None:
            self._write_summary_event(summary)

    def _write_summary_event(self, summary):
        """A linha que substitui uma sequência: diz o padrão e quantas foram."""
        import json

        event_type, raw = summary["signature"] if summary["kind"] == "repeat" else (
            "diario", "{}"
        )
        try:
            data = dict(json.loads(raw))
        except (ValueError, TypeError):
            data = {}
        count = int(summary["count"])
        if summary["kind"] == "repeat":
            data["repeated"] = count
            data["reason"] = (
                f"mesma decisão repetida {count}× seguidas sem nada mudar"
            )
            self._write_event(f"{event_type}_repeated", data, live=True)
            return
        # Ciclo: eventos diferentes que se repetem em ordem. É o formato que um
        # bot preso produz, e o que enchia 12.558 linhas em Mt. Moon.
        self._write_event("ciclo_repetido", {
            "period": int(summary["period"]),
            "events_suppressed": count,
            "turns": int(summary["turns"]),
            "reason": (
                f"a mesma sequência de {summary['period']} eventos se repetiu "
                f"{summary['turns']}× sem nada mudar"
            ),
        }, live=True)

    def _write_event(self, event_type, data, live=True):
        """Log events to shared feed for visualization"""
        import json

        # Create event object
        try:
            map_id = int(self.read_m(0xD35E))
            coords = [int(self.read_m(0xD362)), int(self.read_m(0xD361))]
        except Exception:
            map_id = None
            coords = None
        event = {
            "id": f"{self.run_id}:{self.step_count}:{event_type}:{time.time_ns()}",
            "agent": self.agent_name,
            "run_id": self.run_id,
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
            "step": self.step_count,
            "journey_step": self.journey_total_steps,
            "map_id": map_id,
            "map_name": self._map_name(map_id),
            "coords": coords,
            "task": getattr(self, "current_task", ""),
            "milestone": getattr(self, "current_milestone", "start"),
            "live": live,
        }
        
        # Add specific info based on type
        if event_type == "capture":
            if isinstance(data, dict) and data.get("pokemon"):
                event["pokemon"] = data["pokemon"]
            else:
                party = self.get_party_info()
                if party:
                    event["pokemon"] = party[-1]  # Last captured
        
        if live:
            # Only semantic events enter the live window. Raw map transitions
            # remain in JSONL without evicting captures and story milestones.
            self.recent_events.append(event)
            self.recent_events = self.recent_events[-15:]
            print(f"[{self.agent_name}] 📡 Event logged: {event_type} (total in memory: {len(self.recent_events)})")
        
        # Also write to file for persistence
        events_file = Path(__file__).parent / "tasks/events_feed.json"
        events_file.parent.mkdir(exist_ok=True)
        
        # Read existing events
        events = []
        if events_file.exists():
            try:
                with open(events_file, 'r') as f:
                    events = json.load(f)
            except:
                events = []
        
        events.append(event)
        
        # Keep only last 50 events in file
        events = events[-50:]
        
        # Write back
        try:
            with open(events_file, 'w') as f:
                json.dump(events, f, indent=2)
        except:
            pass

        # Full history is append-only and per-agent. The UI receives the small
        # recent_events window above, while this JSONL remains inspectable after
        # a long real run without repeatedly rewriting an unbounded JSON file.
        try:
            self.decision_log_dir.mkdir(parents=True, exist_ok=True)
            with open(self.decision_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            pass
    
    def _track_battles_and_deaths(self):
        """Track battle victories and deaths for events"""
        deaths_before = self.deaths
        # Check if in battle
        is_in_battle = self.read_m(0xD057) != 0

        if is_in_battle:
            enemy_id = int(self.read_m(0xCFE5))
            enemy_hp = (int(self.read_m(0xCFE6)) << 8) + int(self.read_m(0xCFE7))
            player_hp = (int(self.read_m(0xD015)) << 8) + int(self.read_m(0xD016))
            if enemy_id not in (0, 0xFF):
                self.last_battle_enemy_id = enemy_id
                self.last_battle_enemy_hp = enemy_hp
            self.last_battle_player_hp = player_hp
            party_during_battle = self.get_party_info()
            optional_rival_in_progress = (
                self.last_battle_is_trainer
                and self.last_battle_map_id == 40
                and self.current_task == "QUEST: OAK_EVENT"
            )
            if (
                party_during_battle
                and not optional_rival_in_progress
                and all(
                    int(mon.get("hp") or 0) <= 0 for mon in party_during_battle
                )
            ):
                self.whiteout_pending = True
        
        # Detect battle end (was in battle, now not)
        if self.in_battle and not is_in_battle:
            # Battle ended. Trainer battles cannot be fled; wild battles can,
            # so an alive party alone is not enough evidence of a victory.
            party = self.get_party_info()
            has_alive_pokemon = any(p.get('hp', 0) > 0 for p in party)
            battle_kind = "trainer" if self.last_battle_is_trainer else "wild"
            capture_confirmed = (
                self.capture_attempts > 0
                and (
                    len(party) > self.battle_party_count_before
                    or self._pokedex_owned_count() > self.battle_pokedex_owned_before
                )
            )
            optional_rival_loss = (
                self.last_battle_player_hp == 0
                and self.last_battle_is_trainer
                and self.last_battle_map_id == 40
                and self.current_task == "QUEST: OAK_EVENT"
            )
            end_map_id = int(self.read_m(0xD35E))
            party_is_full = bool(party) and all(
                int(mon.get("hp") or 0) >= int(mon.get("max_hp") or 0) > 0
                for mon in party
            )
            whiteout_transition = (
                self.last_battle_map_id is not None
                and end_map_id != self.last_battle_map_id
                and party_is_full
            )
            if self.last_battle_player_hp == 0 or not has_alive_pokemon:
                battle_result = "optional_loss" if optional_rival_loss else "loss"
            elif capture_confirmed:
                # A new party member and a new Pokédex entry are stronger
                # evidence than the last enemy-HP read, which can land on zero
                # while the ball is closing. Ranked below the win check, a real
                # capture was reported as a knockout.
                battle_result = "capture"
            elif self.last_battle_is_trainer or self.last_battle_enemy_hp == 0:
                battle_result = "win"
            else:
                battle_result = "escaped"
            if whiteout_transition and not optional_rival_loss:
                # A battle ending on another map is the cartridge's whiteout
                # transition. Do not let an enemy HP sample mislabel it as a
                # victory before the party reaches the healing point.
                battle_result = "loss"
            self._log_event("battle_end", {
                "type": battle_kind,
                "result": battle_result,
                "enemy_id": self.last_battle_enemy_id,
                "active_pokemon": self.last_active_internal_id,
                "player_hp_at_end": self.last_battle_player_hp,
                "battle_map_id": self.last_battle_map_id,
                "end_map_id": end_map_id,
            }, live=False)

            if battle_result == "win":
                if self.last_battle_is_trainer:
                    self.trainer_battles_won += 1
                else:
                    self.wild_battles_won += 1
                self._log_event("battle_win", {
                    "type": battle_kind,
                    "enemy_id": self.last_battle_enemy_id,
                    "total_trainer_wins": self.trainer_battles_won,
                    "total_wild_wins": self.wild_battles_won,
                }, live=self.last_battle_is_trainer)
            elif battle_result in ("loss", "optional_loss"):
                self._log_event("battle_loss", {
                    "type": battle_kind,
                    "enemy_id": self.last_battle_enemy_id,
                    "optional": optional_rival_loss,
                    "reason": (
                        "derrota opcional na primeira luta contra o rival; a história continua"
                        if optional_rival_loss
                        else "todos os Pokémon da party estavam sem HP"
                    ),
                })
                # On a whiteout, Pokémon Blue can heal the party and warp to
                # the last healing point before the first non-battle frame is
                # observable. Preserve that transition as a real death.
                healed_during_warp = (
                    whiteout_transition
                )
                if battle_result == "loss" and healed_during_warp:
                    self.deaths += 1
                    self.whiteout_pending = True
                    self._log_event("death", {
                        **self._close_death_cycle(),
                        "location": end_map_id,
                        "battle_location": self.last_battle_map_id,
                        "reason": "whiteout confirmado pela transição de mapa e cura automática",
                    })
            # A capture decision is only half the story. Close it with what
            # actually happened to that Pokémon, so the feed never leaves
            # "decidiu capturar" hanging without "capturou", "derrotou" ou
            # "fugiu".
            if battle_kind == "wild":
                intent = getattr(self, "battle_capture_intent", None) or (
                    self.last_capture_policy or {}
                )
                balls_before = getattr(self, "battle_balls_before", None)
                balls_now = self._poke_ball_count()
                outcome = {
                    "capture": "captured",
                    "win": "defeated",
                    "escaped": "fled",
                    "loss": "fainted",
                    "optional_loss": "fainted",
                }.get(battle_result, battle_result)
                party_after = self.get_party_info()
                self._log_event("capture_outcome", {
                    "intent": intent.get("choice"),
                    "reason_code": intent.get("reason_code"),
                    "reason": intent.get("reason"),
                    "outcome": outcome,
                    "enemy_species_id": intent.get("enemy_species_id"),
                    "enemy_level": intent.get("enemy_level"),
                    "balls_thrown": (
                        max(balls_before - balls_now, 0)
                        if balls_before is not None
                        else None
                    ),
                    "pokeballs": balls_now,
                    "shiny_candidate": intent.get("shiny_candidate", False),
                    "party": party_after,
                    "party_size": len(party_after),
                }, live=(outcome == "captured" or intent.get("choice") == "capture"))
                if outcome == "captured":
                    # The panel reads a snapshot written every few dozen steps.
                    # A new team member is exactly the moment someone is looking,
                    # so publish it now instead of at the next interval.
                    self._update_agent_state()
                self.battle_capture_intent = None

            if battle_result == "escaped":
                self._log_event("battle_escaped", {
                    "type": battle_kind,
                    "enemy_id": self.last_battle_enemy_id,
                    "reason": "batalha selvagem terminou sem nocaute nem captura confirmada",
                }, live=False)
        
        # Detect death (whiteout) - all pokemon fainted
        if not is_in_battle:
            party = self.get_party_info()
            if party and len(party) > 0:
                all_fainted = all(p.get('hp', 0) == 0 for p in party)
                optional_rival_loss = (
                    self.last_battle_is_trainer
                    and int(self.read_m(0xD35E)) == 40
                    and self.current_task == "QUEST: OAK_EVENT"
                )
                if all_fainted and self.last_hp_check is True and not optional_rival_loss:
                    # Just died (whiteout), detected on the alive -> fainted edge.
                    self.deaths += 1
                    self.whiteout_pending = True
                    self._log_event("death", {
                        **self._close_death_cycle(),
                        "location": self.read_m(0xD35E),
                        "reason": "party inteira sem HP fora de batalha",
                    })
                self.last_hp_check = not all_fainted
        
        # Update battle state
        if is_in_battle and not self.in_battle:
            # Battle just started - record info
            battle_info = self._get_battle_info()
            if battle_info:
                self.battle_sequence += 1
                self.last_battle_decision_key = None
                self.capture_plan = []
                self.capture_bag_open = False
                # None means "this battle still needs a plan". Setting it to the
                # sequence number marked every fight as already planned, so the
                # menu controller never built one: four trainers decided to
                # capture 83 times between them, threw zero balls, and the
                # feed showed only decisions and knockouts.
                self.capture_plan_battle = None
                self.capture_in_flight = False
                self.capture_attempts = 0
                self.capture_forced = False
                self.capture_result_steps = 0
                self.capture_balls_before_attempt = None
                self.battle_action_mode = "attack"
                self.last_battle_enemy_hp = None
                self.last_battle_player_hp = None
                self.last_battle_map_id = int(self.read_m(0xD35E))
                self.battle_party_count_before = len(self.get_party_info())
                self.battle_pokedex_owned_before = self._pokedex_owned_count()
                # What the bot meant to do with this encounter, kept for the
                # end of the battle. A decision without an outcome cannot be
                # read: "quis capturar" and "capturou" are different facts.
                self.battle_capture_intent = None
                self.battle_balls_before = self._poke_ball_count()
                self.last_battle_enemy_id = battle_info.get('enemy_id', 0)
                # Check if trainer battle (0xD057 bit 1)
                battle_type = self.read_m(0xD057)
                self.last_battle_is_trainer = (battle_type & 0b00000010) != 0
                self._log_event("battle_started", {
                    "battle": "trainer" if self.last_battle_is_trainer else "wild",
                    "enemy_id": battle_info.get("enemy_id"),
                    "enemy_species_id": battle_info.get("enemy_species_id"),
                    "enemy_level": battle_info.get("enemy_level"),
                    "encounter_type": battle_info.get("encounter_type"),
                    "encounter_label": battle_info.get("encounter_label"),
                    "map_name": battle_info.get("map_name"),
                    "active_pokemon": battle_info.get("active_pokemon"),
                    "pokeballs": self._poke_ball_count(),
                    "shiny_candidate": battle_info.get("shiny_candidate", False),
                }, live=self.last_battle_is_trainer)

                if not self.last_battle_is_trainer:
                    capture_policy = self._capture_policy(battle_info)
                    self.last_capture_policy = capture_policy
                    if capture_policy.get("shiny_candidate"):
                        self._log_event("rare_encounter", {
                            "enemy_id": battle_info.get("enemy_id"),
                            "enemy_species_id": battle_info.get("enemy_species_id"),
                            "enemy_level": battle_info.get("enemy_level"),
                            "rarity": "gen2_shiny_dvs",
                            "title": "Encontro compatível com shiny",
                            "reason": battle_info.get("shiny_note"),
                            "dvs": battle_info.get("dvs"),
                            "capture_unlocked": capture_policy.get("capture_unlocked"),
                            "pokeballs": capture_policy.get("pokeballs"),
                        })
                    decision_key = (
                        battle_info.get("enemy_species_id"),
                        capture_policy.get("reason_code"),
                        battle_info.get("map_id"),
                    )
                    decision_is_new = decision_key not in self.announced_capture_decisions
                    self.announced_capture_decisions.add(decision_key)
                    self.battle_capture_intent = {
                        "choice": capture_policy.get("choice"),
                        "reason_code": capture_policy.get("reason_code"),
                        "reason": capture_policy.get("reason"),
                        "enemy_species_id": battle_info.get("enemy_species_id"),
                        "enemy_level": battle_info.get("enemy_level"),
                        "shiny_candidate": capture_policy.get("shiny_candidate", False),
                    }
                    # Decisão de derrota de selvagem fica no JSONL, não no feed:
                    # com a fuga ativa, cada novo inimigo "decidiu derrotar" e
                    # enchia a janela de 30 — o feed parecia atrasado por reenviar
                    # a mesma fila de decisões. Só captura e shiny merecem o feed.
                    self._log_event("capture_decision", {
                        "enemy_id": battle_info.get("enemy_id"),
                        "enemy_species_id": battle_info.get("enemy_species_id"),
                        "enemy_level": battle_info.get("enemy_level"),
                        **capture_policy,
                    }, live=(
                        capture_policy.get("choice") == "capture"
                        or capture_policy.get("shiny_candidate", False)
                    ))
                self._log_training_target(battle_info)
        
        self.in_battle = is_in_battle
        if self.deaths > deaths_before or getattr(self, "whiteout_pending", False):
            self._invalidate_current_checkpoint()
            self._save_whiteout_checkpoint()

    def _trail_ready_to_inherit(self):
        """Is there already a walked path for this trainer's own objective?

        The head start exists for one reason: somebody has to cross the map
        first, or two bots discover it at the same time and the published path
        is never tested. A step count is a bad way to say that — it is a guess
        at how long a crossing takes, and 1500 steps is seven minutes of a bot
        standing still at the rate two slots actually run.

        The condition the number was standing in for is checkable: a dense
        trail for this quest exists, so there is something to inherit. Once it
        does, the rest of the wait buys nothing.
        """
        quest_id = getattr(self, "active_quest_id", None)
        if not quest_id:
            return False
        node = self.quest_graph.nodes_by_id.get(quest_id)
        executor = getattr(node, "executor", None)
        store = getattr(getattr(self, "scripted_agent", None), "trail_store", None)
        if not executor or store is None:
            return False
        try:
            return bool(store.read(executor).get("dense"))
        except Exception:
            return False

    def _close_death_cycle(self):
        """Number the attempt that just ended, and start the next one.

        Dying is not a stumble in the middle of a route: the cartridge puts the
        trainer back at the Center and the crossing starts over from there.
        Unnumbered, attempt 1 and attempt 2 are one blurred walk and there is no
        saying what either cost. The trail recorded so far goes with it — the
        approach that lost the fight is not the way through, and publishing it
        would hand the follower the detour as if it were the route.
        """
        self.death_cycle = getattr(self, "death_cycle", 0) + 1
        self._persist_journey_memory()
        agent = getattr(self, "scripted_agent", None)
        steps = 0
        if agent is not None and hasattr(agent, "begin_death_cycle"):
            try:
                steps = agent.begin_death_cycle(self.death_cycle)
            except Exception as error:
                print(f"[{self.agent_name}] Trail Error: {error}")
        return {
            "total_deaths": self.deaths,
            "death_cycle": self.death_cycle,
            "quest_id": self.active_quest_id,
            "steps_in_cycle": steps,
        }

    def _commit_resume_state(self, label, state_bytes):
        """Gravar o par estado+manifesto de forma que matar no meio não custe o save.

        A ordem antiga era: renomeia `current.state`, depois renomeia o
        manifesto. Matar o processo **entre os dois** deixa o estado novo com o
        manifesto velho, o sha256 não bate, a retomada é recusada, e o
        emulador cai no estado de partida. CARON perdeu a jornada assim duas
        vezes num dia — as duas quando eu derrubei a corrida para aplicar
        conserto.

        Agora o estado vai para um arquivo com o nome derivado do próprio
        conteúdo, e o manifesto é o **único** ponto de commit: enquanto ele não
        troca, o par antigo continua inteiro e válido. Um arquivo órfão custa
        160 KB; um save perdido custa a corrida.
        """
        digest = hashlib.sha256(state_bytes).hexdigest()
        state_name = f"resume-{digest[:16]}.state"
        state_path = self.trainer_dir / state_name

        if not state_path.exists():
            temporary = state_path.with_suffix(state_path.suffix + ".tmp")
            with open(temporary, "wb") as state_file:
                state_file.write(state_bytes)
                state_file.flush()
                os.fsync(state_file.fileno())
            os.replace(temporary, state_path)

        manifest_path = self.trainer_dir / CURRENT_STATE_MANIFEST
        manifest_temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
        with open(manifest_temporary, "w", encoding="utf-8") as manifest_file:
            json.dump({
                "checkpoint": label,
                "state": state_name,
                "sha256": digest,
                "generation": self.checkpoint_generation,
            }, manifest_file)
            manifest_file.flush()
            os.fsync(manifest_file.fileno())
        os.replace(manifest_temporary, manifest_path)

        # `current.state` continua existindo para quem lê de fora — ferramentas,
        # sondas, o operador. Ele não é mais a autoridade, então escrevê-lo
        # depois do commit não arrisca nada.
        try:
            (self.trainer_dir / "current.state").write_bytes(state_bytes)
        except OSError:
            pass
        self._prune_resume_states(keep=state_name)
        return True

    def _prune_resume_states(self, keep, survivors=3):
        """Apagar estados antigos, menos o vigente e os poucos mais recentes."""
        try:
            arquivos = sorted(
                self.trainer_dir.glob("resume-*.state"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for path in arquivos[survivors:]:
            if path.name == keep:
                continue
            try:
                path.unlink()
            except OSError:
                pass

    def _invalidate_current_checkpoint(self):
        """Prevent a pre-death checkpoint from being loaded on restart."""
        trainer_dir = getattr(self, "trainer_dir", None)
        if trainer_dir is None:
            return
        manifest_path = trainer_dir / CURRENT_STATE_MANIFEST
        try:
            manifest_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _save_whiteout_checkpoint(self):
        """Preserve a real post-whiteout Center position, never the loss state."""
        try:
            map_id = int(self.read_m(0xD35E))
        except Exception:
            return
        if map_id not in POKEMON_CENTER_MAP_IDS:
            return
        party = self.get_party_info()
        if not party or not all(
            int(mon.get("hp") or 0) >= int(mon.get("max_hp") or 0) > 0
            for mon in party
        ):
            return
        if self._save_checkpoint(f"center_{map_id}"):
            self.whiteout_pending = False

    def _save_checkpoint(self, milestone):
        """Save only a Pokémon Center state, healed or not."""
        if not str(milestone).startswith("center_"):
            return False
        checkpoint_file = self.checkpoint_dir / f"{milestone}.state"
        try:
            state = BytesIO()
            self.pyboy.save_state(state)
            state_bytes = state.getvalue()
            temporary = checkpoint_file.with_suffix(checkpoint_file.suffix + ".tmp")
            with open(temporary, "wb") as state_file:
                state_file.write(state_bytes)
                state_file.flush()
                os.fsync(state_file.fileno())
            os.replace(temporary, checkpoint_file)
            # The bytes above already contain every quest observed so far, so
            # stamping the manifest one generation ahead is what seals them:
            # a completion recorded at generation N is proven by any checkpoint
            # numbered above N.
            self.checkpoint_generation = int(
                getattr(self, "checkpoint_generation", 0)
            ) + 1
            self._commit_resume_state(milestone, state_bytes)
            print(f"[{self.agent_name}] Checkpoint saved: {milestone}")
            self.saved_checkpoint_milestones.add(milestone)
            # Persist the sealed generation with the journey: the manifest and
            # journey.json have to come back from a crash agreeing on it.
            self._persist_journey_memory()
            return True
        except Exception as e:
            print(f"[{self.agent_name}] Checkpoint save failed: {e}")
            return False

    def _state_is_center_after_heal(self):
        """Accept a resume state only inside a Center with a full party."""
        try:
            if int(self.read_m(0xD35E)) not in POKEMON_CENTER_MAP_IDS:
                return False
            party = self.get_party_info()
            return bool(party) and all(
                int(mon.get("hp") or 0) >= int(mon.get("max_hp") or 0) > 0
                for mon in party
            )
        except Exception:
            return False
    
    def _load_current_checkpoint(self):
        """Load only the current checkpoint explicitly written by this code.

        There is deliberately no fallback to ``center_*.state`` or any older
        milestone. A stale ``current.state`` is ignored before PyBoy sees it,
        so a death can never be replaced by a historical position.
        """
        manifest_path = self.trainer_dir / CURRENT_STATE_MANIFEST
        if not manifest_path.exists():
            return self._load_last_center_checkpoint()
        try:
            with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                manifest = json.load(manifest_file)
            # O manifesto nomeia o arquivo, e o nome vem do conteúdo. Jornadas
            # antigas apontam para `current.state`, que continua servindo.
            state_name = str(manifest.get("state") or "")
            if not state_name or "/" in state_name or state_name.startswith("."):
                return False
            current_state = self.trainer_dir / state_name
            if not current_state.exists():
                return self._load_last_center_checkpoint()
            state_bytes = current_state.read_bytes()
            if hashlib.sha256(state_bytes).hexdigest() != manifest.get("sha256"):
                return False
            with BytesIO(state_bytes) as state_file:
                self.pyboy.load_state(state_file)
            # The manifest travels with the bytes, so it — not journey.json —
            # says which generation this emulator is actually at.
            self.checkpoint_generation = int(manifest.get("generation", 0) or 0)
            self._checkpoint_loaded_from_disk = True
            print(f"[{self.agent_name}] ✅ Loaded explicit current checkpoint")
            return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return self._load_last_center_checkpoint()

    def _load_last_center_checkpoint(self):
        """Fall back to the newest Center checkpoint, never to a new game.

        Refusing every state is not the safe option it sounds like: a trainer
        with a level 18 Ivysaur woke up in Oak's lab choosing a starter again,
        and the journey file still claimed five finished quests. A Center with
        a healed party is exactly where a whiteout would have left the run, so
        resuming there costs nothing that dying would not have cost already.
        """
        newest = None
        try:
            for candidate in self.checkpoint_dir.glob("center_*.state"):
                if newest is None or candidate.stat().st_mtime > newest.stat().st_mtime:
                    newest = candidate
        except OSError:
            return False
        if newest is None:
            return False
        try:
            with open(newest, "rb") as state_file:
                self.pyboy.load_state(state_file)
        except (OSError, ValueError):
            return False
        # Um `center_*.state` sem manifesto não prova o avanço por si — mas o
        # journey carrega a última geração selada, e zerá-la reabria quests
        # que a RAM ainda prova. Medido (2026-08-12): a retomada pelo Centro
        # devolveu o FARON ao `buy_pokeballs` (bolas gastas no farm) e o bot
        # quicou entre Pewter e a Rota 2 indo comprar em Viridian. A geração
        # do journey é o melhor sinal disponível; cada quest lembrada continua
        # tendo de responder à RAM de novo.
        self.checkpoint_generation = int(
            getattr(self, "journey_checkpoint_generation", 0) or 0
        )
        self._checkpoint_loaded_from_disk = True
        print(f"[{self.agent_name}] ♻️ Retomando do último Centro: {newest.name}")
        return True
    
    def _check_milestones(self):
        """Save one state, in the only place worth returning to.

        Milestones used to be scattered: party filled, parcel delivered, Pewter
        reached, Brock beaten. Any of them could be reloaded later and quietly
        rewind an hour of play — and dying reloaded too, which erased the loss
        instead of paying for it. A whiteout is part of the game and is left
        alone; the cartridge already carries the run back to a Center.

        What is worth keeping is a place a stuck run can be resumed from
        without cheating: inside a Center.

        Estar aqui basta. Antes o checkpoint exigia cura confirmada e time
        cheio, e isso amarrava a persistência a uma decisão de jogo: derrotar
        Surge sem levar dano e entrar no Centro a 100% não gravava nada,
        porque não havia o que curar. Com a cura automática cancelada em
        2026-08-07, essa exigência não sobrava nenhum checkpoint — o time
        nunca mais fica cheio por vontade própria.

        Retomar com o time machucado é aceitável por decisão do operador: um
        apagão durante o treino não é problema, e o cartucho reergue o time
        num Centro sozinho.
        """
        if self.in_battle:
            return
        scripted = getattr(self, "scripted_agent", None)
        if scripted is None:
            return
        try:
            map_id = int(self.read_m(0xD35E))
        except Exception:
            return
        if map_id not in POKEMON_CENTER_MAP_IDS:
            # Sair rearma: a próxima entrada neste mesmo Centro grava de novo,
            # com o progresso que houver. Gravar uma vez por Centro por jornada
            # congelava o ponto de retomada na primeira visita.
            self.center_checkpoint_armed = True
            return
        if not getattr(self, "center_checkpoint_armed", True):
            return
        party = self.get_party_info()
        if not party:
            return
        self.center_checkpoint_armed = False
        self._save_checkpoint(f"center_{map_id}")

    def _mark_golden_tiles(self):
        """Mark current seen tiles as golden in shared DB"""
        try:
            with sqlite3.connect(self.shared_db_path, timeout=10) as conn:
                cursor = conn.cursor()
                # Mark all locally seen tiles as golden
                for coord in self.seen_coords.keys():
                    cursor.execute("UPDATE tiles SET is_golden = 1 WHERE id = ?", (coord,))
                conn.commit()
            print(f"[{self.agent_name}] 🌟 GOLDEN PATH ESTABLISHED! Tiles marked for 3x reward.")
        except Exception as e:
            print(f"[{self.agent_name}] ⚠️ Failed to mark golden tiles: {e}")

    def _persist_center_checkpoints(self):
        """Persist nurse-dialogue checkpoints, never emulator state."""
        scripted = getattr(self, "scripted_agent", None)
        if scripted is None:
            return
        changed = False
        for attribute, milestone in (
            ("viridian_center_checkpoint_confirmed", "viridian_center_healed"),
            ("pewter_center_checkpoint_confirmed", "pewter_center_healed"),
        ):
            if getattr(scripted, attribute, False) and milestone not in self.announced_story_milestones:
                self.announced_story_milestones.add(milestone)
                changed = True
        if changed:
            self._persist_journey_memory()

    def _track_healing(self, current_party):
        """Report a real heal, confirmed by HP in RAM.

        Walking into a Center and coming out is not evidence of anything: the
        nurse dialogue can be skipped, and the pair spent a whole crossing at
        1 HP with nothing in the feed either way. What counts is party HP
        going from damaged to full while out of battle.
        """
        if self.in_battle or not current_party:
            return
        before = getattr(self, "last_party_info", []) or []
        if len(before) != len(current_party):
            return

        def damaged(party):
            return sum(
                max(int(mon.get("max_hp") or 0) - int(mon.get("hp") or 0), 0)
                for mon in party
            )

        missing_before = damaged(before)
        if missing_before <= 0:
            return
        if damaged(current_party) > 0:
            return
        # A whiteout also restores full HP, and it is a defeat, not care taken.
        # `death` owns that story; this event is only for a heal that was paid
        # for by walking to the counter.
        if any(int(mon.get("hp") or 0) == 0 for mon in before):
            return

        map_id = int(self.read_m(0xD35E))
        map_name = self._map_name(map_id)
        self.heal_count = getattr(self, "heal_count", 0) + 1
        self._log_event("healed", {
            "hp_restored": missing_before,
            "party": current_party,
            "party_size": len(current_party),
            "map_id": map_id,
            "map_name": map_name,
            "source": (
                "pokemon_center"
                if "center" in str(map_name).lower()
                else "item_or_event"
            ),
            "total_heals": self.heal_count,
            "reason": (
                f"HP da equipe voltou ao máximo ({missing_before} pontos) "
                f"fora de batalha em {map_name}"
            ),
        })
        # A full heal in a room the game calls a Center, on a map this project
        # does not list as one, is a checkpoint that was never written. Map 68
        # — the Center at the mouth of Mt. Moon — sat outside
        # `POKEMON_CENTER_MAP_IDS` while an executor talked to its nurse in a
        # branch of its own, so the hardest stretch reached so far was the one
        # with no resume point, and nothing anywhere said so. Silence is what
        # made that cost a day; say it instead.
        if (
            "center" in str(map_name).lower()
            and map_id not in POKEMON_CENTER_MAP_IDS
        ):
            self._log_event("unknown_center", {
                "map_id": map_id,
                "map_name": map_name,
                "reason": (
                    "cura confirmada num Centro que não está em "
                    "POKEMON_CENTER_MAP_IDS: nenhum checkpoint foi gravado aqui"
                ),
            })

        # The panel shows HP bars; a full party is worth publishing at once.
        self._update_agent_state()

    def _track_party_changes(self):
        """Track Level Ups, Captures and Party Swaps"""
        try:
            current_party = self.get_party_info()
            current_pokedex_owned = self._pokedex_owned_count()
            
            if not self.party_tracking_initialized:
                self.last_party_info = current_party
                self.last_pokedex_owned = current_pokedex_owned
                self.party_tracking_initialized = True
                return

            self._track_healing(current_party)

            evolution_detected = False

            # Check for Level Up
            for i, mon in enumerate(current_party):
                if i < len(self.last_party_info):
                    last_mon = self.last_party_info[i]
                    
                    # Same species, higher level
                    if mon['species_id'] == last_mon['species_id']:
                        if mon['level'] > last_mon['level']:
                            self.level_up_count += 1
                            self._log_event("level_up", {
                                "pokemon": mon, 
                                "old_level": last_mon['level'],
                                "new_level": mon['level'],
                                "training_target": mon,
                                "reason": "ganhou experiência enquanto estava ativo",
                            })

                        previous_moves = [
                            move.get("id") for move in last_mon.get("moves", [])
                            if move.get("id")
                        ]
                        current_moves = [
                            move.get("id") for move in mon.get("moves", [])
                            if move.get("id")
                        ]
                        if previous_moves != current_moves:
                            removed = list((Counter(previous_moves) - Counter(current_moves)).elements())
                            learned = list((Counter(current_moves) - Counter(previous_moves)).elements())
                            self._log_event("move_learned", {
                                "pokemon": mon,
                                "learned_move_id": learned[0] if learned else None,
                                "replaced_move_id": removed[0] if removed else None,
                                "moves_before": previous_moves,
                                "moves_after": current_moves,
                                "reason": "build alterada e confirmada diretamente na RAM da party",
                            })
                    elif mon.get('species_id') and last_mon.get('species_id'):
                        evolution_detected = True
                        self.evolution_count += 1
                        self._log_event("evolution", {
                            "old_pokemon": last_mon,
                            "new_pokemon": mon,
                            "reason": "espécie do slot mudou após evolução confirmada pela RAM",
                        })

            previous_ids = Counter(
                mon.get("internal_id", mon.get("species_id"))
                for mon in self.last_party_info
            )
            current_ids = Counter(
                mon.get("internal_id", mon.get("species_id"))
                for mon in current_party
            )
            added_ids = current_ids - previous_ids
            new_mon = next(
                (
                    mon for mon in current_party
                    if added_ids.get(mon.get("internal_id", mon.get("species_id")), 0) > 0
                ),
                None,
            )

            # A capture may go directly to the PC when the party has six
            # members, so party length alone is insufficient. Combine the
            # party diff with the real Pokédex counter and exclude evolution.
            party_addition = new_mon is not None and len(current_party) > len(self.last_party_info)
            confirmed_pc_capture = (
                current_pokedex_owned > self.last_pokedex_owned
                and bool(self.last_capture_policy)
                and self.last_capture_policy.get("choice") == "capture"
            )
            capture_detected = (
                (party_addition or confirmed_pc_capture)
                and not evolution_detected
            )
            if capture_detected:
                is_starter = (
                    not self.last_party_info
                    and self.last_pokedex_owned == 0
                    and current_pokedex_owned <= 1
                )
                if is_starter:
                    self._log_event("starter_selected", {
                        "pokemon": new_mon or current_party[0],
                        "decision": "starter_confirmed",
                        "reason": "primeiro Pokémon detectado na party durante o início real da jornada",
                    })
                else:
                    self.capture_count += 1
                    # Publish the new team right away: this is the moment the
                    # panel is worth looking at, and the periodic snapshot can
                    # be dozens of steps away.
                    self._update_agent_state()
                    result = "party" if len(current_party) > len(self.last_party_info) else "pc"
                    capture_policy = self.last_capture_policy or {}
                    self._log_event("capture", {
                        "pokemon": new_mon or {"species_id": None},
                        "count": current_pokedex_owned,
                        "nickname": (new_mon or {}).get('name', 'Unknown'),
                        "result": result,
                        "decision": "capture_confirmed",
                        "reason": capture_policy.get(
                            "reason", "mudança confirmada pela party/Pokédex na RAM"
                        ),
                        "reason_code": capture_policy.get("reason_code"),
                        "motivation": capture_policy.get("motivation"),
                        "new_species": capture_policy.get("new_species"),
                        "upgrade_candidate": capture_policy.get("upgrade_candidate"),
                        "shiny_candidate": capture_policy.get("shiny_candidate", False),
                        "party_size": len(current_party),
                    })

            # Check for Party Changes (PC Deposit)
            if len(current_party) < len(self.last_party_info):
                 self._log_event("pc_deposit", {
                     "size": len(current_party),
                     "reason": "party diminuiu; Pokémon provavelmente foi enviado ao PC",
                 })
            
            self.last_party_info = current_party
            self.last_pokedex_owned = current_pokedex_owned
        except Exception as e:
            self._log_event("telemetry_error", {
                "source": "party_tracking",
                "error": str(e),
            }, live=False)

    def _periodic_save(self):
        """Do not write arbitrary emulator positions as resume points.

        The regular step loop already checks for a verified Center heal. This
        hook remains for callers that still trigger the old periodic cadence,
        but it intentionally performs no state save.
        """
        return None

    def _manual_save(self, timestamp):
        """Keep manual-save compatibility without creating unsafe states."""
        self._check_milestones()

    def _write_resume_state(self, label):
        """Write current.state plus its manifest, wherever the run happens to be.

        This is the end-of-session save: the next start continues from here.
        It is deliberately the *only* other writer besides the Center
        checkpoint, and nothing reads it mid-run — a bot that gets stuck has to
        walk out of it, not be rewound into a better position.
        """
        try:
            with BytesIO() as state:
                self.pyboy.save_state(state)
                state_bytes = state.getvalue()
            self.checkpoint_generation = int(
                getattr(self, "checkpoint_generation", 0)
            ) + 1
            return self._commit_resume_state(label, state_bytes)
        except Exception as error:
            print(f"[{self.agent_name}] Resume state save failed: {error}")
            return False

    def close(self):
        """Persist the journey and where it stopped, so the next run resumes."""
        # Uma sequência repetida em aberto perderia a contagem no fim da sessão.
        self._flush_repeated_event()
        # State first: writing it seals a new generation, and journey.json has
        # to go to disk carrying that number, not the one before it.
        self._write_resume_state("session_end")
        self._persist_journey_memory()
        print(f"[{self.agent_name}] 💾 Estado final salvo para retomada")
        return super().close()


    def _str_to_action(self, s):
        """
        Convert string action to env action index.
        Valid actions indices (from red_gym_env_v2.py):
        0: DOWN, 1: LEFT, 2: RIGHT, 3: UP, 4: A, 5: B, 6: START
        """
        return name_to_action(s, default=GameAction.A)



if __name__ == "__main__":
    # Test hybrid environment
    from pathlib import Path
    
    env_config = {
        'headless': False,  # Show window for testing
        'save_final_state': False,
        'early_stop': False,
        'action_freq': 24,
        'init_state': '../init.state',
        'max_steps': 2048 * 10,
        'print_rewards': True,
        'save_video': False,
        'session_path': Path('test_hybrid'),
        'gb_path': '../PokemonRed.gb',
        'debug': True,
        'reward_scale': 0.5,
        'explore_weight': 0.25
    }
    
    env = HybridGymEnv(env_config)
    
    print("Testing Hybrid Environment...")
    print("RL will handle exploration, LLM will handle battles")
    
    obs = env.reset()
    
    for step in range(1000):
        # Random action (RL would choose smart action)
        import random
        action = random.randint(0, 7)
        
        obs, reward, done, truncated, info = env.step(action)
        
        if done:
            print("Episode finished!")
            break
    
    env.close()
