"""Per-trainer directives: what to play, how far, and which custom orders.

A directive is the typed contract between a human (or, later, a language
model) and the deterministic executors.  It never contains button inputs and
never contains free text that the runtime has to interpret at play time: every
order carries a success condition that the QuestGraph predicates can verify
against real cartridge RAM.

Keeping the schema independent from the emulator is deliberate.  The whole
loop — order in, RAM-verified completion out — is testable without PyBoy, so a
language model can be plugged in front of it later without changing any of the
rules below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path


DIRECTIVE_VERSION = 1

MODE_MAIN_QUEST = "main_quest"
MODE_CUSTOM = "custom"
MODES = (MODE_MAIN_QUEST, MODE_CUSTOM)

AFTER_ORDERS_STOP = "stop"
AFTER_ORDERS_MAIN_QUEST = "main_quest"
AFTER_ORDERS = (AFTER_ORDERS_STOP, AFTER_ORDERS_MAIN_QUEST)

# An order satisfied simply by advancing the story needs no dedicated
# controller; anything else must name one that actually exists.
MAIN_QUEST_EXECUTOR = "main_quest"

# Predicate kinds the QuestGraph can evaluate against RAM. An order whose
# success cannot be expressed with these is rejected at submission time rather
# than accepted and silently never completed.
VERIFIABLE_CONDITIONS = frozenset({
    "event_flag",
    "badge",
    "badge_count",
    "map_in",
    "party_count",
    "pokeballs",
    "pokeballs_stocked",
    "bag_item",
    "species_owned",
    "party_species",
    "party_max_level",
})


class DirectiveError(ValueError):
    """Raised with a human-readable reason when a directive is not executable."""


@dataclass(frozen=True)
class Order:
    id: str
    kind: str
    title: str
    params: dict
    success: tuple[dict, ...]
    executor: str = MAIN_QUEST_EXECUTOR

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "params": dict(self.params),
            "success": [dict(condition) for condition in self.success],
            "executor": self.executor,
        }


@dataclass(frozen=True)
class Directive:
    mode: str = MODE_MAIN_QUEST
    stop_at: str | None = None
    after_orders: str = AFTER_ORDERS_STOP
    orders: tuple[Order, ...] = ()
    constraints: tuple[dict, ...] = ()
    completed_orders: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict:
        return {
            "version": DIRECTIVE_VERSION,
            "mode": self.mode,
            "stop_at": self.stop_at,
            "after_orders": self.after_orders,
            "orders": [order.as_dict() for order in self.orders],
            "constraints": [dict(constraint) for constraint in self.constraints],
            "completed_orders": list(self.completed_orders),
        }

    def pending_orders(self) -> tuple[Order, ...]:
        done = set(self.completed_orders)
        return tuple(order for order in self.orders if order.id not in done)

    def with_completed(self, order_id: str) -> "Directive":
        if order_id in self.completed_orders:
            return self
        return Directive(
            mode=self.mode,
            stop_at=self.stop_at,
            after_orders=self.after_orders,
            orders=self.orders,
            constraints=self.constraints,
            completed_orders=self.completed_orders + (str(order_id),),
        )


def default_directive() -> Directive:
    """The product default: play the main story to its last node."""
    return Directive(mode=MODE_MAIN_QUEST, stop_at=None)


# --- order kinds -----------------------------------------------------------
#
# Each builder turns typed parameters into RAM predicates. Adding a kind here
# is what widens the vocabulary a planner (human or model) may compose.


def _require_int(params: dict, key: str, *, minimum: int, maximum: int) -> int:
    if key not in params:
        raise DirectiveError(f"parâmetro obrigatório ausente: '{key}'")
    try:
        value = int(params[key])
    except (TypeError, ValueError):
        raise DirectiveError(f"parâmetro '{key}' precisa ser um inteiro")
    if not minimum <= value <= maximum:
        raise DirectiveError(
            f"parâmetro '{key}' fora do intervalo permitido ({minimum}..{maximum})"
        )
    return value


def _build_own_species(params: dict):
    national_id = _require_int(params, "national_id", minimum=1, maximum=151)
    return (
        f"Capturar a espécie #{national_id} (confirmada na Pokédex)",
        ({"type": "species_owned", "national_id": national_id},),
        "farm_species",
    )


def _build_party_species(params: dict):
    national_id = _require_int(params, "national_id", minimum=1, maximum=151)
    return (
        f"Manter a espécie #{national_id} na equipe ativa",
        ({"type": "party_species", "national_id": national_id},),
        "farm_species",
    )


def _build_reach_level(params: dict):
    level = _require_int(params, "level", minimum=2, maximum=100)
    return (
        f"Treinar até que algum Pokémon da equipe alcance o nível {level}",
        ({"type": "party_max_level", "minimum": level},),
        MAIN_QUEST_EXECUTOR,
    )


def _build_collect_badges(params: dict):
    count = _require_int(params, "count", minimum=1, maximum=8)
    return (
        f"Conquistar {count} insígnia(s)",
        ({"type": "badge_count", "minimum": count},),
        MAIN_QUEST_EXECUTOR,
    )


def _build_reach_map(params: dict):
    map_id = _require_int(params, "map_id", minimum=0, maximum=247)
    return (
        f"Chegar ao mapa {map_id}",
        ({"type": "map_in", "values": [map_id]},),
        MAIN_QUEST_EXECUTOR,
    )


ORDER_KINDS = {
    "own_species": _build_own_species,
    "party_species": _build_party_species,
    "reach_level": _build_reach_level,
    "collect_badges": _build_collect_badges,
    "reach_map": _build_reach_map,
}


def build_order(
    order_id: str,
    kind: str,
    params: dict | None = None,
    available_executors=None,
) -> Order:
    """Compile typed parameters into an order with a verifiable predicate.

    ``available_executors`` is the set of controllers the runtime actually
    implements. Passing it turns "there is no controller for this yet" into an
    error at submission time instead of a bot that wanders and never finishes.
    """
    order_id = str(order_id).strip()
    if not order_id:
        raise DirectiveError("toda ordem precisa de um id não vazio")
    kind = str(kind).strip()
    if kind not in ORDER_KINDS:
        known = ", ".join(sorted(ORDER_KINDS))
        raise DirectiveError(
            f"tipo de ordem desconhecido: '{kind}'. Conhecidos: {known}"
        )
    params = dict(params or {})
    title, success, executor = ORDER_KINDS[kind](params)
    if available_executors is not None and executor != MAIN_QUEST_EXECUTOR:
        if executor not in set(available_executors):
            raise DirectiveError(
                f"ordem '{kind}' precisa do executor '{executor}', que ainda não "
                "existe no runtime; a ordem seria aceita mas nunca cumprida"
            )
    return Order(
        id=order_id,
        kind=kind,
        title=title,
        params=params,
        success=success,
        executor=executor,
    )


# --- validation ------------------------------------------------------------


def validate_condition(condition: dict) -> dict:
    if not isinstance(condition, dict):
        raise DirectiveError("cada condição de sucesso precisa ser um objeto")
    kind = condition.get("type")
    if kind not in VERIFIABLE_CONDITIONS:
        known = ", ".join(sorted(VERIFIABLE_CONDITIONS))
        raise DirectiveError(
            f"condição não verificável na RAM: '{kind}'. Verificáveis: {known}"
        )
    return dict(condition)


def parse_directive(
    payload: dict, known_quest_ids=(), available_executors=None
) -> Directive:
    """Validate a directive payload, rejecting anything not executable.

    ``known_quest_ids`` is the QuestGraph vocabulary; ``stop_at`` must name one
    of its nodes, otherwise the run would silently never reach its target.
    """
    if not isinstance(payload, dict):
        raise DirectiveError("a diretiva precisa ser um objeto JSON")

    version = int(payload.get("version", DIRECTIVE_VERSION))
    if version != DIRECTIVE_VERSION:
        raise DirectiveError(f"versão de diretiva não suportada: {version}")

    mode = str(payload.get("mode", MODE_MAIN_QUEST))
    if mode not in MODES:
        raise DirectiveError(
            f"modo inválido: '{mode}'. Use um de: {', '.join(MODES)}"
        )

    after_orders = str(payload.get("after_orders", AFTER_ORDERS_STOP))
    if after_orders not in AFTER_ORDERS:
        raise DirectiveError(
            f"after_orders inválido: '{after_orders}'. "
            f"Use um de: {', '.join(AFTER_ORDERS)}"
        )

    stop_at = payload.get("stop_at")
    if stop_at is not None:
        stop_at = str(stop_at)
        known = tuple(str(quest_id) for quest_id in known_quest_ids)
        if known and stop_at not in known:
            raise DirectiveError(
                f"stop_at desconhecido: '{stop_at}'. "
                f"Objetivos válidos: {', '.join(known)}"
            )

    orders = []
    seen_ids = set()
    for raw in payload.get("orders", []) or []:
        if not isinstance(raw, dict):
            raise DirectiveError("cada ordem precisa ser um objeto")
        order_id = str(raw.get("id", "")).strip()
        if not order_id:
            raise DirectiveError("toda ordem precisa de um id não vazio")
        if order_id in seen_ids:
            raise DirectiveError(f"id de ordem duplicado: '{order_id}'")
        seen_ids.add(order_id)

        order = build_order(
            order_id,
            raw.get("kind"),
            raw.get("params"),
            available_executors=available_executors,
        )
        # An explicit success list overrides the builder, but still has to be
        # made of predicates the runtime can actually confirm.
        if raw.get("success"):
            success = tuple(
                validate_condition(condition) for condition in raw["success"]
            )
            order = Order(
                id=order.id,
                kind=order.kind,
                title=str(raw.get("title") or order.title),
                params=order.params,
                success=success,
                executor=order.executor,
            )
        elif raw.get("title"):
            order = Order(
                id=order.id,
                kind=order.kind,
                title=str(raw["title"]),
                params=order.params,
                success=order.success,
                executor=order.executor,
            )
        if not order.success:
            raise DirectiveError(
                f"ordem '{order_id}' não tem condição de sucesso verificável"
            )
        orders.append(order)

    if mode == MODE_CUSTOM and not orders:
        raise DirectiveError("modo 'custom' exige pelo menos uma ordem")

    constraints = tuple(
        dict(constraint)
        for constraint in (payload.get("constraints") or [])
        if isinstance(constraint, dict)
    )

    completed = tuple(
        str(order_id) for order_id in (payload.get("completed_orders") or [])
    )
    unknown_completed = set(completed) - seen_ids
    if unknown_completed:
        raise DirectiveError(
            "completed_orders referencia ordens inexistentes: "
            + ", ".join(sorted(unknown_completed))
        )

    return Directive(
        mode=mode,
        stop_at=stop_at,
        after_orders=after_orders,
        orders=tuple(orders),
        constraints=constraints,
        completed_orders=completed,
    )


# --- persistence -----------------------------------------------------------


def directive_path(trainer_dir: Path) -> Path:
    return Path(trainer_dir) / "directives.json"


def load_directive(
    trainer_dir: Path, known_quest_ids=(), available_executors=None
) -> Directive:
    """Read a trainer's directive, falling back to the main-story default.

    A malformed file must not silently become "play everything": it raises, so
    the operator sees the reason instead of a bot quietly ignoring the order.
    """
    path = directive_path(trainer_dir)
    if not path.is_file():
        return default_directive()
    with open(path, "r", encoding="utf-8") as source:
        payload = json.load(source)
    return parse_directive(payload, known_quest_ids, available_executors)


def save_directive(trainer_dir: Path, directive: Directive) -> Path:
    path = directive_path(trainer_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as output:
        json.dump(directive.as_dict(), output, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    return path


def target_quest_ids(directive: Directive, quest_ids) -> tuple[str, ...]:
    """Quest ids that must be complete for this directive to be finished.

    ``stop_at`` is inclusive: "vai até Brock" means Brock's node counts as the
    final one. In custom mode the story is not the completion target unless the
    directive explicitly falls back to it.
    """
    quest_ids = tuple(str(quest_id) for quest_id in quest_ids)
    if directive.mode == MODE_CUSTOM and directive.after_orders != AFTER_ORDERS_MAIN_QUEST:
        return ()
    if directive.stop_at is None:
        return quest_ids
    if directive.stop_at not in quest_ids:
        raise DirectiveError(f"stop_at fora do grafo: '{directive.stop_at}'")
    return quest_ids[: quest_ids.index(directive.stop_at) + 1]


def story_is_needed(directive: Directive) -> bool:
    """True when the story must keep running regardless of ``mode``.

    An order such as "treinar até o nível 20" is satisfied *by* playing the
    story, so bounding the story away would make that order unreachable. The
    order's own RAM predicate is what ends the run.
    """
    return any(
        order.executor == MAIN_QUEST_EXECUTOR
        for order in directive.pending_orders()
    )


def directive_is_complete(directive: Directive, quest_ids, completed_quest_ids) -> bool:
    """True when every targeted quest and every pending order is confirmed.

    ``quest_ids`` must be the graph's own order, since ``stop_at`` is defined
    as a prefix of the story rather than as a set membership test.
    """
    if directive.pending_orders():
        return False
    targets = target_quest_ids(directive, quest_ids)
    if not targets:
        # Custom-only directive: completion is decided purely by its orders,
        # and an order-less custom directive can never be built (see parse).
        return bool(directive.orders)
    completed = {str(quest_id) for quest_id in completed_quest_ids}
    return set(targets).issubset(completed)
