"""The map as the cartridge shows it, remembered while walking.

Reading the screen tells the truth about eighty tiles at a time, and that is
plenty to step around what is directly in front — but not to walk around a
building, or out of a pocket whose exit is off screen. That is what kept a bot
pacing two tiles: from each of them the other looked like the best way to a
waypoint neither could reach.

So the readings are kept. Every step reveals a screenful of terrain, and terrain
does not change: unlike the old learned collision, which inferred walls from
failed steps and turned people into permanent geometry, nothing here is ever a
guess. Sprites are deliberately left out — they move, and they are read live.
"""

from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path

DIRECTIONS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}

# Mapa estático extraído do cartucho por `tools/extract_map_data.py`: 238 mapas
# e 49.412 células andáveis, contra 21 mapas aprendidos em dias de jogo.
STATIC_MAPS_PATH = (
    Path(__file__).resolve().parents[1]
    / "blue-agents" / "knowledge" / "maps" / "static_maps.json"
)


def _cells(tiles):
    out = set()
    for tile in tiles or ():
        try:
            x, y = (int(part) for part in str(tile).split(","))
        except ValueError:
            continue
        out.add((x, y))
    return out


def _load_static_maps(path):
    """Andável, mato e treinador por mapa, lidos do cartucho."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {}, {}, {}
    walkable, grass, trainers = {}, {}, {}
    for map_key, data in payload.items():
        cells = _cells(data.get("walkable"))
        if not cells:
            continue
        map_id = int(map_key)
        walkable[map_id] = cells
        grass[map_id] = _cells(data.get("grass"))
        trainers[map_id] = {
            (int(o["x"]), int(o["y"]))
            for o in data.get("objects", ())
            if o.get("kind") == "trainer"
        }
    return walkable, grass, trainers


class MapMemory:
    """Onde dá para pisar, segundo o cartucho — e o que sobrou de aprendido.

    A leitura de tela continua existindo para os mapas que a extração não
    cobre, mas onde o cartucho responde é ele quem manda. A diferença não é de
    grau: aprender esbarrando gravou 4067 paredes que nunca existiram, e uma
    batalha na tela faz todo tile ler como parede.
    """

    def __init__(self, path=None, static_path=STATIC_MAPS_PATH):
        self.path = Path(path) if path else None
        self.walkable = {}
        self.solid = {}
        self.dirty = False
        if static_path:
            self.static, self.grass, self.trainers = _load_static_maps(static_path)
        else:
            self.static, self.grass, self.trainers = {}, {}, {}
        self._load()

    def known_from_rom(self, map_id):
        """Este mapa saiu do cartucho? Se saiu, não há o que adivinhar nele."""
        return int(map_id) in self.static

    def grass_cells(self, map_id):
        """Células que rolam encontro selvagem, segundo o tileset do mapa."""
        return self.grass.get(int(map_id), set())

    def trainer_positions(self, map_id):
        """Onde cada treinador do mapa começa, para se manter longe deles."""
        return self.trainers.get(int(map_id), set())

    def _load(self):
        if self.path is None or not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return
        for key, maps in (("walkable", self.walkable), ("solid", self.solid)):
            for map_key, tiles in (payload.get(key) or {}).items():
                stored = set()
                for tile in tiles:
                    try:
                        x, y = (int(part) for part in str(tile).split(","))
                    except ValueError:
                        continue
                    stored.add((x, y))
                maps[int(map_key)] = stored

    def save(self):
        if self.path is None or not self.dirty:
            return
        payload = {"walkable": {}, "solid": {}}
        for key, maps in (("walkable", self.walkable), ("solid", self.solid)):
            for map_id, tiles in maps.items():
                payload[key][str(map_id)] = sorted(f"{x},{y}" for x, y in tiles)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(temporary, self.path)
        self.dirty = False

    def observe(self, map_id, origin, grid):
        """Store a screenful of terrain, given as offsets from ``origin``."""
        map_id = int(map_id)
        if self.known_from_rom(map_id):
            # Onde o cartucho já respondeu, a tela não acrescenta e pode
            # estragar: em batalha o mapa de tiles guarda a arena, e todo tile
            # lê como parede. Foi assim que a Floresta virou um bolsão fechado.
            return
        walkable = self.walkable.setdefault(map_id, set())
        solid = self.solid.setdefault(map_id, set())
        for (dx, dy), is_walkable in grid.items():
            tile = (origin[0] + dx, origin[1] + dy)
            target, other = (walkable, solid) if is_walkable else (solid, walkable)
            if tile in target:
                continue
            target.add(tile)
            other.discard(tile)
            self.dirty = True

    def is_solid(self, map_id, tile):
        map_id = int(map_id)
        cells = self.static.get(map_id)
        if cells is not None:
            return tuple(tile) not in cells
        return tuple(tile) in self.solid.get(map_id, ())

    def nearest_frontier(self, map_id, start, blocked=(), limit=4000):
        """Closest walkable tile that still touches something never seen.

        A goal behind a long wall turns optimistic planning into scraping: each
        search hops at the wall through a different unseen tile, learns one more
        stone, and tries the mirror image. Two trainers did that between (6,30)
        and (8,30) in the Forest for an afternoon.

        Frontier first, then. Walking to the edge of what is known is always
        progress, because it is the only thing that turns unknown into map.
        """
        map_id = int(map_id)
        start = tuple(start)
        solid = self.solid.get(map_id, set())
        walkable = self.walkable.get(map_id, set())
        avoid = {tuple(tile) for tile in blocked}
        seen = {start}
        queue = deque([start])
        while queue and len(seen) < limit:
            tile = queue.popleft()
            if tile != start and tile in walkable:
                for dx, dy in DIRECTIONS.values():
                    neighbour = (tile[0] + dx, tile[1] + dy)
                    if neighbour not in walkable and neighbour not in solid:
                        return tile
            for dx, dy in DIRECTIONS.values():
                neighbour = (tile[0] + dx, tile[1] + dy)
                if neighbour in seen or neighbour in solid or neighbour in avoid:
                    continue
                if neighbour not in walkable:
                    continue
                seen.add(neighbour)
                queue.append(neighbour)
        return None

    def forget_solid(self, map_id, tile):
        """Standing on a tile proves it is walkable, whatever was recorded.

        The screen stores metatile ids, and a few walkable subtiles read as
        wall. One wrong stone is harmless; a map full of them disconnects
        regions that are joined in the game, and the bot ends up trapped by
        its own notes. Walking onto a tile is the correction.
        """
        map_id = int(map_id)
        tile = tuple(tile)
        if tile in self.solid.get(map_id, ()):
            self.solid[map_id].discard(tile)
            self.walkable.setdefault(map_id, set()).add(tile)
            self.dirty = True

    def find_path(self, map_id, start, goal, blocked=(), limit=4000, ignore_solid=False):
        """Caminho mais curto: pelo mapa do cartucho, ou pelo que se viu.

        Onde o cartucho respondeu não há incógnita — a busca anda só por célula
        andável, e um alvo inalcançável é inalcançável de verdade em vez de um
        buraco no que ainda não foi olhado.

        Nos mapas que a extração não cobre vale a regra antiga: tile nunca visto
        conta como livre, e cada passo troca esse otimismo por uma leitura. O
        último waypoint de uma rota fica de propósito fora da grade, então o
        alvo nunca é exigido como andável.
        """
        map_id = int(map_id)
        start, goal = tuple(start), tuple(goal)
        if start == goal:
            return []
        cells = None if ignore_solid else self.static.get(map_id)
        solid = set() if ignore_solid else self.solid.get(map_id, set())
        avoid = {tuple(tile) for tile in blocked}
        came = {start: None}
        queue = deque([start])
        while queue and len(came) < limit:
            tile = queue.popleft()
            if tile == goal:
                break
            for direction, (dx, dy) in DIRECTIONS.items():
                neighbour = (tile[0] + dx, tile[1] + dy)
                if neighbour in came or neighbour in avoid:
                    continue
                if cells is not None:
                    if neighbour != goal and neighbour not in cells:
                        continue
                elif neighbour in solid:
                    continue
                if not (0 <= neighbour[0] <= 255 and 0 <= neighbour[1] <= 255):
                    continue
                came[neighbour] = (tile, direction)
                queue.append(neighbour)
        if goal not in came:
            return None
        path = []
        node = goal
        while came[node] is not None:
            previous, direction = came[node]
            path.append(direction)
            node = previous
        path.reverse()
        return path
