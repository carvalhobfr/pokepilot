"""Persistent two-slot roster and completed-journey archiving.

The emulator slot is intentionally separate from the trainer identity.  A slot
can therefore receive a new trainer while the other slot resumes its own
``current.state`` and ``current.sav`` unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

from trainer_directives import (
    DirectiveError,
    directive_is_complete,
    load_directive,
    target_quest_ids,
)


ROSTER_VERSION = 1
DEFAULT_SLOT_COUNT = 2
PROFILE_COUNT = 8


def agent_name_for_index(index: int) -> str:
    """Return stable, human-readable names for successive completed runs."""
    index = int(index)
    if index < 0:
        raise ValueError("agent index must be non-negative")
    if index == 0:
        return "AARON"
    if index == 1:
        return "BARON"
    if index == 2:
        return "CAARON"
    if index < 26:
        return f"{chr(ord('A') + index)}ARON"
    return f"RUN{index + 1:04d}"


def _atomic_json_write(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def default_roster(slot_count: int = DEFAULT_SLOT_COUNT) -> dict:
    slot_count = int(slot_count)
    if slot_count < 1:
        raise ValueError("slot_count must be at least one")
    return {
        "version": ROSTER_VERSION,
        "slot_count": slot_count,
        "next_agent_index": slot_count,
        "slots": [
            {
                "slot": slot,
                "agent_name": agent_name_for_index(slot),
                "identity_index": slot,
                "profile_index": slot % PROFILE_COUNT,
                "generation": 1,
                "status": "active",
            }
            for slot in range(slot_count)
        ],
        "completed_runs": [],
    }


def validate_roster(roster: dict, slot_count: int | None = None) -> dict:
    if int(roster.get("version", -1)) != ROSTER_VERSION:
        raise ValueError(f"unsupported roster version: {roster.get('version')}")
    slots = sorted(roster.get("slots", []), key=lambda entry: int(entry["slot"]))
    expected = int(roster.get("slot_count", len(slots)))
    if slot_count is not None and expected != int(slot_count):
        raise ValueError(
            f"roster has {expected} slots, but this run requested {slot_count}"
        )
    if len(slots) != expected or [int(entry["slot"]) for entry in slots] != list(range(expected)):
        raise ValueError("roster slots must be contiguous and match slot_count")
    names = [str(entry.get("agent_name", "")).strip() for entry in slots]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("active roster agent names must be non-empty and unique")
    roster["slots"] = slots
    roster.setdefault("completed_runs", [])
    return roster


def resize_roster(roster: dict, slot_count: int) -> dict:
    """Grow or shrink the active slots without touching any trainer on disk.

    Shrinking only removes the slot from the active list: the trainer keeps its
    save, journey and logs, so putting it back later resumes where it stopped.
    """
    slot_count = int(slot_count)
    if slot_count < 1:
        raise ValueError("slot_count must be at least one")
    slots = sorted(roster.get("slots", []), key=lambda entry: int(entry["slot"]))

    while len(slots) > slot_count:
        retired = slots.pop()
        roster.setdefault("retired_slots", []).append({
            "agent_name": retired["agent_name"],
            "reason": "slot removido; treinador preservado em trainers/",
        })

    while len(slots) < slot_count:
        index = int(roster.get("next_agent_index", len(slots)))
        names = {str(entry["agent_name"]) for entry in slots}
        while agent_name_for_index(index) in names:
            index += 1
        slots.append({
            "slot": len(slots),
            "agent_name": agent_name_for_index(index),
            "identity_index": index,
            "profile_index": index % PROFILE_COUNT,
            "generation": 1,
            "status": "active",
        })
        roster["next_agent_index"] = index + 1

    for position, entry in enumerate(slots):
        entry["slot"] = position
    roster["slots"] = slots
    roster["slot_count"] = slot_count
    return roster


def load_or_create_roster(path: Path, slot_count: int = DEFAULT_SLOT_COUNT) -> dict:
    path = Path(path)
    if not path.exists():
        roster = default_roster(slot_count)
        _atomic_json_write(path, roster)
        return roster
    with open(path, "r", encoding="utf-8") as source:
        roster = json.load(source)
    if slot_count is not None and int(roster.get("slot_count", 0)) != int(slot_count):
        roster = validate_roster(resize_roster(roster, slot_count))
        _atomic_json_write(path, roster)
        return roster
    return validate_roster(roster, slot_count)


def save_roster(path: Path, roster: dict) -> None:
    _atomic_json_write(Path(path), validate_roster(roster))


def quest_ids_from_graph(graph_path: Path) -> tuple[str, ...]:
    with open(graph_path, "r", encoding="utf-8") as source:
        graph = json.load(source)
    return tuple(str(node["id"]) for node in graph["nodes"])


def journey_is_complete(trainer_dir: Path, quest_ids: tuple[str, ...]) -> bool:
    """True when this trainer finished what *its directive* asked for.

    The completion target is per-trainer: one slot may be told to play only up
    to Brock while the other runs the full story, and each rotates when its own
    target is met.
    """
    trainer_dir = Path(trainer_dir)
    journey_path = trainer_dir / "journey.json"
    try:
        with open(journey_path, "r", encoding="utf-8") as source:
            journey = json.load(source)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    completed = {str(quest_id) for quest_id in journey.get("completed_quests", [])}

    try:
        directive = load_directive(trainer_dir, quest_ids)
    except (DirectiveError, OSError, ValueError):
        # An unreadable directive must never be read as "this run is done";
        # rotating on it would archive an unfinished journey.
        return False
    return directive_is_complete(directive, quest_ids, completed)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_if_present(source: Path, destination: Path) -> bool:
    if not source.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def archive_completed_agent(
    *,
    project_root: Path,
    agent_slot: dict,
    quest_graph_path: Path,
    policy_path: Path | None = None,
    rom_identity: dict | None = None,
    archived_at: datetime | None = None,
) -> Path:
    """Copy the reproducible artifacts for one completed trainer.

    Runtime probe states are deliberately excluded: the canonical emulator
    state, SRAM, milestones, semantic journey and decision log are sufficient
    and keep each archive compact.
    """
    project_root = Path(project_root)
    agent_name = str(agent_slot["agent_name"])
    trainer_dir = project_root / "trainers" / agent_name
    archived_at = archived_at or datetime.now(timezone.utc)
    stamp = archived_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    archive_dir = project_root / "archives" / f"{stamp}-{agent_name}"
    suffix = 1
    while archive_dir.exists():
        archive_dir = project_root / "archives" / f"{stamp}-{agent_name}-{suffix}"
        suffix += 1
    archive_dir.mkdir(parents=True)

    # What the run was asked to do belongs in the archive next to what it did;
    # otherwise a bounded run looks like an abandoned full run later on.
    quest_ids = quest_ids_from_graph(quest_graph_path)
    try:
        directive = load_directive(trainer_dir, quest_ids)
        targets = target_quest_ids(directive, quest_ids)
        completion_target = targets[-1] if targets else f"orders:{len(directive.orders)}"
    except (DirectiveError, OSError, ValueError):
        directive = None
        completion_target = quest_ids[-1] if quest_ids else None

    sources = {
        trainer_dir / "current.sav": archive_dir / "save" / "current.sav",
        trainer_dir / "current.state": archive_dir / "save" / "current.state",
        trainer_dir / "journey.json": archive_dir / "journey.json",
        trainer_dir / "directives.json": archive_dir / "directives.json",
        trainer_dir / "logs" / "decisions.jsonl": archive_dir / "logs" / "decisions.jsonl",
        Path(quest_graph_path): archive_dir / "quest_graph.json",
    }
    for source, destination in sources.items():
        _copy_if_present(source, destination)

    checkpoint_dir = trainer_dir / "checkpoints"
    if checkpoint_dir.is_dir():
        shutil.copytree(checkpoint_dir, archive_dir / "checkpoints")

    copied_policy = None
    if policy_path is not None:
        policy_path = Path(policy_path)
        destination = archive_dir / "brain" / "latest_policy.zip"
        if _copy_if_present(policy_path, destination):
            copied_policy = destination

    code_root = project_root / "blue-agents"
    version_sources = (
        code_root / "hybrid_agent.py",
        code_root / "quest_graph.py",
        code_root / "src" / "scripted_agent.py",
    )
    code_hashes = {
        str(path.relative_to(project_root)): _sha256(path)
        for path in version_sources
        if path.is_file()
    }
    archived_files = sorted(
        path for path in archive_dir.rglob("*") if path.is_file()
    )
    manifest = {
        "archive_version": 1,
        "archived_at": archived_at.astimezone(timezone.utc).isoformat(),
        "completion_target": completion_target,
        "agent": {
            "name": agent_name,
            "slot": int(agent_slot["slot"]),
            "identity_index": int(agent_slot.get("identity_index", 0)),
            "profile_index": int(agent_slot.get("profile_index", 0)),
            "generation": int(agent_slot.get("generation", 1)),
        },
        "rom": rom_identity,
        "brain": {
            "policy": "brain/latest_policy.zip" if copied_policy else None,
            "policy_sha256": _sha256(copied_policy) if copied_policy else None,
            "code_sha256": code_hashes,
        },
        "files": {
            str(path.relative_to(archive_dir)): {
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in archived_files
        },
    }
    _atomic_json_write(archive_dir / "manifest.json", manifest)
    return archive_dir


def rotate_completed_slots(
    *,
    roster_path: Path,
    project_root: Path,
    quest_graph_path: Path,
    policy_path: Path | None = None,
    rom_identity: dict | None = None,
    slot_count: int = DEFAULT_SLOT_COUNT,
) -> list[dict]:
    """Archive complete runs and replace only those trainer identities."""
    roster = load_or_create_roster(roster_path, slot_count)
    quest_ids = quest_ids_from_graph(quest_graph_path)
    rotations = []

    for slot in roster["slots"]:
        completed_name = str(slot["agent_name"])
        trainer_dir = Path(project_root) / "trainers" / completed_name
        if not journey_is_complete(trainer_dir, quest_ids):
            continue

        archive_dir = archive_completed_agent(
            project_root=project_root,
            agent_slot=slot,
            quest_graph_path=quest_graph_path,
            policy_path=policy_path,
            rom_identity=rom_identity,
        )
        next_index = int(roster["next_agent_index"])
        next_name = agent_name_for_index(next_index)
        completed_record = {
            "agent_name": completed_name,
            "slot": int(slot["slot"]),
            "archive": str(archive_dir),
            "replaced_by": next_name,
        }
        roster["completed_runs"].append(completed_record)
        slot.update({
            "agent_name": next_name,
            "identity_index": next_index,
            "profile_index": next_index % PROFILE_COUNT,
            "generation": int(slot.get("generation", 1)) + 1,
            "status": "active",
        })
        roster["next_agent_index"] = next_index + 1
        rotations.append(completed_record)

    if rotations:
        save_roster(roster_path, roster)
    return rotations
