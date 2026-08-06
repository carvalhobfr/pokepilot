"""Trails: what the guide proved, and how the follower joins it."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.route_trails import TrailRecorder, TrailStore, waypoints_from


class TrailRecorderTests(unittest.TestCase):
    def test_legs_split_by_map_and_keep_only_turns(self):
        recorder = TrailRecorder()
        for x, y in [(5, 3), (5, 4), (5, 5), (6, 5), (7, 5)]:
            recorder.record("parcel_event", 40, x, y)
        recorder.record("parcel_event", 0, 5, 11)
        recorder.record("parcel_event", 0, 5, 12)

        self.assertEqual(
            recorder.legs(),
            [
                {"map": 40, "points": [[5, 3], [5, 5], [7, 5]]},
                {"map": 0, "points": [[5, 11], [5, 12]]},
            ],
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


if __name__ == "__main__":
    unittest.main()
