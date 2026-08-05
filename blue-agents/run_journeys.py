#!/usr/bin/env python3
"""Run two resumable journeys and rotate only completed trainers."""

from __future__ import annotations

import argparse
from pathlib import Path
import signal
import subprocess
import sys

from journey_roster import load_or_create_roster, rotate_completed_slots
from rom_identity import require_blue


SLOT_COUNT = 2


def parse_args():
    parser = argparse.ArgumentParser(
        description="Keep two Pokémon Blue journeys running and archive completed saves"
    )
    parser.add_argument(
        "--chunk-steps",
        type=int,
        default=8192,
        help="Steps per agent before a safe save/rotation check (default: 8192)",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=0,
        help="Stop after N chunks; 0 keeps running until interrupted",
    )
    parser.add_argument("--rollout-steps", type=int, default=128)
    parser.add_argument("--state-update-interval", type=int, default=250)
    parser.add_argument("--device", choices=["auto", "cpu", "mps"], default="auto")
    parser.add_argument("--state", choices=["fresh", "pokedex"], default="fresh")
    parser.add_argument("--rom", default="PokemonBlue.gb")
    parser.add_argument("--roster", default="tasks/slot_roster.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.chunk_steps < 64:
        raise ValueError("--chunk-steps must be at least 64")
    if args.max_chunks < 0:
        raise ValueError("--max-chunks cannot be negative")

    agent_root = Path(__file__).resolve().parent
    project_root = agent_root.parent
    roster_path = Path(args.roster).expanduser()
    if not roster_path.is_absolute():
        roster_path = agent_root / roster_path
    graph_path = agent_root / "knowledge" / "quests" / "main_quest_graph.json"
    policy_path = agent_root / "v2_repro_runs" / "latest_policy.zip"
    requested_rom = Path(args.rom).expanduser()
    rom_path = requested_rom if requested_rom.is_absolute() else project_root / "roms" / requested_rom
    rom_identity = require_blue(rom_path).as_dict()
    load_or_create_roster(roster_path, SLOT_COUNT)

    stop_requested = False
    child: subprocess.Popen | None = None

    def request_stop(signum, _frame):
        nonlocal stop_requested
        stop_requested = True
        print(f"\n🛑 Signal {signum}: saving both active journeys before exit...", flush=True)
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGINT)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    def rotate_if_ready():
        rotations = rotate_completed_slots(
            roster_path=roster_path,
            project_root=project_root,
            quest_graph_path=graph_path,
            policy_path=policy_path,
            rom_identity=rom_identity,
            slot_count=SLOT_COUNT,
        )
        for rotation in rotations:
            print(
                "🏆 "
                f"{rotation['agent_name']} archived at {rotation['archive']}; "
                f"slot {rotation['slot']} now belongs to {rotation['replaced_by']}",
                flush=True,
            )

    # Also recovers the case where the previous process ended immediately
    # after persisting the final Mewtwo event but before rotating the slot.
    rotate_if_ready()

    chunks_finished = 0
    while not stop_requested and (
        args.max_chunks == 0 or chunks_finished < args.max_chunks
    ):
        roster = load_or_create_roster(roster_path, SLOT_COUNT)
        active = ", ".join(
            f"slot {slot['slot']}={slot['agent_name']}"
            for slot in roster["slots"]
        )
        print(
            f"\n🎮 Journey chunk {chunks_finished + 1}: {active} "
            f"({args.chunk_steps} steps each)",
            flush=True,
        )
        command = [
            sys.executable,
            str(agent_root / "train_hybrid.py"),
            "--agents", str(SLOT_COUNT),
            "--steps", str(args.chunk_steps),
            "--rollout-steps", str(args.rollout_steps),
            "--state-update-interval", str(args.state_update_interval),
            "--device", args.device,
            "--state", args.state,
            "--rom", str(rom_path),
            "--roster", str(roster_path),
            "--resume",
        ]
        child = subprocess.Popen(command, cwd=agent_root)
        return_code = child.wait()
        child = None
        if stop_requested:
            rotate_if_ready()
            break
        if return_code != 0:
            print(f"❌ Journey worker exited with code {return_code}", flush=True)
            return return_code

        chunks_finished += 1
        rotate_if_ready()

    print("💾 Journey supervisor stopped with both active slots persisted.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
