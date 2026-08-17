"""Vermilion fica ao SUL de Cerulean — e o executor mandava para leste.

Medido no cartucho entre 14/08 e 16/08 de 2026, dois dias de corrida do AARON:
1.976 transições entre o mapa 3 (Cerulean) e o mapa 20 (Rota 9), o bot parado
em (20, 0,9) e (3, 39,17), nenhum tile novo. A Rota 9 é o caminho do Túnel da
Rocha; o warp de Cerulean para lá desemboca num beco de nove tiles cuja única
saída é voltar — e o mapa 3 mandava para leste de novo.

O caminho real: borda sul de Cerulean (26,35) -> Route 5 (16) -> Underground
(71/119/74) -> Route 6 (17) -> Vermilion (mapa **5**, não 1).

Cada waypoint aqui é conferido contra `static_maps.json` com o `find_path` do
MapMemory — a mesma pergunta que o executor faz em tempo de execução. Uma
cadeia com um hop `NONE` é um waypoint que queima orçamento sem sair do lugar.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from pyboy.utils import WindowEvent

from src.map_memory import MapMemory
from src.scripted_agent import (
    CERULEAN_SOUTH_EXIT,
    CUT_MOVE_ID,
    HM01_CUT,
    ROUTE_EVENTS,
    SS_ANNE_CABIN_APPROACH,
    SS_ANNE_CAPTAIN_MAP_ID,
    SS_ANNE_DECK_MAP_ID,
    SS_ANNE_UPPER_MAP_ID,
    TRAIL_BLOCKED_QUESTS,
    VERMILION_CENTER_MAP_ID,
    VERMILION_CITY_MAP_ID,
    ScriptedAgent,
)

CERULEAN = 3
ROUTE_5 = 16
ROUTE_9 = 20
ROUTE_6 = 17
UNDERGROUND_NORTH = 71
UNDERGROUND_PATH = 119
UNDERGROUND_SOUTH = 74


class RouteMemory:
    """Mapa, posição, endereço de renascimento e a mochila."""

    def __init__(self, map_id, position, blackout=0, bag=None, party=None):
        self.map_id = map_id
        self.position = position
        self.blackout = blackout
        self.bag = list((bag or {}).items())
        self.facing_up = False
        # Cada membro é a lista dos quatro slots de golpe.
        self.party = list(party or [])

    def get_party_count(self):
        return len(self.party)

    def get_map_id(self):
        return self.map_id

    def get_player_pos(self):
        return self.position

    def read_byte(self, address):
        if address == 0xD719:      # wLastBlackoutMap
            return self.blackout
        if address == 0xC109:      # wSpriteStateData1 + 9: para onde encara
            return 4 if self.facing_up else 0
        if address == 0xD163:      # wPartyCount
            return len(self.party)
        if 0xD16B <= address < 0xD16B + 44 * max(len(self.party), 1):
            slot, offset = divmod(address - 0xD16B, 44)
            if slot < len(self.party) and 8 <= offset <= 11:
                return self.party[slot][offset - 8]
            return 0
        if address == 0xD31D:      # wNumBagItems
            return len(self.bag)
        if 0xD31E <= address < 0xD31E + 2 * len(self.bag):
            index, offset = divmod(address - 0xD31E, 2)
            item_id, count = self.bag[index]
            return item_id if offset == 0 else count
        return 0


class VermilionRouteTests(unittest.TestCase):
    def agent_at(self, map_id, position, blackout=0, bag=None, party=None):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        memory = RouteMemory(map_id, position, blackout, bag, party)
        agent.emulator = type("FakeEmulator", (), {"memory": memory})()
        agent.walked = []
        agent.centers = []
        agent.map_memory = MapMemory(path=None)
        agent._map_memory = lambda: agent.map_memory
        agent._follow_route = lambda route_id, waypoints: agent.walked.append(
            (route_id, list(waypoints))
        ) or "WALKING"
        agent._run_pokemon_center = lambda prefix, healed: agent.centers.append(
            (prefix, healed)
        ) or "CENTER"
        return agent

    def route_from(self, map_id, position, blackout=0, bag=None, party=None):
        agent = self.agent_at(map_id, position, blackout, bag, party)
        action = agent._run_vermilion_gym_quest()
        return action, agent.walked

    def assert_chain_walkable(self, map_id, start, waypoints, last_is_anchor=False):
        """Toda perna existe **e todo waypoint do meio é pisável**.

        `find_path` isenta o alvo de propósito — o último waypoint de uma rota
        fica fora do mapa andável, porque é ele que força o passo que
        atravessa. Só que isso fazia esta checagem aprovar waypoint em cima de
        parede: (19,20) de Vermilion é muro, a cadeia passou verde, e o AARON
        gastou 120 passos batendo `L` contra ele com `path: L` no relatório.
        Caminho existir não basta; o tile do meio tem de existir.
        """
        memory = MapMemory(path=None)
        cells = memory.static[map_id]
        current = tuple(start)
        for index, waypoint in enumerate(waypoints):
            waypoint = tuple(waypoint)
            self.assertIsNotNone(
                memory.find_path(map_id, current, waypoint),
                f"mapa {map_id}: {current} -> {waypoint} não tem caminho",
            )
            is_last = index == len(waypoints) - 1
            if not (is_last and last_is_anchor):
                self.assertIn(
                    waypoint, cells,
                    f"mapa {map_id}: waypoint {waypoint} não é andável",
                )
            current = waypoint

    # --- o ciclo que custou dois dias -----------------------------------

    def test_cerulean_leste_desce_para_o_sul_nunca_para_a_rota_9(self):
        # (39,17) é onde AARON passou dois dias: a borda leste, de onde se
        # cruza para o beco da Rota 9.
        _, walked = self.route_from(CERULEAN, (39, 17))
        route_id, waypoints = walked[-1]
        self.assertEqual("cerulean-south-to-route5", route_id)
        self.assertEqual(CERULEAN_SOUTH_EXIT, waypoints[-2])
        # Nenhum waypoint mira a borda leste (x=39), que é a Rota 9.
        self.assertTrue(all(x < 39 for x, _ in waypoints))

    def test_a_cadeia_sul_e_andavel_de_ponta_a_ponta(self):
        for start in ((39, 17), (38, 17), (27, 9), (33, 12), (36, 29)):
            _, walked = self.route_from(CERULEAN, start)
            _, waypoints = walked[-1]
            # O último waypoint fica um tile além da borda de propósito.
            self.assert_chain_walkable(CERULEAN, start, waypoints[:-1])

    def test_a_borda_sul_entra_na_route_5(self):
        # A conexão soma 10 ao x: (26,35) em Cerulean é (16,0) na Route 5, e
        # de lá a coluna leste desce até a porta do Underground.
        memory = MapMemory(path=None)
        self.assertIn(CERULEAN_SOUTH_EXIT, memory.static[CERULEAN])
        self.assertIsNotNone(memory.find_path(ROUTE_5, (16, 0), (17, 27)))

    def test_lado_oeste_do_rio_vai_para_a_casa_nao_para_o_sul(self):
        # Do Centro de Cerulean (19,17) nenhuma célula do sul é alcançável:
        # o rio parte o mapa em dois componentes. O caminho é a casa acima
        # do ginásio, cujo buraco devolve o jogador em (27,9), já a leste.
        _, walked = self.route_from(CERULEAN, (19, 18))
        route_id, waypoints = walked[-1]
        self.assertEqual("cerulean-to-house", route_id)
        self.assertEqual((27, 12), waypoints[-1])
        self.assert_chain_walkable(CERULEAN, (19, 18), waypoints)

    def test_o_teste_de_componente_separa_o_ginasio_do_lado_leste(self):
        # A caixa antiga (26 <= x <= 39, 7 <= y <= 17) chamava de "leste"
        # qualquer coisa naquele retângulo. O ginásio (30,19) e o Centro são
        # do lado oeste, e o `_can_reach` acerta os dois.
        agent = self.agent_at(CERULEAN, (30, 20))
        self.assertFalse(agent._can_reach(CERULEAN, CERULEAN_SOUTH_EXIT))
        agent = self.agent_at(CERULEAN, (27, 9))
        self.assertTrue(agent._can_reach(CERULEAN, CERULEAN_SOUTH_EXIT))

    # --- pernas do meio -------------------------------------------------

    def test_route_5_desce_pela_coluna_que_alcanca_a_porta(self):
        _, walked = self.route_from(ROUTE_5, (16, 0))
        route_id, waypoints = walked[-1]
        self.assertEqual("route5-to-underground", route_id)
        self.assertEqual((17, 27), waypoints[-1])
        self.assert_chain_walkable(ROUTE_5, (16, 0), waypoints)

    def test_a_coluna_13_da_route_5_nao_alcanca_a_porta(self):
        # Era a cadeia antiga. Os penhascos isolam a faixa do meio.
        memory = MapMemory(path=None)
        self.assertIsNone(memory.find_path(ROUTE_5, (9, 0), (17, 27)))

    def test_underground_termina_no_tile_do_warp(self):
        _, walked = self.route_from(UNDERGROUND_PATH, (5, 4))
        _, waypoints = walked[-1]
        self.assertEqual((2, 41), waypoints[-1])
        self.assert_chain_walkable(UNDERGROUND_PATH, (5, 4), waypoints)

    def test_route_6_desce_ate_a_borda_de_vermilion(self):
        _, walked = self.route_from(ROUTE_6, (17, 13))
        route_id, waypoints = walked[-1]
        self.assertEqual("route6-to-vermilion", route_id)
        self.assertEqual((9, 36), waypoints[-1])
        self.assert_chain_walkable(ROUTE_6, (17, 13), waypoints[:-1])

    # --- chegar -----------------------------------------------------------

    def test_vermilion_e_o_mapa_5_e_o_centro_dela_e_o_89(self):
        self.assertEqual(5, VERMILION_CITY_MAP_ID)
        self.assertEqual(89, VERMILION_CENTER_MAP_ID)

    def test_na_cidade_o_executor_vai_ao_centro_registrar(self):
        _, walked = self.route_from(VERMILION_CITY_MAP_ID, (19, 0))
        route_id, waypoints = walked[-1]
        self.assertEqual("vermilion-to-center", route_id)
        self.assertEqual((11, 3), waypoints[-1])
        self.assert_chain_walkable(VERMILION_CITY_MAP_ID, (19, 0), waypoints)

    def test_com_o_centro_gravado_a_cidade_manda_para_o_navio(self):
        # `wLastBlackoutMap` apontando para Vermilion (5) é o cartucho
        # dizendo que o checkpoint está gravado. Sem Cut na mochila, a perna
        # seguinte é o S.S. Anne — a árvore do ginásio não abre sem ele.
        _, walked = self.route_from(
            VERMILION_CITY_MAP_ID, (19, 0), blackout=VERMILION_CITY_MAP_ID
        )
        route_id, waypoints = walked[-1]
        self.assertEqual("vermilion-to-ss-anne", route_id)
        self.assertEqual((18, 31), waypoints[-1])
        self.assert_chain_walkable(VERMILION_CITY_MAP_ID, (19, 0), waypoints)

    def test_a_descida_desvia_do_marinheiro_parado_em_19_30(self):
        _, walked = self.route_from(
            VERMILION_CITY_MAP_ID, (19, 0), blackout=VERMILION_CITY_MAP_ID
        )
        _, waypoints = walked[-1]
        memory = MapMemory(path=None)
        self.assertIn(
            (19, 30), memory.object_positions(VERMILION_CITY_MAP_ID),
            "o marinheiro é objeto do ROM em (19,30)",
        )
        self.assertTrue(all(tuple(w) != (19, 30) for w in waypoints))

    def test_com_o_hm_na_mochila_mas_sem_o_golpe_a_cidade_ensina(self):
        # HM na mochila não corta árvore nenhuma: o golpe precisa estar num
        # Pokémon. Sem menu aberto, o primeiro passo é START.
        action, walked = self.route_from(
            VERMILION_CITY_MAP_ID, (19, 0),
            blackout=VERMILION_CITY_MAP_ID,
            bag={HM01_CUT: 1},
            party=[[77, 45, 73, 22]],
        )
        self.assertEqual(WindowEvent.PRESS_BUTTON_START, action)
        self.assertEqual([], walked)

    def test_com_o_cut_aprendido_a_cidade_solta_o_controle(self):
        action, walked = self.route_from(
            VERMILION_CITY_MAP_ID, (19, 0),
            blackout=VERMILION_CITY_MAP_ID,
            bag={HM01_CUT: 1},
            party=[[77, CUT_MOVE_ID, 73, 22]],
        )
        self.assertIsNone(action)
        self.assertEqual([], walked)

    def test_em_cima_da_prancha_o_passo_e_atravessar(self):
        action, _ = self.route_from(
            VERMILION_CITY_MAP_ID, (18, 31), blackout=VERMILION_CITY_MAP_ID
        )
        self.assertEqual(ROUTE_EVENTS["D"], action)

    def test_dentro_do_centro_de_vermilion_manda_o_controlador_de_centro(self):
        agent = self.agent_at(VERMILION_CENTER_MAP_ID, (3, 7))
        self.assertEqual("CENTER", agent._run_vermilion_gym_quest())
        self.assertEqual([("vermilion-center", "vermilion_center_healed")], agent.centers)

    def test_viridian_nao_e_mais_confundida_com_vermilion(self):
        # O bloco antigo reagia no mapa 1 (Viridian) e mandava para a porta
        # (23,25), que é o Centro de Viridian.
        action, walked = self.route_from(1, (23, 24))
        self.assertIsNone(action)
        self.assertEqual([], walked)

    def test_o_beco_da_rota_9_so_volta_para_cerulean(self):
        _, walked = self.route_from(ROUTE_9, (0, 9))
        route_id, _ = walked[-1]
        self.assertEqual("route9-back-to-cerulean", route_id)

    # --- S.S. Anne: o navio que entrega o Cut -----------------------------

    def test_o_convés_desce_ate_a_escada_do_segundo_andar(self):
        _, walked = self.route_from(SS_ANNE_DECK_MAP_ID, (26, 1))
        route_id, waypoints = walked[-1]
        self.assertEqual("ss-anne-1f", route_id)
        self.assertEqual((2, 6), waypoints[-1], "a escada (2,6) sobe para o 96")
        self.assert_chain_walkable(SS_ANNE_DECK_MAP_ID, (26, 1), waypoints)

    def test_o_segundo_andar_aproxima_a_cabine_pelo_leste(self):
        _, walked = self.route_from(SS_ANNE_UPPER_MAP_ID, (2, 4))
        route_id, waypoints = walked[-1]
        self.assertEqual("ss-anne-2f", route_id)
        self.assertEqual(SS_ANNE_CABIN_APPROACH, waypoints[-1])
        self.assert_chain_walkable(SS_ANNE_UPPER_MAP_ID, (2, 4), waypoints)
        memory = MapMemory(path=None)
        self.assertNotIn(
            (35, 4), memory.static[SS_ANNE_UPPER_MAP_ID],
            "o tile a oeste da porta não é andável: a aproximação é (37,4)",
        )

    def test_o_rival_em_cima_da_porta_e_encostado_nao_contornado(self):
        # O bloco de objetos do ROM põe um `trainer` (classe 225) exatamente
        # no warp (36,4). Um passo para a esquerda encosta nele; a máquina de
        # sprite abre o diálogo e a batalha assume.
        memory = MapMemory(path=None)
        self.assertIn(
            (36, 4), memory.object_positions(SS_ANNE_UPPER_MAP_ID),
            "o rival é objeto do ROM em cima da porta da cabine",
        )
        action, _ = self.route_from(SS_ANNE_UPPER_MAP_ID, SS_ANNE_CABIN_APPROACH)
        self.assertEqual(ROUTE_EVENTS["L"], action)

    def test_na_cabine_o_bot_anda_ate_a_frente_do_capitao(self):
        _, walked = self.route_from(SS_ANNE_CAPTAIN_MAP_ID, (0, 7))
        route_id, waypoints = walked[-1]
        self.assertEqual("ss-anne-captain", route_id)
        self.assertEqual((4, 3), waypoints[-1])
        self.assert_chain_walkable(SS_ANNE_CAPTAIN_MAP_ID, (0, 7), waypoints)

    def test_de_costas_o_bot_encara_o_capitao_antes_de_apertar_A(self):
        # A de costas não abre diálogo nenhum em Gen I.
        agent = self.agent_at(SS_ANNE_CAPTAIN_MAP_ID, (4, 3))
        agent._menu_is_open = lambda: False
        self.assertEqual(WindowEvent.PRESS_ARROW_UP, agent._run_vermilion_gym_quest())

    def test_encarando_o_capitao_o_passo_e_A(self):
        agent = self.agent_at(SS_ANNE_CAPTAIN_MAP_ID, (4, 3))
        agent._menu_is_open = lambda: False
        agent.emulator.memory.facing_up = True
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._run_vermilion_gym_quest())

    def test_com_texto_na_tela_o_passo_e_A(self):
        agent = self.agent_at(SS_ANNE_CAPTAIN_MAP_ID, (4, 3))
        agent._menu_is_open = lambda: True
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._run_vermilion_gym_quest())

    def test_com_o_hm_na_mochila_a_cabine_e_abandonada(self):
        # Quem decide que acabou é o cartucho — o HM01 na mochila —, não um
        # contador de "já falei", que some no reinício.
        _, walked = self.route_from(
            SS_ANNE_CAPTAIN_MAP_ID, (4, 3), bag={HM01_CUT: 1}
        )
        route_id, waypoints = walked[-1]
        self.assertEqual("ss-anne-captain-exit", route_id)
        self.assertEqual((0, 7), waypoints[-1])

    def test_com_o_hm_o_navio_inteiro_vira_saida(self):
        # Sem isto o 2º andar continuava mirando a porta da cabine: o bot saía
        # em (0,7), desembarcava em cima do próprio warp (36,4) e reentrava.
        # Medido no cartucho: duas viagens por segundo entre 96 e 101.
        for map_id, start, expected in (
            (SS_ANNE_UPPER_MAP_ID, (36, 4), "ss-anne-2f-exit"),
            (SS_ANNE_DECK_MAP_ID, (2, 6), "ss-anne-1f-exit"),
        ):
            _, walked = self.route_from(map_id, start, bag={HM01_CUT: 1})
            route_id, waypoints = walked[-1]
            self.assertEqual(expected, route_id)
            self.assert_chain_walkable(map_id, start, waypoints)

    def test_a_saida_do_segundo_andar_nao_tenta_ir_para_oeste(self):
        # (35,4) é parede: de cima da porta só se desce pela coluna leste.
        memory = MapMemory(path=None)
        self.assertNotIn((35, 4), memory.static[SS_ANNE_UPPER_MAP_ID])
        _, walked = self.route_from(
            SS_ANNE_UPPER_MAP_ID, (36, 4), bag={HM01_CUT: 1}
        )
        _, waypoints = walked[-1]
        self.assertEqual((36, 12), waypoints[0], "desce antes de cruzar")

    # --- o trail não dirige esta quest ------------------------------------

    def test_o_trail_da_guia_manual_nao_sequestra_o_executor(self):
        # Desligar o modo guia publica o caminho do operador como trail da
        # quest. Medido em 2026-08-16, minutos depois: o trail assumiu no
        # mapa 16 (`trail-vermilion_gym_quest-16`), mirou (9,0) — a faixa do
        # meio, isolada da porta — com `path_to_target: None`, e o bot quicou
        # em (15,0)..(15,5) por 600 passos.
        self.assertIn("vermilion_gym_quest", TRAIL_BLOCKED_QUESTS)

    def test_o_bloqueio_de_trail_vale_para_o_override(self):
        agent = self.agent_at(ROUTE_5, (15, 0))
        agent.current_task_name = "vermilion_gym_quest"
        agent._manual_mode_active = lambda: False
        self.assertIsNone(agent._trail_override_step())


class LedgeIsNotAWallWithADoorBehindItTests(unittest.TestCase):
    """Penhasco e parede-com-porta-atrás têm a mesma assinatura no estático.

    A regra de pulo dispara com o alvo alinhado a dois tiles, o tile do meio
    sólido e o pouso andável. A porta do Underground na Route 5 é isso: de
    (15,27) o alvo (17,27) está a dois tiles, (16,27) é parede do prédio e
    (17,27) é a porta. Medido em 2026-08-16: o bot apertou R contra a parede
    por 250 passos com o desvio de quatro passos (D,R,R,U) já calculado.

    O desempate é o plano: quem tem caminho andando não pula. Na Rota 4 o
    penhasco parte o mapa e não existe plano — é lá que o pulo vale.
    """

    def make_agent(self, position, map_id, blocked, planned=None):
        from src.warp_memory import WarpMemory

        agent = ScriptedAgent.__new__(ScriptedAgent)
        memory = RouteMemory(map_id, tuple(position))
        agent.emulator = type("FakeEmulator", (), {"memory": memory})()
        agent._tile_truth = lambda: dict(blocked)
        agent._planned_step = lambda *args: planned
        agent.warp_memory = WarpMemory()
        agent.map_memory = MapMemory(path=None)
        agent._map_memory = lambda: agent.map_memory
        return agent

    def test_a_porta_atras_da_parede_e_contornada_nao_pulada(self):
        from pyboy.utils import WindowEvent

        agent = self.make_agent(
            (15, 27), ROUTE_5, {"R": "terrain"}, planned="D"
        )
        self.assertEqual(
            WindowEvent.PRESS_ARROW_DOWN,
            agent._follow_route("route5-to-underground", [(17, 27)]),
        )

    def test_sem_plano_o_pulo_continua_valendo(self):
        from pyboy.utils import WindowEvent

        # Rota 4, (79,8) -> (79,10): o penhasco em y=9 não tem desvio.
        agent = self.make_agent((79, 8), 15, {"D": "terrain"}, planned=None)
        self.assertEqual(
            WindowEvent.PRESS_ARROW_DOWN,
            agent._follow_route("mt-moon-to-cerulean", [(79, 10)]),
        )


if __name__ == "__main__":
    unittest.main()
