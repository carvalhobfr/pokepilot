"""A porta é destino, nunca atalho — mas o último waypoint fica depois dela.

As rotas deste projeto terminam **um tile além** da porta de propósito: é esse
passo que atravessa. O planejador tratava toda porta como intransponível, então
o alvo de fora do mapa ficava sem caminho — não existe outro caminho para um
tile que só a porta alcança. Sem plano, `route_no_progress` sobe até a regra de
fronteira trocar o alvo pelo canto inexplorado mais próximo.

Medido em 2026-08-16 na casa inicial do jogo (mapa 37), com dois bots novos e
10 minutos cada: nenhum saiu da primeira casa. O HARON andava até (7,6),
voltava a casa inteira e ficava oscilando em (0,2)/(1,2) — **11.355**
relatórios de travamento no mesmo tile, com a porta a oito passos e o cartucho
respondendo `reachable=47, steps=7, path=RDDDDRD` para ela.

Com a exceção, o mesmo save sai da casa, cruza Pallet e entra no laboratório do
Oak em ~200 passos roteirizados.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.map_memory import MapMemory
from src.scripted_agent import ScriptedAgent

PLAYERS_HOUSE = 37
HOUSE_DOORS = {(2, 7), (3, 7)}
# O último waypoint de `start-house-1f`, fora do mapa andável de propósito.
BEYOND_THE_DOOR = (3, 8)


class Reader:
    def __init__(self, warps):
        self.warps = set(warps)

    def occupied_offsets(self):
        return ()

    def warp_tiles(self):
        return set(self.warps)

    def terrain_grid(self):  # pragma: no cover - o menu aberto pula a leitura
        raise AssertionError("não deveria ler terreno com menu aberto")


class Memory:
    def __init__(self, position):
        self.position = tuple(position)

    def get_player_pos(self):
        return self.position

    def get_map_id(self):
        return PLAYERS_HOUSE

    def read_byte(self, address):
        return 0


class DoorAsLastWaypointTests(unittest.TestCase):
    def agent_at(self, position, warps=HOUSE_DOORS):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.emulator = type(
            "FakeEmulator", (), {"memory": Memory(position), "pyboy": object()}
        )()
        agent.tile_collision = Reader(warps)
        agent.map_memory = MapMemory(path=None)
        agent._map_memory = lambda: agent.map_memory
        # Com o menu "aberto" o plano não lê terreno da tela — o teste é sobre
        # o estático, que é a autoridade de geometria.
        agent._menu_is_open = lambda: True
        return agent

    def test_o_tile_depois_da_porta_tem_plano(self):
        agent = self.agent_at((3, 6))
        self.assertNotIn(
            BEYOND_THE_DOOR, agent.map_memory.static[PLAYERS_HOUSE],
            "o waypoint final é fora do mapa andável, por convenção",
        )
        self.assertEqual(
            "D", agent._planned_step(PLAYERS_HOUSE, 3, 6, *BEYOND_THE_DOOR),
            "de cima da porta, o passo é atravessá-la",
        )

    def test_do_outro_lado_da_casa_o_plano_chega_na_porta(self):
        agent = self.agent_at((1, 2))
        step = agent._planned_step(PLAYERS_HOUSE, 1, 2, *BEYOND_THE_DOOR)
        self.assertIsNotNone(step, "sem plano, a fronteira sequestra o alvo")
        self.assertIn(step, ("D", "R"))

    def test_waypoint_comum_continua_contornando_a_porta(self):
        # A gravidade do Mart: alvo andável a poucos tiles, com a porta no
        # meio do caminho reto. O bot entrava na loja, saía no capacho e
        # replanejava o mesmo caminho. Isso não pode voltar.
        agent = self.agent_at((1, 7))
        step = agent._planned_step(PLAYERS_HOUSE, 1, 7, 4, 7)
        self.assertIsNotNone(step)
        self.assertNotEqual(
            "R", step, "R pisaria na porta (2,7) — o alvo andável desvia",
        )

    def test_a_excecao_exige_que_a_porta_seja_vizinha_do_alvo(self):
        # Porta longe do alvo de fora do mapa continua bloqueada: a exceção é
        # para a porta que **é** a passagem, não para toda porta do mapa.
        agent = self.agent_at((1, 7), warps=HOUSE_DOORS | {(6, 7)})
        step = agent._planned_step(PLAYERS_HOUSE, 1, 7, *BEYOND_THE_DOOR)
        self.assertIsNotNone(step)


if __name__ == "__main__":
    unittest.main()
