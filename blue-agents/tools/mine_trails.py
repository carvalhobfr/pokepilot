#!/usr/bin/env python3
"""Publica, para cada quest, a melhor travessia que alguém já fez.

O projeto acumula jornadas em `archives/` e `trainers/`, e cada uma registra
onde o treinador estava a cada evento. Quando o QuestGraph troca de objetivo,
a quest anterior foi confirmada na RAM — então tudo o que foi andado entre o
início dela e essa troca é um caminho que **chegou**.

Esta ferramenta lê esses trechos, apaga os laços (voltas que o bot deu e
desfez), comprime em pontos de virada e publica como trilha compartilhada. A
mais curta ganha: os dois treinadores passam a segui-la em vez de redescobrir
o mapa cada um por si.

    ./blue-agents/tools/mine_trails.py           # publica o que for melhor
    ./blue-agents/tools/mine_trails.py --dry-run # só mostra o que faria
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.route_trails import TrailStore, _corner_points  # noqa: E402


def carregar_eventos(caminho: Path) -> list[dict]:
    eventos = []
    try:
        texto = caminho.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return eventos
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            eventos.append(json.loads(linha))
        except ValueError:
            continue
    eventos.sort(key=lambda evento: evento.get("timestamp", 0))
    return eventos


def travessias(eventos: list[dict]) -> dict[str, list[list[dict]]]:
    """Trechos que terminaram com a quest confirmada, por quest."""
    encontradas: dict[str, list[list[dict]]] = {}
    inicio = {}
    for indice, evento in enumerate(eventos):
        if evento.get("type") != "quest_advanced":
            continue
        dados = evento.get("data") or {}
        anterior = dados.get("from_quest_id")
        seguinte = dados.get("to_quest_id")
        if anterior and anterior in inicio:
            bruto = eventos[inicio[anterior]:indice]
            # Morrer começa um ciclo novo. O que veio antes do whiteout inclui
            # a ida que terminou em derrota e a volta desde o Centro — publicar
            # isso ensinaria o desvio como se fosse o caminho. Só o trecho
            # depois da última morte é uma travessia limpa.
            ultima_morte = max(
                (posicao for posicao, registro in enumerate(bruto)
                 if registro.get("type") in ("death", "battle_loss")),
                default=None,
            )
            if ultima_morte is not None:
                bruto = bruto[ultima_morte + 1:]
            trecho = [
                registro for registro in bruto
                if registro.get("coords") and registro.get("map_id") is not None
            ]
            if trecho:
                encontradas.setdefault(anterior, []).append(trecho)
        if seguinte:
            inicio[seguinte] = indice
    return encontradas


def pernas(trecho: list[dict]) -> list[dict]:
    """Posições andadas viram pernas por mapa, sem laços e só com as viradas."""
    pontos = []
    for registro in trecho:
        posicao = (int(registro["map_id"]), tuple(registro["coords"]))
        if not pontos or pontos[-1] != posicao:
            pontos.append(posicao)
    limpos: list[tuple] = []
    for posicao in pontos:
        if posicao in limpos:
            limpos = limpos[: limpos.index(posicao) + 1]
        else:
            limpos.append(posicao)
    resultado: list[dict] = []
    mapa_atual = None
    corrida: list[list[int]] = []
    for mapa, (x, y) in limpos:
        if mapa != mapa_atual:
            if corrida:
                resultado.append({"map": mapa_atual, "points": _corner_points(corrida)})
            mapa_atual = mapa
            corrida = []
        corrida.append([x, y])
    if corrida:
        resultado.append({"map": mapa_atual, "points": _corner_points(corrida)})
    return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="não grava nada")
    argumentos = parser.parse_args()

    logs = sorted(ROOT.glob("archives/**/decisions.jsonl")) + sorted(
        ROOT.glob("trainers/*/logs/decisions.jsonl")
    )
    melhores: dict[str, tuple[tuple[int, int], int, list[dict], str]] = {}
    for caminho in logs:
        eventos = carregar_eventos(caminho)
        if not eventos:
            continue
        origem = caminho.relative_to(ROOT).parts[1]
        for quest, trechos in travessias(eventos).items():
            for trecho in trechos:
                legs = pernas(trecho)
                if not legs:
                    continue
                tamanho = sum(len(perna["points"]) for perna in legs)
                if tamanho < 2:
                    # Um ponto só não é caminho, é carimbo de chegada.
                    continue
                mapas = len({perna["map"] for perna in legs})
                # Cobertura primeiro, tamanho depois: uma travessia que passa
                # por quatro mapas vale mais que um toco de dois pontos que por
                # acaso é mais curto. O toco levaria o seguidor a lugar nenhum.
                nota = (mapas, -tamanho)
                atual = melhores.get(quest)
                if atual is None or nota > atual[0]:
                    melhores[quest] = (nota, tamanho, legs, origem)

    if not melhores:
        print("Nenhuma travessia confirmada encontrada nos arquivos.")
        return 0

    store = TrailStore()
    for quest in sorted(melhores):
        _, tamanho, legs, origem = melhores[quest]
        mapas = ", ".join(str(perna["map"]) for perna in legs)
        anterior = store.load(quest)
        antes = sum(len(perna["points"]) for perna in anterior) if anterior else None
        estado = "nova" if antes is None else f"tinha {antes}"
        if argumentos.dry_run:
            print(f"{quest}: {tamanho} pontos ({estado}) — mapas {mapas} — de {origem}")
            continue
        publicada = store.publish(quest, f"minerada:{origem}", legs, force=True)
        marca = "publicada" if publicada else "mantida a que já existia"
        print(f"{quest}: {tamanho} pontos, {marca} — mapas {mapas} — de {origem}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
