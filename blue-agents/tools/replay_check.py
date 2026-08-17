#!/usr/bin/env python3
"""Roda os trechos já vencidos e confere que continuam vencidos.

O problema que isto resolve foi medido em 2026-08-16: o AARON passou dias
sendo **retomado no meio da jornada**, então o começo do jogo ficou sem ser
exercitado desde 12/08. Quando três bots novos largaram do zero, a trilha
inteira quebrou em quatro pontos seguidos — casa inicial, laboratório, lista
do balcão, prancha do navio —, e nenhum deles tinha teste, porque teste de
unidade não pisa no cartucho.

Cada trecho vencido vira um save em `states/replay/` mais uma expectativa que
o **cartucho** tem de satisfazer depois de N passos roteirizados. Sem PPO e
sem hybrid: só o executor, que é quem leva a história para frente.

    ../.venv/bin/python tools/replay_check.py            # tudo
    ../.venv/bin/python tools/replay_check.py mart       # só o que casa

Sai com código 1 se qualquer trecho regredir, para servir de portão antes de
um commit.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "blue-agents"))

from pyboy import PyBoy
from pyboy.utils import WindowEvent

from src import screen
from src.memory import Memory
from src.scripted_agent import ScriptedAgent
from src.simple_battle import SimpleBattleAgent

# Em batalha quem manda é o controlador de batalha, não o executor — é assim
# no hybrid e tem de ser assim aqui, senão o replay não cobre o que acontece
# dentro de uma luta (e foi lá que os três bots novos ficaram presos).
IN_BATTLE_ADDRESS = 0xD057

NAME_TO_EVENT = {
    "A": WindowEvent.PRESS_BUTTON_A,
    "B": WindowEvent.PRESS_BUTTON_B,
    "START": WindowEvent.PRESS_BUTTON_START,
    "UP": WindowEvent.PRESS_ARROW_UP,
    "DOWN": WindowEvent.PRESS_ARROW_DOWN,
    "LEFT": WindowEvent.PRESS_ARROW_LEFT,
    "RIGHT": WindowEvent.PRESS_ARROW_RIGHT,
}

RELEASE = {
    WindowEvent.PRESS_ARROW_LEFT: WindowEvent.RELEASE_ARROW_LEFT,
    WindowEvent.PRESS_ARROW_RIGHT: WindowEvent.RELEASE_ARROW_RIGHT,
    WindowEvent.PRESS_ARROW_UP: WindowEvent.RELEASE_ARROW_UP,
    WindowEvent.PRESS_ARROW_DOWN: WindowEvent.RELEASE_ARROW_DOWN,
    WindowEvent.PRESS_BUTTON_A: WindowEvent.RELEASE_BUTTON_A,
    WindowEvent.PRESS_BUTTON_B: WindowEvent.RELEASE_BUTTON_B,
    WindowEvent.PRESS_BUTTON_START: WindowEvent.RELEASE_BUTTON_START,
}

# O mesmo tempo de aperto do `probe_route.py`, que é o que move o personagem
# de verdade: segurar demais come o passo seguinte, de menos não registra.
PRESS_FRAMES, RELEASE_FRAMES = 8, 16


class Adapter:
    """O mínimo que o ScriptedAgent lê de um emulador."""

    def __init__(self, pyboy):
        self.pyboy = pyboy
        self.memory = Memory(pyboy)


def battle_switcher(pyboy):
    """O controlador de troca do hybrid, sem subir o ambiente inteiro.

    A troca mora no `HybridGymEnv` e o golpe no `SimpleBattleAgent`: cobrir só
    um dos dois deixa de fora metade do que acontece numa luta — e foi na
    troca que três bots ficaram presos.
    """
    from hybrid_agent import HybridGymEnv

    env = HybridGymEnv.__new__(HybridGymEnv)
    env.read_m = lambda address: pyboy.memory[address]
    env.read_rom = lambda bank, address: pyboy.memory[bank, address]
    env.capture_in_flight = False
    env.capture_plan = []
    env.capture_bag_open = False
    env.switch_plan = []
    env.switch_menu_open = False
    env.switch_steps = 0
    env._log_event = lambda *args, **kwargs: None
    return env


def party_moves(pyboy):
    count = min(int(pyboy.memory[0xD163]), 6)
    return [
        int(pyboy.memory[0xD16B + slot * 44 + 8 + index])
        for slot in range(count)
        for index in range(4)
    ]


def party_nickname(pyboy, slot=0):
    """O apelido de um membro da equipe, decodificado de `wPartyMonNicknames`.

    É o que separa "a tela foi respondida" de "o A foi martelado": o cartucho
    auto-confirma o teclado quando o nome enche, então mashing A não trava —
    só devolve um inicial chamado `AAAAAAAAAA`.
    """
    letters = []
    for index in range(11):
        tile = int(pyboy.memory[0xD2B5 + slot * 11 + index])
        if tile == 0x50:  # fim de string
            break
        letters.append(screen._character(tile))
    return "".join(letters)


def bag_items(pyboy):
    count = min(int(pyboy.memory[0xD31D]), 20)
    return {int(pyboy.memory[0xD31E + i * 2]): int(pyboy.memory[0xD31F + i * 2])
            for i in range(count)}


def run_check(check, rom, quiet=True):
    state_path = ROOT / check["state"]
    pyboy = PyBoy(str(rom), window="null", sound_emulated=False)
    with state_path.open("rb") as handle:
        pyboy.load_state(handle)
    pyboy.tick(60, False, False)

    emulator = Adapter(pyboy)
    agent = ScriptedAgent(
        str(ROOT / "walkthrough.json"),
        emulator=emulator,
        player_name="REPLAY",
        save_dir=str(ROOT / "trainers" / "REPLAY"),
        route_role="guide",
    )
    quest = check["quest"]
    agent.current_task_name = quest

    battler = SimpleBattleAgent()
    switcher = battle_switcher(pyboy)
    seen_maps, seen_tiles = set(), set()
    for _ in range(int(check["steps"])):
        if int(pyboy.memory[IN_BATTLE_ADDRESS]) != 0:
            # A ordem do hybrid: a troca decide primeiro (é ela que atende a
            # lista da equipe aberta), e o golpe assume quando não há troca.
            choice = switcher._next_switch_action()
            if choice is None:
                choice = battler.get_action(emulator.memory)
            action = NAME_TO_EVENT.get(
                str(choice).upper(), WindowEvent.PRESS_BUTTON_A
            )
        else:
            action = agent.step(quest)
        if action in RELEASE:
            pyboy.send_input(action)
            pyboy.tick(PRESS_FRAMES, False, False)
            pyboy.send_input(RELEASE[action])
            pyboy.tick(RELEASE_FRAMES, False, False)
        else:
            pyboy.tick(PRESS_FRAMES + RELEASE_FRAMES, False, False)
        map_id = int(pyboy.memory[0xD35E])
        position = (int(pyboy.memory[0xD362]), int(pyboy.memory[0xD361]))
        seen_maps.add(map_id)
        seen_tiles.add((map_id, position))

    expect = check.get("expect", {})
    failures = []
    if "map_in" in expect and not seen_maps & set(expect["map_in"]):
        failures.append(
            f"não chegou em nenhum de {expect['map_in']}; visitou {sorted(seen_maps)}"
        )
    if "tiles_min" in expect and len(seen_tiles) < int(expect["tiles_min"]):
        failures.append(
            f"andou {len(seen_tiles)} tiles, esperado ao menos {expect['tiles_min']}"
        )
    if "bag_has" in expect and int(expect["bag_has"]) not in bag_items(pyboy):
        failures.append(
            f"item {hex(int(expect['bag_has']))} não entrou na mochila "
            f"({[hex(i) for i in bag_items(pyboy)]})"
        )
    if "party_move" in expect and int(expect["party_move"]) not in party_moves(pyboy):
        failures.append(
            f"golpe {expect['party_move']} não está na equipe ({party_moves(pyboy)})"
        )
    if "party_nickname" in expect:
        found = party_nickname(pyboy)
        if found != expect["party_nickname"]:
            failures.append(
                f"apelido do slot 0 é {found!r}, esperado "
                f"{expect['party_nickname']!r}"
            )
    if expect.get("not_in_battle") and int(pyboy.memory[0xD057]) != 0:
        failures.append("continua preso em batalha depois do orçamento de passos")
    pyboy.stop(False)
    return failures, sorted(seen_maps), len(seen_tiles)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filtro", nargs="?", default="")
    parser.add_argument("--rom", default=str(ROOT / "roms" / "PokemonBlue.gb"))
    parser.add_argument(
        "--manifest", default=str(ROOT / "states" / "replay" / "manifest.json")
    )
    args = parser.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    checks = [
        check for check in manifest["checks"]
        if not args.filtro or args.filtro.lower() in check["name"].lower()
    ]
    if not checks:
        print(f"nenhum trecho casa com {args.filtro!r}")
        return 1

    broken = 0
    for check in checks:
        failures, maps, tiles = run_check(check, args.rom)
        if failures:
            broken += 1
            print(f"✗ {check['name']}: " + "; ".join(failures))
            print(f"   regressão conhecida: {check['regressao']}")
        else:
            print(f"✓ {check['name']}: mapas {maps}, {tiles} tiles")
    print(f"\n{len(checks) - broken}/{len(checks)} trechos de pé")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
