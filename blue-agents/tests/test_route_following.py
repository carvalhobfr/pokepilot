import sys
import unittest
from pathlib import Path

from pyboy.utils import WindowEvent

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.scripted_agent import ScriptedAgent
from src.warp_memory import WarpMemory


class FakeMemory:
    def __init__(self, position, map_id=51):
        self.position = tuple(position)
        self.map_id = map_id
        self.menu = 0

    def get_player_pos(self):
        return self.position

    def get_map_id(self):
        return self.map_id

    def read_byte(self, address):
        return self.menu if address == 0xCFC4 else 0


class RouteFollowingTests(unittest.TestCase):
    """The route reads the cartridge instead of guessing.

    Before this, a wall was learned from a failed step — which meant a person
    standing still became geometry, forever, in knowledge every trainer shared.
    Four bots lost a day to that. Now terrain and people are read directly, and
    the route is only a step chooser.
    """

    def make_agent(self, position, map_id=51, blocked=None):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.memory_probe = FakeMemory(position, map_id)
        agent.emulator = type("FakeEmulator", (), {"memory": agent.memory_probe})()
        agent._tile_truth = lambda: dict(blocked or {})
        agent.warp_memory = WarpMemory()
        return agent

    def test_it_walks_toward_the_waypoint(self):
        agent = self.make_agent((5, 5))
        self.assertEqual(
            WindowEvent.PRESS_ARROW_RIGHT, agent._follow_route("r", [(9, 5)])
        )

    def test_the_longer_axis_is_taken_first(self):
        agent = self.make_agent((5, 5))
        self.assertEqual(
            WindowEvent.PRESS_ARROW_DOWN, agent._follow_route("r", [(6, 12)])
        )

    def test_a_wall_ahead_sends_it_along_the_other_axis(self):
        agent = self.make_agent((5, 5), blocked={"R": "terrain"})
        self.assertEqual(
            WindowEvent.PRESS_ARROW_DOWN, agent._follow_route("r", [(9, 7)])
        )

    def test_a_person_ahead_is_waited_out_before_walking_around(self):
        # People pace on their own, so a moment of patience beats a detour —
        # and a wall never moves, so the patience has to run out.
        agent = self.make_agent((5, 5), blocked={"R": "sprite"})
        first = [agent._follow_route("r", [(9, 5)]) for _ in range(4)]
        self.assertEqual([None] * 4, first, "espera a pessoa andar")
        later = [agent._follow_route("r", [(9, 5)]) for _ in range(8)]
        self.assertTrue(
            any(action is not None for action in later),
            "mas não espera para sempre",
        )

    def test_a_wall_is_never_waited_out(self):
        agent = self.make_agent((5, 5), blocked={"R": "terrain"})
        self.assertIsNotNone(
            agent._follow_route("r", [(9, 5)]), "parede não vai sair do lugar"
        )

    def test_a_resumed_route_starts_at_the_closest_waypoint(self):
        agent = self.make_agent((16, 4))
        action = agent._follow_route("mt-moon", [(21, 17), (12, 4), (3, 4)])
        self.assertEqual(WindowEvent.PRESS_ARROW_LEFT, action)

    def test_a_menu_is_closed_before_walking(self):
        agent = self.make_agent((5, 5))
        agent.memory_probe.menu = 1
        actions = [agent._follow_route("r", [(9, 5)]) for _ in range(4)]
        self.assertIn(WindowEvent.PRESS_BUTTON_B, actions, "B fecha menu")
        self.assertIn(WindowEvent.PRESS_BUTTON_A, actions, "A confirma aviso")

    def test_the_last_waypoint_past_the_border_keeps_the_heading(self):
        agent = self.make_agent((1, 0))
        self.assertEqual(
            WindowEvent.PRESS_ARROW_UP, agent._follow_route("f", [(1, 5), (1, -1)])
        )

    def test_a_ledge_jump_crosses_the_wall_tile_in_front(self):
        # (79,8)->(79,10) da Rota 4: descer por um penhasco pula o tile do
        # meio (79,9), que o planejador trata como parede. Medido no cartucho:
        # D de (79,8) pousa em (79,10). Apertar numa parede comum não move
        # nada, então tentar é de graça.
        agent = self.make_agent((79, 8), map_id=15, blocked={"D": "terrain"})
        self.assertEqual(
            WindowEvent.PRESS_ARROW_DOWN,
            agent._follow_route("mt-moon-to-cerulean", [(79, 10)]),
        )

    def test_a_wall_two_ahead_does_not_become_a_jump(self):
        # Alvo alinhado a dois tiles mas com o pouso bloqueado não é penhasco:
        # o bot desvia pelo outro eixo em vez de apertar na parede.
        agent = self.make_agent((5, 5), map_id=51, blocked={"R": "terrain"})
        self.assertEqual(
            WindowEvent.PRESS_ARROW_DOWN,
            agent._follow_route("f", [(7, 7)]),
            "desce pelo outro eixo; (7,5) bloqueado não é pulo",
        )

    def test_a_sprite_blocking_the_way_is_faced_then_talked_to(self):
        # Medido em Mt. Moon: o bot ficou 1000+ passos ao lado do mesmo
        # treinador porque o fallback só virava o personagem — D-pad sozinho
        # nunca abre diálogo em Gen I. Treinador responde com batalha, fóssil
        # com pickup; os dois somem do tile e a rota segue.
        agent = self.make_agent((13, 8), map_id=61, blocked={"L": "sprite"})
        self.assertEqual(
            WindowEvent.PRESS_ARROW_LEFT,
            agent._follow_route("mt-moon-61", [(3, 4)]),
            "vira para o sprite que fecha a passagem",
        )
        self.assertEqual(
            WindowEvent.PRESS_BUTTON_A,
            agent._follow_route("mt-moon-61", [(3, 4)]),
            "e aperta A: diálogo, batalha ou pickup",
        )

    def test_the_talk_ends_when_the_sprite_leaves(self):
        agent = self.make_agent((13, 8), map_id=61, blocked={"L": "sprite"})
        agent._follow_route("mt-moon-61", [(3, 4)])
        agent._follow_route("mt-moon-61", [(3, 4)])
        agent._tile_truth = lambda: {"L": "terrain"}
        action = agent._follow_route("mt-moon-61", [(3, 4)])
        self.assertIsNotNone(action, "sprite removido (luta/pickup): a rota volta")
        self.assertNotEqual(WindowEvent.PRESS_BUTTON_A, action)

    def test_the_talk_gives_up_after_the_dialog_limit(self):
        agent = self.make_agent((13, 8), map_id=61, blocked={"L": "sprite"})
        for _ in range(13):
            agent._follow_route("mt-moon-61", [(3, 4)])
        action = agent._follow_route("mt-moon-61", [(3, 4)])
        self.assertEqual(
            WindowEvent.PRESS_BUTTON_B, action,
            "diálogo que não remove o sprite: B fecha e o desvio assume",
        )
        # O desvio pode andar agora: a máquina foi desligada.
        agent._tile_truth = lambda: {}
        self.assertIsNotNone(agent._follow_route("mt-moon-61", [(3, 4)]))

    def test_a_defeated_trainer_ghost_is_not_talked_to_again(self):
        # Treinador derrotado em Gen I fica no tile para sempre, visível e
        # bloqueando, com o texto pós-batalha (medido: o Youngster de Mt. Moon
        # em (12,16)). Conversar de novo não resolve nada — depois do limite,
        # o tile entra em `route_sprites_tried` e o desvio assume.
        agent = self.make_agent((13, 8), map_id=61, blocked={"L": "sprite"})
        for _ in range(14):
            agent._follow_route("mt-moon-61", [(3, 4)])
        self.assertIn((61, 12, 8), agent.route_sprites_tried)
        action = agent._follow_route("mt-moon-61", [(3, 4)])
        self.assertNotEqual(
            WindowEvent.PRESS_ARROW_LEFT, action,
            "não vira de novo para o ghost: o desvio assume",
        )
        self.assertNotEqual(WindowEvent.PRESS_BUTTON_A, action)

    def test_a_sprite_adjacent_but_off_axis_triggers_after_no_progress(self):
        # O fóssil (12,6) do B2F fica à direita de quem chega pelo bolsão oeste
        # com o alvo a oeste — fora do eixo do waypoint. Sem esta regra, o bot
        # paceia entre (10,6) e (11,6) para sempre, sem nunca apertar A.
        agent = self.make_agent((11, 6), map_id=61, blocked={"R": "sprite"})
        agent.route_progress_key = (61, 3, 4)
        agent.route_best_distance = 9
        agent.route_no_progress = 7
        action = agent._follow_route("mt-moon-61", [(3, 4)])
        self.assertEqual(
            WindowEvent.PRESS_ARROW_RIGHT, action,
            "sem progresso e sprite ao lado: vira e interage",
        )

    def test_o_destino_dinamico_e_resolvido_ao_atravessar(self):
        # Onde há porta é fato de ROM. O que andar acrescenta é para onde vai
        # um warp que o cartucho marca como dinâmico.
        agent = self.make_agent((3, 11), map_id=13)
        agent.warp_memory.doors["13"] = {"3,11": -1}
        agent._follow_route("f", [(3, 8)])
        agent.memory_probe.map_id = 47
        agent.memory_probe.position = (4, 7)
        agent._follow_route("f", [(4, 1)])
        self.assertEqual((3, 11), agent.warp_memory.door_to(13, 47))

    def test_chao_comum_nunca_vira_porta(self):
        # A regra antiga gravava o tile onde o bot estava quando o mapa mudava.
        # Num apagão isso inventa uma porta no meio do chão: Mt. Moon 1F juntou
        # 62, das quais o cartucho reconhece 5.
        agent = self.make_agent((3, 11), map_id=13)
        agent.warp_memory.doors["13"] = {}
        agent._follow_route("f", [(3, 8)])
        agent.memory_probe.map_id = 47
        agent.memory_probe.position = (4, 7)
        agent._follow_route("f", [(4, 1)])
        self.assertEqual({}, agent.warp_memory.doors_from(13))

    def test_viridian_resume_approaches_the_old_man_before_heading_north(self):
        agent = self.make_agent((17, 3), map_id=1)
        self.assertEqual(
            WindowEvent.PRESS_ARROW_DOWN,
            agent._run_route_2_nav(),
        )

    def test_viridian_old_man_dialog_is_confirmed_before_exit(self):
        agent = self.make_agent((17, 4), map_id=1)
        live_blocked = {"D": "sprite"}
        agent._tile_truth = lambda: dict(live_blocked)

        # Face the live sprite, open its text, then confirm until the cartridge
        # reports the text closed and the blocker is no longer in front.
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent._run_route_2_nav())
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._run_route_2_nav())
        agent.memory_probe.menu = 1
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._run_route_2_nav())
        agent.memory_probe.menu = 0
        live_blocked.clear()
        self.assertEqual(WindowEvent.PRESS_ARROW_UP, agent._run_route_2_nav())


if __name__ == "__main__":
    unittest.main()


class TudoFechadoPorGenteTests(unittest.TestCase):
    """Com as quatro direções fechadas, falar com quem está na frente.

    AARON ficou preso em (5,1) no lab do Oak: paredes acima e à direita, o Oak
    abaixo e alguém à esquerda. As quatro entravam em `blocked`, o último
    recurso não achava nenhuma livre e devolvia None — o bot não apertava nada,
    39 passos sem progresso e sem sair.
    """

    def agente(self, bloqueado, alvo=(4, 1), pos=(5, 1)):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.route_progress = {}
        memoria = type("M", (), {
            "get_map_id": staticmethod(lambda: 40),
            "get_player_pos": staticmethod(lambda: pos),
            "read_byte": staticmethod(lambda a: 0),
        })()
        agent.emulator = type("E", (), {"memory": memoria})()
        agent._tile_truth = lambda: dict(bloqueado)
        agent._menu_is_open = lambda: False
        agent._map_memory = lambda: None
        agent._planned_step = lambda *a: None
        agent._visible_step = lambda dx, dy: None
        agent._recently_walked_steps = lambda *a: set()
        agent._warp_steps = lambda *a: {}
        agent._tile_reader = lambda: None
        agent._report_if_stuck = lambda *a, **k: None
        agent.movido = []
        agent._route_move = lambda step: agent.movido.append(step) or step
        agent.alvo = alvo
        return agent

    def test_anda_contra_o_sprite_em_vez_de_parar(self):
        agent = self.agente({"U": "terrain", "R": "terrain",
                             "D": "sprite", "L": "bumped"})
        passo = agent._follow_route("lab", [agent.alvo])
        self.assertEqual("D", passo, "vira para o Oak e abre a fala dele")

    def test_parede_de_verdade_nao_vira_alvo_de_conversa(self):
        # Sem sprite nenhum, continua devolvendo None — não há com quem falar.
        agent = self.agente({"U": "terrain", "R": "terrain",
                             "D": "terrain", "L": "terrain"})
        self.assertIsNone(agent._follow_route("lab", [agent.alvo]))

    def test_direcao_livre_sempre_ganha_do_sprite(self):
        agent = self.agente({"U": "terrain", "R": "terrain", "D": "sprite"})
        passo = agent._follow_route("lab", [agent.alvo])
        self.assertEqual("L", passo, "andar para o alvo vem antes de falar")
