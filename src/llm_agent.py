import os
import json
import logging

# Setup logger
logger = logging.getLogger("LLMAgent")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.FileHandler("llm.log")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

try:
    from src.agent import BaseAgent
except ImportError:
    # Fallback if running from different directory structure
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from src.agent import BaseAgent
from pyboy.utils import WindowEvent

class LLMAgent(BaseAgent):
    def __init__(self, api_key=None, model="gpt-4o", knowledge=None):
        if not api_key and not os.getenv("OPENAI_API_KEY"):
            try:
                from dotenv import load_dotenv
                from pathlib import Path
                env_path = Path(__file__).parent.parent / '.env'
                load_dotenv(env_path)
                logger.info(f"Attempted to load .env from {env_path}")
            except Exception as e:
                logger.error(f"Failed to load .env: {e}")

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.knowledge = knowledge
        if not self.api_key:
            logger.warning("No OpenAI API Key provided. LLM features will not work.")
        if self.knowledge:
            logger.info(f"Loaded {len(self.knowledge.get('steps', []))} knowledge snippets.")

    def get_battle_action(self, battle_state):
        """
        Consults the LLM for the best move in the current battle state.
        """
        if not self.api_key:
            return None

        prompt = self._create_battle_prompt(battle_state)
        logger.info(f"Consulting LLM for Battle: {prompt}")
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            
            system_content = "You are a Pokemon Blue expert AI. Reply with ONLY the move name or action."
            if self.knowledge:
                 system_content += f"\n\nReference Guide:\n{json.dumps(self.knowledge, indent=2)}"
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0.2
            )
            
            action_text = response.choices[0].message.content.strip()
            logger.info(f"LLM Battle suggestion: {action_text}")
            
            # Map LLM text to button press
            # TODO: Improved mapping needed. For now, if it suggests anything, we press A (Select first move)
            # Ideally we need to know which move slot corresponds to the suggestion
            return WindowEvent.PRESS_BUTTON_A
            
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return WindowEvent.PRESS_BUTTON_A # Fallback

    def _create_battle_prompt(self, state):
        return f"""
        You are a Pokemon Master playing Pokemon Blue.
        
        **Current Battle State:**
        - **My Pokemon:** {state.get('my_pokemon', 'Unknown')} (HP: {state.get('my_hp', '?')})
        - **Enemy Pokemon:** {state.get('enemy_pokemon', 'Unknown')} (HP: {state.get('enemy_hp', '?')})
        
        **Available Moves:** {state.get('moves', ['Tackle', 'Growl'])} (Placeholder)
        
        **Strategy Guide:**
        - Check type effectiveness (Water > Fire, Fire > Grass, etc.)
        - If enemy HP is low, use a damaging move.
        - If my HP is low, consider using a Potion (if available) or switching.
        - Prioritize STAB moves.
        
        **Task:**
        Choose the best action. Reply with ONLY the move name or action (e.g., "Tackle", "Potion", "Switch to Pikachu").
        """

    def get_navigation_action(self, task_description, game_state):
        """
        Consults the LLM for the next navigation step.
        """
        if not self.api_key:
            return None
            
        prompt = f"""
        You are playing Pokemon Blue.
        
        **Current Goal:** {task_description}
        
        **Current State:**
        - Map ID: {game_state.get('map_id', 'Unknown')}
        - Position: {game_state.get('pos', 'Unknown')}
        - Party Count: {game_state.get('party_count', 0)}
        
        **Available Actions:**
        UP, DOWN, LEFT, RIGHT, A, B, START
        
        **Task:**
        What button should I press next to achieve the goal?
        Reply with ONLY the button name (e.g., "UP", "A").
        If you believe the goal is achieved based on the state, reply "DONE".
        """
        
        logger.info(f"Consulting LLM for Navigation: {task_description}")
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            
            system_content = "You are a Pokemon Blue expert AI. Reply with ONLY the button name or DONE."
            if self.knowledge:
                 system_content += f"\n\nReference Guide:\n{json.dumps(self.knowledge, indent=2)}"
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0.1
            )
            
            action_text = response.choices[0].message.content.strip().upper()
            logger.info(f"LLM Navigation suggestion: {action_text}")
            
            if action_text == "DONE":
                return "DONE"
            
            # Map to WindowEvent
            mapping = {
                "UP": WindowEvent.PRESS_ARROW_UP,
                "DOWN": WindowEvent.PRESS_ARROW_DOWN,
                "LEFT": WindowEvent.PRESS_ARROW_LEFT,
                "RIGHT": WindowEvent.PRESS_ARROW_RIGHT,
                "A": WindowEvent.PRESS_BUTTON_A,
                "B": WindowEvent.PRESS_BUTTON_B,
                "START": WindowEvent.PRESS_BUTTON_START
            }
            
            return mapping.get(action_text, None)
            
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return None
