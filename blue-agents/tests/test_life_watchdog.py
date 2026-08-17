"""O watchdog de vida contra os sete travamentos de 2026-08-16.

Cada teste aqui é uma das sete formas medidas naquele dia, reproduzida como o
cartucho a produziu: a porta da casa inicial, o corredor do lab, a prancha do
S.S. Anne, o balcão do Mart, o teclado de apelido, a lista da equipe em
batalha e o vaivém entre dois tiles.

O detector que existia antes não pega nenhuma delas por construção:
`route_no_progress` mede distância — e o vaivém encurta distância a cada outro
passo —, e `_watch_for_stagnation` compara posição mas retorna antes de olhar
quando a tarefa começa com QUEST, que é toda corrida real.

O que se mede aqui é o cartucho: mapa, posição, equipe, mochila, insígnias e
em-batalha. Não há noção de progresso nenhuma para uma camada mentir.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.life_watchdog import (
    BADGES_ADDRESS,
    BAG_ITEM_COUNT_ADDRESS,
    BATTLE_ENEMY_HP_ADDRESS,
    BATTLE_PLAYER_HP_ADDRESS,
    IN_BATTLE_ADDRESS,
    MAP_ID_ADDRESS,
    PARTY_COUNT_ADDRESS,
    PARTY_HP_OFFSET,
    PARTY_LEVEL_OFFSET,
    PARTY_STRUCT_ADDRESS,
    PARTY_STRUCT_SIZE,
    PLAYER_X_ADDRESS,
    PLAYER_Y_ADDRESS,
    LifeWatchdog,
    cartridge_fingerprint,
)

WINDOW = 40


class FakeCartridge:
    """Os bytes que o watchdog lê, e nada mais."""

    def __init__(self, map_id=37, x=3, y=6, in_battle=0, bag=0, badges=0,
                 party=((1, 5, 20),), battle_hp=(20, 20)):
        self.map_id = map_id
        self.x = x
        self.y = y
        self.in_battle = in_battle
        self.bag = bag
        self.badges = badges
        self.party = [list(member) for member in party]
        # `wBattleMon` e `wEnemyMon`: é onde a luta acontece. A HP da party só
        # é reescrita quando a batalha termina.
        self.battle_hp = list(battle_hp)
        self.reads = []

    def read_byte(self, address):
        self.reads.append(address)
        if address in (BATTLE_PLAYER_HP_ADDRESS, BATTLE_PLAYER_HP_ADDRESS + 1):
            valor = self.battle_hp[0]
            return valor >> 8 if address == BATTLE_PLAYER_HP_ADDRESS else valor & 0xFF
        if address in (BATTLE_ENEMY_HP_ADDRESS, BATTLE_ENEMY_HP_ADDRESS + 1):
            valor = self.battle_hp[1]
            return valor >> 8 if address == BATTLE_ENEMY_HP_ADDRESS else valor & 0xFF
        if address == MAP_ID_ADDRESS:
            return self.map_id
        if address == PLAYER_X_ADDRESS:
            return self.x
        if address == PLAYER_Y_ADDRESS:
            return self.y
        if address == IN_BATTLE_ADDRESS:
            return self.in_battle
        if address == BAG_ITEM_COUNT_ADDRESS:
            return self.bag
        if address == BADGES_ADDRESS:
            return self.badges
        if address == PARTY_COUNT_ADDRESS:
            return len(self.party)
        if PARTY_STRUCT_ADDRESS <= address < (
            PARTY_STRUCT_ADDRESS + PARTY_STRUCT_SIZE * max(len(self.party), 1)
        ):
            slot, offset = divmod(address - PARTY_STRUCT_ADDRESS,
                                  PARTY_STRUCT_SIZE)
            if slot >= len(self.party):
                return 0
            species, level, hp = self.party[slot]
            if offset == 0:
                return species
            if offset == PARTY_HP_OFFSET:
                return hp >> 8
            if offset == PARTY_HP_OFFSET + 1:
                return hp & 0xFF
            if offset == PARTY_LEVEL_OFFSET:
                return level
        return 0


def run(watchdog, cartridge, steps, mutate=None):
    """Roda N passos e devolve em qual deles o congelamento foi declarado."""
    fired = []
    for step in range(steps):
        if mutate is not None:
            mutate(cartridge, step)
        if watchdog.observe(cartridge_fingerprint(cartridge.read_byte)):
            fired.append(step)
    return fired


class SeteTravamentosTests(unittest.TestCase):
    def watchdog(self):
        return LifeWatchdog(window=WINDOW, distinct_floor=6, cooldown=WINDOW)

    def test_porta_da_casa_inicial_um_tile_so(self):
        # 11.355 relatórios no mesmo tile (1,2) do mapa 37.
        fired = run(self.watchdog(), FakeCartridge(map_id=37, x=1, y=2), WINDOW)
        self.assertEqual([WINDOW - 1], fired)

    def test_vaivem_entre_duas_casas(self):
        # A forma que `route_no_progress` nunca pega: a distância encurta a
        # cada outro passo, então o contador dele zera para sempre.
        def andar(cartridge, step):
            cartridge.y = 2 + (step % 2)

        fired = run(self.watchdog(), FakeCartridge(), WINDOW, andar)
        self.assertEqual([WINDOW - 1], fired)

    def test_balcao_do_mart_com_a_mochila_vazia(self):
        # ¥3175 no bolso, mochila em 0, cursor andando num menu: nada do que o
        # cartucho guarda muda.
        fired = run(self.watchdog(), FakeCartridge(map_id=42, bag=0), WINDOW)
        self.assertEqual([WINDOW - 1], fired)

    def test_lista_da_equipe_em_batalha_com_hp_intacto(self):
        # Butterfree 40 (124/124) contra um Charmeleon 20 (56/56) por 8
        # minutos, nenhum golpe lançado: nem a party, nem o `wBattleMon`, nem o
        # inimigo mudam de HP.
        cartridge = FakeCartridge(
            map_id=101, in_battle=1, party=((125, 40, 124), (12, 16, 45)),
            battle_hp=(124, 56),
        )
        self.assertEqual([WINDOW - 1], run(self.watchdog(), cartridge, WINDOW))

    def test_teclado_de_apelido(self):
        cartridge = FakeCartridge(map_id=51, in_battle=1)
        self.assertEqual([WINDOW - 1], run(self.watchdog(), cartridge, WINDOW))

    def test_prancha_do_navio_que_pede_o_ticket(self):
        # O passo D em (14,1) não move: o marinheiro pede o S.S. Ticket.
        cartridge = FakeCartridge(map_id=94, x=14, y=1)
        self.assertEqual([WINDOW - 1], run(self.watchdog(), cartridge, WINDOW))


class BotSaudavelTests(unittest.TestCase):
    """O que não pode disparar, senão o relatório vira ruído."""

    def watchdog(self):
        return LifeWatchdog(window=WINDOW, distinct_floor=6, cooldown=WINDOW)

    def test_bot_andando_nunca_dispara(self):
        def andar(cartridge, step):
            cartridge.x = step % 30
            cartridge.y = step // 30

        self.assertEqual([], run(self.watchdog(), FakeCartridge(), WINDOW * 3,
                                 andar))

    # A régua destes três é a proporção, não o número: janela de 600 passos
    # com piso de 6 impressões distintas pede **uma mudança a cada ~85
    # passos** — meio minuto de jogo. Nos testes a janela é 40, então o
    # equivalente é uma mudança a cada ~6.

    def test_batalha_com_hp_mudando_e_progresso(self):
        # Parado no tile durante uma luta é o normal; o que conta é o HP dos
        # dois lados andando.
        def lutar(cartridge, step):
            cartridge.in_battle = 1
            cartridge.party[0][2] = 40 - (step % 30)

        self.assertEqual([], run(self.watchdog(), FakeCartridge(), WINDOW * 2,
                                 lutar))

    def test_farm_no_mato_e_luta_anda_luta_e_isso_e_vida(self):
        # O caso que a primeira corrida real reprovou: 28 relatórios em meia
        # hora com os três bots farmando e o Charmeleon do IARON indo do nível
        # 16 ao 33. Em batalha a posição não muda e a HP da party não é
        # reescrita até o fim da luta — quem anda é o HP da própria batalha.
        def farmar(cartridge, step):
            dentro = (step % 20) < 16
            cartridge.in_battle = 1 if dentro else 0
            if dentro:
                cartridge.battle_hp = [40 - step % 16, 30 - step % 16]
            else:
                cartridge.x = 12 + (step % 2)

        self.assertEqual([], run(self.watchdog(), FakeCartridge(), WINDOW * 3,
                                 farmar))

    def test_farm_parado_no_mato_com_a_equipe_subindo(self):
        def farmar(cartridge, step):
            cartridge.party[0][1] = 5 + step // 5

        self.assertEqual([], run(self.watchdog(), FakeCartridge(), WINDOW * 2,
                                 farmar))

    def test_uma_compra_no_balcao_conta_como_vida(self):
        def comprar(cartridge, step):
            cartridge.bag = step // 5

        self.assertEqual([], run(self.watchdog(), FakeCartridge(), WINDOW * 2,
                                 comprar))

    def test_hp_travado_em_1_e_congelamento_de_verdade(self):
        # O contraste do teste da batalha: HP que desce e para de descer é o
        # AARON a 1/59 em Mt. Moon, fugindo de tudo por 2.176 passos.
        def sangrar(cartridge, step):
            cartridge.in_battle = 1
            cartridge.party[0][2] = max(1, 40 - step)

        self.assertTrue(run(self.watchdog(), FakeCartridge(), WINDOW * 3,
                            sangrar))


class CadenciaTests(unittest.TestCase):
    def test_dispara_uma_vez_e_cala_pelo_cooldown(self):
        watchdog = LifeWatchdog(window=WINDOW, distinct_floor=6, cooldown=100)
        fired = run(watchdog, FakeCartridge(), WINDOW * 4)
        self.assertEqual([WINDOW - 1], fired)

    def test_depois_do_silencio_ele_volta_a_medir(self):
        watchdog = LifeWatchdog(window=WINDOW, distinct_floor=6, cooldown=10)
        fired = run(watchdog, FakeCartridge(), WINDOW * 3)
        self.assertEqual([WINDOW - 1, WINDOW * 2 + 9], fired)

    def test_o_teto_de_relatorios_limita_o_disco(self):
        watchdog = LifeWatchdog(window=WINDOW, distinct_floor=6, cooldown=0,
                                max_reports=2)
        fired = run(watchdog, FakeCartridge(), WINDOW * 6)
        self.assertEqual(2, len(fired))
        self.assertEqual(2, watchdog.reports)

    def test_a_janela_recomeca_ao_declarar(self):
        # Sem isto o mesmo travamento escreveria um save por passo.
        watchdog = LifeWatchdog(window=WINDOW, distinct_floor=6, cooldown=0)
        run(watchdog, FakeCartridge(), WINDOW)
        self.assertEqual(0, len(watchdog.window))

    def test_piso_maior_que_a_janela_nao_declara_tudo_congelado(self):
        # `POKEAI_WATCHDOG_STEPS=4` com o piso padrão 6 diria "congelado" em
        # todo passo: uma janela de 4 nunca tem 7 impressões distintas.
        watchdog = LifeWatchdog(window=4, distinct_floor=6, cooldown=0)
        self.assertEqual(3, watchdog.distinct_floor)

        def andar(cartridge, step):
            cartridge.x = step

        self.assertEqual([], run(watchdog, FakeCartridge(), 40, andar))

    def test_janela_incompleta_nao_declara_nada(self):
        watchdog = LifeWatchdog(window=WINDOW, distinct_floor=6)
        self.assertEqual([], run(watchdog, FakeCartridge(), WINDOW - 1))


class ImpressaoDigitalTests(unittest.TestCase):
    def test_a_direcao_do_jogador_fica_de_fora(self):
        # A máquina `route_sprite_talk` gira no lugar: incluir a direção
        # (0xC109) faria um bot preso contra um NPC parecer vivo.
        cartridge = FakeCartridge()
        cartridge_fingerprint(cartridge.read_byte)
        self.assertNotIn(0xC109, cartridge.reads)

    def test_a_insignia_muda_a_impressao(self):
        cartridge = FakeCartridge()
        antes = cartridge_fingerprint(cartridge.read_byte)
        cartridge.badges = 1
        self.assertNotEqual(antes, cartridge_fingerprint(cartridge.read_byte))

    def test_hp_de_dois_bytes_e_lido_inteiro(self):
        cartridge = FakeCartridge(party=((125, 40, 300),))
        self.assertEqual(300, cartridge_fingerprint(cartridge.read_byte)[6][0][2])


if __name__ == "__main__":
    unittest.main()
