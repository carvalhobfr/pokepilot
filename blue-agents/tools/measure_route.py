#!/usr/bin/env python3
"""Mede a rota de um save até um alvo e imprime os waypoints prontos.

Este projeto perdeu cinco tentativas seguidas numa tarde porque alguém — eu —
olhou o mapa e decidiu por onde se anda. A rota da travessia parecia mato e era
caminho de terra; o corredor "da entrada" era terra também; o mato mais distante
ficava para o norte, onde está o apanhador de insetos. Nenhuma delas foi medida.

A rota feita à mão é o caminho principal do projeto — é ela que leva a história
adiante. Então escrevê-la não pode ser palpite. Esta ferramenta pega um save,
anda de verdade no cartucho (ramificando o estado, um passo por ramo, igual ao
`probe_route.py`) e devolve a lista de waypoints em pontos de virada, no formato
que os executores de `src/scripted_agent.py` já usam.

    # até uma coordenada do mesmo mapa
    ./blue-agents/tools/measure_route.py SAVE --to 17 43

    # até a porta que leva a outro mapa (o cartucho diz onde ela fica)
    ./blue-agents/tools/measure_route.py SAVE --to-map 47

    # o que é alcançável a partir daqui, quando nem o alvo se sabe
    ./blue-agents/tools/measure_route.py SAVE --reach
"""

from __future__ import annotations

import argparse
from collections import deque
from io import BytesIO
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pyboy import PyBoy  # noqa: E402
from pyboy.utils import WindowEvent  # noqa: E402

from src.route_trails import _corner_points  # noqa: E402
from src.tile_collision import TileCollision  # noqa: E402

PASSOS = (
    ("L", WindowEvent.PRESS_ARROW_LEFT, WindowEvent.RELEASE_ARROW_LEFT, (-1, 0)),
    ("R", WindowEvent.PRESS_ARROW_RIGHT, WindowEvent.RELEASE_ARROW_RIGHT, (1, 0)),
    ("U", WindowEvent.PRESS_ARROW_UP, WindowEvent.RELEASE_ARROW_UP, (0, -1)),
    ("D", WindowEvent.PRESS_ARROW_DOWN, WindowEvent.RELEASE_ARROW_DOWN, (0, 1)),
)


def onde(pyboy):
    return (
        int(pyboy.memory[0xD35E]),
        int(pyboy.memory[0xD362]),
        int(pyboy.memory[0xD361]),
    )


def estado(pyboy):
    saida = BytesIO()
    pyboy.save_state(saida)
    return saida.getvalue()


def assentar(pyboy):
    """Deixa a entrada em curso terminar antes de ramificar."""
    pyboy.tick(60, False, False)
    for _ in range(4):
        if int(pyboy.memory[0xCFC4]) != 1:
            break
        pyboy.send_input(WindowEvent.PRESS_BUTTON_A)
        pyboy.tick(8, False, False)
        pyboy.send_input(WindowEvent.RELEASE_BUTTON_A)
        pyboy.tick(16, False, False)


def buscar(pyboy, alvo, limite):
    """Anda de verdade, um passo por ramo, até o alvo ou até esgotar o limite."""
    inicio = onde(pyboy)
    raiz = estado(pyboy)
    fila = deque([(inicio, raiz, [(inicio[1], inicio[2])])])
    vistos = {inicio}
    alcance = {inicio}
    while fila and len(vistos) < limite:
        atual, bytes_estado, caminho = fila.popleft()
        if alvo is not None and (atual[1], atual[2]) == alvo:
            return caminho, alcance
        for _rotulo, aperta, solta, (dx, dy) in PASSOS:
            pyboy.load_state(BytesIO(bytes_estado))
            pyboy.send_input(aperta)
            pyboy.tick(8, False, False)
            pyboy.send_input(solta)
            pyboy.tick(16, False, False)
            candidato = onde(pyboy)
            if candidato[0] != inicio[0]:
                # Trocou de mapa: o tile que a gente tentou pisar era a porta.
                # Ela é o destino, e nunca aparece como posição alcançada —
                # pisar nela já leva embora. Sem isto, um alvo que é porta
                # jamais é encontrado, e foi o que aconteceu na primeira
                # medição desta ferramenta.
                porta = (atual[1] + dx, atual[2] + dy)
                if alvo is not None and porta == alvo:
                    return caminho + [list(porta)], alcance
                continue
            if candidato in vistos:
                continue
            vistos.add(candidato)
            alcance.add(candidato)
            fila.append((
                candidato, estado(pyboy),
                caminho + [(candidato[1], candidato[2])],
            ))
    return None, alcance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("--rom", type=Path, default=ROOT / "roms/PokemonBlue.gb")
    parser.add_argument(
        "--to", nargs=2, type=int, metavar=("X", "Y"),
        help="alvo em coordenadas do mapa atual",
    )
    parser.add_argument(
        "--to-map", type=int,
        help="alvo é a porta que leva a este mapa, lida da tabela de warps",
    )
    parser.add_argument(
        "--reach", action="store_true",
        help="só relatar o que é alcançável a partir daqui",
    )
    parser.add_argument("--limit", type=int, default=600)
    parser.add_argument(
        "--name", default="rota",
        help="nome do route_id na linha pronta para colar",
    )
    argumentos = parser.parse_args()

    pyboy = PyBoy(str(argumentos.rom), window="null", sound_emulated=False)
    with argumentos.state.open("rb") as arquivo:
        pyboy.load_state(arquivo)
    assentar(pyboy)

    mapa, x, y = onde(pyboy)
    leitor = TileCollision(pyboy)
    portas = leitor.warp_destinations()
    print(f"save: mapa {mapa} em ({x}, {y})")
    print(f"portas deste mapa: {portas or 'nenhuma'}")

    alvo = None
    if argumentos.to_map is not None:
        candidatas = [
            tile for tile, destino in portas.items()
            if destino == argumentos.to_map
        ]
        if not candidatas:
            print(f"nenhuma porta deste mapa leva ao mapa {argumentos.to_map}")
            return 1
        alvo = min(candidatas, key=lambda t: abs(t[0] - x) + abs(t[1] - y))
        print(f"alvo: porta para o mapa {argumentos.to_map} em {alvo}")
    elif argumentos.to:
        alvo = tuple(argumentos.to)
        print(f"alvo: {alvo}")
    elif not argumentos.reach:
        print("informe --to, --to-map ou --reach")
        return 1

    caminho, alcance = buscar(pyboy, alvo, max(argumentos.limit, 1))

    xs = [p[1] for p in alcance]
    ys = [p[2] for p in alcance]
    print(f"alcançável: {len(alcance)} tiles | x {min(xs)}..{max(xs)} y {min(ys)}..{max(ys)}")

    if alvo is None:
        return 0
    if caminho is None:
        print("sem caminho até o alvo dentro do limite — aumente --limit ou "
              "confira se o alvo é alcançável deste mapa")
        return 1

    waypoints = _corner_points([list(p) for p in caminho])
    print(f"caminho: {len(caminho)} passos, {len(waypoints)} pontos de virada")
    pontos = ", ".join(f"({p[0]}, {p[1]})" for p in waypoints)
    print("\npronto para colar num executor:\n")
    print(f'        return self._follow_route(\n'
          f'            "{argumentos.name}",\n'
          f'            [{pontos}],\n'
          f'        )')
    pyboy.stop(save=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
