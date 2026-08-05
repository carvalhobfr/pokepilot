"""
LLM Pokemon Agent using OpenAI API
Reads game state and decides actions based on the brock.json guide
"""

import os
import json
from pathlib import Path
from openai import OpenAI
from pyboy.utils import WindowEvent

class LLMPokemonAgent:
    def __init__(self, api_key=None, guide_path=None):
        """
        Initialize LLM Agent with OpenAI API
        """
        # Load API key from env or parameter
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key not found in environment or parameters")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = os.getenv('MODEL_SUMMARIZATION', 'gpt-4o-mini')
        
        # Load Brock Guide for context
        self.guide = {}
        if guide_path and Path(guide_path).exists():
            with open(guide_path, 'r') as f:
                self.guide = json.load(f)
        
        # Action mapping
        self.action_map = {
            "UP": WindowEvent.PRESS_ARROW_UP,
            "DOWN": WindowEvent.PRESS_ARROW_DOWN,
            "LEFT": WindowEvent.PRESS_ARROW_LEFT,
            "RIGHT": WindowEvent.PRESS_ARROW_RIGHT,
            "A": WindowEvent.PRESS_BUTTON_A,
            "B": WindowEvent.PRESS_BUTTON_B,
            "START": WindowEvent.PRESS_BUTTON_START,
            "SELECT": WindowEvent.PRESS_BUTTON_SELECT,
            "WAIT": None
        }
        
    def get_action(self, game_state):
        """
        Query OpenAI to decide next action based on game state
        
        game_state should include:
        - map_id: current map ID
        - position: (x, y) tuple
        - party: list of pokemon
        - badges: number of badges
        - in_battle: boolean
        - enemy_info: if in battle
        """
        # Build prompt with game state
        prompt = self._build_prompt(game_state)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Low temperature for more deterministic actions
                max_tokens=150
            )
            
            # Parse response
            action_text = response.choices[0].message.content.strip().upper()
            
            # Extract action from response
            for action_name, action_event in self.action_map.items():
                if action_name in action_text:
                    return action_event
            
            # Default: press A to advance dialogue
            return WindowEvent.PRESS_BUTTON_A
            
        except Exception as e:
            print(f"[LLM Agent] Error calling OpenAI: {e}")
            return WindowEvent.PRESS_BUTTON_A  # Fallback
    
    def _get_system_prompt(self):
        """
        System prompt defining th LLM's role
        """
        return """You are an expert Pokemon Blue speedrunner AI. Your goal is to beat Brock (the first gym leader) as quickly as possible.

You have access to a detailed walkthrough guide and can see the current game state.

Your responses should be SHORT and ACTION-ORIENTED. Respond with ONLY ONE of these actions:
- UP, DOWN, LEFT, RIGHT (movement)
- A (select/interact/attack)
- B (cancel/back)
- START (menu)
- SELECT (switch pokemon in menu)
- WAIT (do nothing this frame)

Be decisive and efficient. If in dialogue, press A. If stuck, try different directions.
Follow the walkthrough guide steps closely."""

    def _build_prompt(self, game_state):
        """
        Build prompt with current game state
        """
        map_id = game_state.get('map_id', 0)
        pos = game_state.get('position', (0, 0))
        party_count = game_state.get('party_count', 0)
        badges = game_state.get('badges', 0)
        in_battle = game_state.get('in_battle', False)
        
        # Map ID to location name
        location_map = {
            38: "Player's Bedroom",
            37: "Player's House (Living Room)",
            0: "Pallet Town",
            40: "Oak's Lab",
            1: "Route 1",
            2: "Viridian City",
            # Add more as needed
        }
        
        location = location_map.get(map_id, f"Unknown (Map {map_id})")
        
        # Find relevant guide step
        current_step = self._get_relevant_step(map_id, party_count)
        
        prompt = f"""CURRENT GAME STATE:
Location: {location} (Map ID: {map_id})
Position: {pos}
Pokemon in Party: {party_count}
Badges: {badges}
In Battle: {in_battle}

WALKTHROUGH STEP:
{current_step}

What action should I take RIGHT NOW? Respond with ONE action word only."""
        
        return prompt
    
    def _get_relevant_step(self, map_id, party_count):
        """
        Get the relevant step from brock.json based on game state
        """
        if not self.guide or 'steps' not in self.guide:
            return "No walkthrough available. Explore and interact with A button."
        
        # Simple logic to find relevant step
        if map_id == 38:  # Bedroom
            step = self.guide['steps'][0]  # Step 1
            return f"Step {step['id']}: {step['title']}\n" + "\n".join(step['instructions'][:3])
        
        elif map_id == 37:  # Living Room
            step = self.guide['steps'][1]  # Step 2
            return f"Step {step['id']}: {step['title']}\n" + "\n".join(step['instructions'][:3])
        
        elif map_id == 0 and party_count == 0:  # Pallet Town, no pokemon
            step = self.guide['steps'][2]  # Step 3
            return f"Step {step['id']}: {step['title']}\n" + "\n".join(step['instructions'][:3])
        
        elif map_id == 40:  # Oak's Lab
            if party_count == 0:
                step = self.guide['steps'][3]  # Step 4 - Choose starter
            else:
                step = self.guide['steps'][4]  # Step 5 - Rival battle
            return f"Step {step['id']}: {step['title']}\n" + "\n".join(step['instructions'][:3])
        
        # Default
        return "Continue following the walkthrough. Interact with NPCs using A button."
