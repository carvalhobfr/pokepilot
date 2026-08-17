# pokepilot

**English** · [Português](README.pt-BR.md)

Bots playing **the real Pokémon Blue** — the original ROM on an emulator, not a
simulation. You watch from the browser: the map of Kanto with the trainers
moving across it, each one's party, and a journal explaining why every decision
was made.

The goal is a bot that **understands objectives**, not a script that memorizes
button presses. Today it crosses half of Kanto on its own; the direction is
taking orders in plain language — *"catch a Pikachu"* — and working out for
itself where to go and what to do.

What guarantees nothing is invented: **every bit of progress is verified in
cartridge memory**. No script gets to say "I earned the badge" — the badge bit
has to show up in RAM.

> ### 🚧 Work in progress
>
> Nothing here is finished, and the game is not beaten. Everything marked ✅ was
> **reproduced from scratch**, more than once, with the same result. The rest is
> beta or doesn't work yet — and it's labeled that way in each section, instead
> of hidden behind a promise.

## Status of each piece

| Piece | Status |
|---|---|
| graph navigation and quests, Pallet through Cut | ✅ tested, reproducible from scratch |
| battle (expert system reading RAM) | ✅ tested |
| dashboard, live map, arena and replays | ✅ works |
| **archetypes** (the four personalities) | 🟡 **BETA** — they run, but no complete run has compared all four to the same point |
| **reinforcement learning (PPO)** | 🟡 **BETA** — it trains, but decides **0%** of actions today ([measured](#learning-measured-rather-than-estimated)) |
| **plain-language orders via LLM** | ⛔ **coming soon** — does not work yet; the LLM only answers the "Ask AI" button |
| Lt. Surge's gym through the League | ⛔ no executor |

---

## How far the bots get

One bot, from a brand new game, with nobody helping, in **under two hours**:

| | |
|---|---|
| leaves home, picks a starter, delivers Oak's parcel | ✅ |
| buys Poké Balls, crosses Viridian and the Forest | ✅ |
| trains until the starter evolves | ✅ |
| **beats Brock — 1st badge** | ✅ |
| crosses Route 3 and **all of Mt. Moon** (three floors) | ✅ |
| reaches Cerulean, solves Bill's puzzle | ✅ |
| **beats Misty — 2nd badge** | ✅ |
| reaches Vermilion, boards the S.S. Anne, earns HM01 | ✅ |
| **learns Cut** | ✅ |
| Lt. Surge's gym (the trash can puzzle) | ⛔ not yet |

This was reproduced by **two independent bots** on the same day, each starting
from zero. Eleven of the game's 19 objectives are closed; what remains is
listed, by name and cause, in the [handoff](docs/HANDOFF.md).

## What you see on screen

- **the map of Kanto** with each bot walking in real time (drag to pan, scroll
  to zoom, click a bot to lock the camera on it);
- **each trainer's party** — species, level, HP, moves;
- **the journal**: "picked Vine Whip because it's 4× against Rock", "didn't
  catch it, no balls left", "stuck on this screen";
- **the arena**, when you click in: up to four live battles, with replays of
  each bot's most recent ones.

Every bot has a **fixed personality** and plays differently on purpose: a
completionist that wants everything registered, a rusher that only stops for
what's worth it, a team builder, and a themed one that fields nothing but fire
and dragon. Same rules, same map, different answers.

## Running it

Works on **Windows, macOS and Linux**. You need three things: Python 3.11+,
Node.js, and your own copy of Pokémon Blue.

1. Install [Python 3.11+](https://www.python.org/downloads/) and
   [Node.js LTS](https://nodejs.org). **On Windows, tick "Add python.exe to
   PATH"** — it's the most common mistake.
2. Put **your** legal copy at `roms/PokemonBlue.gb` (Red works too).
3. Start it:

   | System | How |
   |---|---|
   | **Windows** | double-click `start.bat` |
   | **macOS** | double-click `start.command` |
   | any | `python start.py` in a terminal |

It installs what's missing, brings up the dashboard, opens the browser and
starts playing. The first run takes a few minutes pulling dependencies; later
ones come up in seconds. `Ctrl+C` shuts down **saving** progress.

Worth knowing: `--slots 1` runs a single bot (lighter), `--no-browser` skips
opening the browser. **Two bots is the ceiling on an 8 GB laptop** — with three,
the OS kills one without warning (out of memory, not heat).

> **macOS:** if the system blocks it the first time, right-click → *Open*.
> **Windows:** if SmartScreen warns you, *More info* → *Run anyway*.

## Questions everyone asks

**Is this real AI?** Yes, though not the kind the word suggests today. It isn't
a model that learned to play by watching, nor an LLM mashing buttons. It's an
agent built from four classical AI pieces — graph search, planning with
preconditions, a battle expert system, and anomaly detection — plus a
reinforcement learning network that, when measured, currently decides **0%** of
the actions. The honest breakdown is in the [technical
details](#technical-details).

**Does it learn, or is it all hand-written?** Both, and the split is measured.
The pathing comes from a map **extracted from the cartridge** plus search — not
from a memorized route — and the bot recomputes from wherever it stands. What is
hand-written are the objectives and a few hard stretches. The neural network
exists, but what plays today is the search.

**Isn't reading game memory cheating?** It's the opposite: it's what prevents
cheating. The bot can't claim progress — the badge, the capture, the move
learned, all of it has to appear in RAM. Nothing is ever written to memory to
force a result.

**Do I need the ROM?** Yes, your own. Pokémon Blue is commercial software and
does not ship with this repository.

**Why Pokémon?** Because it's a large world with closed rules and an impartial
judge: the cartridge itself says whether you won.

## Where this is going: plain-language orders (coming soon)

**Nothing in this section works today.** It's the project's direction, written
against pieces that already exist — not a feature you'll find running.

The point of the project isn't finishing the game faster — it's the bot
**understanding an order**. *"Catch a Pikachu"* should be enough: it knows
Pikachu shows up in Viridian Forest at 5%, that it needs Poké Balls, and it
computes the path there from wherever it is.

The design for that, using pieces that already exist:

1. **a vocabulary of objectives** — be in place X, own species Y, hold item Z,
   have N badges — each one verifiable in RAM (which is what the QuestGraph
   already does across the game's 19 nodes);
2. **a solver**: given the objective, the Kanto graph answers the path and the
   preconditions say what's missing first (a ball in the bag, the badge that
   unlocks the area);
3. **the LLM as translator** — that's all: turn the sentence into an objective,
   once per order. It never decides step by step, where it's slow and wrong;
   execution belongs to the search, and verification to the cartridge.

Finishing the game, under that design, is just one order among others: "get the
eight badges".

---

# Technical details

From here down it's implementation: architecture, what was measured, and the
traps that cost real time. If you only want to watch the bots play, the part
above is enough.

## What AI is actually in here

| piece | what it is | where |
|---|---|---|
| **search** | Kanto as a graph — 49,412 cells, 2,152 doors, 106 edges — and breadth-first search from any point to any point | `src/kanto_graph.py` |
| **planning** | 19 objectives with preconditions verified in RAM; nothing is "done" because time passed or a button was pressed | `blue-agents/quest_graph.py` |
| **expert system** | battle policy reading type, power and PP from the cartridge's own tables | `src/simple_battle.py` |
| **anomaly detection** | a cartridge fingerprint every step; state that stops changing, or a loop repeating while the plan stands still, dumps a save plus the screen | `src/life_watchdog.py` |
| **reinforcement learning** 🟡 BETA | PPO (stable-baselines3) over exploration — decides 0% of actions today | `blue-agents/hybrid_agent.py` |

**The LLM part does not work yet.** There is an `src/llm_agent.py`, but today it
only answers the dashboard's "Ask AI" button — it decides nothing during the
journey, which neither depends on it nor touches the network. Translating a
plain-language order into a verifiable objective is the [project's next
step](#where-this-is-going-plain-language-orders-coming-soon), not something
already standing.

## Learning, measured rather than estimated

Instrumenting the origin of every action across a real run to Brock, over 471
steps:

```
battle_controller : 252  (53.5%)   heuristic reading RAM
quest_controller  : 219  (46.5%)   search and measured routes
ppo               :   0   (0.0%)
trainable transitions: none
```

PPO only gets the step when no controller wants to act. On top of that,
`ScriptAwarePPO` discards the entire rollout if **any** step was overridden by a
script — crediting reward to an action the network didn't take would be training
on fabricated data.

**The honest path to making learning matter more** is the reverse of the usual
attempt: use the recorded runs as **demonstrations** (behavior cloning) and let
reinforcement refine where no executor exists, instead of fighting the script
for the wheel.

### Archetypes 🟡 BETA

The **archetypes** (`blue-agents/archetypes.py`) fix traits, starter, and what
to do with a catchable wild encounter. They're the experiment's variable: same
map, same routes, different decisions.

They're beta because the easy half is done and the hard half isn't: all four run
and each decides differently on a catch, but **no complete run has compared the
four to the same point**. Until then the table below is the intended design, not
a measured result — unlike the PPO numbers above, which are a count from a real
traversal.

| Archetype | Stance on a possible catch |
|---|---|
| Completionist | 100% of what's reachable in each area; rarity never gets away |
| Rusher | spare balls and a strong Pokémon; the rest is a wasted turn |
| Team builder | whatever fills a slot or upgrades the front line |
| Fire and dragon | fire and dragon only; the hardest run in Kanto |

The completionist's target is 100% of what is **reachable**, which isn't 100% of
the area: Surf and the rods lock away whole encounter tables, so the required
set grows as badges arrive (`knowledge/maps/encounters.json`). Rarity outranks
quota — Pikachu is 5% of the Forest against Caterpie's 45%, and no fulfilled
quota makes the bot walk past it.

## How the bots find their way

**The geometry comes from the cartridge, not from bumping into things.**
`tools/extract_map_data.py` reads wall, grass, trainer, item and door for all
248 maps straight from the ROM: 238 maps and 49,412 cells in
`knowledge/maps/static_maps.json`. The previous version learned walls by
colliding, and that produced 21 maps and **4,067 walls that never existed** — a
standing NPC is indistinguishable from a wall, and a battle on screen makes
every tile read as one.

Since 2026-08-17 all three kinds of world connection live in the same graph:
a step within a map, a **border** between maps, and a **door**, the last two
extracted from the map header and the warp table
(`tools/extract_connections.py`). With that, "go from where I am to
`(map, tile)`" is a single search — Pallet to Brock is 371 steps across ten
maps, without a single hand-written coordinate. The graph even models the ledge
hop, as a one-way edge, and finds shortcuts no written route had (Vermilion via
Diglett's Cave).

The order of authority is fixed, and every inversion of it cost hours:
**live reads > ROM statics > recorded trail**. The measured route drives while
it reaches; the graph is the net for when it doesn't. A recorded trail never
drives where an executor exists — that caused four freezes in a single day.

The watchdog is the **cartridge fingerprint**: every step, map, position, party,
bag, badges and battle HP. State that doesn't grow in 600 steps, or the same
loop repeating while the plan stands still, is a freeze — and the save plus the
decoded screen get written automatically, so the defect becomes a test instead
of an all-nighter.

## Safety net

```bash
cd blue-agents && MPLCONFIGDIR=tasks/matplotlib ../.venv/bin/python -m unittest discover -s tests -q
cd blue-agents && ../.venv/bin/python tools/replay_check.py
```

The first is the unit suite (632). The second matters more: every stretch
already beaten became a **real save** in `states/replay/` plus what the
cartridge must answer after N steps. Unit tests don't touch the cartridge — the
suite once sat green at 548 tests while three fresh bots broke at four
consecutive points.

## Layout

- `blue-agents/`: PPO environment, agents, WebSocket and dashboard.
- `blue-agents/knowledge/`: QuestGraph, ROM-extracted maps, connections,
  per-area encounters and the 8 gyms.
- `blue-agents/tools/`: extractors (map, warps, connections, Centers), route
  probe, replay of beaten stretches, and the trail miner.
- `src/`: emulator, memory, Kanto graph, navigation, battle and watchdog.
- `roms/`: your legal copy, git-ignored.
- `states/`: game states and the replay saves.
- `trainers/<AGENT>/`: each trainer's save, journey and decision journal.
- `archives/<date>-<AGENT>/`: closed journeys, with a hash manifest.

## The ROM

Pokémon Blue is commercial software and is **not part of this repository**.
Everyone brings their own legal copy at `roms/PokemonBlue.gb`. The git history
doesn't carry it either: the ROMs that were versioned while the repository was
private were purged from every commit before it was made public.

`blue-agents/rom_identity.py` identifies the cartridge by its **header**: Red or
Blue both work, because they share maps, RAM addresses and the entire
QuestGraph. Yellow doesn't, and is rejected on purpose. There is no SHA-1 check
— legal cartridges get dumped by different people with different tools, and
demanding a byte-identical file would only push a team into passing a ROM around.
The digest is still computed and recorded into generated files, so an archived
journey can say which dump it came from.

## Speed and performance

The control at the top of the dashboard starts at `1×`, Game Boy pace, and goes
to `0.5×`, `2×` and `TRAINING` (uncapped). **With no dashboard open the cap
lifts by itself** — it exists only so the arena is watchable, and it costs a lot:
the same binary did 4 steps per second at `1×` and **446** uncapped, on the same
M1.

The environments run **sequentially inside a single process**, so throughput
saturates around 4 bots:

| Bots | Total steps/s | Per bot | Times Game Boy pace |
|---|---|---|---|
| 2 | 285 | 143 | ~57× |
| 4 | 377 | 94 | ~38× |
| 6 | 381 | 64 | ~25× |
| 8 | 390 | 49 | ~20× |

Reducing the bot count **deletes nobody**: the trainer leaves the active list
but keeps save, journal and progress under `trainers/`, and resumes where it
stopped.

## Replaying battles

The **Replays** button opens each trainer's most recent battles, with play,
pause and step-through. Recording only happens with the dashboard open and up to
`2×` — above that, battles end faster than anyone would watch. It costs no
performance: these are exactly the frames the arena already encodes.

## Journey telemetry

Each agent reads PyBoy's RAM and records into `trainers/<AGENT>/logs/`:

- maps, objectives and checkpoints reached;
- battle start/end, win, loss and whiteout;
- move chosen, effectiveness, reasoning and active Pokémon;
- catches confirmed via party/Pokédex, including sends to the PC;
- level ups, evolutions, PC deposits and the real XP target;
- freezes, with the decoded screen and the save attached.

In wild battles, catching is only considered available after the real
`EVENT_GOT_POKEDEX` event and when an actual Poké Ball is in the bag. The agent
explains whether it caught out of collector profile, team improvement or rarity;
otherwise it explains that it knocked the encounter out to train. Trainer
battles never attempt a catch, and the log distinguishes decision, attempt, and
capture confirmed in RAM.

## Continuing development

Contributors (human or agent) start from [AGENTS.md](AGENTS.md) and the
[canonical handoff](docs/HANDOFF.md), which records the real save state, the
freeze in progress, and the safe command to continue without restarting a
journey. The [QuestGraph map](docs/QUEST_GRAPH.md) separates what is already
validated on the cartridge, what has an executor, and what is still only a plan.

## Credits and asset provenance

This project is a fork of earlier community work. The credit lives here, in
writing, rather than burned into the images:

| Source | What came from it | Link |
|---|---|---|
| **Peter Whidden (PWhiddy)** — *PokemonRedExperiments* | The full Kanto map (`kanto_big_done1.png`), `map_data.json`, `global_map.py`, the base of the Gym environment and the visualizer | https://github.com/PWhiddy/PokemonRedExperiments |
| **Joseph Suárez (jsuarez5341) / PufferAI** | The RL tooling that ships with the original project | https://github.com/PufferAI |
| **PyBoy** | The Game Boy emulator used to run the real ROM | https://github.com/Baekalfen/PyBoy |

The watermarks embedded in the map PNG (three blocks, over Route 1) were removed
from the asset and replaced by this textual attribution. The removal was done by
reconstructing the map's own grass pattern — an 8×8 tile in two colors — and
erased no game element.
