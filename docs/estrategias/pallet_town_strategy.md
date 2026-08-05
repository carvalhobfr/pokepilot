# Pokemon Blue - Pallet Town & Oak's Lab Strategy Guide

> **Area Goal**: Complete introduction, get starter Pokemon, optionally fight Rival

---

## 🗺️ Area Map & Navigation

### Player's House (Map IDs: 38, 37)
**Bedroom (Map 38)**
- Starting position after naming: ~(3, 6)
- Target: Stairs at (7, 1)
- **Navigation tip**: Hold RIGHT for ~2 seconds, then UP for ~2 seconds

**Living Room (Map 37)**
- Entry point from stairs: ~(7, 1)
- Target: Door at (2, 7) or (3, 7)
- **Mom will talk to you** - spam A to advance text
- Exit via door at bottom

### Pallet Town (Map 0)
- House exit: ~(5, 7)
- Route 1 entrance: North edge (triggers Oak Event)
- **Oak's trigger**: Walk into tall grass (coordinates ~(5, 1) or any northern tile)

### Oak's Lab (Map ID TBD)
- Entry: Forced teleport after Oak Event
- Pokeball table: Center-north of room
- Rival position: Near door
- **Exit trigger**: Try to leave → Rival stops you

---

## ⚙️ Technical Challenges & Solutions

### Challenge 1: Bedroom Navigation Stuck
**Problem**: Agent gets stuck at (3, 6), doesn't reach stairs

**Memory indicators**:
- Map ID stays at 38
- Position doesn't change significantly

**Solutions**:
1. **Hold movement longer**: Use 120+ frame duration instead of 60
2. **Check for obstacles**: Furniture blocks path (bed, desk)
3. **Smart pathfinding**: Use Navigation.get_path_to(7, 1) with held presses
4. **Debug logging**: Print position every 10 frames to track movement

**Optimal path**:
```python
# From (3, 6) to Stairs (7, 1):
1. Move RIGHT →→→→ (to x=7)
2. Move UP ↑↑↑↑↑ (to y=1)
3. Stairs auto-trigger when stepped on
```

---

### Challenge 2: Oak Event Trigger
**Problem**: Walking north doesn't trigger Oak

**Trigger conditions**:
- Must be in Pallet Town (Map 0)
- Must walk onto tall grass tiles (northern edge)
- Oak will **call you back** and take you to lab

**Solution**:
- Keep walking UP until map changes
- Don't expect immediate response - spam UP for 5-10 seconds
- Map ID will change from 0 → Lab Map ID

---

### Challenge 3: Starter Selection
**Problem**: Don't know which Pokeball to interact with

**Pokeball positions** (approximate):
- **Left** (Bulbasaur): (3, 3)
- **Middle** (Charmander): (4, 3)
- **Right** (Squirtle): (5, 3)

**Recommended for AI**:
- **Bulbasaur** (Grass): Easy mode - wrecks Brock and Misty
- **Squirtle** (Water): Medium - good vs Brock, struggles vs Misty
- **Charmander** (Fire): Hard mode - bad vs both first gyms

**Implementation**:
1. Walk UP to table (target y=3)
2. Navigate to desired X coordinate
3. Press A to interact
4. Press A again to confirm

---

## ⚔️ Battle Tips: Rival Fight (Optional)

### Rival Pokemon
**If you chose Bulbasaur**: Rival has Charmander (Fire)
- **Type advantage**: YOU (Grass > Fire is NEUTRAL, but Fire > Grass!)
- **Correction**: Fire beats Grass, so you're at DISADVANTAGE
- **Strategy**: Use Tackle (Normal) instead of Vine Whip (Grass)

**If you chose Charmander**: Rival has Squirtle (Water)
- **Type advantage**: RIVAL (Water > Fire)
- **Strategy**: Use Scratch/Ember, avoid prolonged fight

**If you chose Squirtle**: Rival has Bulbasaur (Grass)
- **Type advantage**: RIVAL (Grass > Water)
- **Strategy**: Use Tackle (Normal) instead of Water moves

### General Battle Strategy

**Move Priority**:
1. **Normal-type moves** (Tackle, Scratch) - neutral damage, safe choice
2. **STAB moves** (Same Type Attack Bonus) - only if type advantage
3. **Avoid disadvantageous types** - don't use Grass vs Fire, etc.

**When to use items**: NEVER in first rival fight (no items at this point)

**Run or Fight?**: Optional fight, but good for XP. If LLM seems confused, just spam FIGHT → Move 1 (Tackle)

---

## 🎯 AI Implementation Checklist

- [ ] Bedroom: Reach stairs successfully (Map 38 → 37)
- [ ] Living Room: Exit house (Map 37 → 0)
- [ ] Pallet Town: Trigger Oak Event (walk north)
- [ ] Oak's Lab: Navigate to Pokeball table
- [ ] Starter Selection: Choose and confirm Pokemon
- [ ] Rival Trigger: Attempt to leave lab
- [ ] Battle System: LLM makes move decisions
- [ ] Battle End Detection: Recognize victory (battle status = 0)
- [ ] Checkpoint Save: Save after rival defeated

---

## 📊 Checkpoint Saves

**checkpoint_naming_done.state**
- When: After naming player and rival
- Location: Player's Bedroom (Map 38), position (3, 6)
- Next step: Leave house

**checkpoint_pre_oak.state** (optional)
- When: Exited house successfully
- Location: Pallet Town (Map 0), outside house
- Next step: Trigger Oak Event

**checkpoint_starter_chosen.state**
- When: After selecting starter Pokemon
- Location: Oak's Lab, near Pokeballs
- Next step: Try to leave → Rival fight

**checkpoint_rival_defeated.state**
- When: After winning first rival battle
- Location: Oak's Lab, after battle
- Next step: Navigate to Route 1

---

## 🐛 Common Bugs & Fixes

**Bug**: Agent walks into walls
- **Fix**: Add small wait frame after direction change
- **Code**: `(None, 10)` between movement commands

**Bug**: Oak Event doesn't trigger
- **Fix**: Keep walking UP for longer (300+ frames)
- **Reason**: Trigger tile might be further north than expected

**Bug**: Can't confirm starter selection
- **Fix**: Press A twice with delay between
- **Code**: Press A, wait 30 frames, Press A again

**Bug**: Battle doesn't end after winning
- **Fix**: Check Battle Status memory (0xD057) for 0 value
- **Implementation**: Poll every frame until battle_status == 0

**Bug**: Stuck in "battle finished" state
- **Fix**: Clear battle flags after detection
- **Code**: `self.was_in_battle = False; self.battle_finished = False`

---

## 💡 LLM Prompt Improvements

### Current Prompt Issues
- Doesn't consider rival's type advantage
- May not know to avoid ineffective moves
- Lacks context about Pokemon levels

### Enhanced Prompt Template
```python
prompt = f"""You are an expert Pokemon Blue player in your first Rival battle.

YOUR POKEMON:
- Species: {my_pokemon} (Type: {my_type})
- Level: ~5
- HP: {my_hp}/{my_max_hp}
- Moves: {move_list}

ENEMY POKEMON:
- Species: {enemy_pokemon} (Type: {enemy_type})
- Level: ~5
- HP: Unknown

TYPE MATCHUPS:
- Grass > Water, Rock, Ground
- Water > Fire, Rock, Ground
- Fire > Grass, Bug, Ice
- Normal = Neutral vs all

STRATEGY TIPS:
1. If type disadvantage, use Normal-type moves (Tackle/Scratch)
2. If type advantage, use STAB moves (your type's moves)
3. If low HP (<30%), consider RUN (but you probably can WIN)

BATTLE COMMANDS:
- FIGHT <move_number>: Use move 1-4
- RUN: Flee battle (lose XP)

Choose your action (FIGHT 1, FIGHT 2, etc.):
"""
```

### Type Matchup Chart for AI
```
Attacker → Defender
GRASS: Weak to (Fire, Ice, Poison, Flying, Bug)
       Strong vs (Water, Rock, Ground)

WATER: Weak to (Electric, Grass)
       Strong vs (Fire, Rock, Ground)

FIRE:  Weak to (Water, Rock, Ground)
       Strong vs (Grass, Ice, Bug)

NORMAL: Neutral vs all (can't hit Ghost)
```

---

## 📈 Success Metrics

**Fast clear**: < 3000 frames (~50 seconds at 60fps)
**Safe clear**: HP > 50% after rival fight
**Perfect clear**: No wasted moves, optimal type usage

Track these in logs for analysis!
