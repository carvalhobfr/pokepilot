"""Executor sem nada a dizer numa tela de menu fecha com B.

`None` numa tela de menu é como um travamento nasce: o hybrid passa a vez ao
PPO, que aperta botão aleatório, e num menu isso dura horas — foi assim que
AARON..DARON "passavam" pela lista da equipe, por acidente.

Medido em 2026-08-17, na corrida do LARON em Vermilion: o Cut já estava
aprendido (golpe 15 na equipe), o controlador do Cut devolvia `None` com razão,
e a tela `esquecer_golpe` ficou aberta em (18,29) por **194 relatórios de
congelamento** — com a tela decodificada no relatório dizendo
`VENUSAUR learned CUT`.
"""

import sys
import unittest
from pathlib import Path

from pyboy.utils import WindowEvent

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src import screen
from src.scripted_agent import ESCAPABLE_SCREENS, ScriptedAgent


class FakeScreen:
    """Só os bytes que o classificador de tela lê."""

    def __init__(self, corner=(0, 0), text_box=0, in_battle=0, lcd=144,
                 party_count=0, last_row=0, cc50=0):
        self.corner = corner
        self.text_box = text_box
        self.in_battle = in_battle
        self.lcd = lcd
        self.party_count = party_count
        self.last_row = last_row
        self.cc50 = cc50

    def read_byte(self, address):
        return {
            screen.MENU_TOP_Y_ADDRESS: self.corner[0],
            screen.MENU_TOP_X_ADDRESS: self.corner[1],
            screen.MENU_LAST_ROW_ADDRESS: self.last_row,
            screen.BATTLE_MENU_STATE_ADDRESS: self.cc50,
            screen.TEXT_BOX_ADDRESS: self.text_box,
            screen.IN_BATTLE_ADDRESS: self.in_battle,
            screen.PARTY_COUNT_ADDRESS: self.party_count,
            screen.LCD_WINDOW_ADDRESS: self.lcd,
        }.get(address, 0)


class EscapeMenuTests(unittest.TestCase):
    def agent(self, memory, action=None):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.emulator = type("FakeEmulator", (), {"memory": memory})()
        agent._manual_mode_active = lambda: False
        agent._naming_screen_open = lambda: False
        agent.current_task_name = "vermilion_gym_quest"
        agent.get_action = lambda state: action
        return agent

    def test_na_tela_de_esquecer_golpe_o_passo_e_b(self):
        # O caso do LARON: Cut aprendido, controlador em silêncio, menu aberto.
        memory = FakeScreen(corner=screen.MENU_FORGET_MOVE, text_box=1)
        self.assertEqual(
            screen.ESQUECER_GOLPE, screen.classify(memory.read_byte)
        )
        agent = self.agent(memory)
        self.assertEqual(WindowEvent.PRESS_BUTTON_B, agent.step())

    def test_no_overworld_o_silencio_continua_silencio(self):
        # Sem menu aberto não há o que fechar, e um B ali é passo perdido.
        agent = self.agent(FakeScreen())
        self.assertIsNone(agent.step())

    def test_em_batalha_o_b_nao_entra(self):
        # Em batalha quem manda é o controlador de batalha: um B no lugar
        # errado é turno perdido.
        memory = FakeScreen(in_battle=1, cc50=106, lcd=0)
        self.assertEqual(screen.LISTA_GOLPES, screen.classify(memory.read_byte))
        agent = self.agent(memory)
        self.assertIsNone(agent.step())

    def test_o_executor_que_decide_nao_e_atropelado(self):
        memory = FakeScreen(corner=screen.MENU_FORGET_MOVE, text_box=1)
        agent = self.agent(memory, action=WindowEvent.PRESS_ARROW_DOWN)
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent.step())

    def test_a_lista_de_telas_cobre_os_menus_de_fora_de_batalha(self):
        self.assertIn(screen.MOCHILA, ESCAPABLE_SCREENS)
        self.assertIn(screen.DESCONHECIDA, ESCAPABLE_SCREENS)
        self.assertNotIn(screen.OVERWORLD, ESCAPABLE_SCREENS)
        self.assertNotIn(screen.MENU_BATALHA, ESCAPABLE_SCREENS)
        self.assertNotIn(screen.TECLADO_NOME, ESCAPABLE_SCREENS)


if __name__ == "__main__":
    unittest.main()
