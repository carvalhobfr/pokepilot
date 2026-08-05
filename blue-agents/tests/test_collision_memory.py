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


class RouteReplanningTests(unittest.TestCase):
    def make_agent(self, position, map_id=51, walls=()):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.memory_probe = FakeWorldMemory(position, map_id, walls)
        agent.emulator = type("FakeEmulator", (), {"memory": agent.memory_probe})()
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

    def test_learned_walls_persist_for_the_trainer(self):
        with tempfile.TemporaryDirectory() as directory:
            walls = {(7, y) for y in range(25, 40) if y != 33}
            agent = self.make_agent((6, 30), walls=walls)
            agent.save_dir = directory
            self.drive(agent, "forest-51", [(10, 30)], 220)
            self.assertTrue((Path(directory) / "collision.json").exists())
            reloaded = CollisionMemory(Path(directory) / "collision.json")
            self.assertTrue(reloaded.is_blocked(51, 6, 30, "R"))

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
