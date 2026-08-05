# AI Development Guide - PokeAI Blue Project

> **Purpose**: This document helps future AI assistants quickly understand the architecture, design decisions, and development patterns for the Pokemon Blue autonomous AI project.

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Key Components](#key-components)
4. [Development Patterns](#development-patterns)
5. [Common Tasks](#common-tasks)
6. [Debugging Tips](#debugging-tips)
7. [Memory Addresses Reference](#memory-addresses-reference)

---

## Project Overview

**Goal**: Create an AI that autonomously plays and completes Pokemon Blue (Game Boy).

**Current Status**: 
- ✅ Intro sequence (Start → Oak → Naming)
- ✅ Basic navigation (House → Pallet Town)
- ✅ LLM integration for battles
- ✅ Multi-simulation support
- 🚧 Rival fight (in progress)
- ❌ Route 1 → Brock → Full game

**Tech Stack**:
- **Emulator**: PyBoy (Game Boy emulator in Python)
- **AI**: Hybrid approach (Scripted + LLM)
- **LLM**: OpenAI GPT-4 (via API)
- **Language**: Python 3.x
- **Concurrency**: multiprocessing for parallel simulations

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────┐
│              multi_runner.py                    │
│  (Orchestrates multiple concurrent sims)        │
└────────────┬────────────────────────────────────┘
             │ spawns
             ▼
┌─────────────────────────────────────────────────┐
│                 main.py                         │
│  Entry point for single simulation              │
│  Args: --rom, --agent, --name, --save-dir      │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│               Emulator                          │
│  - PyBoy wrapper                                │
│  - save_state(filename)                         │
│  - step(), get_state()                          │
│  - Contains Memory instance                     │
└────────────┬────────────────────────────────────┘
             │
       ┌─────┴─────┐
       ▼           ▼
┌─────────────┐  ┌──────────────┐
│   Memory    │  │   Agent      │
│             │  │  (Interface) │
│ - read_byte │  └──────┬───────┘
│ - read_word │         │
│ - get_pos() │    ┌────┴─────┐
│ - get_map() │    ▼          ▼
└─────────────┘  ┌──────┐  ┌──────┐
                 │Script│  │ LLM  │
                 │Agent │  │Agent │
                 └──┬───┘  └──────┘
                    │
                    ▼
              ┌──────────┐
              │Navigation│
              │ pathfind │
              └──────────┘
```

### Hybrid AI Strategy

**Why Hybrid?**
- **Scripted**: Fast, deterministic, perfect for routine tasks (walking, menu navigation)
- **LLM**: Flexible, handles complex decisions (battle strategy, item usage)

**When to use each:**
- Scripted: Intro sequence, navigation, menu interactions
- LLM: Battles, uncertain situations, strategic planning

---

## Key Components

### 1. `src/emulator.py` - Emulator Wrapper

**Purpose**: Thin wrapper around PyBoy for cleaner API.

**Key Methods**:
```python
emulator.step()  # Advance 1 frame
emulator.get_state()  # Returns {pos, map_id, party_count, etc.}
emulator.save_state(filename)  # Save .state file
emulator.pyboy  # Direct PyBoy access if needed
emulator.memory  # Memory reader instance
```

**Important**: 
- Runs at emulation_speed=0 (unlimited) in headless mode
- Window type should be "null" (not "headless" - deprecated)

---

### 2. `src/memory.py` - Game State Reader

**Purpose**: Read Pokemon Blue's memory directly.

**Key Methods**:
```python
memory.get_player_pos()  # Returns (x, y) tuple
memory.get_map_id()  # Returns int (38=Bedroom, 37=Living Room, 0=Pallet, etc.)
memory.read_byte(address)  # Generic byte read
memory.get_battle_state()  # Returns battle info (WIP)
```

**Memory Addresses** (see `memory_map.py`):
- Player X: 0xD362
- Player Y: 0xD361
- Map ID: 0xD35E
- Battle Status: 0xD057 (0=no battle, 1=wild, 2=trainer)
- Party Count: 0xD163

---

### 3. `src/scripted_agent.py` - Rule-Based Agent

**Purpose**: Execute predefined sequences from `docs/cidades/1/badge1.json`.

**State Machine Pattern**:
```python
action_desc = self.steps[self.current_step]

if action_desc == "Some Task":
    # Implement task logic
    # When done:
    self.current_step += 1
    return None
```

**Key Patterns**:

#### Timed Sequences
```python
# For fixed button press sequences
sequence = [
    (WindowEvent.PRESS_ARROW_UP, 60),  # Press for 60 frames
    (WindowEvent.RELEASE_ARROW_UP, 5),
    (None, 30)  # Wait 30 frames
]
return self._execute_timed_sequence(sequence)
```

#### State-Aware Navigation
```python
# For movement based on current location
map_id = self.emulator.memory.get_map_id()

if map_id == 38:  # Bedroom
    return self._navigate_to(7, 1)  # Walk to stairs
elif map_id == 37:  # Living Room
    return self._navigate_to(2, 7)  # Walk to door
```

**Stuck Detection**:
- Tracks `current_step` changes
- If no progress for 100,000 frames → auto-save and exit
- Prevents infinite loops

---

### 4. `src/llm_agent.py` - LLM Decision Maker

**Purpose**: Use GPT-4 for complex decisions.

**Current Use**: Battle strategy

**API Structure**:
```python
def get_battle_action(self, battle_state):
    prompt = f"""
    You are playing Pokemon Blue.
    Your Pokemon: {battle_state['my_pokemon']}
    Enemy: {battle_state['enemy_pokemon']}
    Available moves: {battle_state['moves']}
    
    Choose: FIGHT <move_number>
    """
    response = openai.chat.completions.create(...)
    return self._parse_action(response)
```

**Important**:
- Requires `OPENAI_API_KEY` in `.env`
- Currently uses placeholder battle_state (needs full memory reading)
- Response parsing is flexible (handles various formats)

---

### 5. `src/navigation.py` - Pathfinding

**Purpose**: Heuristic pathfinding to target coordinates.

**Algorithm**: Manhattan distance (simple, works for Gen 1 grid)

```python
navigation.get_path_to(target_x, target_y)
# Returns: WindowEvent.PRESS_ARROW_<direction>
# Returns: None if at target
```

**Limitations**:
- No obstacle avoidance
- Assumes clear path
- Good for simple indoor navigation

---

### 6. `src/multi_runner.py` - Simulation Orchestrator

**Purpose**: Run multiple AI instances concurrently.

**Features**:
- Timestamped run directories: `runs/YYYYMMDD_HHMMSS/`
- Per-agent logs: `aaron.log`, `baron.log`
- Concurrent subprocess execution
- Graceful shutdown on Ctrl+C

**Usage**:
```bash
python3 src/multi_runner.py  # Runs AARON and BARON
```

**Customization**:
```python
# In multi_runner.py, modify:
agents = ["AARON", "BARON", "CARON", "DARON"]  # Add more
```

---

## Development Patterns

### Pattern 1: Adding a New Scripted Sequence

**Example**: Add "Enter Pokemon Center" logic

1. **Add to `badge1.json`**:
```json
"actions": [
  "Enter Pokemon Center",
  "Talk to Nurse Joy"
]
```

2. **Implement in `scripted_agent.py`**:
```python
if action_desc == "Enter Pokemon Center":
    map_id = self.emulator.memory.get_map_id()
    
    if map_id == ROUTE_1:  # Outside
        return self._navigate_to(CENTER_DOOR_X, CENTER_DOOR_Y)
    elif map_id == POKE_CENTER:  # Inside
        self.current_step += 1
        return None
```

### Pattern 2: Adding Memory Reads

**Example**: Read current HP

1. **Find memory address** (use existing PokeBot references or memory viewers)
2. **Add to `memory_map.py`**:
```python
PLAYER_HP_CURRENT = 0xD016  # Example
PLAYER_HP_MAX = 0xD017
```

3. **Add method to `memory.py`**:
```python
def get_current_hp(self):
    return self.read_word(PLAYER_HP_CURRENT)
```

4. **Use in agent**:
```python
hp = self.emulator.memory.get_current_hp()
if hp < 20:
    # Go to Pokemon Center
```

### Pattern 3: LLM Integration for New Decision

**Example**: Item usage in battle

1. **Get game state**:
```python
items = self.emulator.memory.get_bag_items()
battle_state['items'] = items
```

2. **Update LLM prompt**:
```python
prompt += f"\nAvailable items: {items}\nOptions: FIGHT/ITEM/RUN"
```

3. **Parse response**:
```python
if "ITEM" in response:
    item_num = extract_number(response)
    return self._use_item(item_num)
```

---

## Common Tasks

### Task: Run Multi-Simulation
```bash
cd poke-ai
python3 src/multi_runner.py
# Logs in runs/YYYYMMDD_HHMMSS/
# Auto-saves on stuck/milestone
```

### Task: Debug Single Agent
```bash
python3 src/main.py --rom "roms/Pokemon Blue.gb" \
                     --agent scripted \
                     --name DEBUG \
                     --save-dir runs/debug
# Watch console output in real-time
```

### Task: Test Navigation Coordinates
```bash
# 1. Load a save state at target location
# 2. Read position from logs: "Debug - Pos: (X, Y)"
# 3. Update coordinates in scripted_agent.py
# 4. Rerun
```

### Task: Add New Agent Name
```python
# In multi_runner.py:
agents = ["AARON", "BARON", "YOUR_NAME"]
```

---

## Debugging Tips

### Issue: Agent Gets Stuck

**Check**:
1. **Logs**: `runs/<timestamp>/<name>.log`
   - Look for repeated "Current Objective"
   - Check Map ID and Position
2. **Stuck saves**: `stuck_<name>_<timestamp>.state`
   - Load in PyBoy to see exact stuck location
3. **Navigation**:
   - Are coordinates correct for this Map ID?
   - Is Map ID transition happening?

**Fix**:
- Adjust target coordinates in `_navigate_to(x, y)`
- Add wait frames for map transitions
- Check for pause menu (press B to close)

### Issue: LLM Not Working

**Check**:
1. `.env` file exists with `OPENAI_API_KEY=sk-...`
2. `python-dotenv` installed
3. `load_dotenv()` called in `main.py`
4. API key is valid (test with curl)

**Debug**:
```python
# In llm_agent.py:
print(f"API Key: {os.getenv('OPENAI_API_KEY')[:10]}...")  # First 10 chars
```

### Issue: Map ID Not Changing

**Possible Causes**:
1. Navigation not reaching transition tile
2. Transition requires facing direction (e.g., doors)
3. Not enough frames for transition to complete

**Fix**:
- Hold direction longer: `(PRESS_ARROW_UP, 120)` instead of `60`
- Add wait frames: `(None, 200)` after expected transition
- Check if door requires pressing A

---

## Memory Addresses Reference

### Essential Addresses (Pokemon Blue US)

| Description | Address | Type | Notes |
|------------|---------|------|-------|
| Player X | 0xD362 | byte | Tile coordinate |
| Player Y | 0xD361 | byte | Tile coordinate |
| Map ID | 0xD35E | byte | 38=Bedroom, 37=Living, 0=Pallet |
| Battle Status | 0xD057 | byte | 0=None, 1=Wild, 2=Trainer |
| Party Count | 0xD163 | byte | Number of Pokemon |
| Badges | 0xD356 | byte | Bitfield (0x01=Boulder, etc.) |

### Map IDs
```python
MAP_IDS = {
    0: "Pallet Town",
    38: "Player's House - Bedroom (2F)",
    37: "Player's House - Living Room (1F)",
    # ... (See disassembly for full list)
}
```

### Battle State (WIP - needs implementation)
- My Pokemon Species: 0xD014
- Enemy Pokemon Species: 0xCFE5
- My Pokemon HP: 0xD016 (current), 0xD017 (max)
- Move 1-4: 0xD01C - 0xD01F

---

## Design Philosophy

### 1. **Robustness over Speed**
- State-aware navigation > Blind timing
- Auto-save on stuck > Manual intervention
- Map ID checks > Assuming transitions worked

### 2. **Modularity**
- Agents are swappable (ScriptedAgent, LLMAgent, HybridAgent)
- Memory reader independent of agent logic
- Navigation is a separate concern

### 3. **Observability**
- Debug prints every 60 frames
- Detailed logs per agent
- Save states for post-mortem analysis

### 4. **Scalability**
- Multi-process for parallel experiments
- Minimal shared state
- Headless mode for server deployment

---

## Next Steps for Future Development

### High Priority
1. **Complete Rival Fight**
   - Test battle trigger logic
   - Verify LLM battle decisions work
   - Ensure save after victory

2. **Route 1 Navigation**
   - Wild Pokemon encounter handling
   - Trainer battles
   - Item pickup (optional)

3. **Pokemon Center Healing**
   - Navigate to center
   - Talk to Nurse Joy (spam A)
   - Confirm healing worked

### Medium Priority
4. **Viridian Forest**
   - Complex pathfinding (obstacles)
   - Caterpie/Weedle catching logic
   - Trainer battles

5. **Brock Battle**
   - Type advantage logic (Grass/Water > Rock)
   - Starter-dependent strategy
   - Badge verification

### Low Priority
6. **Full Memory System**
   - Read all Pokemon stats
   - Read bag items
   - Read Pokedex data

7. **Advanced LLM**
   - Long-term strategy planning
   - Team composition suggestions
   - HM usage decisions

---

## Useful Commands

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run single simulation
python3 src/main.py --rom "roms/Pokemon Blue.gb" --agent scripted --name TEST

# Run multi-simulation
python3 src/multi_runner.py

# Check logs
tail -f runs/20251122_HHMMSS/aaron.log

# Load stuck state for inspection
# (Open PyBoy GUI, File > Load State > stuck_*.state)

# Git status
git status
git add .
git commit -m "feat: description"
```

---

## Resources

- **PyBoy Docs**: https://github.com/Baekalfen/PyBoy
- **Pokemon Blue Disassembly**: https://github.com/pret/pokered
- **Memory Map**: https://datacrystal.romhacking.net/wiki/Pokemon_Red/Blue:RAM_map
- **Reference Bot**: https://github.com/Kakumi/Pokebot (inspiration)

---

## Final Notes for AI Assistants

**When resuming this project**:
1. First, read this guide entirely
2. Check `task.md` for current progress
3. Look at most recent logs in `runs/` for context
4. Review `scripted_agent.py` to see last implemented sequence
5. Test changes with single agent before multi-sim

**Common pitfalls**:
- Forgetting to increment `self.current_step` (infinite loop)
- Using wrong Map IDs (check logs for actual values)
- Not adding wait frames for transitions (maps don't change)
- Returning action when should return None (frame timing issues)

**Best practices**:
- Add debug prints liberally (removed later)
- Test navigation in PyBoy GUI first (visual feedback)
- Use stuck saves to debug exact failure point
- Update this guide when adding major features

---

**Good luck! The AI is well-architected and ready for expansion. Focus on incremental progress and robust state handling.** 🎮🤖
