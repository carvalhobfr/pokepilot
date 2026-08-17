"""A tela decodificada, num lugar só.

Três arquivos deste projeto liam o `wTileMap` (0xC3A0) por conta própria e cada
controlador decorava os seus bytes de "estado de menu" — 12 endereços
diferentes espalhados por três arquivos. Os sete travamentos de 2026-08-16
terminaram todos do mesmo jeito: uma tela que ninguém sabia nomear, um `press
A` ou um `return None` calado.

A tela acertou nas três vezes em que foi usada naquele dia: `ABLE/NOT ABLE`
disse quem aprende Cut, `NICKNAME` achou o teclado, `is already out!` explicou
a recusa da troca. É RAM, é o que o jogador vê, e não é ambíguo — enquanto
`0xCC50` significa coisas diferentes em cinco contextos.

Cada sinal daqui foi medido no cartucho e já vivia em algum controlador; este
módulo é onde eles passam a viver juntos. Nada foi deduzido.

Todas as funções recebem `read_byte`, um callable `(endereço) -> int`. É o
menor denominador comum entre os três chamadores: o `EmulatorAdapter` do
hybrid, o `emulator.memory` do `ScriptedAgent` e o `emulator` do controlador de
batalha.
"""

# wTileMap: 20x18 tiles do que está desenhado. É RAM, não ROM.
SCREEN_TILEMAP_ADDRESS = 0xC3A0
SCREEN_WIDTH, SCREEN_HEIGHT = 20, 18
SCREEN_TILES = SCREEN_WIDTH * SCREEN_HEIGHT

# wTopMenuItemY / wTopMenuItemX: o canto do menu desenhado. É o que separa uma
# tela de menu da outra sem depender de um byte de estado ambíguo.
MENU_TOP_Y_ADDRESS = 0xCC24
MENU_TOP_X_ADDRESS = 0xCC25
# wMaxMenuItem: a última linha selecionável da lista que está na tela.
MENU_LAST_ROW_ADDRESS = 0xCC28
# Em batalha: 106 com a lista de golpes desenhada, 94 no seletor 2x2. Qualquer
# outro valor é texto ou animação — e fora de batalha ele não significa nada.
BATTLE_MENU_STATE_ADDRESS = 0xCC50
BATTLE_MOVE_LIST_STATE = 106
BATTLE_MENU_2X2_STATE = 94
# Balcão do Mart: 32 é o BUY/SELL, 161 o seletor de quantidade, e 123 em
# 0xCF8B é a lista de itens que este balcão vende.
SHOP_MENU_ADDRESS = 0xCC52
SHOP_BUY_SELL_STATE = 32
SHOP_QUANTITY_STATE = 161
SHOP_TRANSACTION_ADDRESS = 0xCF8B
SHOP_ITEM_LIST_STATE = 123
# Caixa de texto / menu tomando a entrada.
TEXT_BOX_ADDRESS = 0xCFC4
IN_BATTLE_ADDRESS = 0xD057
PARTY_COUNT_ADDRESS = 0xD163
# Janela do LCD: 144 = nada desenhado por cima do mapa. Batalha, menu, loja e
# diálogo de cutscene baixam a janela; só o mapa a deixa fora da tela.
LCD_WINDOW_ADDRESS = 0xFF4A
LCD_WINDOW_PARKED = 144

# Cantos medidos no cartucho em 2026-08-16, ensinando o Cut ao Ivysaur.
MENU_MAIN = (2, 11)          # POKéDEX / POKéMON / ITEM / ...
MENU_BAG = (4, 5)            # a mochila, com 3 linhas visíveis e rolagem
MENU_ITEM_USE_TOSS = (11, 14)
MENU_TEACH_YES_NO = (8, 15)
MENU_PARTY = (1, 0)          # "Use TM on which POKéMON?"
MENU_FORGET_MOVE = (8, 5)    # "Which move should be forgotten?"

# Os nomes que um controlador pode perguntar. Tela que não é nenhum destes é
# `DESCONHECIDA` — e isso é um evento, nunca um padrão silencioso.
OVERWORLD = "overworld"
TEXTO = "texto"
TEXTO_BATALHA = "texto_batalha"
SIM_NAO = "sim_nao"
LISTA_EQUIPE = "lista_equipe"
LISTA_MART = "lista_mart"
COMPRA_VENDA = "compra_venda"
QUANTIDADE = "quantidade"
TECLADO_NOME = "teclado_nome"
LISTA_GOLPES = "lista_golpes"
MENU_BATALHA = "menu_batalha"
MENU_PRINCIPAL = "menu_principal"
MOCHILA = "mochila"
USAR_JOGAR_FORA = "usar_jogar_fora"
ESQUECER_GOLPE = "esquecer_golpe"
DESCONHECIDA = "desconhecida"

_CORNERS = {
    MENU_MAIN: MENU_PRINCIPAL,
    MENU_BAG: MOCHILA,
    MENU_ITEM_USE_TOSS: USAR_JOGAR_FORA,
    MENU_TEACH_YES_NO: SIM_NAO,
    MENU_PARTY: LISTA_EQUIPE,
    MENU_FORGET_MOVE: ESQUECER_GOLPE,
}


def _character(tile):
    """Um tile do `wTileMap` como caractere, na tabela da Gen I."""
    if 0x80 <= tile <= 0x99:
        return chr(ord("A") + tile - 0x80)
    if 0xA0 <= tile <= 0xB9:
        return chr(ord("a") + tile - 0xA0)
    if 0xF6 <= tile <= 0xFF:
        return chr(ord("0") + tile - 0xF6)
    if tile == 0x7F:
        return " "
    return "."


def rows(read_byte):
    """As 18 linhas desenhadas, decodificadas."""
    drawn = []
    for y in range(SCREEN_HEIGHT):
        line = []
        for x in range(SCREEN_WIDTH):
            line.append(_character(int(read_byte(
                SCREEN_TILEMAP_ADDRESS + y * SCREEN_WIDTH + x
            ))))
        drawn.append("".join(line))
    return drawn


def text(read_byte):
    """Tudo o que está escrito, numa string só."""
    return " ".join(rows(read_byte))


def visible_lines(read_byte):
    """Só as linhas com letra, sem os pontos do cenário — para log e relatório."""
    lines = []
    for line in rows(read_byte):
        stripped = line.replace(".", " ").strip()
        if stripped:
            lines.append(stripped)
    return lines


def naming_screen_open(read_byte):
    """O teclado de apelido está aberto?

    O cabeçalho do teclado escreve NICKNAME. Medido em 2026-08-16, com três
    bots capturando um Metapod e passando onze chunks inteiros digitando
    letras: em Gen I o START é o END desta tela.
    """
    return "NICKNAME" in text(read_byte)


def party_list_open(read_byte):
    """A lista da equipe é a tela que está tomando a entrada?

    O seletor 2x2 da batalha e a lista da party dividem os bytes do cursor. O
    que separa as duas é a forma da própria lista: a última linha selecionável
    é o último Pokémon e o cursor fica na coluna zero.
    """
    party_count = int(read_byte(PARTY_COUNT_ADDRESS))
    if party_count <= 1:
        return False
    return (
        int(read_byte(MENU_LAST_ROW_ADDRESS)) == party_count - 1
        and int(read_byte(MENU_TOP_X_ADDRESS)) == 0
    )


def classify(read_byte):
    """O nome da tela que está desenhada.

    A ordem importa e é a ordem em que o cartucho é inequívoco: o teclado se
    identifica pelo texto, a batalha pelo `0xCC50`, o resto pelo canto do menu.
    Nada aqui adivinha — tela que não casa com nenhum sinal medido volta
    `DESCONHECIDA`, que é o que faz o chamador logar em vez de apertar A.
    """
    if naming_screen_open(read_byte):
        return TECLADO_NOME

    if int(read_byte(IN_BATTLE_ADDRESS)) != 0:
        if party_list_open(read_byte):
            return LISTA_EQUIPE
        battle_menu = int(read_byte(BATTLE_MENU_STATE_ADDRESS))
        if battle_menu == BATTLE_MOVE_LIST_STATE:
            return LISTA_GOLPES
        if battle_menu == BATTLE_MENU_2X2_STATE:
            return MENU_BATALHA
        return TEXTO_BATALHA

    shop_menu = int(read_byte(SHOP_MENU_ADDRESS))
    transaction = int(read_byte(SHOP_TRANSACTION_ADDRESS))
    if transaction == SHOP_ITEM_LIST_STATE:
        return QUANTIDADE if shop_menu == SHOP_QUANTITY_STATE else LISTA_MART
    if shop_menu == SHOP_BUY_SELL_STATE:
        return COMPRA_VENDA

    corner = (
        int(read_byte(MENU_TOP_Y_ADDRESS)),
        int(read_byte(MENU_TOP_X_ADDRESS)),
    )
    named = _CORNERS.get(corner)
    if named is not None:
        return named

    if int(read_byte(TEXT_BOX_ADDRESS)) == 1:
        return TEXTO
    if int(read_byte(LCD_WINDOW_ADDRESS)) == LCD_WINDOW_PARKED:
        return OVERWORLD
    return DESCONHECIDA


def describe(read_byte):
    """A tela com o que sustenta o nome — para o diário de um congelamento."""
    return {
        "tela": classify(read_byte),
        "canto": [
            int(read_byte(MENU_TOP_Y_ADDRESS)),
            int(read_byte(MENU_TOP_X_ADDRESS)),
        ],
        "cc50": int(read_byte(BATTLE_MENU_STATE_ADDRESS)),
        "caixa_de_texto": int(read_byte(TEXT_BOX_ADDRESS)),
        "em_batalha": int(read_byte(IN_BATTLE_ADDRESS)),
        "linhas": visible_lines(read_byte),
    }
