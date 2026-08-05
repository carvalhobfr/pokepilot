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
import sqlite3
import math
import time
# Add project root to path so we can import src.llm_agent
project_root = str(Path(__file__).parent.parent.absolute())
if project_root not in sys.path:
    sys.path.append(project_root)

from src.simple_battle import SimpleBattleAgent
from src.scripted_agent import ScriptedAgent
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
from game_actions import GameAction, NOOP_ACTION, event_to_action, name_to_action
from quest_graph import LiveQuestState, QuestGraph
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
MAJOR_LOCATION_IDS = set(range(0, 11))
BATTLE_MENU_SAVED_ITEM_ADDRESS = 0xCC2D
CAPTURE_RESULT_ADVANCE_STEPS = 18

# Small, explicit Gen I strategy prior. Level still drives the general upgrade
# heuristic; these values cover species whose utility is not obvious from the
# encounter level alone (typing, evolution potential or rarity).
# A Gen I team is six. Below that, an empty slot is a weakness in itself.
PARTY_TARGET = 6

# Soften the target before spending a ball, and never keep throwing while the
# active Pokémon is about to faint.
CAPTURE_HP_THRESHOLD = 0.5
SELF_PRESERVATION_HP = 0.35

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
            starter_choice=self.starter_preference
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
        
        # Resume is opt-in. Otherwise the selected CLI state is the true start.
        if self.resume_state and not self._load_best_checkpoint():
            print(f"[{self.agent_name}] No checkpoint found – starting from the selected state")
        
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
        self.capture_count = 0
        self.capture_enabled = bool(config.get("capture_enabled", True))
        self.capture_plan = []
        self.capture_plan_battle = None
        self.capture_in_flight = False
        self.capture_attempts = 0
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

        # `--resume` selects the external autosave only for the first episode.
        # On PPO rollout resets, the process-scoped carry state above is newer;
        # loading the old autosave again would silently rewind the journey.
        if self.resume_state and not carry_journey and self._load_best_checkpoint():
            obs = self.refresh_after_external_state_load()

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
        self.capture_result_steps = 0
        self.capture_balls_before_attempt = None
        self.battle_action_mode = "attack"
        self.last_capture_policy = None

        # Recompute the active story node after every reset or external state
        # load. The save is the source of truth; scripts never advance the
        # story by elapsed time or by claiming that they are finished.
        self._sync_quest_objective()
            
        return obs, info

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
        for candidate in self.quest_graph.nodes:
            if candidate.id in self.quest_completed_ids:
                continue
            if self.quest_graph.node_matches(candidate, state):
                self.quest_completed_ids.add(candidate.id)
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
            self.agent_paused = bool(agent_control.get("paused", False))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # The relay writes atomically, but keeping the previous state is
            # safer than changing speed due to a transient read failure.
            pass

    def _apply_playback_throttle(self, step_started_at):
        """Throttle the synchronous vector loop to Game Boy wall-clock speed.

        A Game Boy runs at about 60 frames/s. Each environment action advances
        `act_freq` frames. DummyVecEnv steps agents sequentially, so each agent
        contributes only its share of the target vector-step duration.
        Speed 0 means explicit uncapped training mode.
        """
        if self.playback_speed <= 0:
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
            if self.task_file.exists():
                try:
                    with open(self.task_file, 'r') as f:
                        task = f.read().strip().upper()
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
        if self.steps_elapsed < self.delay_steps:
            self.steps_elapsed += 1
            if self.steps_elapsed == self.delay_steps:
                print(f"[{self.agent_name}] 🏁 RACE START! Joining the competition!")
            elif self.steps_elapsed % 600 == 0:  # Log every 10 seconds
                remaining = (self.delay_steps - self.steps_elapsed) / 60
                print(f"[{self.agent_name}] ⏳ Waiting... {remaining:.0f}s remaining")
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
            battle_action_str = self._next_capture_action()
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
                action = name_to_action(cmd)
                action_source = "manual"
            
            elif self.current_task.startswith("QUEST"):
                action_source = "quest_controller"
                # Delegate to ScriptedAgent
                try:
                    # Extract quest name (e.g., "QUEST: OAK_EVENT")
                    quest_name = self.current_task.split(":")[1].strip().lower()
                    supported = (
                        quest_name in self.scripted_agent.walkthrough.get("game_flow", {})
                        or hasattr(self.scripted_agent, f"_run_{quest_name}")
                    )
                    script_action = (
                        self.scripted_agent.step(quest_name)
                        if supported
                        else None
                    )
                    
                    if script_action is not None:
                        # Convert PyBoy WindowEvent to RL Action
                        action = self._convert_llm_to_rl_action(script_action)
                    else:
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
        import fcntl
        
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
        }
        
        # Write back (with file locking to avoid race conditions)
        try:
            with open(state_file, 'w') as f:
                # Try to lock file (non-blocking)
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    json.dump(all_states, f)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except IOError:
                    pass # Skip update if locked
        except:
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

    def _select_capture_ball(self, shiny_candidate=False):
        inventory = self._capture_ball_inventory()
        priority = (1, 2, 3, 4) if shiny_candidate else (4, 3, 2, 1)
        return next(
            (item for item_id in priority for item in inventory if item["item_id"] == item_id),
            None,
        )

    def _battle_menu_path_to_item(self):
        """Navigate the remembered 2x2 battle menu cursor to ITEM safely."""
        try:
            saved_item = int(self.read_m(BATTLE_MENU_SAVED_ITEM_ADDRESS))
        except Exception:
            saved_item = 0
        return {
            0: ["DOWN"],          # FIGHT -> ITEM
            1: ["LEFT", "DOWN"],  # PKMN -> FIGHT -> ITEM
            2: [],                # already on ITEM
            3: ["LEFT"],          # RUN -> ITEM
        }.get(saved_item, ["DOWN"])

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
        if quality["enemy_hp_fraction"] > CAPTURE_HP_THRESHOLD:
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

        if policy["choice"] != "capture":
            return None

        if self.capture_plan_battle != self.battle_sequence:
            ball_slot = policy.get("ball_slot")
            if ball_slot is None:
                return None
            # Reach ITEM from whichever battle-menu option is remembered,
            # open the Bag, clamp its cursor to the top, then select the real
            # inventory slot. This remains correct across shiny retries.
            self.capture_plan = (
                self._battle_menu_path_to_item()
                + ["A"]
                + (["UP"] * 20)
                + (["DOWN"] * ball_slot)
                + ["A"]
            )
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

        if self.capture_plan:
            action = self.capture_plan.pop(0)
            self.battle_action_mode = "capture"
            if not self.capture_plan:
                self.capture_in_flight = True
                self.capture_result_steps = CAPTURE_RESULT_ADVANCE_STEPS
                self.capture_balls_before_attempt = self._poke_ball_count()
            return action

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
            "pokeballs": balls,
            "collector": self.collector,
            "meta_score": self.meta_score,
            "new_species": capture_policy.get("new_species", False),
            "upgrade_candidate": capture_policy.get("upgrade_candidate", False),
            "shiny_candidate": capture_policy.get("shiny_candidate", False),
            "capture_unlocked": capture_policy.get("capture_unlocked", False),
            "controller": "SimpleBattleAgent",
            "capture_controller": self.battle_action_mode == "capture",
        })

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
            self.recent_events = self.recent_events[-30:]
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
            if self.last_battle_player_hp == 0 or not has_alive_pokemon:
                battle_result = "optional_loss" if optional_rival_loss else "loss"
            elif self.last_battle_is_trainer or self.last_battle_enemy_hp == 0:
                battle_result = "win"
            elif capture_confirmed:
                battle_result = "capture"
            else:
                battle_result = "escaped"
            self._log_event("battle_end", {
                "type": battle_kind,
                "result": battle_result,
                "enemy_id": self.last_battle_enemy_id,
                "active_pokemon": self.last_active_internal_id,
                "player_hp_at_end": self.last_battle_player_hp,
                "battle_map_id": self.last_battle_map_id,
                "end_map_id": int(self.read_m(0xD35E)),
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
                end_map_id = int(self.read_m(0xD35E))
                healed_during_warp = (
                    has_alive_pokemon
                    and self.last_battle_map_id is not None
                    and end_map_id != self.last_battle_map_id
                )
                if battle_result == "loss" and healed_during_warp:
                    self.deaths += 1
                    self._log_event("death", {
                        "total_deaths": self.deaths,
                        "location": end_map_id,
                        "battle_location": self.last_battle_map_id,
                        "reason": "whiteout confirmado pela transição de mapa e cura automática",
                    })
            elif battle_result == "escaped":
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
                    self._log_event("death", {
                        "total_deaths": self.deaths,
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
                self.capture_plan_battle = self.battle_sequence
                self.capture_in_flight = False
                self.capture_attempts = 0
                self.capture_result_steps = 0
                self.capture_balls_before_attempt = None
                self.battle_action_mode = "attack"
                self.last_battle_enemy_hp = None
                self.last_battle_player_hp = None
                self.last_battle_map_id = int(self.read_m(0xD35E))
                self.battle_party_count_before = len(self.get_party_info())
                self.battle_pokedex_owned_before = self._pokedex_owned_count()
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
                    self._log_event("capture_decision", {
                        "enemy_id": battle_info.get("enemy_id"),
                        "enemy_species_id": battle_info.get("enemy_species_id"),
                        "enemy_level": battle_info.get("enemy_level"),
                        **capture_policy,
                    }, live=(
                        decision_is_new
                        or capture_policy.get("choice") == "capture"
                        or capture_policy.get("shiny_candidate", False)
                    ))
                self._log_training_target(battle_info)
        
        self.in_battle = is_in_battle

    def _save_checkpoint(self, milestone):
        """Save game state at important milestones"""
        checkpoint_file = self.checkpoint_dir / f"{milestone}.state"
        try:
            with open(checkpoint_file, 'wb') as f:
                self.pyboy.save_state(f)
            print(f"[{self.agent_name}] Checkpoint saved: {milestone}")
            self.saved_checkpoint_milestones.add(milestone)
        except Exception as e:
            print(f"[{self.agent_name}] Checkpoint save failed: {e}")
    
    def _load_best_checkpoint(self):
        """Load most recent save (PRIORIDADE: autosave > milestones)"""
        
        # 1. FIRST: Try to load autosave.state (most recent progress)
        autosave_path = self.trainer_dir / "current.state"
        if autosave_path.exists():
            try:
                with open(autosave_path, 'rb') as f:
                    self.pyboy.load_state(f)
                print(f"[{self.agent_name}] ✅ Loaded AUTO-SAVE (most recent progress)")
                return True
            except Exception as e:
                print(f"[{self.agent_name}] ⚠️ Auto-save corrupted, trying fallback: {e}")
        
        # 2. FALLBACK: Load milestone checkpoints if autosave not found
        # Priority: brock_defeated > pewter_reached > parcel_delivered > oak_done
        milestones = ["brock_defeated", "pewter_reached", "parcel_delivered", "oak_done"]
        
        for milestone in milestones:
            checkpoint_file = self.checkpoint_dir / f"{milestone}.state"
            if checkpoint_file.exists():
                try:
                    with open(checkpoint_file, 'rb') as f:
                        self.pyboy.load_state(f)
                    print(f"[{self.agent_name}] 🏁 Loaded CHECKPOINT: {milestone}")
                    self.current_milestone = milestone
                    return True
                except:
                    pass
        
        return False  # No save found, start from beginning
    
    def _check_milestones(self):
        """Check and save checkpoints at key milestones"""
        # Check party count for Oak Event completion
        party_count = self.read_m(0xD163)
        if party_count > 0 and "oak_done" not in self.saved_checkpoint_milestones:
            self._save_checkpoint("oak_done")
        
        # Check if delivered parcel (got Pokedex)
        has_pokedex = self._capture_story_complete()
        if has_pokedex and "parcel_delivered" not in self.saved_checkpoint_milestones:
            self._save_checkpoint("parcel_delivered")
            
            # If Khalliss, mark tiles as golden!
            # if self.is_khalliss:
            #     self._mark_golden_tiles()
        
        # Check if reached Pewter City (Map ID 2)
        map_id = self.read_m(0xD35E)
        if map_id == 2 and "pewter_reached" not in self.saved_checkpoint_milestones:
            self._save_checkpoint("pewter_reached")
        
        # Check if defeated Brock
        has_boulder_badge = (self.read_m(0xD356) & 0b00000001) != 0
        if has_boulder_badge and "brock_defeated" not in self.saved_checkpoint_milestones:
            self._save_checkpoint("brock_defeated")

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
        """Save auto-save checkpoint (PRIORITÁRIO ao carregar)"""
        try:
            # Save to autosave.state (single file, always most recent)
            autosave_path = self.trainer_dir / "current.state"
            autosave_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save current state
            with open(autosave_path, "wb") as f:
                self.pyboy.save_state(f)
            
            # Quiet - only log occasionally
            if hasattr(self, 'step_count') and self.step_count % 6000 == 0:  # Every ~100s
                print(f"[{self.agent_name}] 💾 Auto-save updated")
                    
        except Exception as e:
            print(f"[{self.agent_name}] ⚠️ Failed auto-save: {e}")

    def _manual_save(self, timestamp):
        """Save manual checkpoint triggered by user"""
        try:
            filename = f"manual_{int(timestamp)}.state"
            path = self.checkpoint_dir / filename
            
            # Save current state
            with open(path, "wb") as f:
                self.pyboy.save_state(f)
            
            print(f"[{self.agent_name}] ✅ Manual Save Complete: {filename}")
                    
        except Exception as e:
            print(f"[{self.agent_name}] ⚠️ Failed to perform manual save: {e}")

    def close(self):
        """Persist the newest emulator state before PyBoy exports the .sav."""
        pyboy = getattr(self, "pyboy", None)
        if pyboy is not None:
            try:
                current_state = self.trainer_dir / "current.state"
                current_state.parent.mkdir(parents=True, exist_ok=True)
                temporary = current_state.with_suffix(".state.tmp")
                with open(temporary, "wb") as state_file:
                    pyboy.save_state(state_file)
                temporary.replace(current_state)
                self._persist_journey_memory()
            except Exception as exc:
                print(f"[{self.agent_name}] Final state save failed: {exc}")
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
