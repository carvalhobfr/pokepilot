#!/usr/bin/env python3
"""Cronômetro de parede até Cerulean, escrito onde o operador enxerga.

Não interfere na corrida: só lê `tasks/agent_states.json` e anota a que horas
cada mapa novo apareceu. A saída vai para `runtime/marcos.log`, ao lado do log
da jornada.

Uso:

    ../.venv/bin/python tools/watch_milestones.py AARON --until 3
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE = PROJECT_ROOT / "blue-agents" / "tasks" / "agent_states.json"
OUTPUT = PROJECT_ROOT / "runtime" / "marcos.log"

NOMES = {
    0: "Pallet Town", 1: "Viridian City", 2: "Pewter City", 3: "CERULEAN CITY",
    12: "Rota 1", 13: "Rota 2", 14: "Rota 3", 15: "Rota 4",
    37: "casa do rival", 38: "quarto", 40: "lab do Oak", 41: "Centro Viridian",
    42: "Mart Viridian", 47: "Portão Rota 2", 50: "Portão Floresta",
    51: "Floresta de Viridian", 54: "Ginásio Pewter", 58: "Centro Pewter",
    59: "Mt. Moon 1F", 60: "Mt. Moon B1F", 61: "Mt. Moon B2F",
    64: "Centro Cerulean", 65: "Ginásio Misty", 68: "Centro Rota 4",
}


def snapshot(agent):
    try:
        with open(STATE, "r", encoding="utf-8") as handle:
            return json.load(handle).get(agent) or {}
    except (OSError, ValueError):
        return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", nargs="?", default="AARON")
    parser.add_argument("--until", type=int, default=3, help="map id que encerra")
    parser.add_argument("--poll", type=float, default=2.0)
    args = parser.parse_args()

    inicio = time.time()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    visto = set()
    anterior = None

    def anotar(linha):
        print(linha, flush=True)
        with open(OUTPUT, "a", encoding="utf-8") as handle:
            handle.write(linha + "\n")

    anotar(f"=== {args.agent}: cronômetro iniciado {time.strftime('%H:%M:%S')} ===")
    while True:
        estado = snapshot(args.agent)
        mapa = estado.get("map_id")
        if mapa is not None and mapa != anterior:
            anterior = mapa
            decorrido = time.time() - inicio
            marca = "" if mapa in visto else "  <-- primeira vez"
            visto.add(mapa)
            party = estado.get("party") or []
            anotar(
                f"{decorrido/60:6.1f} min  mapa {mapa:3d} {NOMES.get(mapa,'?'):22s}"
                f" passo {estado.get('step_count')}"
                f" ins {estado.get('badges')}"
                f" time {[m.get('level') for m in party]}{marca}"
            )
            if mapa == args.until:
                anotar(f"=== CHEGOU em {decorrido/60:.1f} min de relógio ===")
                return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
