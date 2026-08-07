#!/usr/bin/env python3
"""As portas de Kanto, lidas do cartucho em vez de aprendidas esbarrando.

`WarpMemory.record` gravava "o tile onde o bot estava quando o mapa mudou". A
regra parece boa e se envenena sozinha: num apagão o mapa muda sem que o bot
tenha pisado em porta nenhuma, e o chão onde ele estava vira porta para sempre.
Mt. Moon 1F acumulou **62 portas** apontando para a Rota 4, quase todas tiles
de chão comum — e com elas o controlador de saída passou a atravessar paredes
imaginárias no meio da caverna.

O cartucho tem a lista de verdade. Cada cabeçalho de mapa aponta para um bloco
de objetos que começa com os warps: um byte de quantidade e quatro bytes por
entrada, `{y, x, índice do warp de destino, mapa de destino}`.

Destino `0xFF` significa "volta para o mapa de fora de onde vim" — o cartucho
resolve isso em tempo de execução, e aqui ele fica registrado como `-1` para
quem lê saber que é dinâmico.

Uso:

    ../.venv/bin/python tools/extract_warps.py            # mostra o diff
    ../.venv/bin/python tools/extract_warps.py --write    # grava warps.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROM_PATH = PROJECT_ROOT / "roms" / "PokemonBlue.gb"
OUTPUT = PROJECT_ROOT / "blue-agents" / "knowledge" / "maps" / "warps.json"

MAP_HEADER_POINTERS = 0x01AE
MAP_HEADER_BANKS = 0xC23D
MAP_COUNT = 248
MAX_WARPS_PER_MAP = 32
DYNAMIC_DESTINATION = 0xFF


def _absolute(bank, address):
    return bank * 0x4000 + (address - 0x4000 if address >= 0x4000 else address)


def object_block(rom, map_id):
    """Onde começa o bloco de objetos deste mapa, ou None se ilegível."""
    pointer = (
        rom[MAP_HEADER_POINTERS + map_id * 2]
        | (rom[MAP_HEADER_POINTERS + map_id * 2 + 1] << 8)
    )
    bank = rom[MAP_HEADER_BANKS + map_id]
    start = _absolute(bank, pointer)
    if not 0 <= start < len(rom) - 16:
        return None
    cursor = start + 9
    connections = rom[cursor]
    cursor += 1 + 11 * bin(connections).count("1")
    if not 0 <= cursor < len(rom) - 2:
        return None
    block = _absolute(bank, rom[cursor] | (rom[cursor + 1] << 8))
    return block if 0 <= block < len(rom) - 2 else None


def warps_of(rom, map_id):
    """`{"x,y": mapa de destino}` — o que o cartucho diz, e só isso."""
    block = object_block(rom, map_id)
    if block is None:
        return {}
    total = rom[block + 1]
    if total > MAX_WARPS_PER_MAP:
        return {}
    doors = {}
    for index in range(total):
        base = block + 2 + index * 4
        y, x, _target_index, destination = rom[base:base + 4]
        doors[f"{x},{y}"] = (
            -1 if destination == DYNAMIC_DESTINATION else int(destination)
        )
    return doors


def build(rom_path=ROM_PATH):
    rom = Path(rom_path).read_bytes()
    doors = {}
    for map_id in range(MAP_COUNT):
        found = warps_of(rom, map_id)
        if found:
            doors[str(map_id)] = found
    return doors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if not ROM_PATH.is_file():
        print(f"ROM não encontrada em {ROM_PATH}", file=sys.stderr)
        return 1

    novo = build()
    try:
        antigo = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        antigo = {}

    total_novo = sum(len(v) for v in novo.values())
    total_antigo = sum(len(v) for v in antigo.values())
    print(f"cartucho: {len(novo)} mapas, {total_novo} portas")
    print(f"arquivo : {len(antigo)} mapas, {total_antigo} portas")

    for map_id in sorted(antigo, key=int):
        inventadas = set(antigo[map_id]) - set(novo.get(map_id, {}))
        if inventadas:
            print(f"  mapa {map_id}: {len(inventadas)} portas que o cartucho não tem")

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(novo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"gravado em {OUTPUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
