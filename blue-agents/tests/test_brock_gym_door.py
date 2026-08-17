"""A porta do ginásio de Pewter são dois tiles, e a rota começava em cima de um.

Medido na corrida do operador em 2026-08-17, com o painel aberto: JARON e KARON
em porta giratória entre o ginásio (mapa 54) e Pewter (mapa 2) — **78 transições
de mapa em 400 eventos**, sempre com a mesma assinatura no diário:

    (5,13) dentro  ->  (4,13) dentro  ->  (16,17) na cidade  ->  de novo

O mapa explica em uma linha: `warps.json` lista **(4,13) e (5,13)**, os dois
indo para o mapa 2. A rota `brock-approach` tinha (4,13) como **primeiro**
waypoint, então quem entrasse pelo (5,13) andava `L` para o outro tile de warp
e saía do ginásio. O executor da cidade o trazia de volta, e o ciclo fechava.

A regra do projeto já cobria o caso — *porta nunca é alvo de rota, exceto a
última* —, faltava a rota obedecer. E o desvio pelo x=1 era inútil: a coluna
x=4 é corredor reto de (4,12) a (4,2).
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.map_memory import MapMemory
from src.scripted_agent import TRAIL_BLOCKED_QUESTS, ScriptedAgent

PEWTER_GYM = 54
GYM_DOORS = {(4, 13), (5, 13)}
BROCK_APPROACH = (4, 2)


class GymMemory:
    def __init__(self, position, badges=0):
        self.position = position
        self.badges = badges

    def get_map_id(self):
        return PEWTER_GYM

    def get_player_pos(self):
        return self.position

    def get_party_count(self):
        return 1

    def read_byte(self, address):
        if address == 0xD356:      # wObtainedBadges
            return self.badges
        return 0


class BrockGymDoorTests(unittest.TestCase):
    def route_from(self, position, badges=0):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.emulator = type(
            "FakeEmulator", (), {"memory": GymMemory(position, badges)}
        )()
        agent.walked = []
        agent._follow_route = lambda route_id, waypoints: agent.walked.append(
            (route_id, [tuple(w) for w in waypoints])
        ) or "WALKING"
        action = agent._run_brock_quest()
        return action, agent.walked

    def test_nenhum_waypoint_da_rota_e_porta(self):
        for entrada in sorted(GYM_DOORS):
            _, walked = self.route_from(entrada)
            route_id, waypoints = walked[-1]
            self.assertEqual("brock-approach", route_id)
            self.assertEqual(
                set(), set(waypoints) & GYM_DOORS,
                f"de {entrada}: a rota mira um tile de warp",
            )

    def test_a_cadeia_e_andavel_dos_dois_tiles_da_porta(self):
        memory = MapMemory(path=None)
        cells = memory.static[PEWTER_GYM]
        for entrada in sorted(GYM_DOORS):
            _, walked = self.route_from(entrada)
            _, waypoints = walked[-1]
            current = entrada
            for waypoint in waypoints:
                self.assertIn(
                    waypoint, cells, f"waypoint {waypoint} não é andável"
                )
                self.assertIsNotNone(
                    memory.find_path(PEWTER_GYM, current, waypoint),
                    f"{current} -> {waypoint} não tem caminho",
                )
                current = waypoint
            self.assertEqual(BROCK_APPROACH, waypoints[-1])

    def test_o_caminho_do_estatico_nao_passa_por_warp(self):
        # A prova independente da rota escrita: o próprio mapa diz que existe
        # caminho da porta até o Brock sem pisar na outra porta.
        memory = MapMemory(path=None)
        cells = memory.static[PEWTER_GYM]
        self.assertIn((4, 12), cells)
        self.assertIn((5, 12), cells)
        for entrada in sorted(GYM_DOORS):
            caminho = memory.find_path(PEWTER_GYM, entrada, BROCK_APPROACH)
            self.assertIsNotNone(caminho)

    def test_no_tile_do_brock_a_rota_sai_de_cena(self):
        action, walked = self.route_from(BROCK_APPROACH)
        self.assertEqual([], walked, "em (4,2) quem manda é a conversa, não a rota")
        self.assertIsNotNone(action)

    def test_o_trail_nao_dirige_no_ginasio(self):
        # A causa medida da porta giratória. Mesmo save vivo do KARON (mapa 54,
        # (5,13)), 400 passos, mudando só `POKEAI_FOLLOW_TRAILS`: 32 trocas de
        # mapa 54↔2 e nenhuma insígnia com o trail dirigindo; com ele
        # bloqueado, o mesmo save tira a insígnia em 600 passos. O trecho
        # `porta-do-ginasio` do replay_check roda isso no cartucho.
        self.assertIn("brock_quest", TRAIL_BLOCKED_QUESTS)

    def test_com_a_insignia_o_executor_nao_tem_mais_nada_a_fazer(self):
        action, walked = self.route_from((4, 12), badges=0x01)
        self.assertIsNone(action)
        self.assertEqual([], walked)


if __name__ == "__main__":
    unittest.main()
