# PokeAI 2026 — handoff canônico

Última atualização: **2026-08-06 (Europe/Madrid)**.

Este documento registra o estado executável do projeto. Progresso só é
considerado real quando confirmado na RAM de Pokémon Blue e persistido no save.

## Continuar daqui (2026-08-06, fim do dia)

**Objetivo da próxima sessão: cada quest em menos passos, e o ciclo de morte
tratado como ciclo.** Morrer não é um tropeço no meio do caminho — é um
recomeço a partir do Centro registrado. Quem mistura os dois ensina o desvio
como se fosse a rota, e aí o erro vira regra.

### Onde os dois estão

| Treinador | Posição | Quests | Observação |
|---|---|---|---|
| AARON | Mt. Moon / Rota 4 | 8, com a insígnia do Brock | atravessa a caverna; dois Pokémon desmaiados |
| BARON | Rota 2, rumo à Floresta | 5 | destravado do vaivém do Centro de Viridian |

Os saves de referência ficam versionados: `states/viridian-passed-AARON.state`
e `-BARON.state`. Carregue um deles em vez de replayar uma hora de jogo.

### As três ferramentas de diagnóstico

```bash
python3 blue-agents/tools/stuck_report.py          # por que travou, com o motivo
python3 blue-agents/tools/mine_trails.py           # publica a melhor travessia conhecida
python3 blue-agents/tools/probe_route.py <state>   # o que é alcançável a partir de um save
```

`stuck_report.py` lê `trainers/<AGENTE>/logs/stuck.jsonl`, escrito sozinho
quando o treinador passa 30 decisões preso em poucos tiles. Traz posição e
alvo, direções recusadas **com o motivo** (tileset, gente, porta, fronteira,
esbarrão), passos sem encurtar distância, o que o mapa acumulado conhece e se
existe caminho até o alvo. Foi ele que apontou os dois últimos consertos.

`mine_trails.py` varre `archives/` e `trainers/`, acha os trechos em que o
QuestGraph confirmou a quest na RAM — caminhos que **chegaram** — apaga os
laços e publica a melhor de cada em `knowledge/routes/`. Critério: cobertura
primeiro, tamanho depois. E **corta tudo o que veio antes da última morte no
trecho**, justamente para não ensinar o desvio da derrota como rota.

### O que atacar, na ordem

1. **Menos passos por quest.** As trilhas mineradas hoje têm 4 a 15 pontos
   porque o log só grava coordenada quando acontece um evento. Uma trilha densa
   (uma posição por passo, gravada durante uma travessia limpa) daria caminho
   fechado em vez de âncoras esparsas. O gravador já existe em
   `src/route_trails.py`; falta persistir a travessia inteira quando a quest é
   confirmada.
2. **Ciclo de morte explícito.** Hoje o whiteout é detectado
   (`death` no log) mas nada separa "tentativa 1" de "tentativa 2". Numerar o
   ciclo e gravar a trilha por ciclo deixa medir: quantos passos custou cada
   tentativa, e qual delas virou a rota publicada.
3. **Treinar antes de entrar.** Não existe nó de treino: nível sobe por
   acidente, nas batalhas do caminho. Um predicado `party_max_level >= X` antes
   da Floresta e antes de Mt. Moon evitaria metade das mortes.

### Regras de cura, como ficaram

| Situação | Limite | Ação |
|---|---|---|
| Centro no caminho (mapas 1, 2, 15) | HP total < 70% | para e cura |
| Viajando machucado | HP total < 50% | foge de selvagem |
| Emergência em qualquer lugar | HP total < 20% | vai ao Centro |
| **Dentro** de um Centro | qualquer coisa faltando | cura tudo |

A última linha é recente e não é detalhe: com o limite de emergência lá dentro,
um time a 55% entrava, não curava, saía — e a regra de 70% que o trouxe mandava
voltar. Entrar e sair, sem fim.

## Marco validado: Viridian passada

Definido em 2026-08-06. É o ponto a partir do qual a jornada anda sozinha, do
jogo novo até dentro da Floresta de Viridian, sem intervenção:

| Etapa | Confirmação |
|---|---|
| sair de casa, laboratório, escolher Bulbasaur | `start`, `oak_event` |
| encomenda entregue ao Oak | `parcel_event` |
| Poké Bolas compradas no Mart | `buy_pokeballs` |
| atravessar Viridian e entrar na Floresta | `route_2_nav` |

Estado guardado em `states/viridian-passed-AARON.state` e
`states/viridian-passed-BARON.state` — AARON com quatro Pokémon dentro da
Floresta em `(31,24)`, BARON com dois em `(25,25)`. São referência para testar
o trecho seguinte sem replayar uma hora de jogo: carregue um deles em vez de
começar do zero.

O que ainda não é marco: a travessia da Floresta até Pewter
(`viridian_forest_nav`).

## A regra que explica quase todos os travamentos

Todo congelamento desta jornada teve a mesma forma: **algo guardado na memória
do processo no lugar de perguntado ao cartucho**, ou **uma sequência de teclas
tocada às cegas**. Vale como critério de revisão para qualquer código novo aqui:

| Sintoma no jogo | O que estava guardado | O que responde de verdade |
|---|---|---|
| Sai do Centro e volta na mesma hora | flag "já curei", uma vez por jornada | HP total da party |
| Cura, toma um arranhão, volta | "falta HP" (29/30 conta) | menos de 20% do HP **total** do time |
| Some da rota e nunca volta | `_fixed_route`, lista de teclas | rota andada com colisão lida |
| Fica na porta piscando | warp tratado como tile comum | porta é destino, nunca atalho |
| Trilha quicando entre 2 tiles | trilha recalculada a cada passo | plano mantido, refeito só a 12+ tiles |
| Aperta DOWN eternamente na luta | posição do menu decorada | linha/coluna lidas; se nada mudou, `B` |
| Joga bola e nada acontece | slot da bola decorado | id do item sob o cursor |
| Pokémon cai e ninguém entra | espera o aviso "Use next POKéMON?" | a lista da equipe se identifica sozinha (`0xCC28`) |
| Atravessa a fronteira sem parar | conexão de mapa tratada como tile comum | volta retida no tile de chegada |

`_fixed_route` sobrou apenas onde a sequência é curta e verificada. Nenhuma
delas navega mais entre mapas.

## Andar em círculo: as três causas, medidas

Registrado em 2026-08-06 depois de uma tarde inteira de "estão presos nos mesmos
tiles". Não era uma coisa só, eram três, e todas se escondiam atrás do mesmo
sintoma. Medidas no mesmo save, 2000 passos:

| | antes | depois |
|---|---|---|
| tiles distintos | 45 | **123** |
| mapas visitados | 3 | **5** (chega na Floresta) |
| tile mais repetido | **654 vezes** | 9 vezes |

**A fronteira entre dois mapas não é uma porta.** Rota 2 ↔ Viridian é uma
*conexão*, não um warp: não aparece em `0xD3AF`, então a regra "porta é destino,
nunca atalho" não a cobria. O bot atravessava e voltava a cada passo — 2176
trocas de mapa em cinco minutos. Agora, ao atravessar, o passo de volta fica
retido por `ENTRY_BLOCK_STEPS` enquanto ele estiver parado no tile de chegada;
sair dele e voltar continua permitido.

**A trilha puxava para trás.** `waypoints_from` rejunta pelo ponto mais próximo,
e um passo depois de entrar num mapa o ponto mais próximo é o começo da perna —
atrás. O bot subia um tile e a trilha o mandava descer, 654 vezes. Ponto que
acabou de ser pisado é ponto gasto: ao rejuntar, os pontos que estão na memória
recente são descartados do começo do plano.

**Explorar sequestrava o último passo.** A regra "repetiu tile, mire no
desconhecido" é o que tira o bot de trás de um muro — e era exatamente o que o
fazia dar as costas para a porta do portão, porque ele já tinha cruzado aquele
tile várias vezes. Agora alvo a um tile de distância se resolve andando até ele,
sem plano nenhum, e a fronteira só entra em cena a partir de
`FRONTIER_MIN_DISTANCE` tiles.

O plano de terreno também deixou de ser recalculado a cada passo: uma vez
traçado, é seguido até acabar, até o objetivo mudar, ou até o tile que ele quer
pisar se revelar parede.

## Cura, morte e checkpoint

Definido com o operador em 2026-08-06:

- **Curar** vale a viagem somente quando o time está abaixo de
  `HEAL_HP_FRACTION = 0.20` do HP somado. PP esgotado ou ausência de golpe de
  dano não cria uma segunda ida ao Centro; um Caterpie desmaiado atrás de um
  líder inteiro também não é emergência.
- **Morrer não rebobina.** O whiteout é parte do jogo: o cartucho já devolve o
  treinador ao Centro, e nada recarrega estado por causa disso. O fallback que
  voltava para `brock_defeated`/`parcel_delivered` foi removido — ele apagava
  uma hora de jogo em silêncio.
- **Checkpoint só existe em um lugar:** dentro de um Centro Pokémon, com a
  party inteira curada (`center_<mapa>.state`). Depois de um whiteout, o estado
  pós-morte no Centro também pode substituir esse checkpoint. É o único ponto
  de onde uma corrida travada pode ser retomada sem trapacear.

## Navegação: o cartucho responde, não adivinhamos

Esta é a mudança mais importante do projeto e a que mais custou a chegar.

Durante meses a navegação foi **aprendizado por esbarrão**: apertou uma direção,
não saiu do lugar, grava a aresta como parede. Funciona, e falha de um jeito
específico e fatal — um NPC parado é indistinguível de parede naquele passo, e
gente virava geometria permanente, em conhecimento compartilhado por todos os
treinadores. Em cima disso foram crescendo camadas para compensar: esquecer o
tile quando ele se contradizia, duvidar enquanto havia caixa de texto, proibir
voltar para quebrar o vaivém que o esquecimento criava, anistia por tile,
reinício de missão. Cada camada consertava a de baixo e inventava um jeito novo
de travar.

O motivo de tudo isso existir era **uma informação ausente**: quais tiles são
caminháveis. O cartucho responde direto, e barato:

| Fonte | Endereço | O que dá |
|---|---|---|
| lista de tiles caminháveis do tileset | ponteiro em `0xD530` | terreno, verdade permanente |
| mapa de tiles da tela (20x18) | `0xC3A0` | o que está em volta |
| tabela de sprites (16 bytes cada) | `0xC100` | onde estão as pessoas, agora |

O ponteiro de colisão aponta para o **banco 0**, sempre mapeado — era isso que
fazia a opção parecer cara ("exige troca de banco"). Não exige. E o PyBoy lê ROM
por banco (`memory[banco, endereço]`) se algum dia for preciso.

`src/tile_collision.py` junta as três leituras e responde quais das quatro
direções estão bloqueadas e **por quê**: `terrain` ou `sprite`. A distinção é o
ponto inteiro — terreno é permanente, gente anda embora.

Conferido contra o save real do CARON, parado havia horas na Rota 3: a leitura
diz `{U: terrain, D: sprite, R: sprite}` e a esquerda livre. Exatamente o que o
operador descrevia como "NPC invisível".

### A porta não está na lista de tiles caminháveis

Corrigido em 2026-08-06. Os quatro treinadores acabaram de escolher o starter e
pararam sobre a porta do laboratório, em `(5,11)` do mapa 40, sem sair. Não era
diálogo nem NPC: o tile da porta **não pertence ao tileset caminhável**, então
`blocked_directions()` respondia `{D: terrain}` e o seguidor de rota nunca
tentava descer. A ROM aceita o passo — um `DOWN` avulso no save travado sai
direto para Pallet.

Warps são invisíveis à colisão de tileset, mas o próprio mapa os declara:

| Fonte | Endereço | O que dá |
|---|---|---|
| número de warps do mapa | `0xD3AE` | quantas portas |
| tabela de warps (4 bytes: y, x, destino, mapa) | `0xD3AF` | onde estão |

`src/tile_collision.py` lê a tabela e trata tile de warp como caminhável. Em
cima de um warp, terreno **não tem voto** — só sprite ainda bloqueia, porque ali
a saída é justamente o passo que o tileset chama de parede.

Validado no cartucho a partir dos saves travados: os quatro saíram do
laboratório e AARON/BARON/DARON chegaram a Viridian; CARON estava em Pallet no
fim do bloco.

### Saída norte de Viridian e o velho

Corrigido em 2026-08-06. A rota da cidade usava o waypoint mais próximo como
se fosse sempre o próximo waypoint. Depois de um whiteout ou de um processo
novo, `(17,3)` escolhia `(17,4)` e andava para sul; no lado leste, `(27,5)`
repetia o mesmo contorno. A sonda confirma que `(27,5) -> (17,0)` existe em 15
passos.

O trecho norte agora tem a perna explícita `(17,4) -> (17,0) -> (17,-1)` e
possui um id separado da perna sul. Ao chegar em `(17,4)`, o controlador só
inicia a conversa se a colisão ao vivo disser `sprite`: vira para o sprite,
pressiona `A` enquanto a caixa real estiver aberta e só libera a rota quando a
caixa fecha e o bloqueio deixa de existir. Não há flag sintética nem conclusão
por quantidade de botões. Se o NPC andar entre a leitura e o próximo tick, o
diálogo é cancelado e o bot segue pelo corredor.

### Checkpoint sem rebobinar morte

`current.state` deixou de ser autosave periódico. Ele só é escrito junto de
`checkpoints/center_<mapa>.state`, depois de uma cura confirmada na RAM dentro
de um Centro Pokémon. Um whiteout confirmado que já devolveu o time inteiro a
um Centro também grava o estado **pós-morte**, para o bloco seguinte não
carregar a posição anterior à derrota. O resume só aceita `current.state` com
o manifesto/hash criado na mesma gravação; estado antigo, órfão ou divergente
é ignorado. Não existe fallback para outro `.state`.

Fechamento do processo, sinal manual e periodicidade não criam mais estados em
mapas ou batalhas. A morte continua sendo evento real do cartucho; não há
fallback para `brock`, `parcel`, `oak` ou qualquer marco antigo.

### O que sobrou de `_follow_route`

Um escolhedor de passo, em `src/scripted_agent.py`:

1. menu ou texto aberto: alterna `B` e `A` (o `B` fecha menu **e** avança texto;
   `A` sozinho abre submenu e nunca fecha — foi o que prendeu dois bots por
   milhares de passos);
2. anda na direção do waypoint, eixo mais longo primeiro;
3. lado ocupado: usa o outro eixo;
4. se quem bloqueia é **gente**, espera alguns passos antes de contornar —
   pessoa anda sozinha, parede não;
5. troca de mapa grava a porta em `knowledge/maps/warps.json`, compartilhada.

Removidos por não serem mais necessários: `src/collision_memory.py`, colisão
aprendida, suspeitas transitórias, anistia por tile, regra de contradição,
anti-oscilação. As 910 paredes que o arquivo tinha acumulado foram descartadas.

**Regra para quem mexer aqui:** não volte a inferir geometria de um passo que
falhou. Se algo parece parede e a leitura diz que não é, o obstáculo é outra
coisa — gente, script, texto — e a resposta certa é ler mais, não gravar mais.

### Detector de loops da interface

`dashboard-react/src/workers/loopDetector.worker.ts` observa somente os estados
que o relay já transmite (`mapa`, coordenadas e quest). Três repetições do mesmo
ciclo podem publicar um pedido de diagnóstico; o worker não envia D-pad, não
escreve RAM e o backend não aplica replan automático durante quests. O follower
de quest voltou a um passo determinístico por waypoint, com desvio perpendicular
simples. O caso conhecido da porta do Mart preserva a origem `mapa 42` para
escolher o portão norte, sem proibir backtracking em outras rotas.

## Dois treinadores, o mesmo trabalho: achar o caminho

Redefinido em 2026-08-06. Antes disso os papéis eram estilos de jogo; o que
faltava era o mapa, não variedade. Agora os dois slots (AARON completista,
BARON rushador) começam com **Bulbasaur**, capturam pelo caminho e vão até o
fim da história. Os dois gravam trilha, os dois leem a do outro: quem confirmar
a quest primeiro publica, e o outro entra nela pelo ponto mais próximo.

### O mapa que o cartucho mostra, guardado

`src/map_memory.py` existia desde a sessão anterior e **nunca tinha sido
ligado**. Agora `_follow_route` guarda, a cada passo, a tela de terreno lida em
`TileCollision.terrain_grid()` e planeja por busca em largura sobre tudo o que
já viu daquele mapa (`knowledge/maps/terrain.json`, compartilhado).

Uma tela resolve desviar de uma árvore e não resolve sair de um bolsão cuja
saída está fora dela — foi isso que prendeu os dois na Floresta, cada tile
parecendo o melhor caminho para uma âncora que nenhum alcançava. Terreno não
muda, então guardar não é chute; sprites ficam de fora de propósito e são lidos
ao vivo.

**Porta é destino, nunca atalho.** Planejar *através* de um warp foi o que deu
ao Mart de Viridian aquele efeito de gravidade: o caminho até uma âncora duas
casas adiante cruzava a soleira, o bot entrava, saía no capacho e replanejava
igual. No planejador, todo warp que não seja o destino entra como bloqueado.

### Fugir quando não há como ganhar

Sem nenhum golpe de dano com PP, batalha selvagem vira Growl e Struggle: não dá
para ganhar, demora a perder, e o mato devolve outro encontro no passo seguinte.
`_next_escape_action` lê o mesmo menu 2x2 e escolhe RUN, e a quest segue para o
Centro — na Gen I só o Centro devolve PP. Batalha de treinador não tem saída;
essas continuam sendo lutadas.

`_party_needs_healing` agora responde somente à regra operacional nova: a soma
do HP atual fica **abaixo de 20%** da soma do HP máximo do time. Dano ausente ou
PP esgotado não dispara uma ida ao Centro; o controlador de batalha pode fugir
de selvagem sem golpe ofensivo, mas cura é decisão de HP.

### Medido no cartucho, a partir dos saves travados

| Treinador | antes | depois |
|---|---|---|
| AARON, Floresta `(8,30)` | 10 tiles, parado | **91 tiles**, saiu para Viridian |
| BARON, Floresta `(18,32)` | 1 tile, parado | **186 tiles**, atravessou 4 mapas |

## Histórico: dois papéis, guia e seguidor

Definido em 2026-08-06. O roster tem **2 slots**: AARON é `route_role=guide` e
BARON é `follower`.

**AARON anda a rota como ela está desenhada.** Lê colisão e warp do cartucho
para não andar contra parede, e espera quando quem bloqueia é gente — nada além
disso. Sem trilha de ninguém, sem desvio local, sem replanejamento. Se a rota
estiver errada, ele trava; travar **é o resultado**, e é a única forma de o
desenho errado aparecer em vez de ser encoberto por um contorno que ninguém
mediu.

**BARON pode tudo o que AARON não pode**, e começa do que AARON provou.

| Caminho | Responsabilidade |
|---|---|
| `src/route_trails.py` | gravar, publicar e reentrar nas trilhas |
| `blue-agents/knowledge/routes/<quest>.json` | trilha publicada, comum aos dois |

A trilha é gravada enquanto o guia joga e só é **publicada quando o predicado
da quest é confirmado na RAM** (`hybrid_agent`, no mesmo ponto em que o nó é
marcado como concluído). Um seguidor nunca herda um caminho que não chegou.
Publicação preserva a mais curta já confirmada.

O arquivo guarda os pontos de virada, separados em pernas por mapa — um
waypoint só significa alguma coisa dentro do mapa em que foi medido:

```json
{"quest": "route_2_nav", "recorded_by": "AARON",
 "legs": [{"map": 1, "points": [[29, 20], [16, 20], ...]}, {"map": 13, ...}]}
```

**Reentrada é recalculada a cada passo**, pelo ponto mais próximo entre todas as
pernas do mapa atual. É também a resposta inteira para morrer: o whiteout joga o
bot para trás, o ponto mais próximo passa a ser um anterior, e ele segue dali
sem que ninguém escreva rota de recuperação. Empate entre pernas vai para a mais
tardia — o mesmo tile é cruzado na ida e na volta, e a volta é o que ainda falta.

Validado no cartucho: AARON concluiu `route_2_nav` e publicou
`knowledge/routes/route_2_nav.json` (18 waypoints, 3 pernas), com a trilha
disponível para BARON no mesmo instante.

**Cuidado com `--agents N`.** `train_hybrid.py` redimensionava o roster pelo
número pedido: o comando de validação curta deste documento (`--agents 1`)
aposentou BARON, CARON e DARON e entregou os slots a EARON, FARON e GARON.
Agora rodar menos agentes é uma corrida menor, não um roster menor; crescer
continua sendo ato explícito (`run_journeys.py --slots`).

## Estado dos quatro treinadores

Reiniciados do zero em 2026-08-05, um arquétipo cada
(`blue-agents/archetypes.py`, campo `archetype` no roster):

| Bot | Arquétipo | Inicial | Onde estava na última verificação |
|---|---|---|---|
| AARON | Completista | Bulbasaur | Viridian Forest (2,0), rumo a Pewter |
| BARON | Rushador | Bulbasaur | Viridian Forest (2,0), rumo a Pewter |
| CARON | Construtor de time | Squirtle | Viridian Forest (1,0), rumo a Mt. Moon |
| DARON | Fogo e dragão | Charmander | Viridian Forest (1,0), terminando a travessia |

O checkpoint atual é a Floresta de Viridian; os quatro chegaram nela após cura
confirmada no Centro de Viridian e seguem em velocidade de treino para Pewter.

Em 2026-08-06 as jornadas anteriores foram preservadas em
`archives/manual-reset-20260806T084317Z/` a pedido do operador. As quatro novas
jornadas começaram em `states/init.state`; AARON é o slot `route_role=guide` e
BARON/CARON/DARON são `follower`. Todos executam o mesmo catálogo determinístico
de quest e não usam PPO/roaming enquanto existe executor. Na última verificação,
os quatro chegaram ao topo da Floresta, sem mortes; havia apenas um supervisor
ativo depois da limpeza dos órfãos.

## Política de captura: por que o time cresce

Ordem de decisão em `_capture_policy`, do mais forte ao mais fraco. As duas
primeiras regras foram acrescentadas em 2026-08-05 depois de um bot lançar
Poké Bolas num Kakuna com `17/17` HP até o próprio starter cair a `2` HP:

| # | Regra | `reason_code` |
|---|---|---|
| 1 | Ativo abaixo de `SELF_PRESERVATION_HP` (35%) → lutar | `self_preservation` |
| 2 | Alvo acima de `CAPTURE_HP_THRESHOLD` (50%) → reduzir HP antes | `soften_before_capture` |
| 3 | Espécie já na Pokédex → nunca capturar | `duplicate_species` |
| 4 | Vaga livre + espécie nova → capturar | `party_slot_new_species` |
| 5 | Time cheio: personalidade decide | `collector_new_species`, `team_upgrade` |
| 6 | Nada disso | `training_value` |

Shiny continua acima de tudo. Taxas de captura da Gen I escalam com HP perdido,
então lançar numa vida cheia é quase bola jogada fora **e** um turno grátis para
o selvagem. Aplicar status (sono, paralisia) multiplicaria mais ainda a taxa —
está registrado como trabalho futuro, ainda não implementado.

As regras 3 e 4 chegaram antes, quando dois treinadores ficaram permanentemente
com um único Pokémon. Havia três causas somadas:

1. Os ramos de captura exigiam `collector >= 55` ou `meta_score >= 45`. Os
   traços são sorteados por execução; BARON tirou 42 e CARON 52/41, então
   nenhum dos dois alcançava os limiares — CARON não conseguia capturar nada.
2. `upgrade_candidate` julgava só por nível. Um starter nível 9 faz todo
   Caterpie da Floresta parecer pior do que o time atual.
3. `_run_buy_pokeballs` comprava **uma** Poké Bola, e uma tentativa falha
   esgotava o inventário.

A regra 4 ignora personalidade de propósito: com menos de `PARTY_TARGET = 6` no
time, uma vaga vazia é fraqueza maior que qualquer preferência sorteada.
Personalidade volta a mandar só com o time completo.

`STRATEGIC_CAPTURE_VALUE` passou a valer pela **linha evolutiva**, não pela
forma encontrada no mato: Metapod vale 70 porque Butterfree segura as primeiras
horas de Kanto. O que não estiver na tabela continua em 50.

### Lançar a bola: menu lido, nunca decorado

Corrigido em 2026-08-06 depois de BARON encontrar um Pikachu selvagem com sete
Poké Bolas na mochila e não lançar nenhuma. A política estava certa
(`capture_intent`, `team_upgrade`); quem falhava era a execução.

O menu era um **plano cego**: uma lista de teclas, uma por passo. Texto de
batalha come tecla. Com `"Nothing happened!"` ainda na tela o `DOWN` não ia a
lugar nenhum, o plano acabava mesmo assim, e o `A` que era da mochila caía em
**FIGHT**. Sete tentativas, nenhuma bola gasta, e todas registradas como "menu
não confirmou o uso da Poké Bola" enquanto o bot atacava calado.

O menu de batalha não é um índice, são dois bytes:

| Fonte | Endereço | O que dá |
|---|---|---|
| linha do cursor | `0xCC26` | `0` FIGHT/PKMN, `1` ITEM/RUN |
| coluna do cursor | `0xCC25` | `9` esquerda, `15` direita |
| mochila | `0xD31D` conta, `0xD31E` pares id/quantidade | o que existe e onde |

A coluna é também o único sinal honesto de que **o menu está desenhado** — com
texto na tela ela lê outra coisa (`5`). Então: coluna inválida → `B`, que
avança texto e nunca escolhe um golpe por acidente; menu desenhado → linha e
coluna dizem para onde ir; `A` só com ITEM confirmado sob o cursor.

Dentro da mochila, a linha é como chegar e **o id do item é o que confirma ter
chegado**: a posição da bola muda a cada item pego ou gasto, e uma tecla comida
deixa o cursor uma linha fora. Se a linha certa tiver o item errado, o
controlador desiste do turno em vez de lançar o que estiver ali. A bola em si é
escolhida por id (`_select_capture_ball`), Poké primeiro, Master primeiro
quando o encontro é candidato a shiny.

Validado no cartucho, rodando o próprio `_next_capture_action` sobre o save do
BARON em batalha: **7 → 6 bolas**, Poké Bola lançada no Metapod.

### Trocar de Pokémon depois de um desmaio

Corrigido em 2026-08-06, com o save real de uma luta de treinador.

Em batalha de treinador a lista da equipe abre **direto**, sem o aviso "Use next
POKéMON?" — então esperar pelo aviso nunca funcionaria. Pior: a lista e o menu
2x2 compartilham os bytes de cursor, e o controlador lia a coluna, via `0`,
concluía "isto não é menu" e apertava `B`. Em troca forçada `B` não faz nada. O
AARON perdeu uma luta assim, com dois Pokémon inteiros no banco.

`_party_menu_open()` reconhece a lista pela própria forma: última linha
selecionável igual ao último Pokémon (`0xCC28 == party-1`) e cursor na coluna
zero. Validado no cartucho: `DOWN`, `A`, e o Metapod entra com 23 HP.

A ordem entre controladores também mudou: **trocar vem antes de fugir**. Líder
caído não é batalha que se abandona, é batalha parada esperando alguém entrar; a
fuga se recusa enquanto houver troca pendente.

### Golpe de status: qual, e quantas vezes

O controlador já ignorava golpes de status enquanto houvesse ataque com PP —
Growl só aparece quando nenhum ataque tem PP. O que faltava era escolher entre
os de status: Leech Seed drena sozinha todo turno e vale **uma** vez (marcada ao
usar, zerada a cada batalha, nunca em Pokémon do tipo Grass, que é imune);
sono e paralisia valem uma; Growl e Tail Whip com o atributo já no fundo não
valem nenhuma. Tabela em `STATUS_MOVE_PRIORITY`.

### `MANUAL: THROW_BALL`: uma ordem, não uma sequência de teclas

O operador escreve uma linha no arquivo de tarefa do treinador:

```bash
echo "MANUAL: THROW_BALL" > blue-agents/tasks/BARON.txt
```

A ordem vence a política — é para isso que se pede à mão — mas não vence o
cartucho: o menu continua sendo operado de verdade, com a bola escolhida por id
na mochila real. Fora de batalha a ordem **fica de pé** e espera o próximo
encontro em vez de virar uma tecla solta. Ela é consumida quando a bola sai da
mochila (`manual_order_completed`), e o treinador volta à quest ativa — deixada
de pé, ela esvaziaria a mochila ao longo das batalhas seguintes.

Não existe atalho de item no Game Boy: em Gen I o menu **é** a interface. O que
existe é escolher uma vez e deixar o executor tocar os botões reais. Escrever o
uso do item direto na RAM seria forjar o resultado — a taxa de captura da Gen I
é calculada pela rotina do item, a partir de HP, status e espécie.

### Estoque de Poké Bolas

`POKEBALL_TARGET` em `src/scripted_agent.py`, padrão **8**, ajustável por
`POKEAI_POKEBALL_TARGET`. Comprado **uma unidade por vez com releitura do
inventário entre cada compra**: o Codex registrou que o seletor de quantidade
debitava dinheiro sem entregar o lote, então a compra repetida é o caminho
verificado. `_can_afford_another_ball` lê o dinheiro em BCD
(`0xD347..0xD349`) para parar por falta de grana em vez de travar.

O predicado do nó virou `pokeballs_stocked`, um tipo novo em `quest_graph.py`:

```python
state.pokeballs >= minimum or not state.can_afford_pokeball
```

O segundo ramo é o que evita o deadlock. Um treinador que perdeu metade do
dinheiro num whiteout não consegue mais atingir o alvo, e sem essa saída ficaria
preso no nó da loja para sempre.

**Pendente:** o `buy_pokeballs` só sabe voltar ao Mart de Viridian, com rotas
para os mapas 40, 0, 12 e 1. Reabastecer a partir do norte é impossível — a
Route 2 é dividida em duas metades sem ligação direta, e a sonda confirmou que
de `(3,11)` só 86 tiles são alcançáveis (`x 0..9, y 0..11`). Um controlador de
"reabastecer no Mart mais próximo" ainda não existe.

### Cuidado ao mudar um predicado

A conclusão é *sticky* em `journey.json`. Um treinador que já concluiu o nó sob
a definição antiga não o reexecuta. Remover o id de `completed_quests` reabre o
nó — mas só faça isso se o executor conseguir chegar lá a partir da posição
atual, senão o bot fica girando. Foi exatamente o que aconteceu ao reabrir
`buy_pokeballs` de um treinador que já estava na Route 2 norte.

## Travamento por PP zerado (corrigido)

Registrado e corrigido em 2026-08-05. Foi o que prendeu BARON e CARON na
Floresta de Viridian por horas, e a causa não era navegação:

```
BARON | Tackle PP 0 | Growl 40 | Leech Seed 10
CARON | Tackle PP 0 | Tail Whip 30 | Bubble PP 0
```

Os golpes de dano zeraram. `simple_battle.py` filtra golpes sem PP ao montar
`candidates`, mas quando a lista ficava vazia `best_move_idx` permanecia em
**0** — exatamente o golpe exausto. O jogo reabria a caixa "no PP" a cada
confirmação, para sempre.

A Geração I só substitui por Struggle quando **todos** os golpes acabam. Com um
golpe de status ainda com PP, o menu continua aberto esperando uma escolha
válida. Agora, sem candidato ofensivo, o controlador cai para qualquer golpe que
ainda tenha PP; se nenhum tiver, confirma o menu e deixa o cartucho aplicar
Struggle.

Consequência para a jornada: PP só se recupera em Centro Pokémon. Sem a rotina
de cura (tarefas #2 e #4), um bot fica sem dano e depende de desmaiar para
restaurar — o whiteout é hoje o único mecanismo de recuperação de PP.

## Navegação: busca em largura sobre colisão aprendida

Registrado em 2026-08-05, substitui o "BUG ABERTO" descrito na seção seguinte.

`_follow_route` não persegue mais o waypoint em linha reta. A cada passo ele
planeja um caminho **do tile onde o bot realmente está** até a âncora seguinte,
por busca em largura sobre os tiles caminháveis. Os waypoints continuam sendo
âncoras de rota; deixaram de ser o único meio de navegar. Sair da linha parou de
ser um estado sem retorno, porque o replanejamento parte da posição atual.

A colisão vem do próprio jogo, aprendida enquanto joga. Não existe leitura de
colisão no projeto e as duas alternativas eram caras: `wTilesetCollisionPtr`
(`0xD530`) exige lidar com troca de banco de ROM, e `tools/probe_route.py`
descobre paredes ramificando save states — inviável a cada passo. Mas o agente
já produzia o dado e o jogava fora: apertou uma direção e não saiu do lugar,
logo aquela aresta é bloqueada.

| Caminho | Responsabilidade |
|---|---|
| `src/collision_memory.py` | conjunto de arestas bloqueadas + BFS |
| `blue-agents/knowledge/maps/collision.json` | mapa aprendido, comum a todos |

O arquivo é **compartilhado entre treinadores**, não por treinador: onde ficam
as paredes não depende de quem esbarra nelas. É a versão honesta de "um bot
guiando os outros" — dividem o mapa, não um canal de comando, que continua não
existindo (`HiveMind` só é consultado em `EXPLORE`). A escrita faz
read-modify-write, então duas jornadas simultâneas somam o que aprendem em vez
de sobrescrever uma à outra. Um treinador que nunca pisou na Floresta já começa
com as 300+ arestas que os outros pagaram para descobrir.

Regras do controlador:

- aresta desconhecida conta como **livre**. O primeiro plano num mapa novo é a
  linha reta, e cada colisão o estreita;
- sem deslocamento por 4 passos: o primeiro ciclo aperta `A` (diálogo e
  transição de mapa ignoram o D-pad), os seguintes gravam
  `(mapa, x, y, direção)` como bloqueado e o BFS já desvia na chamada seguinte;
- **atravessou uma aresta bloqueada → esquece o bloqueio.** Um NPC parado é
  indistinguível de parede enquanto está lá; sem esse esquecimento a memória
  planejaria para sempre em volta de alguém que já saiu;
- troca de mapa replaneja sozinha: a chave do plano inclui o mapa;
- BFS limitado a uma caixa de `margin=15` em volta de origem e destino e a 6000
  nós. Sem caminho dentro da caixa, cai no passo por eixo antigo — é o que
  mantém o último waypoint "um tile além da borda" funcionando;
- empate de caminho expande na ordem `U, R, L, D`. "Sul por último" é
  deliberado: várias rotas entram por um warp na borda sul, e preferir sul ali
  devolvia o bot ao mapa anterior.
- escrita atômica com `os.replace`; arquivo corrompido é ignorado, não derruba a
  jornada (o bot reaprende andando).

`trainers/` é ignorado pelo git: `collision.json` é estado de execução, cresce
sozinho a cada corrida e não é versionado.

### O plano é guardado, não recalculado a cada passo

A primeira versão refazia o BFS toda chamada e **um bot ficou 800 passos indo e
voltando entre dois tiles livres**, sem gravar uma única aresta nova. Com meio
muro conhecido, o desvio pelo norte e o pelo sul custam o mesmo; o desempate
mudava conforme o tile de origem e o bot alternava entre os dois — nunca batia
em nada, portanto nunca aprendia nada. Agora o plano é mantido e seguido tile a
tile; só é refeito quando surge uma colisão nova, quando o objetivo muda ou
quando o bot está fora do corredor planejado.

### Warp atravessado sem querer também é aresta bloqueada

Um warp é **invisível** para a colisão aprendida: pisar numa porta funciona,
logo nada parece bloqueado. Ao sair do ginásio de Brock o bot cai no tile da
porta em Pewter, o plano até a âncora seguinte cruzava esse mesmo tile, e os
dois ficaram quicando ginásio → cidade → ginásio:

```text
m54 [4,13] → m2 [16,18] → m54 [16,17] → m54 [4,13] → …
```

Troca de mapa no meio da rota agora grava `(mapa, x, y, direção)` como
bloqueada, igual a uma parede. **Só as não intencionais:** rotas terminam de
propósito num warp — o último waypoint costuma ficar um tile além da borda — e
marcar essas selaria toda saída de mapa. O critério é o índice do waypoint
perseguido: final = saída legítima, meio da rota = engano.

### Três travas que só aparecem no cartucho

Nenhuma era geometria; todas foram vistas rodando e corrigidas em 2026-08-05.

| Sintoma | Causa | Correção |
|---|---|---|
| Parado em `(3,11)` da Rota 2 norte, centenas de passos, sem aprender nada | `0xCFC4` (menu) preso em `1`; o executor devolvia `A` para sempre e nunca tentava andar | número limitado de `A` e depois anda assim mesmo; com o flag de pé **não grava** aresta, porque aí parede e caixa de texto são indistinguíveis |
| Vaivém na frente do mesmo ledge da Rota 3 | pular desce **duas** casas; o passo "funciona", então nada parecia bloqueado | deslocamento diferente do esperado vira aresta bloqueada — o planejador só modela passo unitário |
| Quique ginásio ↔ cidade | warp atravessado sem querer (ver acima) | transição no meio da rota vira aresta bloqueada |

A sonda foi o que separou controlador de geometria em cada caso:

```bash
cd blue-agents && ../.venv/bin/python tools/probe_route.py \
    ../trainers/BARON/current.state --limit 40
# start=(13, 3, 11) reachable=40 → o tile de cima era caminhável o tempo todo
```

### Validado no cartucho (2026-08-05, `start.py --no-browser`)

Partindo exatamente do save travado, BARON em `(6,30)` e CARON em `(7,30)`:

```text
BARON  (6,30) → aprende o muro em y=30 → (10,32) → (18,33) → (27,25)
       → (1,18) → sai da Floresta → mapa 13 (Rota 2 norte)
CARON  (7,30) → (25,20) → (1,18) → (6,1), a um passo da saída norte
```

Os dois atravessaram a barreira de `y=30` que os prendia, com 44 e 188 arestas
aprendidas no mapa 51. Nenhum waypoint novo foi medido à mão.

BARON completou a travessia, venceu Brock (`badges: 1`) e seguiu; CARON fez o
mesmo trecho depois. Corrigido o quique do ginásio, os dois saíram de Pewter e
estão na **Rota 3 (mapa 14)**, a caminho de Mt. Moon.

O custo da travessia ainda é alto porque cada bot desmaiou uma vez pelo caminho
(`deaths: 1` no bloco anterior) — BARON entrou na Floresta com `1/25` HP, CARON
caiu a `5/48` — e o whiteout devolve o bot a Pallet/Viridian, recomeçando o
percurso. Isso é a lacuna de cura já registrada em "Cura antes da Floresta
(pendente)", não navegação, e é a primeira coisa a resolver agora que dá para
chegar a qualquer porta sem medir waypoints à mão.

## BUG ABERTO (histórico): `_follow_route` não replaneja — a causa raiz

Registrado em 2026-08-05, **corrigido pela seção acima**. Mantido porque explica
por que waypoints medidos à mão nunca resolveram o problema.

O livelock na boca da Floresta (descrito abaixo) foi **confirmado e corrigido**:
o desvio de colisão escolhia `DOWN` primeiro e, em `y=47`, descer é o warp de
volta ao portão. Agora o desvio se inclina para o próximo waypoint. Antes os
bots quicavam em `y=47`; depois da correção atravessam até `y=30`.

Só que isso expôs o problema de verdade. De `(7, 30)` a sonda responde:

```
target=(51, 17, 43)  steps=25  path=RDDRRRRRRRDRRRDDDDDDDDDDL
```

Eles estão **fora da rota**, precisando voltar para sudeste — e param ali. O
motivo é estrutural:

> `_follow_route` persegue waypoints em linha reta, um eixo de cada vez, e não
> tem nenhuma noção de caminho. Quando um obstáculo o tira da linha, ele não
> replaneja: continua mirando o mesmo waypoint, trava de novo, desvia de novo e
> se afasta mais. O desvio deixa de ser correção pontual e vira o piloto.

Isso explica o padrão que se repetiu a jornada inteira — Route 25, Pewter,
laboratório do Oak, agora a Floresta. Cada caso foi resolvido acrescentando
waypoints medidos à mão para aquele trecho específico. É paliativo: qualquer
NPC que ande para um tile diferente recria o problema.

**Correção recomendada:** trocar o passo em linha reta por uma busca em largura
sobre os tiles caminháveis até o próximo waypoint. Waypoints continuam úteis
como âncoras de rota, mas param de ser a única forma de navegar.

O obstáculo é que **não existe leitura de colisão em lugar nenhum do projeto**.
`tools/probe_route.py` descobre paredes ramificando save states — salva e
recarrega o emulador para cada tile testado. Funciona offline; a cada passo do
jogo é inviável.

Duas saídas:

1. **Ler a colisão da RAM.** `wTilesetCollisionPtr` (`0xD530`) aponta para a
   lista de tiles atravessáveis do tileset atual, e a janela de tiles fica em
   `wTileMap`. Dá o grid exato, mas exige lidar com troca de banco de ROM e
   com a diferença entre tile e bloco.

2. **Aprender a colisão jogando** *(recomendado)*. O agente já produz essa
   informação e a joga fora: tentou andar na direção D a partir do tile T e não
   saiu do lugar — logo `T→D` é bloqueado. Guardar isso num conjunto por
   `(mapa, x, y, direção)`, tratar arestas desconhecidas como livres e
   replanejar a cada falha. Não exige engenharia reversa, melhora sozinho a cada
   execução e pode ser persistido por treinador junto do resto da jornada.

A opção 2 também resolve o sintoma que originou tudo isto: como o BFS replaneja
a partir do tile atual, sair da linha deixa de ser um estado sem retorno.

### Regras de comportamento pedidas (dependem da navegação)

Registradas em 2026-08-05, todas bloqueadas pela navegação acima porque cada
uma é, no fundo, "chegar até X e interagir":

- ao entrar numa cidade nova: Centro Pokémon, curar, Mart, comprar Poké Bolas;
- curar por bom senso quando o HP estiver baixo e houver Centro acessível, sem
  depender de estar num nó específico do QuestGraph;
- capturar ao menos um de cada tipo, não só espécie nova — cobertura de tipos é
  o que faz o time durar; excedentes ficam no PC e a montagem final do time de
  seis vira etapa própria.

Sem BFS, cada uma exige medir à mão a rota até a porta do Centro e do Mart de
**cada** cidade, e cada rota dessas quebra quando um NPC para num tile
diferente.

### Cura antes da Floresta (implementada)

`viridian_forest_nav` usa o Centro de Viridian (**mapa 41**) quando a soma do HP
cai abaixo de 20%, confirma a enfermeira pelo diálogo real e pela party cheia e
só então retoma a rota. Após whiteout, a ROM devolve o jogo ao último ponto de
cura; esse estado pós-morte também é persistido se o mapa for um Centro. A
recuperação foi sondada na ROM e preserva o XP ganho antes da derrota. Pewter
usa a mesma regra no Centro (**mapa 58**) antes de Brock.

### Registro original do livelock (corrigido)

Os dois oscilam entre o portão norte de Viridian (mapa 50) e a entrada da
Floresta (mapa 51) num ciclo de ~35s, sem nunca atravessar:

```
15:08:18  BARON m50[4,5]     CARON m50[4,5]
15:08:30  BARON m51[15,47]   CARON m51[15,47]    entram
15:08:42  BARON m51[5,0]     CARON m50[4,2]      voltam
15:09:06  BARON m51[15,47]   CARON m51[16,47]    entram
15:09:18  BARON m50[4,3]     CARON m50[4,7]      voltam
```

**Não é geometria.** A sonda partindo do save real confirma que o caminho
existe e é curto:

```
start=(51, 15, 47)  target=(51, 17, 47)  steps=2  path=RR
reachable=400  x=1..32  y=6..47
```

`routes[51]` em `_run_viridian_forest_nav` começa exatamente em `(17, 47)`, a
dois passos do tile de entrada. O executor certo está sendo despachado
(`journey.json` mostra `route_2_nav` concluído e a task ativa é
`QUEST: VIRIDIAN_FOREST_NAV`).

**Suspeito principal:** o desvio de colisão que adicionei em `_follow_route` no
mesmo dia. Quando o movimento horizontal não produz deslocamento, ele tenta
`DOWN` primeiro — e em `y=47`, descer é justamente o warp de volta para o
portão. Se qualquer coisa atrasar um passo à direita, o desvio empurra o bot
para fora do mapa. A hipótese ainda **não foi confirmada**; confirmar exige
instrumentar `route_stuck_cycles` durante a travessia.

Correção provável: o desvio precisa conhecer a direção de onde o bot veio e
nunca escolher o eixo que leva de volta ao mapa anterior, ou ser desativado nos
primeiros passos após uma transição de mapa.

**Segundo problema, independente:** o Bulbasaur do BARON está preso em `1/25`
HP e nenhum passo do `viridian_forest_nav` cura. `_run_pokemon_center` existe e
é usado em Cerulean e Pewter, mas não neste trecho. Entrar na Floresta com 1 HP
garante whiteout no primeiro encontro selvagem — o que produziria um segundo
livelock, este por derrota, mesmo depois de a navegação ser corrigida.

### Por que "usar o AARON para guiar" não resolve

AARON não é um agente de tipo diferente. Os três rodam exatamente o mesmo
`ScriptedAgent` + `SimpleBattleAgent`, com os mesmos predicados de RAM e as
mesmas rotas — inclusive esta rota da Floresta, que é código compartilhado.
AARON chegou mais longe porque as rotas dele foram medidas e corrigidas ao
longo de várias sessões, não porque ele tenha um mecanismo próprio.

Também não existe hoje nenhum canal de um bot guiar outro: `HiveMind` só é
consultado quando `current_task == "EXPLORE"`, e nunca durante um nó do
QuestGraph. Guiar exigiria construir esse canal do zero. O que o AARON de fato
oferece já está incorporado: as rotas validadas dele estão no código que
BARON e CARON executam.

## Asset do mapa: marcas d'água removidas

O `kanto_big_done1.png` vinha do fork com três marcas d'água gravadas sobre a
Route 1 (PWhiddy, PufferAI, "Map by"). Foram removidas em 2026-08-05 e a
atribuição passou a viver no README, por escrito.

Método: o PNG é **modo P com `transparency=0`** — o índice 0 é o vazio preto do
mapa. A grama é um padrão de 2 cores com período de 8px, então as caixas foram
repintadas com o tile de grama alinhado por fase, **editando índices de paleta,
nunca convertendo para RGB**. Uma primeira tentativa via `convert('RGB')`
destruiu a transparência e pintou todo o fundo do mapa de verde.

```python
idx[y0:y1, x0:x1] = np.where(block == 0, 0, grass)   # vazio continua vazio
out.save(path, transparency=0)
```

Resultado verificado: 11.044 pixels alterados, todos dentro das três caixas
(`x 943..1511`, `y 4448..5087`), contagem de pixels transparentes idêntica à do
original. Backup do arquivo com as marcas fica fora do repositório.

## Dashboard: navegação do mapa

Reescrita em 2026-08-05 (`MapViz.tsx`). O que existia era zoom por roda que
escalava em torno da origem do container — o mapa fugia do cursor — e listeners
de arraste em `window`, então arrastar sobre a barra lateral ou o feed também
movia o mapa.

| Gesto | Comportamento |
|---|---|
| Roda do mouse | zoom **na direção do cursor** |
| Pinça no trackpad | zoom; chega como `wheel` com `ctrlKey`, com constante mais suave |
| Pinça por toque | dois ponteiros, escala pela razão da distância, centrada no ponto médio |
| Arrastar | mover; quebra o modo seguir |
| Clicar no bot | seleciona **e** trava a câmera nele |

Escala limitada a `0.08..6`. Todos os listeners ficam no canvas, com Pointer
Events e `touchAction: none`.

**Modo seguir:** a câmera recentra no sprite a cada frame do ticker, depois da
animação, para o bot não ficar um quadro atrás. Ao ativar, o zoom sobe para
`FOLLOW_SCALE = 2` se estiver mais afastado — seguir na escala do mapa inteiro
não mostra nada. Arrastar cancela; os chips no canto inferior esquerdo ligam e
desligam por treinador.

## Dashboard: sprites no mapa

Corrigido em 2026-08-05. `MapViz.tsx` destruía o sprite ao fim da animação de
1s, mas o backend só envia coordenadas a cada `upload_interval` steps (~15s em
1x). Resultado: os bots apareciam 1s a cada 15s, e em batalha — quando a
posição não muda — pareciam ter sumido.

Agora há **um sprite persistente por treinador**, indexado por `meta.user`, que
estaciona na última tile em vez de ser destruído. Badge `⚔` e `alpha 0.85`
enquanto `status === 'battle'`, para o mapa responder "onde está" e "o que está
fazendo" ao mesmo tempo. A animação dura o intervalo real medido entre
atualizações (`clamp 500ms..20s`) em vez de 1s fixo seguido de congelamento.

## Diretivas: o que cada treinador joga e até onde

Cada treinador tem uma diretiva em `trainers/<AGENTE>/directives.json`. Sem
arquivo, o padrão é a história completa — nada muda para quem já roda hoje.

| Caminho | Função |
|---|---|
| `blue-agents/trainer_directives.py` | esquema, compilador de ordens e validador |
| `blue-agents/directives.py` | CLI para inspecionar e submeter ordens |
| `blue-agents/quest_graph.py` | predicados novos: `species_owned`, `party_species`, `party_max_level` |

Regras:

- `stop_at` é um nó do grafo e é **inclusivo**: `--stop-at brock_quest` termina
  a corrida com Brock derrotado. A rotação de slot passou a usar esse alvo em
  vez do último nó fixo, então dois slots podem ter metas diferentes.
- Toda ordem carrega uma condição verificável na RAM. Uma ordem sem predicado
  checável é **recusada na submissão**, nunca aceita e silenciosamente ignorada.
- Ordem cujo executor ainda não existe é recusada com o nome do executor que
  falta. Hoje `own_species`/`party_species` pedem `farm_species`, que não existe.
- Ordens satisfeitas pela própria história (`reach_level`, `collect_badges`,
  `reach_map`) mantêm a história rodando mesmo no modo `custom`; quem encerra a
  corrida é o predicado da ordem.
- Ordem pendente tem prioridade sobre a história: uma instrução explícita do
  operador vence a atividade de fundo.

```bash
./blue-agents/directives.py targets                     # alvos válidos
./blue-agents/directives.py set BARON --stop-at brock_quest
./blue-agents/directives.py order BARON --kind reach_level --param level=20
./blue-agents/directives.py show BARON
```

Validado no cartucho: diretiva `custom` com a ordem "nível 14" partindo de
Pewter fez o bot jogar a história, atingir o nível durante a luta do ginásio e
encerrar em `order_completed` → `run_completed` no passo 277, sem mencionar
Brock nem mapa nenhum na ordem.

## Dois slots e rotação

Implementado em:

| Caminho | Função |
|---|---|
| `blue-agents/tasks/slot_roster.json` | identidade atual de cada um dos 2 slots |
| `blue-agents/journey_roster.py` | conclusão, arquivo, nomes e troca de slot |
| `blue-agents/run_journeys.py` | supervisor contínuo em blocos recuperáveis |
| `blue-agents/train_hybrid.py` | carrega roster e salva `latest_policy.zip` |

O alvo de conclusão atual é o último nó `mewtwo_postgame`. Quando um slot
conclui todos os 19 nós:

1. os dois emuladores encerram o bloco e persistem o estado;
2. somente o concluído é copiado para `archives/<UTC>-<AGENTE>/`;
3. o arquivo recebe `.sav`, `.state`, journey, JSONL, checkpoints, cópia do
   QuestGraph, política compartilhada e `manifest.json` com hashes;
4. o roster troca AARON por CAARON (ou o nome seguinte);
5. BARON permanece BARON e recarrega seu próprio `current.state`.

Estados temporários de diagnóstico em `runtime/` não entram no arquivo para não
inflar armazenamento. A ROM também não é copiada; apenas sua identidade/hash é
registrada.

## Portabilidade (Windows)

Suporte adicionado em 2026-08-05 porque o projeto passou a ser testado no
Windows. Três bloqueios reais foram corrigidos:

| Bloqueio | Correção |
|---|---|
| `import fcntl` em `_update_agent_state` | escrita atômica com `os.replace`; `fcntl` não existe no Windows e derrubava a execução no primeiro update de estado |
| Launchers em `.sh`, `lsof`, `.venv/bin/python` | `start.py`, único e multiplataforma; resolve `Scripts\python.exe` vs `bin/python` e libera portas com `netstat`/`taskkill` ou `lsof` |
| `--agents` inexistente em `run_journeys.py` | `--slots`, com `resize_roster` para crescer/encolher sem apagar treinador |

`start.bat` e `start.command` são apenas invólucros de clique duplo para
`start.py`. A escrita atômica também eliminou a janela de leitura parcial que um
leitor do `agent_states.json` podia pegar no meio da escrita.

**Ainda pendente no Windows:** a pausa global usa `SIGSTOP`/`SIGCONT` em
`viz_server/ws_relay.js`, sinais que não existem lá. A pausa por agente, que
passa por `runtime_controls.json`, é portátil e funciona.

## Execução

Suíte:

```bash
cd /Users/matheuscarvalho/Dev/2025/cursor/poke-ai-2026/blue-agents
MPLCONFIGDIR=tasks/matplotlib ../.venv/bin/python \
  -m unittest discover -s tests -q
```

Jornada contínua, exatamente dois slots:

```bash
cd /Users/matheuscarvalho/Dev/2025/cursor/poke-ai-2026
POKEAI_TORCH_THREADS=2 ./blue-agents/run_all.sh --journeys
```

Teste limitado do supervisor:

```bash
./blue-agents/run_all.sh --journeys --chunk-steps 1024 --max-chunks 1
```

Validação curta de AARON sem iniciar BARON:

```bash
cd /Users/matheuscarvalho/Dev/2025/cursor/poke-ai-2026/blue-agents
POKEAI_NO_DELAY=1 POKEAI_TORCH_THREADS=2 MPLCONFIGDIR=tasks/matplotlib \
../.venv/bin/python train_hybrid.py \
  --agents 1 --steps 512 --rollout-steps 128 --resume \
  --device cpu --state-update-interval 50
```

Evite `--fresh-model` em validação normal: agora `latest_policy.zip` é o cérebro
compartilhado canônico entre blocos.

## Arquivos essenciais

| Caminho | Responsabilidade |
|---|---|
| `src/scripted_agent.py` | executores e rotas da história |
| `blue-agents/hybrid_agent.py` | orquestração, RAM, eventos, captura e checkpoints de Centro |
| `src/simple_battle.py` | escolhas e menus de batalha |
| `blue-agents/knowledge/quests/main_quest_graph.json` | 19 objetivos e predicados |
| `blue-agents/quest_graph.py` | avaliação dos predicados reais |
| `trainers/<AGENT>/current.state` | retomada exata do PyBoy |
| `trainers/<AGENT>/current.sav` | save portátil |
| `trainers/<AGENT>/journey.json` | conclusão persistente do grafo |
| `trainers/<AGENT>/logs/decisions.jsonl` | histórico detalhado append-only |
| `blue-agents/tasks/agent_states.json` | snapshot recente da interface |

## Regras de qualidade para cada nova quest

Uma quest só fica “Validada” quando possui:

1. predicado de sucesso baseado na RAM/evento real;
2. rota de entrada, cura, diálogos e retorno após whiteout;
3. retomada de processo por `current.state`;
4. teste unitário para regras novas;
5. execução no cartucho sem editar RAM para forçar progresso;
6. evento observável com motivo e dados brutos;
7. atualização deste documento e de `docs/QUEST_GRAPH.md`.

## Armadilhas conhecidas

- Reset de PPO não pode recarregar o início de uma jornada já ativa.
- Rotas retomadas devem escolher o waypoint seguro mais próximo.
- Diálogo pode continuar aberto depois de o battle flag zerar; `_follow_route`
  avança texto antes de tentar andar.
- PP ativo é `0xD02D..0xD030` com máscara `0x3F`; Disable é `0xCCEE`.
- Pokémon Blue usa DVs e Stat Experience, não IV/EV moderno.
- Quest no JSON não significa executor pronto. Neste momento, o limite validado
  é Misty e o próximo executor ausente é Lt. Surge.
