"""Two trainers, two jobs: the guide proves the route, the follower reuses it."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pyboy.utils import WindowEvent

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.route_trails import TrailRecorder, TrailStore
from src.scripted_agent import ScriptedAgent
from src.warp_memory import WarpMemory

from tests.test_route_following import FakeMemory


class RouteRoleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def make_agent(self, position, role, map_id=51, blocked=None, quest="route_2_nav"):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.memory_probe = FakeMemory(position, map_id)
        agent.emulator = type("FakeEmulator", (), {"memory": agent.memory_probe})()
        agent._tile_truth = lambda: dict(blocked or {})
        agent._visible_step = lambda dx, dy: "U"
        agent.warp_memory = WarpMemory()
        agent.route_role = role
        agent.player_name = "AARON" if role == "guide" else "BARON"
        agent.current_task_name = quest
        agent.trail_store = TrailStore(self.directory.name)
        agent.trail_recorder = TrailRecorder()
        return agent

    def test_the_guide_also_walks_around_a_wall(self):
        # The guide once stopped at any wall, so that a wrong route would show
        # instead of being papered over. In practice it stopped: 11 tiles in
        # 400 steps in Viridian, then nothing. Walking is the job; the role is
        # now only about who writes the trail and who reads it.
        guide = self.make_agent((5, 5), "guide", blocked={"R": "terrain"})
        self.assertIsNotNone(guide._follow_route("r", [(9, 5)]))

    def test_the_follower_walks_around_the_same_wall(self):
        follower = self.make_agent((5, 5), "follower", blocked={"R": "terrain"})
        self.assertIsNotNone(follower._follow_route("r", [(9, 5)]))

    def test_the_guide_records_where_it_walked(self):
        guide = self.make_agent((5, 5), "guide")
        guide._follow_route("r", [(9, 5)])
        guide.memory_probe.position = (6, 5)
        guide._follow_route("r", [(9, 5)])
        self.assertEqual(
            guide.trail_recorder.legs(),
            [{"map": 51, "points": [[5, 5], [6, 5]]}],
        )

    def test_a_trail_is_published_only_once_the_quest_is_confirmed(self):
        guide = self.make_agent((5, 5), "guide")
        guide._follow_route("r", [(9, 5)])
        self.assertEqual(guide.trail_store.load("route_2_nav"), [])
        self.assertTrue(guide.publish_trail("route_2_nav"))
        self.assertTrue(guide.trail_store.load("route_2_nav"))

    def test_either_trainer_publishes_what_it_confirmed(self):
        # Both are looking for the way through now, so whoever finishes a quest
        # first writes it down and the other one joins.
        follower = self.make_agent((5, 5), "follower")
        follower.trail_recorder.record("route_2_nav", 51, 5, 5)
        self.assertTrue(follower.publish_trail("route_2_nav"))

    def test_a_trail_from_another_quest_is_never_published(self):
        follower = self.make_agent((5, 5), "follower")
        follower.trail_recorder.record("route_2_nav", 51, 5, 5)
        self.assertFalse(follower.publish_trail("viridian_forest_nav"))

    def test_publishing_reports_what_the_crossing_cost(self):
        guide = self.make_agent((5, 5), "guide")
        guide.trail_recorder.restart(2)
        for y in (5, 4, 3):
            guide.trail_recorder.record("route_2_nav", 51, 5, y)
        cost = guide.publish_trail("route_2_nav")
        self.assertEqual(cost["death_cycle"], 2)
        self.assertEqual(cost["steps"], 3)
        self.assertEqual(cost["maps"], [51])

    def test_the_walk_that_died_is_dropped_before_the_next_attempt(self):
        # Publishing the approach that lost together with the walk back from
        # the Center would teach the detour as the route.
        guide = self.make_agent((5, 5), "guide")
        guide.trail_recorder.record("route_2_nav", 51, 9, 9)
        self.assertEqual(guide.begin_death_cycle(1), 1)
        guide._follow_route("r", [(9, 5)])
        self.assertEqual(
            guide.trail_recorder.legs(), [{"map": 51, "points": [[5, 5]]}]
        )

    def test_a_death_drops_the_trail_the_bot_was_walking(self):
        # The plan in hand points into the attempt that just ended.
        guide = self.make_agent((5, 5), "guide")
        guide.trail_plan = (("route_2_nav", 51), [(5, 1)])
        guide.begin_death_cycle(1)
        self.assertIsNone(guide.trail_plan)

    def test_the_drawn_route_wins_over_a_published_trail(self):
        # The hand-drawn route is the path that finishes the game, so it is the
        # one that drives. A trail only has to be wrong once to cost an hour:
        # one mined point on Route 4 turned the sidestep axis vertical, and
        # south from that tile is Route 3.
        store = TrailStore(self.directory.name)
        store.publish(
            "route_2_nav", "AARON", [{"map": 51, "points": [[5, 5], [5, 1]]}]
        )
        follower = self.make_agent((5, 5), "follower")
        # The route says right; the trail says up. The route wins.
        self.assertEqual(
            WindowEvent.PRESS_ARROW_RIGHT, follower._follow_route("r", [(9, 5)])
        )

    def test_a_trail_is_still_recorded_while_the_route_drives(self):
        # Following is off; measuring what a crossing cost is not.
        follower = self.make_agent((5, 5), "follower")
        follower._follow_route("r", [(9, 5)])
        self.assertEqual(
            [{"map": 51, "points": [[5, 5]]}], follower.trail_recorder.legs()
        )

    def test_following_a_trail_is_opt_in(self):
        store = TrailStore(self.directory.name)
        store.publish(
            "route_2_nav", "AARON", [{"map": 51, "points": [[5, 5], [5, 1]]}]
        )
        follower = self.make_agent((5, 5), "follower")
        with mock.patch("src.scripted_agent.FOLLOW_TRAILS", True):
            self.assertEqual(
                WindowEvent.PRESS_ARROW_UP, follower._follow_route("r", [(9, 5)])
            )

    def test_the_other_trainer_joins_the_same_trail(self):
        store = TrailStore(self.directory.name)
        store.publish(
            "route_2_nav", "BARON", [{"map": 51, "points": [[5, 5], [5, 1]]}]
        )
        guide = self.make_agent((5, 5), "guide")
        with mock.patch("src.scripted_agent.FOLLOW_TRAILS", True):
            self.assertEqual(
                WindowEvent.PRESS_ARROW_UP, guide._follow_route("r", [(9, 5)])
            )

    def test_a_follower_thrown_backwards_rejoins_the_trail_behind_it(self):
        store = TrailStore(self.directory.name)
        store.publish(
            "route_2_nav",
            "AARON",
            [{"map": 51, "points": [[5, 20], [5, 10], [5, 1]]}],
        )
        follower = self.make_agent((5, 5), "follower")
        with mock.patch("src.scripted_agent.FOLLOW_TRAILS", True):
            follower._follow_route("r", [(9, 5)])
            # A whiteout drops it back at the start of the map: it must head
            # for the trail again, not keep aiming at where it used to be.
            follower.memory_probe.position = (5, 25)
            self.assertEqual(
                WindowEvent.PRESS_ARROW_UP, follower._follow_route("r", [(9, 5)])
            )




class PacingTests(unittest.TestCase):
    """The two-tile loop, and who is allowed to break it."""

    class WalkingMemory(FakeMemory):
        """A cartridge that actually moves when the D-pad is pressed."""

        def step(self, direction):
            x, y = self.position
            moves = {"R": (x + 1, y), "L": (x - 1, y), "D": (x, y + 1), "U": (x, y - 1)}
            self.position = moves.get(direction, (x, y))

    def make_agent(self, position, role, blocked):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.memory_probe = self.WalkingMemory(position, 51)
        agent.emulator = type("FakeEmulator", (), {"memory": agent.memory_probe})()
        agent._tile_truth = lambda: dict(blocked)
        agent._visible_step = lambda dx, dy: None
        agent.warp_memory = WarpMemory()
        agent.route_role = role
        agent.player_name = "AARON" if role == "guide" else "BARON"
        return agent

    def walk(self, agent, waypoints, steps=8):
        seen = []
        for _ in range(steps):
            action = agent._follow_route("forest-51", waypoints)
            seen.append(agent.memory_probe.position)
            for name, direction in (
                ("PRESS_ARROW_RIGHT", "R"), ("PRESS_ARROW_LEFT", "L"),
                ("PRESS_ARROW_DOWN", "D"), ("PRESS_ARROW_UP", "U"),
            ):
                if action == getattr(WindowEvent, name):
                    agent.memory_probe.step(direction)
        return seen

    def test_the_follower_stops_pacing_between_two_tiles(self):
        # The forest entrance: east is wall, so the detour goes south, and from
        # the south tile the route wants north again.
        follower = self.make_agent((17, 43), "follower", {"R": "terrain"})
        visited = self.walk(follower, [(26, 43)])
        self.assertGreater(
            len(set(visited)), 2, f"vaivém entre dois tiles: {visited}"
        )

    def test_the_guide_gets_the_same_treatment(self):
        # Pacing used to be left to the guide on purpose, as a visible report
        # that its route was wrong. It reported by standing in tall grass
        # taking encounters, which reads as farming, so both roles now get the
        # memory of where they have just been.
        guide = self.make_agent((17, 43), "guide", {"R": "terrain"})
        visited = self.walk(guide, [(26, 43)])
        self.assertGreater(
            len(set(visited)), 2, f"vaivém entre dois tiles: {visited}"
        )



class HealingNeedTests(unittest.TestCase):
    """Only a Center restores PP, so no damage left is a reason to walk back."""

    class PartyMemory:
        def __init__(self, mons):
            self.mons = mons

        def get_party_count(self):
            return len(self.mons)

        def get_player_pos(self):
            return (0, 0)

        def get_map_id(self):
            return 51

        def read_byte(self, address):
            index, offset = divmod(address - 0xD16B, 44)
            mon = self.mons[index]
            if offset == 1:
                return mon["hp"] >> 8
            if offset == 2:
                return mon["hp"] & 0xFF
            if offset == 34:
                return mon["max_hp"] >> 8
            if offset == 35:
                return mon["max_hp"] & 0xFF
            if 8 <= offset <= 11:
                moves = mon["moves"]
                slot = offset - 8
                return moves[slot][0] if slot < len(moves) else 0
            if 29 <= offset <= 32:
                moves = mon["moves"]
                slot = offset - 29
                return moves[slot][1] if slot < len(moves) else 0
            return 0

    def agent_with(self, mons):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        memory = self.PartyMemory(mons)
        agent.emulator = type("FakeEmulator", (), {"memory": memory})()
        return agent

    @staticmethod
    def mon(hp, max_hp, moves):
        return {"hp": hp, "max_hp": max_hp, "moves": moves}

    def test_a_team_pool_under_a_fifth_asks_for_a_center(self):
        agent = self.agent_with([self.mon(5, 30, [(33, 20)])])
        self.assertTrue(agent._party_needs_healing())

    def test_a_scratch_does_not(self):
        # 29/30 sent a trainer across the city, healed, took one hit on the way
        # out and turned around: the round trip never ended.
        agent = self.agent_with([self.mon(29, 30, [(33, 20)])])
        self.assertFalse(agent._party_needs_healing())

    def test_one_fainted_teammate_behind_a_healthy_lead_is_not_an_emergency(self):
        agent = self.agent_with([
            self.mon(30, 30, [(33, 20)]),
            self.mon(0, 16, [(33, 20)]),
        ])
        self.assertFalse(agent._party_needs_healing())

    def test_half_health_is_not_a_reason_to_walk_back(self):
        agent = self.agent_with([self.mon(15, 30, [(33, 20)])])
        self.assertFalse(agent._party_needs_healing())

    def test_full_health_with_an_attack_left_does_not(self):
        agent = self.agent_with([self.mon(30, 30, [(33, 5), (45, 40)])])
        self.assertFalse(agent._party_needs_healing())

    def test_full_health_with_only_status_moves_does_not(self):
        # PP availability is not a healing trigger. The operator's rule is HP
        # only, so a full team stays on the route even with status moves only.
        agent = self.agent_with([
            self.mon(30, 30, [(33, 0), (45, 40)]),
            self.mon(20, 20, [(106, 30)]),
        ])
        self.assertFalse(agent._party_needs_healing())

    def test_exactly_one_fifth_does_not_trigger(self):
        agent = self.agent_with([self.mon(6, 30, [(33, 20)])])
        self.assertFalse(agent._party_needs_healing())

    def test_below_one_fifth_triggers(self):
        agent = self.agent_with([self.mon(5, 30, [(33, 0)])])
        self.assertTrue(agent._party_needs_healing())

    def test_one_teammate_with_a_usable_attack_is_enough(self):
        agent = self.agent_with([
            self.mon(30, 30, [(33, 0), (45, 40)]),
            self.mon(20, 20, [(33, 12)]),
        ])
        self.assertFalse(agent._party_needs_healing())


if __name__ == "__main__":
    unittest.main()


class TopUpOnTheWayTests(unittest.TestCase):
    """A Center on the route is cheap; one reached after dying is not."""

    def agent_at(self, fraction):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent._party_health_fraction = lambda: fraction
        return agent

    def test_half_health_stops_at_the_center_in_viridian(self):
        # Entering the Forest at half health means dying in the middle of it
        # and walking the whole stretch again after the whiteout.
        self.assertTrue(self.agent_at(0.5)._should_top_up_before(1))

    def test_a_healthy_team_walks_past_it(self):
        self.assertFalse(self.agent_at(0.9)._should_top_up_before(1))

    def test_maps_without_a_center_on_the_way_never_detour(self):
        self.assertFalse(self.agent_at(0.3)._should_top_up_before(51))


class HealForwardTests(unittest.TestCase):
    """Hurt in the second half of a crossing, the Center ahead is the near one."""

    class ForestMemory:
        def __init__(self, map_id, pos, party):
            self.map_id = map_id
            self.pos = pos
            self.party = party

        def get_map_id(self): return self.map_id
        def get_player_pos(self): return self.pos
        def get_party_count(self): return len(self.party)

        def read_byte(self, address):
            index, offset = divmod(address - 0xD16B, 44)
            if 0 <= index < len(self.party):
                hp, max_hp = self.party[index]
                if offset == 1: return hp >> 8
                if offset == 2: return hp & 0xFF
                if offset == 34: return max_hp >> 8
                if offset == 35: return max_hp & 0xFF
                if 8 <= offset <= 11: return 33
                if 29 <= offset <= 32: return 20
            return 0

    def agent(self, map_id, pos, party=((5, 40),)):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        memory = self.ForestMemory(map_id, pos, list(party))
        agent.emulator = type("FakeEmulator", (), {"memory": memory})()
        agent.calls = []
        agent._follow_route = lambda route_id, waypoints: agent.calls.append(route_id)
        agent._run_pokemon_center = lambda *a: agent.calls.append("center")
        agent._run_route_2_nav = lambda: agent.calls.append("route_2_nav")
        agent._leave_unknown_map = lambda: agent.calls.append("leave")
        return agent

    def test_the_southern_half_walks_back_to_viridian(self):
        agent = self.agent(51, (16, 40))
        agent._run_viridian_forest_nav()
        self.assertEqual(["forest-back-to-gate"], agent.calls)

    def test_the_northern_half_keeps_going_to_pewter(self):
        # Walking back from here means crossing the whole Forest twice.
        agent = self.agent(51, (16, 10))
        agent._run_viridian_forest_nav()
        self.assertNotIn("forest-back-to-gate", agent.calls)

    def test_route_2_north_never_turns_around(self):
        agent = self.agent(13, (8, 6))
        agent._run_viridian_forest_nav()
        self.assertNotIn("route2-back-to-viridian", agent.calls)
