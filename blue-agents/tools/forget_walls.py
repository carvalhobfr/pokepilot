#!/usr/bin/env python3
"""Esquece as paredes lembradas, preservando os tiles caminháveis.

O mapa acumulado (`knowledge/maps/terrain.json`) guarda duas coisas, e elas não
correm o mesmo risco. Um tile marcado **caminhável** por engano custa uma
esbarrada: o passo falha, a leitura ao vivo recusa, e a vida segue. Um tile
marcado **parede** por engano é permanente e invisível — o planejador desvia
dele para sempre, o bot nunca volta a olhá-lo, e nada no projeto desaprende uma
parede.

Foi assim que a Floresta de Viridian virou quatro pedaços sem ligação entre si.
A tela de batalha ocupa o mesmo tilemap do mapa, e todo tile dela lê como
parede; algumas lutas no mato bastaram para emparedar o caminho. A trava já
existe em `_planned_step` (só lê terreno fora de batalha e fora de menu), mas os
dados gravados antes dela continuaram valendo, compartilhados por todos os
treinadores.

Esta ferramenta descarta as paredes e mantém o que foi visto como caminhável. O
arquivo anterior é copiado para `.envenenado/` antes de qualquer escrita.

    ./blue-agents/tools/forget_walls.py --dry-run   # só mostra
    ./blue-agents/tools/forget_walls.py             # esquece e guarda cópia
    ./blue-agents/tools/forget_walls.py --map 51    # só um mapa
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERRAIN = ROOT / "blue-agents" / "knowledge" / "maps" / "terrain.json"


def componentes(caminhaveis: set[tuple[int, int]]) -> list[int]:
    """Tamanho de cada ilha de tiles caminháveis ligados entre si."""
    from collections import deque

    restantes = set(caminhaveis)
    tamanhos = []
    while restantes:
        inicio = restantes.pop()
        ilha = {inicio}
        fila = deque([inicio])
        while fila:
            x, y = fila.popleft()
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                vizinho = (x + dx, y + dy)
                if vizinho in restantes:
                    restantes.discard(vizinho)
                    ilha.add(vizinho)
                    fila.append(vizinho)
        tamanhos.append(len(ilha))
    return sorted(tamanhos, reverse=True)


def tiles(entradas) -> set[tuple[int, int]]:
    saida = set()
    for entrada in entradas or ():
        try:
            x, y = (int(parte) for parte in str(entrada).split(","))
        except ValueError:
            continue
        saida.add((x, y))
    return saida


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="não grava nada")
    parser.add_argument("--map", default="", help="esquecer as paredes de um mapa só")
    argumentos = parser.parse_args()

    try:
        with TERRAIN.open(encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except (OSError, ValueError) as erro:
        print(f"Não consegui ler {TERRAIN}: {erro}")
        return 1

    caminhaveis = dados.get("walkable") or {}
    solidos = dados.get("solid") or {}
    alvos = [argumentos.map] if argumentos.map else sorted(
        set(caminhaveis) | set(solidos), key=lambda chave: int(chave)
    )

    total_paredes = 0
    for mapa in alvos:
        livres = tiles(caminhaveis.get(mapa))
        paredes = tiles(solidos.get(mapa))
        total_paredes += len(paredes)
        ilhas = componentes(livres)
        partido = "" if len(ilhas) <= 1 else f"  ⚠️  partido em {len(ilhas)}: {ilhas[:4]}"
        print(f"  mapa {mapa:>3}: {len(livres):>5} caminháveis, {len(paredes):>5} paredes{partido}")

    if argumentos.dry_run:
        print(f"\n--dry-run: {total_paredes} paredes seriam esquecidas.")
        return 0

    reserva = TERRAIN.parent / ".envenenado"
    reserva.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    copia = reserva / f"terrain-{marca}.json"
    shutil.copy2(TERRAIN, copia)

    for mapa in alvos:
        solidos.pop(mapa, None)
    dados["solid"] = solidos

    temporario = TERRAIN.with_suffix(".json.tmp")
    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo)
    os.replace(temporario, TERRAIN)

    print(f"\n{total_paredes} paredes esquecidas; os tiles caminháveis ficaram.")
    print(f"Arquivo anterior preservado em {copia.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
