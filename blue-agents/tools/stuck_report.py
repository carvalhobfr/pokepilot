#!/usr/bin/env python3
"""Onde cada treinador travou, e por quê — lido dos relatórios gravados.

Cada travamento escreve uma linha em `trainers/<AGENTE>/logs/stuck.jsonl` com o
que foi decidido naquele instante: posição, alvo da rota, direções que o
cartucho recusa e por qual motivo, o que o mapa acumulado sabe, e há quanto
tempo a distância até o alvo parou de cair.

    ./blue-agents/tools/stuck_report.py            # último de cada treinador
    ./blue-agents/tools/stuck_report.py --all      # todos, em ordem
    ./blue-agents/tools/stuck_report.py --agent AARON --limit 5
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAINERS = ROOT / "trainers"

MOTIVOS = {
    "terrain": "parede (leitura do tileset)",
    "sprite": "gente na frente",
    "warp": "porta que não é o destino",
    "map_edge": "volta pela fronteira recém-atravessada",
    "bumped": "parede descoberta na marra: o passo não moveu",
}


def carregar(agent: str) -> list[dict]:
    caminho = TRAINERS / agent / "logs" / "stuck.jsonl"
    if not caminho.exists():
        return []
    relatorios = []
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            relatorios.append(json.loads(linha))
        except ValueError:
            continue
    return relatorios


def explicar(relatorio: dict) -> str:
    """A leitura mais provável do travamento, dita em uma linha."""
    if relatorio.get("in_battle"):
        return "estava em batalha: navegação parada é o certo aqui"
    bloqueios = relatorio.get("blocked") or {}
    livres = {"U", "D", "L", "R"} - set(bloqueios)
    if not livres:
        return "as quatro direções recusadas ao mesmo tempo"
    if relatorio.get("path_to_target") is None:
        if relatorio.get("nearest_unexplored"):
            return "sem caminho conhecido até o alvo, mas ainda há o que explorar"
        return "o mapa acumulado não liga esta posição ao alvo, e não sobrou nada para explorar"
    return "existe caminho até o alvo: o passo escolhido é que não sai"


def mostrar(relatorio: dict) -> None:
    quando = time.strftime("%d/%m %H:%M:%S", time.localtime(relatorio.get("at", 0)))
    print(f"[{quando}] {relatorio.get('agent')} — {relatorio.get('quest')}")
    print(
        f"  mapa {relatorio.get('map')} em {tuple(relatorio.get('position', []))}"
        f" mirando {tuple(relatorio.get('target', []))}"
        f" (rota {relatorio.get('route_id')}, índice {relatorio.get('route_index')})"
    )
    bloqueios = relatorio.get("blocked") or {}
    if bloqueios:
        partes = [f"{lado}: {MOTIVOS.get(motivo, motivo)}" for lado, motivo in bloqueios.items()]
        print("  bloqueado — " + "; ".join(partes))
    else:
        print("  nada bloqueado pela leitura do cartucho")
    print(
        f"  {relatorio.get('steps_on_this_tile')} passos neste tile,"
        f" {relatorio.get('steps_without_progress')} sem encurtar a distância"
        f" (menor distância atingida: {relatorio.get('closest_it_got')})"
    )
    caminho = relatorio.get("path_to_target")
    conhecido = relatorio.get("terrain_known") or {}
    print(
        f"  mapa conhecido: {conhecido.get('walkable')} caminháveis,"
        f" {conhecido.get('solid')} paredes"
        f" | caminho até o alvo: {caminho or 'nenhum'}"
        f" | fronteira: {relatorio.get('nearest_unexplored') or 'nenhuma'}"
    )
    party = relatorio.get("party") or []
    if party:
        resumo = ", ".join(
            f"{mon['hp']}/{mon['max_hp']}" + ("" if any(mon["pp"]) else " sem PP")
            for mon in party
        )
        print(f"  time: {resumo}")
    print(f"  → {explicar(relatorio)}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", help="só este treinador")
    parser.add_argument("--limit", type=int, default=1, help="quantos por treinador")
    parser.add_argument("--all", action="store_true", help="todos os relatórios")
    argumentos = parser.parse_args()

    agentes = (
        [argumentos.agent]
        if argumentos.agent
        else sorted(p.name for p in TRAINERS.iterdir() if p.is_dir() and not p.name.startswith("."))
        if TRAINERS.exists()
        else []
    )
    encontrou = False
    for agente in agentes:
        relatorios = carregar(agente)
        if not relatorios:
            continue
        encontrou = True
        escolhidos = relatorios if argumentos.all else relatorios[-argumentos.limit:]
        for relatorio in escolhidos:
            mostrar(relatorio)
    if not encontrou:
        print("Nenhum travamento registrado ainda.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
