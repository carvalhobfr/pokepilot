"""Kanto como grafo: cada aresta conferida contra fato já medido no cartucho.

O grafo existe para acabar com a classe de trabalho que dominou 12 e 16 de
agosto: onze executores com as coordenadas de cada travessia decoradas, um erro
de mapa custando dois dias (a rota do vermilion apontando para a Rota 9), e o
trail — que é gravação de passos, não geometria — dirigindo por cima deles.

Os números aqui não são escolhidos: cada um é um fato que este projeto mediu no
cartucho antes de existir grafo nenhum.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.kanto_graph import KantoGraph

PALLET, ROUTE_1, VIRIDIAN, ROUTE_2 = 0, 12, 1, 13
PEWTER, PEWTER_GYM = 2, 54
CERULEAN, ROUTE_4, ROUTE_5 = 3, 15, 16
FOREST, NORTH_GATE = 51, 47


class GraphFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = KantoGraph()


class BordasTests(GraphFixture):
    def test_cerulean_sul_cai_na_route_5_dez_a_oeste(self):
        # Medido em 2026-08-16: "(26,35) é a saída sul, e um passo além entra na
        # Route 5 em (16,0) — a conexão soma 10 ao x".
        border = next(
            b for b in self.graph.borders[CERULEAN] if b["dir"] == "south"
        )
        self.assertEqual(ROUTE_5, border["to"])
        self.assertEqual(
            (ROUTE_5, 16, 0),
            self.graph.border_arrival(CERULEAN, border, 26, 35),
        )

    def test_route_4_leste_entra_em_cerulean_no_tile_do_aaron(self):
        # Medido em 2026-08-12: o AARON entrou na cidade em m3 (0,18), vindo da
        # Rota 4 na altura y=10.
        border = next(
            b for b in self.graph.borders[ROUTE_4] if b["dir"] == "east"
        )
        self.assertEqual(CERULEAN, border["to"])
        self.assertEqual(
            (CERULEAN, 0, 18),
            self.graph.border_arrival(ROUTE_4, border, 79, 10),
        )

    def test_pallet_sobe_para_a_route_1(self):
        border = next(
            b for b in self.graph.borders[PALLET] if b["dir"] == "north"
        )
        self.assertEqual(ROUTE_1, border["to"])
        arrival = self.graph.border_arrival(PALLET, border, 10, 0)
        self.assertEqual(ROUTE_1, arrival[0])
        self.assertIn(arrival[1:], self.graph._cells(ROUTE_1))


class PortasTests(GraphFixture):
    def test_a_porta_do_ginasio_de_pewter_e_o_par_do_tile_16_17(self):
        # O par exato onde JARON e KARON ficaram em porta giratória em
        # 2026-08-17: (16,17) da cidade e (4,13) do ginásio.
        door = next(
            d for d in self.graph.warps[PEWTER]
            if (d["x"], d["y"]) == (16, 17)
        )
        self.assertEqual(
            (PEWTER_GYM, 4, 13), self.graph.warp_arrival(PEWTER, door)
        )

    def test_porta_dinamica_resolve_pelo_par_mutuo(self):
        # O portão norte da Floresta tem as duas portas de fora com destino
        # `0xFF`. "Quem aponta para cá" é ambíguo (Rota 2 e Floresta apontam), e
        # o par mútuo não é: a porta 1 do portão casa com a porta 1 da Rota 2.
        door = next(
            d for d in self.graph.warps[NORTH_GATE]
            if (d["x"], d["y"]) == (5, 0)
        )
        self.assertEqual(-1, door["to"], "é dinâmica no ROM")
        self.assertEqual(
            (ROUTE_2, 3, 11), self.graph.warp_arrival(NORTH_GATE, door)
        )

    def test_tile_de_porta_e_pisavel_no_grafo(self):
        # O estático do ROM não marca warp como andável — é por isso que
        # `_planned_step` precisa da exceção da porta. Sem tratar porta como nó,
        # a busca respondia "sem caminho" para dentro de qualquer prédio.
        self.assertIn((4, 13), self.graph._cells(PEWTER_GYM))
        self.assertIn((16, 17), self.graph._cells(PEWTER))


class BuscaTests(GraphFixture):
    def test_de_pallet_ao_brock_pelo_caminho_que_o_jogo_tem(self):
        path = self.graph.path((PALLET, 5, 6), (PEWTER_GYM, 4, 2))
        self.assertIsNotNone(path)
        crossed = self.graph.maps_crossed(path)
        # Pallet, Rota 1, Viridian, Rota 2, portão, Floresta, portão, Rota 2,
        # Pewter, ginásio — a abertura do jogo, sem uma coordenada escrita à mão.
        for map_id in (PALLET, ROUTE_1, VIRIDIAN, ROUTE_2, FOREST, PEWTER,
                       PEWTER_GYM):
            self.assertIn(map_id, crossed)
        self.assertEqual((PEWTER_GYM, 4, 2), path[-1])

    def test_o_caminho_e_continuo_passo_a_passo(self):
        # Cada nó do caminho tem de ser vizinho do seguinte: sem isso o
        # "caminho" é uma lista de carimbos, que é o defeito do trail.
        path = self.graph.path((PALLET, 5, 6), (PEWTER_GYM, 4, 2))
        for current, following in zip(path, path[1:]):
            neighbours = [
                node for _key, node
                in self.graph.neighbors(current, allow_jumps=True)
            ]
            self.assertIn(following, neighbours, f"{current} -> {following}")

    def test_dentro_de_um_mapa_o_grafo_concorda_com_o_find_path(self):
        # O corredor do ginásio de Pewter: 11 passos da porta ao Brock, o mesmo
        # número que o `find_path` do MapMemory dá.
        path = self.graph.path((PEWTER_GYM, 4, 13), (PEWTER_GYM, 4, 2))
        self.assertEqual(11, len(path) - 1)

    def test_quem_tem_caminho_andando_nao_pula(self):
        # A mesma ordem de autoridade do executor. Vale como regra porque
        # penhasco e parede-com-chão-atrás têm a mesma assinatura no estático.
        path = self.graph.path((PEWTER_GYM, 4, 13), (PEWTER_GYM, 4, 2))
        self.assertTrue(
            all(not key.startswith("J") for key in self.graph.steps(path))
        )

    def test_a_route_4_so_atravessa_com_pulo_de_penhasco(self):
        # O penhasco da Rota 4 parte o mapa no estático: foi ele que segurou o
        # grafo na saída de Mt. Moon, com a borda leste inalcançável.
        start, goal = (ROUTE_4, 19, 10), (ROUTE_4, 89, 10)
        self.assertIsNone(self.graph.path(start, goal, allow_jumps=False))
        self.assertIsNotNone(self.graph.path(start, goal, allow_jumps=True))

    def test_alvo_igual_a_origem_devolve_o_proprio_no(self):
        self.assertEqual(
            [(PALLET, 5, 6)], self.graph.path((PALLET, 5, 6), (PALLET, 5, 6))
        )

    def test_pernas_sao_por_mapa(self):
        path = self.graph.path((PALLET, 5, 6), (PEWTER_GYM, 4, 2))
        legs = self.graph.legs(path)
        self.assertEqual(
            self.graph.maps_crossed(path), [map_id for map_id, _ in legs]
        )
        self.assertTrue(all(tiles for _map_id, tiles in legs))


class PortaNuncaEAlvoDoMeioTests(GraphFixture):
    """Warp no meio de uma rota é a mesma armadilha, três vezes em um dia.

    Em 2026-08-17: a porta do ginásio de Pewter (dois tiles de warp, o primeiro
    waypoint era um deles) e a boca de Mt. Moon (idem, `(14,35)`), as duas
    produzindo vaivém de mapa — 78 transições em 400 eventos no ginásio, 10 idas
    e voltas 59↔15 na caverna. A regra do projeto já era escrita; faltava
    alguém conferindo as rotas contra a lista de warps do cartucho.
    """

    def waypoints(self, map_id, position):
        from src.map_memory import MapMemory
        from src.scripted_agent import ScriptedAgent

        class Memory:
            def get_map_id(self):
                return map_id

            def get_player_pos(self):
                return position

            def get_party_count(self):
                return 1

            def read_byte(self, address):
                return 0

        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.emulator = type("FakeEmulator", (), {"memory": Memory()})()
        agent.map_memory = MapMemory()
        agent._map_memory = lambda: agent.map_memory
        agent.walked = []
        agent._follow_route = lambda route_id, tiles: agent.walked.append(
            (route_id, [tuple(t) for t in tiles])
        ) or "WALKING"
        agent._run_mt_moon_nav()
        return agent.walked[-1]

    def test_a_rota_do_1f_nao_comeca_em_cima_do_warp_de_saida(self):
        doors = {
            (int(d["x"]), int(d["y"])) for d in self.graph.warps[59]
        }
        self.assertIn((14, 35), doors, "a boca da caverna é warp")
        route_id, waypoints = self.waypoints(59, (14, 34))
        self.assertEqual("mt-moon-59", route_id)
        self.assertEqual(
            set(), set(waypoints[:-1]) & doors,
            "só o último waypoint pode ser porta — os do meio levam para fora",
        )
        self.assertIn(waypoints[-1], doors, "o último é a escada, que é warp")


class GrafoComoRedeDaRotaTests(unittest.TestCase):
    """O executor de Mt. Moon usando o grafo quando a rota medida não alcança."""

    def agent_at(self, map_id, position):
        from src.map_memory import MapMemory
        from src.scripted_agent import ScriptedAgent

        class Memory:
            def get_map_id(self):
                return map_id

            def get_player_pos(self):
                return position

            def get_party_count(self):
                return 1

            def read_byte(self, address):
                return 0

        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.emulator = type("FakeEmulator", (), {"memory": Memory()})()
        agent.map_memory = MapMemory()
        agent._map_memory = lambda: agent.map_memory
        agent.walked = []
        agent._follow_route = lambda route_id, waypoints: agent.walked.append(
            (route_id, [tuple(w) for w in waypoints])
        ) or "WALKING"
        return agent

    def test_na_rota_3_o_grafo_assume_onde_a_rota_medida_nao_alcanca(self):
        # O tile exato do travamento do LARON em 2026-08-17: 56 minutos com
        # `route_id=mt-moon-14`, `target=(59,-1)` e `path_to_target: None`. O
        # estático não tem caminho de (22,8) até a borda norte — a Rota 3 é
        # partida por penhascos —, e a rota escrita à mão nunca alcançava dali.
        agent = self.agent_at(14, (22, 8))
        self.assertIsNone(
            agent.map_memory.find_path(14, (22, 8), (59, -1)),
            "se a rota medida passar a alcançar, este teste perdeu o sentido",
        )
        agent._run_mt_moon_nav()
        route_id, waypoints = agent.walked[-1]
        self.assertEqual("grafo-14", route_id)
        # A perna termina um tile **fora** do mapa: é esse passo que atravessa
        # para a Rota 4, a mesma convenção das rotas medidas.
        self.assertEqual((61, -1), waypoints[-1])
        self.assertEqual((61, 0), waypoints[-2])

    def test_dentro_de_mt_moon_a_rota_medida_continua_no_volante(self):
        # 1F tem rota medida que alcança, e ela ganha: o grafo é rede, não
        # substituto.
        agent = self.agent_at(59, (14, 35))
        agent._run_mt_moon_nav()
        route_id, _waypoints = agent.walked[-1]
        self.assertEqual("mt-moon-59", route_id)

    def test_rota_parada_passa_o_volante_mesmo_com_caminho_no_papel(self):
        # O oeste do 1F de Mt. Moon: em (10,22) o passo L não move no cartucho,
        # mas colisão ao vivo, `static_maps.json` e `terrain.json` dizem os três
        # que (9,22) é andável — inconsistência registrada em aberto no handoff.
        # Medido em 2026-08-17: o LARON deu 47 relatórios de travamento entre
        # (7,22) e (10,24) mirando (16,15), com caminho existindo no papel.
        agent = self.agent_at(59, (10, 23))
        self.assertIsNotNone(
            agent.map_memory.find_path(59, (10, 23), (5, 5)),
            "o estático diz que dá — é por isso que 'sem caminho' não bastava",
        )
        # O contador é o do orçamento do waypoint, que conta passos no mesmo
        # alvo e **não zera na oscilação** — `route_no_progress` zera, e por
        # isso não serve de gatilho aqui.
        agent.route_waypoint_steps = 60
        agent._run_mt_moon_nav()
        route_id, waypoints = agent.walked[-1]
        self.assertEqual("grafo-59", route_id)
        self.assertTrue(waypoints)

    def test_com_o_orcamento_baixo_a_rota_medida_segue_no_volante(self):
        agent = self.agent_at(59, (10, 23))
        agent.route_waypoint_steps = 5
        agent._run_mt_moon_nav()
        self.assertEqual("mt-moon-59", agent.walked[-1][0])


if __name__ == "__main__":
    unittest.main()
