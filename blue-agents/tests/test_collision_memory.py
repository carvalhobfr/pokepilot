import json
import sys
import tempfile
from pathlib import Path
import unittest

from pyboy.utils import WindowEvent

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.collision_memory import CollisionMemory
from src.scripted_agent import ScriptedAgent


class FakeWorldMemory:
    """A tiny walkable grid, so a route can be executed step by step."""

    def __init__(self, position, map_id=51, walls=()):
        self.position = tuple(position)
        self.map_id = map_id
        self.walls = set(walls)

    def get_player_pos(self):
        return self.position

    def get_map_id(self):
        return self.map_id

    def read_byte(self, _address):
        return 0

    def walk(self, dx, dy):
        candidate = (self.position[0] + dx, self.position[1] + dy)
        if candidate in self.walls:
            return
        self.position = candidate


class CollisionMemoryTests(unittest.TestCase):
    def test_unknown_edges_are_free_so_the_first_plan_is_the_straight_line(self):
        memory = CollisionMemory()
        self.assertEqual(["R", "R"], memory.find_path(51, (15, 47), (17, 47)))

    def test_blocked_edges_are_planned_around(self):
        memory = CollisionMemory()
        memory.mark_blocked(51, 15, 47, "R")
        path = memory.find_path(51, (15, 47), (17, 47))
        self.assertEqual("U", path[0], "com R bloqueado o desvio sobe")
        self.assertEqual(4, len(path))

    def test_a_tile_is_never_sealed_on_all_four_sides(self):
        # The bot is standing there, so it walked in through one of the sides.
        # Believing a sealed tile is fatal: the search finds no path, and a
        # blocked edge is only forgotten by crossing it, which is exactly what
        # became impossible. Oak's lab sealed itself like this, in shared
        # knowledge, and stranded four trainers at once.
        memory = CollisionMemory()
        for direction in ("U", "R", "L"):
            self.assertTrue(memory.mark_blocked(40, 8, 4, direction))
        self.assertFalse(memory.mark_blocked(40, 8, 4, "D"))
        self.assertFalse(memory.is_blocked(40, 8, 4, "D"))
        self.assertIsNotNone(memory.find_path(40, (8, 4), (8, 6)))

    def test_a_file_written_before_the_rule_is_repaired_on_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collision.json"
            path.write_text(json.dumps({"version": 1, "blocked": {
                "40": ["8,4,U", "8,4,D", "8,4,L", "8,4,R", "9,4,R"],
            }}))
            memory = CollisionMemory(path)
            self.assertEqual(set(), {
                edge for edge in memory.blocked if edge[1:3] == (8, 4)
            })
            self.assertTrue(memory.is_blocked(40, 9, 4, "R"), "o resto continua")

    def test_a_walled_corridor_still_finds_the_way_around(self):
        memory = CollisionMemory()
        for y in range(0, 10):
            memory.mark_blocked(51, 5, y, "R")
        path = memory.find_path(51, (5, 5), (7, 5))
        self.assertIsNotNone(path)
        self.assertNotIn((5, 5, "R"), [(5, 5, step) for step in path[:1]])

    def test_goal_enclosed_by_walls_reports_no_path(self):
        memory = CollisionMemory()
        for direction, tile in (
            ("L", (11, 10)), ("R", (9, 10)), ("D", (10, 9)), ("U", (10, 11)),
        ):
            memory.mark_blocked(51, tile[0], tile[1], direction)
        self.assertIsNone(memory.find_path(51, (5, 5), (10, 10)))

    def test_marking_open_forgets_a_wall_that_was_an_npc(self):
        memory = CollisionMemory()
        memory.mark_blocked(51, 6, 30, "R")
        self.assertTrue(memory.is_blocked(51, 6, 30, "R"))
        memory.mark_open(51, 6, 30, "R")
        self.assertFalse(memory.is_blocked(51, 6, 30, "R"))

    def test_memory_survives_a_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collision.json"
            first = CollisionMemory(path)
            first.mark_blocked(51, 6, 30, "R")
            first.mark_blocked(2, 1, 2, "U")
            reloaded = CollisionMemory(path)
            self.assertTrue(reloaded.is_blocked(51, 6, 30, "R"))
            self.assertTrue(reloaded.is_blocked(2, 1, 2, "U"))
            self.assertFalse(reloaded.is_blocked(51, 6, 30, "L"))

    def test_a_corrupt_file_is_ignored_instead_of_crashing_the_journey(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collision.json"
            path.write_text("{not json")
            self.assertEqual(set(), CollisionMemory(path).blocked)


class LedgeWorldMemory(FakeWorldMemory):
    """Route 3 style ledge: walking down the ledge row jumps two tiles."""

    def __init__(self, position, map_id=14, ledges=()):
        super().__init__(position, map_id)
        self.ledges = set(ledges)

    def walk(self, dx, dy):
        if dy == 1 and self.position in self.ledges:
            self.position = (self.position[0], self.position[1] + 2)
            return
        super().walk(dx, dy)


class RouteReplanningTests(unittest.TestCase):
    def make_agent(self, position, map_id=51, walls=(), memory_path=None):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.memory_probe = FakeWorldMemory(position, map_id, walls)
        agent.emulator = type("FakeEmulator", (), {"memory": agent.memory_probe})()
        # Never touch the shared knowledge file from a test: it would both read
        # real learned walls into the assertions and write test junk back.
        agent.collision_memory = CollisionMemory(memory_path)
        return agent

    def drive(self, agent, route_id, waypoints, steps):
        """Run the controller against the fake world, applying each press."""
        deltas = {
            WindowEvent.PRESS_ARROW_UP: (0, -1),
            WindowEvent.PRESS_ARROW_DOWN: (0, 1),
            WindowEvent.PRESS_ARROW_LEFT: (-1, 0),
            WindowEvent.PRESS_ARROW_RIGHT: (1, 0),
        }
        for _ in range(steps):
            action = agent._follow_route(route_id, waypoints)
            if action in deltas:
                agent.memory_probe.walk(*deltas[action])
        return agent.memory_probe.position

    def test_a_wall_across_the_straight_line_is_learned_and_walked_around(self):
        # A vertical wall between x=6 and x=7 with one gap at y=33. Straight
        # line navigation dies at (6,30) — exactly where BARON and CARON were
        # stuck in Viridian Forest.
        walls = {(7, y) for y in range(25, 40) if y != 33}
        agent = self.make_agent((6, 30), walls=walls)
        final = self.drive(agent, "forest-51", [(10, 30)], 220)
        self.assertEqual((10, 30), final, "o bot precisa contornar o muro")
        self.assertTrue(
            agent._collision_memory().is_blocked(51, 6, 30, "R"),
            "a colisão observada precisa ser aprendida",
        )

    def test_learned_walls_are_persisted_and_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            walls = {(7, y) for y in range(25, 40) if y != 33}
            path = Path(directory) / "collision.json"
            agent = self.make_agent((6, 30), walls=walls, memory_path=path)
            self.drive(agent, "forest-51", [(10, 30)], 220)
            self.assertTrue(path.exists())
            # A second trainer opening the same file starts with the wall
            # already known instead of walking into it again.
            other = CollisionMemory(path)
            self.assertTrue(other.is_blocked(51, 6, 30, "R"))
            other.mark_blocked(51, 1, 1, "U")
            self.assertTrue(
                CollisionMemory(path).is_blocked(51, 6, 30, "R"),
                "a escrita de um treinador não pode apagar o que o outro aprendeu",
            )

    def test_leaving_the_line_is_no_longer_a_dead_end(self):
        # Off-route to the north-west of the anchor, the old controller kept
        # aiming at the same waypoint forever. The search replans from here.
        agent = self.make_agent((7, 30))
        final = self.drive(agent, "forest-51", [(17, 43)], 400)
        self.assertEqual((17, 43), final)

    def test_the_plan_is_followed_instead_of_pacing_between_two_free_tiles(self):
        # Half-known wall: only the tile straight ahead is known blocked, so the
        # detour north and the detour south cost the same. Recomputing every
        # step flipped between them and the bot paced without ever colliding —
        # therefore without ever learning. The kept plan commits to one side.
        walls = {(11, y) for y in range(28, 36)}
        agent = self.make_agent((10, 32), walls=walls)
        agent._collision_memory().mark_blocked(51, 10, 32, "R")
        visited = set()
        for _ in range(80):
            action = agent._follow_route("forest-51", [(10, 22)])
            deltas = {
                WindowEvent.PRESS_ARROW_UP: (0, -1),
                WindowEvent.PRESS_ARROW_DOWN: (0, 1),
                WindowEvent.PRESS_ARROW_LEFT: (-1, 0),
                WindowEvent.PRESS_ARROW_RIGHT: (1, 0),
            }
            if action in deltas:
                agent.memory_probe.walk(*deltas[action])
            visited.add(agent.memory_probe.position)
        self.assertEqual((10, 22), agent.memory_probe.position)
        self.assertNotIn(
            (10, 33), visited, "o plano não deve oscilar para trás do objetivo"
        )

    def test_a_map_with_no_route_is_left_through_the_door_it_was_entered_by(self):
        # Wandering into an interior used to be terminal: with no route for
        # that map the executor pressed A forever, and both bots sat inside the
        # Mt. Moon trader's house until someone noticed.
        agent = self.make_agent((4, 4), map_id=59)
        agent.route_id = "mt-moon-59"
        agent.route_index = 0
        agent.route_stuck_steps = 0
        agent.route_last_position = (59, 4, 4)
        agent.route_last_direction = "U"
        agent.route_target_was_final = False
        agent.memory_probe.map_id = 63
        agent.memory_probe.position = (2, 7)
        agent._follow_route("mt-moon-59", [(4, 2), (9, 2)])

        # Standing on the door tile, the way out is the opposite of the step
        # that walked in.
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent._leave_unknown_map())

        # One tile away from it, walk back to the door first.
        agent.memory_probe.position = (2, 5)
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent._leave_unknown_map())
        agent.memory_probe.position = (5, 7)
        self.assertEqual(WindowEvent.PRESS_ARROW_LEFT, agent._leave_unknown_map())

    def test_an_unseen_interior_still_tries_the_south_door(self):
        # A resumed save or a whiteout warp never showed the transition. House
        # doors are on the south edge, so down is the best blind guess — and
        # anything beats pressing A forever.
        agent = self.make_agent((3, 4), map_id=63)
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent._leave_unknown_map())

    def test_a_ledge_jump_is_learned_because_it_is_not_a_single_step(self):
        agent = self.make_agent((10, 8))
        agent.memory_probe = LedgeWorldMemory((10, 8), ledges={(10, 8)})
        agent.emulator.memory = agent.memory_probe
        agent._follow_route("route3-14", [(10, 9)])
        agent.memory_probe.walk(0, 1)
        agent._follow_route("route3-14", [(10, 9)])
        self.assertEqual((10, 10), agent.memory_probe.position)
        self.assertTrue(
            agent._collision_memory().is_blocked(14, 10, 8, "D"),
            "um salto de duas casas não é um passo que o planejador possa usar",
        )

    def test_a_stuck_menu_flag_does_not_freeze_the_route_forever(self):
        # On Route 2 north a bot sat on (3,11) for hundreds of steps pressing A
        # while the probe showed the tile above was walkable: 0xCFC4 stayed at 1
        # and nothing cleared it. Obeying it forever is a livelock, and the bot
        # never even tries to walk, so it also learns nothing.
        agent = self.make_agent((3, 11), map_id=13)
        agent.memory_probe.read_byte = lambda address: 1 if address == 0xCFC4 else 0
        actions = [agent._follow_route("mt-moon-recovery-13", [(3, 8)]) for _ in range(40)]
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, actions[0])
        self.assertIn(WindowEvent.PRESS_ARROW_UP, actions)

    def test_dialogue_is_never_recorded_as_a_wall(self):
        # Text that does not clear looks exactly like a wall from the outside:
        # the position stops changing either way. Attributing it to the last
        # direction walled in the starter table at Oak's lab.
        agent = self.make_agent((8, 4), map_id=40)
        agent.memory_probe.read_byte = lambda address: 1 if address == 0xCFC4 else 0
        for _ in range(200):
            agent._follow_route("oak-rival-trigger", [(7, 5), (5, 5)])
        self.assertEqual(
            set(), {edge for edge in agent._collision_memory().blocked if edge[0] == 40},
            "nenhuma parede pode nascer de uma caixa de texto",
        )
        self.assertTrue(
            agent.route_suspect,
            "a suspeita existe, mas fica só nesta rota e não vira conhecimento",
        )

    def test_a_defeated_trainer_reopening_its_line_never_freezes_the_route(self):
        # A beaten Route 3 trainer stays on its tile and its line reopens on
        # every A, so the menu flag says "text" forever. The pair once froze
        # thousands of steps in front of someone they had already beaten.
        #
        # It must get around — and it must not write that around into shared
        # knowledge, because the same signal is what a text box produces.
        agent = self.make_agent((14, 9), map_id=14, walls={(13, 9)})
        agent.memory_probe.read_byte = lambda address: 1 if address == 0xCFC4 else 0
        moved = self.drive(agent, "mt-moon-14", [(11, 9)], 200)
        self.assertNotEqual((14, 9), moved, "não pode congelar diante do NPC")
        self.assertEqual(
            set(), agent._collision_memory().blocked,
            "sinal ambíguo não vira conhecimento compartilhado",
        )

    def test_an_unintended_warp_is_learned_like_a_wall(self):
        # Leaving Brock's gym lands the bot on the Pewter door tile. The plan to
        # the next anchor crossed that same tile, warped back in, and the pair
        # bounced gym → city → gym forever. Stepping onto a warp succeeds, so
        # only the map change itself can reveal it.
        agent = self.make_agent((16, 18), map_id=2)
        agent.route_id = "mt-moon-2-gym"
        agent.route_index = 1
        agent.route_stuck_steps = 0
        agent.route_last_position = (2, 16, 18)
        agent.route_last_direction = "U"
        agent.route_target_was_final = False
        agent.memory_probe.map_id = 54
        agent.memory_probe.position = (4, 13)
        agent._follow_route("mt-moon-2-gym", [(16, 18), (10, 18), (10, 13)])
        self.assertTrue(
            agent._collision_memory().is_blocked(2, 16, 18, "U"),
            "a porta atravessada sem querer precisa virar aresta bloqueada",
        )

    def test_the_warp_that_ends_a_route_stays_free(self):
        # Routes deliberately end on a warp: the last waypoint is often one tile
        # past the map border. Learning those would seal every exit.
        agent = self.make_agent((1, 0), map_id=51)
        agent.route_id = "forest-51"
        agent.route_index = 1
        agent.route_stuck_steps = 0
        agent.route_last_position = (51, 1, 0)
        agent.route_last_direction = "U"
        agent.route_target_was_final = True
        agent.memory_probe.map_id = 13
        agent.memory_probe.position = (3, 11)
        agent._follow_route("forest-13", [(3, 11), (3, 8)])
        self.assertFalse(agent._collision_memory().is_blocked(51, 1, 0, "U"))

    def test_a_wall_that_was_an_npc_is_forgotten_after_it_is_crossed(self):
        agent = self.make_agent((5, 5))
        agent._collision_memory().mark_blocked(51, 5, 5, "R")
        # Mid-route: the walk that proves the tile free is the previous step.
        agent.route_id = "npc-51"
        agent.route_index = 0
        agent.route_stuck_steps = 0
        agent.route_last_position = (51, 5, 5)
        agent.route_last_direction = "R"
        agent.memory_probe.position = (6, 5)
        agent._follow_route("npc-51", [(9, 5)])
        self.assertFalse(agent._collision_memory().is_blocked(51, 5, 5, "R"))


if __name__ == "__main__":
    unittest.main()
