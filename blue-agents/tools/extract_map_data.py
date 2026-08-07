#!/usr/bin/env python3
"""O mapa inteiro, lido do cartucho: parede, mato, treinador, item, porta.

Este projeto aprendia geometria esbarrando: apertou uma direção, não saiu do
lugar, logo aquela aresta é parede. A regra parece razoável e se envenena
sozinha — um NPC parado vira parede, uma batalha na tela faz todo tile ler como
parede, e o handoff registra 4067 paredes que nunca existiram. O mesmo aconteceu
com as portas: 62 registradas em Mt. Moon, das quais o cartucho reconhece 5.

Nada disso precisava ser aprendido. Está tudo na ROM:

| o que | onde |
|---|---|
| parede vs andável | lista de tiles passáveis do tileset |
| mato que rola encontro | byte de grama do tileset (o que a RAM espelha em 0xD535) |
| treinador, NPC, item no chão | bloco de objetos do mapa |
| porta | tabela de warps, no mesmo bloco |
| geometria | blockdata: blocos de 4x4 tiles, 2x2 passos cada |

Conferido no mapa 51: a ROM diz 719 células andáveis, e das 719 que o bot pisou
de verdade em horas de jogo, **nenhuma** é chamada de parede aqui.

Uso:

    ../.venv/bin/python tools/extract_map_data.py 51        # mostra um mapa
    ../.venv/bin/python tools/extract_map_data.py --write   # grava todos
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROM_PATH = PROJECT_ROOT / "roms" / "PokemonBlue.gb"
OUTPUT = PROJECT_ROOT / "blue-agents" / "knowledge" / "maps" / "static_maps.json"

MAP_HEADER_POINTERS = 0x01AE
MAP_HEADER_BANKS = 0xC23D
TILESET_TABLE = 0xC7BE
TILESET_ENTRY_BYTES = 12
MAP_COUNT = 248
# Um bloco tem 4x4 tiles e vale 2x2 passos: cada passo é um quadrante 2x2, e a
# colisão do quadrante é decidida pelo tile inferior-esquerdo dele.
BLOCK_TILES = 16
NO_GRASS = 0xFF
# No registro de objeto, o id de texto carrega o tipo nos dois bits altos.
TEXT_TRAINER = 0x40
TEXT_ITEM = 0x80
OBJECT_BYTES = 6
# As coordenadas de objeto vêm deslocadas de 4 no cartucho.
OBJECT_ORIGIN = 4


class Cartridge:
    def __init__(self, rom_bytes):
        self.rom = rom_bytes
        self._passable = {}

    @staticmethod
    def _absolute(bank, address):
        return bank * 0x4000 + (address - 0x4000 if address >= 0x4000 else address)

    def header(self, map_id):
        pointer = (
            self.rom[MAP_HEADER_POINTERS + map_id * 2]
            | (self.rom[MAP_HEADER_POINTERS + map_id * 2 + 1] << 8)
        )
        bank = self.rom[MAP_HEADER_BANKS + map_id]
        start = self._absolute(bank, pointer)
        if not 0 <= start < len(self.rom) - 16:
            return None
        cursor = start + 9
        connections = self.rom[cursor]
        cursor += 1 + 11 * bin(connections).count("1")
        if not 0 <= cursor < len(self.rom) - 2:
            return None
        return {
            "tileset": self.rom[start],
            "height": self.rom[start + 1],
            "width": self.rom[start + 2],
            "blockdata": self._absolute(
                bank, self.rom[start + 3] | (self.rom[start + 4] << 8)
            ),
            "objects": self._absolute(
                bank, self.rom[cursor] | (self.rom[cursor + 1] << 8)
            ),
        }

    def tileset(self, index):
        base = TILESET_TABLE + index * TILESET_ENTRY_BYTES
        return {
            "bank": self.rom[base],
            "blocks": self.rom[base + 1] | (self.rom[base + 2] << 8),
            "collision": self.rom[base + 5] | (self.rom[base + 6] << 8),
            "grass": self.rom[base + 10],
        }

    def passable_tiles(self, index):
        """Tiles que se pode pisar, segundo o tileset. Lista termina em 0xFF."""
        if index in self._passable:
            return self._passable[index]
        cursor = self.tileset(index)["collision"]
        tiles = set()
        while self.rom[cursor] != 0xFF:
            tiles.add(self.rom[cursor])
            cursor += 1
        self._passable[index] = tiles
        return tiles

    def terrain(self, map_id):
        """`(andaveis, mato)` em coordenadas de passo, como o jogo as conta."""
        head = self.header(map_id)
        if head is None:
            return set(), set()
        tileset = self.tileset(head["tileset"])
        passable = self.passable_tiles(head["tileset"])
        blocks = self._absolute(tileset["bank"], tileset["blocks"])
        walkable, grass = set(), set()
        for block_y in range(head["height"]):
            for block_x in range(head["width"]):
                block = self.rom[head["blockdata"] + block_y * head["width"] + block_x]
                tiles = self.rom[blocks + block * BLOCK_TILES:][:BLOCK_TILES]
                if len(tiles) < BLOCK_TILES:
                    continue
                for step_y in range(2):
                    for step_x in range(2):
                        tile = tiles[(step_y * 2 + 1) * 4 + step_x * 2]
                        cell = (block_x * 2 + step_x, block_y * 2 + step_y)
                        if tile in passable:
                            walkable.add(cell)
                        if tile == tileset["grass"] != NO_GRASS:
                            grass.add(cell)
        return walkable, grass

    def objects(self, map_id):
        """Warps, placas e o resto: treinador, NPC e item, com coordenadas."""
        head = self.header(map_id)
        if head is None:
            return [], []
        cursor = head["objects"]
        warp_count = self.rom[cursor + 1]
        if warp_count > 32:
            return [], []
        warps = []
        for index in range(warp_count):
            base = cursor + 2 + index * 4
            y, x, _target, destination = self.rom[base:base + 4]
            warps.append({
                "x": x, "y": y,
                "to": -1 if destination == 0xFF else int(destination),
            })
        cursor += 2 + warp_count * 4
        sign_count = self.rom[cursor]
        cursor += 1 + sign_count * 3
        object_count = self.rom[cursor]
        cursor += 1
        people = []
        for _ in range(object_count):
            sprite, y, x, movement, facing, text = self.rom[cursor:cursor + OBJECT_BYTES]
            cursor += OBJECT_BYTES
            entry = {
                "x": int(x) - OBJECT_ORIGIN,
                "y": int(y) - OBJECT_ORIGIN,
                "sprite": int(sprite),
                "movement": int(movement),
            }
            if text & TEXT_TRAINER:
                entry["kind"] = "trainer"
                entry["trainer_class"] = int(self.rom[cursor])
                entry["trainer_number"] = int(self.rom[cursor + 1])
                entry["facing"] = int(facing)
                cursor += 2
            elif text & TEXT_ITEM:
                entry["kind"] = "item"
                entry["item_id"] = int(self.rom[cursor])
                cursor += 1
            else:
                entry["kind"] = "npc"
            people.append(entry)
        return warps, people


def build(rom_path=ROM_PATH):
    cart = Cartridge(Path(rom_path).read_bytes())
    maps = {}
    for map_id in range(MAP_COUNT):
        head = cart.header(map_id)
        if head is None:
            continue
        walkable, grass = cart.terrain(map_id)
        if not walkable:
            continue
        warps, people = cart.objects(map_id)
        maps[str(map_id)] = {
            "tileset": head["tileset"],
            "size": [head["width"] * 2, head["height"] * 2],
            "walkable": sorted(f"{x},{y}" for x, y in walkable),
            "grass": sorted(f"{x},{y}" for x, y in grass),
            "warps": warps,
            "objects": people,
        }
    return maps


def describe(maps, map_id):
    data = maps.get(str(map_id))
    if data is None:
        print(f"mapa {map_id}: sem dados")
        return
    trainers = [o for o in data["objects"] if o["kind"] == "trainer"]
    items = [o for o in data["objects"] if o["kind"] == "item"]
    print(f"mapa {map_id}: tileset {data['tileset']}, {data['size'][0]}x{data['size'][1]} passos")
    print(f"  andáveis {len(data['walkable'])}  mato {len(data['grass'])}")
    print(f"  portas {len(data['warps'])}  treinadores {len(trainers)}  itens {len(items)}")
    for trainer in trainers:
        print(f"    treinador classe {trainer['trainer_class']}"
              f" #{trainer['trainer_number']} em ({trainer['x']},{trainer['y']})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map_id", nargs="?", type=int)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if not ROM_PATH.is_file():
        print(f"ROM não encontrada em {ROM_PATH}", file=sys.stderr)
        return 1

    maps = build()
    total = sum(len(m["walkable"]) for m in maps.values())
    print(f"{len(maps)} mapas, {total} células andáveis")

    if args.map_id is not None:
        describe(maps, args.map_id)
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(maps, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        tamanho = OUTPUT.stat().st_size / 1024
        print(f"gravado em {OUTPUT.relative_to(PROJECT_ROOT)} ({tamanho:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
