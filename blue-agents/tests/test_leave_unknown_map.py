"""Sair de um mapa sem rota: em cima da porta, atravessar; longe dela, andar.

Três versões desta função erraram de jeitos diferentes. A primeira descartava a
porta quando o bot já estava em cima dela e caía num passeio cego de dez tiles
ao sul — BARON foi retomado exatamente sobre a porta do Centro da Rota 4 e ficou
indo e voltando. A segunda escolhia "a porta mais próxima que não seja esta", o
que parece óbvio e quebra no lab do Oak: a porta é dupla, (4,11) e (5,11), então
o bot trocava de metade e a outra virava a mais próxima, para sempre.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from pyboy.utils import WindowEvent

from src.scripted_agent import ScriptedAgent


class MemoriaFalsa:
    def __init__(self, map_id, pos):
        self.map_id = map_id
        self.pos = pos

    def get_map_id(self):
        return self.map_id

    def get_player_pos(self):
        return self.pos

    def read_byte(self, address):
        return 0


class SairDeMapaDesconhecidoTests(unittest.TestCase):
    LAB_DO_OAK = {(4, 11): 0, (5, 11): 0}      # porta dupla
    ROTA_4 = {(11, 6): 68, (18, 5): 59}

    def agente(self, map_id, pos, portas):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.emulator = type("FakeEmulator", (), {"memory": MemoriaFalsa(map_id, pos)})()
        agent.map_entry_tiles = {}
        agent.andou = []
        agent.last_action_was_move = False
        agent._warp_memory = lambda: type("FakeWarps", (), {
            "doors_from": staticmethod(lambda _m: dict(portas)),
        })()
        agent._follow_route = lambda route_id, waypoints: agent.andou.append(
            (route_id, waypoints)
        ) or "ANDANDO"
        return agent

    def test_em_cima_da_porta_atravessa(self):
        agent = self.agente(40, (5, 11), self.LAB_DO_OAK)
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent._leave_unknown_map())
        self.assertEqual([], agent.andou, "não anda para lugar nenhum")
        self.assertTrue(agent.last_action_was_move)

    def test_a_outra_metade_da_porta_dupla_tambem_atravessa(self):
        # Era aqui que nascia o pinguepongue entre (4,11) e (5,11).
        agent = self.agente(40, (4, 11), self.LAB_DO_OAK)
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent._leave_unknown_map())
        self.assertEqual([], agent.andou)

    def test_longe_da_porta_anda_ate_a_mais_proxima(self):
        agent = self.agente(15, (16, 6), self.ROTA_4)
        self.assertEqual("ANDANDO", agent._leave_unknown_map())
        self.assertEqual([(18, 5)], agent.andou[0][1])

    def test_em_cima_de_uma_porta_de_rota_tambem_atravessa(self):
        # O caso do BARON retomado sobre a porta do Centro da Rota 4.
        agent = self.agente(15, (11, 6), self.ROTA_4)
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent._leave_unknown_map())

    def test_mapa_sem_porta_conhecida_cai_no_passeio_cego(self):
        agent = self.agente(99, (7, 7), {})
        self.assertEqual("ANDANDO", agent._leave_unknown_map())
        self.assertTrue(agent.andou[0][0].startswith("exit-99"))


if __name__ == "__main__":
    unittest.main()
