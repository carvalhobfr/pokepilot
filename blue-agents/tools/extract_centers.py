#!/usr/bin/env python3
"""Os Centros Pokémon, lidos do cartucho em vez de escritos à mão.

A lista à mão tinha 11 mapas: faltava o da Rota 10 (81), que é o Centro antes
do Túnel da Rocha, e sobrava o saguão do Indigo (174), que não é um Centro —
tem outro tileset, outro tamanho e outra planta, então o controlador genérico
(enfermeira em (3,3), capacho em (3,7)) faria besteira lá dentro.

Como o cartucho responde:

- o **tileset 6** é o interior de Centro, e os 12 mapas que o usam têm todos
  exatamente 4×7;
- um deles, o 140, é o **Hotel de Celadon**: mesmo tileset e mesmo tamanho, mas
  o cabeçalho denuncia — os Centros de verdade têm o ponteiro de texto seis
  bytes depois do de script e quatro NPCs, e o hotel tem três bytes, três NPCs
  e uma planta de blocos que nenhum outro mapa usa;
- a porta de cada Centro sai da tabela de warps do mapa de fora, então nenhuma
  coordenada aqui foi medida à mão.

Uso:

    ../.venv/bin/python tools/extract_centers.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROM_PATH = PROJECT_ROOT / "roms" / "PokemonBlue.gb"
OUTPUT = PROJECT_ROOT / "blue-agents" / "knowledge" / "maps" / "pokemon_centers.json"

MAP_HEADER_POINTERS = 0x01AE
MAP_HEADER_BANKS = 0xC23D
MAP_COUNT = 248
POKECENTER_TILESET = 6
POKECENTER_SIZE = (4, 7)
# Num Centro o ponteiro de texto vem logo depois do de script. O hotel de
# Celadon reaproveita o tileset mas não essa disposição.
CENTER_TEXT_OFFSET = 6


def _absolute(bank, address):
    return bank * 0x4000 + (address - 0x4000 if address >= 0x4000 else address)


class Cartridge:
    def __init__(self, rom_bytes):
        self.rom = rom_bytes

    def header(self, map_id):
        pointer = (
            self.rom[MAP_HEADER_POINTERS + map_id * 2]
            | (self.rom[MAP_HEADER_POINTERS + map_id * 2 + 1] << 8)
        )
        bank = self.rom[MAP_HEADER_BANKS + map_id]
        start = _absolute(bank, pointer)
        if not 0 <= start < len(self.rom) - 16:
            return None
        script = self.rom[start + 7] | (self.rom[start + 8] << 8)
        text = self.rom[start + 5] | (self.rom[start + 6] << 8)
        cursor = start + 9
        connections = self.rom[cursor]
        cursor += 1 + 11 * bin(connections).count("1")
        objects = _absolute(
            bank, self.rom[cursor] | (self.rom[cursor + 1] << 8)
        )
        return {
            "tileset": self.rom[start],
            "height": self.rom[start + 1],
            "width": self.rom[start + 2],
            "script": script,
            "text": text,
            "objects": objects,
        }

    def warps(self, map_id):
        head = self.header(map_id)
        if head is None:
            return []
        start = head["objects"]
        if not 0 <= start < len(self.rom) - 2:
            return []
        total = self.rom[start + 1]
        if total > 32:
            return []
        entries = []
        for index in range(total):
            base = start + 2 + index * 4
            entries.append({
                "x": self.rom[base + 1],
                "y": self.rom[base],
                "destination": self.rom[base + 3],
            })
        return entries

    def npc_count(self, map_id):
        head = self.header(map_id)
        if head is None:
            return 0
        cursor = head["objects"] + 1
        warps = self.rom[cursor]
        cursor += 1 + warps * 4
        signs = self.rom[cursor]
        cursor += 1 + signs * 3
        return self.rom[cursor]


def find_centers(cart):
    """Mapas que são de fato Centro Pokémon, com o hotel descartado."""
    centers = []
    for map_id in range(MAP_COUNT):
        head = cart.header(map_id)
        if head is None or head["tileset"] != POKECENTER_TILESET:
            continue
        if (head["height"], head["width"]) != POKECENTER_SIZE:
            continue
        if head["text"] - head["script"] != CENTER_TEXT_OFFSET:
            # Hotel de Celadon: mesma casca, outro roteiro.
            continue
        centers.append(map_id)
    return centers


def find_doors(cart, centers):
    """Para cada Centro, de qual mapa e por qual tile se entra."""
    doors = {}
    wanted = set(centers)
    for map_id in range(MAP_COUNT):
        for warp in cart.warps(map_id):
            destination = warp["destination"]
            if destination in wanted:
                doors.setdefault(destination, []).append(
                    {"map": map_id, "x": warp["x"], "y": warp["y"]}
                )
    return doors


def build(rom_path=ROM_PATH):
    cart = Cartridge(Path(rom_path).read_bytes())
    centers = find_centers(cart)
    doors = find_doors(cart, centers)
    return {
        "source": "roms/PokemonBlue.gb",
        "how": (
            "tileset 6, 4x7, ponteiro de texto seis bytes depois do de script; "
            "portas vindas da tabela de warps do mapa de fora"
        ),
        "centers": sorted(centers),
        "doors": {
            str(center): doors.get(center, []) for center in sorted(centers)
        },
    }


def main():
    if not ROM_PATH.is_file():
        print(f"ROM não encontrada em {ROM_PATH}", file=sys.stderr)
        return 1
    payload = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{len(payload['centers'])} Centros -> {OUTPUT.relative_to(PROJECT_ROOT)}")
    for center in payload["centers"]:
        portas = ", ".join(
            f"mapa {d['map']} ({d['x']},{d['y']})" for d in payload["doors"][str(center)]
        )
        print(f"  {center:3d}: {portas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
