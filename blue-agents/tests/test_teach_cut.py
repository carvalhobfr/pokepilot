"""Ensinar o Cut, dirigindo os menus reais — cada tela medida no cartucho.

Sequência fixa de botões não serve aqui, e o teste existe por causa disso: o
número de caixas de texto **varia** (a mensagem "não cabe mais golpe" só
aparece com quatro golpes), e um D apertado durante o texto é comido, o que
dessincroniza tudo o que vem depois. Medido em 2026-08-16, no save do AARON
logo depois do capitão do S.S. Anne: tentar por sequência fixa voltou para a
mochila três vezes antes de eu desistir e ler a tela.

Cada tela é reconhecida pelo canto do menu (`wTopMenuItemY`/`X`, 0xCC24/0xCC25),
os valores anotados abaixo saíram da corrida real:

    menu principal   (2, 11)   POKéDEX / POKéMON / ITEM / ...
    mochila          (4, 5)    3 linhas visíveis, índice = rolagem + cursor
    USE / TOSS       (11, 14)
    "Teach CUT?"     (8, 15)   SIM em cima
    lista da party   (1, 0)    "Use TM on which POKéMON?"
    esquecer golpe   (8, 5)    "Which move should be forgotten?"

E o desfecho medido: `IVYSAUR learned CUT!`, com a party em [77, 15, 73, 22].
A **Butterfree não aprende Cut** — a tela escreve NOT ABLE ao lado dela —,
então "ensinar a quem não é o inicial" não era escolha: o cartucho recusa.
"""

import sys
import unittest
from pathlib import Path

from pyboy.utils import WindowEvent

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.scripted_agent import (
    CUT_MOVE_ID,
    HM01_CUT,
    MENU_BAG,
    MENU_FORGET_MOVE,
    MENU_ITEM_USE_TOSS,
    MENU_MAIN,
    MENU_PARTY,
    MENU_TEACH_YES_NO,
    TEACH_MENU_STEP_LIMIT,
    ScriptedAgent,
)

IVYSAUR_MOVES = [77, 45, 73, 22]      # PoisonPowder, Growl, Leech Seed, Vine Whip
BUTTERFREE_MOVES = [33, 81, 18, 60]

# A tela da party como o cartucho a desenhou, com o Ivysaur ABLE e a
# Butterfree NOT ABLE.
PARTY_SCREEN = [
    "   IVYSAUR   .23",
    ">           ABLE",
    "   BUTTERFREE.40",
    "            NOT ABLE",
]


class TeachMemory:
    def __init__(self, bag, party, menu=None, cursor=0, scroll=0, menu_open=True):
        self.bag = list(bag.items())
        self.party = list(party)
        self.menu = menu or (0, 0)
        self.cursor = cursor
        self.scroll = scroll
        self.menu_open = menu_open

    def get_party_count(self):
        return len(self.party)

    def get_map_id(self):
        return 5

    def get_player_pos(self):
        return (19, 0)

    def read_byte(self, address):
        if address == 0xCFC4:
            return 1 if self.menu_open else 0
        if address == 0xCC24:
            return self.menu[0]
        if address == 0xCC25:
            return self.menu[1]
        if address == 0xCC26:
            return self.cursor
        if address == 0xCC36:
            return self.scroll
        if address == 0xD163:
            return len(self.party)
        if 0xD16B <= address < 0xD16B + 44 * max(len(self.party), 1):
            slot, offset = divmod(address - 0xD16B, 44)
            if slot < len(self.party) and 8 <= offset <= 11:
                return self.party[slot][offset - 8]
            return 0
        if address == 0xD31D:
            return len(self.bag)
        if 0xD31E <= address < 0xD31E + 2 * len(self.bag):
            index, offset = divmod(address - 0xD31E, 2)
            item_id, count = self.bag[index]
            return item_id if offset == 0 else count
        return 0


class TeachCutTests(unittest.TestCase):
    def agent(self, menu=None, cursor=0, scroll=0, menu_open=True,
              party=None, bag=None, screen=None):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        memory = TeachMemory(
            bag if bag is not None else {HM01_CUT: 1},
            party if party is not None else [IVYSAUR_MOVES, BUTTERFREE_MOVES],
            menu, cursor, scroll, menu_open,
        )
        agent.emulator = type("FakeEmulator", (), {"memory": memory})()
        agent.memory_probe = memory
        if screen is not None:
            agent._screen_rows = lambda: list(screen)
        return agent

    # --- quem decide que acabou é o cartucho -----------------------------

    def test_com_o_golpe_na_party_nao_ha_nada_a_fazer(self):
        agent = self.agent(party=[[77, CUT_MOVE_ID, 73, 22]])
        self.assertIsNone(agent._teach_cut_action())

    def test_sem_o_hm_na_mochila_nao_ha_nada_a_fazer(self):
        agent = self.agent(bag={})
        self.assertIsNone(agent._teach_cut_action())

    def test_fora_de_menu_o_primeiro_passo_e_start(self):
        agent = self.agent(menu_open=False)
        self.assertEqual(WindowEvent.PRESS_BUTTON_START, agent._teach_cut_action())

    # --- uma tela de cada vez, todas medidas ------------------------------

    def test_no_menu_principal_o_cursor_desce_ate_ITEM(self):
        agent = self.agent(menu=MENU_MAIN, cursor=0)
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent._teach_cut_action())
        agent = self.agent(menu=MENU_MAIN, cursor=2)
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._teach_cut_action())

    def test_na_mochila_o_indice_e_rolagem_mais_cursor(self):
        # HM01 é o sétimo item: índice 6 = rolagem 4 + cursor 2.
        bag = {0xEA: 1, 0x2A: 1, 0x31: 1, 0x3F: 1, 0xD3: 1, 0xE4: 1, HM01_CUT: 1}
        agent = self.agent(menu=MENU_BAG, cursor=0, scroll=0, bag=bag)
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent._teach_cut_action())
        agent = self.agent(menu=MENU_BAG, cursor=2, scroll=4, bag=bag)
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._teach_cut_action())

    def test_no_submenu_a_escolha_e_USE(self):
        agent = self.agent(menu=MENU_ITEM_USE_TOSS, cursor=0)
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._teach_cut_action())
        agent = self.agent(menu=MENU_ITEM_USE_TOSS, cursor=1)
        self.assertEqual(WindowEvent.PRESS_ARROW_UP, agent._teach_cut_action())

    def test_no_sim_ou_nao_a_resposta_e_sim(self):
        agent = self.agent(menu=MENU_TEACH_YES_NO, cursor=1)
        self.assertEqual(WindowEvent.PRESS_ARROW_UP, agent._teach_cut_action())
        agent = self.agent(menu=MENU_TEACH_YES_NO, cursor=0)
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._teach_cut_action())

    def test_a_party_escolhe_quem_a_tela_marca_ABLE(self):
        # Cursor na Butterfree (NOT ABLE): sobe para o Ivysaur.
        agent = self.agent(menu=MENU_PARTY, cursor=1, screen=PARTY_SCREEN)
        self.assertEqual(WindowEvent.PRESS_ARROW_UP, agent._teach_cut_action())
        agent = self.agent(menu=MENU_PARTY, cursor=0, screen=PARTY_SCREEN)
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._teach_cut_action())

    def test_ninguem_ABLE_fecha_o_menu_em_vez_de_insistir(self):
        screen = ["   BUTTERFREE.40", "            NOT ABLE"]
        agent = self.agent(menu=MENU_PARTY, cursor=0, screen=screen)
        self.assertEqual(WindowEvent.PRESS_BUTTON_B, agent._teach_cut_action())

    def test_o_golpe_esquecido_e_o_pior_status_nao_o_de_dano(self):
        # Ivysaur: PoisonPowder(3), Growl(9), Leech Seed(0), Vine Whip(dano).
        # Growl é o pior pela mesma régua que o controlador de batalha usa.
        agent = self.agent(menu=MENU_FORGET_MOVE, cursor=0, screen=PARTY_SCREEN)
        agent.teach_cut_party_slot = 0
        self.assertEqual(1, agent._move_slot_to_forget(0))
        self.assertEqual(WindowEvent.PRESS_ARROW_DOWN, agent._teach_cut_action())
        agent = self.agent(menu=MENU_FORGET_MOVE, cursor=1, screen=PARTY_SCREEN)
        agent.teach_cut_party_slot = 0
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._teach_cut_action())

    def test_um_hm_nunca_e_o_golpe_esquecido(self):
        # O cartucho recusa apagar HM: escolher um seria entrar em ciclo.
        agent = self.agent(party=[[CUT_MOVE_ID, 45, 73, 22]])
        self.assertNotEqual(0, agent._move_slot_to_forget(0))

    def test_tela_desconhecida_com_menu_aberto_e_texto(self):
        agent = self.agent(menu=(9, 9))
        self.assertEqual(WindowEvent.PRESS_BUTTON_A, agent._teach_cut_action())

    def test_menu_que_nao_se_comporta_e_abandonado_com_B(self):
        agent = self.agent(menu=(9, 9))
        agent.teach_cut_steps = TEACH_MENU_STEP_LIMIT
        self.assertEqual(WindowEvent.PRESS_BUTTON_B, agent._teach_cut_action())


if __name__ == "__main__":
    unittest.main()
