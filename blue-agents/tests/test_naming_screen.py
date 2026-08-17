"""O teclado de apelido responde a START, em qualquer quest.

O controlador de batalha já sabia disto, e era o único: a tela também aparece
**ao receber o inicial**, com `0xD057` em zero. Ali o executor via menu aberto
e respondia A — que nesta tela digita letra.

Medido em 2026-08-17 do save `states/replay/casa-inicial.state`, sem PPO: não
travava, porque o cartucho auto-confirma quando o nome enche; custava 11 passos
e o inicial saía chamado `AAAAAAAAAA` em vez de `BULBASAUR`. O trecho
`apelido-do-inicial` do `replay_check.py` cobre isso no cartucho; aqui fica a
regra, que vale para toda quest e não só para a `start`.
"""

import sys
import unittest
from pathlib import Path

from pyboy.utils import WindowEvent

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src import screen
from src.scripted_agent import ScriptedAgent


class DrawnScreen:
    """O `wTileMap` com uma linha escrita, e o resto do cenário."""

    def __init__(self, header=""):
        self.tiles = [0x00] * screen.SCREEN_TILES
        for column, character in enumerate(header[:screen.SCREEN_WIDTH]):
            tile = 0x7F
            if "A" <= character <= "Z":
                tile = 0x80 + ord(character) - ord("A")
            self.tiles[3 * screen.SCREEN_WIDTH + column] = tile

    def read_byte(self, address):
        if screen.SCREEN_TILEMAP_ADDRESS <= address < (
            screen.SCREEN_TILEMAP_ADDRESS + screen.SCREEN_TILES
        ):
            return self.tiles[address - screen.SCREEN_TILEMAP_ADDRESS]
        return 0


class NamingScreenTests(unittest.TestCase):
    def agent(self, header):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        memory = DrawnScreen(header)
        agent.emulator = type("FakeEmulator", (), {"memory": memory})()
        agent._manual_mode_active = lambda: False
        agent.current_task_name = "start"
        return agent

    def test_com_o_teclado_na_tela_a_resposta_e_start(self):
        agent = self.agent("NICKNAME")
        self.assertEqual(WindowEvent.PRESS_BUTTON_START, agent.step("start"))

    def test_a_regra_nao_depende_da_quest(self):
        agent = self.agent("NICKNAME")
        agent.current_task_name = "viridian_forest_nav"
        self.assertEqual(
            WindowEvent.PRESS_BUTTON_START, agent.step("viridian_forest_nav")
        )

    def test_sem_o_teclado_o_executor_continua_mandando(self):
        # Sem a tela, o gate não pode responder nada — quem decide é a quest.
        agent = self.agent("BULBASAUR")
        self.assertFalse(agent._naming_screen_open())

    def test_emulador_que_recusa_a_leitura_nao_derruba_o_passo(self):
        agent = self.agent("NICKNAME")

        class Broken:
            def read_byte(self, address):
                raise RuntimeError("sem emulador")

        agent.emulator = type("FakeEmulator", (), {"memory": Broken()})()
        self.assertFalse(agent._naming_screen_open())


if __name__ == "__main__":
    unittest.main()
