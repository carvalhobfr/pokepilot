"""Trails: what the guide proved, and how the follower joins it."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.route_trails import TrailRecorder, TrailStore, waypoints_from


class TrailRecorderTests(unittest.TestCase):
    def test_legs_split_by_map_and_keep_every_tile_walked(self):
        # A trail is worth having because it knows the whole way. Turning
        # points alone are anchors, and anchors are what the follower already
        # had to guess between.
        recorder = TrailRecorder()
        for x, y in [(5, 3), (5, 4), (5, 5), (6, 5), (7, 5)]:
            recorder.record("parcel_event", 40, x, y)
        recorder.record("parcel_event", 0, 5, 11)
        recorder.record("parcel_event", 0, 5, 12)

        self.assertEqual(
            recorder.legs(),
            [
                {"map": 40, "points": [[5, 3], [5, 4], [5, 5], [6, 5], [7, 5]]},
                {"map": 0, "points": [[5, 11], [5, 12]]},
            ],
        )

    def test_the_turns_alone_are_still_available(self):
        recorder = TrailRecorder()
        for x, y in [(5, 3), (5, 4), (5, 5), (6, 5), (7, 5)]:
            recorder.record("parcel_event", 40, x, y)
        self.assertEqual(
            recorder.legs(dense=False),
            [{"map": 40, "points": [[5, 3], [5, 5], [7, 5]]}],
        )

    def test_standing_still_does_not_grow_the_trail(self):
        recorder = TrailRecorder()
        for _ in range(10):
            recorder.record("start", 40, 5, 3)
        self.assertEqual(recorder.legs(), [{"map": 40, "points": [[5, 3]]}])

    def test_a_new_quest_starts_a_new_trail(self):
        recorder = TrailRecorder()
        recorder.record("start", 40, 5, 3)
        recorder.record("parcel_event", 40, 5, 4)
        self.assertEqual(recorder.quest_id, "parcel_event")
        self.assertEqual(recorder.legs(), [{"map": 40, "points": [[5, 4]]}])

    def test_a_detour_that_came_back_is_not_part_of_the_way(self):
        # Pushing at a wall and returning is not a route; walked as written it
        # would be walked again on purpose.
        recorder = TrailRecorder()
        for x, y in [(5, 3), (6, 3), (7, 3), (6, 3), (5, 3), (5, 4)]:
            recorder.record("parcel_event", 40, x, y)
        self.assertEqual(
            recorder.legs(), [{"map": 40, "points": [[5, 3], [5, 4]]}]
        )


class DeathCycleTests(unittest.TestCase):
    """Dying is attempt N+1, not a stumble in the middle of attempt N."""

    def walk(self, recorder, positions):
        for x, y in positions:
            recorder.record("viridian_forest_nav", 51, x, y)

    def test_the_attempt_that_died_is_not_published_with_the_one_that_arrived(self):
        recorder = TrailRecorder()
        self.walk(recorder, [(15, 47), (15, 46), (15, 45)])
        recorder.restart(1)
        self.walk(recorder, [(17, 47), (17, 46)])
        self.assertEqual(
            recorder.legs(), [{"map": 51, "points": [[17, 47], [17, 46]]}]
        )

    def test_a_restart_reports_what_the_dead_attempt_cost(self):
        recorder = TrailRecorder()
        self.walk(recorder, [(15, 47), (15, 46), (15, 45)])
        self.assertEqual(recorder.restart(1), 3)
        self.assertEqual(recorder.steps, 0)

    def test_the_cycle_is_numbered_so_two_attempts_can_be_told_apart(self):
        recorder = TrailRecorder()
        self.assertEqual(recorder.cycle, 0)
        recorder.restart(1)
        recorder.restart(2)
        self.assertEqual(recorder.cycle, 2)

    def test_the_quest_survives_the_death(self):
        # The whiteout throws the trainer backwards; the objective is unchanged
        # and the recording has to keep belonging to it.
        recorder = TrailRecorder()
        self.walk(recorder, [(15, 47)])
        recorder.restart(1)
        self.walk(recorder, [(17, 47)])
        self.assertEqual(recorder.quest_id, "viridian_forest_nav")


class TrailStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = TrailStore(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_missing_trail_is_empty_not_an_error(self):
        self.assertEqual(self.store.load("never_walked"), [])

    def test_published_trail_comes_back(self):
        legs = [{"map": 40, "points": [[5, 3], [5, 11]]}]
        self.assertTrue(self.store.publish("parcel_event", "AARON", legs))
        self.assertEqual(self.store.load("parcel_event"), legs)

    def test_a_longer_trail_never_replaces_a_shorter_one(self):
        short = [{"map": 40, "points": [[5, 3], [5, 11]]}]
        long = [{"map": 40, "points": [[5, 3], [8, 3], [8, 11], [5, 11]]}]
        self.store.publish("parcel_event", "AARON", short)
        self.assertFalse(self.store.publish("parcel_event", "AARON", long))
        self.assertEqual(self.store.load("parcel_event"), short)

    def test_a_corrupt_trail_is_ignored_rather_than_fatal(self):
        path = Path(self.directory.name) / "parcel_event.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not json", encoding="utf-8")
        self.assertEqual(self.store.load("parcel_event"), [])

    def test_a_walked_crossing_replaces_the_mined_anchors(self):
        # The old rule was brevity alone, and it locked the sparse trails in:
        # four points mined from an event log could never be beaten by the
        # fifty tiles somebody actually walked.
        anchors = [{"map": 51, "points": [[15, 47], [17, 20], [1, 18]]}]
        walked = [{"map": 51, "points": [[15, 47 - step] for step in range(30)]}]
        self.store.publish("viridian_forest_nav", "minerada:AARON", anchors)
        self.assertTrue(
            self.store.publish("viridian_forest_nav", "AARON", walked, dense=True)
        )
        self.assertEqual(self.store.load("viridian_forest_nav"), walked)

    def test_mined_anchors_never_replace_a_walked_crossing(self):
        walked = [{"map": 51, "points": [[15, 47 - step] for step in range(30)]}]
        anchors = [{"map": 51, "points": [[15, 47], [17, 20], [1, 18]]}]
        self.store.publish("viridian_forest_nav", "AARON", walked, dense=True)
        self.assertFalse(
            self.store.publish("viridian_forest_nav", "minerada:BARON", anchors)
        )

    def test_reach_still_outranks_density(self):
        # A stump that knows every tile of one map leads the follower nowhere;
        # anchors across four maps at least cross the whole thing.
        stump = [{"map": 51, "points": [[15, 47], [15, 46]]}]
        far = [
            {"map": 51, "points": [[15, 47], [1, 18]]},
            {"map": 13, "points": [[8, 6], [8, 1]]},
        ]
        self.store.publish("viridian_forest_nav", "AARON", stump, dense=True)
        self.assertTrue(
            self.store.publish("viridian_forest_nav", "minerada:BARON", far)
        )

    def test_a_shorter_walked_crossing_wins_over_a_longer_one(self):
        # Fewer steps per quest is the point of measuring at all.
        long_way = [{"map": 51, "points": [[15, 47 - step] for step in range(30)]}]
        short_way = [{"map": 51, "points": [[15, 47 - step] for step in range(20)]}]
        self.store.publish("viridian_forest_nav", "AARON", long_way, dense=True)
        self.assertTrue(
            self.store.publish("viridian_forest_nav", "BARON", short_way, dense=True)
        )
        self.assertEqual(self.store.load("viridian_forest_nav"), short_way)

    def test_a_pile_of_stamps_does_not_count_as_reach(self):
        # This is the shape of every trail published so far: nine maps, nine
        # legs, not one of them with two points in it. The follower reads a
        # single point and hands the step back to the drawn route, so counting
        # those maps as reach would keep a real crossing out forever.
        stamps = [{"map": m, "points": [[5, 5]]} for m in (0, 12, 1, 13, 50, 51)]
        walked = [{"map": 51, "points": [[15, 47 - step] for step in range(30)]}]
        self.store.publish("viridian_forest_nav", "minerada:AARON", stamps)
        self.assertTrue(
            self.store.publish("viridian_forest_nav", "AARON", walked, dense=True)
        )
        self.assertEqual(self.store.load("viridian_forest_nav"), walked)

    def test_the_cost_of_the_winning_attempt_is_stored(self):
        legs = [{"map": 51, "points": [[15, 47], [15, 46]]}]
        self.store.publish(
            "viridian_forest_nav", "AARON", legs, dense=True, cycle=2, steps=180
        )
        stored = self.store.read("viridian_forest_nav")
        self.assertEqual(stored["death_cycle"], 2)
        self.assertEqual(stored["steps"], 180)
        self.assertTrue(stored["dense"])


class JoiningTests(unittest.TestCase):
    LEGS = [
        {"map": 0, "points": [[10, 6], [10, 1]]},
        {"map": 1, "points": [[20, 35], [20, 30], [24, 30]]},
        {"map": 0, "points": [[10, 1], [10, 6], [12, 6]]},
    ]

    def test_follower_joins_at_the_nearest_point_and_keeps_the_rest(self):
        self.assertEqual(
            waypoints_from(self.LEGS, 1, 20, 31), [(20, 30), (24, 30)]
        )

    def test_standing_on_a_point_moves_to_the_next_one(self):
        self.assertEqual(waypoints_from(self.LEGS, 1, 20, 35), [(20, 30), (24, 30)])

    def test_a_map_the_trail_never_visited_yields_nothing(self):
        self.assertEqual(waypoints_from(self.LEGS, 51, 15, 47), [])

    def test_a_tile_crossed_twice_resolves_to_the_later_leg(self):
        # (10, 6) is walked on the way out and on the way back. The way back is
        # the part still owed, so that is the one to continue.
        self.assertEqual(waypoints_from(self.LEGS, 0, 10, 6), [(12, 6)])

    def test_being_thrown_backwards_rejoins_behind_instead_of_stalling(self):
        # A whiteout drops the run in Pallet while the trail was in Viridian.
        self.assertEqual(
            waypoints_from(self.LEGS, 0, 10, 2)[0], (10, 1)
        )


class JoinAnywhereTests(unittest.TestCase):
    """Getting lost must cost the distance back, never the crossing.

    There is more than one right way through a map. What matters is that the
    one written down can be joined at any height: wherever the bot ends up —
    thrown back by a whiteout, pushed off by an NPC, walked into a pocket — the
    trail has to answer with the rest of the way, not with "you are not on me".
    That answer is only possible because the trail is dense. Four anchors leave
    the nearest point twenty tiles away and the join is a hike; one point per
    tile means the nearest point is the tile next door.
    """

    # An L across one map: south down x=15, then east along y=20.
    TRAIL = [{"map": 51, "points": (
        [[15, y] for y in range(47, 20, -1)] + [[x, 20] for x in range(15, 30)]
    )}]
    LAST = [29, 20]

    def rest(self, x, y):
        return waypoints_from(self.TRAIL, 51, x, y)

    def test_every_tile_of_the_map_is_answered_with_the_rest_of_the_way(self):
        for x in range(0, 32, 3):
            for y in range(0, 48, 3):
                remainder = self.rest(x, y)
                self.assertTrue(remainder, f"sem resposta em ({x},{y})")
                self.assertEqual(
                    tuple(self.LAST), remainder[-1],
                    f"de ({x},{y}) a trilha não termina no fim da travessia",
                )

    def test_joining_costs_only_the_distance_back_to_the_path(self):
        # Two tiles off the line, the first waypoint is the tile beside it.
        remainder = self.rest(17, 34)
        self.assertEqual((15, 34), remainder[0])

    def test_a_whiteout_thrown_backwards_rejoins_behind(self):
        # Dropped at the entrance while the crossing had reached the corner.
        self.assertEqual((15, 46), self.rest(15, 47)[0])

    def test_walking_past_the_end_still_points_at_the_end(self):
        self.assertEqual([tuple(self.LAST)], self.rest(31, 20))

    def test_progress_is_forward_from_wherever_it_joined(self):
        # However far off it starts, the remainder never grows.
        lengths = [len(self.rest(15, y)) for y in range(47, 20, -1)]
        self.assertEqual(lengths, sorted(lengths, reverse=True))


if __name__ == "__main__":
    unittest.main()
