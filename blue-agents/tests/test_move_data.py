"""Golpe que existe no cartucho não pode virar status por falta de tabela."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.move_data import MOVE_COUNT, MoveTable
from src.simple_battle import SimpleBattleAgent

from tests.rom_fixture import MOVES, read_rom


class FakeMemory:
    def __init__(self, values):
        self.values = values

    def read_byte(self, address):
        return self.values.get(address, 0)

    def read_rom(self, bank, address):
        return read_rom(bank, address)


class MoveTableTests(unittest.TestCase):
    def test_le_os_cento_e_sessenta_e_cinco_golpes(self):
        self.assertEqual(MOVE_COUNT, len(MOVES))

    def test_bate_com_os_valores_canonicos(self):
        # Cinco pontos de conferência espalhados pela tabela.
        for move_id, power, type_name, pp in [
            (1, 40, "NORMAL", 35),      # Pound
            (33, 35, "NORMAL", 35),     # Tackle
            (45, 0, "NORMAL", 40),      # Growl
            (84, 40, "ELECTRIC", 30),   # Thundershock
            (85, 95, "ELECTRIC", 15),   # Thunderbolt
            (56, 120, "WATER", 5),      # Hydro Pump
        ]:
            move = MOVES.get(move_id)
            self.assertEqual(power, move.power, f"potência do golpe {move_id}")
            self.assertEqual(type_name, move.type, f"tipo do golpe {move_id}")
            self.assertEqual(pp, move.pp, f"PP do golpe {move_id}")

    def test_o_golpe_que_faltava_na_tabela_escrita_a_mao(self):
        # A tabela antiga tinha 85 (Thunderbolt) e não 84 (Thundershock).
        self.assertTrue(MOVES.is_damaging(84))

    def test_desconhecido_responde_none_em_vez_de_zero(self):
        vazia = MoveTable()
        self.assertIsNone(vazia.power(84))
        self.assertFalse(vazia.is_damaging(84))

    def test_tabela_vazia_quando_ninguem_sabe_ler_rom(self):
        self.assertEqual(0, len(MoveTable.from_memory(object())))


class GrowlNoLongerWinsTests(unittest.TestCase):
    def test_pikachu_ataca_com_thundershock_e_nao_com_growl(self):
        agent = SimpleBattleAgent()
        memory = FakeMemory({
            0xCFE5: 165,   # Rattata (interno) -> National #19
            0xCFE7: 20,
            0xCFEA: 0,     # Normal
            0xCFEB: 0,
            0xD014: 84,    # Pikachu (interno) -> National #25
            0xD019: 23,    # Electric
            0xD01A: 23,
            0xD01C: 45,    # slot 0: Growl
            0xD01D: 84,    # slot 1: Thundershock
            0xD02D: 40,    # PP do Growl
            0xD02E: 30,    # PP do Thundershock
            0xCC50: 106,   # lista de golpes aberta
            0xCC26: 1,
        })

        agent.get_action(memory)

        self.assertEqual(84, agent.last_decision["selected_move_id"])
        self.assertEqual(40, agent.last_decision["selected"]["power"])
        self.assertEqual("ELECTRIC", agent.last_decision["selected"]["type"])

    def test_so_growl_disponivel_ainda_usa_growl(self):
        # Sem golpe de dano com PP, o de status continua sendo a jogada.
        agent = SimpleBattleAgent()
        memory = FakeMemory({
            0xCFE5: 165,
            0xCFE7: 20,
            0xCFEA: 0,
            0xCFEB: 0,
            0xD014: 84,
            0xD019: 23,
            0xD01A: 23,
            0xD01C: 45,    # Growl
            0xD01D: 84,    # Thundershock, sem PP
            0xD02D: 40,
            0xD02E: 0,
            0xCC50: 106,
            0xCC26: 1,
        })

        agent.get_action(memory)

        self.assertEqual(45, agent.last_decision["selected_move_id"])


if __name__ == "__main__":
    unittest.main()
