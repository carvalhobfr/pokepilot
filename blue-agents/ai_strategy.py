"""
On-demand AI Strategy Assistant for Pokemon Blue Agents
Provides strategic advice when requested via dashboard button
"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from ai_config import AI_MODEL, MAX_TOKENS, TEMPERATURE, SYSTEM_PROMPT
from shared_strategy_library import SharedStrategyLibrary

# Load environment variables
load_dotenv(Path(__file__).parent.parent / '.env')

# Initialize OpenAI client (new API >=1.0.0)
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def get_ai_strategy(agent_name: str, agent_state: dict) -> str:
    """
    Get AI strategy recommendation for an agent
    Checks shared library first, only calls AI if needed
    
    Args:
        agent_name: Name of the agent
        agent_state: Current state including map_id, position, party, badges, etc.
    
    Returns:
        Detailed strategy recommendation from GPT or library
    """
    
    # Initialize shared library
    library = SharedStrategyLibrary()
    
    # Check if we have a similar strategy already
    similar_strategy = library.find_similar_strategy(agent_state)
    if similar_strategy:
        print(f"💰 SAVED MONEY! Reusing existing strategy for {agent_name}")
        # Return formatted response with the cached strategy
        return f"""```json
{json.dumps(similar_strategy, indent=2)}
```

**Note**: This strategy was reused from the shared library to save API costs. 
Other agents in similar situations have found this path successful!"""
    
    # No similar strategy found - need to call AI
    print(f"🤖 No cached strategy found - consulting AI for {agent_name}...")
    
    # Extract key information
    map_id = agent_state.get('map_id', '?')
    badges = agent_state.get('badges', 0)
    party = agent_state.get('party', [])
    pokedex_owned = agent_state.get('pokedex_owned', 0)
    battle_info = agent_state.get('battle_info', {})
    
    # Build party context
    party_summary = []
    for i, mon in enumerate(party):
        party_summary.append(
            f"  {i+1}. Species ID #{mon.get('species_id', '?')} - Level {mon.get('level', '?')} (HP: {mon.get('hp', '?')}/{mon.get('max_hp', '?')})"
        )
    
    party_text = "\n".join(party_summary) if party_summary else "  No Pokemon in party"
    
    in_battle = battle_info.get('is_battle', False)
    battle_text = ""
    if in_battle:
        battle_text = f"\n🔴 Currently IN BATTLE against {battle_info.get('enemy_species', 'Unknown')}"
    
    # Check for critical story flags
    has_pokedex = pokedex_owned > 0  # If you own Pokemon, you likely have Pokédex
    
    # Build critical story context
    story_context = []
    if badges == 0:
        story_context.append("⚠️ No badges yet - early game!")
        if not has_pokedex:
            story_context.append("⚠️ CRITICAL: Need to get Oak's Parcel from Viridian Poke Mart and deliver to Oak in Pallet Town to get Pokédex!")
        else:
            story_context.append("✅ Has Pokédex - can now focus on Pewter Gym")
    
    story_text = "\n".join(story_context) if story_context else ""
    
    prompt = f"""You are an expert Pokemon Blue navigation assistant with COMPLETE game knowledge.

IMPORTANT STORY SEQUENCE (MUST follow in order):
1. Get Oak's Parcel from Viridian Poke Mart (if not done)
2. Deliver parcel to Professor Oak in Pallet Town → GET POKÉDEX (REQUIRED!)
3. Train Pokemon to Level 10+
4. Challenge Pewter Gym (Brock)

Agent: {agent_name}
Current Map ID: {map_id}
Badges Earned: {badges}/8
Pokemon Owned: {pokedex_owned}
Has Pokédex: {"YES ✅" if has_pokedex else "NO ❌ (MUST GET FIRST!)"}
{battle_text}
{story_text}

Current Party:
{party_text}

OUTPUT FORMAT (respond with valid JSON + explanation):

```json
{{
  "current_objective": "Short description of NEXT immediate step",
  "target_map_id": 123,
  "waypoints": [
    {{"action": "get_parcel", "description": "Go to Viridian Poke Mart, get Oak's Parcel"}},
    {{"action": "deliver_parcel", "description": "Return to Pallet Town, deliver to Oak, GET POKÉDEX"}},
    {{"action": "exit_building", "description": "Walk DOWN to exit current building"}},
    {{"action": "navigate", "target_map": 12, "description": "Go to Route 1"}},
    {{"action": "level_up", "target_level": 10, "description": "Train to Level 10"}},
    {{"action": "gym_battle", "gym": "pewter", "description": "Challenge Brock"}}
  ],
  "priority": "immediate/short-term/long-term",
  "notes": "WHY this path (explain story requirements)"
}}
```

RULES:
- If agent doesn't have Pokédex yet ({has_pokedex}), MUST include parcel quest first!
- Be specific about MAP IDs
- Check current map_id ({map_id}) to know where agent is
- Common Map IDs: 0=Pallet Town, 1=Viridian City, 12=Route 1, 40=Oak's Lab

Provide JSON first, then brief explanation."""

    try:
        # New API (>=1.0.0)
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Try to extract JSON from response
        import re
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        
        if json_match:
            path_json = json.loads(json_match.group(1))
            
            # Save to shared library for other agents to reuse
            library.save_strategy(agent_name, agent_state, path_json)
            
            # Save to agent-specific instruction file
            instructions_dir = Path(__file__).parent.parent / "tasks" / "ai_instructions"
            instructions_dir.mkdir(parents=True, exist_ok=True)
            
            instruction_file = instructions_dir / f"{agent_name.lower()}_path.json"
            with open(instruction_file, 'w') as f:
                json.dump(path_json, f, indent=2)
            
            print(f"✅ AI Path saved for {agent_name}: {instruction_file}")
        
        return response_text
    
    except Exception as e:
        return f"❌ Error consulting AI: {str(e)}\n\nPlease check your OpenAI API key and quota."

if __name__ == "__main__":
    # Test
    test_state = {
        "map_id": 40,  # Oak's Lab
        "badges": 0,
        "party": [
            {"species_id": 1, "level": 6, "hp": 20, "max_hp": 20}
        ],
        "pokedex_owned": 1
    }
    
    result = get_ai_strategy("TestAgent", test_state)
    print(result)
