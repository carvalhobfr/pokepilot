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
        # Gate de texto por cursor: menu de golpes desenhado = coluna 9/15;
        # texto = 5. O 0xD125 lê 1 sempre (2026-08-12). Padrão: menu aberto.
        if address == 0xCC25 and address not in self.values:
            return 9
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


class DanoNuncaPerdeParaStatusTests(unittest.TestCase):
    """No desempate, golpe de dano vem antes de Growl — sempre.

    A tabela de prioridade ordena *entre* golpes de status: Growl vale 9, e um
    golpe de ataque sem entrada cai no padrão 50. Growl ganhava de Tackle e de
    Vine Whip.

    Isso só entra em cena quando a lista de candidatos vem vazia por leitura
    ruim — o controlador é chamado com texto ainda na tela e `0xD01C` não é o
    menu de golpes ainda. Medido: 10 decisões seguidas, todas com
    `battle_text: 1`, `battle_menu` em 172/10/54/95/247, e Growl escolhido em 8.
    """

    def cenario(self, moves, pps, tipo_inimigo=(0, 0)):
        valores = {
            0xCFE5: 165, 0xCFE7: 20,
            0xCFEA: tipo_inimigo[0], 0xCFEB: tipo_inimigo[1],
            0xD014: 153, 0xD019: 22, 0xD01A: 3,
            0xCC50: 106, 0xCC26: 1,
        }
        for i, (mid, pp) in enumerate(zip(moves, pps)):
            valores[0xD01C + i] = mid
            valores[0xD02D + i] = pp
        return FakeMemory(valores)

    def test_tackle_ganha_de_growl_no_desempate(self):
        agent = SimpleBattleAgent()
        # Leech Seed já plantada força o caminho do desempate.
        agent.leech_seed_used = True
        agent.get_action(self.cenario([45, 33, 73], [40, 35, 10]))
        self.assertEqual(33, agent.last_decision["selected_move_id"])

    def test_o_mais_forte_ganha_entre_dois_de_dano(self):
        agent = SimpleBattleAgent()
        agent.leech_seed_used = True
        agent.get_action(self.cenario([45, 33, 22], [40, 35, 10]))
        self.assertIn(agent.last_decision["selected_move_id"], (33, 22))

    def test_sem_golpe_de_dano_o_status_ainda_decide(self):
        agent = SimpleBattleAgent()
        agent.get_action(self.cenario([45, 73], [40, 10]))
        self.assertEqual(73, agent.last_decision["selected_move_id"],
                         "Leech Seed vale mais que Growl")


class StatusValeUmaVezPorBatalhaTests(unittest.TestCase):
    """Growl tem 40 PP e o atributo para de descer no mínimo.

    O bot passava a batalha inteira baixando um ataque que já estava no fundo,
    perdia, e não subia de nível. A ordem que o operador pediu em 2026-08-08:
    dano primeiro, depois efeito no inimigo uma vez, depois o resto.
    """

    def cenario(self, moves, pps):
        valores = {
            0xCFE5: 165, 0xCFE7: 20, 0xCFEA: 0, 0xCFEB: 0,
            0xD014: 153, 0xD019: 22, 0xD01A: 3,
            0xCC50: 106, 0xCC26: 1,
        }
        for i, (mid, pp) in enumerate(zip(moves, pps)):
            valores[0xD01C + i] = mid
            valores[0xD02D + i] = pp
        return FakeMemory(valores)

    def test_nenhum_status_repete_antes_de_todos_terem_vez(self):
        # A garantia real. Depois que todos foram usados a batalha já está
        # perdida — repetir é melhor que escolher slot vazio, que foi o
        # travamento de 7.650 passos.
        agent = SimpleBattleAgent()
        memoria = self.cenario([45, 73], [40, 10])
        escolhidos = []
        for _ in range(2):
            agent.get_action(memoria)
            escolhidos.append(agent.last_decision["selected_move_id"])
        self.assertEqual({45, 73}, set(escolhidos),
                         f"cada um tem a sua vez antes de repetir: {escolhidos}")

    def test_growl_nao_queima_quarenta_pp(self):
        # O sintoma que o operador viu: Growl repetido até zerar.
        agent = SimpleBattleAgent()
        memoria = self.cenario([45, 73], [40, 10])
        growls = 0
        for _ in range(10):
            agent.get_action(memoria)
            if agent.last_decision["selected_move_id"] == 45:
                growls += 1
        self.assertLessEqual(growls, 5, "Growl não pode dominar a batalha")

    def test_a_semente_vem_antes_do_growl(self):
        agent = SimpleBattleAgent()
        agent.get_action(self.cenario([45, 73], [40, 10]))
        self.assertEqual(73, agent.last_decision["selected_move_id"])

    def test_gastos_todos_ainda_devolve_um_golpe_com_pp(self):
        # Sem opção nova, é melhor repetir que escolher slot vazio.
        agent = SimpleBattleAgent()
        memoria = self.cenario([45], [40])
        for _ in range(3):
            agent.get_action(memoria)
        self.assertEqual(45, agent.last_decision["selected_move_id"])

    def test_nova_batalha_zera_a_contagem(self):
        agent = SimpleBattleAgent()
        memoria = self.cenario([45, 73], [40, 10])
        agent.get_action(memoria)
        agent.reset_battle()
        self.assertEqual(set(), agent.status_moves_used)

if __name__ == "__main__":
    unittest.main()
