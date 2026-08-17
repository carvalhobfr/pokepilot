#!/usr/bin/env python3
"""As bordas e as portas de Kanto, lidas do cartucho.

Este projeto já lê do ROM a geometria de cada mapa (`static_maps.json`, 238
mapas e 49.412 células) e onde ficam as portas (`warps.json`). O que faltava era
**como um mapa se liga ao outro** — e sem isso `find_path` só sabe andar dentro
de um mapa, então atravessar Kanto virou onze executores escritos à mão, cada um
com as coordenadas de uma travessia decoradas.

Duas ligações existem no cartucho e as duas saem daqui:

1. **borda** (`connection`): o cabeçalho de cada mapa tem um byte de direções
   (N=8, S=4, O=2, L=1) e, para cada uma, 11 bytes com o mapa vizinho e dois
   alinhamentos. Andar para fora da borda não é warp: é o jogo carregar o mapa
   vizinho e reposicionar o jogador;
2. **porta** (`warp`): a tabela de warps de cada mapa, com o índice do warp de
   chegada no mapa de destino — é ele que dá o **tile** onde se chega, e era o
   que faltava para uma porta virar aresta de grafo.

A conta do reposicionamento de borda, conferida contra dois fatos que este
projeto já tinha medido no cartucho:

    vertical   (N/S): y de chegada = y_align,      x de chegada = x + x_align
    horizontal (O/L): x de chegada = x_align,      y de chegada = y + y_align

- Cerulean sul → Route 5 tem `x_align = -10`, e reproduz o `(26,35) -> (16,0)`
  medido em 2026-08-16 ("a conexão soma 10 ao x");
- Route 4 leste → Cerulean tem `y_align = 8`, e reproduz o `(79,10) -> (0,18)`
  medido em 2026-08-12, que é o tile por onde o AARON entrou na cidade.

Destino `0xFF` numa porta é "volta para o mapa de onde vim", resolvido em tempo
de execução — fica gravado como `-1`, e quem monta o grafo trata isso como a
volta da porta por onde se entrou.

    cd blue-agents && ../.venv/bin/python tools/extract_connections.py --write
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROM_PATH = PROJECT_ROOT / "roms" / "PokemonBlue.gb"
OUTPUT = PROJECT_ROOT / "blue-agents" / "knowledge" / "maps" / "connections.json"

MAP_HEADER_POINTERS = 0x01AE
MAP_HEADER_BANKS = 0xC23D
MAP_COUNT = 248
# Byte de direções do cabeçalho, e a ordem em que os blocos de 11 bytes vêm.
CONNECTION_BYTE_OFFSET = 9
CONNECTION_BLOCK_BYTES = 11
DIRECTIONS = (("north", 0x08), ("south", 0x04), ("west", 0x02), ("east", 0x01))
DYNAMIC_DESTINATION = 0xFF


def signed(value):
    """Os alinhamentos são deslocamentos com sinal: 246 é -10, 248 é -8."""
    return value - 256 if value > 127 else value


class Cartridge:
    def __init__(self, rom_bytes):
        self.rom = rom_bytes

    @staticmethod
    def _absolute(bank, address):
        return bank * 0x4000 + (address - 0x4000 if address >= 0x4000 else address)

    def header_start(self, map_id):
        pointer = (
            self.rom[MAP_HEADER_POINTERS + map_id * 2]
            | (self.rom[MAP_HEADER_POINTERS + map_id * 2 + 1] << 8)
        )
        bank = self.rom[MAP_HEADER_BANKS + map_id]
        start = self._absolute(bank, pointer)
        if not 0 <= start < len(self.rom) - 16:
            return None, None
        return start, bank

    def borders(self, map_id):
        """As conexões de borda deste mapa, já com a conta do reposicionamento."""
        start, _bank = self.header_start(map_id)
        if start is None:
            return []
        flags = self.rom[start + CONNECTION_BYTE_OFFSET]
        cursor = start + CONNECTION_BYTE_OFFSET + 1
        found = []
        for name, bit in DIRECTIONS:
            if not flags & bit:
                continue
            block = self.rom[cursor:cursor + CONNECTION_BLOCK_BYTES]
            cursor += CONNECTION_BLOCK_BYTES
            if len(block) < CONNECTION_BLOCK_BYTES:
                continue
            found.append({
                "dir": name,
                "to": int(block[0]),
                "y_align": signed(block[7]),
                "x_align": signed(block[8]),
                "strip_length": int(block[5]),
                "dest_width_blocks": int(block[6]),
            })
        return found

    def warps(self, map_id):
        """Portas com o **índice de chegada** no mapa de destino."""
        start, bank = self.header_start(map_id)
        if start is None:
            return []
        flags = self.rom[start + CONNECTION_BYTE_OFFSET]
        cursor = start + CONNECTION_BYTE_OFFSET + 1
        cursor += CONNECTION_BLOCK_BYTES * bin(flags).count("1")
        if not 0 <= cursor < len(self.rom) - 2:
            return []
        block = self._absolute(
            bank, self.rom[cursor] | (self.rom[cursor + 1] << 8)
        )
        if not 0 <= block < len(self.rom) - 2:
            return []
        total = self.rom[block + 1]
        found = []
        for index in range(total):
            base = block + 2 + index * 4
            if base + 4 > len(self.rom):
                break
            y, x, target_index, destination = self.rom[base:base + 4]
            found.append({
                "x": int(x),
                "y": int(y),
                "to": (
                    -1 if destination == DYNAMIC_DESTINATION else int(destination)
                ),
                "to_warp": int(target_index),
            })
        return found


def build(rom_path=ROM_PATH):
    cartridge = Cartridge(Path(rom_path).read_bytes())
    maps = {}
    for map_id in range(MAP_COUNT):
        borders = cartridge.borders(map_id)
        warps = cartridge.warps(map_id)
        if not borders and not warps:
            continue
        maps[str(map_id)] = {"borders": borders, "warps": warps}
    return {
        "why": (
            "Como um mapa se liga ao outro, lido do cabeçalho de mapa e da "
            "tabela de warps. Borda reposiciona pela conta dos alinhamentos; "
            "porta chega no warp de índice `to_warp` do mapa de destino."
        ),
        "maps": maps,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", default=str(ROM_PATH))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--map", type=int, default=None)
    args = parser.parse_args()

    data = build(args.rom)
    maps = data["maps"]
    borders = sum(len(m["borders"]) for m in maps.values())
    warps = sum(len(m["warps"]) for m in maps.values())
    print(f"{len(maps)} mapas, {borders} bordas, {warps} portas")

    if args.map is not None:
        print(json.dumps(maps.get(str(args.map), {}), indent=2))

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        temporary = OUTPUT.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, indent=1), encoding="utf-8")
        temporary.replace(OUTPUT)
        print(f"escrito em {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
