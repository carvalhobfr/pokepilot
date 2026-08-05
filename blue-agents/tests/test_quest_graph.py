import unittest
from pathlib import Path

from quest_graph import QuestGraph


class FakeState:
    def __init__(self, *, flags=None, map_id=38, badges=0, party=0, pokeballs=0,
                 items=None, money=3000):
        self.flags = flags or set()
        self.map_id = map_id
        self.badges_mask = badges
        self.badge_count = badges.bit_count()
        self.party_count = party
        self.pokeballs = pokeballs
        self.items = items or {}
        self.money = money
        self.can_afford_pokeball = money >= 200

    def event_flag(self, address, bit):
        resolved = int(address, 0) if isinstance(address, str) else int(address)
        return (resolved, int(bit)) in self.flags

    def item_count(self, item_id):
        return self.items.get(int(item_id), 0)


class QuestGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        graph_path = Path(__file__).parents[1] / "knowledge/quests/main_quest_graph.json"
        cls.graph = QuestGraph.load(graph_path)

    def test_fresh_save_starts_at_start(self):
        self.assertEqual("start", self.graph.active_node(FakeState()).id)

    def test_ram_flags_advance_to_parcel(self):
        state = FakeState(flags={(0xD74B, 1), (0xD74B, 3)}, party=1)
        self.assertEqual("parcel_event", self.graph.active_node(state).id)

    def test_pokedex_without_balls_requires_balls(self):
        state = FakeState(
            flags={(0xD74B, 1), (0xD74B, 3), (0xD74B, 5)},
            party=1,
        )
        self.assertEqual("buy_pokeballs", self.graph.active_node(state).id)

    def test_transient_map_completion_can_be_sticky(self):
        state = FakeState(
            flags={(0xD74B, 1), (0xD74B, 3), (0xD74B, 5)},
            map_id=51,
            pokeballs=8,
        )
        completed = set(self.graph.completed_nodes(state))
        self.assertIn("route_2_nav", completed)

        state.map_id = 47
        self.assertEqual(
            "viridian_forest_nav",
            self.graph.active_node(state, completed).id,
        )

    def test_broke_trainer_is_not_stuck_on_the_shop(self):
        # Stocking is satisfied by "has the target" OR "cannot buy another".
        # Without the second branch a trainer who lost money to a whiteout would
        # never leave the shop node.
        flags = {(0xD74B, 1), (0xD74B, 3), (0xD74B, 5)}
        broke = FakeState(flags=flags, party=1, pokeballs=1, money=150)
        self.assertNotEqual("buy_pokeballs", self.graph.active_node(broke).id)

        rich = FakeState(flags=flags, party=1, pokeballs=1, money=3000)
        self.assertEqual("buy_pokeballs", self.graph.active_node(rich).id)

    def test_cerulean_requires_bill_ticket_before_misty(self):
        early_nodes = {node.id for node in self.graph.nodes[:9]}
        state = FakeState(map_id=3, badges=1, pokeballs=8)
        self.assertEqual("bill_quest", self.graph.active_node(state, early_nodes).id)

        state.items[63] = 1
        self.assertEqual(
            "cerulean_gym_quest",
            self.graph.active_node(state, early_nodes).id,
        )


if __name__ == "__main__":
    unittest.main()
