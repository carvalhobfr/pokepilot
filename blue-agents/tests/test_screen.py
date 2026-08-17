"""A tela como fonte de verdade, num decodificador só.

`0xCC50` significa coisas diferentes em cinco contextos; a tela não. Foi ela
que acertou nas três vezes em que foi consultada em 2026-08-16: `ABLE/NOT
ABLE` disse quem aprende Cut, `NICKNAME` achou o teclado, `is already out!`
explicou a recusa da troca.

Os valores de cada tela aqui saíram do cartucho e já viviam espalhados por
`scripted_agent.py`, `simple_battle.py` e `hybrid_agent.py` — o teste existe
para que continuem significando a mesma coisa nos três.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src import screen


class FakeScreen:
    """O `wTileMap` e os bytes de estado, como o cartucho os escreve."""

    def __init__(self, lines=(), corner=(0, 0), cc50=0, text_box=0,
                 in_battle=0, party_count=0, last_row=0, shop_menu=0,
                 transaction=0, lcd_window=screen.LCD_WINDOW_PARKED):
        self.tiles = [0x00] * screen.SCREEN_TILES
        for row, line in enumerate(lines):
            for column, character in enumerate(line[:screen.SCREEN_WIDTH]):
                self.tiles[row * screen.SCREEN_WIDTH + column] = _tile(character)
        self.corner = corner
        self.cc50 = cc50
        self.text_box = text_box
        self.in_battle = in_battle
        self.party_count = party_count
        self.last_row = last_row
        self.shop_menu = shop_menu
        self.transaction = transaction
        self.lcd_window = lcd_window

    def read_byte(self, address):
        if screen.SCREEN_TILEMAP_ADDRESS <= address < (
            screen.SCREEN_TILEMAP_ADDRESS + screen.SCREEN_TILES
        ):
            return self.tiles[address - screen.SCREEN_TILEMAP_ADDRESS]
        return {
            screen.MENU_TOP_Y_ADDRESS: self.corner[0],
            screen.MENU_TOP_X_ADDRESS: self.corner[1],
            screen.MENU_LAST_ROW_ADDRESS: self.last_row,
            screen.BATTLE_MENU_STATE_ADDRESS: self.cc50,
            screen.SHOP_MENU_ADDRESS: self.shop_menu,
            screen.SHOP_TRANSACTION_ADDRESS: self.transaction,
            screen.TEXT_BOX_ADDRESS: self.text_box,
            screen.IN_BATTLE_ADDRESS: self.in_battle,
            screen.PARTY_COUNT_ADDRESS: self.party_count,
            screen.LCD_WINDOW_ADDRESS: self.lcd_window,
        }.get(address, 0)


def _tile(character):
    if "A" <= character <= "Z":
        return 0x80 + ord(character) - ord("A")
    if "a" <= character <= "z":
        return 0xA0 + ord(character) - ord("a")
    if "0" <= character <= "9":
        return 0xF6 + ord(character) - ord("0")
    return 0x7F


class DecodificacaoTests(unittest.TestCase):
    def test_as_18_linhas_saem_com_20_colunas(self):
        drawn = screen.rows(FakeScreen().read_byte)
        self.assertEqual(screen.SCREEN_HEIGHT, len(drawn))
        self.assertTrue(all(len(line) == screen.SCREEN_WIDTH for line in drawn))

    def test_maiuscula_minuscula_digito_e_espaco(self):
        line = screen.rows(FakeScreen(["Ab 90"]).read_byte)[0]
        self.assertTrue(line.startswith("Ab 90"))

    def test_cenario_nao_vira_letra(self):
        # Tile fora das faixas de texto é ".", nunca um caractere inventado.
        self.assertEqual("." * screen.SCREEN_WIDTH,
                         screen.rows(FakeScreen().read_byte)[0].replace(" ", "."))

    def test_linhas_visiveis_deixam_o_cenario_de_fora(self):
        visible = screen.visible_lines(FakeScreen(["", "IVYSAUR"]).read_byte)
        self.assertEqual(["IVYSAUR"], visible)


class ClassificacaoTests(unittest.TestCase):
    def test_o_teclado_se_identifica_pelo_proprio_cabecalho(self):
        # E vem antes de tudo: em batalha ou não, A nesta tela digita letra.
        keyboard = FakeScreen(["NICKNAME"], in_battle=1, cc50=106)
        self.assertEqual(screen.TECLADO_NOME, screen.classify(keyboard.read_byte))

    def test_lista_de_golpes_e_seletor_2x2_pelo_cc50(self):
        self.assertEqual(
            screen.LISTA_GOLPES,
            screen.classify(FakeScreen(in_battle=1, cc50=106).read_byte),
        )
        self.assertEqual(
            screen.MENU_BATALHA,
            screen.classify(FakeScreen(in_battle=1, cc50=94).read_byte),
        )

    def test_qualquer_outro_cc50_em_batalha_e_texto(self):
        # 5 é o valor durante "Nothing happened!" — e a coluna sozinha não
        # distingue, que é o erro que o gate de texto pagou duas vezes.
        self.assertEqual(
            screen.TEXTO_BATALHA,
            screen.classify(FakeScreen(in_battle=1, cc50=5).read_byte),
        )

    def test_a_lista_da_equipe_se_identifica_pela_forma(self):
        # Última linha selecionável = último Pokémon, cursor na coluna zero.
        party = FakeScreen(in_battle=1, cc50=94, party_count=3, last_row=2)
        self.assertEqual(screen.LISTA_EQUIPE, screen.classify(party.read_byte))

    def test_cada_canto_de_menu_tem_nome(self):
        for corner, expected in (
            (screen.MENU_MAIN, screen.MENU_PRINCIPAL),
            (screen.MENU_BAG, screen.MOCHILA),
            (screen.MENU_ITEM_USE_TOSS, screen.USAR_JOGAR_FORA),
            (screen.MENU_TEACH_YES_NO, screen.SIM_NAO),
            (screen.MENU_PARTY, screen.LISTA_EQUIPE),
            (screen.MENU_FORGET_MOVE, screen.ESQUECER_GOLPE),
        ):
            self.assertEqual(
                expected,
                screen.classify(FakeScreen(corner=corner, text_box=1).read_byte),
                f"canto {corner}",
            )

    def test_o_balcao_do_mart_separa_lista_de_quantidade(self):
        self.assertEqual(
            screen.LISTA_MART,
            screen.classify(FakeScreen(transaction=123).read_byte),
        )
        self.assertEqual(
            screen.QUANTIDADE,
            screen.classify(
                FakeScreen(transaction=123, shop_menu=161).read_byte
            ),
        )
        self.assertEqual(
            screen.COMPRA_VENDA,
            screen.classify(FakeScreen(shop_menu=32).read_byte),
        )

    def test_caixa_de_texto_sem_menu_conhecido_e_texto(self):
        self.assertEqual(
            screen.TEXTO,
            screen.classify(FakeScreen(corner=(9, 9), text_box=1).read_byte),
        )

    def test_janela_estacionada_e_o_mapa(self):
        self.assertEqual(screen.OVERWORLD, screen.classify(FakeScreen().read_byte))

    def test_tela_que_nenhum_sinal_medido_explica_e_desconhecida(self):
        # É este valor que vira evento em vez de `press A` calado.
        unknown = FakeScreen(corner=(9, 9), lcd_window=0)
        self.assertEqual(screen.DESCONHECIDA, screen.classify(unknown.read_byte))


class RelatorioTests(unittest.TestCase):
    def test_descricao_traz_a_tela_e_o_que_a_sustenta(self):
        drawn = FakeScreen(["", "IVYSAUR   ABLE"], in_battle=1, cc50=106)
        description = screen.describe(drawn.read_byte)
        self.assertEqual(screen.LISTA_GOLPES, description["tela"])
        self.assertEqual(106, description["cc50"])
        self.assertIn("IVYSAUR   ABLE", description["linhas"])


if __name__ == "__main__":
    unittest.main()
