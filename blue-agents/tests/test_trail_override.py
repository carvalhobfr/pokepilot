"""Um waypoint restante é carimbo de chegada, não caminho.

`waypoints_from` devolve o que falta do trail a partir de onde o bot está.
Quando só resta um ponto, o trail não tem mais nada a dizer: o seguidor põe o
bot em cima dele e o deixa lá, porque não há próximo waypoint para querer — e
aí cai no "continua para onde veio", que é o vaivém.

Medido em 2026-08-16, com três bots novos largando do zero ao mesmo tempo: os
três oscilando entre (4,1) e (4,2) no laboratório do Oak, **4.500 passos no
mesmo tile**, com `route_id=trail-override-parcel_event-40` e
`waypoints=[[4,1]]`. O executor do `parcel_event` tem a rota inteira do
laboratório — [(4,1), (4,3), (5,3), (5,12)] — e estava sendo sobreposto por um
ponto solto.

A extensão pelo warp de saída continua valendo: um trail que termina perto de
uma porta ganha a porta como segundo ponto, e aí volta a ser caminho.

O `parcel_event` em si acabou entrando na lista de quests que o trail não
dirige — o fluxo de largada passa duas vezes pelos mesmos tiles e o trail não
sabe qual passagem é qual —, então os casos abaixo usam uma quest que ainda
aceita trail; a regra do ponto solto vale para todas.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.scripted_agent import TRAIL_BLOCKED_QUESTS, ScriptedAgent

# O trail do laboratório, como o executor o desenha.
LAB_LEG = [{"map": 40, "points": [[4, 1], [4, 3], [5, 3], [5, 12]]}]


class TrailMemory:
    def __init__(self, map_id, position):
        self.map_id = map_id
        self.position = position

    def get_map_id(self):
        return self.map_id

    def get_player_pos(self):
        return self.position

    def read_byte(self, address):
        return 0


class Store:
    def __init__(self, legs):
        self.legs = legs

    def load(self, quest_id):
        return list(self.legs)


class Reader:
    def __init__(self, warps=()):
        self.warps = set(warps)

    def warp_tiles(self):
        return set(self.warps)


class OnePointLegTests(unittest.TestCase):
    def agent(self, legs, position, map_id=40, warps=()):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.emulator = type(
            "FakeEmulator", (), {"memory": TrailMemory(map_id, position)}
        )()
        agent.current_task_name = "route_2_nav"
        agent.trail_store = Store(legs)
        agent.tile_collision = Reader(warps)
        agent._manual_mode_active = lambda: False
        agent.walked = []
        agent._follow_route = lambda route_id, waypoints: agent.walked.append(
            (route_id, list(waypoints))
        ) or "WALKING"
        return agent

    def test_no_ultimo_ponto_o_passo_volta_para_o_executor(self):
        # De (5,3) só resta (5,12); de (5,12) só resta ele mesmo.
        for position in ((5, 3), (5, 12)):
            agent = self.agent(LAB_LEG, position)
            self.assertIsNone(
                agent._trail_override_step(), f"de {position} o trail acabou"
            )
            self.assertEqual([], agent.walked)

    def test_com_caminho_pela_frente_o_trail_continua_dirigindo(self):
        agent = self.agent(LAB_LEG, (4, 2))
        self.assertEqual("WALKING", agent._trail_override_step())
        route_id, waypoints = agent.walked[-1]
        self.assertEqual("trail-override-route_2_nav-40", route_id)
        self.assertGreaterEqual(len(waypoints), 2)

    def test_o_ultimo_ponto_perto_de_uma_porta_ganha_a_porta(self):
        # Medido em 2026-08-13: o trail terminava a um passo do warp e o bot
        # parava na soleira. Com a porta como segundo ponto, ele atravessa.
        agent = self.agent(LAB_LEG, (5, 3), warps=[(5, 6)])
        self.assertEqual("WALKING", agent._trail_override_step())
        _, waypoints = agent.walked[-1]
        self.assertEqual(2, len(waypoints))
        self.assertEqual((5, 6), tuple(waypoints[-1]), "a porta é o segundo ponto")

    def test_sem_trail_nao_ha_override(self):
        agent = self.agent([], (4, 2))
        self.assertIsNone(agent._trail_override_step())

    def test_na_floresta_quem_dirige_e_o_executor(self):
        # O executor da Floresta escolhe o mato pelo `wGrassTile` lido ao vivo;
        # o trail guarda por onde alguém passou, e a travessia segue o caminho
        # de terra de propósito. Medido em 2026-08-17, mesmo save, 1.200
        # passos: 2 batalhas e nível parado no 9 com o trail dirigindo, contra
        # 15 batalhas e nível 11 com o executor. Na corrida do operador, três
        # bots em MISSION: AUTO passaram 3h30 num canto sem mato.
        self.assertIn("viridian_forest_nav", TRAIL_BLOCKED_QUESTS)
        agent = self.agent(LAB_LEG, (4, 2), map_id=51)
        agent.current_task_name = "viridian_forest_nav"
        self.assertIsNone(agent._trail_override_step())
        self.assertEqual([], agent.walked)


if __name__ == "__main__":
    unittest.main()
