#!/usr/bin/env python3
"""Probe walkable cartridge tiles from a PyBoy state without modifying it.

This is a development tool for validating scripted routes. It branches the
emulator state in memory, applies one D-pad press per branch and reports either
the shortest path to a target or the reachable component around the player.
"""

from __future__ import annotations

import argparse
from collections import deque
from io import BytesIO
from pathlib import Path

from pyboy import PyBoy
from pyboy.utils import WindowEvent


ACTIONS = (
    ("L", WindowEvent.PRESS_ARROW_LEFT, WindowEvent.RELEASE_ARROW_LEFT),
    ("R", WindowEvent.PRESS_ARROW_RIGHT, WindowEvent.RELEASE_ARROW_RIGHT),
    ("U", WindowEvent.PRESS_ARROW_UP, WindowEvent.RELEASE_ARROW_UP),
    ("D", WindowEvent.PRESS_ARROW_DOWN, WindowEvent.RELEASE_ARROW_DOWN),
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Find real walkable paths from a saved PyBoy state"
    )
    parser.add_argument("state", type=Path)
    parser.add_argument("--rom", type=Path, default=Path("../roms/PokemonBlue.gb"))
    parser.add_argument("--target-x", type=int)
    parser.add_argument("--target-y", type=int)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument(
        "--path",
        default="",
        help="Apply an L/R/U/D/A prefix before probing (for map transitions)",
    )
    parser.add_argument(
        "--save-output",
        type=Path,
        help="Save the post-prefix diagnostic branch; never changes the input state",
    )
    return parser.parse_args()


def snapshot(pyboy):
    output = BytesIO()
    pyboy.save_state(output)
    return output.getvalue()


def coordinates(pyboy):
    return (
        int(pyboy.memory[0xD35E]),
        int(pyboy.memory[0xD362]),
        int(pyboy.memory[0xD361]),
    )


def main():
    args = parse_args()
    pyboy = PyBoy(str(args.rom), window="null", sound_emulated=False)
    with args.state.open("rb") as state_file:
        pyboy.load_state(state_file)

    # Autosaves can land between a press and release. Let the current input
    # settle before creating the immutable root branch.
    pyboy.tick(60, True, False)
    for _ in range(4):
        if int(pyboy.memory[0xCFC4]) != 1:
            break
        pyboy.send_input(WindowEvent.PRESS_BUTTON_A)
        pyboy.tick(8, False, False)
        pyboy.send_input(WindowEvent.RELEASE_BUTTON_A)
        pyboy.tick(16, True, False)

    input_events = {
        "L": (WindowEvent.PRESS_ARROW_LEFT, WindowEvent.RELEASE_ARROW_LEFT),
        "R": (WindowEvent.PRESS_ARROW_RIGHT, WindowEvent.RELEASE_ARROW_RIGHT),
        "U": (WindowEvent.PRESS_ARROW_UP, WindowEvent.RELEASE_ARROW_UP),
        "D": (WindowEvent.PRESS_ARROW_DOWN, WindowEvent.RELEASE_ARROW_DOWN),
        "A": (WindowEvent.PRESS_BUTTON_A, WindowEvent.RELEASE_BUTTON_A),
    }
    for label in args.path.upper():
        if label.isspace():
            continue
        if label not in input_events:
            raise ValueError(f"Unsupported --path action: {label!r}")
        press, release = input_events[label]
        pyboy.send_input(press)
        pyboy.tick(8, False, False)
        pyboy.send_input(release)
        pyboy.tick(16, True, False)

    # A warp lands the player in two phases: the tile appears at the source
    # coordinates first, then the game repositions to the destination warp
    # tile ~40+ frames later. Snapshoting 16 frames after the last press
    # captures the player mid-warp, where every direction reads as blocked
    # ("reachable=1"). Settle past the repositioning before branching.
    if args.path:
        pyboy.tick(120, True, False)

    if args.save_output:
        args.save_output.parent.mkdir(parents=True, exist_ok=True)
        with args.save_output.open("wb") as output:
            pyboy.save_state(output)
    start = coordinates(pyboy)
    root_state = snapshot(pyboy)
    target = (
        (start[0], args.target_x, args.target_y)
        if args.target_x is not None and args.target_y is not None
        else None
    )

    queue = deque([(start, root_state, ())])
    visited = {start}
    found_path = None

    while queue and len(visited) < max(args.limit, 1):
        current, state_bytes, path = queue.popleft()
        if target is not None and current == target:
            found_path = path
            break

        for label, press, release in ACTIONS:
            pyboy.load_state(BytesIO(state_bytes))
            pyboy.send_input(press)
            pyboy.tick(8, False, False)
            pyboy.send_input(release)
            pyboy.tick(16, True, False)
            candidate = coordinates(pyboy)

            # Keep the probe local to the current outdoor/interior map. Story
            # transitions and battles are deliberately handled by live runs.
            if candidate[0] != start[0] or candidate == current:
                continue
            if candidate in visited:
                continue
            visited.add(candidate)
            queue.append((candidate, snapshot(pyboy), path + (label,)))

    pyboy.stop(save=False)

    xs = [position[1] for position in visited]
    ys = [position[2] for position in visited]
    print(
        f"start={start} reachable={len(visited)} "
        f"x={min(xs)}..{max(xs)} y={min(ys)}..{max(ys)}"
    )
    if target is not None:
        if found_path is None:
            print(f"target={target} unreachable within limit={args.limit}")
        else:
            print(f"target={target} steps={len(found_path)} path={''.join(found_path)}")
    else:
        rows = {}
        for _, x, y in sorted(visited, key=lambda item: (item[2], item[1])):
            rows.setdefault(y, []).append(x)
        for y, row_xs in rows.items():
            print(f"y={y:02d}: {','.join(str(x) for x in row_xs)}")


if __name__ == "__main__":
    main()
