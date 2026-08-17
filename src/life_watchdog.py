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
# Ciclo de posição: a mesma volta repetida N vezes. Isto **não** é o mesmo teste
# da impressão digital, e existe porque ela não pega o caso: na Rota 3, em
# 2026-08-17, o LARON passou 56 minutos girando por **oito** tiles com batalha
# no meio — a posição mudava e o HP mudava, então o conjunto de impressões
# crescia e o piso nunca era cruzado. Foram 26 mil relatórios de travamento do
# executor e nenhum do watchdog.
#
# "Andar em círculo" não é como uma missão anda: uma rota atravessa, e o que
# repete a mesma volta é quem não sai do lugar. O período cobre até doze tiles
# (o vaivém de dois é o caso mais comum, o círculo da Rota 3 tinha oito), e o
# teto de repetições é alto de propósito — quinze voltas idênticas não são
# coincidência, e ainda deixa passar o farm, que muda de mato e de alvo.
CYCLE_MAX_PERIOD = 12
# Cem voltas idênticas — o número é do operador, e a primeira medição com quinze
# mostrou por que ele é alto: em um minuto de corrida, quinze voltas acusaram o
# **farm** (o MARON andando dois tiles no mato de propósito, rota `treino-51`) e
# o LARON parado num menu. Farm é ciclo legítimo; cem voltas sem desviar uma
# casa, não.
CYCLE_REPEATS = 100
# Período 1 é "não saiu do tile", e isso já é medido pela impressão digital —
# em janela de 600 passos, não de 15. Incluí-lo aqui fazia toda caixa de texto
# longa virar relatório.
CYCLE_MIN_PERIOD = 2

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
# Dentro de uma batalha a luta acontece em `wBattleMon`/`wEnemyMon`, e a HP da
# **party** só é reescrita no fim dela. Sem estes dois endereços — os mesmos
# que o controlador de batalha já lê — uma luta inteira é uma impressão digital
# só, e um farm de vinte minutos vira relatório de congelamento.
BATTLE_PLAYER_HP_ADDRESS = 0xD015
BATTLE_ENEMY_HP_ADDRESS = 0xCFE6


def cartridge_fingerprint(read_byte):
    """O estado do cartucho que qualquer progresso real muda.

    Andar muda a posição; lutar muda o HP dos dois lados; capturar, evoluir e
    subir de nível mudam a equipe; comprar muda a mochila; um ginásio muda as
    insígnias. O que fica de fora é de propósito: a direção para onde o jogador
    está virado **não** entra — a máquina de falar com sprite gira no lugar, e
    incluir isso faria um bot preso parecer vivo.

    O HP da batalha entra por medição, não por completude. Sem ele, a primeira
    corrida real do watchdog escreveu **28 relatórios em meia hora** com os três
    bots farmando na Floresta e o Charmeleon do IARON indo do nível 16 ao 33: em
    batalha a posição não muda e a HP da party não é reescrita até o fim da
    luta, então uma luta longa é uma impressão digital só. Um farm é
    luta-anda-luta, e a janela inteira caía embaixo do piso.
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
    in_battle = int(read_byte(IN_BATTLE_ADDRESS))
    battle_hp = (0, 0)
    if in_battle:
        # Fora de batalha estes bytes guardam a luta anterior: lê-los sempre
        # não daria vida falsa, mas também não diria nada — e zerá-los deixa a
        # impressão digital do overworld estável, que é o que se quer.
        battle_hp = (
            (int(read_byte(BATTLE_PLAYER_HP_ADDRESS)) << 8)
            + int(read_byte(BATTLE_PLAYER_HP_ADDRESS + 1)),
            (int(read_byte(BATTLE_ENEMY_HP_ADDRESS)) << 8)
            + int(read_byte(BATTLE_ENEMY_HP_ADDRESS + 1)),
        )
    return (
        int(read_byte(MAP_ID_ADDRESS)),
        int(read_byte(PLAYER_X_ADDRESS)),
        int(read_byte(PLAYER_Y_ADDRESS)),
        in_battle,
        int(read_byte(BAG_ITEM_COUNT_ADDRESS)),
        int(read_byte(BADGES_ADDRESS)),
        tuple(party),
        battle_hp,
    )


class LifeWatchdog:
    """Declara congelamento quando o conjunto de impressões para de crescer."""

    def __init__(
        self,
        window=FREEZE_WINDOW_STEPS,
        distinct_floor=FREEZE_DISTINCT_FLOOR,
        cooldown=FREEZE_COOLDOWN_STEPS,
        max_reports=FREEZE_MAX_REPORTS,
        cycle_repeats=CYCLE_REPEATS,
        cycle_max_period=CYCLE_MAX_PERIOD,
    ):
        self.cycle_repeats = int(cycle_repeats)
        self.cycle_max_period = int(cycle_max_period)
        self.places = deque(maxlen=self.cycle_max_period * self.cycle_repeats)
        self.cycle = None
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

    def _cycle_period(self):
        """O período da volta que está se repetindo, ou `None`.

        Procura do menor período para o maior: `A B A B A B…` é período 2, e o
        círculo da Rota 3 era oito tiles. Só conta se a volta inteira couber
        `cycle_repeats` vezes na memória de posições, o que é a diferença entre
        "passou duas vezes pelo mesmo tile" e "está girando".
        """
        places = list(self.places)
        for period in range(CYCLE_MIN_PERIOD, self.cycle_max_period + 1):
            # O mínimo é **por período**: um vaivém de dois tiles fecha quinze
            # voltas em trinta passos, e exigir a memória cheia (doze × quinze)
            # antes de testar qualquer período fazia o detector nunca disparar.
            span = period * self.cycle_repeats
            if len(places) < span:
                break
            recent = places[-span:]
            first = recent[:period]
            # Sequência constante casa com **qualquer** período: ficar parado
            # passava por "ciclo de período 2". Uma volta tem de ter mais de um
            # tile — quem não sai do lugar é assunto da impressão digital, em
            # janela de 600 passos.
            if len(set(first)) < 2:
                continue
            if all(
                recent[index] == first[index % period]
                for index in range(span)
            ):
                return period
        return None

    def observe(self, fingerprint, place=None):
        """`True` no passo em que o congelamento é declarado, uma vez só.

        A janela é esvaziada ao declarar: o que vem depois é uma medição nova,
        senão o mesmo travamento continuaria disparando enquanto durasse.

        `place` é a posição `(mapa, x, y)` — quando vem, um **ciclo de posição**
        repetido também declara congelamento, mesmo que a impressão digital
        esteja crescendo. É o caso que a impressão sozinha não pega: girar por
        oito tiles com batalha no meio muda HP e posição a cada passo.
        """
        if self.quiet_steps > 0:
            self.quiet_steps -= 1
            return False
        if place is not None:
            self.places.append(tuple(place))
            period = self._cycle_period()
            if period is not None:
                self.cycle = {
                    "period": period,
                    "repeats": self.cycle_repeats,
                    "tiles": [list(t) for t in list(self.places)[-period:]],
                }
                return self._declare()
        self.window.append(fingerprint)
        if len(self.window) < self.window_size:
            return False
        if self.distinct > self.distinct_floor:
            return False
        self.cycle = None
        return self._declare()

    def _declare(self):
        """Fecha a medição e diz se este passo vira relatório."""
        self.window.clear()
        self.places.clear()
        self.quiet_steps = self.cooldown
        if self.reports >= self.max_reports:
            # O teto não desliga a medição: a janela recomeça e o silêncio
            # vale, para o custo continuar limitado sem mentir sobre o estado.
            self.cycle = None
            return False
        self.reports += 1
        return True

    def reset(self):
        """Recomeçar a medição — troca de mapa por whiteout, retomada, etc."""
        self.window.clear()
        self.places.clear()
        self.cycle = None
        self.quiet_steps = 0
