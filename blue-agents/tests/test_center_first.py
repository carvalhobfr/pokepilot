"""Dentro de um Centro, registrar — antes de qualquer executor.

AARON atravessou a Floresta, chegou a Pewter, entrou no Centro a 53% com um
Caterpie desmaiado, e parou. `_run_pewter_city_nav` só entra no ramo do Centro
quando o portão de 20% diz sim; nada casou, e o passo caiu no fallback de mapa
desconhecido.

Todo executor que pode terminar num Centro tem o mesmo buraco, então a regra
mora à frente de todos eles.

O que a regra faz mudou em 2026-08-07, por ordem do operador: a cura automática
travava o personagem e saiu. Ficar até morrer é aceitável. Sobrou a metade que
importa — estar num Centro grava o ponto de retomada — e o desvio até a porta
de um Centro por HP baixo foi cancelado junto.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.scripted_agent import (
    POKEMON_CENTER_MAP_IDS,
    VIRIDIAN_CENTER_MAP_ID,
    ScriptedAgent,
)


class CenterMemory:
    def __init__(self, map_id, party):
        self.map_id = map_id
        self.party = party

    def get_map_id(self):
        return self.map_id

    def get_player_pos(self):
        return (11, 5)

    def get_party_count(self):
        return len(self.party)

    def read_byte(self, address):
        index, offset = divmod(address - 0xD16B, 44)
        if not 0 <= index < len(self.party):
            return 0
        hp, max_hp = self.party[index]
        if offset == 1:
            return hp >> 8
        if offset == 2:
            return hp & 0xFF
        if offset == 34:
            return max_hp >> 8
        if offset == 35:
            return max_hp & 0xFF
        return 0


class HealBeforeAnythingElseTests(unittest.TestCase):
    # AARON's real party, read from the panel while it was frozen.
    HURT = [(11, 37), (0, 18), (18, 18), (20, 20)]
    WHOLE = [(37, 37), (18, 18), (18, 18), (20, 20)]

    def agent_in(self, map_id, party, doors=None):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        memory = CenterMemory(map_id, party)
        agent.emulator = type("FakeEmulator", (), {"memory": memory})()
        agent.called = []
        agent.walked = []
        agent._run_pokemon_center = lambda prefix, healed: agent.called.append(
            (prefix, healed)
        ) or "HEALING"
        agent._tile_reader = lambda: type("FakeReader", (), {
            "warp_destinations": staticmethod(lambda: dict(doors or {})),
        })()
        agent._follow_route = lambda route_id, waypoints: agent.walked.append(
            (route_id, waypoints)
        ) or "WALKING"
        return agent

    def step(self, agent):
        return agent._center_first_action()

    def test_a_hurt_party_in_pewters_center_is_registered(self):
        agent = self.agent_in(58, self.HURT)
        self.assertEqual("HEALING", self.step(agent))
        self.assertEqual([("center-58", "center_58_healed")], agent.called)

    def test_qualquer_hp_entrega_o_controle_uma_vez_dentro(self):
        # Não há mais portão de HP: estar dentro basta.
        agent = self.agent_in(58, self.HURT)
        self.assertLess(agent._party_health_fraction(), 1.0)
        self.assertGreater(agent._party_health_fraction(), 0.2)
        self.assertEqual("HEALING", self.step(agent))

    def test_a_healed_party_inside_still_gets_the_center_controller(self):
        # It owns leaving, not just healing. Gating the whole controller on
        # "is anything missing" left AARON healed on Pewter's doormat with
        # nothing left to press it, and the executor has no branch for a whole
        # party in a Center either.
        agent = self.agent_in(58, self.WHOLE)
        self.assertEqual("HEALING", self.step(agent))
        self.assertEqual([("center-58", "center_58_healed")], agent.called)

    def test_a_porta_do_centro_nao_e_mais_desvio(self):
        # Machucado do lado de fora segue a rota. Era aqui que nascia a viagem
        # de cura, e é ela que foi cancelada.
        agent = self.agent_in(2, self.HURT, doors={(13, 25): 58, (16, 17): 54})
        self.assertIsNone(self.step(agent))
        self.assertEqual([], agent.walked)

    def test_a_whole_party_walks_straight_past_it(self):
        agent = self.agent_in(2, self.WHOLE, doors={(13, 25): 58})
        self.assertIsNone(self.step(agent))
        self.assertEqual([], agent.walked)

    def test_o_hp_nao_decide_mais_nada_do_lado_de_fora(self):
        # Só o mapa decide: dentro entrega, fora devolve None — inteiro ou
        # machucado, tanto faz.
        for party in (self.HURT, self.WHOLE):
            self.assertIsNone(self.step(self.agent_in(2, party, doors={(13, 25): 58})))
            self.assertEqual("HEALING", self.step(self.agent_in(58, party)))

    def test_viridian_keeps_its_own_milestone_name(self):
        # `viridian_center_healed` is read outside this class as the story
        # milestone for the first Center.
        agent = self.agent_in(VIRIDIAN_CENTER_MAP_ID, self.HURT)
        self.step(agent)
        self.assertEqual(
            [("viridian-center", "viridian_center_healed")], agent.called
        )

    def test_a_city_without_a_center_door_is_left_to_the_executor(self):
        # A Center a city away is a trip, and trips still belong to the routes.
        agent = self.agent_in(14, self.HURT, doors={})
        self.assertIsNone(self.step(agent))
        self.assertEqual([], agent.called)

    def test_mt_moons_center_counts_as_a_center(self):
        # Map 68 sat outside the set while `_run_mt_moon_nav` talked to its
        # nurse in a branch of its own. The checkpoint writer refuses any map
        # not in the set, so the stretch right before the cave — the hardest
        # one reached so far — was the one with no resume point.
        agent = self.agent_in(68, self.HURT)
        self.assertEqual("HEALING", self.step(agent))
        self.assertEqual([("center-68", "center_68_healed")], agent.called)

    def test_a_rota_4_segue_para_a_caverna_e_nao_para_o_centro(self):
        agent = self.agent_in(15, self.HURT, doors={(11, 5): 68, (18, 5): 59})
        self.assertIsNone(self.step(agent))
        self.assertEqual([], agent.walked)

    def test_the_rule_covers_every_known_center(self):
        for map_id in POKEMON_CENTER_MAP_IDS:
            agent = self.agent_in(map_id, self.HURT)
            self.assertEqual("HEALING", self.step(agent), f"mapa {map_id}")


if __name__ == "__main__":
    unittest.main()
