import json
from pathlib import Path
import tempfile
import unittest

from journey_roster import (
    agent_name_for_index,
    default_roster,
    journey_is_complete,
    load_or_create_roster,
    rotate_completed_slots,
)


class JourneyRosterTests(unittest.TestCase):
    def test_first_rotated_name_matches_two_slot_sequence(self):
        self.assertEqual("AARON", agent_name_for_index(0))
        self.assertEqual("BARON", agent_name_for_index(1))
        self.assertEqual("CAARON", agent_name_for_index(2))

    def test_roster_is_created_with_two_stable_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks" / "slot_roster.json"
            roster = load_or_create_roster(path, 2)
            self.assertEqual(["AARON", "BARON"], [
                slot["agent_name"] for slot in roster["slots"]
            ])
            self.assertEqual(roster, json.loads(path.read_text(encoding="utf-8")))

    def test_completion_requires_every_graph_node(self):
        with tempfile.TemporaryDirectory() as directory:
            trainer = Path(directory) / "AARON"
            trainer.mkdir()
            (trainer / "journey.json").write_text(
                json.dumps({"completed_quests": ["start"]}), encoding="utf-8"
            )
            self.assertFalse(journey_is_complete(trainer, ("start", "league")))
            (trainer / "journey.json").write_text(
                json.dumps({"completed_quests": ["start", "league"]}), encoding="utf-8"
            )
            self.assertTrue(journey_is_complete(trainer, ("start", "league")))

    def test_rotation_archives_only_complete_slot_and_keeps_other_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            agent_root = project / "blue-agents"
            graph = agent_root / "knowledge" / "quests" / "main_quest_graph.json"
            graph.parent.mkdir(parents=True)
            graph.write_text(
                json.dumps({"nodes": [{"id": "start"}, {"id": "mewtwo_postgame"}]}),
                encoding="utf-8",
            )
            roster_path = agent_root / "tasks" / "slot_roster.json"
            roster_path.parent.mkdir(parents=True)
            roster_path.write_text(json.dumps(default_roster(2)), encoding="utf-8")

            aaron = project / "trainers" / "AARON"
            (aaron / "logs").mkdir(parents=True)
            (aaron / "runtime").mkdir()
            (aaron / "current.sav").write_bytes(b"save")
            (aaron / "current.state").write_bytes(b"state")
            (aaron / "journey.json").write_text(
                json.dumps({"completed_quests": ["start", "mewtwo_postgame"]}),
                encoding="utf-8",
            )
            (aaron / "logs" / "decisions.jsonl").write_text("{}\n", encoding="utf-8")
            (aaron / "runtime" / "probe.state").write_bytes(b"discard me")

            baron = project / "trainers" / "BARON"
            baron.mkdir(parents=True)
            (baron / "journey.json").write_text(
                json.dumps({"completed_quests": ["start"]}), encoding="utf-8"
            )
            policy = agent_root / "v2_repro_runs" / "latest_policy.zip"
            policy.parent.mkdir()
            policy.write_bytes(b"policy")

            rotations = rotate_completed_slots(
                roster_path=roster_path,
                project_root=project,
                quest_graph_path=graph,
                policy_path=policy,
                rom_identity={"game": "pokemon_blue", "sha1": "test"},
                slot_count=2,
            )

            self.assertEqual(1, len(rotations))
            updated = json.loads(roster_path.read_text(encoding="utf-8"))
            self.assertEqual("CAARON", updated["slots"][0]["agent_name"])
            self.assertEqual("BARON", updated["slots"][1]["agent_name"])
            archive = Path(rotations[0]["archive"])
            self.assertEqual(b"save", (archive / "save" / "current.sav").read_bytes())
            self.assertEqual(b"policy", (archive / "brain" / "latest_policy.zip").read_bytes())
            self.assertFalse((archive / "runtime").exists())
            manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("mewtwo_postgame", manifest["completion_target"])
            self.assertIsNotNone(manifest["brain"]["policy_sha256"])


if __name__ == "__main__":
    unittest.main()
