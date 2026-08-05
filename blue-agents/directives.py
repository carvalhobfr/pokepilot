#!/usr/bin/env python3
"""Inspect and submit trainer directives.

This is the deterministic backend a chat front-end will sit on top of. Every
order is validated here — unknown target, unknown order kind, out-of-range
parameter or missing controller are rejected with a reason — so the layer that
eventually parses natural language cannot introduce an unverifiable goal.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quest_graph import QuestGraph  # noqa: E402
from trainer_directives import (  # noqa: E402
    MAIN_QUEST_EXECUTOR,
    Directive,
    DirectiveError,
    build_order,
    default_directive,
    load_directive,
    save_directive,
    target_quest_ids,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = Path(__file__).resolve().parent / "knowledge/quests/main_quest_graph.json"


def trainer_dir(agent_name: str) -> Path:
    return PROJECT_ROOT / "trainers" / agent_name.upper()


def available_executors() -> set[str]:
    from src.scripted_agent import ScriptedAgent

    return {
        name[len("_run_"):] for name in dir(ScriptedAgent) if name.startswith("_run_")
    }


def load(agent_name: str, quest_ids) -> Directive:
    return load_directive(trainer_dir(agent_name), quest_ids, available_executors())


def cmd_show(args, quest_ids) -> int:
    directive = load(args.agent, quest_ids)
    targets = target_quest_ids(directive, quest_ids)
    print(f"treinador     : {args.agent.upper()}")
    print(f"modo          : {directive.mode}")
    print(f"até           : {directive.stop_at or '(fim da história)'}")
    print(f"após ordens   : {directive.after_orders}")
    print(f"nós alvo      : {len(targets)}/{len(quest_ids)}")
    if directive.orders:
        print("ordens        :")
        done = set(directive.completed_orders)
        for order in directive.orders:
            mark = "✓" if order.id in done else "·"
            executor = (
                "" if order.executor == MAIN_QUEST_EXECUTOR else f" [{order.executor}]"
            )
            print(f"  {mark} {order.id}: {order.title}{executor}")
    else:
        print("ordens        : (nenhuma)")
    return 0


def cmd_targets(args, quest_ids) -> int:
    for index, quest_id in enumerate(quest_ids, start=1):
        print(f"{index:2d}. {quest_id}")
    return 0


def cmd_set(args, quest_ids) -> int:
    directive = load(args.agent, quest_ids)
    payload = directive.as_dict()
    if args.mode:
        payload["mode"] = args.mode
    if args.stop_at is not None:
        payload["stop_at"] = None if args.stop_at == "none" else args.stop_at
    if args.after_orders:
        payload["after_orders"] = args.after_orders

    from trainer_directives import parse_directive

    updated = parse_directive(payload, quest_ids, available_executors())
    save_directive(trainer_dir(args.agent), updated)
    return cmd_show(args, quest_ids)


def cmd_order(args, quest_ids) -> int:
    directive = load(args.agent, quest_ids)
    params = dict(pair.split("=", 1) for pair in args.param or [])
    order_id = args.id or f"{args.kind}-{len(directive.orders) + 1}"
    # Build first so an invalid order never reaches disk.
    order = build_order(order_id, args.kind, params, available_executors())

    payload = directive.as_dict()
    payload["orders"].append(order.as_dict())
    if args.custom:
        payload["mode"] = "custom"

    from trainer_directives import parse_directive

    updated = parse_directive(payload, quest_ids, available_executors())
    save_directive(trainer_dir(args.agent), updated)
    print(f"ordem aceita: {order.id} — {order.title}")
    print("verificação : " + json.dumps(
        [dict(condition) for condition in order.success], ensure_ascii=False
    ))
    return 0


def cmd_reset(args, quest_ids) -> int:
    save_directive(trainer_dir(args.agent), default_directive())
    print(f"{args.agent.upper()}: diretiva restaurada para a história completa")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    show = subparsers.add_parser("show", help="mostrar a diretiva atual")
    show.add_argument("agent")
    show.set_defaults(handler=cmd_show)

    targets = subparsers.add_parser("targets", help="listar objetivos válidos p/ --stop-at")
    targets.add_argument("agent", nargs="?", default="AARON")
    targets.set_defaults(handler=cmd_targets)

    setter = subparsers.add_parser("set", help="definir modo e até onde jogar")
    setter.add_argument("agent")
    setter.add_argument("--mode", choices=["main_quest", "custom"])
    setter.add_argument("--stop-at", dest="stop_at", help="id do objetivo, ou 'none'")
    setter.add_argument(
        "--after-orders", dest="after_orders", choices=["stop", "main_quest"]
    )
    setter.set_defaults(handler=cmd_set)

    order = subparsers.add_parser("order", help="adicionar uma ordem custom")
    order.add_argument("agent")
    order.add_argument("--kind", required=True)
    order.add_argument("--param", action="append", metavar="CHAVE=VALOR")
    order.add_argument("--id")
    order.add_argument("--custom", action="store_true", help="também muda o modo")
    order.set_defaults(handler=cmd_order)

    reset = subparsers.add_parser("reset", help="voltar ao padrão (história completa)")
    reset.add_argument("agent")
    reset.set_defaults(handler=cmd_reset)

    args = parser.parse_args()
    quest_ids = tuple(node.id for node in QuestGraph.load(GRAPH_PATH).nodes)
    try:
        return args.handler(args, quest_ids)
    except DirectiveError as exc:
        print(f"ordem recusada: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
