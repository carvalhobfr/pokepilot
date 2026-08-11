# Referência: pokemonred_puffer (pokerl)

Pedaços úteis do [drubinstein/pokemonred_puffer](https://github.com/drubinstein/pokemonred_puffer)
(clonado em 2026-08-11, branch `main`) — o projeto sucessor do PokemonRedExperiments que
anunciou ter zerado Pokémon Red com RL puro. Copiado como **referência de reward shaping e
de RAM**, não para rodar: a stack de treino deles (PufferLib + swarm de 72 envs) não é a nossa.

Licença MIT (declarada no GitHub; o clone não traz arquivo LICENSE). Red e Blue compartilham
motor e RAM, então endereços e savestates servem para o nosso Blue com ressalvas.

## O que foi copiado

| Caminho | O que é | Para que serve aqui |
|---|---|---|
| `data/events.py` | `EventFlagsBits` (struct bit-a-bit de 0xD747), `EVENTS`, `REQUIRED_EVENTS` | `REQUIRED_EVENTS` (~75 flags) = checklist legível em RAM do que precisa acontecer pra zerar. Cruzar com as quests em `knowledge/routes/` para medir cobertura real. Nomes em asm (EVENT_GOT_HM01) são mais canônicos que nosso events.json |
| `data/items.py` | IDs de item + `REQUIRED_ITEMS`, `USEFUL_ITEMS`, `KEY_ITEMS`, `HM_ITEMS` | Progressão com gate de item (Cut, SS Ticket, Lift Key) que nossa régua de insígnias não pega. Padrão de leitura da mochila: `wBagItems[wBagItems : wBagItems + 2*numBagItems : 2]` |
| `rewards/baseline.py` | As classes de recompensa do game inteiro (eventos, Bill, Cut, menus, missables) | Referência de reward shaping; mostra a cadeia do Bill como beats de história sequenciais |
| `wrappers/exploration.py` | `LRUCache` + `DecayWrapper` | Exploração com decaimento em vez do contador monotônico de `seen_coords` |
| `data/strength_puzzles.py` | Geometria dos puzzles Sokoban de Strength | Futura quest de Strength |
| `data/tilesets.py` | IDs de tileset | Recompensa de exploração por tileset |
| `data/field_moves.py` | `FieldMoves` (CUT/FLY/SURF/...) | Enum de campo |
| `pyboy_states/` | Savestates de marcos do jogo (Brock → campeão) | Validar extractores e batalha sem jogar o jogo todo; **carregam no nosso Blue** com risco pequeno nas versões exclusivas (SS Anne, Safari) |

> **Nota:** carregar um `.state` gera `WARNING  Loading state from an older
> version of PyBoy`. É esperado; os estados carregam e a RAM lê normalmente.

## O que foi podado (não copiado)

- `environment.py` (1.980 linhas) — já temos nosso env
- `cleanrl_puffer.py`, `train.py`, `sweep.py`, `policies/`, `resnet.py`, `c_gae.pyx`, `profile.py` — stack PufferLib, outra arquitetura
- `global_map.py`, `kanto_map_dsv.png` — navegam por imagem global; nosso `static_maps.json` (238 mapas) é superior
- `data/map.py` — enum de mapas; já temos os mapas do cartucho
- `data/{bag,elevators,flags,moves,party,species,tm_hm,missable_objects}.py` — conhecimento que já construímos via PokéAPI
- `visualizations/`, `tests/`, `.github/`, `assets/`, `eval.py`, `events.json` (o nosso tem 2.558 endereços), `map_data.json`

## Ideias do MaKSiiMe/PokemonBlueExperiments (Blue, não copiado — só idéias)

- **visited_mask persistente entre episódios** — nosso `explore_map` zera a cada reset; manter a memória cruza episódios
- **action masking em batalha** (desabilita A se todos os moves são imunes) + reward de tipo-advantage

## Uso rápido

```bash
# cruzar REQUIRED_EVENTS com as quests que temos:
#   grep EVENT_ data/events.py  vs  knowledge/routes/*.json
```

```bash
# carregar um savestate no Blue (ex.: mtmoon) para validar extractor de mapa:
cd blue-agents && ../.venv/bin/python -c "
from pyboy import PyBoy
pyboy = PyBoy('../../../roms/PokemonBlue.gb', window='null')
with open('examples/pokered_puffer/pyboy_states/mtmoon.state','rb') as f:
    pyboy.load_state(f)
print('map', hex(pyboy.memory[0xD35E]))
pyboy.stop(save=False)
"
```
