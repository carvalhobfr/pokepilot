#!/usr/bin/env python3
"""A travessia gravada de uma quest, sem laços, conferida contra o cartucho.

Uma trilha densa é o registro de uma travessia que **aconteceu**: cada tile
pisado, na ordem. Ela não serve para dirigir — trilha não sabe o que é porta nem
parede, e trail no volante causou quatro travamentos em 2026-08-17 — mas serve
para **derivar waypoints**, que é o que o executor consome.

O que este script faz, e por que cada passo existe:

1. **apaga laços**: ir até uma parede e voltar não é caminho, e um seguidor que
   herdasse o laço o andaria de propósito;
2. **guarda só as viradas**: o meio de uma reta é redundante para quem anda com
   busca em largura entre waypoints;
3. **confere contra o cartucho**: todo waypoint tem de ser pisável no estático,
   todo par consecutivo tem de ter caminho, e **porta só pode ser o primeiro ou
   o último** — o primeiro porque é onde se chega vindo de outro mapa, o último
   porque é o passo que atravessa. Porta no meio é o defeito que produziu 78
   transições de mapa no ginásio de Pewter e 10 idas e voltas na boca de Mt.
   Moon, no mesmo dia.

O que sobra depois disso é uma lista pronta para o executor, com procedência:
quem gravou, quando, e em que ciclo de morte.

    cd blue-agents && ../.venv/bin/python tools/mine_quest_route.py mt_moon_nav
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.kanto_graph import KantoGraph
from src.map_memory import MapMemory

ROUTES = ROOT / "blue-agents" / "knowledge" / "routes"


def erase_loops(points):
    """Corta tudo o que está entre duas passagens pelo mesmo tile."""
    walked, seen = [], {}
    for point in points:
        point = tuple(point)
        if point in seen:
            walked = walked[: seen[point] + 1]
            seen = {tile: index for index, tile in enumerate(walked)}
            continue
        seen[point] = len(walked)
        walked.append(point)
    return walked


def turning_points(points):
    """Só onde a direção muda — o resto é reta."""
    if len(points) < 3:
        return list(points)
    turns = [points[0]]
    for before, here, after in zip(points, points[1:], points[2:]):
        if (here[0] - before[0], here[1] - before[1]) != (
            after[0] - here[0], after[1] - here[1]
        ):
            turns.append(here)
    turns.append(points[-1])
    return turns


def audit(map_id, waypoints, maps, graph):
    """Os problemas que impedem esta perna de virar rota, ou lista vazia."""
    doors = {(w["x"], w["y"]) for w in graph.warps.get(map_id, [])}
    cells = maps.static.get(map_id, set())
    problems = []
    for waypoint in waypoints[1:-1]:
        if waypoint in doors:
            problems.append(f"porta no meio: {waypoint}")
    for waypoint in waypoints:
        if waypoint not in cells and waypoint not in doors:
            problems.append(f"fora do estático: {waypoint}")
    for here, following in zip(waypoints, waypoints[1:]):
        if maps.find_path(map_id, here, following) is None:
            # Pode ser penhasco: o estático trata o tile do meio como parede.
            jump = graph.path(
                (map_id,) + here, (map_id,) + following, allow_jumps=True
            )
            problems.append(
                f"{'só com pulo' if jump else 'sem caminho'}: {here} -> {following}"
            )
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("quest")
    parser.add_argument("--from-tile", nargs=2, type=int, default=None,
                        help="Tile de chegada, para conferir o encaixe da perna")
    args = parser.parse_args()

    path = ROUTES / f"{args.quest}.json"
    if not path.exists():
        print(f"sem trilha publicada para {args.quest} em {path}")
        return 1
    trail = json.loads(path.read_text(encoding="utf-8"))
    maps, graph = MapMemory(), None
    graph = KantoGraph(map_memory=maps)

    print(f"{args.quest}: gravada por {trail.get('recorded_by')} "
          f"em {trail.get('steps')} passos, ciclo de morte "
          f"{trail.get('death_cycle')}, {len(trail.get('legs') or [])} pernas")
    for leg in trail.get("legs") or []:
        map_id = int(leg["map"])
        raw = [tuple(p) for p in leg["points"]]
        waypoints = turning_points(erase_loops(raw))
        problems = audit(map_id, waypoints, maps, graph)
        print(f"\nmapa {map_id}: {len(raw)} gravados -> {len(waypoints)} viradas")
        print(f"  {waypoints}")
        print(f"  {'OK' if not problems else 'PROBLEMAS: ' + '; '.join(problems[:4])}")
        if args.from_tile:
            start = (int(args.from_tile[0]), int(args.from_tile[1]))
            alcance = all(
                maps.find_path(map_id, start, waypoint) is not None
                for waypoint in waypoints
            )
            print(f"  encaixe a partir de {start}: "
                  f"{'todos alcançáveis' if alcance else 'algum inalcançável'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
