"""Executable, RAM-verified quest graph for Pokémon Red/Blue."""

from dataclasses import dataclass
import json
from pathlib import Path


POKEBALL_PRICE = 200


@dataclass(frozen=True)
class QuestNode:
    id: str
    title: str
    executor: str
    success: tuple[dict, ...]


class QuestGraph:
    """Ordered story graph whose nodes are completed only by game state.

    The first version is a linear main story. The condition format already
    supports reusable branches and loops, such as healing, buying items and
    retrying a rare encounter, without making scripts declare themselves done.
    """

    def __init__(self, nodes):
        self.nodes = tuple(nodes)
        self.nodes_by_id = {node.id: node for node in self.nodes}

    @classmethod
    def load(cls, path):
        with open(Path(path), "r", encoding="utf-8") as graph_file:
            payload = json.load(graph_file)
        return cls(
            QuestNode(
                id=node["id"],
                title=node["title"],
                executor=node.get("executor", node["id"]),
                success=tuple(node.get("success", [])),
            )
            for node in payload["nodes"]
        )

    def active_node(self, state, completed=()):
        completed = set(completed)
        for node in self.nodes:
            if node.id in completed:
                continue
            if not all(self._matches(condition, state) for condition in node.success):
                return node
        return None

    def completed_nodes(self, state, completed=()):
        sticky = set(completed)
        completed = []
        for node in self.nodes:
            if node.id in sticky or all(
                self._matches(condition, state) for condition in node.success
            ):
                completed.append(node.id)
            else:
                break
        return completed

    def node_matches(self, node, state):
        return all(self._matches(condition, state) for condition in node.success)

    @staticmethod
    def _matches(condition, state):
        kind = condition.get("type")
        if kind == "event_flag":
            return state.event_flag(condition["address"], condition["bit"])
        if kind == "badge":
            return bool(state.badges_mask & (1 << int(condition["index"])))
        if kind == "badge_count":
            return state.badge_count >= int(condition["minimum"])
        if kind == "map_in":
            return state.map_id in {int(map_id) for map_id in condition["values"]}
        if kind == "party_count":
            return state.party_count >= int(condition["minimum"])
        if kind == "pokeballs":
            return state.pokeballs >= int(condition["minimum"])
        # "Estocado" = tem o alvo, ou não tem como comprar mais. Sem o segundo
        # ramo um treinador sem dinheiro ficaria preso no nó para sempre.
        if kind == "pokeballs_stocked":
            return (
                state.pokeballs >= int(condition["minimum"])
                or not state.can_afford_pokeball
            )
        if kind == "bag_item":
            return state.item_count(int(condition["item_id"])) >= int(
                condition.get("minimum", 1)
            )
        # Order predicates. ``species_owned`` reads the Pokédex "owned" bit, so
        # a Pokémon sent to the PC still counts; ``party_species`` requires it
        # to be carried right now.
        if kind == "species_owned":
            return state.owns_species(int(condition["national_id"]))
        if kind == "party_species":
            return int(condition["national_id"]) in state.party_national_ids
        if kind == "party_max_level":
            return state.party_max_level >= int(condition["minimum"])
        raise ValueError(f"Unknown quest condition: {kind}")


class LiveQuestState:
    """Small read-only view over the emulator state used by quest predicates."""

    def __init__(self, env):
        self.env = env
        self.map_id = int(env.read_m(0xD35E))
        self.party_count = int(env.read_m(0xD163))
        self.badges_mask = int(env.read_m(0xD356))
        self.badge_count = self.badges_mask.bit_count()
        self.pokeballs = int(env._poke_ball_count())
        self.money = int(env._read_money())
        self.can_afford_pokeball = self.money >= POKEBALL_PRICE
        self.party_national_ids = frozenset(self._read_party_national_ids())
        self.party_max_level = max(self._read_party_levels(), default=0)

    def _read_party_national_ids(self):
        from pokemon_ids import get_national_id

        for index in range(min(self.party_count, 6)):
            internal_id = int(self.env.read_m(0xD16B + index * 44))
            national_id = int(get_national_id(internal_id))
            if national_id:
                yield national_id

    def _read_party_levels(self):
        # Offset 33 of the party struct is the live level; offset 3 is only
        # kept in sync for boxed Pokémon.
        return [
            int(self.env.read_m(0xD16B + index * 44 + 33))
            for index in range(min(self.party_count, 6))
        ]

    def event_flag(self, address, bit):
        resolved = int(address, 0) if isinstance(address, str) else int(address)
        return bool(int(self.env.read_m(resolved)) & (1 << int(bit)))

    def item_count(self, item_id):
        return int(self.env._bag_item_count(int(item_id)))

    def owns_species(self, national_id):
        return bool(self.env._pokedex_owns(int(national_id)))
