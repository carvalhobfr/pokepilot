"""Insígnia na RAM manda mais que bola na mochila.

A história é linear e o nó ativo é o primeiro incompleto — o que funcionava até
um predicado de **recurso** aparecer no meio. `buy_pokeballs` pede oito Poké
Bolas, e quem gastou as suas volta a falhar ali. Um save com a insígnia da
Misty era mandado comprar bolas em Viridian, e o executor daquele nó só conhece
o caminho até o Mart de Viridian: da Rota 4 ele não tem rota nenhuma e fica
indo e voltando na mesma casa.
"""

import sys
import unittest
from pathlib import Path

AGENTS_ROOT = str(Path(__file__).resolve().parents[1])
if AGENTS_ROOT not in sys.path:
    sys.path.append(AGENTS_ROOT)

from quest_graph import MONOTONIC_PREDICATES, QuestGraph, QuestNode

BOULDER, CASCADE = 0, 1


def graph():
    """Um recorte com a mesma forma do grafo real: recurso no meio."""
    return QuestGraph([
        QuestNode("start", "Sair de casa", "start",
                  ({"type": "event_flag", "address": 0xD747, "bit": 0},)),
        QuestNode("buy_pokeballs", "Estocar bolas", "buy_pokeballs",
                  ({"type": "pokeballs_stocked", "minimum": 8},)),
        QuestNode("route_2_nav", "Chegar à Floresta", "route_2_nav",
                  ({"type": "map_in", "values": [51]},)),
        QuestNode("brock_quest", "Vencer Brock", "brock_quest",
                  ({"type": "badge", "index": BOULDER},)),
        QuestNode("mt_moon_nav", "Atravessar Mt. Moon", "mt_moon_nav",
                  ({"type": "map_in", "values": [59]},)),
        QuestNode("cerulean_gym_quest", "Vencer Misty", "cerulean_gym_quest",
                  ({"type": "badge", "index": CASCADE},)),
        QuestNode("vermilion_gym_quest", "Vencer Surge", "vermilion_gym_quest",
                  ({"type": "badge", "index": 2},)),
    ])


class Estado:
    def __init__(self, badges=0, map_id=0, pokeballs=0, money=3000, flags=()):
        self.badges_mask = badges
        self.badge_count = bin(badges).count("1")
        self.map_id = map_id
        self.pokeballs = pokeballs
        self.money = money
        self.can_afford_pokeball = money >= 200
        self.flags = set(flags)

    def event_flag(self, address, bit):
        return (int(address), int(bit)) in self.flags


class PisoDeFeitoTests(unittest.TestCase):
    def setUp(self):
        self.g = graph()

    def test_sem_nada_o_primeiro_no_e_o_ativo(self):
        self.assertEqual("start", self.g.active_node(Estado()).id)

    def test_uma_insignia_pula_o_no_de_recurso(self):
        # Era aqui que BARON, com a insígnia do Brock e sem bolas, era mandado
        # de volta a Viridian.
        estado = Estado(badges=1 << BOULDER, map_id=15, pokeballs=0)
        self.assertEqual("mt_moon_nav", self.g.active_node(estado).id)

    def test_duas_insignias_vao_para_o_ginasio_seguinte(self):
        estado = Estado(badges=(1 << BOULDER) | (1 << CASCADE), map_id=65)
        self.assertEqual("vermilion_gym_quest", self.g.active_node(estado).id)

    def test_o_piso_marca_tudo_atras_como_concluido(self):
        estado = Estado(badges=1 << BOULDER, map_id=15)
        completas = self.g.completed_nodes(estado)
        self.assertIn("buy_pokeballs", completas)
        self.assertIn("brock_quest", completas)
        self.assertNotIn("mt_moon_nav", completas)

    def test_sem_insignia_o_recurso_ainda_manda(self):
        # O piso não pode atropelar a fase inicial: sem feito nenhum
        # confirmado, comprar bolas continua sendo a tarefa.
        estado = Estado(flags=[(0xD747, 0)], pokeballs=0)
        self.assertEqual("buy_pokeballs", self.g.active_node(estado).id)

    def test_bolas_no_bolso_seguem_valendo(self):
        estado = Estado(flags=[(0xD747, 0)], pokeballs=8)
        self.assertEqual("route_2_nav", self.g.active_node(estado).id)

    def test_bag_item_nao_e_monotonico(self):
        # O Bilhete do S.S. Anne some da mochila quando é usado, então não pode
        # servir de piso.
        self.assertNotIn("bag_item", MONOTONIC_PREDICATES)
        self.assertEqual({"badge", "badge_count", "event_flag"}, MONOTONIC_PREDICATES)

    def test_map_in_nunca_vira_piso(self):
        # Estar num mapa é transitório; sozinho não prova nada do passado.
        estado = Estado(map_id=59)
        self.assertEqual("start", self.g.active_node(estado).id)


if __name__ == "__main__":
    unittest.main()
