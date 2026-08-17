import json
import time
from pathlib import Path
from pyboy.utils import WindowEvent
from src.agent import BaseAgent
import os
from datetime import datetime

from src.llm_agent import LLMAgent

from src.navigation import Navigation
from src.exploration_tracker import ExplorationTracker
from src.warp_memory import WarpMemory
from src.map_memory import MapMemory
from src.tile_collision import TileCollision
from src.route_trails import TrailRecorder, TrailStore, waypoints_from
from src.simple_battle import HM_MOVE_IDS, STATUS_MOVE_PRIORITY
from src import screen

# How many A presses a route spends on a dialogue before it walks anyway. The
# menu flag at 0xCFC4 has been observed stuck at 1 with no text on screen.
MENU_PRESS_LIMIT = 12

# Fração do HP total do time abaixo da qual a viagem até o Centro vale a pena.
# Regra por Pokémon mandava voltar cedo demais: 29/30 atravessava a cidade.
HEAL_HP_FRACTION = 0.20

# The north street in Viridian has a scripted NPC on the approach tile. The
# route must reach that tile before leaving so a blocking sprite can be talked
# to instead of being treated as ordinary geometry.
# Every Pokémon Center in Gen I is the same building inside: nurse at (3,3),
# doormat at (3,7). Every Mart likewise, clerk behind the top-left counter. That
# is what makes "the nearest one" a real controller instead of one more route
# measured by hand for one city.
# Onde o cartucho devolve o treinador depois de um apagão. Guarda o mapa de
# **fora** do último Centro usado — 1 para Viridian, 15 para a Rota 4.
LAST_BLACKOUT_MAP_ADDRESS = 0xD719

# Os Centros vêm do cartucho, não da memória de ninguém: tileset 6, 4×7, e o
# ponteiro de texto seis bytes depois do de script. Ver
# `blue-agents/tools/extract_centers.py`, que gera o arquivo abaixo.
#
# A lista escrita à mão errava dos dois lados. Faltava o 81, o Centro da Rota
# 10 antes do Túnel da Rocha. E sobrava o 174, o saguão do Indigo, que tem
# outro tileset e é 6×8 — o controlador genérico procuraria uma enfermeira em
# (3,3) e um capacho em (3,7) que não existem lá. O 140 parece Centro e não é:
# é o Hotel de Celadon, mesma casca e outro roteiro.
_CENTERS_PATH = (
    Path(__file__).resolve().parents[1]
    / "blue-agents" / "knowledge" / "maps" / "pokemon_centers.json"
)


def _load_centers():
    """Centros, mapa de fora de cada um, e a porta vista de fora."""
    try:
        with open(_CENTERS_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return set(), {}, {}
    centers = {int(map_id) for map_id in payload.get("centers", [])}
    outdoor, doors = {}, {}
    for center, entries in (payload.get("doors") or {}).items():
        for entry in entries:
            outdoor.setdefault(int(center), int(entry["map"]))
            doors.setdefault(int(entry["map"]), []).append(
                (int(entry["x"]), int(entry["y"]))
            )
    return centers, outdoor, doors


POKEMON_CENTER_MAP_IDS, CENTER_OUTDOOR_MAP, CENTER_DOOR_BY_OUTDOOR_MAP = _load_centers()
VIRIDIAN_CENTER_MAP_ID = 41
# Only Viridian's is proven — it is the one this project has actually walked
# into and bought from. A Mart id that is wrong here sends a trainer through
# the wrong door, so this set grows by measurement, never by memory. Until
# then `_run_nearest_mart` simply finds no door in other cities and the caller
# falls back to what it did before. Medido (2026-08-12): o Mart de Pewter é o
# mapa 56 — planta idêntica ao 42 (mesma balconista, sprite 38, no mesmo
# tile), confirmado no bloco de objetos da ROM e na constante PEWTER_MART do
# disassembly. O FARON, devolvido ao `buy_pokeballs` pela retomada sem
# manifesto, quicava entre Pewter e a Rota 2 indo comprar em Viridian.
POKE_MART_MAP_IDS = {42, 56}
SHOP_COUNTER_TILE = (2, 5)
# O que o balcão vende: contagem, depois os ids, terminados por 0xFF. Medido
# em 2026-08-16 varrendo a RAM de um save com o menu aberto — a lista de
# Viridian (`04 0B 0F 0C`) está aqui, não em 0xCF8C.
MART_ITEM_COUNT_ADDRESS = 0xCF7B
MART_ITEM_LIST_ADDRESS = 0xCF7C

# The hand-drawn route is the path that finishes the game, so it drives.
# Trails keep being recorded and published — they are the measurement of what a
# crossing cost — but *following* one is opt-in. Exploration is optional; the
# route is not.
FOLLOW_TRAILS = os.getenv("POKEAI_FOLLOW_TRAILS", "0") == "1"

# Quests cujo executor tem rota medida em todos os mapas do caminho: aqui o
# trail só pode piorar, e um trail ruim custa horas.
#
# - `bill_quest`: o trail publicado pelo GARON oscila dentro da casa do Bill;
# - `cerulean_gym_quest`: o trail do ginásio tem 2 pontos e não cobre o
#   labirinto — o bot mirava (5,3) com parede no meio;
# - `vermilion_gym_quest`: o trail é a guia manual do operador. Ele carrega a
#   perna da Rota 9 (Túnel da Rocha, não Vermilion) e entra na Route 5 em
#   (9,0) — a faixa do meio, que os penhascos isolam da porta do Underground.
#   Medido em 2026-08-16, minutos depois de o modo guia ser desligado: o
#   `_publish_manual_trail` publicou a guia, o trail assumiu no mapa 16 com
#   `route_id=trail-vermilion_gym_quest-16`, alvo (9,0) e `path_to_target:
#   None`, e o bot quicou em (15,0)..(15,5) por 600 passos.
#
# O bloqueio vale nos dois lugares que consultam trail: `_trail_override` e o
# ramo de trail do `_follow_route`. Trilha continua sendo gravada e publicada
# — o que muda é só quem dirige.
#
# - `start`, `oak_event`, `parcel_event`: o fluxo de largada é roteirizado
#   tile a tile e passa **duas vezes** pelos mesmos tiles do laboratório —
#   sobe para falar com o Oak, desce para sair. O trail guarda as duas
#   passagens sem saber qual é qual, então ele aponta para o tile do Oak
#   depois do pacote já entregue. Medido em 2026-08-16, com três bots novos:
#   o executor levava para (4,3), o trail puxava de volta para (4,1), e os
#   três ficaram presos entre duas casas — nenhum saiu de Pallet.
# - `viridian_forest_nav`: o executor daqui não só atravessa, ele **escolhe o
#   mato** — o trecho de treino sai do `wGrassTile` (0xD535) lido ao vivo, e é
#   isso que faz o farm render. O trail não sabe o que é mato: ele guarda por
#   onde alguém passou, e a travessia segue o caminho de terra de propósito.
#   Medido em 2026-08-17, mesmo save (`states/replay/apelido-na-floresta`),
#   1.200 passos, mudando só se o trail dirige: **2 batalhas e nível parado no
#   9 com o trail, contra 15 batalhas e nível 11 com o executor**. Na corrida
#   do operador foi pior: IARON, JARON e KARON passaram 3h30 em (1,1)/(1,2),
#   um canto sem mato, com `route_id=trail-override-viridian_forest_nav-51` —
#   em MISSION: AUTO, que é o modo que deveria estar farmando. Foi o watchdog
#   de vida que apontou os três.
# - `brock_quest`: a porta do ginásio são **dois** tiles de warp, (4,13) e
#   (5,13), e o trail guarda o tile de entrada como ponto. Medido em
#   2026-08-17, do save vivo do KARON (mapa 54, parado em (5,13)), 400 passos,
#   mudando só `POKEAI_FOLLOW_TRAILS`: **32 trocas de mapa 54↔2 e nenhuma
#   insígnia** com o trail dirigindo, contra chegar em (4,2) e lutar sem ele.
#   As rotas no relatório eram `trail-brock_quest-54` e
#   `trail-override-brock_quest-54`. O executor daqui tem rota medida dos dois
#   lados da porta (`_run_pewter_city_nav` e `brock-approach`).
# Esta lista virou **rede, não regra**, em 2026-08-17: quem decide agora é
# `_trail_may_drive`, e o critério é existir executor (`_run_<quest>`). A lista
# fica para as quests cujo executor mora em outro nome (o `start` é
# `_run_start_deterministic`, o `oak_event` e o `route_2_nav` entram pelo fluxo
# da largada) e como registro dos quatro travamentos que a construíram.
TRAIL_BLOCKED_QUESTS = frozenset({
    "start", "oak_event", "parcel_event",
    "viridian_forest_nav", "brock_quest",
    "bill_quest", "cerulean_gym_quest", "vermilion_gym_quest",
})

VIRIDIAN_CITY_MAP_ID = 1
VIRIDIAN_OLD_MAN_APPROACH = (17, 4)
VIRIDIAN_NORTH_EXIT = (17, 0)
VIRIDIAN_OLD_MAN_DIALOG_LIMIT = 48

# Vermilion é o mapa 5 e o Centro dela é o 89 — os dois vêm da ROM
# (`knowledge/maps/pokemon_centers.json`: porta (11,3) no mapa 5). O executor do
# vermilion tratava a cidade como mapa 1 e o Centro como 41, que são Viridian:
# chegar em Vermilion não disparava nada, e qualquer prédio de Viridian
# disparava a rota do ginásio de outra cidade.
VERMILION_CITY_MAP_ID = 5
VERMILION_CENTER_MAP_ID = 89

# O S.S. Anne, lido do bloco de objetos e da tabela de warps da ROM: a prancha
# em Vermilion (18,31)/(19,31) leva à doca (94); (14,2) sobe para o convés
# (95); a escada (2,6) sobe para o 2º andar (96); e a porta (36,4) do 2º andar
# é a cabine do capitão (101), com o **rival** parado exatamente em cima dela
# (objeto `trainer`, classe 225). O capitão é o NPC (4,2) da cabine e é ele
# quem entrega o HM01.
SS_ANNE_DOCK_MAP_ID = 94
SS_ANNE_DECK_MAP_ID = 95
SS_ANNE_UPPER_MAP_ID = 96
SS_ANNE_CAPTAIN_MAP_ID = 101
SS_ANNE_MAP_IDS = frozenset({94, 95, 96, 101})
SS_ANNE_GANGWAY = {(18, 31), (19, 31)}
SS_ANNE_BOARDING_TILE = (14, 2)
# O tile onde o marinheiro do cais para o jogador para ver o S.S. Ticket.
SS_ANNE_TICKET_TILE = (14, 1)
SS_ANNE_CABIN_DOOR = (36, 4)
SS_ANNE_CABIN_APPROACH = (37, 4)
CAPTAIN_APPROACH_TILE = (4, 3)
# Ids de item da Gen I: 0x3F é o S.S. Ticket (já usado pelo `bill_quest`) e
# 0xC4..0xC8 são os HMs, na ordem. HM01 é o Cut.
HM01_CUT = 0xC4
CUT_MOVE_ID = 15

# O `wTileMap` é uma janela de 20x18 centrada no jogador, então tudo dentro
# deste raio está na tela e tem leitura ao vivo. Fora dele, só o estático.
VISIBLE_TILE_RADIUS_X = 4
VISIBLE_TILE_RADIUS_Y = 3

# --- Menus de ensinar HM, medidos no cartucho em 2026-08-16 -----------------
#
# Cada tela é identificada pelo canto do menu — `wTopMenuItemY`/`X` (0xCC24 e
# 0xCC25) —, que é como o `_buy_first_shop_item` já faz com a loja. Sequência
# fixa de botões não serve: o número de caixas de texto varia (a mensagem de
# "não cabe mais golpe" só aparece com quatro golpes), e um D apertado durante
# o texto é comido, o que dessincroniza tudo o que vem depois.
MENU_TOP_Y_ADDRESS = 0xCC24
MENU_TOP_X_ADDRESS = 0xCC25
MENU_CURSOR_ADDRESS = 0xCC26
MENU_SCROLL_ADDRESS = 0xCC36
# wTileMap: 20x18 tiles do que está desenhado. É RAM, não ROM — a tela é a
# resposta do próprio jogo, e é ela que diz quem pode aprender o HM.
SCREEN_TILEMAP_ADDRESS = 0xC3A0
SCREEN_WIDTH, SCREEN_HEIGHT = 20, 18

MENU_MAIN = (2, 11)          # POKéDEX / POKéMON / ITEM / ...
MENU_MAIN_ITEM_INDEX = 2
MENU_BAG = (4, 5)            # a mochila, com 3 linhas visíveis e rolagem
MENU_ITEM_USE_TOSS = (11, 14)
MENU_TEACH_YES_NO = (8, 15)
MENU_PARTY = (1, 0)          # "Use TM on which POKéMON?"
MENU_FORGET_MOVE = (8, 5)    # "Which move should be forgotten?"
# Teto de passos dentro do fluxo. Menu que não se comporta é abandonado com B,
# não martelado — a mesma regra da troca em batalha.
TEACH_MENU_STEP_LIMIT = 240

# `wSpriteStateData1 + 9` do sprite 0 é para onde o jogador está virado:
# 0 baixo, 4 cima, 8 esquerda, 12 direita. Falar com um NPC exige estar
# virado para ele — A de costas não abre diálogo nenhum.
PLAYER_FACING_ADDRESS = 0xC109
FACING_UP = 4
# Borda sul de Cerulean, a saída para a Route 5 (mapa 16, que entra em (16,0):
# a conexão soma 10 ao x). É também o teste de componente do mapa 3 — quem
# alcança este tile está do lado leste do rio e desce sozinho.
CERULEAN_SOUTH_EXIT = (26, 35)
# Onde a travessia de Mt. Moon termina: o tile por onde o AARON entrou em
# Cerulean em 2026-08-12, e o mesmo do BARON em 05/08. É o alvo que o grafo
# recebe quando a rota medida não alcança.
CERULEAN_ARRIVAL = (3, 0, 18)

VIRIDIAN_FOREST_MAP_ID = 51

# Rocha e Terra são o que o ginásio de Pewter põe na frente, e Tackle apanha dos
# dois. Grama e Água batem 4× no Geodude; Luta bate na Rocha. Ter um destes na
# mão é o que separa vencer o Brock de 269 apagões seguidos, medidos em corrida.
GYM_EFFECTIVE_TYPES = {"GRASS", "WATER", "FIGHTING"}
# Teto de paciência do treino: sem ele, um time que nunca aprende o golpe certo
# treinaria para sempre. Não é o alvo — o alvo é o golpe.
TRAINING_MAX_LEVEL = 14
# Casas de distância mínima até qualquer treinador do mapa. Os três bug catchers
# da Floresta ficam a 23-25 do trecho de mato perto da porta sul.
TRAINING_TRAINER_CLEARANCE = 12

# Metas de farm por linha inicial, definidas com o operador (2026-08-12).
# Os três iniciais evoluem no nível 16; o Charmander ainda precisa de um
# Butterfree — a linha Caterpie/Metapod evolui no 10 e Confusion no 12
# carrega contra o Brock. Pikachu é ideal contra a Misty: no modo FARM o
# farm continua até ele aparecer (5% na Floresta); no AUTO a captura é por
# prioridade natural (espécie nova + raridade). Ids internos da Gen I
# (o índice interno ≠ dex nacional; ver `blue-agents/pokemon_ids.py`).
FIRST_EVOLUTION_LEVEL = 16
BUTTERFREE_INTERNAL = 125
# O nível em que o inicial resolve o Brock sozinho, sem depender do Confusion
# do Butterfree. Decisão do operador em 2026-08-17, com o IARON parado na
# Floresta: "um charmander 25 já destrói o brock". É teto de paciência para a
# meta do Butterfree, que sem ele não termina — o inicial mata o encontro antes
# do Metapod pegar XP, e o Metapod é quem precisa chegar ao 10.
BROCK_BRUTE_FORCE_LEVEL = 25
PIKACHU_INTERNAL = 84
CHARMANDER_LINE_INTERNAL = {176, 178, 180}

# Tipos de missão lidos da task file (`tasks/<AGENTE>.txt`, linha MISSION:).
# - STORY (história): nunca farma — a rota corre.
# - FARM: farma até as metas da linha inicial (e o Pikachu) — a saída é a UX.
# - AUTO (recomendado, padrão): farma quando a linha inicial ainda não está
#   pronta para a história.
MISSION_TYPES = ("STORY", "FARM", "AUTO")

# Steps spent waiting for a person to move before walking around them. People
# in Gen I pace on their own; walls do not.
SPRITE_PATIENCE_STEPS = 6

# Botões A gastos interagindo com um sprite que fecha a única passagem antes de
# desistir. Treinador responde com batalha (vencer remove o sprite), fóssil
# responde com pickup (some do tile) e NPC com diálogo (fica — o desvio assume).
SPRITE_DIALOG_LIMIT = 12

# Steps spent unable to get any closer before the route gives up on this anchor
# and backs up to the previous one.
UNREACHABLE_PATIENCE_STEPS = 8

# How far south to aim when leaving a map whose door was never observed. Kanto
# interiors are small; this clears any of them.
BLIND_EXIT_REACH = 10

# Failed cycles on the same tile before the route stops believing anything it
# knows about that tile. Each cycle is four steps plus a text attempt.
STUCK_TILE_AMNESTY_CYCLES = 6

# Tiles remembered to notice pacing. Two visits to the same tile inside this
# window is a bot going back and forth, not a bot walking a corridor. Eight
# covers the four-step cycle that kept a trainer between (6,30) and (8,30) in
# the Forest; three would only have caught the two-tile version.
ROUTE_MEMORY_TILES = 8

ROUTE_STEP_OFFSETS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}

# Learned walls live with the rest of the map knowledge, not inside a trainer:
# geometry is the same for everyone who walks it.
# Doors already had a home in the knowledge directory; only free exploration
# ever wrote to it, and the scripted journey never read it.
SHARED_TERRAIN_PATH = (
    Path(__file__).resolve().parents[1]
    / "blue-agents" / "knowledge" / "maps" / "terrain.json"
)

# Writing a few thousand tiles every step is pointless; the map is only useful
# across runs, and a crash costs at most this many steps of looking.
TERRAIN_SAVE_INTERVAL = 200

# How far from its own plan a trainer has to be before the trail is joined
# again. Short enough to recover from a whiteout, long enough that a detour
# around one tree is not a reason to start over.
TRAIL_REJOIN_DISTANCE = 12

# Passos em que a volta pela fronteira recém-atravessada fica retida. Só vale
# parado no tile de chegada: sair dele e voltar continua permitido.
ENTRY_BLOCK_STEPS = 4

# Só vale procurar o desconhecido quando o alvo ainda está longe. Perto dele,
# "explorar" é dar as costas para a porta em que já se está encostado.
FRONTIER_MIN_DISTANCE = 3

# Passos sem encurtar a distância até o alvo antes de aceitar que o caminho
# está fechado. Menos que isso confunde batalha no mato com estar preso: o
# encontro congela o bot no lugar e o tile se repete sozinho.
NO_PROGRESS_STEPS = 15

# Passos sem progresso antes de aceitar que o waypoint está errado para onde o
# bot está, e mirar numa porta do mapa em vez de insistir.
STUCK_GIVE_UP_STEPS = 40

# Passos sem encurtar a distância antes de soltar o avanço lembrado da rota. O
# avanço existe para não voltar ao waypoint da entrada ao reentrar num mapa;
# quando o bot sai da rota, ele vira uma âncora à frente que nunca se alcança.
# Bem acima de STUCK_GIVE_UP_STEPS: primeiro tenta-se a porta, e só então se
# admite que o trecho inteiro está errado.
ROUTE_REPLAN_STEPS = 120

# Teto duro de passos de rota por waypoint. O contador de distância só vê "não
# encostou": um desvio longo que encolhe a distância devagar zera o contador a
# cada passo, e o bot queimava milhares de passos no mesmo alvo. Estourou o
# orçamento, o waypoint é gasto — mira o próximo; no último, solta a rota e
# reentra pelo mais próximo. Alto de propósito: batalha e texto não contam
# (a rota nem roda neles), mas um waypoint legítimo com encontros no caminho
# precisa caber.
WAYPOINT_STEP_BUDGET = 300

# Passos que uma parede descoberta na marra vale. Curto de propósito: gente
# some, e a leitura do cartucho continua sendo a fonte principal.
BUMP_MEMORY_STEPS = 8

# Passos parado no mesmo tile antes de gravar um relatório de travamento. O
# segundo relatório do mesmo tile sai no dobro, o terceiro no triplo: quem trava
# de verdade fica registrado, e quem só esperou um NPC não polui o arquivo.
STUCK_REPORT_STEPS = 30

# Janela olhada para decidir se ele está preso, e quantos lugares diferentes
# dentro dela ainda contam como parado. Dois tiles alternados são parados.
STUCK_WINDOW_TILES = 12
# Quatro, não três: entrar e sair de uma porta muda o mapa e conta como lugar
# novo, e era assim que o vaivém na porta do Centro escapava do gatilho.
STUCK_DISTINCT_TILES = 4
# Quantas trocas de mapa seguidas entre os mesmos dois mapas já contam como
# vaivém. Seis é curto o bastante para pegar o ciclo em segundos e longo o
# bastante para não acusar quem entra numa porta e sai porque terminou ali.
STUCK_MAP_CROSSINGS = 6

# A âncora de aproximação da boca de Mt. Moon, na Rota 4. Quem já está em x=11
# ou mais a leste passou dela; voltar para trás é o que fechava o ciclo com a
# caverna.
MT_MOON_APPROACH_X = 11

# Mapas onde um Centro fica no caminho e a próxima etapa não tem nenhum.
# Viridian antes da Floresta, Pewter antes da Rota 3.
CENTER_ON_THE_WAY = {1, 2, 15}

# Abaixo disso vale parar no Centro que já está no caminho. Bem acima do
# limite de emergência: entrar na Floresta pela metade é morrer no meio dela.
TOP_UP_HP_FRACTION = 0.7

# A Floresta é atravessada de sul para norte. Passando da metade, o Centro mais
# perto é o de Pewter, e ele fica no caminho — voltar custa a travessia inteira.
FOREST_MIDPOINT_Y = 24
ROUTE_2_NORTH_Y = 20

SHARED_WARP_PATH = (
    Path(__file__).resolve().parents[1]
    / "blue-agents" / "knowledge" / "maps" / "warps.json"
)

OPPOSITE_DIRECTIONS = {"U": "D", "D": "U", "L": "R", "R": "L"}

ROUTE_EVENTS = {
    "U": WindowEvent.PRESS_ARROW_UP,
    "D": WindowEvent.PRESS_ARROW_DOWN,
    "L": WindowEvent.PRESS_ARROW_LEFT,
    "R": WindowEvent.PRESS_ARROW_RIGHT,
}

# O deslocamento de cada tecla, na convenção deste projeto (y cresce ao sul).
STEP_BY_KEY = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}

# O grafo de Kanto é imutável (vem do ROM) e caro de montar: 49 mil células e
# 2.152 portas. Um por processo, carregado na primeira pergunta.
_KANTO_GRAPH = None

class ScriptedAgent(BaseAgent):
    def __init__(self, walkthrough_path, emulator=None, player_name="AARON", save_dir=".", starter_choice=None, route_role="follower"):
        with open(walkthrough_path, 'r') as f:
            self.walkthrough = json.load(f)
            
        # Load extra knowledge (Brock Guide)
        try:
            guide_candidates = [
                Path(walkthrough_path).resolve().parent / "docs/cidades/1/brock.json",
                Path(__file__).resolve().parents[1] / "docs/cidades/1/brock.json",
            ]
            brock_guide_path = next(
                (candidate for candidate in guide_candidates if candidate.exists()),
                None,
            )
            if brock_guide_path is None:
                raise FileNotFoundError("Pokemon Blue detonado not found")
            with open(brock_guide_path, 'r') as f:
                self.brock_guide = json.load(f)
        except FileNotFoundError:
            print("Warning: brock.json not found.")
            self.brock_guide = {}
        
        self.emulator = emulator
        self.llm_agent = LLMAgent(knowledge=self.brock_guide) # Pass knowledge to LLM
        self.navigation = Navigation(emulator) if emulator else None
        self.exploration = ExplorationTracker(save_dir=save_dir)  # NEW
        self.player_name = player_name
        self.save_dir = save_dir
        self.starter_choice = starter_choice
        # The guide walks the route as drawn and nothing else, so that getting
        # stuck stays a readable verdict on the route instead of being papered
        # over. The follower inherits whatever the guide has already proved.
        self.route_role = route_role
        self.trail_store = TrailStore()
        self.trail_recorder = TrailRecorder()
        self._debug_route = os.getenv("POKEAI_DEBUG_ROUTE", "0") == "1"
        self.current_step = 0
        self.steps = self._flatten_actions(self.walkthrough)
        
    def step(self, task_name=None):
        """
        Executes the next step for the given task.
        If task_name is provided and different from current, switches context.
        """
        # Com o modo guia ativo, o operador é o piloto: o bot não decide NADA
        # — nem trail, nem executor, nem exploração. O passo manual do hybrid
        # já tem prioridade; aqui só garantimos que nada do scripted disputa
        # o D-pad enquanto o operador dirige (medido 2026-08-13: o executor
        # rodava mesmo com o guia ligado, movendo o bot para longe do
        # operador).
        if self._manual_mode_active():
            if getattr(self, "_debug_route", False):
                print(f"[DEBUG-MANUAL] {getattr(self, 'player_name', '?')}: guia ativo, scripted em espera", flush=True)
            return None
        if self._naming_screen_open():
            # O teclado de apelido não é texto: A nele **digita letra**. Ele
            # aparece depois de toda captura e também ao receber o inicial —
            # e aí `0xD057` já é zero, fora do alcance do controlador de
            # batalha, que era o único que sabia respondê-lo. Aqui o menu está
            # aberto, então `_run_start_deterministic` respondia A.
            #
            # Medido em 2026-08-17 pelo watchdog de vida, do save
            # `states/replay/casa-inicial.state`, sem PPO: o cartucho
            # **auto-confirma** quando o nome enche, então isto não travava —
            # custava 11 passos digitando e o inicial saía chamado
            # `AAAAAAAAAA`. Com o START (que é o END desta tela em Gen I) é um
            # passo e o nome fica `BULBASAUR`. Não depender do acidente do
            # preenchimento é o ponto: numa tela conhecida, quem responde é a
            # tela.
            return WindowEvent.PRESS_BUTTON_START
        if task_name:
            # Normalize task name
            task_name = task_name.lower()
            if task_name == "brock":
                task_name = "brock_quest"
            
            # Check if we need to switch tasks
            if not hasattr(self, 'current_task_name') or self.current_task_name != task_name:
                native_controller = hasattr(self, f"_run_{task_name}")
                if native_controller:
                    # Executor nativo manda: o walkthrough legado é lista de
                    # teclas cega, e para as quests com executor ele só
                    # desviou o bot (medido 2026-08-12: o buy_pokeballs do
                    # FARON seguia "Go to Viridian City PokeMart" do
                    # walkthrough e quicava entre Pewter e a Rota 2, e o
                    # cerulean_gym_quest do AARON nunca chegava ao executor
                    # que sabe sair do ginásio com a insígnia).
                    self.steps = []
                    self.current_step = 0
                    self.current_task_name = task_name
                    # Reset internal state variables for new task
                    if hasattr(self, 'tick_counter'): del self.tick_counter
                    if hasattr(self, 'seq_index'): del self.seq_index
                    if hasattr(self, 'seq_timer'): del self.seq_timer
                    if hasattr(self, 'route_id'): del self.route_id
                    if hasattr(self, 'route_index'): del self.route_index
                    print(f"[{self.player_name}] Switched to task: {task_name}")
                elif (
                    "game_flow" in self.walkthrough
                    and task_name in self.walkthrough["game_flow"]
                ):
                    self.steps = self.walkthrough["game_flow"][task_name]["actions"]
                    self.current_step = 0
                    self.current_task_name = task_name
                    # Reset internal state variables for new task
                    if hasattr(self, 'tick_counter'): del self.tick_counter
                    if hasattr(self, 'seq_index'): del self.seq_index
                    if hasattr(self, 'seq_timer'): del self.seq_timer
                    if hasattr(self, 'route_id'): del self.route_id
                    if hasattr(self, 'route_index'): del self.route_index
                    print(f"[{self.player_name}] Switched to task: {task_name}")
                else:
                    # print(f"[{self.player_name}] Warning: Task '{task_name}' not found in walkthrough.")
                    pass

        if getattr(self, "current_task_name", None) == "start" and self.emulator:
            return self._run_start_deterministic()
        return self.get_action(None)

    def _run_start_deterministic(self):
        """Complete the opening walk without the legacy timed action list."""
        map_id = int(self.emulator.memory.get_map_id())
        position = self.emulator.memory.get_player_pos()
        if map_id == 38:
            return self._follow_route("start-bedroom", [(5, 6), (5, 1), (7, 1)])
        if map_id == 37:
            return self._follow_route("start-house-1f", [(7, 6), (3, 6), (3, 8)])
        if map_id == 0:
            oak_appeared = bool(self.emulator.memory.read_byte(0xD74B) & 0x80)
            if oak_appeared or position[1] <= 1:
                return WindowEvent.PRESS_BUTTON_A
            return self._follow_route("start-pallet", [(10, 6), (10, 1)])
        if map_id == 40:
            if self._menu_is_open():
                # Oak's starter description uses consecutive confirmations;
                # alternating B here leaves CC50/CFC4 open forever.
                return WindowEvent.PRESS_BUTTON_A
            if self.emulator.memory.get_party_count() == 0:
                return self._choose_starter_verified()
            return self._complete_oak_rival_event()
        return None

    def get_current_task_name(self):
        return getattr(self, 'current_task_name', 'start')

    def _flatten_actions(self, walkthrough):
        """
        Flattens the hierarchical JSON into a linear list of actions.
        This is a simplification. A real implementation would need a state machine.
        """
        actions = []
        # Default to "start" if available
        if "game_flow" in walkthrough and "start" in walkthrough["game_flow"]:
            actions.extend(walkthrough["game_flow"]["start"]["actions"])
            self.current_task_name = "start"
        return actions

    def get_action(self, state):
        """
        Decides the next action based on the current step and game state.
        """
        if self.current_step >= len(self.steps):
            # Script finished. If we have LLM, ask for guidance instead of giving up.
            if self.llm_agent:
                # Fallthrough to LLM logic below
                pass
            else:
                return None # Done
        
        # Track exploration (update visited tiles)
        if self.emulator:
            map_id = self.emulator.memory.get_map_id()
            pos = self.emulator.memory.get_player_pos()
            if pos != (0, 0):  # Only track if position is valid
                self.exploration.update(map_id, pos[0], pos[1])
        
        # Auto-detect step from checkpoint (first time only)
        if not hasattr(self, 'checkpoint_step_detected'):
            self._detect_checkpoint_step()
            self.checkpoint_step_detected = True
            
        # Stuck Detection
        if not hasattr(self, 'last_step_change_frame'):
            self.last_step_change_frame = 0
            self.last_step_index = 0
            self.last_progress_position = None

        # Native quest executors intentionally keep ``current_step`` fixed.
        # Treat real movement as progress too, otherwise the legacy watchdog
        # eventually injects random directions while a route is working.
        if self.emulator:
            progress_position = (
                int(self.emulator.memory.get_map_id()),
                tuple(self.emulator.memory.get_player_pos()),
            )
            if progress_position != self.last_progress_position:
                self.last_progress_position = progress_position
                self.last_step_change_frame = self.emulator.pyboy.frame_count
            
        if self.current_step != self.last_step_index:
            self.last_step_index = self.current_step
            if self.emulator:
                self.last_step_change_frame = self.emulator.pyboy.frame_count
        
        # If stuck for 100000 frames (approx 30 mins at 60fps, but faster in headless), save and exit
        # In headless, this might be ~1-2 minutes depending on speed
        if self.emulator and (self.emulator.pyboy.frame_count - self.last_step_change_frame > 100000):
            print(f"Stuck detected! No progress for 100000 frames. Resetting navigation state...")
            # Save with timestamp and name just for debugging
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.save_dir}/stuck_{self.player_name}_{timestamp}.state"
            self.emulator.save_state(filename)
            
            # Reset internal state to try again or unstuck
            if hasattr(self, 'nav_timer'): del self.nav_timer
            if hasattr(self, 'tick_counter'): del self.tick_counter
            
            # Update last change frame to avoid spamming
            self.last_step_change_frame = self.emulator.pyboy.frame_count
            
            # Return random action to try to unstuck
            import random
            return random.choice([
                WindowEvent.PRESS_ARROW_UP, WindowEvent.PRESS_ARROW_DOWN, 
                WindowEvent.PRESS_ARROW_LEFT, WindowEvent.PRESS_ARROW_RIGHT
            ])

        # Check for battle
        is_battle = False
        if self.emulator:
            battle_status = self.emulator.memory.read_byte(0xD057)
            is_battle = battle_status != 0
        if is_battle:
            self.was_in_battle = True
            # print("Battle detected! Using simple battle logic (No LLM)...")
            
            # Simple Battle Strategy: Spam A to attack/advance text
            # This is much faster and saves LLM for story decisions
            return WindowEvent.PRESS_BUTTON_A
            
            # OLD LLM LOGIC (Disabled per user request)
            # battle_state = self.emulator.memory.get_battle_state()
            # action = self.llm_agent.get_battle_action(battle_state)
            # if action:
            #     return action
            # return WindowEvent.PRESS_BUTTON_A
        
        # Check if we just finished a battle
        if hasattr(self, 'was_in_battle') and self.was_in_battle and not is_battle:
            print("Battle finished!")
            self.was_in_battle = False
            self.battle_finished = True

        if self.current_step < len(self.steps):
            action_desc = self.steps[self.current_step]
            if not hasattr(self, 'last_printed_objective') or self.last_printed_objective != action_desc:
                print(f"Current Objective: {action_desc}")
                self.last_printed_objective = action_desc
        else:
            action_desc = "Explore and advance story"
            if not hasattr(self, 'last_printed_objective') or self.last_printed_objective != action_desc:
                print(f"Current Objective: {action_desc} (LLM Autopilot)")
                self.last_printed_objective = action_desc
        
        # Simple state machine for "Start -> New Game"
        # This is hardcoded for demo purposes. 
        # Real implementation needs a proper sequence manager.
        
        if self.emulator:
            pos = self.emulator.memory.get_player_pos()
            map_id = self.emulator.memory.get_map_id()
            
            # Cutscene Detection: Check if player moved without our input
            if hasattr(self, 'last_pos') and hasattr(self, 'last_action_was_move'):
                if pos != self.last_pos and not self.last_action_was_move:
                    print(f"[CUTSCENE] Player moving automatically! Waiting...")
                    self.last_pos = pos
                    return None # Wait/PASS
            
            self.last_pos = pos
            self.last_action_was_move = False # Reset flag, will be set if we return a move action

            if self.emulator.pyboy.frame_count % 60 == 0:
                # print(f"Debug - Step: {action_desc}, Map: {map_id}, Pos: {pos}")
                pass

            # Self-Correction: If in Bedroom (Map 38) but step is "Start" or "Intro" or "Naming" (steps 0, 1, 2)
            # We should be at least at step 3 "Leave house"
            if map_id == 38 and self.current_task_name == "start" and self.current_step < 3:
                 print(f"[CORRECTION] In Bedroom but at step {self.current_step}. Jumping to Step 3 (Leave House).")
                 self.current_step = 3
                 return None # Skip this frame to let loop update action_desc

        center_action = self._center_first_action()
        if center_action is not None:
            return center_action

        # A trilha do operador sobrepõe TUDO: foi medida no cartucho real,
        # perna a perna, e é a prova de que o caminho funciona. Se há trilha
        # publicada para a quest + mapa atual, ela manda — o executor pode
        # errar o ramo (beco, waypoint inalcançável) mas a trilha não.
        trail_step = self._trail_override_step()
        if trail_step is not None:
            return trail_step

        if getattr(self, "current_task_name", None) == "parcel_event":
            return self._run_parcel_event()
        if getattr(self, "current_task_name", None) == "buy_pokeballs":
            return self._run_buy_pokeballs()
        if getattr(self, "current_task_name", None) == "route_2_nav":
            return self._run_route_2_nav()
        if getattr(self, "current_task_name", None) == "viridian_forest_nav":
            return self._run_viridian_forest_nav()
        if getattr(self, "current_task_name", None) == "pewter_city_nav":
            return self._run_pewter_city_nav()
        if getattr(self, "current_task_name", None) == "brock_quest":
            return self._run_brock_quest()
        if getattr(self, "current_task_name", None) == "mt_moon_nav":
            return self._run_mt_moon_nav()
        if getattr(self, "current_task_name", None) == "bill_quest":
            return self._run_bill_quest()
        if getattr(self, "current_task_name", None) == "cerulean_gym_quest":
            return self._run_cerulean_gym_quest()
        if getattr(self, "current_task_name", None) == "vermilion_gym_quest":
            return self._run_vermilion_gym_quest()

        if action_desc == "Start -> New Game":
            # Sequence: Press Start -> Wait -> Press A (New Game) -> Wait
            # We need to maintain internal state to know where we are in this sequence
            
            # Hacky implementation using static counter for now
            if not hasattr(self, 'tick_counter'):
                self.tick_counter = 0
            
            self.tick_counter += 1
            
            # Slower sequence to ensure we hit the menu
            if self.tick_counter == 60:
                return WindowEvent.PRESS_BUTTON_START
            elif self.tick_counter == 65:
                return WindowEvent.RELEASE_BUTTON_START
            elif self.tick_counter == 180: # Wait 2s
                return WindowEvent.PRESS_BUTTON_START # Press Start again just in case
            elif self.tick_counter == 185:
                return WindowEvent.RELEASE_BUTTON_START
            elif self.tick_counter == 300: # Wait more
                return WindowEvent.PRESS_BUTTON_A # Select New Game / Continue
            elif self.tick_counter == 305:
                return WindowEvent.RELEASE_BUTTON_A
            elif self.tick_counter == 360:
                return WindowEvent.PRESS_BUTTON_A # Confirm New Game
            elif self.tick_counter == 365:
                return WindowEvent.RELEASE_BUTTON_A
            elif self.tick_counter > 420:
                # Done with this step, move to next
                self.current_step += 1
                self.tick_counter = 0
                return None
            
            return None

        if action_desc == "Complete Oak introduction":
            # Just spam A for a while to get through text
            # In a real implementation, we would check memory for text state
            
            if not hasattr(self, 'tick_counter'):
                self.tick_counter = 0
            
            self.tick_counter += 1
            
            # Press A every 30 frames (0.5s)
            if self.tick_counter % 30 == 0:
                return WindowEvent.PRESS_BUTTON_A
            elif self.tick_counter % 30 == 1:
                return WindowEvent.RELEASE_BUTTON_A
            
            # Assume it takes about 60 seconds (3600 frames) to get through intro
            if self.tick_counter > 3600:
                 self.current_step += 1
                 self.tick_counter = 0
                 
            return None

        if action_desc == "Set player name and rival name":
            # Select "NEW NAME" (Top option) -> Type Name -> Start
            # Then "NEW NAME" (Top option) -> Type Rival Name -> Start
            
            # Default names
            p_name = self.player_name
            r_name = "GARY"
            
            # Sequence:
            # 1. Press A (Select NEW NAME for Player)
            # 2. Type Player Name
            # 3. Press START (Finish Player)
            # 4. Wait for Rival screen (long wait)
            # 5. Press A (Select NEW NAME for Rival)
            # 6. Type Rival Name
            # 7. Press START (Finish Rival)
            # 8. Wait for game to start
            
            if not hasattr(self, 'naming_sequence'):
                self.naming_sequence = []
                
                # Player Name
                self.naming_sequence.append((WindowEvent.PRESS_BUTTON_A, 30))
                self.naming_sequence.append((WindowEvent.RELEASE_BUTTON_A, 30))
                self.naming_sequence.extend(self._get_typing_sequence(p_name))
                self.naming_sequence.append((WindowEvent.PRESS_BUTTON_START, 30))
                self.naming_sequence.append((WindowEvent.RELEASE_BUTTON_START, 200)) # Wait for Rival text
                
                # Navigate through Rival text (Spam A a bit)
                for _ in range(5):
                    self.naming_sequence.append((WindowEvent.PRESS_BUTTON_A, 30))
                    self.naming_sequence.append((WindowEvent.RELEASE_BUTTON_A, 30))
                
                # Rival Name
                self.naming_sequence.append((WindowEvent.PRESS_BUTTON_A, 30))
                self.naming_sequence.append((WindowEvent.RELEASE_BUTTON_A, 30))
                self.naming_sequence.extend(self._get_typing_sequence(r_name))
                self.naming_sequence.append((WindowEvent.PRESS_BUTTON_START, 30))
                self.naming_sequence.append((WindowEvent.RELEASE_BUTTON_START, 200)) # Wait for game start
                
            # Execute sequence
            action = self._execute_timed_sequence(self.naming_sequence)
            
            # If sequence just finished (action is None and we were at last step)
            if action is None and not hasattr(self, 'naming_checkpoint_saved'):
                # Save checkpoint after naming
                if self.emulator:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    checkpoint_file = f"{self.save_dir}/checkpoint_naming_done_{self.player_name}_{timestamp}.state"
                    self.emulator.save_state(checkpoint_file)
                    self.naming_checkpoint_saved = True
                    print(f"✓ Checkpoint saved: Naming complete!")
            
            return action

        if action_desc == "Leave house and try to go to Route 1":
            # Wait for memory to stabilize after checkpoint load
            if not hasattr(self, 'stabilization_frames'):
                self.stabilization_frames = 0
            
            if self.stabilization_frames < 60:
                self.stabilization_frames += 1
                return None  # Do nothing while stabilizing
            
            # Robust navigation using Map ID
            if not self.emulator:
                return None
                
            map_id = self.emulator.memory.get_map_id()
            pos = self.emulator.memory.get_player_pos()
            
            # Debug every 60 frames
            if not hasattr(self, 'nav_debug_counter'):
                self.nav_debug_counter = 0
            self.nav_debug_counter += 1
            
            if self.nav_debug_counter % 60 == 0:
                print(f"[NAV] Map {map_id}, Pos {pos}")
            
            if map_id == 38:  # Bedroom
                # Collision-safe route around the PC/furniture to the stairs.
                return self._follow_route(
                    "start-bedroom",
                    [(5, 6), (5, 1), (7, 1)],
                )
                
            elif map_id == 37:  # Living Room
                # The door transition occurs when walking from y=7 to y=8.
                return self._follow_route(
                    "start-house-1f",
                    [(7, 6), (3, 6), (3, 8)],
                )


                
            elif map_id == 0:  # Pallet Town
                # Debug event flags every 120 frames
                if not hasattr(self, 'pallet_debug_counter'):
                    self.pallet_debug_counter = 0
                self.pallet_debug_counter += 1
                
                if self.pallet_debug_counter % 120 == 0:
                    # Check key event flags
                    from src.memory_map import FOLLOWED_OAK_INTO_LAB, OAK_ASKED_TO_CHOOSE_MON
                    followed_oak = self.emulator.memory.read_event_flag(*FOLLOWED_OAK_INTO_LAB)
                    oak_asked = self.emulator.memory.read_event_flag(*OAK_ASKED_TO_CHOOSE_MON)
                    
                    print(f"[EVENT FLAGS] Followed Oak: {followed_oak}, Oak Asked: {oak_asked}")
                    print(f"[PALLET TOWN] Pos: {pos}, trying to trigger Oak...")
                
                # At the north grass edge Oak interrupts movement and opens a
                # dialogue. Once that flag appears, A advances the real
                # cutscene until the game moves us into the laboratory.
                oak_appeared = bool(self.emulator.memory.read_byte(0xD74B) & 0x80)
                if oak_appeared or pos[1] <= 1:
                    return WindowEvent.PRESS_BUTTON_A
                return self._follow_route(
                    "start-pallet",
                    [(10, 6), (10, 1)],
                )

            elif map_id == 40:  # Oak's Lab cutscene/text
                return WindowEvent.PRESS_BUTTON_A
                
            else:
                # Unknown map (might be Oak's Lab after event)
                print(f"[UNKNOWN MAP {map_id}] Pos {pos}")
                return WindowEvent.PRESS_ARROW_UP

        if action_desc == "Choose starter: Bulbasaur, Charmander or Squirtle":
            return self._choose_starter_verified()

            # Legacy timed implementation retained below temporarily as
            # reference while later routes are migrated to RAM predicates.
            # Oak takes us to lab. We need to walk to the table.
            # Assuming we are at door of lab after Oak drags us.
            
            if not hasattr(self, 'starter_state'):
                self.starter_state = "APPROACH_TABLE"
                self.starter_target = None # 0=Bulbasaur, 1=Squirtle, 2=Charmander
                self.starter_attempts = 0
                
            # State Machine for Starter Choice
            if self.starter_state == "APPROACH_TABLE":
                # Walk UP to the table area
                if not hasattr(self, 'approach_seq'):
                    self.approach_seq = [
                        (WindowEvent.PRESS_ARROW_UP, 180), (WindowEvent.RELEASE_ARROW_UP, 5)
                    ]
                action = self._execute_timed_sequence(self.approach_seq)
                if action is None:
                    # Done approaching
                    self.starter_state = "PICK_STARTER"
                    # Reset seq index for next sequence
                    if hasattr(self, 'seq_index'): del self.seq_index
                return action
                
            elif self.starter_state == "PICK_STARTER":
                import random
                # RNG Choice
                if self.starter_choice is not None:
                    self.starter_target = self.starter_choice
                else:
                    self.starter_target = random.choice([0, 1, 2])
                # Canonical product order: Bulbasaur, Charmander, Squirtle.
                # Oak's physical table order is handled below and must not leak
                # into the profile/config index used by the rest of the app.
                starters = ["BULBASAUR", "CHARMANDER", "SQUIRTLE"]
                choice = starters[self.starter_target]
                
                print(f"[{self.player_name}] 🤔 Considering {choice}...")
                if choice == "BULBASAUR":
                    print(f"[{self.player_name}] 🍃 Bulbasaur: Strong vs Brock/Misty. Good for beginners.")
                elif choice == "SQUIRTLE":
                    print(f"[{self.player_name}] 💧 Squirtle: Strong vs Brock. Balanced choice.")
                elif choice == "CHARMANDER":
                    print(f"[{self.player_name}] 🔥 Charmander: Weak vs Brock/Misty. For experts/hard mode!")
                
                self.starter_state = "NAVIGATE_TO_BALL"
                return None
                
            elif self.starter_state == "NAVIGATE_TO_BALL":
                # We are roughly at the table center.
                # Bulbasaur (Left), Squirtle (Middle), Charmander (Right)
                # Adjust position based on target
                
                if not hasattr(self, 'nav_ball_seq'):
                    seq = []
                    # Reset position (move right then left to align? Hard to know exact pos)
                    # Let's assume we are centered below Squirtle after APPROACH_TABLE
                    
                    if self.starter_target == 0: # Bulbasaur (Left)
                        seq.append((WindowEvent.PRESS_ARROW_LEFT, 20))
                        seq.append((WindowEvent.RELEASE_ARROW_LEFT, 5))
                    elif self.starter_target == 1: # Charmander (Right)
                        seq.append((WindowEvent.PRESS_ARROW_RIGHT, 20))
                        seq.append((WindowEvent.RELEASE_ARROW_RIGHT, 5))
                    # Squirtle (2) is middle, no move needed if aligned
                    
                    # Face UP
                    seq.append((WindowEvent.PRESS_ARROW_UP, 5))
                    seq.append((WindowEvent.RELEASE_ARROW_UP, 5))
                    
                    self.nav_ball_seq = seq
                    
                action = self._execute_timed_sequence(self.nav_ball_seq)
                if action is None:
                    self.starter_state = "INTERACT"
                    if hasattr(self, 'seq_index'): del self.seq_index
                    if hasattr(self, 'nav_ball_seq'): del self.nav_ball_seq
                return action
                
            elif self.starter_state == "INTERACT":
                # Press A to open menu
                if not hasattr(self, 'interact_seq'):
                    self.interact_seq = [
                        (WindowEvent.PRESS_BUTTON_A, 10), (WindowEvent.RELEASE_BUTTON_A, 60) # Wait for text
                    ]
                action = self._execute_timed_sequence(self.interact_seq)
                if action is None:
                    self.starter_state = "DECIDE"
                    if hasattr(self, 'seq_index'): del self.seq_index
                    if hasattr(self, 'interact_seq'): del self.interact_seq
                return action
                
            elif self.starter_state == "DECIDE":
                # A configured trainer preference is a decision, not a random
                # retry loop. Future personality logic may deliberately compare
                # starters before this state, but confirmation stays reliable.
                print(f"[{self.player_name}] Confirming configured starter choice. ✅")
                self.starter_state = "CONFIRM"
                return None
                
            elif self.starter_state == "CONFIRM":
                party_count = self.emulator.memory.get_party_count()
                first_species = self.emulator.memory.read_byte(0xD16B)
                first_level = self.emulator.memory.read_byte(0xD18C)
                starter_materialized = (
                    party_count > 0
                    and first_species not in (0, 0xFF)
                    and first_level > 0
                )
                if starter_materialized:
                    if self.emulator and not hasattr(self, 'starter_checkpoint_saved'):
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        checkpoint_file = f"{self.save_dir}/checkpoint_starter_chosen_{self.player_name}_{timestamp}.state"
                        self.emulator.save_state(checkpoint_file)
                        self.starter_checkpoint_saved = True
                        print(f"✓ Checkpoint saved: Starter chosen!")
                    self.current_step += 1
                    return None

                # Confirm the selected ball once. B then advances received
                # text and answers the nickname prompt with No. The script
                # advances only after the complete party struct exists in RAM.
                if not hasattr(self, "starter_confirmation_sent"):
                    self.starter_confirmation_sent = True
                    return WindowEvent.PRESS_BUTTON_A
                return WindowEvent.PRESS_BUTTON_B
                
            elif self.starter_state == "CANCEL":
                if not hasattr(self, 'cancel_seq'):
                    self.cancel_seq = [
                        (WindowEvent.PRESS_BUTTON_B, 10), (WindowEvent.RELEASE_BUTTON_B, 30)
                    ]
                action = self._execute_timed_sequence(self.cancel_seq)
                if action is None:
                    # Go back to picking
                    self.starter_state = "PICK_STARTER"
                    if hasattr(self, 'seq_index'): del self.seq_index
                    if hasattr(self, 'cancel_seq'): del self.cancel_seq
                    
                    # Move back to center to reset position for next pick
                    # This is tricky without knowing where we are.
                    # Best guess: Inverse of previous move
                    if self.starter_target == 0: # Was Left
                        self.reset_move = [(WindowEvent.PRESS_ARROW_RIGHT, 20), (WindowEvent.RELEASE_ARROW_RIGHT, 5)]
                    elif self.starter_target == 2: # Was Right
                        self.reset_move = [(WindowEvent.PRESS_ARROW_LEFT, 20), (WindowEvent.RELEASE_ARROW_LEFT, 5)]
                    else:
                        self.reset_move = []
                        
                    self.starter_state = "RESET_POS"
                return action
                
            elif self.starter_state == "RESET_POS":
                if not hasattr(self, 'reset_seq'):
                    self.reset_seq = getattr(self, 'reset_move', [])
                
                action = self._execute_timed_sequence(self.reset_seq)
                if action is None:
                    self.starter_state = "PICK_STARTER"
                    if hasattr(self, 'seq_index'): del self.seq_index
                    if hasattr(self, 'reset_seq'): del self.reset_seq
                return action
            
            return None
            
        if action_desc == "Accept or reject optional rival fight":
            return self._complete_oak_rival_event()

            # Legacy timed implementation retained temporarily as reference.
            # Rival challenges us when we try to leave.
            # We need to walk down to trigger it.
            
            # After battle, we save
            if hasattr(self, 'battle_finished') and self.battle_finished:
                 if self.emulator:
                     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                     filename = f"{self.save_dir}/rival_defeated_{self.player_name}_{timestamp}.state"
                     self.emulator.save_state(filename)
                 self.current_step += 1
                 self.tick_counter = 0
                 return None
            
            # If we haven't triggered battle yet, walk down then spam A
            if not hasattr(self, 'rival_trigger_sequence'):
                self.rival_trigger_sequence = [
                    (WindowEvent.PRESS_ARROW_DOWN, 200), (WindowEvent.RELEASE_ARROW_DOWN, 5)
                ]
                # Then spam A forever (handled by returning PRESS_BUTTON_A below)
            
            # We use a separate sequence for walking down
            if not hasattr(self, 'rival_walk_done'):
                action = self._execute_timed_sequence(self.rival_trigger_sequence)
                if action is None:
                    self.rival_walk_done = True
                    # Reset seq_index for future sequences? 
                    # _execute_timed_sequence resets it when done, but we are reusing the method.
                    # Actually, _execute_timed_sequence increments current_step when done!
                    # We DON'T want to increment current_step yet.
                    # We want to stay on this step until battle finishes.
                    # So we should NOT use _execute_timed_sequence for this sub-task if it increments step.
                    # Or we decrement it back.
                    self.current_step -= 1 
                return action

            return WindowEvent.PRESS_BUTTON_A

            return WindowEvent.PRESS_BUTTON_A
            
        # Fallback to LLM for unknown steps
        if self.llm_agent:
            # Rate limit LLM calls (e.g., once every 60 frames)
            if not hasattr(self, 'llm_cooldown'):
                self.llm_cooldown = 0
                
            if self.llm_cooldown > 0:
                self.llm_cooldown -= 1
                # Continue holding previous action if it was a move
                if hasattr(self, 'last_llm_action') and self.last_llm_action:
                     # Only hold moves, not A/B/Start to avoid spamming interactions
                     if self.last_llm_action in [WindowEvent.PRESS_ARROW_UP, WindowEvent.PRESS_ARROW_DOWN, WindowEvent.PRESS_ARROW_LEFT, WindowEvent.PRESS_ARROW_RIGHT]:
                         return self.last_llm_action
                return None
                
            # Prepare state for LLM
            state = {
                "map_id": self.emulator.memory.get_map_id() if self.emulator else "Unknown",
                "pos": self.emulator.memory.get_player_pos() if self.emulator else "Unknown",
                "party_count": self.emulator.memory.get_party_count() if self.emulator else 0
            }
            
            # If action_desc is a list (from walkthrough), take the first item or join them
            if isinstance(action_desc, list):
                action_desc = " ".join(action_desc)
            
            action = self.llm_agent.get_navigation_action(str(action_desc), state)
            
            if action:
                self.last_llm_action = action
                self.llm_cooldown = 60 # Wait 1 second before asking again
                return action
            else:
                self.llm_cooldown = 60 # Wait even if failed
                
        return None

    def _execute_timed_sequence(self, sequence):
        """
        Executes a list of (Action, Duration) tuples.
        """
        if not hasattr(self, 'seq_index'):
            self.seq_index = 0
            self.seq_timer = 0
            
        if self.seq_index >= len(sequence):
            self.current_step += 1
            self.seq_index = 0
            self.seq_timer = 0
            return None
            
        action, duration = sequence[self.seq_index]
        
        self.seq_timer += 1
        if self.seq_timer >= duration:
            self.seq_index += 1
            self.seq_timer = 0
            return None
            
        # Update move flag
        if action in [WindowEvent.PRESS_ARROW_UP, WindowEvent.PRESS_ARROW_DOWN, WindowEvent.PRESS_ARROW_LEFT, WindowEvent.PRESS_ARROW_RIGHT]:
            self.last_action_was_move = True
            
        return action

    def _detect_checkpoint_step(self):
        """
        Auto-detect which step we should be on based on game state.
        Useful when loading from checkpoint.
        """
        if not self.emulator:
            return
            
        map_id = self.emulator.memory.get_map_id()
        pos = self.emulator.memory.get_player_pos()
        party_count = self.emulator.memory.get_party_count()
        
        print(f"[CHECKPOINT DETECT] Map: {map_id}, Pos: {pos}, Party: {party_count}")
        
        # Logic to detect step:
        # - If in bedroom (Map 38), we completed naming → step 3 (Leave house)
        # - If in Pallet Town (Map 0) with no party, still leaving house
        # - If in Oak's Lab and no party → step 4 (Choose starter)
        # - If party_count > 0 → step 5 (Rival fight)
        
        if map_id == 38:  # Bedroom after naming
            print("[CHECKPOINT] Detected: In bedroom after naming. Skipping to 'Leave house'")
            # Ensure we are in 'start' task
            if "game_flow" in self.walkthrough and "start" in self.walkthrough["game_flow"]:
                self.steps = self.walkthrough["game_flow"]["start"]["actions"]
                self.current_task_name = "start"
            self.current_step = 3  # "Leave house and try to go to Route 1"
            
        elif map_id == 37:  # Living room
            print("[CHECKPOINT] Detected: In living room. Continuing 'Leave house'")
            if "game_flow" in self.walkthrough and "start" in self.walkthrough["game_flow"]:
                self.steps = self.walkthrough["game_flow"]["start"]["actions"]
                self.current_task_name = "start"
            self.current_step = 3
            
        elif map_id == 0 and party_count == 0:  # Pallet Town, no Pokemon
            print("[CHECKPOINT] Detected: Outside, no Pokemon. Continuing 'Leave house'")
            if "game_flow" in self.walkthrough and "start" in self.walkthrough["game_flow"]:
                self.steps = self.walkthrough["game_flow"]["start"]["actions"]
                self.current_task_name = "start"
            self.current_step = 3
            
        elif map_id == 40 and party_count > 0:  # Oak's Lab with a Pokemon
            # A luta com o rival acontece no laboratório. O ramo antigo
            # pegava *qualquer* mapa com time — o AARON, no ginásio de
            # Cerulean (mapa 65), era reescrito para o oak_event e ficava
            # parado apertando nada (medido 2026-08-12).
            print("[CHECKPOINT] Detected: In Oak's Lab with a Pokemon. Starting 'Rival fight'")
            # This corresponds to 'oak_event' task usually
            if "game_flow" in self.walkthrough and "oak_event" in self.walkthrough["game_flow"]:
                self.steps = self.walkthrough["game_flow"]["oak_event"]["actions"]
                self.current_task_name = "oak_event"
                self.current_step = 1 # "Accept or reject optional rival fight" (Index 1 in oak_event)
            else:
                 # Fallback if oak_event not found
                 self.current_step = 5  # "Accept or reject optional rival fight" (if using flattened list, but we are not)
        # else: keep current_step as is (probably fine)

    def _navigate_to(self, target_x, target_y):
        """
        Uses Navigation class to move to target.
        Holds buttons long enough to actually move character.
        """
        if not self.navigation:
            return None
        
        # Initialize navigation state
        if not hasattr(self, 'nav_timer'):
            self.nav_timer = 999  # Force immediate recalc
            self.nav_action = None
            
        # If we don't have a direction yet or timer expired, get new direction
        if self.nav_timer >= 1:  # Check every step. The env handles the actual button press duration.
            self.nav_action = self.navigation.get_path_to(target_x, target_y)
            self.nav_timer = 0
            
            if self.nav_action is None:
                # Reached target
                # print(f"[NAV] Reached target ({target_x}, {target_y})!")
                return None
            
            # print(f"[NAV] New action: {self.nav_action}")
        
        # Hold the button
        self.nav_timer += 1
        self.last_action_was_move = True
        return self.nav_action

    def _choose_starter_verified(self):
        """Choose the configured starter and wait for a complete party struct."""
        party_count = int(self.emulator.memory.get_party_count())
        first_species = int(self.emulator.memory.read_byte(0xD16B))
        first_level = int(self.emulator.memory.read_byte(0xD18C))
        if party_count > 0 and first_species not in (0, 0xFF) and first_level > 0:
            if not hasattr(self, "starter_checkpoint_saved"):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                checkpoint_file = f"{self.save_dir}/checkpoint_starter_chosen_{self.player_name}_{timestamp}.state"
                self.emulator.save_state(checkpoint_file)
                self.starter_checkpoint_saved = True
                print("✓ Checkpoint saved: Starter chosen!")
            self.current_step += 1
            return None

        # During the nickname prompt party_count is already one, but the party
        # struct is still zero-filled. B declines the nickname and lets the
        # game finalize the real starter data.
        if party_count > 0:
            return WindowEvent.PRESS_BUTTON_B

        # Verified Blue table order at y=3, approached from y=4:
        # x=6 Charmander, x=7 Squirtle, x=8 Bulbasaur.
        target_x = {0: 8, 1: 6, 2: 7}[int(self.starter_choice or 0)]
        current_x, current_y = self.emulator.memory.get_player_pos()
        if current_y < 4:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_DOWN
        if current_y > 4:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_UP
        if current_x < target_x:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_RIGHT
        if current_x > target_x:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_LEFT
        if not hasattr(self, "starter_faced_ball"):
            self.starter_faced_ball = True
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_UP

        # Advances species description, confirmation and received text. The
        # party-count branch above switches to B exactly at nickname handling.
        return WindowEvent.PRESS_BUTTON_A

    def _complete_oak_rival_event(self):
        """Clear post-starter text, trigger the rival and verify its event flag."""
        battled_rival = bool(self.emulator.memory.read_byte(0xD74B) & (1 << 3))
        if battled_rival or (hasattr(self, "battle_finished") and self.battle_finished):
            self.battle_finished = False
            self.current_step += 1
            return None

        # (6,4) is occupied once the rival has taken his starter, so the row in
        # front of the table is not a through path. Drop to y=5 first; the exit
        # corridor is reached from there.
        return self._follow_route(
            "oak-rival-trigger",
            [(7, 5), (5, 5), (5, 10), (5, 12)],
        )

    def _run_parcel_event(self):
        """Fetch and deliver Oak's Parcel using the verified speedrun route."""
        map_id = int(self.emulator.memory.get_map_id())
        position = self.emulator.memory.get_player_pos()
        event_byte = int(self.emulator.memory.read_byte(0xD74E))
        has_parcel = bool(event_byte & (1 << 1))
        got_pokedex = bool(self.emulator.memory.read_byte(0xD74B) & (1 << 5))

        if got_pokedex:
            return None

        if map_id == 40:
            if not has_parcel:
                return self._follow_route("parcel-leave-lab", [(5, 12)])

            # Approach Oak from above exactly as the reference route does.
            if position != (5, 1):
                return self._follow_route(
                    "parcel-deliver-oak",
                    [(5, 3), (4, 3), (4, 1), (5, 1)],
                )
            if not getattr(self, "parcel_faced_oak", False):
                self.parcel_faced_oak = True
                self.last_action_was_move = True
                return WindowEvent.PRESS_ARROW_DOWN
            return WindowEvent.PRESS_BUTTON_A

        if map_id == 42 and not has_parcel:
            # The parcel clerk is immediately left of the entrance tile. The
            # flag at D74E is the only completion signal; keep confirming the
            # real dialogue until the cartridge records the parcel.
            if position != (2, 5):
                return self._follow_route(
                    "parcel-get-mart", [(3, 7), (3, 5), (2, 5)]
                )
            if self.emulator.memory.read_byte(0xD52A) != 2:
                self.last_action_was_move = True
                return WindowEvent.PRESS_ARROW_LEFT
            return WindowEvent.PRESS_BUTTON_A

        if not has_parcel:
            routes = {
                # Antes do primeiro Centro Pokémon, o whiteout devolve o bot
                # para a casa da mãe. Nenhum executor conhecia esses dois
                # mapas, e três treinadores ficaram parados na sala apertando A.
                38: [(7, 1), (7, 7), (2, 7), (2, 8)],
                37: [(2, 7), (2, 8)],
                0: [(9, 12), (9, 2), (10, 2), (10, -1)],
                12: [
                    (10, 30), (8, 30), (8, 24), (12, 24), (12, 20),
                    (9, 20), (9, 14), (14, 14), (14, 2), (10, 2), (10, -1),
                ],
                1: [(20, 28), (19, 28), (19, 20), (29, 20), (29, 19)],
                42: [(3, 5), (3, 8)],
            }
            route = routes.get(map_id)
            if route:
                return self._follow_route(f"parcel-outbound-{map_id}", route)
        else:
            routes = {
                38: [(7, 1), (7, 7), (2, 7), (2, 8)],
                37: [(2, 7), (2, 8)],
                42: [(3, 5), (3, 8)],
                # The intermediate waypoints at (26,21)/(26,30) create a
                # false two-tile loop when resumed at the Viridian barrier.
                # One real south-exit anchor lets collision-aware steering
                # choose the currently open contour — but a single anchor is
                # also a route with no next step: standing exactly on (20,35),
                # a trainer had nothing left to want and sidestepped forever
                # with Oak's parcel in the bag. The tile past the border is
                # what turns "arrived" into "leave".
                1: [(20, 35), (20, 36)],
                12: [
                    (10, 3), (8, 3), (8, 18), (9, 18), (9, 21),
                    (12, 21), (12, 24), (10, 24), (10, 36),
                ],
                0: [(10, 7), (9, 7), (9, 12), (12, 12), (12, 11)],
            }
            route = routes.get(map_id)
            if route:
                return self._follow_route(f"parcel-return-{map_id}", route)

        # A transition or story textbox can temporarily expose a map before its
        # coordinates settle, and a whiteout can drop the run into a map this
        # quest never planned for. Walking out beats pressing A forever.
        return self._leave_unknown_map()

    # One ball is enough to satisfy the story predicate but not enough to build
    # a team: the first failed throw leaves the bot unable to catch anything for
    # the rest of the route. The quantity selector debits money without adding
    # stock on this cartridge, so the reliable path is repeating the validated
    # single purchase and re-reading the bag between each one.
    POKEBALL_TARGET = int(os.getenv("POKEAI_POKEBALL_TARGET", "8"))

    def _run_buy_pokeballs(self):
        """Return to Viridian and stock Poké Balls, one verified buy at a time.

        The story predicate remains the source of truth: this controller only
        stops once item id 4 is present in the real Gen I bag.  Menu addresses
        and cursor handling mirror the reference PokeBot shop transaction.
        """
        map_id = int(self.emulator.memory.get_map_id())

        if self._bag_item_count(4) >= self.POKEBALL_TARGET or (
            self._bag_item_count(4) > 0 and not self._can_afford_another_ball()
        ):
            # Close any remaining shop textbox before handing control to the
            # next quest. The QuestGraph has already verified the purchase.
            if map_id == 42 and self._menu_is_open():
                return WindowEvent.PRESS_BUTTON_B
            return None

        routes = {
            38: [(7, 1), (7, 7), (2, 7), (2, 8)],
            37: [(2, 7), (2, 8)],
            # After delivering the parcel the player is above Oak at (5, 1).
            # Walk around him; moving straight down only reopens his dialogue.
            40: [(4, 1), (4, 3), (5, 3), (5, 12)],
            0: [(9, 12), (9, 2), (10, 2), (10, -1)],
            12: [
                (10, 30), (8, 30), (8, 24), (12, 24), (12, 20),
                (9, 20), (9, 14), (14, 14), (14, 2), (10, 2), (10, -1),
            ],
            1: [(20, 28), (19, 28), (19, 20), (29, 20), (29, 19)],
        }
        if map_id in routes:
            return self._follow_route(f"buy-balls-{map_id}", routes[map_id])

        if map_id not in POKE_MART_MAP_IDS:
            # The hand-measured routes above only know the way back to
            # Viridian's Mart. Before giving up, ask this map whether it has a
            # Mart door of its own — a trainer that spends its last ball north
            # of Route 2 has no way home and never buys another one.
            nearest = self._run_nearest_mart("buy-balls-nearest")
            if nearest is not None:
                return nearest
            # A whiteout before the first Pokémon Center sends the run back to
            # its mother's house, a map this quest never planned for. Three
            # trainers stood in that living room pressing A while the fourth
            # walked to Pewter.
            return self._leave_unknown_map()

        return self._run_shop_counter()

    def _can_afford_another_ball(self):
        """Money is BCD across 0xD347..0xD349; a Poké Ball costs 200."""
        try:
            digits = 0
            for offset in range(3):
                byte = int(self.emulator.memory.read_byte(0xD347 + offset))
                digits = digits * 100 + (byte >> 4) * 10 + (byte & 0x0F)
            return digits >= 200
        except Exception:
            return False

    def _mart_item_list(self):
        """O que este balcão vende, na ordem em que a lista aparece.

        Contagem em `MART_ITEM_COUNT_ADDRESS`, ids logo em seguida, 0xFF como
        fim. Achado varrendo a RAM pela sequência conhecida de Viridian
        (`04 0B 0F 0C`) a partir de um save com o menu aberto — o endereço
        antigo, 0xCF8C, caía 17 bytes depois e devolvia lixo.
        """
        count = int(self.emulator.memory.read_byte(MART_ITEM_COUNT_ADDRESS))
        items = []
        for offset in range(min(max(count, 0), 20)):
            item_id = int(
                self.emulator.memory.read_byte(MART_ITEM_LIST_ADDRESS + offset)
            )
            if item_id in (0x00, 0xFF):
                break
            items.append(item_id)
        return items

    def _buy_first_shop_item(self):
        """Navigate Blue's shop menus and buy the best ball in stock.

        The Mart's item list is read from the cartridge: `wMartItemList` é a
        contagem em **0xCF7B** seguida dos ids em **0xCF7C**, terminados por
        0xFF. O clerk vende o que essa lista diz, então preferir Great Ball a
        Poké Ball é fato da lista, não palpite sobre a cidade. O seletor de
        quantidade dá a volta: com o valor em zero, UP salta direto para o
        máximo que o dinheiro compra — o "vai para a esquerda do zero" do
        operador — em vez de somar uma bola por aperto.

        **Dois erros medidos no cartucho em 2026-08-16**, com três bots novos
        parados no Mart de Viridian com ¥3175 e a mochila vazia:

        1. o endereço estava 17 bytes adiante (0xCF8C), e o que voltava de lá
           era lixo — `['0xcf', '0x81', '0xcd', ...]`, ids que não existem;
        2. e a navegação comparava **índice de linha com id de item**: o
           `best_ball` é 4 (o id da Poké Ball) e o cursor era empurrado até a
           *linha* 4, que não existe numa lista de quatro. Ele parava na
           última linha e ia comprar **BURN HEAL** por ¥250.

        A lista de Viridian, lida do endereço certo: `04 0B 0F 0C FF` —
        Poké Ball, Antidote, Parlyz Heal, Burn Heal.
        """
        if not self._menu_is_open():
            return WindowEvent.PRESS_BUTTON_A

        shop_menu = int(self.emulator.memory.read_byte(0xCC52))
        transaction_menu = int(self.emulator.memory.read_byte(0xCF8B))
        menu_row = int(self.emulator.memory.read_byte(0xCC26))
        menu_column = int(self.emulator.memory.read_byte(0xCC25))

        # BUY/SELL menu. BUY is row zero.
        if shop_menu == 32:
            return (
                WindowEvent.PRESS_ARROW_UP
                if menu_row > 0
                else WindowEvent.PRESS_BUTTON_A
            )

        # Yes/no confirmation column used by the shop dialogue.
        if menu_column == 15:
            return WindowEvent.PRESS_BUTTON_A

        if transaction_menu == 123:
            # Item selector: a lista que este balcão vende, lida do cartucho.
            # A linha do cursor mais a rolagem (0xCC36) dá o índice escolhido.
            mart_list = self._mart_item_list()
            # Prefer the best ball available: Great Ball (5) over Poké Ball
            # (4). Ultra Ball (6) does not exist in any pre-Celadon Mart, but
            # if a future city sells it, the same preference picks it.
            balls = [
                index for index, item in enumerate(mart_list)
                if item in (4, 5, 6)
            ]
            if not balls:
                # Balcão sem bola nenhuma: sair. Comprar outra coisa é gastar
                # o dinheiro das bolas — foi o Burn Heal de ¥250.
                return WindowEvent.PRESS_BUTTON_B
            # O alvo é o **índice** da melhor bola na lista, não o id dela.
            best_index = max(balls, key=lambda index: mart_list[index])
            selected_index = menu_row + int(self.emulator.memory.read_byte(0xCC36))
            if selected_index != best_index:
                return (
                    WindowEvent.PRESS_ARROW_UP
                    if selected_index > best_index
                    else WindowEvent.PRESS_ARROW_DOWN
                )
            if shop_menu == 161:
                amount = int(self.emulator.memory.read_byte(0xCF96))
                # Quantity selector: at zero, UP wraps to the maximum the
                # money can buy — one press, not one ball per press. Above
                # zero, back down to zero so the wrap works every time.
                if amount == 0:
                    return WindowEvent.PRESS_ARROW_UP
                if amount > 1:
                    return WindowEvent.PRESS_ARROW_DOWN
                if amount < 0:
                    return WindowEvent.PRESS_ARROW_UP
            return WindowEvent.PRESS_BUTTON_A

        # Advance clerk text or back out of an unrelated menu state. Repeated
        # calls re-read RAM, so this cannot declare a purchase by timing alone.
        return WindowEvent.PRESS_BUTTON_B

    def _run_route_2_nav(self):
        """Leave Viridian through the north gate and enter the forest.

        A whiteout before the player has registered a Pokémon Center returns
        the save to Pallet.  The objective is sticky, so this route must also
        know how to rebuild the complete Pallet -> Viridian leg.
        """
        map_id = int(self.emulator.memory.get_map_id())
        if map_id == 51:
            return None

        if map_id == 42:
            if self._menu_is_open():
                return WindowEvent.PRESS_BUTTON_B
            return self._follow_route(
                "route2-leave-mart", [(2, 5), (3, 5), (3, 8)]
            )

        routes = {
            0: [(9, 6), (9, 2), (10, 2), (10, -1)],
            12: [
                (10, 35), (10, 30), (8, 30), (8, 24), (12, 24),
                (12, 20), (9, 20), (9, 14), (14, 14), (14, 2),
                (10, 2), (10, -1),
            ],
            13: [
                (7, 71), (7, 57), (4, 57), (4, 52), (10, 52),
                (10, 44), (3, 44), (3, 43),
            ],
            50: [(4, 7), (4, 1), (5, 1), (5, 0)],
        }
        if map_id == 1:
            _, y = self.emulator.memory.get_player_pos()
            # A route resumed at (17,3) used to select (17,4) as its nearest
            # point and walk back south forever. From the upper half of the
            # city, the only useful objective is the north exit itself. Keep a
            # separate route id so a stale index from the southern leg cannot
            # be reused after a whiteout or process restart.
            routes[1] = (
                [
                    (20, 35), (20, 28), (19, 28), (19, 20),
                    (16, 20), (16, 16), (18, 16), (18, 6),
                    (17, 4), (17, 0), (17, -1),
                ]
                if y > 25
                else [
                    (17, 4), VIRIDIAN_NORTH_EXIT, (17, -1),
                ]
            )
            route_id_suffix = "-south" if y > 25 else "-north"
        else:
            route_id_suffix = ""
        if map_id == VIRIDIAN_CITY_MAP_ID:
            old_man_action = self._viridian_old_man_action()
            if old_man_action is not None:
                return old_man_action
        route = routes.get(map_id)
        if route:
            return self._follow_route(f"route2-{map_id}{route_id_suffix}", route)
        return self._leave_unknown_map()

    def _viridian_old_man_action(self):
        """Talk to the north-exit NPC when the cartridge says he is in front.

        A failed movement is not enough evidence to call a sprite the tutorial
        NPC. The route only enables this small interaction state machine on the
        measured approach tile and only when live collision identifies a
        sprite. Dialog progress is observed through the menu flag; completion
        is not declared from the number of button presses.
        """
        position = self.emulator.memory.get_player_pos()
        if tuple(position) != VIRIDIAN_OLD_MAN_APPROACH:
            return None

        blocked = self._tile_truth()
        active = getattr(self, "viridian_old_man_dialog_active", False)
        if active:
            direction = getattr(self, "viridian_old_man_direction", None)
            if (
                not getattr(self, "viridian_old_man_dialog_seen", False)
                and blocked.get(direction) != "sprite"
            ):
                # The NPC can walk away between the facing press and the next
                # controller tick. Do not press A into empty ground or keep a
                # stale dialog latch alive.
                self.viridian_old_man_dialog_active = False
                return None
            self.viridian_old_man_dialog_steps = (
                getattr(self, "viridian_old_man_dialog_steps", 0) + 1
            )
            if self._menu_is_open():
                self.viridian_old_man_dialog_seen = True
                if self.viridian_old_man_dialog_steps <= VIRIDIAN_OLD_MAN_DIALOG_LIMIT:
                    return WindowEvent.PRESS_BUTTON_A
                # A stuck text flag is not a route wall. B is the safe input
                # that advances or closes Gen I text without choosing a move.
                self.viridian_old_man_dialog_active = False
                return WindowEvent.PRESS_BUTTON_B
            if not getattr(self, "viridian_old_man_dialog_seen", False):
                return WindowEvent.PRESS_BUTTON_A

            if blocked.get(direction) == "sprite":
                # CFC4 briefly drops while a page is being rendered. Keep
                # confirming until the sprite is no longer the live blocker.
                if self.viridian_old_man_dialog_steps <= VIRIDIAN_OLD_MAN_DIALOG_LIMIT:
                    return WindowEvent.PRESS_BUTTON_A
                self.viridian_old_man_dialog_active = False
                return None

            # The dialog ended and the obstacle moved or stopped blocking the
            # approach. The next route call may now head for the exit.
            self.viridian_old_man_dialog_active = False
            self.viridian_old_man_interaction_confirmed = True
            return None

        direction = next(
            (
                candidate
                for candidate in ("U", "D")
                if blocked.get(candidate) == "sprite"
            ),
            None,
        )
        if direction is None:
            return None

        self.viridian_old_man_dialog_active = True
        self.viridian_old_man_dialog_seen = False
        self.viridian_old_man_dialog_steps = 0
        self.viridian_old_man_direction = direction
        self.route_last_issue = "old_man_dialog"
        self.last_action_was_move = True
        return ROUTE_EVENTS[direction]

    def _run_viridian_forest_nav(self):
        """Cross Viridian Forest and reach Pewter using collision-safe paths."""
        map_id = int(self.emulator.memory.get_map_id())
        if map_id in (2, 54):
            return None

        # Aqui havia a viagem de volta ao Centro por HP baixo, com um ramo
        # medido à mão para Viridian e um "meia travessia atrás, meia à
        # frente" para decidir qual Centro. Saiu inteira: sem cura automática,
        # HP baixo não interrompe mais a travessia. Estar dentro de um Centro
        # continua valendo checkpoint, e isso é tratado antes de todo executor,
        # na regra no topo de `step`.

        if map_id in (0, 12, 1, 50) or (
            map_id == 13 and self.emulator.memory.get_player_pos()[1] > 20
        ):
            return self._run_route_2_nav()

        # Treino antes de sair da Floresta. Cinco tentativas anteriores erraram
        # *onde* treinar e cada uma custou uma corrida; a diferença agora é que
        # a grama vem medida do cartucho, com a distância aos treinadores junto.
        if map_id == VIRIDIAN_FOREST_MAP_ID and self._needs_training():
            step = self._train_in_measured_grass(map_id)
            if step is not None:
                return step

        routes = {
            51: [
                (17, 47), (17, 43), (26, 43), (26, 34), (25, 34),
                (25, 32), (27, 32), (27, 20), (25, 20), (25, 12),
                (25, 9), (17, 9), (17, 16), (13, 16), (13, 3),
                (7, 3), (7, 22), (1, 22), (1, 19), (1, 18),
                (1, 16), (1, 5), (1, -1),
            ],
            47: [(4, 7), (4, 1), (5, 1), (5, 0)],
            13: [(3, 11), (3, 8), (8, 8), (8, -1)],
        }
        route = routes.get(map_id)
        if route:
            return self._follow_route(f"forest-{map_id}", route)
        return self._leave_unknown_map()

    def _needs_training(self):
        """Fraco demais para a história, segundo as metas da linha inicial.

        As metas vieram do operador (2026-08-12): o inicial evolui uma vez
        (nível 16 nas três linhas), e o Charmander ainda precisa de um
        Butterfree no time — a linha Caterpie/Metapod evolui no 10 e
        Confusion no 12 carrega contra o Brock. O tipo de missão da task
        file decide o quanto farmar:

        - STORY: nunca farma, a rota corre;
        - FARM: farma até as metas (inclusive o Pikachu da Misty) — a saída
          é o operador trocar a missão pela UX;
        - AUTO (padrão): farma enquanto as metas não estão cumpridas.
        """
        mission = getattr(self, "mission_type", "AUTO")
        if mission == "STORY":
            return False
        return bool(self._farm_goals(include_pikachu=(mission == "FARM")))

    def _farm_goals(self, include_pikachu=False):
        """Metas de farm não cumpridas — lista vazia quando o time está pronto.

        Retorna os nomes das metas pendentes para o relatório e para o
        operador ver o que falta (ex.: `evolucao_inicial`, `butterfree`,
        `pikachu`).
        """
        goals = []
        starter = self._starter_internal()
        if (
            starter in CHARMANDER_LINE_INTERNAL
            and BUTTERFREE_INTERNAL not in set(self._party_internal_ids())
            and self._starter_level() < BROCK_BRUTE_FORCE_LEVEL
        ):
            # A meta do Butterfree existe porque Confusion resolve o Brock que
            # o Charmander não resolve. Só que ela virou gate infinito na
            # corrida do operador em 2026-08-17: o IARON ficou com **Charmeleon
            # 34 e Metapod 8** na Floresta, porque quem mata o encontro é o
            # inicial e o Metapod nunca chega ao 10 para evoluir. Nível resolve
            # o mesmo problema por outro caminho — um inicial no 25 passa por
            # cima do ginásio de Pewter —, então o que vier primeiro encerra o
            # farm. Ordem do operador.
            goals.append("butterfree")
        if self._starter_level() < FIRST_EVOLUTION_LEVEL:
            goals.append("evolucao_inicial")
        if include_pikachu and \
                PIKACHU_INTERNAL not in set(self._party_internal_ids()):
            goals.append("pikachu")
        return goals

    def _starter_internal(self):
        """Id interno da Gen I do primeiro Pokémon da party (o inicial)."""
        try:
            return int(self.emulator.memory.read_byte(0xD164))
        except Exception:
            return 0

    def _starter_level(self):
        try:
            return int(self.emulator.memory.read_byte(0xD18C))
        except Exception:
            return 0

    def _party_internal_ids(self):
        read = self.emulator.memory.read_byte
        count = min(int(read(0xD163)), 6)
        return [int(read(0xD164 + index)) for index in range(count)]

    def _party_has_effective_move(self):
        """Alguém do time tem golpe que Rocha e Terra não resistem?"""
        table = self._move_table()
        count = min(int(self.emulator.memory.get_party_count()), 6)
        read = self.emulator.memory.read_byte
        for index in range(count):
            struct = 0xD16B + index * 44
            for slot in range(4):
                move_id = int(read(struct + 8 + slot))
                if not move_id:
                    continue
                move = table.get(move_id)
                if move and move.power and move.type in GYM_EFFECTIVE_TYPES:
                    return True
        return False

    def _move_table(self):
        """Potência e tipo de cada golpe, lidos do cartucho uma vez."""
        table = getattr(self, "move_table", None)
        if table is None or not len(table):
            from src.move_data import MoveTable

            table = self.move_table = MoveTable.from_memory(self.emulator.memory)
        return table

    def _train_in_measured_grass(self, map_id):
        """Ir e voltar entre duas células de mato longe de todo treinador.

        A grama, a distância até a porta e a posição de cada treinador saem de
        `static_maps.json`, extraído da ROM. É a única das seis tentativas com
        medição por trás: na Floresta são 365 células de mato, todas alcançáveis
        da porta sul, e os três bug catchers ficam a mais de vinte casas do
        trecho escolhido.

        O par de células é fixado uma vez e não se refaz: "pisar na grama mais
        próxima" parece local e não é — escolher sempre o mesmo canto do trecho
        é um rumo fixo, e foi assim que uma versão anterior subiu quatorze casas
        pela coluna de mato até esbarrar no bug catcher.
        """
        pair = getattr(self, "training_pair", None)
        if pair is None:
            pair = self._pick_training_pair(map_id)
            if pair is None:
                return None
            self.training_pair = pair
        position = tuple(self.emulator.memory.get_player_pos())
        home, away = pair
        target = away if position == home else home
        return self._follow_route(f"treino-{map_id}", [target])

    def _pick_training_pair(self, map_id):
        """Duas células de mato vizinhas, perto da porta e longe de treinador."""
        memory = self._map_memory()
        grass = memory.grass_cells(map_id)
        if not grass:
            return None
        trainers = memory.trainer_positions(map_id)
        position = tuple(self.emulator.memory.get_player_pos())

        def distancia_treinador(cell):
            if not trainers:
                return 999
            return min(abs(cell[0] - t[0]) + abs(cell[1] - t[1]) for t in trainers)

        candidates = [
            cell for cell in grass
            if distancia_treinador(cell) >= TRAINING_TRAINER_CLEARANCE
        ]
        if not candidates:
            return None
        # Perto de onde o bot está, para a caminhada até lá não ser a viagem.
        candidates.sort(
            key=lambda c: abs(c[0] - position[0]) + abs(c[1] - position[1])
        )
        for cell in candidates:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbour = (cell[0] + dx, cell[1] + dy)
                if neighbour in grass and distancia_treinador(neighbour) >= (
                    TRAINING_TRAINER_CLEARANCE
                ):
                    return (cell, neighbour)
        return None

    def _party_max_level(self):
        """Highest level in the party, read from the cartridge."""
        count = min(int(self.emulator.memory.get_party_count()), 6)
        read = self.emulator.memory.read_byte
        # Offset 33 of the party struct is the live level; offset 3 only stays
        # in sync for boxed Pokémon.
        return max(
            (int(read(0xD16B + index * 44 + 33)) for index in range(count)),
            default=0,
        )

    def _run_pewter_city_nav(self):
        """Walk to Pewter's Gym, rebuilding the route after a whiteout."""
        map_id = int(self.emulator.memory.get_map_id())
        if map_id == 54:
            return None
        # O desvio para o Centro de Pewter saiu com a cura automática. Dentro
        # do 58 o registro do Centro é feito antes do executor, na regra do
        # topo de `step`.
        if map_id == 2:
            return self._follow_route(
                "pewter-to-gym",
                [
                    (18, 35), (18, 22), (19, 22), (19, 13),
                    (10, 13), (10, 18), (16, 18), (16, 17),
                ],
            )

        # Until a Pokémon Center has been registered, a poison faint or
        # whiteout returns this early journey to Pallet. Reconstruct the path
        # instead of leaving the bot pressing A in an unrelated map.
        recovery_routes = {
            0: [(9, 6), (9, 2), (10, 2), (10, -1)],
            12: [
                (10, 35), (10, 30), (8, 30), (8, 24), (12, 24),
                (12, 20), (9, 20), (9, 14), (14, 14), (14, 2),
                (10, 2), (10, -1),
            ],
            1: [
                (20, 35), (20, 28), (19, 28), (19, 20), (16, 20),
                (16, 16), (18, 16), (18, 6), (17, 4), (17, -1),
            ],
            50: [(4, 7), (4, 1), (5, 1), (5, 0)],
            51: [
                (17, 47), (17, 43), (26, 43), (26, 34), (25, 34),
                (25, 32), (27, 32), (27, 20), (25, 20), (25, 12),
                (25, 9), (17, 9), (17, 16), (13, 16), (13, 3),
                (7, 3), (7, 22), (1, 22), (1, 19), (1, 18),
                (1, 16), (1, 5), (1, -1),
            ],
            47: [(4, 7), (4, 1), (5, 1), (5, 0)],
        }
        if map_id == 13:
            _, y = self.emulator.memory.get_player_pos()
            recovery_routes[13] = (
                [
                    (7, 71), (7, 57), (4, 57), (4, 52), (10, 52),
                    (10, 44), (3, 44), (3, 43),
                ]
                if y > 20
                else [(3, 11), (3, 8), (8, 8), (8, -1)]
            )
        route = recovery_routes.get(map_id)
        if route:
            return self._follow_route(f"pewter-recovery-{map_id}", route)
        return self._leave_unknown_map()

    def _run_brock_quest(self):
        """Approach Brock; battle inputs are owned by the battle controller."""
        if int(self.emulator.memory.read_byte(0xD356)) & 0x01:
            return None
        map_id = int(self.emulator.memory.get_map_id())
        if map_id != 54:
            return self._run_pewter_city_nav()
        if map_id == 54:
            position = self.emulator.memory.get_player_pos()
            if position != (4, 2):
                # A porta do ginásio são **dois** tiles, (4,13) e (5,13), e os
                # dois voltam para a cidade. A rota antiga começava em (4,13):
                # quem entrasse pelo (5,13) andava `L` para o outro tile de
                # warp e saía. Medido na corrida do operador em 2026-08-17,
                # com o painel aberto: JARON e KARON em porta giratória,
                # (5,13) → (4,13) → cidade (16,17) → de volta, 78 transições
                # de mapa em 400 eventos. A regra deste projeto já dizia isto:
                # porta nunca é alvo de rota, exceto a última.
                #
                # E o desvio pelo x=1 era inútil: a coluna x=4 é um corredor
                # reto de (4,12) até (4,2) — 11 passos, medido no estático.
                return self._follow_route(
                    "brock-approach",
                    [(4, 12), (4, 8), (4, 4), (4, 2)],
                )
            if int(self.emulator.memory.read_byte(0xD52A)) != 8:
                self.last_action_was_move = True
                return WindowEvent.PRESS_ARROW_UP
            return WindowEvent.PRESS_BUTTON_A
        return WindowEvent.PRESS_BUTTON_A

    def _run_mt_moon_nav(self):
        """Cross Route 3 and Mt. Moon, then enter Cerulean City.

        The coordinates are the collision-safe Pokémon Red/Blue route from
        the local PokeBot walkthrough. Trainer and fossil interactions are
        deliberately reached as physical obstacles; `_follow_route` advances
        their dialogue when movement is blocked, while the battle controller
        owns every actual fight.
        """
        map_id = int(self.emulator.memory.get_map_id())
        if map_id in (3, 65):
            return None

        # Leave Brock's room after the badge dialogue finishes.
        if map_id == 54:
            return self._follow_route(
                "mt-moon-leave-gym",
                [(4, 2), (4, 4), (1, 4), (1, 8), (4, 8), (4, 14)],
            )

        # A loss before registering the Route 4 Center can still return the
        # run to Pallet. Rebuild the complete early route without regressing
        # the sticky quest graph.
        recovery_routes = {
            0: [(9, 6), (9, 2), (10, 2), (10, -1)],
            12: [
                (10, 35), (10, 30), (8, 30), (8, 24), (12, 24),
                (12, 20), (9, 20), (9, 14), (14, 14), (14, 2),
                (10, 2), (10, -1),
            ],
            50: [(4, 7), (4, 1), (5, 1), (5, 0)],
            51: [
                (17, 47), (17, 43), (26, 43), (26, 34), (25, 34),
                (25, 32), (27, 32), (27, 20), (25, 20), (25, 12),
                (25, 9), (17, 9), (17, 16), (13, 16), (13, 3),
                (7, 3), (7, 22), (1, 22), (1, 19), (1, 18),
                (1, 16), (1, 5), (1, -1),
            ],
            47: [(4, 7), (4, 1), (5, 1), (5, 0)],
        }
        if map_id == 1:
            _, y = self.emulator.memory.get_player_pos()
            recovery_routes[1] = (
                [
                    (20, 35), (20, 28), (19, 28), (19, 20),
                    (16, 20), (16, 16), (18, 16), (18, 6),
                    (17, 4), (17, -1),
                ]
                if y > 25
                else [
                    (29, 20), (19, 20), (16, 20), (16, 16),
                    (18, 16), (18, 6), (17, 4), (17, -1),
                ]
            )
        if map_id == 13:
            _, y = self.emulator.memory.get_player_pos()
            recovery_routes[13] = (
                [
                    (7, 71), (7, 57), (4, 57), (4, 52), (10, 52),
                    (10, 44), (3, 44), (3, 43),
                ]
                if y > 20
                else [(3, 11), (3, 8), (8, 8), (8, -1)]
            )
        route = recovery_routes.get(map_id)
        if route:
            return self._follow_route(f"mt-moon-recovery-{map_id}", route)

        if map_id == 2:
            x, y = self.emulator.memory.get_player_pos()
            if not hasattr(self, "mt_moon_pewter_origin"):
                if y >= 22:
                    self.mt_moon_pewter_origin = "south"
                    south_start = (18, y) if x == 18 and 22 <= y <= 35 else (18, 35)
                    self.mt_moon_pewter_route = [
                        south_start, (18, 22), (19, 22), (19, 13),
                        (21, 13), (21, 18), (23, 18), (40, 18),
                    ]
                elif x >= 21:
                    self.mt_moon_pewter_origin = "east"
                    self.mt_moon_pewter_route = [
                        (x, y), (21, 13), (21, 18), (23, 18), (40, 18)
                    ]
                else:
                    self.mt_moon_pewter_origin = "gym"
                    self.mt_moon_pewter_route = [
                        (16, 18), (10, 18), (10, 13), (21, 13),
                        (21, 18), (23, 18), (40, 18),
                    ]

            return self._follow_route(
                f"mt-moon-2-{self.mt_moon_pewter_origin}",
                self.mt_moon_pewter_route,
            )

        routes = {
            14: [
                (0, 10), (8, 10), (8, 8), (11, 8), (11, 6),
                (11, 4), (12, 4), (13, 4), (13, 5), (18, 5),
                (18, 6), (22, 6), (22, 5), (23, 5), (24, 5),
                (27, 5), (27, 9), (37, 8), (37, 5), (49, 5),
                (49, 10), (57, 10), (57, 8), (59, 8), (59, -1),
            ],
            # Medida a partir da travessia real que chegou a Cerulean
            # (arquivo 20260805T101255.414852Z-AARON, quest_advanced em
            # mt_moon_nav). A rota antiga passava por (35,31) — item ball
            # sólida em Gen I — e o bot quicava numa caixa de 4 tiles até
            # morrer de atrito. Esta sobe ao norte, corta oeste por cima,
            # desce a coluna oeste (x=2) e entra na escada NW (5,5).
            59: [
                (14, 35), (14, 26), (21, 22), (24, 27), (25, 32),
                (35, 7), (16, 15), (2, 16), (2, 5), (5, 5),
            ],
            61: [
                (21, 17), (26, 31), (10, 26), (13, 8), (3, 4),
                (7, 4), (11, 4), (16, 4), (5, 7),
            ],
        }
        if map_id in routes:
            # A travessia de Mt. Moon é o trecho que mais custou medição à mão
            # neste projeto, e a Rota 3 mostrou o limite disso: em 2026-08-17 o
            # LARON ficou 56 minutos entre Pewter e a Rota 3 com
            # `route_id=mt-moon-14`, `target=(59,-1)`, `path_to_target: None` e
            # o orçamento do waypoint em 283 de 300 — a rota escrita não casava
            # com a geometria de onde ele estava. Do mesmo tile, o grafo
            # respondia 75 passos até a caverna e 302 até Cerulean.
            #
            # A rota medida continua ganhando enquanto alcança; o grafo é a rede.
            return self._route_or_graph(
                f"mt-moon-{map_id}", routes[map_id], CERULEAN_ARRIVAL
            )

        # Map 68 is the Route 4 Center and is handled before every executor,
        # like every other one. It used to have its own copy of the nurse dance
        # here — and that copy was the whole reason Mt. Moon never produced a
        # checkpoint: it healed the party but never set
        # `last_center_healed_map_id`, which is what the checkpoint writer
        # waits for. Its `mt_moon_center_healed` flag was written and never
        # read by anything.

        if map_id == 60:
            x, y = self.emulator.memory.get_player_pos()
            route = (
                [(5, 5), (5, 17), (21, 17)]
                if x < 20 or y > 4
                else [(23, 3), (27, 3)]
            )
            return self._follow_route("mt-moon-60", route)

        if map_id == 15:
            x, _ = self.emulator.memory.get_player_pos()
            # "Já curei aqui" era mais um trinco de processo: reiniciado, ele
            # voltava ao Centro da Rota 4 com o time inteiro e ficava indo e
            # vindo entre (12,6) e (13,6). Quem responde é a party na RAM.
            # O desvio para o Centro da Rota 4 saiu junto com a cura
            # automática. Quem estiver a oeste segue direto para a caverna.
            if x < 20:
                # (11,6) é âncora de aproximação para quem chega **do oeste** —
                # do Centro ou da Rota 3. Para quem já está a leste dela, ela
                # fica atrás, e o ciclo que ela cria é fechado: sai da caverna
                # em (18,5), o índice é recalculado para o ponto "mais
                # próximo", volta a andar oeste até (11,6), leste até (18,6),
                # entra na caverna em (18,5), sai, recomeça. Medido: 400
                # travessias em 300 segundos.
                #
                # Mesmo padrão da porta do Centro de Viridian, já registrado no
                # handoff: âncora de aproximação atrás do bot é âncora gasta.
                aproximacao = [] if x >= MT_MOON_APPROACH_X else [(11, 6)]
                return self._follow_route(
                    "mt-moon-enter-cave", aproximacao + [(18, 6), (18, 5)]
                )
            return self._follow_route(
                "mt-moon-to-cerulean",
                [
                    (24, 6), (24, 8), (35, 8), (35, 10), (61, 10),
                    (61, 8), (79, 8), (79, 10), (90, 10),
                ],
            )

        return self._leave_unknown_map()

    def _manual_mode_active(self):
        """True quando o operador está dirigindo pelo modo guia."""
        try:
            with open(Path("tasks/runtime_controls.json"), "r", encoding="utf-8") as f:
                controls = json.load(f)
            name = getattr(self, "player_name", "AARON").upper()
            return bool(
                controls.get("agents", {}).get(name, {}).get("manual_mode", False)
            )
        except Exception:
            return False

    def _trail_override_step(self):
        """Follow the operator's measured trail for this quest+map, if any.

        A trilha publicada é o caminho que o operador atravessou no cartucho
        real — ela sobrepõe QUALQUER ramo do executor, porque o executor pode
        errar (beco não mapeado, waypoint inalcançável, ramo errado) e a
        trilha não. O operador pediu explicitamente: se ele fez uma trilha,
        ela manda. Para o Cut, a trilha também vai registrar quando e onde
        cortar.
        """
        # Com o modo guia ativo, o operador é o piloto: o trail (e qualquer
        # executor) fica em espera. O bot não decide nada enquanto o
        # operador estiver dirigindo.
        if self._manual_mode_active():
            return None
        if not self._trail_may_drive(getattr(self, "current_task_name", None)):
            return None
        quest_id = getattr(self, "current_task_name", None)
        if not quest_id:
            return None
        store = getattr(self, "trail_store", None)
        if store is None:
            return None
        try:
            map_id = int(self.emulator.memory.get_map_id())
            x, y = self.emulator.memory.get_player_pos()
        except Exception:
            return None
        legs = store.load(quest_id)
        if not legs:
            return None
        waypoints = waypoints_from(legs, map_id, x, y)
        if not waypoints:
            return None
        # O trail de um mapa termina um tile antes do warp de saída — o
        # operador guiou até a porta, não a atravessou. Warps são coordenadas
        # conhecidas do cartucho (warps.json): se o trail acabou e há um warp
        # de saída neste mapa, ele vira o próximo destino. O _warp_steps só
        # bloqueia warp que não é o goal; com o warp no fim da lista, pisar
        # nele é permitido e o bot atravessa a porta (medido 2026-08-13:
        # trail do mapa 16 terminava em (17,28) e o warp do 71 está em
        # (17,27) — o bot ficava parado a um passo da porta).
        remaining = waypoints
        if len(remaining) <= 2:
            reader = self._tile_reader()
            if reader is not None:
                try:
                    warps = reader.warp_tiles()
                except Exception:
                    warps = set()
                if warps:
                    # Só warps que realmente saem do mapa (para outro mapa) e
                    # não são a entrada recém-usada.
                    entry = getattr(self, "route_entry_block", None)
                    entry_tile = (int(entry[1]), int(entry[2])) if entry else None
                    recent = {
                        (int(a), int(b))
                        for _, a, b in getattr(self, "route_recent_tiles", [])
                    }
                    candidates = [
                        warp for warp in warps
                        if warp != entry_tile and warp not in recent
                        and warp not in remaining
                    ]
                    if candidates:
                        nearest = min(
                            candidates,
                            key=lambda w: abs(w[0] - x) + abs(w[1] - y),
                        )
                        if abs(nearest[0] - x) + abs(nearest[1] - y) <= 6:
                            remaining = remaining + [nearest]
        # **Perna de um ponto é carimbo de passagem, não caminho.** O trail
        # minerado de log grava uma coordenada por evento, então "passei por
        # este mapa" vira uma perna de um ponto só — e dirigir por ela põe o
        # bot em cima do ponto e o deixa lá, porque não há próximo waypoint
        # para querer. Medido em 2026-08-16, com três bots novos: os três
        # oscilando entre (4,1) e (4,2) no laboratório do Oak, 4.500 passos no
        # mesmo tile, `route_id=trail-override-parcel_event-40`,
        # `waypoints=[[4,1]]`. O warp de saída acima já estende a perna curta
        # quando existe um; se nem assim há dois pontos, o trail não tem
        # caminho a oferecer e quem manda é o executor, que tem rota medida.
        if len(remaining) < 2:
            return None
        # Usa a rota do trail com um id próprio; o _follow_route re-consulta
        # o trail interno (FOLLOW_TRAILS) e segue os waypoints medidos.
        return self._follow_route(f"trail-override-{quest_id}-{map_id}", remaining)

    def _center_first_action(self):
        """A Center on this map outranks whatever the executor wanted to do.

        The prize is not the HP, it is the **checkpoint**. Entering a Center is
        the only thing in this project that writes a resume point, so walking
        past one is throwing away the only defence a whiteout has: with a
        checkpoint a death costs the stretch, without one it costs the run back
        to Pallet.

        A viagem até um Centro por causa de HP foi cancelada pelo operador:
        ficar até morrer é aceitável, e a cura automática travava o
        personagem. Sobrou a metade que importa — um Centro **neste mapa**
        vira ponto de retomada, e o executor espera.

        It also closes a hole every executor shared. AARON reached Pewter,
        walked into its Center at 53% with a fainted Caterpie, and stopped:
        `_run_pewter_city_nav` only enters its Center branch when the 20% gate
        says yes, so nothing matched and it fell through to the unknown-map
        fallback.
        """
        if getattr(self, "emulator", None) is None:
            return None
        map_id = int(self.emulator.memory.get_map_id())
        if map_id in POKEMON_CENTER_MAP_IDS:
            # Standing inside one hands over unconditionally, healed or not:
            # this controller owns **both** halves, healing what is missing and
            # walking back out. Gating it on "is anything missing" left AARON
            # healed on Pewter's doormat with nothing to press — the executor
            # has no branch for a whole party in a Center either, so the step
            # fell through to the unknown-map fallback and stopped.
            #
            # Viridian keeps its own names: `viridian_center_healed` is read
            # outside this class as the story milestone for the first Center.
            prefix, healed = (
                ("viridian-center", "viridian_center_healed")
                if map_id == VIRIDIAN_CENTER_MAP_ID
                else (f"center-{map_id}", f"center_{map_id}_healed")
            )
            return self._run_pokemon_center(prefix, healed)
        # HP não desvia mais nada. O que desvia é cidade nova: se este mapa tem
        # porta de Centro e `wLastBlackoutMap` ainda não aponta para cá, o
        # apagão devolveria a corrida a Pallet. Registrar custa a caminhada até
        # a porta; não registrar custa tudo desde a última cidade.
        if (
            map_id in CENTER_DOOR_BY_OUTDOOR_MAP
            and self._blackout_map() != map_id
        ):
            return self._walk_to_door("center-door", POKEMON_CENTER_MAP_IDS)
        return None

    def _waypoints_worth_aiming_at(self, waypoints):
        """Índices que se pode mirar — portas ficam de fora, menos a última.

        A rota de um interior começa no tile da porta, porque é por lá que se
        entra. Mirar esse tile de dentro do prédio é sair dele: AARON chegou ao
        Ginásio de Pewter em 36 segundos e depois entrou e saiu seis vezes,
        porque o waypoint 0 de `brock-approach` é (4,13), a própria porta.

        O último waypoint é exceção, e por isso mesmo: é assim que a rota
        atravessa para o mapa seguinte.
        """
        ultimo = len(waypoints) - 1
        try:
            map_id = int(self.emulator.memory.get_map_id())
            portas = set(self._warp_memory().doors_from(map_id))
        except Exception:
            return list(range(len(waypoints)))
        se_pode_mirar = [
            index for index, ponto in enumerate(waypoints)
            if index == ultimo or tuple(ponto) not in portas
        ]
        return se_pode_mirar or list(range(len(waypoints)))

    def _nearest_reachable_waypoint(self, waypoints, position, candidatos=None):
        """O waypoint mais perto **que dá para chegar**, não o mais perto.

        Distância em linha reta escolhe pontos do outro lado de uma parede.
        AARON e CARON pararam os dois em (8,30) na Floresta mirando (7,22): 8
        casas de distância, marcado como livre, e sem ligação nenhuma com a
        região onde eles estavam. Dali eles alcançavam 560 tiles, entre eles o
        waypoint (13,16) — três posições atrás na rota e perfeitamente andável.

        Se nenhum waypoint responder — mapa novo, conhecimento ainda vazio —
        vale o mais próximo, que é o que este código sempre fez.
        """
        x, y = position
        por_distancia = sorted(
            candidatos if candidatos is not None else range(len(waypoints)),
            key=lambda i: abs(x - waypoints[i][0]) + abs(y - waypoints[i][1]),
        )
        nearest = por_distancia[0]

        def alcancavel(index):
            alvo = tuple(waypoints[index])
            if alvo == (x, y):
                return True
            # O último waypoint de uma rota fica de propósito uma casa **fora**
            # do mapa: é assim que a rota o atravessa. Nenhuma busca chega lá,
            # e isso não é sinal de nada.
            if min(alvo) < 0:
                return True
            try:
                map_id = int(self.emulator.memory.get_map_id())
                return bool(self._map_memory().find_path(map_id, (x, y), alvo))
            except Exception:
                return True

        # A preferência só entra quando o mais próximo é comprovadamente
        # inalcançável. Fora disso vale a distância, que é o que este código
        # sempre fez e acerta na esmagadora maioria dos passos.
        if alcancavel(nearest):
            return nearest
        for index in por_distancia[1:]:
            if alcancavel(index):
                return index
        return nearest

    def _select_route_index(self, route_id, waypoints, position):
        """Qual waypoint mirar agora, sem nunca andar para trás.

        Ao trocar de rota o índice ia para o waypoint **mais próximo**, e é aí
        que nascia o vaivém: BARON e CARON entravam em Mt. Moon, andavam até o
        meio, saíam para a Rota 4 por qualquer motivo, e ao reentrar o "mais
        próximo" era um ponto perto da boca da caverna — atrás de tudo que já
        tinham andado. Dezoito travessias, nenhum progresso.

        Waypoint já passado é waypoint gasto. É a mesma regra que a âncora de
        aproximação de Mt. Moon e a da porta do Centro de Viridian já seguem,
        aplicada ao índice da rota inteira. Estar fisicamente à frente do
        lembrado ainda vale: o que não vale é retroceder.

        O avanço é por `route_id`, e morre no apagão — o cartucho devolveu o
        treinador a um Centro, então mirar o meio da caverna a partir da porta
        seria planejar por cima de terreno que esta tentativa não andou.
        """
        x, y = position
        limite = len(waypoints) - 1
        progress = getattr(self, "route_progress", None)
        if progress is None:
            progress = self.route_progress = {}

        # O avanço lembrado impede voltar ao waypoint da entrada, e essa é a
        # metade certa. A outra metade faltava: quem **sai** da rota fica preso
        # mirando um ponto que não alcança, porque o índice nunca recua para o
        # trecho onde o bot realmente está. AARON e CARON pararam os dois em
        # (8,30) na Floresta, índice 16, mais de 1.500 passos sem encurtar a
        # distância. Distância que não cai por tanto tempo é rota perdida, não
        # rota difícil: solta o avanço e deixa reentrar pelo ponto mais perto.
        replanejando = getattr(self, "route_no_progress", 0) > ROUTE_REPLAN_STEPS
        if replanejando:
            progress.pop(route_id, None)
            self.route_no_progress = 0
            self.route_id = None

        if getattr(self, "route_id", None) != route_id:
            self.route_id = route_id
            # A busca por alcance custa uma varredura em largura por waypoint, e
            # troca de rota acontece o tempo todo: pagá-la sempre derrubou a
            # corrida de 65 para 2,5 passos por segundo, o que na tela parece
            # travamento. Ela só serve quando a distância já provou não bastar,
            # e é exatamente aí que ela entra.
            candidatos = self._waypoints_worth_aiming_at(waypoints)
            if replanejando:
                nearest = self._nearest_reachable_waypoint(
                    waypoints, (x, y), candidatos
                )
            else:
                nearest = min(
                    candidatos,
                    key=lambda i: abs(x - waypoints[i][0]) + abs(y - waypoints[i][1]),
                )
            self.route_index = max(nearest, min(progress.get(route_id, 0), limite))

        index = getattr(self, "route_index", 0)
        while index < limite and (x, y) == tuple(waypoints[index]):
            index += 1
        # A mesma rota pode receber uma lista mais curta que da última vez — o
        # executor da Rota 2 troca os waypoints depois que o Centro é
        # registrado. O índice velho estourava a lista, o IndexError era
        # engolido pelo chamador e virava NOOP: um bot congelado no meio da
        # cidade sem mensagem nenhuma.
        index = min(index, limite)
        if index > progress.get(route_id, -1):
            progress[route_id] = index
        return index

    def _door_is_reachable(self, map_id, door):
        """A porta está no mesmo componente andável que o bot? (BFS no estático.)

        `_walk_to_door` planeja com o `find_path` do MapMemory, que atravessa
        tudo o que o bot já viu — e em Route 4 isso inclui os dois lados do
        penhasco quando ele foi atravessado por outra rota. O caminho existe
        no conhecimento, mas o bot não está nele: andar até a porta vira um
        retorno de 52 tiles. Só desviar para o Centro quando a porta está no
        componente real do bot (medido 2026-08-12: AARON em (63,10), Centro
        da Route 4 em (11,5), 3000 passos parado).
        """
        try:
            memory = self._map_memory()
            if memory is None:
                return True
            x, y = self.emulator.memory.get_player_pos()
            return memory.find_path(map_id, (x, y), door) is not None
        except Exception:
            return True

    def _can_reach(self, map_id, tile):
        """Este tile está no mesmo componente andável que o bot, agora?

        Cerulean tem dois componentes grandes separados pelo rio, e a borda
        sul (a saída para a Route 5) só existe no de leste. Perguntar ao
        estático é mais barato e mais honesto que uma caixa de coordenadas:
        a caixa `26 <= x <= 39 and 7 <= y <= 17` do executor antigo dizia
        "lado leste" e pegava junto o ginásio (30,19), que é do lado oeste.
        """
        try:
            memory = self._map_memory()
            if memory is None:
                return False
            position = self.emulator.memory.get_player_pos()
            return memory.find_path(map_id, tuple(position), tuple(tile)) is not None
        except Exception:
            return False

    def _door_to(self, destinations):
        """Nearest door on this map leading into one of these maps, or None.

        Every route to a Center or a Mart in this project was measured by hand,
        for one city, from a handful of starting maps — `buy_pokeballs` only
        knows the way back to Viridian's Mart, so a trainer that spends its last
        Poké Ball north of Route 2 never buys another one.

        The warp table answers this. It was already being read for *where* the
        doors are; the fourth byte of each entry says where each one goes.
        """
        reader = self._tile_reader()
        if reader is None:
            return None
        x, y = self.emulator.memory.get_player_pos()
        doors = [
            tile for tile, destination in reader.warp_destinations().items()
            if destination in destinations
        ]
        if not doors:
            return None
        return min(doors, key=lambda tile: abs(tile[0] - x) + abs(tile[1] - y))

    def _walk_to_door(self, route_prefix, destinations):
        """Head for that door, or None when this map has none of them.

        Porta inalcançável do componente atual não é desvio que valha: AARON
        parado em (63,10) na Route 4 recebia ordens de andar 52 tiles para
        oeste até o Centro (11,5) — do outro lado do penhasco — e ficava 3000
        passos parado, com o executor do vermilion nunca chegando a rodar
        (medido 2026-08-12).
        """
        door = self._door_to(destinations)
        if door is None:
            return None
        map_id = int(self.emulator.memory.get_map_id())
        if not self._door_is_reachable(map_id, door):
            return None
        # The route id carries the door so a different one, on a different map,
        # cannot inherit a stale waypoint index.
        return self._follow_route(f"{route_prefix}-{door[0]}-{door[1]}", [door])

    def _run_nearest_center(self, route_prefix="nearest-center"):
        """Heal at whatever Center this city has, with no route measured by hand.

        Works anywhere because both halves are general: the door comes from the
        map's own warp table, and every Pokémon Center in Gen I is the same
        building inside — nurse at (3,3), doormat at (3,7).
        """
        map_id = int(self.emulator.memory.get_map_id())
        if map_id in POKEMON_CENTER_MAP_IDS:
            return self._run_pokemon_center(route_prefix, f"{route_prefix}_healed")
        return self._walk_to_door(route_prefix, POKEMON_CENTER_MAP_IDS)

    def _run_nearest_mart(self, route_prefix="nearest-mart"):
        """Restock at whatever Mart this city has. Same two halves as above."""
        map_id = int(self.emulator.memory.get_map_id())
        if map_id in POKE_MART_MAP_IDS:
            return self._run_shop_counter()
        return self._walk_to_door(route_prefix, POKE_MART_MAP_IDS)

    def _run_shop_counter(self):
        """Reach the clerk and buy, from inside any Mart.

        Lifted out of `buy_pokeballs`, where it was written for map 42 and read
        as if the coordinates were Viridian's. They are not: a Gen I Mart is the
        same building in every city, clerk behind the top-left counter.
        """
        if tuple(self.emulator.memory.get_player_pos()) != SHOP_COUNTER_TILE:
            return self._follow_route(
                "shop-counter", [(3, 7), (3, 5), SHOP_COUNTER_TILE]
            )
        if self.emulator.memory.read_byte(0xD52A) != 2:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_LEFT
        return self._buy_first_shop_item()

    def _blackout_map(self):
        """Para onde o cartucho manda o treinador depois de um apagão.

        `wLastBlackoutMap` guarda o **mapa de fora** do último Centro usado — 1
        para Viridian, 15 para a Rota 4. Enquanto ele não avança, todo apagão
        devolve o jogo a Pallet e a corrida vira roguelite.
        """
        try:
            return int(self.emulator.memory.read_byte(LAST_BLACKOUT_MAP_ADDRESS))
        except Exception:
            return None

    def _respawn_is_registered(self, center_map_id):
        """Este Centro já é o ponto de renascimento?

        Medido no cartucho em 2026-08-07: entrar **não** basta. O endereço só
        muda quando a enfermeira termina a cura — entrei no Centro de Viridian
        com o valor em 0 e ele continuou em 0; virou 1 depois de curar.
        """
        outdoor = CENTER_OUTDOOR_MAP.get(int(center_map_id))
        if outdoor is None:
            return True
        return self._blackout_map() == outdoor

    def _run_pokemon_center(self, route_prefix, healed_attribute):
        """Registrar o Centro como ponto de renascimento e sair.

        A cura por HP baixo foi cancelada pelo operador e não volta: nada aqui
        olha para HP. O que traz o treinador até este balcão é outra coisa —
        `wLastBlackoutMap` ainda não aponta para esta cidade, e só a enfermeira
        move esse endereço. A cura é efeito colateral da única interação que
        grava o checkpoint interno do jogo.

        Quem decide se já acabou é o cartucho, não um flag: enquanto o endereço
        não apontar para cá, a conversa continua. Foi assim que a versão
        anterior entrava em ciclo — "já curei" era um flag de processo que
        sumia no reinício.
        """
        position = self.emulator.memory.get_player_pos()
        map_id = int(self.emulator.memory.get_map_id())

        if not self._respawn_is_registered(map_id):
            if tuple(position) != (3, 3):
                return self._follow_route(f"{route_prefix}-nurse", [(3, 7), (3, 3)])
            if int(self.emulator.memory.read_byte(0xD52A)) != 8:
                self.last_action_was_move = True
                return WindowEvent.PRESS_ARROW_UP
            # Falar, confirmar o SIM e atravessar a animação são todos A. O fim
            # da conversa é o endereço de renascimento apontando para cá.
            return WindowEvent.PRESS_BUTTON_A

        setattr(self, healed_attribute, True)
        setattr(
            self,
            f"{healed_attribute.replace('_healed', '')}_checkpoint_confirmed",
            True,
        )
        self.last_center_visited_map_id = int(self.emulator.memory.get_map_id())
        # Leaving used to be a measured D-pad sequence, played once. When any
        # press was eaten — by the nurse's last text box, by a step that landed
        # a tile off — the sequence ran out and the controller returned None
        # forever: a trainer stood on the Center's own doormat, healthy, unable
        # to walk out. Walking to the door and pressing into it repeats until
        # the cartridge actually changes map.
        if tuple(position) not in ((3, 7), (4, 7)):
            return self._follow_route(f"{route_prefix}-exit", [(3, 7)])
        self.last_action_was_move = True
        return WindowEvent.PRESS_ARROW_DOWN

    def _party_health_fraction(self):
        """Combined party HP over combined maximum, 1.0 when whole."""
        party_count = min(int(self.emulator.memory.get_party_count()), 6)
        total_hp = 0
        total_max = 0
        for index in range(party_count):
            struct_start = 0xD16B + index * 44
            total_hp += (
                int(self.emulator.memory.read_byte(struct_start + 1)) << 8
            ) + int(self.emulator.memory.read_byte(struct_start + 2))
            total_max += (
                int(self.emulator.memory.read_byte(struct_start + 34)) << 8
            ) + int(self.emulator.memory.read_byte(struct_start + 35))
        if total_max <= 0:
            return 1.0
        return total_hp / total_max

    def _should_top_up_before(self, map_id):
        """Whether to heal now because the Center is on the way and the next
        stretch has none.

        Twenty per cent is an emergency rule, and emergencies are the wrong
        moment to walk across a city: a team at half health entered the Forest,
        died in the middle of it, whited out back to Viridian and started the
        same walk again. A Center passed on the route is nearly free, so the
        bar to stop there is much higher than the bar to turn around.
        """
        if map_id not in CENTER_ON_THE_WAY:
            return False
        return self._party_health_fraction() < TOP_UP_HP_FRACTION

    def _party_needs_healing(self):
        """True only when the team's combined HP is below one fifth.

        Per-Pokémon rules kept sending the trip back too early: at 29/30 a
        trainer walked the whole city to the Center, healed, took one scratch
        on the way out and turned around. Exhausted PP is handled by battle
        control; it is not a second reason to start a healing trip.
        """
        party_count = min(int(self.emulator.memory.get_party_count()), 6)
        if party_count <= 0:
            return False
        total_hp = 0
        total_max = 0
        for index in range(party_count):
            struct_start = 0xD16B + index * 44
            current_hp = (
                int(self.emulator.memory.read_byte(struct_start + 1)) << 8
            ) + int(self.emulator.memory.read_byte(struct_start + 2))
            max_hp = (
                int(self.emulator.memory.read_byte(struct_start + 34)) << 8
            ) + int(self.emulator.memory.read_byte(struct_start + 35))
            total_hp += current_hp
            total_max += max_hp
        return bool(total_max and total_hp < total_max * HEAL_HP_FRACTION)

    def _run_bill_quest(self):
        """Heal, clear the Cerulean rival/bridge and obtain the S.S. Ticket."""
        if self._bag_item_count(0x3F) > 0:
            return None

        map_id = int(self.emulator.memory.get_map_id())
        if map_id == 64:
            return self._run_pokemon_center(
                "cerulean-center",
                "cerulean_center_healed",
            )

        if map_id == 3:
            # A parada de cura em Cerulean saiu; o Centro só entra na rota se
            # o caminho passar por cima dele.
            return self._follow_route(
                "cerulean-to-rival",
                [
                    # The buildings occupy every direct north line near the
                    # Center. The cartridge's open street is at x=8; use it to
                    # reach y=12, then cross back to Nugget Bridge.
                    (19, 18), (8, 18), (8, 12), (20, 12),
                    (20, 8), (20, 6), (20, -1),
                ],
            )

        if map_id == 35:
            # Nugget Bridge trainers occupy alternating x=10/x=11 tiles.
            # Walking the centre line triggers every required fight and the
            # Rocket recruiter before bending east into Route 25.
            return self._follow_route(
                "route-24-bill",
                [
                    (10, 35), (10, 32), (10, 29),
                    # Two trainers remain on x=10 after their battles. The
                    # bridge's x=9 side is fenced, so bypass them on x=11.
                    (11, 29), (11, 27), (10, 27), (10, 23),
                    (11, 23), (11, 21), (10, 21),
                    (10, 20), (10, 17), (10, 14),
                    # The east turn is above the corner fence, not through it.
                    (10, 10), (11, 10), (11, 8), (15, 8), (19, 8), (20, 8),
                ],
            )

        if map_id == 36:
            # Route 25 is a hedge corridor. These first waypoints are kept
            # explicit so trainer collisions are handled as dialogue/battles;
            # the route is validated incrementally against the cartridge.
            return self._follow_route(
                "route-25-bill",
                [
                    # The upper branch leads to the optional TM19 enclosure
                    # and two one-way traps. The story-safe path zigzags below
                    # the ledges and approaches the Hiker at (13,7) from his
                    # right, making him walk out of the corridor before battle.
                    (0, 8), (9, 8), (9, 7), (11, 7),
                    (11, 9), (15, 9), (15, 7), (15, 4),
                    # Approach the Lass at (18,8) from the open east side,
                    # then continue through the corridor she vacates.
                    (17, 4), (17, 7), (20, 7), (20, 8),
                    (22, 8), (22, 6), (23, 6), (23, 5), (24, 5),
                    # The Jr. Trainer opens the long lower corridor. Approach
                    # the final Lass from below so she does not block it.
                    (24, 6), (36, 6), (36, 5), (37, 5),
                    (45, 5), (45, 3),
                ],
            )

        if map_id == 88:
            bill_flags = int(self.emulator.memory.read_byte(0xD7F2))
            said_use_separator = bool(bill_flags & (1 << 6))
            used_separator = bool(bill_flags & (1 << 3))
            met_human_bill = bool(
                int(self.emulator.memory.read_byte(0xD7F1)) & 0x01
            )

            if not said_use_separator:
                # Bill begins as the Pokémon at (6,5). Walking into the
                # occupied tile and advancing the YES prompt starts his walk
                # into the separation machine.
                return self._follow_route(
                    "bill-lab-introduction",
                    [(3, 7), (3, 6), (5, 6), (5, 5), (6, 5)],
                )

            if not used_separator:
                # O teclado do PC é o tile de fundo (1,4), parede por design:
                # a rota termina em (1,5) e a interação é virada + A — o menu
                # abre e A de novo seleciona "BILL's PC" (a primeira opção),
                # ativando o separador (RAM D7F2.3). O bot ficava encurralado
                # em (0,4) mirando o teclado inalcançável.
                x, y = self.emulator.memory.get_player_pos()
                if (x, y) == (1, 5):
                    if getattr(self, "bill_pc_active", False):
                        return WindowEvent.PRESS_BUTTON_A
                    self.bill_pc_active = True
                    self.route_last_issue = "bill_pc"
                    return ROUTE_EVENTS["U"]
                self.bill_pc_active = False
                return self._follow_route(
                    "bill-lab-separator",
                    [(6, 5), (1, 5)],
                )

            if not met_human_bill:
                # Bill's exit from the machine is an autonomous cutscene.
                # A advances any text while ordinary ticks advance movement.
                self.bill_pc_active = False
                return WindowEvent.PRESS_BUTTON_A

            # Human Bill waits at (4,4). Talk from below to receive the ticket;
            # item 0x3f and D7F2.4 independently verify completion.
            return self._follow_route(
                "bill-lab-ticket",
                [(1, 5), (4, 5), (4, 4)],
            )

        # A whiteout can return to Cerulean Center, and a bot can wander into
        # any house on the way. An unknown map is not a cutscene to press
        # through: walk back out of it and let the route resume outside.
        return self._leave_unknown_map()

    def _run_vermilion_gym_quest(self):
        """Cerulean -> Route 5 -> Underground -> Route 6 -> Vermilion.

        **Vermilion fica ao SUL de Cerulean.** A Rota 9 (mapa 20) é o caminho
        para o Túnel da Rocha, a leste, e o executor antigo mandava o bot
        para lá: a margem leste descia até (39,16), cruzava para o mapa 20 e
        caía num beco de 9 tiles cuja única saída é voltar para Cerulean —
        que mandava para leste de novo. Medido no cartucho (14/08 a 16/08,
        dois dias de corrida): 1.976 transições m3<->m20, o bot parado em
        (20, 0,9) e (3, 39,17), zero progresso.

        A saída sul é fato do estático, não palpite: Cerulean (mapa 3) tem
        dois componentes andáveis grandes, separados pelo rio. O lado LESTE
        (onde o buraco da casa 62 devolve o jogador, em (27,9)) desce pela
        coluna x=36/37 — a única passagem pela faixa de penhascos em y=28 —
        e daí pela coluna x=25..28, que atravessa a faixa de y=33 sem pulo,
        até a borda sul (26,35). Um passo a mais entra na Route 5 em (16,0):
        a conexão soma 10 à coordenada x (Route 5 tem 20 tiles de largura,
        Cerulean 40). Do lado OESTE nenhuma célula alcança o sul — quem
        renasce no Centro tem de cruzar pela casa (27,11), como já fazia.
        """
        map_id = int(self.emulator.memory.get_map_id())
        x, y = self.emulator.memory.get_player_pos()
        if map_id == 65:
            # Na porta do ginásio (4,13): descer atravessa o warp para fora.
            # O waypoint final é a porta; pisar nela (D) é o passo de saída
            # (medido 2026-08-13: o bot parava na porta com D lendo terrain).
            if (x, y) == (4, 13):
                return ROUTE_EVENTS["D"]
            return self._follow_route("misty-exit", [(4, 12), (4, 13)])
        if map_id == 64:
            # Centro de Cerulean: é aqui que um apagão devolve o treinador.
            # Sem esta perna o executor devolvia None dentro do Centro e o
            # bot ficava à mercê do genérico. O renascimento já está gravado
            # nesta cidade, então isto só anda até a porta e sai.
            return self._run_pokemon_center("cerulean-center", "cerulean_center_healed")
        if map_id == 62:
            return self._follow_route(
                "cerulean-house-hole",
                [(3, 0)],
            )
        if map_id == 3:
            if (x, y) == (27, 12):
                # Na porta da casa (27,11): um passo para cima entra. O
                # retorno é o WindowEvent, não a string — o hybrid converte
                # eventos, e "U" vira NOOP (medido 2026-08-12: o bot ficava
                # parado na porta).
                return ROUTE_EVENTS["U"]
            if self._can_reach(3, CERULEAN_SOUTH_EXIT):
                # Lado leste/sul: a borda sul está no mesmo componente, então
                # o caminho é andável inteiro — nenhum pulo de penhasco, nada
                # de adivinhar. Waypoints conferidos um a um no estático a
                # partir de (39,17), (38,17), (27,9), (39,16) e (33,12).
                return self._follow_route(
                    "cerulean-south-to-route5",
                    [
                        (36, 27), (36, 29), (28, 30), (26, 32),
                        CERULEAN_SOUTH_EXIT, (26, 36),
                    ],
                )
            # Lado oeste do rio (Centro, ginásio, Mart): a borda sul não é
            # alcançável daqui em nenhuma célula — só pela casa acima do
            # ginásio, cujo buraco na parede devolve o jogador em (27,9), já
            # do lado leste. É o mesmo caminho validado em 2026-08-12.
            return self._follow_route(
                "cerulean-to-house",
                [(20, 13), (27, 13), (27, 12)],
            )
        if map_id == 15:
            # Rota 4 é o caminho de VOLTA ao Mt. Moon (oeste). Se o bot
            # acabou aqui por engano, retorna a Cerulean pela borda leste.
            # O penhasco divide a rota em componentes: do lado leste
            # (x>=63) o caminho é direto pela borda (89,10) — o find_path
            # guia os desvios. Waypoints do lado oeste (61,10)/(79,8) são
            # inalcançáveis daqui e só queimavam o orçamento (medido
            # 2026-08-12: AARON em (63,10) mirando (11,5) por 3000 passos).
            return self._follow_route(
                "route4-back-to-cerulean",
                [(89, 10), (90, 10)],
            )
        if map_id == 20:
            # Rota 9 é o caminho do Túnel da Rocha, não o de Vermilion. O
            # warp de Cerulean desemboca num beco de 9 tiles (x=0..4,
            # y=8..9) cuja única saída é voltar para oeste. Ninguém mais é
            # mandado para cá; se um apagão ou uma batalha empurrar o bot
            # para dentro do beco, a saída é a borda oeste — e o mapa 3
            # agora manda para o sul, então não há mais o ciclo m3<->m20.
            return self._follow_route(
                "route9-back-to-cerulean",
                [(0, 8), (0, 9)],
            )

        # --- Cerulean -> Vermilion, pernas conferidas no estático ---
        # Cada waypoint abaixo foi verificado com `MapMemory.find_path` a
        # partir do tile em que a perna anterior desemboca: nenhuma das
        # cadeias tem hop `NONE`, e as que dependiam de pulo de penhasco
        # foram trocadas por colunas andáveis de ponta a ponta.

        if map_id == 16:
            # Route 5: a entrada vinda de Cerulean cai em (16,0) e a coluna
            # LESTE (x=17) desce limpa até o prédio do Underground (17,27).
            # A coluna 13 do executor antigo fica na faixa do meio, que os
            # penhascos isolam da porta — de (9,0) a (17,27) o find_path
            # devolve NONE.
            x, y = self.emulator.memory.get_player_pos()
            if (x, y) == (17, 27):
                return ROUTE_EVENTS["D"]
            # Waypoints tirados do caminho real do `find_path`, não escolhidos
            # a olho: (17,24) e (17,5) da versão anterior são parede — a
            # coluna andável é a x=16, e a porta se aproxima por baixo,
            # passando por (15,28), porque (16,27) é a parede do prédio.
            return self._follow_route(
                "route5-to-underground",
                [(16, 8), (16, 16), (16, 23), (15, 28), (17, 27)],
            )
        if map_id == 71:
            # Casa/entrada do Underground (17,27). Atravessar até a porta
            # interna (4,4) que warpa para o mapa 119. O operador guiou o
            # trail até (3,4); o warp (4,4) é a coordenada conhecida — o
            # alvo é a porta, não o tile antes dela.
            x, y = self.emulator.memory.get_player_pos()
            if (x, y) == (4, 4):
                return ROUTE_EVENTS["D"]
            return self._follow_route(
                "underground-entrance",
                [(3, 7), (3, 6), (3, 5), (3, 4), (4, 4)],
            )
        if map_id == 119:
            # Underground Path: descer o corredor até o warp de saída
            # (2,41) -> mapa 74 (a outra extremidade). O alvo é o tile do
            # warp lido da ROM; (3,41) era o tile ao lado dele, e parar ao
            # lado de uma porta é o modo de travar deste projeto.
            return self._follow_route(
                "underground-path",
                [(5, 10), (5, 20), (5, 30), (2, 41)],
            )
        if map_id == 74:
            # Saída sul do Underground: atravessar a casinha até a porta
            # (4,7) que devolve à Route 6.
            return self._follow_route(
                "underground-exit",
                [(4, 4), (4, 7)],
            )
        if map_id == 17:
            # Route 6: da saída do Underground (17,13) até a borda sul
            # (9,35), conexão com Vermilion — que é o mapa **5**, não o 1.
            # O waypoint final fica um tile além da borda, como em toda
            # conexão: é o passo que cruza.
            return self._follow_route(
                "route6-to-vermilion",
                [(13, 20), (13, 28), (9, 31), (9, 35), (9, 36)],
            )
        if map_id == VERMILION_CITY_MAP_ID:
            # **Chegou.** O bloco antigo aqui era Viridian inteiro — mapa 1,
            # Centro 41, Mart 42, porta (23,25) — copiado de `buy_pokeballs`
            # e nunca corrigido. Vermilion é o mapa 5, o Centro é o 89 e a
            # porta dele é (11,3) (`knowledge/maps/pokemon_centers.json`,
            # extraído da ROM). Com os ids errados o executor devolvia None
            # na cidade certa e reagia dentro de prédios de outra cidade.
            #
            # O Centro primeiro: é o único gravador de ponto de retomada, e
            # é o que transforma "chegou a Vermilion" em progresso que
            # sobrevive a um apagão.
            x, y = self.emulator.memory.get_player_pos()
            if not self._respawn_is_registered(VERMILION_CENTER_MAP_ID):
                return self._follow_route(
                    "vermilion-to-center",
                    [(19, 4), (11, 4), (11, 3)],
                )
            if (
                self._bag_item_count(HM01_CUT) > 0
                and not self._party_knows_move(CUT_MOVE_ID)
            ):
                # HM na mochila não corta árvore nenhuma: o golpe precisa
                # estar num Pokémon. Ensinar é o passo, e é aqui — em cima do
                # próprio tile, sem andar.
                return self._teach_cut_action()
            if self._bag_item_count(HM01_CUT) == 0:
                # Sem Cut não há ginásio: a árvore da entrada não abre. O
                # ticket está na mochila desde o `bill_quest`, então a doca
                # aceita. A descida é pela coluna x=18 — a 19 tem o marinheiro
                # parado em (19,30), e desviar dele é de graça.
                if (x, y) in SS_ANNE_GANGWAY:
                    return ROUTE_EVENTS["D"]
                # A descida é pela coluna LESTE (x=30): a faixa y=22..25 é
                # parede de x=16 a x=29, então o centro da cidade não desce
                # para o cais. Da linha 26 se anda para oeste até a coluna
                # x=18, que é a única que chega à prancha — a 19 tem o
                # marinheiro parado em (19,30).
                return self._follow_route(
                    "vermilion-to-ss-anne",
                    [(30, 16), (30, 26), (18, 26), (18, 31)],
                )
            return None
        if map_id == VERMILION_CENTER_MAP_ID:
            # Centro de Vermilion: registrar o checkpoint e sair.
            return self._run_pokemon_center("vermilion-center", "vermilion_center_healed")

        # --- S.S. Anne: o navio que entrega o Cut ---------------------------
        if map_id in SS_ANNE_MAP_IDS and self._bag_item_count(HM01_CUT) > 0:
            # **Com o HM na mão, o navio é só saída.** Sem esta guarda a rota
            # do 2º andar continuava mirando a porta da cabine: o bot saía em
            # (0,7), desembarcava em cima do próprio warp (36,4) e reentrava —
            # medido no cartucho em 2026-08-16, duas viagens por segundo entre
            # os mapas 96 e 101, com o Cut já na mochila desde o capitão.
            if map_id == SS_ANNE_CAPTAIN_MAP_ID:
                return self._follow_route("ss-anne-captain-exit", [(1, 7), (0, 7)])
            if map_id == SS_ANNE_UPPER_MAP_ID:
                # De (36,4) não se anda para oeste — (35,4) é parede. A volta
                # é descer a coluna leste e cruzar o corredor y=12.
                return self._follow_route(
                    "ss-anne-2f-exit",
                    [(36, 12), (28, 12), (20, 12), (12, 12), (4, 12),
                     (3, 5), (2, 4)],
                )
            if map_id == SS_ANNE_DECK_MAP_ID:
                return self._follow_route(
                    "ss-anne-1f-exit",
                    [(10, 6), (18, 6), (26, 6), (26, 0)],
                )
            if map_id == SS_ANNE_DOCK_MAP_ID:
                # (14,0) é o warp de volta a Vermilion — o mesmo por onde se
                # chegou. O ticket já foi mostrado; nada barra a saída.
                return self._follow_route("ss-anne-leave", [(14, 0)])

        if map_id == SS_ANNE_DOCK_MAP_ID:
            # A doca. Medido no cartucho em 2026-08-16: o bot desce de (14,0)
            # para (14,1) e ali o passo D **não move** — 1.440 passos no mesmo
            # tile, com `path_to_target: D` e o D voltando como `bumped`. Não
            # é terreno (o estático e o `_tile_truth` liberam) e não é sprite
            # que a leitura ao vivo enxergue: é o marinheiro do cais pedindo
            # o S.S. Ticket, que está na mochila desde o `bill_quest`.
            #
            # Então aqui D e A se alternam: D anda quando o caminho abre e só
            # vira o personagem quando não abre; A fala com quem estiver na
            # frente. Nenhum dos dois estraga o outro, e o cartucho decide —
            # o passo seguinte é o mapa mudar.
            if (x, y) == SS_ANNE_BOARDING_TILE:
                return ROUTE_EVENTS["D"]
            if (x, y) == SS_ANNE_TICKET_TILE:
                if self._menu_is_open():
                    return WindowEvent.PRESS_BUTTON_A
                steps = getattr(self, "ss_anne_ticket_steps", 0) + 1
                self.ss_anne_ticket_steps = steps
                if steps % 2:
                    self.last_action_was_move = True
                    return ROUTE_EVENTS["D"]
                return WindowEvent.PRESS_BUTTON_A
            # O estático parte a doca em quatro componentes — provável
            # limitação do extrator neste tileset —, então o alvo é a coluna
            # da prancha e o planejador otimista faz o resto.
            return self._follow_route(
                "ss-anne-gangway",
                [SS_ANNE_TICKET_TILE],
            )
        if map_id == SS_ANNE_DECK_MAP_ID:
            # Convés/1º andar: descer a coluna da entrada até o corredor
            # (y=6) e ir para oeste até a escada (2,6), que sobe para o 2º.
            return self._follow_route(
                "ss-anne-1f",
                [(26, 6), (15, 6), (7, 6), (2, 6)],
            )
        if map_id == SS_ANNE_UPPER_MAP_ID:
            # 2º andar: contornar pelo corredor de baixo (y=11) até a coluna
            # leste e subir até (37,4), o tile em frente à porta da cabine.
            # (35,4) não é andável — a aproximação é pelo leste.
            if (x, y) == SS_ANNE_CABIN_APPROACH:
                # O rival está em cima da porta. Um passo para a esquerda
                # encosta nele: a máquina `route_sprite_talk` abre o diálogo
                # e o controlador de batalha assume. Depois da vitória ele
                # sai e o mesmo passo atravessa a porta.
                return ROUTE_EVENTS["L"]
            return self._follow_route(
                "ss-anne-2f",
                [(2, 12), (10, 12), (18, 12), (26, 12), (34, 12),
                 (36, 10), (36, 6), SS_ANNE_CABIN_APPROACH],
            )
        if map_id == SS_ANNE_CAPTAIN_MAP_ID:
            return self._run_ss_anne_captain()

        return None

    def _party_move_ids(self, slot):
        """Os quatro slots de golpe de um membro da party, lidos da RAM."""
        base = 0xD16B + int(slot) * 44
        return [int(self.emulator.memory.read_byte(base + 8 + i)) for i in range(4)]

    def _party_knows_move(self, move_id):
        count = min(int(self.emulator.memory.get_party_count()), 6)
        return any(
            int(move_id) in self._party_move_ids(slot) for slot in range(count)
        )

    def _kanto_graph(self):
        """O grafo de Kanto, carregado uma vez por processo.

        São 49 mil células e 2.152 portas: reconstruir por agente ou por passo
        seria caro sem motivo, e o conteúdo é imutável (vem do ROM).
        """
        global _KANTO_GRAPH
        if _KANTO_GRAPH is None:
            from src.kanto_graph import KantoGraph
            _KANTO_GRAPH = KantoGraph(map_memory=self._map_memory())
        return _KANTO_GRAPH

    def _graph_waypoints(self, target):
        """Os waypoints **do mapa atual** para chegar em `target`, pelo grafo.

        O grafo devolve o caminho inteiro, de qualquer ponto para qualquer
        ponto; aqui só a perna deste mapa é entregue, porque é isso que o
        `_follow_route` sabe andar — com colisão ao vivo, sprite, porta e
        orçamento. O grafo entra como **fonte de waypoint**, não como piloto.

        Quando a perna termina numa borda, o último waypoint vira o tile de
        fora (`y = -1` e afins): é esse passo que atravessa, e é a convenção
        que as rotas medidas deste projeto já usam. Quando termina numa porta,
        o tile da porta é o último waypoint — atravessar é pisar nela.
        """
        try:
            graph = self._kanto_graph()
            map_id = int(self.emulator.memory.get_map_id())
            x, y = self.emulator.memory.get_player_pos()
            path = graph.path((map_id, int(x), int(y)), tuple(target))
            if not path:
                return None
            legs = graph.legs(path)
            tiles = [tile for tile in legs[0][1] if tile != (int(x), int(y))]
            if len(legs) > 1:
                # O nó do grafo é `(mapa, x, y)`; a perna guarda só `(x, y)`.
                # Comparar os dois nunca casa, e o `crossing` saía vazio.
                entrance = (legs[1][0],) + tuple(legs[1][1][0])
                crossing = next(
                    (
                        key for key, node
                        in graph.neighbors(path[len(legs[0][1]) - 1],
                                           allow_jumps=True)
                        if node == entrance
                    ),
                    "",
                )
                step = STEP_BY_KEY.get(crossing[-1:]) if crossing else None
                if step and not crossing.startswith("J"):
                    last = legs[0][1][-1]
                    tiles.append((last[0] + step[0], last[1] + step[1]))
            return tiles or None
        except Exception:
            return None

    def _route_or_graph(self, route_id, waypoints, target):
        """A rota medida enquanto ela alcança; o grafo quando ela não alcança.

        A ordem de autoridade não muda: rota desenhada primeiro. O gatilho é o
        próprio mapa dizer que não há caminho até o fim da rota — foi o que o
        relatório do LARON mostrou na Rota 3 em 2026-08-17, parado em (22,8) com
        `route_id=mt-moon-14`, `target=(59,-1)`, `path_to_target: None` e o
        orçamento do waypoint em 283 de 300. A rota escrita à mão não casava com
        a geometria de onde ele estava, e o grafo respondia 75 passos até Mt.
        Moon do mesmo tile.
        """
        map_id = int(self.emulator.memory.get_map_id())
        here = tuple(self.emulator.memory.get_player_pos())
        anchor = tuple(waypoints[-1])
        if self._map_memory().find_path(map_id, here, anchor) is not None:
            return self._follow_route(route_id, waypoints)
        plan = self._graph_waypoints(target)
        if not plan:
            return self._follow_route(route_id, waypoints)
        return self._follow_route(f"grafo-{map_id}", plan)

    def _trail_may_drive(self, quest_id):
        """O trail dirige só onde **não existe executor**.

        A lista de quests bloqueadas cresceu quatro vezes em 2026-08-17, uma por
        travamento, sempre com a mesma assinatura no relatório
        (`route_id: trail-override-<quest>-<mapa>`): Floresta, ginásio de
        Pewter, e por fim o LARON — bot novo, dois minutos de corrida — parado
        na borda norte de Pallet com `trail-override-buy_pokeballs-0`.

        Ir consertando quest por quest é tratar o sintoma: **toda** quest com
        rota medida acaba precisando entrar na lista, e a que faltar entrar é a
        próxima madrugada perdida. A regra certa é a ordem de autoridade que o
        handoff já escreve — leitura ao vivo > estático > trail, e o plano ganha
        da heurística: onde existe `_run_<quest>`, quem dirige é ele.

        O trail continua sendo **gravado e publicado** — é a medida do que uma
        travessia custou, e é o que sobra para os nós que ainda não têm
        executor (`celadon_story_quest` e os outros seis).
        """
        quest_id = str(quest_id or "")
        if not quest_id or quest_id in TRAIL_BLOCKED_QUESTS:
            return False
        return not hasattr(self, f"_run_{quest_id}")

    def _naming_screen_open(self):
        """O teclado de apelido está desenhado? Pergunta feita à tela."""
        if self.emulator is None:
            return False
        try:
            return screen.naming_screen_open(self.emulator.memory.read_byte)
        except Exception:
            return False

    def _screen_rows(self):
        """O que está desenhado, decodificado do `wTileMap`.

        A tela é RAM. Quem pode aprender um HM é uma pergunta que o cartucho
        já responde: com a lista da party aberta para um TM/HM, ele escreve
        ABLE ou NOT ABLE ao lado de cada um. Ler isso é mais barato e mais
        honesto que caçar a tabela de compatibilidade na ROM — e não há
        palpite nenhum sobre quem aprende o quê.

        A decodificação vive em `src/screen.py`: eram três arquivos lendo o
        mesmo 0xC3A0 por conta própria, e é assim que duas cópias divergem.
        """
        return screen.rows(self.emulator.memory.read_byte)

    def _slots_that_can_learn(self):
        """Slots marcados ABLE na tela da party, na ordem da equipe."""
        able = []
        for row in self._screen_rows():
            if "ABLE" not in row:
                continue
            able.append("NOT ABLE" not in row)
        return able

    def _move_slot_to_forget(self, party_slot):
        """Qual golpe some para o HM entrar.

        Reusa a régua que o controlador de batalha já usa: golpe de status
        vale pela `STATUS_MOVE_PRIORITY` (maior é pior — Growl e Leer valem 9,
        Leech Seed vale 0) e golpe de dano nunca sai enquanto houver status
        para tirar. HM não pode ser apagado pelo cartucho, então nem entra.
        """
        best_slot, best_score = None, None
        for slot, move_id in enumerate(self._party_move_ids(party_slot)):
            if not move_id or move_id in HM_MOVE_IDS:
                continue
            score = STATUS_MOVE_PRIORITY.get(move_id)
            # Golpe de dano (fora da tabela de status) é o último a sair: -1
            # o põe abaixo de qualquer status na escolha do "pior".
            score = -1 if score is None else score
            if best_score is None or score > best_score:
                best_slot, best_score = slot, score
        return best_slot

    def _menu_corner(self):
        return (
            int(self.emulator.memory.read_byte(MENU_TOP_Y_ADDRESS)),
            int(self.emulator.memory.read_byte(MENU_TOP_X_ADDRESS)),
        )

    def _menu_cursor_step(self, current, target):
        """Um passo do cursor, ou None quando já está no alvo."""
        if current < target:
            return WindowEvent.PRESS_ARROW_DOWN
        if current > target:
            return WindowEvent.PRESS_ARROW_UP
        return None

    def _teach_cut_action(self):
        """Ensinar o Cut, dirigindo os menus reais pela RAM.

        Quem decide que acabou é o cartucho: o golpe 15 na party. Medido no
        cartucho em 2026-08-16, do save do AARON logo depois do capitão —
        START, ITEM, HM01, USE, os textos, SIM, a party, e o golpe a esquecer;
        no fim, `IVYSAUR learned CUT!` e a RAM da party em [77, 15, 73, 22].

        A **Butterfree não aprende Cut** (a tela diz NOT ABLE), então "ensinar
        a quem não é o inicial" não era uma opção aqui: o cartucho recusa. A
        escolha sai da própria tela, não de uma preferência.
        """
        if self._party_knows_move(CUT_MOVE_ID):
            self.teach_cut_steps = 0
            return None
        if self._bag_item_count(HM01_CUT) == 0:
            return None

        steps = getattr(self, "teach_cut_steps", 0) + 1
        self.teach_cut_steps = steps
        if steps > TEACH_MENU_STEP_LIMIT:
            # Menu que não se comporta é abandonado, não martelado. B fecha o
            # que estiver aberto e a rota volta a andar; a próxima passagem
            # por aqui tenta de novo do começo.
            self.teach_cut_steps = 0
            return WindowEvent.PRESS_BUTTON_B

        if not self._menu_is_open():
            return WindowEvent.PRESS_BUTTON_START

        corner = self._menu_corner()
        cursor = int(self.emulator.memory.read_byte(MENU_CURSOR_ADDRESS))

        if corner == MENU_MAIN:
            step = self._menu_cursor_step(cursor, MENU_MAIN_ITEM_INDEX)
            return step or WindowEvent.PRESS_BUTTON_A
        if corner == MENU_BAG:
            scroll = int(self.emulator.memory.read_byte(MENU_SCROLL_ADDRESS))
            target = self._bag_item_index(HM01_CUT)
            if target is None:
                return WindowEvent.PRESS_BUTTON_B
            step = self._menu_cursor_step(scroll + cursor, target)
            return step or WindowEvent.PRESS_BUTTON_A
        if corner == MENU_ITEM_USE_TOSS:
            # USE é a primeira opção; TOSS no HM só devolveria uma recusa.
            step = self._menu_cursor_step(cursor, 0)
            return step or WindowEvent.PRESS_BUTTON_A
        if corner == MENU_TEACH_YES_NO:
            step = self._menu_cursor_step(cursor, 0)
            return step or WindowEvent.PRESS_BUTTON_A
        if corner == MENU_PARTY:
            able = self._slots_that_can_learn()
            target = next(
                (slot for slot, can in enumerate(able) if can), None
            )
            if target is None:
                # Ninguém na equipe aprende: sair sem gastar mais passos.
                self.teach_cut_steps = 0
                return WindowEvent.PRESS_BUTTON_B
            self.teach_cut_party_slot = target
            step = self._menu_cursor_step(cursor, target)
            return step or WindowEvent.PRESS_BUTTON_A
        if corner == MENU_FORGET_MOVE:
            party_slot = getattr(self, "teach_cut_party_slot", 0)
            target = self._move_slot_to_forget(party_slot)
            if target is None:
                return WindowEvent.PRESS_BUTTON_B
            step = self._menu_cursor_step(cursor, target)
            return step or WindowEvent.PRESS_BUTTON_A

        # Qualquer outra tela com o flag de menu de pé é texto: avança.
        return WindowEvent.PRESS_BUTTON_A

    def _bag_item_index(self, item_id):
        """Posição do item na mochila, que é a linha dele na lista."""
        count = min(int(self.emulator.memory.read_byte(0xD31D)), 20)
        for index in range(count):
            if int(self.emulator.memory.read_byte(0xD31E + index * 2)) == int(item_id):
                return index
        return None

    def _run_ss_anne_captain(self):
        """Falar com o capitão enjoado até o HM01 entrar na mochila.

        Quem decide que acabou é o cartucho: o HM01 (0xC4) na mochila. Um
        contador de "já falei" seria flag de processo, que some no reinício —
        o mesmo erro que fez o Centro entrar em ciclo de entrar e sair.

        A conversa é longa (o capitão pede a massagem e agradece), então A é
        apertado enquanto houver texto. Sem texto na tela, A de costas não
        abre diálogo nenhum: `wSpriteStateData1+9` diz para onde o jogador
        está virado e o passo para cima encara o capitão em (4,2) sem sair do
        tile — ele bloqueia.
        """
        x, y = self.emulator.memory.get_player_pos()
        if self._bag_item_count(HM01_CUT) > 0:
            # Com o HM na mão, sair da cabine pela porta (0,7).
            return self._follow_route("ss-anne-captain-exit", [(1, 7), (0, 7)])
        if (x, y) != CAPTAIN_APPROACH_TILE:
            return self._follow_route("ss-anne-captain", [CAPTAIN_APPROACH_TILE])
        if self._menu_is_open():
            return WindowEvent.PRESS_BUTTON_A
        if int(self.emulator.memory.read_byte(PLAYER_FACING_ADDRESS)) != FACING_UP:
            self.last_action_was_move = True
            return WindowEvent.PRESS_ARROW_UP
        return WindowEvent.PRESS_BUTTON_A

    def _run_cerulean_gym_quest(self):
        """Enter Cerulean Gym and defeat Misty after Bill is complete."""
        if int(self.emulator.memory.read_byte(0xD356)) & 0x02:
            # Insígnia ganha: sair do ginásio pela porta sul — o executor
            # antigo seguia a rota da abordagem até (4,2) e ficava apertando A
            # na frente da Misty para sempre (medido: AARON parado no tile).
            map_id = int(self.emulator.memory.get_map_id())
            if map_id == 65:
                return self._follow_route(
                    "misty-exit",
                    [(4, 12), (4, 13)],
                )
            return None
        map_id = int(self.emulator.memory.get_map_id())
        if map_id == 88:
            # Finish Bill's post-ticket text, then leave through the south door.
            return self._follow_route(
                "bill-house-exit",
                [(4, 5), (3, 5), (3, 7)],
            )
        if map_id == 36:
            # Reverse the cleared Route 25 maze. This uses the southern return
            # bends opened by trainer movement and ends at the Route 24 seam.
            return self._follow_route(
                "route-25-return",
                [
                    (45, 4), (38, 4), (38, 5), (32, 5), (32, 6),
                    (22, 6), (22, 8), (19, 8), (19, 7), (17, 7),
                    (17, 4), (15, 4), (15, 6), (14, 6), (14, 9),
                    (11, 9), (11, 7), (9, 7), (9, 8), (0, 8),
                ],
            )
        if map_id == 35:
            return self._follow_route(
                "route-24-return",
                [
                    (19, 8), (10, 8), (10, 20), (11, 20),
                    (11, 23), (10, 23), (10, 26), (11, 26),
                    (11, 29), (10, 29), (10, 35),
                ],
            )
        if map_id == 64:
            return self._run_pokemon_center(
                "cerulean-gym-center",
                "cerulean_gym_center_healed",
            )
        if map_id == 3:
            # Sem parada de cura: direto para a porta do ginásio.
            return self._follow_route(
                "cerulean-gym-door",
                [(19, 18), (19, 20), (30, 20), (30, 19)],
            )
        if map_id == 65:
            return self._follow_route(
                "misty-approach",
                [
                    (4, 12), (4, 8), (2, 8), (2, 5),
                    (7, 5), (7, 3), (5, 3), (5, 2), (4, 2),
                ],
            )
        return WindowEvent.PRESS_BUTTON_A

    def _menu_is_open(self):
        return int(self.emulator.memory.read_byte(0xCFC4)) == 1

    def _in_battle_screen(self):
        """True while the battle screen owns the tilemap.

        Em batalha o tilemap (0xC3A0) guarda os gráficos da batalha, não o
        mapa: todo tile lê como parede, e planejar caminho nesse estado grava
        geometria falsa. A batalha manda no passo; a rota só volta depois que
        o flag 0xD057 cair.
        """
        try:
            return int(self.emulator.memory.read_byte(0xD057)) != 0
        except Exception:
            return False

    def _bag_item_count(self, item_id):
        item_count = min(int(self.emulator.memory.read_byte(0xD31D)), 20)
        for index in range(item_count):
            address = 0xD31E + index * 2
            if int(self.emulator.memory.read_byte(address)) == int(item_id):
                return int(self.emulator.memory.read_byte(address + 1))
        return 0

    def _follow_route(self, route_id, waypoints):
        """Walk the route the way it was actually walking before.

        There were two of these in this class, and Python kept the last one:
        the short one. Everything that ever worked on a cartridge worked with
        the short one. Deleting the "dead" duplicate was not a cleanup, it
        swapped the pilot mid-flight — measured from the same save, the long
        version covered 11 tiles in 400 steps and then sat still, where this
        one covered 26 in 77.

        So this is the short one, with two things kept because they are read
        from the cartridge rather than guessed: the published trail, and the
        two-tile pacing guard.
        """
        if not waypoints:
            return None
        # Em batalha o tilemap carrega os gráficos da batalha — todo tile lê
        # como parede. Qualquer plano traçado aqui é lixo e, pior, alimenta o
        # "load de batalha" que já gravou paredes falsas na Floresta. Quem
        # manda no passo em batalha é o controlador de batalha; a rota espera.
        if self._in_battle_screen():
            return None
        if self._menu_is_open():
            presses = getattr(self, "route_menu_presses", 0) + 1
            self.route_menu_presses = presses
            # `MENU_PRESS_LIMIT` was written for this and then stopped being
            # read: the flag at 0xCFC4 can stay up with nothing on screen that
            # a button will clear, and an unbounded B/A alternation is a bot
            # that never walks again. CAARON stood at (5,1) in Oak's Lab for
            # thousands of steps this way, and left no stuck report either,
            # because this return happens before the report is written.
            #
            # So press, then walk anyway, then press again. The D-pad is
            # ignored while real text is up, which makes walking free to try;
            # what must never happen is reading the failed step as a wall, and
            # the bump memory below already refuses to while the flag is up.
            if (presses - 1) % (MENU_PRESS_LIMIT * 2) < MENU_PRESS_LIMIT:
                return self._route_text()
        else:
            self.route_menu_presses = 0

        x, y = self.emulator.memory.get_player_pos()
        map_id = int(self.emulator.memory.get_map_id())
        previous = getattr(self, "route_last_position", None)
        direction = getattr(self, "route_last_direction", None)
        if previous is not None and direction and previous[0] != map_id:
            self.route_entry_map = previous[0]
            self._warp_memory().record(previous[0], previous[1], previous[2], map_id)
            # The tile just arrived on, and how it was entered. `_leave_unknown_map`
            # has always read this and nothing has ever written it, so its first
            # and best way out of a map no executor knows — leave by the door you
            # came in through — was dead code.
            entry_tiles = getattr(self, "map_entry_tiles", None)
            if entry_tiles is None:
                entry_tiles = self.map_entry_tiles = {}
            entry_tiles[map_id] = (x, y, direction)
            # The edge between two outdoor maps is a connection, not a warp:
            # it is in no warp table, so "a door is only ever a destination"
            # never covered it. Standing on the tile you just arrived on, the
            # step back across is the one step that cannot be progress —
            # BARON crossed Viridian/Route 2 twenty-one hundred times in five
            # minutes doing exactly that.
            self.route_entry_block = (
                map_id, x, y, OPPOSITE_DIRECTIONS[direction], 0,
            )
        self.route_last_position = (map_id, x, y)

        # Bumping into something the tileset called walkable. In Mt. Moon the
        # screen stores metatiles and the cave misreads: from (21,25) the game
        # refuses DOWN, the reading calls it free, and the bot pressed into the
        # rock 1813 times. A press that produced no movement is a wall right
        # now — remembered for a handful of steps, never written down. People
        # move away, and so does whatever this was.
        bumped = getattr(self, "route_bumped", {})
        for key in [key for key, age in bumped.items() if age <= 0]:
            del bumped[key]
        for key in list(bumped):
            bumped[key] -= 1
        last_move = getattr(self, "route_last_issue", None) == "move"
        last_direction_taken = getattr(self, "route_last_direction", None)
        if (
            last_move
            and last_direction_taken
            and previous is not None
            and previous == (map_id, x, y)
            and not self._menu_is_open()
        ):
            bumped[(map_id, x, y, last_direction_taken)] = BUMP_MEMORY_STEPS
        self.route_bumped = bumped

        entry_block = getattr(self, "route_entry_block", None)
        blocked_entry = None
        if entry_block:
            entry_map, entry_x, entry_y, back, age = entry_block
            if (map_id, x, y) != (entry_map, entry_x, entry_y) or age >= ENTRY_BLOCK_STEPS:
                self.route_entry_block = None
            else:
                self.route_entry_block = (entry_map, entry_x, entry_y, back, age + 1)
                blocked_entry = back

        # The guide writes the trail down; the follower walks the one that was
        # already confirmed on RAM. Neither changes how a step is chosen.
        # Both trainers are doing the same job now: find the way through and
        # write it down. Whoever confirms a quest first publishes the trail,
        # and the other one joins it — the roles were about styles of play, and
        # what is missing is the map, not variety.
        quest_id = getattr(self, "current_task_name", None)
        recorder = getattr(self, "trail_recorder", None)
        store = getattr(self, "trail_store", None)
        using_trail = False
        if quest_id and recorder is not None:
            recorder.record(quest_id, map_id, x, y)
        # The drawn route is the one that finishes the game, so it is the one
        # that drives. A trail is a measurement of a crossing that worked, and
        # it stays being recorded and published — but following one is opt-in
        # (`POKEAI_FOLLOW_TRAILS=1`), because a trail that overrides the route
        # only has to be wrong once: a single mined point on Route 4, at
        # (27,3), pointed east, which made the sidestep axis vertical, and
        # south from that tile is Route 3. AARON crossed that border every 0.6
        # seconds for an hour, following a "shortcut" over a route that was
        # right the whole time.
        # O `trail-override-*` já carrega o trail (e possivelmente o warp de
        # saída) no chamador — substituir aqui descartaria o warp e o bot
        # pararia a um passo da porta.
        if (
            quest_id
            and store is not None
            and FOLLOW_TRAILS
            and self._trail_may_drive(quest_id)
            and not route_id.startswith("trail-override-")
        ):
            # Recomputing the join every step is what made the trail bounce:
            # from (28,20) the nearest point was (29,20), and from (29,20) it
            # was (28,20) — the trail crosses both on the way out and on the
            # way back. The plan is kept and walked forward like any route;
            # it is only rebuilt when the bot is nowhere near it any more,
            # which is exactly what a whiteout does.
            if getattr(self, "_debug_route", False):
                loaded = store.load(quest_id)
                print(
                    f"[DEBUG-TRAIL] quest={quest_id} mapa={map_id} pos=({x},{y}) "
                    f"legs={len(loaded)} cache={getattr(self, 'trail_plan', None) is not None}",
                    flush=True,
                )
            key = (quest_id, map_id)
            cached = getattr(self, "trail_plan", None)
            trail = cached[1] if cached and cached[0] == key else None
            if trail:
                nearest = min(
                    abs(int(px) - x) + abs(int(py) - y) for px, py in trail
                )
                if nearest > TRAIL_REJOIN_DISTANCE:
                    trail = None
            if trail is None:
                trail = waypoints_from(store.load(quest_id), map_id, x, y)
                # Rejoining by "nearest point" can rejoin *behind*: one step
                # past the tile where the leg begins, the nearest point is that
                # beginning, so the trail pulled the bot back onto the map
                # border it had just crossed — six hundred times. Points just
                # walked are points already spent.
                recent = set(getattr(self, "route_recent_tiles", []))
                while trail and (map_id, int(trail[0][0]), int(trail[0][1])) in recent:
                    trail = trail[1:]
                self.trail_plan = (key, trail)
            if trail and not (len(trail) == 1 and (x, y) == tuple(trail[0])):
                # O cache do trail tem todos os pontos do mapa e não é
                # recalculado enquanto o bot está perto. Chegar no ÚLTIMO
                # ponto com o cache ainda inteiro travava o bot no waypoint
                # final (medido 2026-08-13: Route 5, o bot oscilava em volta
                # de (17,28) com o trail do mapa 16 ainda com 48 pontos).
                # Último ponto alcançado: limpa o cache e devolve ao executor.
                if (x, y) == tuple(trail[-1]) and len(trail) > 1:
                    self.trail_plan = None
                else:
                    waypoints = trail
                    route_id = f"trail-{quest_id}-{map_id}"
                    using_trail = True
            elif trail:
                # The leg ends on the doorway to the next map, and a trail says
                # nothing about how to cross it — the next leg is measured in
                # another map's coordinates. Standing on the last point, hand
                # the step back to the route the quest drew, whose final
                # waypoint is deliberately one tile past the border.
                self.trail_plan = None

        self.route_index = self._select_route_index(route_id, waypoints, (x, y))
        target_x, target_y = waypoints[self.route_index]
        blocked = self._tile_truth()
        if getattr(self, "_debug_route", False):
            print(
                f"[DEBUG-ROUTE] {self.current_task_name} mapa={map_id} pos=({x},{y}) "
                f"route={route_id} idx={self.route_index}/{len(waypoints)} "
                f"target=({target_x},{target_y}) blocked={blocked}",
                flush=True,
            )

        # Orçamento de passos por waypoint. O contador de distância
        # (`route_no_progress`) só vê "não encostou": um waypoint inalcançável
        # com um desvio longo que encolhe a distância devagar zera o contador
        # a cada passo, e o bot queima milhares de passos no mesmo alvo sem
        # nunca liberá-lo. O orçamento é o teto duro: estourou, o waypoint é
        # gasto — mira o próximo; no último, solta a rota e reentra pelo mais
        # próximo. Passos de batalha e de texto não contam (a rota nem roda
        # neles), e o relatório de travamento expõe o orçamento.
        if getattr(self, "route_target_index", None) != self.route_index:
            self.route_target_index = self.route_index
            self.route_waypoint_steps = 0
        else:
            self.route_waypoint_steps = getattr(self, "route_waypoint_steps", 0) + 1
        if self.route_waypoint_steps > WAYPOINT_STEP_BUDGET:
            progress = getattr(self, "route_progress", None) or {}
            if self.route_index < len(waypoints) - 1:
                progress[route_id] = self.route_index + 1
                self.route_index += 1
                self.route_last_issue = "waypoint_budget"
            else:
                progress.pop(route_id, None)
                self.route_id = None
                self.route_last_issue = "route_budget"
            self.route_progress = progress
            self.route_no_progress = 0
            self.route_waypoint_steps = 0
            self.route_target_index = None
        for (bumped_map, bumped_x, bumped_y, direction) in getattr(self, "route_bumped", {}):
            if (bumped_map, bumped_x, bumped_y) == (map_id, x, y):
                blocked.setdefault(direction, "bumped")
        if blocked_entry:
            blocked[blocked_entry] = "map_edge"
        # Collision calls a doorway walkable, which is true and useless: with
        # the Mart door one tile north, "walk north" put the bot inside the
        # shop, out on the mat, and north again — the flashing at the door.
        # A door is only ever somewhere to arrive at.
        # O `_warp_steps` antigo (bloquear pisar em warp que não é o alvo)
        # trancava o bot dentro de prédios cujo corredor passa pela porta de
        # entrada (medido 2026-08-13: no prédio do Underground, o caminho
        # (2,7)→(3,7)→(3,6) cruza a porta (3,7) e a regra o parava em (2,7)
        # para sempre). O `route_entry_block` já impede voltar pela porta por
        # onde entrou; bloquear TODA warp vira parede invisível. Warps são
        # coordenadas conhecidas — pisar nelas é como o jogo funciona (o
        # operador atravessa portas o tempo todo).
        wanted = []
        if abs(target_x - x) >= abs(target_y - y):
            wanted += self._axis_steps(x, target_x, "R", "L")
            wanted += self._axis_steps(y, target_y, "D", "U")
        else:
            wanted += self._axis_steps(y, target_y, "D", "U")
            wanted += self._axis_steps(x, target_x, "R", "L")

        if self.route_index == len(waypoints) - 1 and abs(target_x - x) + abs(
            target_y - y
        ) == 1:
            wanted = [
                "R" if target_x > x else
                "L" if target_x < x else
                "D" if target_y > y else "U"
            ]

        if not wanted:
            # Standing exactly on the last anchor, a route has nothing left to
            # want. With Oak's parcel in the bag a trainer sat on (20,35) doing
            # sidesteps until the watchdog restarted the mission, which put it
            # back on the same tile, which restarted it again — the journey
            # looked like it was rebooting in a loop. Keep heading the way it
            # came in, so "arrived" still means "leave".
            last_direction = getattr(self, "route_last_direction", None)
            if last_direction:
                wanted = [last_direction]

        # Where it has just been. Not learned geometry — a memory eight tiles
        # long, thrown away as it goes.
        stale = self._recently_walked_steps(map_id, x, y)

        # Progress toward this target, measured. Repeating a tile is not
        # evidence of being stuck in tall grass: an encounter freezes the bot
        # where it stands, so the same tile comes up again and again while the
        # route is working perfectly. What being stuck actually looks like is
        # distance to the target that stops falling.
        distance = abs(target_x - x) + abs(target_y - y)
        progress_key = (map_id, target_x, target_y)
        if getattr(self, "route_progress_key", None) != progress_key:
            self.route_progress_key = progress_key
            self.route_best_distance = distance
            self.route_no_progress = 0
        elif distance < getattr(self, "route_best_distance", distance):
            self.route_best_distance = distance
            self.route_no_progress = 0
        else:
            self.route_no_progress = getattr(self, "route_no_progress", 0) + 1

        # A freeze has to leave a trace. Without one, every investigation
        # starts over: load the save, reproduce, guess. This writes down what
        # was decided and why, at the moment the walking stopped.
        self._report_if_stuck(
            map_id, x, y, target_x, target_y, blocked, waypoints, route_id
        )

        # O plano é calculado **antes** da máquina de sprite: é ele que diz se
        # o sprite fecha a passagem ou só está por perto. Ver o comentário do
        # `sprite_closes_the_way` logo abaixo.
        planned = self._planned_step(map_id, x, y, target_x, target_y)

        # Sprite que fecha a única passagem — treinador, fóssil ou NPC parado.
        # Medido em Mt. Moon: o bot ficou 1000+ passos ao lado do mesmo
        # treinador porque o fallback só virava o personagem — D-pad sozinho
        # nunca abre diálogo em Gen I. Aqui, virar para o sprite e apertar A:
        # treinador vira batalha (vencer remove o sprite e o tile abre), fóssil
        # vira pickup (some do tile), NPC vira diálogo (avançado, o desvio
        # assume). Os fósseis (12,6)/(13,6) do B2F são o portão da travessia:
        # não há outro caminho da sala central para a escada oeste.
        #
        # Treinador derrotado em Gen I continua no tile para sempre, visível e
        # bloqueando (o Youngster de Mt. Moon em (12,16) ficou com o texto
        # pós-batalha, "I came down here to show off to girls", e a rota
        # conversava com ele em ciclo). Conversa que não resolve em batalha ou
        # pickup entra em `route_sprites_tried` e deixa de ser alvo: o desvio
        # assume e o ghost vira parede permanente.
        tried = getattr(self, "route_sprites_tried", None)
        if tried is None:
            tried = self.route_sprites_tried = set()
        talk = getattr(self, "route_sprite_talk", None)
        if talk is not None:
            if (
                talk["route"] != route_id
                or talk["map"] != map_id
                or talk["pos"] != (x, y)
                or blocked.get(talk["direction"]) != "sprite"
            ):
                # O sprite saiu, saímos do tile, a rota mudou ou ele andou:
                # a interação acabou e o resto da rota assume.
                self.route_sprite_talk = None
            else:
                talk["steps"] = talk["steps"] + 1
                if talk["steps"] <= SPRITE_DIALOG_LIMIT:
                    # Texto de pickup/diálogo é avançado pelo mesmo A; menu
                    # aberto já é atendido pelo topo do _follow_route.
                    return WindowEvent.PRESS_BUTTON_A
                # Limite estourado: diálogo que não remove o sprite — treinador
                # já derrotado, NPC que não anda. B fecha o que estiver aberto,
                # o tile entra no conjunto de "não conversar de novo" e o
                # desvio assume.
                dx, dy = ROUTE_STEP_OFFSETS[talk["direction"]]
                tried.add((map_id, talk["pos"][0] + dx, talk["pos"][1] + dy))
                self.route_sprite_talk = None
                return WindowEvent.PRESS_BUTTON_B
        elif (
            planned is None
            or blocked.get(planned) == "sprite"
            or getattr(self, "route_no_progress", 0) > SPRITE_PATIENCE_STEPS
            or self._route_is_cycling()
        ):
            # **Só conversa quem não tem por onde andar.** A lista `wanted` é
            # de eixos, não de caminho: de (4,2) para (5,12) ela é ['D', 'R']
            # porque o alvo está a uma casa à direita e dez abaixo — e o Oak,
            # parado em (5,2), caía como "sprite no rumo do waypoint" mesmo
            # sem fechar nada. O caminho real desce primeiro (`DDDDDDDDDRD`).
            #
            # Medido em 2026-08-16 com três bots novos: os três viravam para o
            # Oak, apertavam A, **reabriam o diálogo do pacote** e ficavam
            # alternando A e B para sempre — 6.240 passos no mesmo tile, os
            # três presos no laboratório sem nunca sair de Pallet.
            #
            # Com o plano na mão, andar é a resposta; a conversa fica para
            # quando não há plano — que é exatamente Mt. Moon, onde o
            # treinador parado fecha a única passagem e o `find_path` devolve
            # None porque o objeto do ROM bloqueia o corredor inteiro.
            #
            # Ter plano não é garantia de sair do lugar: no corredor lotado do
            # laboratório o plano alternava L em (4,2) e R em (3,2), e o bot
            # ficava indo e voltando entre as duas casas. Por isso a paciência
            # continua valendo como saída: `SPRITE_PATIENCE_STEPS` passos sem
            # encurtar distância e a conversa volta à mesa, com o limite de
            # diálogo e o `route_sprites_tried` cuidando de quem não sai.
            memory = self._map_memory()
            static_objects = (
                memory.object_positions(map_id) if memory is not None else set()
            )
            sprite_blockers = []
            for step in wanted:
                if blocked.get(step) == "sprite":
                    dx, dy = ROUTE_STEP_OFFSETS[step]
                    tile = (x + dx, y + dy)
                    if tile in static_objects and (map_id, tile[0], tile[1]) not in tried:
                        sprite_blockers.append(step)
            if not sprite_blockers and (
                self.route_no_progress > SPRITE_PATIENCE_STEPS
                or self._route_is_cycling()
            ):
                # Sem sprite no rumo do waypoint: quem fecha a passagem pode
                # estar ao lado (o fóssil (12,6) fica à direita de quem chega
                # pelo bolsão oeste, com o alvo a oeste).
                sprite_blockers = []
                for step in ("U", "D", "L", "R"):
                    if blocked.get(step) != "sprite":
                        continue
                    dx, dy = ROUTE_STEP_OFFSETS[step]
                    if (map_id, x + dx, y + dy) not in tried:
                        sprite_blockers.append(step)
            if sprite_blockers:
                # **Treinador primeiro.** Falar com um NPC devolve texto e ele
                # continua no tile; um treinador vira batalha, e vencer o
                # remove de vez — é a única interação que abre passagem em
                # definitivo. No laboratório quem fecha o corredor para baixo
                # é o rival (objeto `trainer` em (4,3)), e a luta com ele é a
                # própria história: enfrentá-lo é avançar, não um desvio.
                trainers = self._map_memory().trainer_positions(map_id)
                sprite_blockers.sort(
                    key=lambda step: (x + ROUTE_STEP_OFFSETS[step][0],
                                      y + ROUTE_STEP_OFFSETS[step][1]) not in trainers
                )
                direction = sprite_blockers[0]
                self.route_sprite_talk = {
                    "route": route_id,
                    "map": map_id,
                    "pos": (x, y),
                    "direction": direction,
                    "steps": 0,
                }
                self.route_last_issue = "sprite_dialog"
                return ROUTE_EVENTS[direction]

        # What the screen has already shown of this map, kept. A screenful is
        # enough to step around a tree and nowhere near enough to leave a
        # pocket whose exit is off screen — which is why two trainers spent an
        # afternoon in the Forest, each tile looking like the best way to a
        # waypoint neither could reach. Terrain does not change, so remembering
        # it is not a guess; people are left out of it on purpose.
        # One tile away, there is nothing to plan: step onto it. Planning here
        # is how the gate door was missed — the bot had crossed (3,44) often
        # enough for the frontier rule to take over, and it walked away from
        # the doorway it was standing next to, over and over.
        if abs(target_x - x) + abs(target_y - y) == 1:
            step = (
                "R" if target_x > x else
                "L" if target_x < x else
                "D" if target_y > y else "U"
            )
            # Com trail ativo, o terrain do TileCollision não bloqueia: o
            # operador atravessou esse passo para medir o trail, então é o
            # caminho (medido 2026-08-13: no Centro 64 o trail mirava a
            # saída (3,5) mas o wTileMap lia terrain e o bot ficava parado
            # a um passo da porta).
            if step not in blocked or (
                using_trail and blocked.get(step) == "terrain"
            ):
                return self._route_move(step)

        # The plan outranks the eight-tile memory: that memory exists for when
        # there is nothing better than a guess, and a committed path is better.
        # Um trail medido pelo operador é melhor que um plano recalculado: o
        # `_planned_step` replaneja pelo static e pode desviar o bot para uma
        # escada ou contornar um objeto que o trail já atravessou (medido
        # 2026-08-13: no prédio do Underground o plano puxava o bot para a
        # escada (2,7)↔(2,3) em vez do corredor (3,7)→(3,4)).
        # O trail define a ROTA (os waypoints que o operador mediu), mas quem
        # navega o labirinto entre eles é o `_planned_step` (BFS no static).
        # Sem ele o bot tentava cortar em linha reta para o waypoint e batia
        # em paredes que o labirinto contorna (medido 2026-08-13: Cerulean,
        # o bot mirando (37,20) direto batia na parede sem entrar na casa).
        # O `planned` já foi calculado acima, antes da máquina de sprite —
        # é ele que decide se o sprite fecha a passagem ou só está por perto.
        if getattr(self, "_debug_route", False):
            print(
                f"[DEBUG-ROUTE] passo: pos=({x},{y}) target=({target_x},{target_y}) "
                f"wanted={wanted} stale={stale} planned={planned} blocked={blocked}",
                flush=True,
            )
        # O plano do static é a autoridade de terreno; o TileCollision é uma
        # dica ao vivo que às vezes mente (wTileMap dessincronizado em
        # transições ou mapas pequenos — medido 2026-08-13: GARON preso no
        # Centro 64 com D lendo parede onde o static e o jogo abrem). Só
        # gente (sprite) bloqueia um passo planejado; terreno duvidoso é
        # tentado e o `route_bumped` corrige se o jogo recusar.
        if planned is not None and blocked.get(planned) != "sprite":
            return self._route_move(planned)

        # Ledge: o alvo pode estar do outro lado de um penhasco — descer pula
        # o tile do meio, que o planejador trata como parede. (79,8)->(79,10)
        # da Rota 4 é exatamente isso (a faixa de penhasco em y=9). Apertar na
        # parede comum não move nada, então tentar é de graça quando o alvo
        # está alinhado a dois tiles na direção e o pouso é andável.
        #
        # **Só depois do plano.** Um penhasco e uma parede com porta atrás têm
        # a mesma assinatura no estático — meio sólido, pouso andável — e a
        # regra disparava nos dois. Medido em 2026-08-16, na Route 5: o bot
        # em (15,27) mirando a porta do Underground (17,27), com (16,27) de
        # parede, apertou R contra a parede por 250 passos enquanto o
        # planejador já tinha o desvio de quatro passos (D,R,R,U) na mão.
        # Quem tem caminho andando não precisa pular: o pulo é o que sobra
        # quando o plano não existe, e é exatamente assim que a Rota 4 é —
        # o penhasco parte o mapa e não há desvio nenhum.
        if (
            (target_x == x or target_y == y)
            and abs(target_x - x) + abs(target_y - y) == 2
        ):
            step = (
                "R" if target_x > x else
                "L" if target_x < x else
                "D" if target_y > y else "U"
            )
            if blocked.get(step) == "terrain":
                dx, dy = ROUTE_STEP_OFFSETS[step]
                memory = self._map_memory()
                if (
                    memory is not None
                    and not memory.is_solid(map_id, (x + 2 * dx, y + 2 * dy))
                ):
                    return self._route_move(step)

        for step in wanted:
            if step not in blocked and step not in stale:
                return self._route_move(step)

        # Waypoint gasto na memória recente: o bot já passou por ele (o trail
        # cruza tiles já andados quando termina). Voltar para o tile do
        # waypoint final é o caminho, não um vaivém — o stale não pode
        # trancar o último passo (medido 2026-08-13: Route 6, o bot vagueava
        # em volta do último ponto do trail porque (17,20) estava recente).
        # No MEIO da rota, o stale continua valendo: emitir qualquer passo
        # livre (incluindo voltar) é o vaivém que o operador viu em (19,27)
        # oscilando com (20,27).
        if self.route_index == len(waypoints) - 1:
            for step in wanted:
                if step not in blocked:
                    return self._route_move(step)

        # Item ball é objeto sólido em Gen I: não se pisa, e apertar A de
        # frente não a pega — a colisão ao vivo a reporta como sprite e o
        # waypoint em cima dela é inalcançável por construção. A rota tem de
        # contornar o tile, não tentar coletar. Medido na sonda: (35,31) do
        # 1F não entra no componente alcançável de (34,31).
        if wanted and all(blocked.get(step) == "sprite" for step in wanted):
            self.route_blocked_steps = getattr(self, "route_blocked_steps", 0) + 1
            if self.route_blocked_steps <= SPRITE_PATIENCE_STEPS:
                return None

        # Both axes are walls. A sidestep chosen blindly is what parked two
        # trainers against the Forest's y=30 wall — one paced between (6,30)
        # and (8,30) for half an hour while the grass fed it battles, the other
        # simply stopped at (18,32). The screen knows the way around: the tile
        # map says which of the visible tiles are walkable, so ask it instead
        # of guessing left or right.
        step = self._visible_step(target_x - x, target_y - y)
        if step is not None and step not in blocked and step not in stale:
            return self._route_move(step)

        detours = ("U", "D") if wanted and wanted[0] in ("L", "R") else ("L", "R")
        for candidate in detours:
            if candidate not in blocked and candidate not in stale:
                return self._route_move(candidate)
        # Everything ahead is either a wall or somewhere we just came from.
        # Going back is worse than standing still only while there is another
        # option; now there is not.
        if step is not None and step not in blocked:
            return self._route_move(step)
        for candidate in wanted + list(detours):
            if candidate not in blocked:
                return self._route_move(candidate)

        # Nada livre em direção nenhuma. Se o que fecha o caminho é gente,
        # andar contra ela é a jogada: em Gen I isso vira o personagem para o
        # NPC e dispara a fala dele, e o avanço de texto cuida do resto. Muitos
        # saem do caminho depois de falar; os de história precisam ser falados
        # de qualquer forma.
        #
        # AARON ficou preso em (5,1) no lab do Oak com as quatro direções
        # fechadas — duas paredes, o Oak abaixo e alguém à esquerda — e este
        # ramo devolvia None, então ele não apertava nada. Parado para sempre é
        # pior que falar com quem está na frente.
        for candidate in wanted + list(detours):
            if blocked.get(candidate) == "sprite":
                return self._route_move(candidate)
        return None

    def _route_role(self):
        """Guide or follower; tests build agents without going through init."""
        return getattr(self, "route_role", "follower")

    def publish_trail(self, quest_id):
        """Hand the walked path to the followers, once the cartridge agrees.

        Called only when a quest predicate is confirmed on real RAM, so a
        published trail is by construction a path that arrived — and, since a
        whiteout restarts the recording, one that arrived without dying.

        Returns what the crossing cost, or ``False`` when nothing was stored.
        """
        recorder = self.trail_recorder
        if recorder.quest_id != quest_id:
            return False
        legs = recorder.legs()
        cost = {
            "points": sum(len(leg["points"]) for leg in legs),
            "maps": [leg["map"] for leg in legs],
            "death_cycle": recorder.cycle,
            "steps": recorder.steps,
        }
        published = self.trail_store.publish(
            quest_id, self.player_name, legs,
            dense=True, cycle=recorder.cycle, steps=recorder.steps,
        )
        recorder.clear()
        return cost if published else False

    def begin_death_cycle(self, cycle):
        """A whiteout closes the attempt; report what it cost before dropping it."""
        # O avanço de rota morre com a tentativa. O cartucho levou o treinador
        # de volta a um Centro, então "já passei por aqui" deixou de valer: a
        # travessia recomeça, e mirar o waypoint do meio a partir da porta é
        # planejar por cima de terreno que esta tentativa não andou.
        self.route_progress = {}
        self.route_sprite_talk = None
        self.route_target_index = None
        self.route_waypoint_steps = 0
        recorder = getattr(self, "trail_recorder", None)
        if recorder is None:
            return 0
        self.trail_plan = None
        return recorder.restart(cycle)

    def _route_is_cycling(self, window=6):
        """O bot está indo e voltando entre duas casas?

        O contador de progresso mede **distância**, e é cego para vaivém: de
        (3,2) para (4,2) a distância até (5,12) cai de 12 para 11, então o
        passo de volta zera o contador e a paciência nunca acumula. Medido em
        2026-08-16 no laboratório do Oak: três bots novos alternando entre
        duas casas por centenas de passos com `route_no_progress` sempre baixo.

        Ciclo de período 2 é o que um bot preso realmente produz, e o projeto
        já o reconhece em outros lugares (o diário colapsa ciclo, o relay pede
        replan por "2 estados repetidos 3 vezes"). Aqui ele vira o sinal que
        falta: duas casas alternando na janela recente é estar preso, por mais
        que a distância oscile.
        """
        history = list(getattr(self, "route_recent_tiles", []))[-window:]
        if len(history) < 4:
            return False
        if len({tile for tile in history}) != 2:
            return False
        return all(a != b for a, b in zip(history, history[1:]))

    def _recently_walked_steps(self, map_id, x, y):
        """Directions that lead back into the last few tiles walked.

        Pacing is not a wall and not a person: it is the route and the detour
        disagreeing. Two tiles were not enough to see it. BARON walked between
        (6,30) and (8,30) in the Forest for half an hour — a four-step cycle,
        invisible to a memory that only looked two steps back — while the grass
        kept handing him battles, so from outside it looked like training.

        So the memory is the last eight tiles, and it only has an opinion when
        the bot is standing somewhere it has already been in that window: then
        every step that leads back into the window is discouraged. Discouraged,
        not forbidden — the caller falls back to them when nothing else is
        open. Nothing is written down, nothing is learned, nothing outlives
        eight steps.
        """
        history = list(getattr(self, "route_recent_tiles", []))
        history.append((map_id, x, y))
        history = history[-ROUTE_MEMORY_TILES:]
        self.route_recent_tiles = history
        if history.count((map_id, x, y)) < 2:
            return set()
        visited = set(history)
        stale = set()
        for direction, (dx, dy) in ROUTE_STEP_OFFSETS.items():
            if (map_id, x + dx, y + dy) in visited:
                stale.add(direction)
        return stale

    def _report_if_stuck(self, map_id, x, y, target_x, target_y, blocked,
                         waypoints, route_id):
        """Write one line explaining a freeze, the moment it becomes one.

        Everything here is read, never inferred: where the bot is, where the
        route wants it, which directions the cartridge refuses and for what
        reason, what the accumulated map thinks, and how long it has been
        getting no closer. Read it later with `tools/stuck_report.py`.
        """
        # Travar nem sempre é ficar no mesmo tile: dois tiles alternados são
        # igualmente parados, e foi assim que a Rota 4 escapou do primeiro
        # gatilho. O que conta é quantos lugares diferentes ele viu por último.
        window = (getattr(self, "stuck_report_window", []) + [(map_id, x, y)])[-STUCK_WINDOW_TILES:]
        self.stuck_report_window = window

        # Trocar de mapa também é ficar parado, e esse jeito de travar escapava
        # do gatilho acima duas vezes: cada travessia pisa tiles diferentes dos
        # dois lados, então a janela enche de posições distintas; e a chave de
        # progresso inclui o mapa, então "passos sem encurtar a distância"
        # zera a cada ida. AARON cruzou Rota 4 e Mt. Moon **400 vezes em 300
        # segundos** sem produzir uma linha de relatório, e foi a terceira vez
        # no mesmo dia que um vaivém entre mapas precisou ser descoberto na mão.
        crossings = getattr(self, "stuck_map_window", [])
        if not crossings or crossings[-1] != map_id:
            crossings = (crossings + [map_id])[-STUCK_MAP_CROSSINGS:]
            self.stuck_map_window = crossings
        bouncing = (
            len(crossings) >= STUCK_MAP_CROSSINGS and len(set(crossings)) <= 2
        )

        if not bouncing and (
            len(window) < STUCK_WINDOW_TILES
            or len(set(window)) > STUCK_DISTINCT_TILES
        ):
            self.stuck_report_steps = 0
            self.stuck_report_written = 0
            return
        self.stuck_report_steps = getattr(self, "stuck_report_steps", 0) + 1
        written = getattr(self, "stuck_report_written", 0)
        if self.stuck_report_steps < STUCK_REPORT_STEPS * (written + 1):
            return
        self.stuck_report_written = written + 1

        memory = self._map_memory()
        try:
            reachable = memory.find_path(map_id, (x, y), (target_x, target_y))
        except Exception:
            reachable = None
        try:
            frontier = memory.nearest_frontier(map_id, (x, y))
        except Exception:
            frontier = None
        try:
            warps = sorted(self._tile_reader().warp_tiles())
        except Exception:
            warps = []
        party = []
        try:
            for index in range(min(int(self.emulator.memory.get_party_count()), 6)):
                start = 0xD16B + index * 44
                read = self.emulator.memory.read_byte
                party.append({
                    "species": int(read(start)),
                    "hp": (int(read(start + 1)) << 8) + int(read(start + 2)),
                    "max_hp": (int(read(start + 34)) << 8) + int(read(start + 35)),
                    "pp": [int(read(start + 29 + slot)) & 0x3F for slot in range(4)],
                })
        except Exception:
            pass

        report = {
            "at": time.time(),
            "agent": getattr(self, "player_name", "?"),
            "quest": getattr(self, "current_task_name", None),
            "map": map_id,
            "position": [x, y],
            "target": [target_x, target_y],
            "route_id": route_id,
            "route_index": getattr(self, "route_index", None),
            "bouncing_between_maps": (
                sorted(set(getattr(self, "stuck_map_window", []))) if bouncing else None
            ),
            "waypoints": [list(point) for point in waypoints[:8]],
            "blocked": dict(blocked),
            "bumped": [
                list(key) for key in getattr(self, "route_bumped", {})
                if key[:3] == (map_id, x, y)
            ],
            "steps_on_this_tile": self.stuck_report_steps,
            "steps_without_progress": getattr(self, "route_no_progress", 0),
            "waypoint_steps": getattr(self, "route_waypoint_steps", 0),
            "waypoint_budget": WAYPOINT_STEP_BUDGET,
            "closest_it_got": getattr(self, "route_best_distance", None),
            "path_to_target": "".join(reachable) if reachable else None,
            "nearest_unexplored": list(frontier) if frontier else None,
            "map_warps": [list(warp) for warp in warps],
            "terrain_known": {
                "walkable": len(memory.walkable.get(int(map_id), ())),
                "solid": len(memory.solid.get(int(map_id), ())),
            },
            "in_battle": int(self.emulator.memory.read_byte(0xD057)),
            "textbox": int(self.emulator.memory.read_byte(0xCFC4)),
            "party": party,
        }
        try:
            path = Path(self.save_dir) / "logs" / "stuck.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(report, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _nearest_useful_warp(self, x, y):
        """Closest door on this map that is not the one just used."""
        reader = self._tile_reader()
        if reader is None:
            return None
        try:
            warps = reader.warp_tiles()
        except Exception:
            return None
        entry = getattr(self, "route_entry_block", None)
        recent = {(int(a), int(b)) for _, a, b in getattr(self, "route_recent_tiles", [])}
        if entry:
            recent.add((entry[1], entry[2]))
        candidates = [tile for tile in warps if tile not in recent]
        if not candidates:
            candidates = list(warps)
        if not candidates:
            return None
        return min(candidates, key=lambda t: abs(t[0] - x) + abs(t[1] - y))

    def _warp_steps(self, x, y, goal):
        """Directions that step onto a door which is not where we are going."""
        reader = self._tile_reader()
        if reader is None:
            return {}
        try:
            warps = reader.warp_tiles()
        except Exception:
            return {}
        return {
            direction: "warp"
            for direction, (dx, dy) in ROUTE_STEP_OFFSETS.items()
            if (x + dx, y + dy) in warps and (x + dx, y + dy) != tuple(goal)
        }

    def _map_memory(self):
        """Terrain seen so far, shared by every trainer who walks the same map."""
        memory = getattr(self, "map_memory", None)
        if memory is None:
            memory = MapMemory(SHARED_TERRAIN_PATH)
            self.map_memory = memory
        return memory

    def _tile_reader(self):
        reader = getattr(self, "tile_collision", None)
        if reader is None:
            pyboy = getattr(self.emulator, "pyboy", None)
            if pyboy is None:
                return None
            reader = TileCollision(pyboy)
            self.tile_collision = reader
        return reader

    def _planned_step(self, map_id, x, y, target_x, target_y):
        """First step of a path across everything seen of this map, or None.

        Unseen tiles are treated as worth trying, so the plan happily walks off
        the edge of what has been looked at; every step replaces that optimism
        with a reading. People are avoided as of right now, never remembered.
        """
        reader = self._tile_reader()
        if reader is None:
            return None
        memory = self._map_memory()
        try:
            # Only read terrain from a screen that is showing the map. In a
            # battle the tile map holds the battle graphics, and every tile
            # reads as a wall: those readings were stored as permanent
            # geometry, and after a few fights in tall grass the Forest was
            # remembered as a closed pocket — from (6,30) the map offered no
            # path to any waypoint, not even to the edge of what was known.
            if (
                int(self.emulator.memory.read_byte(0xD057)) == 0
                and not self._menu_is_open()
            ):
                memory.observe(map_id, (x, y), reader.terrain_grid())
                memory.forget_solid(map_id, (x, y))
            occupied = {
                (x + dx, y + dy) for dx, dy in reader.occupied_offsets()
            }
            # Treinador parado, NPC, fóssil e item ball não andam: o tile deles
            # sai do ROM e não muda até a luta/pickup. O plano normal os
            # contorna; o fallback abaixo é quem cruza o que já abriu.
            #
            # Mas o bloco de objetos do ROM é onde cada sprite **começa**, não
            # onde ele está. Muitos andam (`movement` 255) e alguns nem
            # entraram em cena ainda. Perto do jogador quem responde é a
            # leitura ao vivo — que também é o cartucho, e mais atual: se a
            # tela diz que o tile está livre, ele está livre.
            #
            # Medido em 2026-08-16, no laboratório do Oak: o rival é objeto
            # `trainer` em (4,3) e ainda não tinha aparecido; o `_tile_truth`
            # via só o Oak à direita, e mesmo assim o plano contornava (4,3)
            # como parede. De (4,2) ele saía `L`, de (3,2) saía `R`, e os três
            # bots novos passaram centenas de passos entre duas casas por
            # causa de um obstáculo que não estava lá.
            #
            # Longe do jogador o estático continua mandando: fora da tela não
            # há leitura ao vivo, e é lá que ele evita planejar por cima do
            # treinador que fecha um corredor inteiro (o portão dos fósseis do
            # B2F de Mt. Moon é exatamente isso, e continua bloqueado porque a
            # essa distância o bot enxerga o sprite quando chega perto).
            static_objects = self._map_memory().object_positions(map_id)
            occupied |= {
                tile for tile in static_objects
                if abs(tile[0] - x) > VISIBLE_TILE_RADIUS_X
                or abs(tile[1] - y) > VISIBLE_TILE_RADIUS_Y
            }
            # A door is walkable and it is also a trapdoor. Planning *through*
            # one is what made the Mart feel like it had gravity: the path to a
            # waypoint two tiles away crossed the doorway, the bot stepped in,
            # came out on the mat, and planned the same path again. Doors are
            # only ever a destination, never a shortcut.
            #
            # Com uma exceção, que é a própria convenção das rotas daqui: o
            # último waypoint fica **um tile depois** da porta, fora do mapa
            # andável, porque é ele que força o passo que atravessa. Bloquear
            # a porta nesse caso torna o alvo inalcançável — não existe outro
            # caminho para um tile que só a porta alcança — e sem plano o
            # `route_no_progress` sobe até a regra de fronteira sequestrar o
            # alvo. Medido em 2026-08-16, na casa inicial: o HARON andou até
            # (7,6), voltou a casa inteira e ficou 11.355 relatórios de
            # travamento oscilando em (0,2)/(1,2), o canto inexplorado, com a
            # porta a oito passos. Dois bots novos, 10 minutos cada, nenhum
            # saiu da primeira casa do jogo.
            #
            # A exceção é estreita de propósito: só vale quando o alvo **não
            # é célula andável do estático** (a âncora de fora do mapa) e a
            # porta é vizinha dele. Waypoint comum continua contornando toda
            # porta, que é o que segura a gravidade do Mart.
            goal = (target_x, target_y)
            static_cells = memory.static.get(int(map_id))
            goal_is_past_the_door = (
                static_cells is not None and goal not in static_cells
            )
            occupied |= {
                tile for tile in reader.warp_tiles()
                if tile != goal and tile != (x, y)
                and not (
                    goal_is_past_the_door
                    and abs(tile[0] - goal[0]) + abs(tile[1] - goal[1]) == 1
                )
            }
            # Walls found by bumping belong in the plan, not only in the last
            # choice of step. Without this the planner kept proposing the same
            # impossible first move: the report read "caminho até o alvo:
            # DRRRUU" while D was the very wall the bot had just hit.
            occupied |= {
                (key[1] + dx, key[2] + dy)
                for key in getattr(self, "route_bumped", {})
                if key[0] == map_id
                for dx, dy in [ROUTE_STEP_OFFSETS[key[3]]]
            }
        except Exception:
            return None
        self.map_memory_steps = getattr(self, "map_memory_steps", 0) + 1
        if self.map_memory_steps % TERRAIN_SAVE_INTERVAL == 0:
            try:
                memory.save()
            except OSError:
                pass
        # A plan is followed, not recomputed. Replanning every step is what the
        # y=30 tree line in the Forest turned into pacing: the way around is
        # long and mostly unseen, so each fresh search picked a different side
        # and the bot alternated between (6,30) and (8,30) forever, learning a
        # screenful each time and never committing to either. Now the path is
        # kept until it is spent, until the goal changes, or until the very
        # tile it wants to step on turns out to be a wall.
        # Repeating a tile means the goal is behind something the map does not
        # know yet. Aim at the edge of the known instead: walking there is the
        # only move that turns unknown into map, and it always ends the loop.
        if (
            getattr(self, "route_no_progress", 0) > NO_PROGRESS_STEPS
            and abs(target_x - x) + abs(target_y - y) > FRONTIER_MIN_DISTANCE
        ):
            frontier = memory.nearest_frontier(map_id, (x, y), blocked=occupied)
            if frontier and frontier != (x, y):
                target_x, target_y = frontier
            elif getattr(self, "route_no_progress", 0) > STUCK_GIVE_UP_STEPS:
                # Nothing to explore and nowhere to get to: the waypoint is
                # wrong for where this bot actually is. The map's own doors are
                # the one thing here that is not a guess — a cave has no other
                # way on — so head for the nearest one that is not the way in.
                door = self._nearest_useful_warp(x, y)
                if door:
                    target_x, target_y = door

        plan = getattr(self, "terrain_plan", None)
        goal_key = (map_id, (target_x, target_y))
        if plan and plan["key"] == goal_key and plan["steps"]:
            step = plan["steps"][0]
            dx, dy = ROUTE_STEP_OFFSETS[step]
            destination = (x + dx, y + dy)
            if (
                plan["from"] == (x, y)
                and destination not in occupied
                and not memory.is_solid(map_id, destination)
            ):
                plan["steps"] = plan["steps"][1:]
                plan["from"] = destination
                return step
        try:
            path = memory.find_path(
                map_id, (x, y), (target_x, target_y), blocked=occupied
            )
            if not path:
                # No route through what is known. The notes are a hint, never
                # an authority: live collision refuses a real wall at the
                # moment of the step, so trying is cheap and standing still is
                # not. Without this the bot sat inside a pocket its own map had
                # invented and had nothing left to explore.
                #
                # The static objects are left out of this last resort on
                # purpose: the Rocket-gated fossil room has no path around its
                # trainer, and a path that crosses his tile is exactly what
                # lets the route continue after the battle removes him. The
                # same for a picked-up fossil.
                path = memory.find_path(
                    map_id, (x, y), (target_x, target_y),
                    blocked=occupied - static_objects, ignore_solid=True,
                )
        except Exception:
            self.terrain_plan = None
            return None
        if not path:
            self.terrain_plan = None
            return None
        first_dx, first_dy = ROUTE_STEP_OFFSETS[path[0]]
        self.terrain_plan = {
            "key": goal_key,
            "steps": path[1:],
            "from": (x + first_dx, y + first_dy),
        }
        return path[0]

    def _visible_step(self, target_dx, target_dy):
        """Find one local step around visible terrain and sprites."""
        reader = getattr(self, "tile_collision", None)
        if reader is None:
            pyboy = getattr(self.emulator, "pyboy", None)
            if pyboy is None:
                return None
            reader = TileCollision(pyboy)
            self.tile_collision = reader
        try:
            return reader.path_step(target_dx, target_dy)
        except Exception:
            return None

    @staticmethod
    def _axis_steps(current, target, positive, negative):
        if target > current:
            return [positive]
        if target < current:
            return [negative]
        return []

    def _leave_unknown_map(self):
        """Walk back out of a map no executor has a route for.

        Wandering into an interior used to be terminal: with no route for that
        map the executor pressed A forever, and both bots sat inside the Mt.
        Moon trader's house until someone noticed. The door is known, though —
        the tile the bot appeared on when the map changed, exited by the
        opposite of the direction that walked in.
        """
        map_id = int(self.emulator.memory.get_map_id())
        position = self.emulator.memory.get_player_pos()

        entry = getattr(self, "map_entry_tiles", {}).get(map_id)
        if entry is None:
            # No transition seen this session, so fall back to a door somebody
            # has already walked through. Ranked below the entry tile on
            # purpose: the nearest door may well be the one just entered, and
            # aiming at it walks the bot straight back where it came from.
            known = self._warp_memory().doors_from(map_id)
            if tuple(position) in known:
                # Já em cima da porta: aqui não se anda, se atravessa. Num
                # interior de Gen I a saída é o capacho na parede sul, e sair
                # dele é apertar para baixo — é o que o controlador de Centro
                # sempre fez em (3,7).
                #
                # Andar até "a porta mais próxima que não é esta" parece a
                # correção óbvia e não é: o lab do Oak tem porta dupla, (4,11)
                # e (5,11), então o bot troca de metade, a outra vira a mais
                # próxima, e ele fica batendo entre as duas para sempre.
                self.last_action_was_move = True
                return WindowEvent.PRESS_ARROW_DOWN
            if known:
                door = min(
                    known,
                    key=lambda tile: (
                        abs(tile[0] - position[0]) + abs(tile[1] - position[1])
                    ),
                )
                return self._follow_route(f"door-{map_id}", [door])
        if entry is None:
            # Never saw the transition — a resumed save, or the whiteout warp
            # that drops a run at its mother's house. Head for the south edge,
            # where interior doors are, but through the route machinery: a
            # blind DOWN press against a wall repeats forever and teaches
            # nothing, while a route learns the wall and plans around it.
            x, y = self.emulator.memory.get_player_pos()
            return self._follow_route(f"exit-{map_id}", [(x, y + BLIND_EXIT_REACH)])

        entry_x, entry_y, entry_direction = entry
        if (self.emulator.memory.get_player_pos()) != (entry_x, entry_y):
            return self._follow_route(f"leave-{map_id}", [(entry_x, entry_y)])
        self.last_action_was_move = True
        return ROUTE_EVENTS[OPPOSITE_DIRECTIONS[entry_direction]]

    def _tile_truth(self):
        """Blocked directions read from the cartridge, or {} if unreadable."""
        reader = getattr(self, "tile_collision", None)
        if reader is None:
            pyboy = getattr(self.emulator, "pyboy", None)
            if pyboy is None:
                return {}
            reader = TileCollision(pyboy)
            self.tile_collision = reader
        try:
            return reader.blocked_directions()
        except Exception:
            return {}

    def _warp_memory(self):
        """Doors shared by every trainer, beside the learned collision map."""
        memory = getattr(self, "warp_memory", None)
        if memory is None:
            memory = WarpMemory(SHARED_WARP_PATH)
            self.warp_memory = memory
        return memory



    def _route_move(self, direction):
        """Issue a D-pad press and remember it, so a failure can be attributed."""
        self.last_action_was_move = True
        self.route_last_direction = direction
        self.route_last_issue = "move"
        return ROUTE_EVENTS[direction]
    def _fixed_route(self, route_id, actions):
        """Replay a measured D-pad segment without inventing collision facts."""
        if getattr(self, "fixed_route_id", None) != route_id:
            self.fixed_route_id = route_id
            self.fixed_route_index = 0
        index = getattr(self, "fixed_route_index", 0)
        if index >= len(actions):
            return None
        direction = actions[index]
        self.fixed_route_index = index + 1
        return self._route_move(direction)

    def _route_text(self):
        """Clear whatever is holding the input, alternating B and A.

        A advances dialogue; it does **not** close a menu — on the START menu
        it opens a submenu instead, so the box never goes away. Two trainers
        stood on Route 1 and Route 3 for thousands of steps in front of a menu
        that only B could close, while the route pressed A forever. B also
        advances text in Gen I, so leading with it is safe; A still gets its
        turn for the prompts that need a confirmation.

        Whatever it presses, the failure must not be read as a wall: text and
        walls look identical from outside, and guessing wrong writes a
        permanent lie into knowledge every trainer shares.
        """
        self.route_last_issue = "text"
        presses = getattr(self, "route_menu_presses", 0)
        return (
            WindowEvent.PRESS_BUTTON_B if presses % 2 == 0
            else WindowEvent.PRESS_BUTTON_A
        )

    def _get_typing_sequence(self, name):
        """
        Generates a sequence of inputs to type the given name on the Gen 1 keyboard.
        Assumes starting position is 'A' (0,0).
        Layout (9 cols):
        A B C D E F G H I
        J K L M N O P Q R
        S T U V W X Y Z
        """
        seq = []
        curr_x, curr_y = 0, 0
        
        grid = {
            'A':(0,0), 'B':(1,0), 'C':(2,0), 'D':(3,0), 'E':(4,0), 'F':(5,0), 'G':(6,0), 'H':(7,0), 'I':(8,0),
            'J':(0,1), 'K':(1,1), 'L':(2,1), 'M':(3,1), 'N':(4,1), 'O':(5,1), 'P':(6,1), 'Q':(7,1), 'R':(8,1),
            'S':(0,2), 'T':(1,2), 'U':(2,2), 'V':(3,2), 'W':(4,2), 'X':(5,2), 'Y':(6,2), 'Z':(7,2)
        }
        
        for char in name.upper():
            if char not in grid:
                continue
                
            target_x, target_y = grid[char]
            
            # Move Y
            dy = target_y - curr_y
            if dy > 0:
                for _ in range(dy):
                    seq.append((WindowEvent.PRESS_ARROW_DOWN, 10))
                    seq.append((WindowEvent.RELEASE_ARROW_DOWN, 10))
            elif dy < 0:
                for _ in range(abs(dy)):
                    seq.append((WindowEvent.PRESS_ARROW_UP, 10))
                    seq.append((WindowEvent.RELEASE_ARROW_UP, 10))
            
            # Move X
            dx = target_x - curr_x
            if dx > 0:
                for _ in range(dx):
                    seq.append((WindowEvent.PRESS_ARROW_RIGHT, 10))
                    seq.append((WindowEvent.RELEASE_ARROW_RIGHT, 10))
            elif dx < 0:
                for _ in range(abs(dx)):
                    seq.append((WindowEvent.PRESS_ARROW_LEFT, 10))
                    seq.append((WindowEvent.RELEASE_ARROW_LEFT, 10))
            
            # Press A
            seq.append((WindowEvent.PRESS_BUTTON_A, 10))
            seq.append((WindowEvent.RELEASE_BUTTON_A, 10))
            
            curr_x, curr_y = target_x, target_y
            
        return seq
