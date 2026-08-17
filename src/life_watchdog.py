"""Impressão digital do cartucho: o sinal que camada nenhuma pode mentir.

Sete travamentos num dia (2026-08-16), e nenhum detector existente pegou os
sete. Cada camada tem a sua noção de progresso e todas erraram do mesmo jeito:

- `route_no_progress` mede **distância** até o alvo, e o vaivém entre duas
  casas encurta distância a cada outro passo — o contador zera para sempre;
- `_watch_for_stagnation` compara **posição**, e desiste de olhar assim que a
  tarefa é uma QUEST (rota de história cuida da própria recuperação);
- o contador de batalhas do painel marcava 0 com 11 batalhas acontecendo.

Aqui não há noção de progresso nenhuma: a cada passo tira-se uma impressão
digital do estado que o **cartucho** guarda — mapa, posição, equipe (espécie,
nível, HP), tamanho da mochila, insígnias, em-batalha. Conjunto de impressões
que não cresce em N passos = congelado, independente do que cada camada ache
que está fazendo.

Os sete disparam aqui: o teclado de apelido (posição fixa, equipe fixa), o
balcão do Mart (mochila que nunca cresce), a prancha do navio (mesmo tile), a
lista da equipe em batalha (HP intacto dos dois lados), o vaivém entre duas
casas (duas impressões alternando), a porta da casa inicial e o corredor do
lab.

**Isto não conserta nada e não deve.** Ele observa e grava: quem decide o que
fazer com um congelamento é quem lê o relatório. Uma recuperação automática
aqui esconderia o defeito de novo — foi o que o resgate acidental do PPO fez
com AARON..DARON, que passavam por acaso.
"""

from collections import deque

# Quatro minutos de jogo a 24 frames por passo. Grande o bastante para uma
# cutscene longa não virar relatório, pequeno o bastante para ninguém passar a
# noite parado: os sete travamentos rodaram por **horas**.
FREEZE_WINDOW_STEPS = 600
# Quantas impressões distintas ainda contam como "nada acontecendo". O vaivém
# entre duas casas dá 2; um teclado ou um balcão dão 1; um bot andando dá
# centenas. A folga cobre o pisca de um contador qualquer sem cegar o detector.
FREEZE_DISTINCT_FLOOR = 6
# Depois de um relatório, silêncio: sem isto o mesmo congelamento escreveria um
# save por passo até encher o disco (163 KB cada).
FREEZE_COOLDOWN_STEPS = 1200
# Teto por processo. Um congelamento que sobrevive a oito relatórios não vai
# ficar mais claro no nono.
FREEZE_MAX_REPORTS = 8

MAP_ID_ADDRESS = 0xD35E
PLAYER_X_ADDRESS = 0xD362
PLAYER_Y_ADDRESS = 0xD361
PARTY_COUNT_ADDRESS = 0xD163
PARTY_STRUCT_ADDRESS = 0xD16B
PARTY_STRUCT_SIZE = 44
PARTY_SPECIES_OFFSET = 0
PARTY_HP_OFFSET = 1
PARTY_LEVEL_OFFSET = 33
BAG_ITEM_COUNT_ADDRESS = 0xD31D
BADGES_ADDRESS = 0xD356
IN_BATTLE_ADDRESS = 0xD057


def cartridge_fingerprint(read_byte):
    """O estado do cartucho que qualquer progresso real muda.

    Andar muda a posição; lutar muda HP; capturar, evoluir e subir de nível
    mudam a equipe; comprar muda a mochila; um ginásio muda as insígnias. O que
    fica de fora é de propósito: a direção para onde o jogador está virado
    **não** entra — a máquina de falar com sprite gira no lugar, e incluir isso
    faria um bot preso parecer vivo.
    """
    party_count = min(int(read_byte(PARTY_COUNT_ADDRESS)), 6)
    party = []
    for slot in range(party_count):
        base = PARTY_STRUCT_ADDRESS + slot * PARTY_STRUCT_SIZE
        hp = (
            int(read_byte(base + PARTY_HP_OFFSET)) << 8
        ) + int(read_byte(base + PARTY_HP_OFFSET + 1))
        party.append((
            int(read_byte(base + PARTY_SPECIES_OFFSET)),
            int(read_byte(base + PARTY_LEVEL_OFFSET)),
            hp,
        ))
    return (
        int(read_byte(MAP_ID_ADDRESS)),
        int(read_byte(PLAYER_X_ADDRESS)),
        int(read_byte(PLAYER_Y_ADDRESS)),
        int(read_byte(IN_BATTLE_ADDRESS)),
        int(read_byte(BAG_ITEM_COUNT_ADDRESS)),
        int(read_byte(BADGES_ADDRESS)),
        tuple(party),
    )


class LifeWatchdog:
    """Declara congelamento quando o conjunto de impressões para de crescer."""

    def __init__(
        self,
        window=FREEZE_WINDOW_STEPS,
        distinct_floor=FREEZE_DISTINCT_FLOOR,
        cooldown=FREEZE_COOLDOWN_STEPS,
        max_reports=FREEZE_MAX_REPORTS,
    ):
        self.window_size = max(int(window), 2)
        # Piso maior que a janela declara congelamento em todo passo — a
        # janela cheia nunca teria impressões distintas suficientes. Como os
        # dois vêm de variável de ambiente (`POKEAI_WATCHDOG_*`), isto é
        # limitado em vez de explodir no meio de uma corrida.
        self.distinct_floor = min(int(distinct_floor), self.window_size - 1)
        self.cooldown = int(cooldown)
        self.max_reports = int(max_reports)
        self.window = deque(maxlen=self.window_size)
        self.reports = 0
        self.quiet_steps = 0

    @property
    def distinct(self):
        return len(set(self.window))

    def observe(self, fingerprint):
        """`True` no passo em que o congelamento é declarado, uma vez só.

        A janela é esvaziada ao declarar: o que vem depois é uma medição nova,
        senão o mesmo travamento continuaria disparando enquanto durasse.
        """
        if self.quiet_steps > 0:
            self.quiet_steps -= 1
            return False
        self.window.append(fingerprint)
        if len(self.window) < self.window_size:
            return False
        if self.distinct > self.distinct_floor:
            return False
        if self.reports >= self.max_reports:
            # O teto não desliga a medição: a janela recomeça e o silêncio
            # vale, para o custo continuar limitado sem mentir sobre o estado.
            self.window.clear()
            self.quiet_steps = self.cooldown
            return False
        self.reports += 1
        self.window.clear()
        self.quiet_steps = self.cooldown
        return True

    def reset(self):
        """Recomeçar a medição — troca de mapa por whiteout, retomada, etc."""
        self.window.clear()
        self.quiet_steps = 0
