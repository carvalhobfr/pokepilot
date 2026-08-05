import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trainer_directives import (  # noqa: E402
    DirectiveError,
    build_order,
    default_directive,
    directive_is_complete,
    load_directive,
    parse_directive,
    save_directive,
    story_is_needed,
    target_quest_ids,
)


QUEST_IDS = (
    "start",
    "oak_event",
    "brock_quest",
    "cerulean_gym_quest",
    "vermilion_gym_quest",
    "mewtwo_postgame",
)


class TrainerDirectiveTest(unittest.TestCase):
    def test_default_is_the_full_main_quest(self):
        directive = default_directive()
        self.assertEqual(directive.mode, "main_quest")
        self.assertIsNone(directive.stop_at)
        self.assertEqual(target_quest_ids(directive, QUEST_IDS), QUEST_IDS)

    def test_stop_at_is_inclusive_prefix(self):
        directive = parse_directive(
            {"mode": "main_quest", "stop_at": "brock_quest"}, QUEST_IDS
        )
        self.assertEqual(
            target_quest_ids(directive, QUEST_IDS),
            ("start", "oak_event", "brock_quest"),
        )

    def test_unknown_stop_at_is_rejected_with_the_valid_options(self):
        with self.assertRaises(DirectiveError) as caught:
            parse_directive({"stop_at": "elite_four"}, QUEST_IDS)
        self.assertIn("elite_four", str(caught.exception))
        self.assertIn("brock_quest", str(caught.exception))

    def test_order_compiles_into_a_ram_predicate(self):
        order = build_order("o1", "own_species", {"national_id": 29})
        self.assertEqual(
            order.success,
            ({"type": "species_owned", "national_id": 29},),
        )

    def test_unknown_order_kind_is_rejected(self):
        with self.assertRaises(DirectiveError) as caught:
            build_order("o1", "befriend_everyone", {})
        self.assertIn("befriend_everyone", str(caught.exception))

    def test_out_of_range_species_is_rejected(self):
        with self.assertRaises(DirectiveError):
            build_order("o1", "own_species", {"national_id": 400})

    def test_order_without_an_implemented_executor_is_rejected(self):
        with self.assertRaises(DirectiveError) as caught:
            build_order(
                "o1",
                "own_species",
                {"national_id": 29},
                available_executors=(),
            )
        self.assertIn("farm_species", str(caught.exception))

    def test_story_satisfiable_orders_need_no_dedicated_executor(self):
        order = build_order(
            "o1", "reach_level", {"level": 20}, available_executors=()
        )
        self.assertEqual(order.executor, "main_quest")

    def test_custom_mode_requires_at_least_one_order(self):
        with self.assertRaises(DirectiveError):
            parse_directive({"mode": "custom", "orders": []}, QUEST_IDS)

    def test_unverifiable_success_condition_is_rejected(self):
        payload = {
            "mode": "custom",
            "orders": [
                {
                    "id": "o1",
                    "kind": "own_species",
                    "params": {"national_id": 25},
                    "success": [{"type": "vibes", "value": "good"}],
                }
            ],
        }
        with self.assertRaises(DirectiveError) as caught:
            parse_directive(payload, QUEST_IDS)
        self.assertIn("vibes", str(caught.exception))

    def test_duplicate_order_ids_are_rejected(self):
        payload = {
            "mode": "custom",
            "orders": [
                {"id": "o1", "kind": "reach_level", "params": {"level": 20}},
                {"id": "o1", "kind": "reach_level", "params": {"level": 30}},
            ],
        }
        with self.assertRaises(DirectiveError):
            parse_directive(payload, QUEST_IDS)

    def test_custom_directive_is_incomplete_until_orders_finish(self):
        directive = parse_directive(
            {
                "mode": "custom",
                "orders": [
                    {"id": "o1", "kind": "own_species", "params": {"national_id": 29}}
                ],
            },
            QUEST_IDS,
        )
        self.assertFalse(directive_is_complete(directive, QUEST_IDS, QUEST_IDS))
        done = directive.with_completed("o1")
        self.assertTrue(directive_is_complete(done, QUEST_IDS, ()))

    def test_main_quest_completion_respects_stop_at(self):
        directive = parse_directive({"stop_at": "brock_quest"}, QUEST_IDS)
        self.assertTrue(
            directive_is_complete(
                directive, QUEST_IDS, ("start", "oak_event", "brock_quest")
            )
        )
        self.assertFalse(
            directive_is_complete(directive, QUEST_IDS, ("start", "oak_event"))
        )

    def test_custom_directive_can_fall_back_to_the_story(self):
        directive = parse_directive(
            {
                "mode": "custom",
                "after_orders": "main_quest",
                "stop_at": "brock_quest",
                "orders": [
                    {"id": "o1", "kind": "reach_level", "params": {"level": 12}}
                ],
            },
            QUEST_IDS,
        )
        self.assertEqual(
            target_quest_ids(directive, QUEST_IDS),
            ("start", "oak_event", "brock_quest"),
        )

    def test_story_stays_available_for_story_satisfiable_orders(self):
        directive = parse_directive(
            {
                "mode": "custom",
                "after_orders": "stop",
                "orders": [
                    {"id": "grind", "kind": "reach_level", "params": {"level": 14}}
                ],
            },
            QUEST_IDS,
        )
        # Without this the custom mode would bound the story to nothing and the
        # order could never be reached.
        self.assertTrue(story_is_needed(directive))
        self.assertFalse(story_is_needed(directive.with_completed("grind")))

    def test_story_is_not_needed_for_a_dedicated_executor_order(self):
        directive = parse_directive(
            {
                "mode": "custom",
                "orders": [
                    {"id": "farm", "kind": "own_species", "params": {"national_id": 29}}
                ],
            },
            QUEST_IDS,
        )
        self.assertFalse(story_is_needed(directive))

    def test_round_trip_through_disk(self):
        directive = parse_directive(
            {
                "mode": "custom",
                "stop_at": "cerulean_gym_quest",
                "after_orders": "main_quest",
                "orders": [
                    {"id": "farm", "kind": "own_species", "params": {"national_id": 29}},
                    {"id": "grind", "kind": "reach_level", "params": {"level": 25}},
                ],
                "completed_orders": ["farm"],
            },
            QUEST_IDS,
        )
        with tempfile.TemporaryDirectory() as folder:
            save_directive(Path(folder), directive)
            reloaded = load_directive(Path(folder), QUEST_IDS)
        self.assertEqual(reloaded, directive)
        self.assertEqual([order.id for order in reloaded.pending_orders()], ["grind"])

    def test_missing_file_falls_back_to_the_default(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(load_directive(Path(folder), QUEST_IDS), default_directive())

    def test_malformed_file_raises_instead_of_playing_everything(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "directives.json"
            path.write_text(json.dumps({"mode": "conquer_the_world"}))
            with self.assertRaises(DirectiveError):
                load_directive(Path(folder), QUEST_IDS)


if __name__ == "__main__":
    unittest.main()
