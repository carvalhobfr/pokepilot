"""Cidade nova, Centro registrado — senão o apagão devolve tudo a Pallet.

Em Gen I o ponto de renascimento é `wLastBlackoutMap` (0xD719), e ele guarda o
mapa **de fora** do último Centro usado. Medido no cartucho em 2026-08-07:
entrar no Centro não move o endereço; só a enfermeira move. Um treinador que
atravessa meia Kanto sem parar num Centro perde tudo desde Pallet no primeiro
apagão — vira roguelite.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.scripted_agent import (
    CENTER_DOOR_BY_OUTDOOR_MAP,
    CENTER_OUTDOOR_MAP,
    LAST_BLACKOUT_MAP_ADDRESS,
    POKEMON_CENTER_MAP_IDS,
    ScriptedAgent,
)


class MemoriaFalsa:
    def __init__(self, map_id, blackout, pos=(10, 10), menu=0):
        self.map_id = map_id
        self.blackout = blackout
        self.pos = pos
        self.menu = menu

    def get_map_id(self):
        return self.map_id

    def get_player_pos(self):
        return self.pos

    def get_party_count(self):
        return 1

    def read_byte(self, address):
        if address == LAST_BLACKOUT_MAP_ADDRESS:
            return self.blackout
        if address == 0xD52A:
            return self.menu
        return 0


class CentrosDoCartuchoTests(unittest.TestCase):
    def test_onze_centros_e_nenhum_hotel(self):
        self.assertEqual(
            {41, 58, 64, 68, 81, 89, 133, 141, 154, 171, 182},
            POKEMON_CENTER_MAP_IDS,
        )

    def test_o_centro_da_rota_10_entrou(self):
        # Faltava na lista à mão: é o Centro antes do Túnel da Rocha.
        self.assertIn(81, POKEMON_CENTER_MAP_IDS)

    def test_o_saguao_do_indigo_saiu(self):
        # Tileset e planta diferentes; a enfermeira em (3,3) não existe lá.
        self.assertNotIn(174, POKEMON_CENTER_MAP_IDS)

    def test_o_hotel_de_celadon_nunca_entrou(self):
        self.assertNotIn(140, POKEMON_CENTER_MAP_IDS)

    def test_cada_centro_conhece_a_propria_cidade(self):
        self.assertEqual(1, CENTER_OUTDOOR_MAP[41])
        self.assertEqual(15, CENTER_OUTDOOR_MAP[68])
        self.assertEqual(len(POKEMON_CENTER_MAP_IDS), len(CENTER_OUTDOOR_MAP))


class RegistrarORenascimentoTests(unittest.TestCase):
    def agente(self, map_id, blackout, pos=(10, 10), menu=0):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        memoria = MemoriaFalsa(map_id, blackout, pos, menu)
        agent.emulator = type("FakeEmulator", (), {"memory": memoria})()
        agent.andou = []
        agent._follow_route = lambda route_id, waypoints: agent.andou.append(
            (route_id, waypoints)
        ) or "ANDANDO"
        agent._walk_to_door = lambda prefix, destinos: agent.andou.append(
            (prefix, sorted(destinos))
        ) or "PORTA"
        return agent

    def test_cidade_nova_manda_procurar_o_centro(self):
        agent = self.agente(map_id=2, blackout=1)   # em Pewter, respawn Viridian
        self.assertEqual("PORTA", agent._center_first_action())

    def test_cidade_ja_registrada_nao_desvia(self):
        agent = self.agente(map_id=2, blackout=2)
        self.assertIsNone(agent._center_first_action())
        self.assertEqual([], agent.andou)

    def test_mapa_sem_centro_nao_desvia(self):
        agent = self.agente(map_id=51, blackout=0)  # Floresta
        self.assertIsNone(agent._center_first_action())

    def test_dentro_do_centro_sem_registro_vai_a_enfermeira(self):
        agent = self.agente(map_id=58, blackout=1, pos=(3, 7))
        self.assertEqual("ANDANDO", agent._center_first_action())
        self.assertEqual([(3, 7), (3, 3)], agent.andou[0][1])

    def test_no_balcao_sem_registro_conversa(self):
        agent = self.agente(map_id=58, blackout=1, pos=(3, 3), menu=8)
        from pyboy.utils import WindowEvent
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._center_first_action())

    def test_depois_de_registrado_sai_do_centro(self):
        # O cartucho diz que acabou: 0xD719 aponta para Pewter.
        agent = self.agente(map_id=58, blackout=2, pos=(3, 3))
        self.assertEqual("ANDANDO", agent._center_first_action())
        self.assertEqual([(3, 7)], agent.andou[0][1])

    def test_no_capacho_registrado_pressiona_para_fora(self):
        from pyboy.utils import WindowEvent
        agent = self.agente(map_id=58, blackout=2, pos=(3, 7))
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent._center_first_action())

    def test_hp_nao_participa_de_nada(self):
        # A cura por HP baixo continua cancelada: o gatilho é só o endereço.
        agent = self.agente(map_id=2, blackout=2)
        agent._party_health_fraction = lambda: 0.01
        self.assertIsNone(agent._center_first_action())

    def test_toda_cidade_com_centro_tem_porta_conhecida(self):
        for center, outdoor in CENTER_OUTDOOR_MAP.items():
            self.assertIn(outdoor, CENTER_DOOR_BY_OUTDOOR_MAP, f"Centro {center}")


if __name__ == "__main__":
    unittest.main()
