"""Waypoint já passado é waypoint gasto.

O índice da rota era recalculado para o waypoint **mais próximo** a cada troca
de `route_id`. Sair de um mapa e voltar zerava o avanço: BARON e CARON entravam
em Mt. Moon, andavam até o meio, saíam para a Rota 4 e ao reentrar o índice
voltava para perto da boca da caverna. Dezoito travessias, nenhum progresso.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.scripted_agent import ScriptedAgent


class IndiceDeRotaTests(unittest.TestCase):
    # O trecho de verdade do mapa 59, do começo.
    ROTA = [(14, 35), (14, 22), (21, 22), (21, 15), (24, 15), (24, 27)]

    def agente(self):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.route_progress = {}
        return agent

    def mirar(self, agent, route_id, posicao, waypoints=None):
        return agent._select_route_index(route_id, waypoints or self.ROTA, posicao)

    def test_rota_nova_pega_o_mais_proximo(self):
        agent = self.agente()
        self.assertEqual(2, self.mirar(agent, "mt-moon-59", (21, 21)))

    def test_pisar_no_waypoint_avanca(self):
        agent = self.agente()
        self.assertEqual(1, self.mirar(agent, "mt-moon-59", (14, 35)))

    def test_sair_e_voltar_nao_zera_o_avanco(self):
        # O caso medido: meio da caverna, saída para a Rota 4, reentrada.
        agent = self.agente()
        # Parado em cima do waypoint 4, o laço já mira o 5 — pisar num ponto
        # gasta o ponto.
        alcancado = self.mirar(agent, "mt-moon-59", (24, 15))
        self.assertEqual(5, alcancado)
        self.mirar(agent, "mt-moon-enter-cave", (18, 6), [(18, 6), (18, 5)])
        indice = self.mirar(agent, "mt-moon-59", (14, 35))   # reentrou na boca
        self.assertEqual(5, indice, "não pode voltar ao waypoint da entrada")

    def test_o_avanco_e_por_rota_e_nao_global(self):
        agent = self.agente()
        self.mirar(agent, "mt-moon-59", (24, 15))
        self.assertEqual(0, self.mirar(agent, "outra-rota", (14, 34)))

    def test_estar_a_frente_do_lembrado_ainda_vale(self):
        agent = self.agente()
        self.mirar(agent, "mt-moon-59", (14, 22))            # índice 2
        self.mirar(agent, "outra", (0, 0), [(0, 0), (1, 1)])
        self.assertEqual(4, self.mirar(agent, "mt-moon-59", (24, 14)))

    def test_lista_mais_curta_nao_estoura(self):
        # O executor da Rota 2 troca a lista depois que o Centro é registrado.
        agent = self.agente()
        agent.route_progress["curta"] = 9
        self.assertEqual(1, self.mirar(agent, "curta", (9, 9), [(1, 1), (5, 5)]))

    def test_o_apagao_apaga_o_avanco(self):
        # O cartucho devolveu o treinador a um Centro: a travessia recomeça, e
        # mirar o meio da caverna a partir da porta seria planejar por cima de
        # terreno que esta tentativa não andou.
        agent = self.agente()
        self.mirar(agent, "mt-moon-59", (24, 15))
        agent.trail_recorder = None
        agent.begin_death_cycle(2)
        self.assertEqual({}, agent.route_progress)
        agent.route_id = None
        self.assertEqual(1, self.mirar(agent, "mt-moon-59", (14, 35)))


if __name__ == "__main__":
    unittest.main()
