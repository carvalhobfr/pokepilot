import json
from pathlib import Path
from pyboy.utils import WindowEvent
from src.agent import BaseAgent
import os
from datetime import datetime

from src.llm_agent import LLMAgent

from src.navigation import Navigation
from src.exploration_tracker import ExplorationTracker

class ScriptedAgent(BaseAgent):
    def __init__(self, walkthrough_path, emulator=None, player_name="AARON", save_dir=".", starter_choice=None):
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

        return self.get_action(None)

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

        return self._follow_route(
            "oak-rival-trigger",
            [(5, 4), (5, 10), (5, 12)],
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

        if not has_parcel:
            routes = {
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
                42: [(3, 5), (3, 8)],
                1: [(29, 21), (26, 21), (26, 30), (20, 30), (20, 36)],
                12: [
                    (10, 3), (8, 3), (8, 18), (9, 18), (9, 21),
                    (12, 21), (12, 24), (10, 24), (10, 36),
                ],
                0: [(10, 7), (9, 7), (9, 12), (12, 12), (12, 11)],
            }
            route = routes.get(map_id)
            if route:
                return self._follow_route(f"parcel-return-{map_id}", route)

        # A transition or story textbox can temporarily expose a map before
        # its coordinates settle. A advances text; the next frame re-routes.
        return WindowEvent.PRESS_BUTTON_A

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

        if map_id != 42:
            return WindowEvent.PRESS_BUTTON_A

        position = self.emulator.memory.get_player_pos()
        if position != (2, 5):
            return self._follow_route("buy-balls-mart", [(3, 7), (3, 5), (2, 5)])

        # The clerk is immediately to the left of the final route tile.
        if self.emulator.memory.read_byte(0xD52A) != 2:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_LEFT
        return self._buy_first_shop_item()

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
            routes[1] = (
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
        route = routes.get(map_id)
        if route:
            return self._follow_route(f"route2-{map_id}", route)
        return WindowEvent.PRESS_BUTTON_A

    def _run_viridian_forest_nav(self):
        """Cross Viridian Forest and reach Pewter using collision-safe paths."""
        map_id = int(self.emulator.memory.get_map_id())
        if map_id in (2, 54):
            return None

        if map_id in (0, 12, 1, 50) or (
            map_id == 13 and self.emulator.memory.get_player_pos()[1] > 20
        ):
            return self._run_route_2_nav()

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
        return WindowEvent.PRESS_BUTTON_A

    def _run_pewter_city_nav(self):
        """Walk to Pewter's Gym, rebuilding the route after a whiteout."""
        map_id = int(self.emulator.memory.get_map_id())
        if map_id == 54:
            return None
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
        return WindowEvent.PRESS_BUTTON_A

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

        if map_id == 68:
            # Register and use the Route 4 Center. The open->closed textbox
            # edge confirms the Nurse interaction without relying on a timer.
            position = self.emulator.memory.get_player_pos()
            if not getattr(self, "mt_moon_center_healed", False):
                if position != (3, 3):
                    return self._follow_route(
                        "mt-moon-center-nurse", [(3, 7), (3, 3)]
                    )
                menu_open = self._menu_is_open()
                if menu_open:
                    self.mt_moon_heal_dialog_opened = True
                    return WindowEvent.PRESS_BUTTON_A
                if getattr(self, "mt_moon_heal_dialog_opened", False):
                    self.mt_moon_center_healed = True
                else:
                    if int(self.emulator.memory.read_byte(0xD52A)) != 8:
                        self.last_action_was_move = True
                        return WindowEvent.PRESS_ARROW_UP
                    return WindowEvent.PRESS_BUTTON_A
            return self._follow_route(
                "mt-moon-center-exit", [(3, 3), (3, 7), (3, 8)]
            )

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
            if x < 20 and not getattr(self, "mt_moon_center_healed", False):
                return self._follow_route(
                    "mt-moon-to-center",
                    [(9, 16), (12, 16), (12, 6), (11, 6), (11, 5)],
                )
            if x < 20:
                return self._follow_route(
                    "mt-moon-enter-cave", [(11, 6), (18, 6), (18, 5)]
                )
            return self._follow_route(
                "mt-moon-to-cerulean",
                [
                    (24, 6), (24, 8), (35, 8), (35, 10), (61, 10),
                    (61, 8), (79, 8), (79, 10), (90, 10),
                ],
            )

        return WindowEvent.PRESS_BUTTON_A

    def _run_pokemon_center(self, route_prefix, healed_attribute):
        """Register a city Center through its real nurse dialogue."""
        position = self.emulator.memory.get_player_pos()
        if (
            not getattr(self, healed_attribute, False)
            and not self._party_needs_healing()
        ):
            setattr(self, healed_attribute, True)
        if not getattr(self, healed_attribute, False):
            if position != (3, 3):
                return self._follow_route(
                    f"{route_prefix}-nurse",
                    [(3, 7), (3, 3)],
                )
            menu_open = self._menu_is_open()
            dialog_attribute = f"{healed_attribute}_dialog_opened"
            if menu_open:
                setattr(self, dialog_attribute, True)
                return WindowEvent.PRESS_BUTTON_A
            if getattr(self, dialog_attribute, False):
                setattr(self, healed_attribute, True)
            else:
                if int(self.emulator.memory.read_byte(0xD52A)) != 8:
                    self.last_action_was_move = True
                    return WindowEvent.PRESS_ARROW_UP
                return WindowEvent.PRESS_BUTTON_A
        return self._follow_route(
            f"{route_prefix}-exit",
            [(3, 3), (3, 7), (3, 8)],
        )

    def _party_needs_healing(self):
        party_count = min(int(self.emulator.memory.get_party_count()), 6)
        for index in range(party_count):
            struct_start = 0xD16B + index * 44
            current_hp = (
                int(self.emulator.memory.read_byte(struct_start + 1)) << 8
            ) + int(self.emulator.memory.read_byte(struct_start + 2))
            max_hp = (
                int(self.emulator.memory.read_byte(struct_start + 34)) << 8
            ) + int(self.emulator.memory.read_byte(struct_start + 35))
            if current_hp < max_hp:
                return True
        return False

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
            if (
                not getattr(self, "cerulean_center_healed", False)
                and not self._party_needs_healing()
            ):
                self.cerulean_center_healed = True
            if not getattr(self, "cerulean_center_healed", False):
                return self._follow_route(
                    "cerulean-to-center",
                    [(0, 18), (19, 18), (19, 17)],
                )
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

        # A whiteout can return to Cerulean Center; unknown transient maps are
        # usually dialogue/cutscene states, where A is the safe progression.
        return WindowEvent.PRESS_BUTTON_A

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
            if (
                not getattr(self, "cerulean_gym_center_healed", False)
                and not self._party_needs_healing()
            ):
                self.cerulean_gym_center_healed = True
            if not getattr(self, "cerulean_gym_center_healed", False):
                return self._follow_route(
                    "cerulean-gym-heal",
                    [
                        (20, 0), (20, 12), (8, 12), (8, 18),
                        (19, 18), (19, 17),
                    ],
                )
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
        """Follow collision-safe waypoints and tolerate transition input lock."""
        if not waypoints:
            return None

        # Trainer victory lines, signs and story speech can remain open after
        # the battle flag clears. Advance them before issuing movement; waiting
        # for the stuck watchdog can otherwise re-talk to the same NPC.
        if self._menu_is_open():
            return WindowEvent.PRESS_BUTTON_A

        current_x, current_y = self.emulator.memory.get_player_pos()
        if getattr(self, "route_id", None) != route_id:
            self.route_id = route_id

            # A resumed save or a whiteout can enter a route in its middle.
            # Begin at the closest collision-safe waypoint instead of blindly
            # walking toward waypoint zero through walls. If standing exactly
            # on a waypoint, continue to the next one in route order.
            closest_index = min(
                range(len(waypoints)),
                key=lambda index: (
                    abs(current_x - int(waypoints[index][0]))
                    + abs(current_y - int(waypoints[index][1]))
                ),
            )
            on_waypoint = (current_x, current_y) == tuple(waypoints[closest_index])
            self.route_index = (
                min(closest_index + 1, len(waypoints) - 1)
                if on_waypoint
                else closest_index
            )
            self.route_last_position = None
            self.route_stuck_steps = 0

        current_position = (
            self.emulator.memory.get_map_id(),
            current_x,
            current_y,
        )
        if current_position == getattr(self, "route_last_position", None):
            self.route_stuck_steps += 1
        else:
            self.route_stuck_steps = 0
        self.route_last_position = current_position

        # Dialogue and map transitions temporarily ignore movement. Advance
        # text deterministically, then resume the same waypoint.
        if self.route_stuck_steps >= 4:
            self.route_stuck_steps = 0
            return WindowEvent.PRESS_BUTTON_A

        while (
            self.route_index < len(waypoints) - 1
            and (current_x, current_y) == tuple(waypoints[self.route_index])
        ):
            self.route_index += 1

        target_x, target_y = waypoints[min(self.route_index, len(waypoints) - 1)]
        self.last_action_was_move = True
        if current_x < target_x:
            return WindowEvent.PRESS_ARROW_RIGHT
        if current_x > target_x:
            return WindowEvent.PRESS_ARROW_LEFT
        if current_y < target_y:
            return WindowEvent.PRESS_ARROW_DOWN
        if current_y > target_y:
            return WindowEvent.PRESS_ARROW_UP

        # The final waypoint may be one tile beyond the visible map boundary;
        # repeat the last direction until the map transition is observable.
        if len(waypoints) >= 2:
            previous_x, previous_y = waypoints[-2]
            if target_x > previous_x:
                return WindowEvent.PRESS_ARROW_RIGHT
            if target_x < previous_x:
                return WindowEvent.PRESS_ARROW_LEFT
            if target_y > previous_y:
                return WindowEvent.PRESS_ARROW_DOWN
            if target_y < previous_y:
                return WindowEvent.PRESS_ARROW_UP
        return None

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
