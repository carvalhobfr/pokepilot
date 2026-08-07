"""Sem golpe de dano, o turno ainda tem de sair — vencer ou perder, mas sair.

A fuga cobria isto e foi removida em 2026-08-07 a pedido do operador. "Ficar
até morrer" precisa que morrer seja possível: com todos os golpes de ataque
zerados e o único de status recusado pela preferência, o bot escolhia um slot
com 0 PP, o cartucho reabria "no PP", e nada acontecia. AARON gastou 7.650
passos numa única batalha contra um Kakuna.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from hybrid_agent import HybridGymEnv
from src.simple_battle import SimpleBattleAgent

from tests.rom_fixture import read_rom


class FakeMemory:
    def __init__(self, values):
        self.values = values

    def read_byte(self, address):
        return self.values.get(address, 0)

    def read_rom(self, bank, address):
        return read_rom(bank, address)


class SemGolpeDeDanoTests(unittest.TestCase):
    def cenario(self, moves, pps):
        """Bulbasaur contra Kakuna, com os PP que o caso exige."""
        valores = {
            0xCFE5: 8,      # Kakuna (interno) -> National #14
            0xCFE7: 20,
            0xCFEA: 7,      # Bug
            0xCFEB: 3,      # Poison
            0xD014: 153,    # Bulbasaur (interno) -> National #1
            0xD019: 22,     # Grass
            0xD01A: 3,      # Poison
            0xCC50: 106,
            0xCC26: 1,
        }
        for indice, (move_id, pp) in enumerate(zip(moves, pps)):
            valores[0xD01C + indice] = move_id
            valores[0xD02D + indice] = pp
        return FakeMemory(valores)

    def test_leech_seed_ja_usada_ainda_e_melhor_que_slot_sem_pp(self):
        # O caso do AARON: Tackle 0, Growl 0, Leech Seed 10 e já plantada.
        agent = SimpleBattleAgent()
        agent.leech_seed_used = True
        agent.get_action(self.cenario([33, 45, 73], [0, 0, 10]))
        self.assertEqual(73, agent.last_decision["selected_move_id"])

    def test_nunca_escolhe_um_golpe_esgotado(self):
        agent = SimpleBattleAgent()
        agent.leech_seed_used = True
        agent.get_action(self.cenario([33, 45, 73], [0, 0, 10]))
        escolhido = agent.last_decision["selected_move_id"]
        self.assertNotIn(escolhido, (33, 45), "slot com 0 PP reabre a caixa")

    def test_com_dano_disponivel_a_preferencia_segue_valendo(self):
        # Leech Seed já usada não deve ser escolhida quando há Tackle com PP.
        agent = SimpleBattleAgent()
        agent.leech_seed_used = True
        agent.get_action(self.cenario([33, 45, 73], [20, 30, 10]))
        self.assertEqual(33, agent.last_decision["selected_move_id"])

    def test_tudo_zerado_deixa_o_cartucho_forcar_struggle(self):
        agent = SimpleBattleAgent()
        agent.get_action(self.cenario([33, 45, 73], [0, 0, 0]))
        self.assertEqual(0, agent.last_decision["selected_move_id"])


class TrocaSoQuandoAlguemCaiTests(unittest.TestCase):
    """A troca voluntária emperrava; a forçada é a que funciona."""

    def env(self, party, active_slot=0):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.get_party_info = lambda: list(party)
        env.read_m = lambda address: active_slot if address == 0xCC2F else 0
        env.read_rom = read_rom
        return env

    HARDEN = {"hp": 6, "max_hp": 20, "moves": [{"id": 106, "pp": 20}]}
    TROVAO = {"hp": 15, "max_hp": 15, "moves": [{"id": 84, "pp": 30}]}
    CAIDO = {"hp": 0, "max_hp": 57, "moves": [{"id": 33, "pp": 35}]}

    def test_ativo_de_pe_sem_dano_nao_pede_troca(self):
        # Era o laço do BARON: pediu o slot 4 vinte vezes e nunca trocou.
        env = self.env([self.HARDEN, self.TROVAO], active_slot=0)
        self.assertIsNone(env._switch_target_slot())

    def test_ativo_caido_ainda_pede_troca(self):
        env = self.env([self.CAIDO, self.TROVAO], active_slot=0)
        self.assertEqual(1, env._switch_target_slot())

    def test_ativo_com_dano_nunca_pediu_troca(self):
        env = self.env([self.TROVAO, self.HARDEN], active_slot=0)
        self.assertIsNone(env._switch_target_slot())


if __name__ == "__main__":
    unittest.main()
