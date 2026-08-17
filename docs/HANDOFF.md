# PokeAI 2026 — handoff canônico

Última atualização: **2026-08-17**.

## Continuar daqui (2026-08-17)

### Marco: o watchdog de vida está de pé, e achou uma tela no primeiro uso

O item 1 do roadmap abaixo ("fazer primeiro") está feito. A cada passo tira-se
uma **impressão digital do cartucho** — mapa, posição, equipe (espécie, nível,
HP), tamanho da mochila, insígnias, em-batalha — e um conjunto que não cresce
numa janela de passos é congelamento, independente do que cada camada ache que
está fazendo. `src/life_watchdog.py`, chamado de `HybridGymEnv.step` ao lado
dos outros rastreadores.

Ao disparar: evento `congelado` no diário com a **tela decodificada**, e o save
gravado sozinho em `states/replay/auto/` com um `.json` do mesmo nome ao lado.
Era isso que eu vinha fazendo à mão — copiar save, sondar, escrever o
checkpoint. O diretório é ignorado pelo git de propósito: o que vira trecho de
replay é promovido à mão para `states/replay/` com entrada no manifesto.

**Ele não conserta nada, e isso é decisão, não falta de tempo.** Uma
recuperação automática esconderia o defeito de novo, que é exatamente o que o
resgate acidental do PPO fazia com AARON..DARON.

**Limiar medido no cartucho** (janela 600 passos, piso de 6 impressões
distintas — configurável por `POKEAI_WATCHDOG_STEPS` e
`POKEAI_WATCHDOG_DISTINCT`):

| save, 800 passos roteirizados | tiles | disparos |
|---|---|---|
| `casa-inicial` andando | 42 | **0** |
| `cais-ss-anne` andando | 131 | **0** |
| `vermilion-com-hm` andando | 1 | **1** (passo 599, tela `esquecer_golpe`) |
| `casa-inicial`, nenhum botão | 1 | **1** (passo 599) |
| `cais-ss-anne`, nenhum botão | 1 | **1** (passo 599) |

A janela importa: com 100 passos ele acusava trechos saudáveis (diálogo do
laboratório, fila de texto do cais). Com 600 — quatro minutos de jogo — nenhum
falso positivo nos dois trechos saudáveis medidos.

A linha do `vermilion-com-hm` **não é falso positivo**: depois de ensinar o
Cut, o executor não tem para onde ir (a árvore do ginásio de Vermilion é o
próximo nó) e o bot fica no mesmo tile. É o travamento aberto nº 2 abaixo, e o
watchdog o nomeou sozinho.

### O que ele achou no primeiro uso: o teclado do inicial

Rodando do save `casa-inicial` sem PPO, o disparo veio com a tela
`teclado_nome` no mapa 40. **O teclado de apelido aparece também ao receber o
inicial**, e ali `0xD057` já é zero — fora do alcance do controlador de
batalha, que era o único que sabia respondê-lo (`START` é o `END` desta tela em
Gen I). O executor via menu aberto e respondia `A`, que nesta tela digita
letra.

Medido dos dois jeitos, no cartucho: **não travava** — o cartucho auto-confirma
quando o nome enche. Custava 11 passos digitando, e o inicial saía chamado
`AAAAAAAAAA` em vez de `BULBASAUR`. Não depender desse acidente é o ponto: numa
tela conhecida, quem responde é a tela. O gate subiu para o topo de
`ScriptedAgent.step`, então vale para toda quest, não só a `start`.

Trecho novo de replay: **`apelido-do-inicial`**, com o save gravado no exato
passo do teclado. A expectativa é o apelido do slot 0 (`party_nickname`, novo em
`replay_check.py`) — é o que separa "a tela foi respondida" de "o A foi
martelado", já que as duas saem do teclado. Reprovado com o código de antes:
`apelido do slot 0 é 'AAAAAAAAAA', esperado 'BULBASAUR'`.

### `src/screen.py`: a tela num lugar só (item 2, parcial)

Eram três arquivos decodificando o `wTileMap` por conta própria. Agora
`rows`, `text`, `visible_lines`, `naming_screen_open`, `party_list_open`,
`classify` e `describe` vivem em `src/screen.py`, e os três chamam de lá.
`classify` devolve nome — `overworld`, `texto`, `texto_batalha`, `lista_golpes`,
`menu_batalha`, `lista_equipe`, `lista_mart`, `quantidade`, `teclado_nome`,
`menu_principal`, `mochila`, `usar_jogar_fora`, `sim_nao`, `esquecer_golpe`,
`compra_venda` — ou `desconhecida`, que é o valor que faz o chamador registrar
em vez de apertar A. Cada sinal usado já estava medido no código; nada foi
deduzido.

**O que falta do item 2:** migrar os controladores para perguntar a `classify`
em vez de decorar byte (`_buy_first_shop_item`, `_teach_cut_action`,
`_next_switch_action` e o gate de texto da batalha), e a escada de fuga
(B → START → B) para `desconhecida`. Hoje só o relatório de congelamento
consome a classificação.

### Na corrida do operador: a trava de (1,1) da Floresta, com nome

O watchdog subiu numa corrida viva de 3 slots e apontou o que estava aberto no
roadmap. **IARON, JARON e KARON, os três parados no mapa 51**, alternando entre
(1,1) e (1,2) — o canto noroeste da Floresta. O relatório diz o que faltava
saber:

```
tela: overworld | caixa_de_texto: 0 | canto: [12,5]
route_id: trail-override-viridian_forest_nav-51
```

Não é tela, não é menu, não é batalha: é **trail dirigindo o executor**.
`TRAIL_BLOCKED_QUESTS` cobre `bill_quest`, `cerulean_gym_quest` e
`vermilion_gym_quest`, e **não cobre `viridian_forest_nav`** — que tem rota
medida (`_run_viridian_forest_nav`). Com `POKEAI_FOLLOW_TRAILS=1`, que é como a
corrida do operador roda, o trail ganha. É a mesma assinatura do travamento de
Vermilion de 16/08, na quest seguinte. Os saves ficaram em
`states/replay/auto/{IARON,JARON,KARON}-m51-1x1-*.state`.

**Não mexi na lista**: mudar `TRAIL_BLOCKED_QUESTS` muda o comportamento de uma
corrida que está de pé, e isso é decisão do operador.

### Uma situação, um save — 179 MB em duas horas

O teto de relatórios por processo (`FREEZE_MAX_REPORTS`) não segura nada
sozinho, e é o **mesmo erro que este documento já registra duas vezes**: um
chunk é um processo novo com o contador zerado — foi assim com o contador de
ciclo de morte e com a vantagem de largada. Medido na corrida acima: três bots
no mesmo tile escreveram **2.190 arquivos e 179 MB em duas horas, para 6
situações distintas** (163 KB por save, numa máquina de 8 GB).

Agora o que identifica uma situação é `<agente>-m<mapa>-<x>x<y>`: já capturada,
não grava de novo — e o evento no diário passa a ter carga idêntica, então o
colapsador de repetição faz o resto. Mais um teto de 40 assinaturas para o
diretório inteiro. O diretório foi limpo guardando o **primeiro** save de cada
uma das 6 situações (179 MB → 1 MB).

### Travamentos abertos, na ordem

1. **O duelo do rival no S.S. Anne** (aberto desde 16/08): navegação resolvida,
   batalha não — Butterfree 40 (124/124) contra um Charmeleon 20 (56/56) por 8
   minutos sem lançar golpe, com `switch_intent` "sem PP de dano no ativo"
   antes do congelamento.
2. **Depois do Cut, o executor acaba** — `vermilion-com-hm` fica 800 passos no
   mesmo tile. O próximo nó é a árvore do ginásio de Vermilion.

Mudanças: `src/life_watchdog.py` e `src/screen.py` (novos);
`blue-agents/hybrid_agent.py` (`_watch_for_freeze`, `_report_freeze`,
`_save_freeze_snapshot`, chamada no `step`); `src/scripted_agent.py` (gate do
teclado no topo do `step`, `_screen_rows` delegando); `src/simple_battle.py`
(`_naming_screen_open` delegando); `blue-agents/tools/replay_check.py`
(`party_nickname`); manifesto com o trecho `apelido-do-inicial`. Suíte: **590
testes OK**; replay: **8/8 trechos de pé**.

## ROADMAP — resolver a classe, não o travamento da vez (2026-08-16)

Sete travamentos num dia, todos com a mesma forma: o bot para, ninguém percebe
por horas, e a causa só aparece quando alguém lê a tela do cartucho. A lista
abaixo é para parar de consertar um por um.

### O que os sete tinham em comum

| trava | faltou mapa? | o que era |
|---|---|---|
| casa inicial (m37) | não | o plano excluía a porta, e o alvo fica um tile depois dela |
| lab do Oak (m40) | não | trail apontando para trás + objeto do ROM tratado como muro |
| prancha do S.S. Anne (m94) | não | marinheiro pedindo o ticket; nada disso aparece no estático |
| Mart de Viridian (m42) | **não é mapa** | lista lida 17 bytes fora + índice comparado com id |
| teclado de apelido | não é mapa | tela que nenhum controlador conhecia |
| lista da equipe em batalha | não é mapa | duas telas diferentes confundidas |
| Floresta (1,1) — **aberto** | a medir | — |

Em nenhum o bot estava perdido: nas três de navegação o mapa estava certo e o
código o sobrepunha; nas outras ele nem estava no mapa, estava numa tela sem
saber qual. **Mais dado de mapa não resolve nada disto.**

E o estado do código explica a recorrência: **12 bytes diferentes de "estado de
menu"** espalhados por três arquivos (`0xCC24`, `0xCC25`, `0xCC26`, `0xCC36`,
`0xCC50`, `0xCFC4`, `0xCF8C`, `0xD52A`, `0xD125`…), cada controlador decorando
os seus, e **três arquivos decodificando a tela** (`0xC3A0`) por conta própria.

### 1. Watchdog de vida com snapshot automático — **feito em 2026-08-17**

Nenhum detector atual pega os sete. `route_no_progress` mede **distância**, e o
vaivém entre duas casas encurta distância a cada outro passo, então ele zera
para sempre. O contador de batalhas do painel marcava 0 com 11 batalhas
acontecendo. Cada camada tem sua noção de progresso e todas erraram.

Um sinal só, que nenhuma camada pode mentir: **impressão digital do cartucho** a
cada passo — mapa, posição, HP da equipe, tamanho da mochila, insígnias,
em-batalha. Conjunto de impressões que não cresce em N passos = congelado,
independente do que cada camada ache que está fazendo. Dispara nos sete.

Ao disparar: loga a **tela decodificada** e **grava o save em
`states/replay/`** sozinho. Hoje esse mecanismo fui eu, à mão: copiar save,
sondar, escrever o checkpoint. Tem de ser o robô — cada congelamento novo
nasce checkpoint com a tela que o causou anexada.

Meio dia de trabalho. É ele que acha a trava de (1,1) que ficou aberta.

### 2. Classificador de tela único, lido de `wTileMap` — **meio feito**

A tela acertou nas três vezes em que foi usada hoje: `ABLE/NOT ABLE` disse quem
aprende Cut, `NICKNAME` achou o teclado, `is already out!` explicou a recusa da
troca. É RAM, é o que o jogador vê, e não é ambíguo — enquanto `0xCC50`
significa coisas diferentes em cinco contextos.

`src/screen.py` devolvendo um nome: `OVERWORLD`, `TEXTO`, `SIM_NAO`,
`LISTA_EQUIPE`, `LISTA_MART`, `TECLADO_NOME`, `LISTA_GOLPES`, `MENU_BATALHA`,
`QUANTIDADE`. Todo controlador pergunta a ele em vez de decorar byte. Migrar
`_buy_first_shop_item`, `_teach_cut_action`, `_next_switch_action` e o gate de
texto da batalha para ele — os quatro que quebraram hoje.

**E tela desconhecida vira evento, nunca padrão silencioso.** Os sete
terminaram em `press A` ou `return None` calado: é isso que transforma um bug
de dez minutos em oito horas paradas. Não classificou → loga
`tela_desconhecida` com o texto e sobe a escada de fuga (B → START → B).

Um dia.

### 3. Ordem de autoridade, escrita e coberta por teste

As três correções de navegação de hoje são a mesma regra dita três vezes:

> **leitura ao vivo > estático do ROM > trail** — e o plano ganha da heurística.

Em regra: trail não dirige onde o executor tem rota medida; objeto do ROM só
bloqueia **fora da tela**; pulo de penhasco e conversa com sprite só quando não
há plano. Está no código; falta estar escrito e testado como uma coisa só.

### 4. Tirar o resgate acidental do PPO da conta

Foi ele que fez AARON..DARON passarem: quando o controlador devolve `None`, a
política aperta botão aleatório e num menu de equipe isso acaba escolhendo
alguém. Passava por acidente. Ele pode continuar apertando, mas **controlador
que não decide numa tela conhecida tem de registrar defeito** — senão o
acidente volta a esconder o próximo travamento.

### 5. Só então: executores 13→19 e a Liga

Com 1-4 de pé, cada nó novo custa medição de rota, não caça a travamento. A
ordem do operador para o resto: Cut feito, **árvore do ginásio de Vermilion**,
puzzle das lixeiras, Strength pronto mas usado mais à frente, itens no roadmap
(fora da Liga não são necessários), overlevel por farm.

## Continuar daqui (2026-08-16, fim do dia)

### Marco: bot novo destravado do zero, e o S.S. Anne até o rival

**O jogo não era mais recomeçável.** Dois bots novos, 10 minutos cada, nenhum
saiu da primeira casa: 11.355 relatórios de travamento no mesmo tile (1,2) do
mapa 37, com `blocked: {}`, `path_to_target` preenchido e o cartucho
respondendo `reachable=47, steps=7, path=RDDDDRD` para a porta.

Causa, reproduzida **sem PPO e sem hybrid** (só o `ScriptedAgent` em cima do
save): `_planned_step` trata toda porta como intransponível — a regra que
matou a gravidade do Mart. Só que as rotas daqui terminam de propósito **um
tile depois da porta**, porque é esse passo que atravessa. O alvo (3,8) só é
alcançável por (3,7), que é porta: sem caminho, `route_no_progress` sobe até a
**regra de fronteira** trocar o alvo pelo canto inexplorado, e o bot passa o
resto da vida indo para lá.

A exceção nova é estreita: a porta só é liberada quando o alvo **não é célula
andável do estático** (a âncora de fora do mapa) **e** a porta é vizinha dele.
Mesmo save, depois: sai da casa em ~13 passos, cruza Pallet e entra no
laboratório do Oak em ~200 passos roteirizados.

**S.S. Anne, medido na ROM e validado no cartucho na mesma corrida:**

| perna | como |
|---|---|
| Vermilion → cais | coluna LESTE (x=30): y=22..25 é parede de x=16 a 29, o centro da cidade não desce. Da linha 26 a oeste até x=18 — a coluna 19 tem o marinheiro parado em (19,30) |
| cais → convés | o passo D em (14,1) **não move**: o marinheiro do cais pede o S.S. Ticket. D e A alternados resolvem (D anda quando abre, A fala quando não) |
| convés (95) → 2º andar (96) | corredor y=6 a oeste até a escada (2,6) |
| 2º andar → cabine (101) | corredor y=12 a leste, sobe a coluna x=36/37 até (37,4). (35,4) não é andável: a porta se aproxima pelo **leste** |
| cabine | capitão é o NPC (4,2); fala-se de (4,3) virado para cima (`0xC109` = 4). Fim = **HM01 (0xC4) na mochila**, não um contador |

**O rival está em cima da porta da cabine** — objeto `trainer` classe 225 no
warp (36,4), lido do bloco de objetos. O executor encosta nele e a máquina
`route_sprite_talk` abre o duelo.

**Travamento aberto nº 1 agora**: o duelo do rival. AARON chegou, o Ivysaur
subiu ao 23 e caiu, e o Butterfree 40 (124/124) ficou **8 minutos contra um
Charmeleon 20 com 56/56 de HP intactos** — nenhum golpe lançado. É a mesma
família do problema do Brock: navegação resolvida, batalha não. `switch_intent`
com "sem PP de dano no ativo" aparece antes do congelamento.

### O Cut aprendido, e a tela como fonte de verdade

O HM01 saiu do capitão e o Cut está no Ivysaur — `[77, 45, 73, 22]` virou
`[77, **15**, 73, 22]`, medido no save e repetido na corrida. Ensinar são seis
telas de menu, e **sequência fixa de botões não serve**: o número de caixas de
texto varia (a mensagem de "não cabe mais golpe" só aparece com quatro
golpes), e um D apertado durante o texto é comido, o que dessincroniza tudo o
que vem depois — errei assim três vezes antes de ler a tela.

Cada tela é reconhecida pelo canto do menu (`wTopMenuItemY`/`X`, 0xCC24/0xCC25),
como o `_buy_first_shop_item` já fazia com a loja:

| tela | canto | o que fazer |
|---|---|---|
| menu principal | (2, 11) | cursor no índice 2 (ITEM) |
| mochila | (4, 5) | índice = rolagem (0xCC36) + cursor (0xCC26) |
| USE / TOSS | (11, 14) | USE é o de cima |
| "Teach CUT?" | (8, 15) | SIM é o de cima |
| lista da party | (1, 0) | quem a tela marca **ABLE** |
| esquecer golpe | (8, 5) | pior status pela `STATUS_MOVE_PRIORITY` |

**Quem pode aprender vem da RAM, não de uma tabela na ROM.** Com a lista da
party aberta para um TM/HM, o cartucho escreve ABLE/NOT ABLE ao lado de cada
um, e `wTileMap` (0xC3A0) — que este projeto já lê para terreno — entrega isso
decodificado. Foi assim que caiu a ideia de ensinar Cut a quem não é o inicial:
a **Butterfree não é compatível**, a tela diz NOT ABLE, e não havia escolha.

O golpe sacrificado sai da régua que o controlador de batalha já usa: Growl
vale 9 na `STATUS_MOVE_PRIORITY` (pior), Leech Seed vale 0, e golpe de dano só
sai se não houver status. Foi o Growl. HM nunca entra na escolha — o cartucho
recusa apagar, e escolher um seria um ciclo.

Medido de ponta a ponta a partir do save real, sem PPO: **47 passos** do tile
de Vermilion até `IVYSAUR learned CUT!`.

### A rede: `tools/replay_check.py` (7 trechos)

Teste de unidade não pisa no cartucho: a suíte estava **verde com 548 testes**
enquanto três bots novos não saíam da primeira casa. Cada trecho vencido virou
um save em `states/replay/` mais o que o cartucho tem de responder depois de N
passos, e o manifesto guarda **a regressão que cada um pegou**.

```bash
cd blue-agents && ../.venv/bin/python tools/replay_check.py
```

Cobre executor **e** batalha (troca primeiro, golpe depois — a ordem do
hybrid). Duas lições sobre o próprio teste, que custaram duas rodadas:

- a expectativa "não estar em batalha no fim" **reprova bot saudável**:
  farmando na grama, entrar em nova batalha é o certo. O que o bot preso nunca
  faz é **sair do tile** — então a medida é `tiles_min`;
- cobrir só o controlador de golpe deixava metade da luta de fora, e foi na
  **troca** que os três ficaram presos.

### O que o bot fazia antes, e era acidente

Quando um controlador devolve `None`, o hybrid passa a vez ao PPO, que aperta
botão aleatório — e num menu de equipe qualquer sequência aleatória acaba
escolhendo alguém. **Era assim que AARON..DARON passavam.** Medido: o código
commitado devolve `None` sessenta vezes seguidas na tela de troca do save
travado do IARON. Não é regressão nova; é um buraco que o acaso tapava.

### Um buraco na *verificação*, que valia para todas as rotas

`find_path` isenta o alvo de propósito, então conferir uma cadeia hop a hop
**aprovava waypoint em cima de parede**. Foi assim que (19,20) de Vermilion
(muro) passou verde e o AARON gastou 120 passos batendo `L` contra ele com
`path: L` no relatório. O helper de teste agora exige que todo waypoint do
meio seja célula andável — e, ao ligar, reprovou na hora mais dois que já
estavam no código: (17,24) da Route 5 e (20,11) do 2º andar do navio. Os
waypoints passaram a ser **derivados do caminho real** do `find_path`, não
escolhidos a olho.

Mudanças: `src/scripted_agent.py` (exceção da porta-âncora; pernas do S.S.
Anne; `_run_ss_anne_captain`; waypoints corrigidos de Route 5, 2º andar e
Vermilion), `blue-agents/tests/test_door_last_waypoint.py` (4 testes),
`test_vermilion_route.py` (30 testes). Suíte: **522 OK**.

## Continuar daqui (2026-08-16)

### Marco: AARON chegou a Vermilion, checkpoint `center_89` gravado

Confirmado na RAM e no save, em 2026-08-16 às 14:25: `location_discovered`
mapa 5 com `first_visit: true`, `major_locations` agora `[0, 3, 5]`, e o
manifesto de retomada aponta para **`center_89`** (geração 409) — um apagão
devolve o treinador a Vermilion, não mais a Cerulean. O trajeto Cerulean →
Route 5 → Underground → Route 6 → Vermilion levou **~7 minutos de relógio**,
3 batalhas, 0 mortes.

Antes disso o AARON estava dois dias sem sair do lugar. Foram **quatro**
travamentos empilhados, e o primeiro não era código:

1. **O bot estava pausado.** `tasks/runtime_controls.json` tinha
   `agents.AARON.paused: true` e `manual_mode: true` desde 14/08 16:36 — o
   operador tinha assumido o controle para guiar à mão e o modo guia ficou
   ligado. Em modo guia e em pausa o `step` devolve NOOP: dois dias de
   emulador rodando com `decision_count: 0`. **Antes de investigar rota
   parada, olhar esse arquivo** — foi o que custou mais tempo aqui.
2. **A rota do vermilion ia para o lado errado.** Vermilion fica ao **sul**
   de Cerulean; o executor mandava para **leste**, para a Rota 9 (mapa 20),
   que é o caminho do Túnel da Rocha. O warp de lá cai num beco de 9 tiles
   cuja única saída é voltar — e o mapa 3 mandava para leste de novo:
   **1.976 transições m3↔m20** medidas no diário, zero progresso.
   A saída sul é fato do estático: Cerulean tem dois componentes andáveis
   separados pelo rio, e só o de **leste** alcança a borda sul. Do lado leste
   a coluna x=36/37 é a única passagem pela faixa de penhascos em y=28, e a
   coluna x=25..28 desce até (26,35) sem nenhum pulo. Um passo além entra na
   Route 5 em (16,0) — a conexão soma 10 ao x. Do lado oeste (Centro,
   ginásio) nada alcança o sul: o caminho é a casa acima do ginásio, cujo
   buraco devolve o jogador em (27,9), já a leste. O teste de lado deixou de
   ser caixa de coordenadas (`26 <= x <= 39 and 7 <= y <= 17` chamava o
   ginásio (30,19) de "leste") e virou `_can_reach`, um BFS no estático.
3. **Vermilion era o mapa 1 no código — que é Viridian.** O bloco da cidade
   tinha sido copiado de `buy_pokeballs` e nunca corrigido: mapa 1, Centro
   41, Mart 42, porta (23,25). Chegar em Vermilion não disparava nada, e
   qualquer prédio de Viridian disparava a rota de outra cidade. Vermilion é
   o mapa **5**, o Centro é o **89** e a porta é **(11,3)** — tudo já estava
   em `knowledge/maps/pokemon_centers.json`, extraído da ROM.
4. **O trail da guia manual sequestrou o executor.** Desligar `manual_mode`
   chama `_publish_manual_trail`, que publicou o caminho do operador como
   trail da quest — com a perna da Rota 9 dentro e entrando na Route 5 em
   (9,0), a faixa do meio que os penhascos isolam da porta do Underground.
   Com `POKEAI_FOLLOW_TRAILS=1` (a corrida do operador roda assim) o trail
   ganha do executor: `route_id=trail-vermilion_gym_quest-16`, alvo (9,0),
   `path_to_target: None`, 600 passos quicando em (15,0)..(15,5). Agora
   `TRAIL_BLOCKED_QUESTS` cobre as três quests cujo executor tem rota medida
   em todo o caminho (`bill_quest`, `cerulean_gym_quest`,
   `vermilion_gym_quest`), nos **dois** lugares que consultam trail.

### E um bug de navegação que valia para o jogo inteiro

**Penhasco e parede-com-porta-atrás têm a mesma assinatura no estático**:
tile do meio sólido, pouso andável, alvo alinhado a dois tiles. A regra de
pulo de ledge disparava nos dois e vinha **antes** do planejador. Medido na
Route 5: o bot em (15,27) mirando a porta do Underground (17,27), com
(16,27) de parede, apertou `R` contra a parede por 250 passos enquanto o
`_planned_step` já tinha o desvio de quatro passos (`D,R,R,U`) na mão.

O desempate é o plano: **quem tem caminho andando não pula**. O pulo é o que
sobra quando o plano não existe — que é exatamente a Rota 4, onde o penhasco
parte o mapa e não há desvio. A regra do ledge foi movida para depois do
`_planned_step`; o teste da Rota 4 continua verde e ganhou par
(`test_sem_plano_o_pulo_continua_valendo`).

Mudanças:

- `src/scripted_agent.py`: `_run_vermilion_gym_quest` reescrito (Cerulean sul,
  Route 5 pela coluna leste, Underground terminando no tile do warp (2,41),
  Route 6, cidade 5 e Centro 89); `_can_reach`; `VERMILION_CITY_MAP_ID`,
  `VERMILION_CENTER_MAP_ID`, `CERULEAN_SOUTH_EXIT`, `TRAIL_BLOCKED_QUESTS`;
  ledge depois do plano; perna do Centro de Cerulean (mapa 64), que é onde um
  apagão devolve o treinador.
- `blue-agents/tests/test_vermilion_route.py`: 17 testes novos. Cada cadeia de
  waypoints é conferida hop a hop com o `find_path` do MapMemory — a mesma
  pergunta que o executor faz em tempo de execução.
- Suíte: **507 testes OK**.

**A fazer daqui:** o AARON está parado em (11,4), a porta do Centro, porque o
executor acaba aqui — o ginásio do Lt. Surge depende do **Cut**, que vem do
capitão do S.S. Anne. A doca é o warp (18,31)/(19,31) → mapa 94, e o
`find_path` do estático diz que ela é alcançável do Centro em 58 passos. O
ticket já está na mochila desde o `bill_quest`. Esse é o próximo executor.

Cuidado ao medir: `POKEAI_FOLLOW_TRAILS=1` está ligado nesta corrida, então
todo trail publicado dirige — `ps eww` não mostra o env do processo no macOS,
e conferir por lá dá falso negativo.

## Continuar daqui (2026-08-12)

### Marco: AARON saiu de Cerulean para a Rota 9 pela casa acima do ginásio

A rota do vermilion estava **invertida**: o executor antigo mandava o bot para
a borda **oeste** de Cerulean (0,18), que conecta na Route 4 — de volta ao
Mt. Moon. A tabela de conexões do cartucho diz o contrário: mapa 3 tem
E→20 (Route 9) e W→15 (Route 4). AARON e FARON ficaram 3000+ passos parados
em (0,18) e depois na Route 4 (63,10), e o executor nem rodava.

**O caminho real para a Rota 9** (confirmado na RAM, em 2026-08-12):

1. Cerulean → porta da casa acima do ginásio (27,11) — warps do mapa 3.
2. Casa 62: atravessar até o buraco na parede (3,0) — o warp devolve ao
   mapa 3 em (27,9), o lado leste do rio.
3. Descer a margem leste: (27,9) → (39,16), conexão com a Rota 9 (mapa 20).
   AARON chegou a **m20 (0,8)** com `FIRST DISCOVERY` na run de validação.

**O que destravou** (a sequência de travamentos que a medição revelou):

1. **O executor do vermilion mirava o lado errado.** `cerulean-to-route4`
   ia para (0,18) (borda oeste = Route 4/Mt. Moon). Reescrito: vai para a
   casa (27,12), entra em 62, e o lado leste desce até (39,16)/(40,16).
   Além disso, o ramo do lado leste só cobria `26 <= x <= 33` — o bot em
   (34,12) caía no ramo errado e voltava para a casa num ciclo RIGHT/UP.
2. **`_center_first_action` sequestrava o bot para uma porta inalcançável.**
   `wLastBlackoutMap` ainda apontava Pallet, e o mapa 15 (Route 4) tem Centro
   em (11,5) — 52 tiles a oeste, do outro lado do penhasco. O desvio rodava
   antes do executor e o bot ficava 3000 passos parado com
   `route_id: center-door-11-5`. Agora `_walk_to_door` só desvia quando a
   porta está **alcançável** (`_door_is_reachable` = `find_path` no
   MapMemory), e o teste `test_porta_inalcancavel_nao_desvia_para_o_centro`
   cobre o caso.
3. **O `ROUTE_EVENTS["U"]` da porta da casa era string, não WindowEvent.**
   O hybrid converte com `event_to_action` que espera int — string vira
   NOOP. O bot parava na porta (27,12) sem entrar.

**Roster agora tem 3 slots**: AARON (speedrunner, guia), FARON (completionist,
**pausado** via `tasks/runtime_controls.json` `agents.FARON.paused=true`),
GARON (team_builder, **Squirtle**, novo — começou do início em 2026-08-12,
arquivado o GARON antigo de 06/08 em `archives/20260812-old-GARON/`).
GARON confirmou Squirtle (interno 177 → nacional 7) e atravessou a Floresta
até (51, 16,44) na mesma run em que o AARON chegou à Rota 9.

Mudanças:

### Marco: Mt. Moon atravessado de novo, confirmado na RAM

`mt_moon_nav` foi concluído no cartucho: AARON saiu de 1F (34,31), cruzou
1F → B1F → B2F → B1F → Rota 4 e entrou em Cerulean em **m3 (0,18)** — o mesmo
tile de entrada do BARON em 08-05. `completed_quests` inclui `mt_moon_nav`
(generation 85) e o nó seguinte (`bill_quest`) ficou ativo. O estado final é
saudável (mapa 88, menu=0) e o checkpoint do Centro da Rota 4 vale.

**O que destravou** (a sequência de travamentos que a medição revelou):

1. **O estático NÃO estava partido.** O diagnóstico anterior ("becos que o
   estático diz conectados, ex.: (9,6)") veio de um diff viciado — células
   inalcançáveis pela sonda foram contadas como "estático diz andável". Medido
   de novo: a sonda do B2F leste (67 células) == estático menos warp (25,9) e
   treinador (29,11); o corredor B1F (47 células) == estático; todos os tiles
   pisados pelo BARON em 08-05 ⊆ estático. A fórmula do extrator (quadrante
   inferior-esquerdo do bloco) confere com `CanWalkOntoTile` do disassembly.
2. **Treinador parado no corredor nunca era enfrentado.** O fallback só virava
   o personagem (D-pad); D-pad sozinho não abre diálogo em Gen I. AARON ficou
   1.000+ passos ao lado do Youngster de 1F (12,16) e do Rocket-gate do B2F.
3. **Treinador derrotado fica no tile para sempre** (comportamento real de Gen
   I — o Youngster em (12,16) ficou com o texto pós-batalha "I came down here
   to show off to girls" e bloqueando). Conversa que não resolve em batalha ou
   pickup entra em `route_sprites_tried` e o desvio assume.
4. **Os fósseis (12,6)/(13,6) do B2F são o portão da travessia** (SPRITE_FOSSIL
   no bloco de objetos, não NPCs): a sala central só alcança a escada oeste
   passando pelos tiles deles (e do Super Nerd (12,8)). Pickup com A abre o
   caminho — e o planejador normal os contorna (fallback cruza o que abriu).
5. **Ledge da Rota 4**: (79,8)→(79,10) é um pulo sobre o penhasco em y=9; o
   planejador trata (79,9) como parede. Regra nova: alvo alinhado a 2 tiles
   com pouso andável → tenta o passo (parede comum não move nada, ledge pula).

Mudanças:

- `src/map_memory.py`: `_load_static_maps` carrega `objects` (treinador + NPC +
  fóssil + item ball) e `object_positions(map_id)`.
- `src/scripted_agent.py`: `_planned_step` bloqueia objetos estáticos no plano
  normal (o fallback `ignore_solid` cruza o que a luta/pickup abriu); máquina
  `route_sprite_talk` (virar + A contra sprite que fecha a passagem, com limite
  e `route_sprites_tried` para o ghost de treinador derrotado); regra de
  pulo de ledge para alvo alinhado a 2 tiles; `begin_death_cycle` limpa o
  estado da máquina.
- `blue-agents/tools/probe_route.py`: settle de 120 frames após `--path` — o
  warp tem dois estágios (~40+ frames de reposicionamento) e o snapshot
  antigo pegava o jogador no meio, retornando "reachable=1".
- Testes: 479 OK (12 novos: objetos do B2F, portão dos fósseis, rota conectada
  com objetos bloqueados, máquina de sprite, ghost não re-triggerado, ledge).

Retomada: AARON segue saudável em `trainers/AARON/` (jornada em
`bill_quest`); o estado de validação da travessia ficou em
`current.state` (o par antigo doente, Centro da Rota 4 com menu preso, foi
preservado como `current.state.sick-route4center.bak`).

### Orçamento de passos por waypoint

`WAYPOINT_STEP_BUDGET = 300`: teto duro de passos de rota por waypoint. O
contador de distância (`route_no_progress`) só vê "não encostou": um desvio
longo que encolhe a distância devagar zera o contador a cada passo, e o bot
queimava milhares de passos no mesmo alvo. Estourado o orçamento, o waypoint
é gasto — mira o próximo; no último, solta a rota e reentra pelo mais
próximo. Batalha e texto não contam (a rota nem roda neles). O relatório de
travamento agora expõe `waypoint_steps` e `waypoint_budget` — dá para ver o
avanço em janelas fixas de passos.

### Fuga desligada, metas de farm e tipo de missão (2026-08-12)

**Fuga em todas as circunstâncias foi desligada** por decisão do operador:
morrer destrava, fugir empaca. O whiteout é o mecanismo de cura projetado —
o cartucho devolve o time curado ao Centro — e fugir o impede. Medido no
FARON: 2.196 fugas de 2.224 batalhas com o time machucado, nunca morreu,
nunca curou, nível 6 parado. `_next_escape_action` agora devolve `None`
sempre.

**Metas de farm por linha inicial** (operador):

- Bulbasaur/Squirtle: treinar até a primeira evolução (nível 16 nas três
  linhas — o inicial evolui no 16).
- Charmander: além do Charmeleon (16), o time precisa de um Butterfree — a
  linha Caterpie/Metapod evolui no 10 e Confusion no 12 carrega contra o
  Brock.
- Pikachu: ideal contra a Misty — no modo FARM o farm continua até ele
  aparecer (5% na Floresta); no AUTO a captura é por prioridade natural.

**Tipo de missão pela task file** (`blue-agents/tasks/<AGENTE>.txt`):

```
MISSION: AUTO        # recomendado (padrão): farma enquanto as metas faltam
MISSION: STORY       # nunca farma, a rota corre
MISSION: FARM        # farma até as metas (e o Pikachu); a saída é a UX
```

A linha MISSION não muda a tarefa atual; só a missão. O par de retomada do
Bill também foi destravado: a rota `bill-lab-separator` terminava no teclado
do PC (1,4), parede por design, e o bot ficava encurralado em (0,4) (8.160
passos). Agora a rota termina em (1,5) e a interação é virada + A + A
(menu → "BILL's PC" → separador, RAM `D7F2.3`). Validado no cartucho: AARON
concluiu `bill_quest` (gen 93) e ainda venceu a Misty (11 quests, badge no
ginásio m65).

**Ritmo do farm (medido)**: o FARON saiu do nível 6 e está subindo (~8 após
~35 min de corrida, com whiteouts devolvendo ao Centro de Viridian). A meta
da evolução (16) é uma reta longa na curva de XP da Gen I; o operador pode
ajustar a meta ou trocar a missão pela UX a qualquer momento.

### Gate de batalha corrigido: 0xD125 não é texto (2026-08-12)

O gate "texto na tela" usava o `0xD125` — que **lê 1 em qualquer estado,
inclusive fora de batalha** (medido: AARON e FARON parados, 0xD125=1) — e o
controlador apertava A para sempre, sem nunca selecionar golpe: o time
perdia toda batalha de treinador por atrito (FARON contra o Brock: 68
derrotas em sequência, todas por não atacar).

O sinal certo é o `0xCC50`: **106** com a lista de golpes desenhada
(variante de coluna 5) e **94** no seletor 2x2; qualquer outro valor é
texto/animação. A coluna sozinha não distingue (5 é tanto a lista quanto
texto). Reproduzido no cartucho: batalha contra o Brock com C50=106/col=5
= lista de golpes aberta. O gate agora avança só o texto de verdade.

**Ainda aberto (próximo trabalho)**: o FARON continua perdendo o Brock —
com o gate certo, o problema passou para a **escolha do ativo/troca**: a
party dele tem Ivysaur 16 com Vine Whip (4×) mas a batalha termina com o
Pikachu (Thundershock 0× no Onix Ground) ou o Metapod (Harden) no lugar —
a regra de troca (`_next_switch_action`) precisa preferir quem tem golpe de
dano eficaz. E a rota do vermilion (AARON em Cerulean, 11 quests) — a
primeira perna (sair do ginásio) está feita; o caminho completo (Rota 5,
Saffron, Rota 6, S.S. Anne, Cut, Lt. Surge) é o próximo executor.

### Farm validado no cartucho: Ivysaur 16, Pikachu 12, Pewter (2026-08-12)

O loop do farm completou a meta no cartucho: o Bulbasaur do FARON
**evoluiu para Ivysaur (nível 16)** — a primeira evolução na curva medium-
slow levou ~2h de corrida com whiteouts curados no Centro — o Pikachu foi
capturado e subiu ao 12, os Metapods evoluíram (3 evoluções no diário), a
Floresta foi atravessada e o FARON está no Ginásio de Pewter (mapa 54),
prestes a enfrentar o Brock. Checkpoint `center_58` preserva o time.

**Flakiness conhecida do checkpoint**: o manifesto `current.state.meta.json`
some a cada whiteout (o `_invalidate_current_checkpoint` o deleta antes de a
gravação pós-morte confirmar) — quando a gravação falha, a retomada cai no
último Centro (`center_58` — o mais novo — progresso preservado). A
gravação pós-morte funciona quando o mapa já é o Centro no momento da
detecção (medido: `center_58` gravado em 08:34); a investigação fina do
timing fica como trabalho futuro.

### O que ficou: gate de texto em batalha (validado, mantido)

O controlador de batalha era chamado com **texto ainda na tela**: `0xD01C` não é
o menu de golpes, a lista de candidatos saía vazia e a escolha caía no desempate
— e pior, o golpe "escolhido" entrava em `status_moves_used` sem nunca ter sido
lançado, aposentando pelo resto da batalha o melhor golpe de status. Agora texto
na tela (oponente de pé) → única ação é avançá-lo, **antes** de ler golpes.

- `src/simple_battle.py:381` (`get_action`) — gate no topo, evolução e
  aprendizado de golpe preservados (o fluxo de pós-batalha continua entrando).
- Testes: `test_battle_controller.py` (`TextGateTests`, 3 novos).
- **Medido no cartucho** (retomada do AARON, 12.000 passos, corrida de validação):
  batalhas caíram de ~40 eventos/3.000 passos para ~16/12.000, **0 mortes**
  (antes: morte a cada ciclo). O time mantém PP e atravessa mais sem morrer.
- Suíte: **467 testes OK** (464 + 3).

### O que foi tentado e descartado: pegar item ball com A

Hipótese inicial: o waypoint (35,31) do 1F está em cima de uma item ball e o bot
quicava numa caixa de 4 tiles até morrer de atrito. Testado no cartucho, **A de
frente NÃO pega item ball em Gen I** (mochila ficou em 1, bola continuou no
tile, nada mudou após vários A). Item ball é **objeto sólido**: não se pisa, não
se pega por A, não se espera. A rota tem de **contornar** o tile. O código do
pickup foi revertido; ficou só o comentário em `_follow_route` documentando a
regra. `src/map_memory.py` voltou ao estado original.

### O que a medição no cartucho revelou sobre Mt. Moon

O ciclo de morte (death_cycle 217→221, todas em `mt_moon_nav`) **não é PP nem
golpe sem efeito**. É navegação contra o mundo real do 1F:

- A rota do mapa 59 tem waypoint em **(35,31)** — **item ball sólida**
  (`item_id 40`). O bot quicava entre (33-35, 29-33) por **1.425 passos**,
  ~78 batalhas por ciclo, até o time morrer de atrito (Butterfree 37 + Ivysaur
  20 vs Zubat nível 8).
- A sonda (colisão real por ramificação) confirma: **(35,31) e (36,31) não
  entram no componente alcançável** de (34,31). Todas as 6 item balls do 1F são
  inalcançáveis — sólidas mesmo.
- **O mapa 1F está partido em componentes:** a entrada sul (690 tiles) não
  alcança a escada NW (5,5) pelo chão; o oeste (x≤6, y≤19) só conecta vindo de
  outro andar.
- Medições de andares: escada 1F (25,15) → B1F desce num **poço cego** (66
  tiles, sem escada B2F nem saída). Escada 1F (17,11) → B1F corredor de 47
  tiles com escada B2F (17,11) → B2F **pocket de 36 tiles** que volta ao
  corredor. Nenhum chega à saída leste (27,3) do B1F.

### Inconsistência de colisão aberta: oeste do 1F

Em (10,22), o passo L (para (9,22)) **não move no cartucho**, mas `TileCollision`
ao vivo, `static_maps.json` E `terrain.json` todos dizem (9,22) caminhável. As
três fontes concordam entre si e discordam do jogo. Não é NPC (tabela de sprites
vazia na área) nem timing (CFC5=0). Suspeito de mapeamento de tileset do extrator
para esta região. Precisa de investigação própria antes de medir rota a oeste.

### Cuidado: os saves atuais estão doentes

Todos os checkpoints de Centro (`center_41/58/68.state`) foram gravados
**durante diálogo** — `0xCFC4` preso em 1, imune a A e B, imune a tempo.
`current.state` tem `0xD125=1` residual (texto de batalha antigo). Nenhum dos
dois serve para validar uma travessia limpa.

Saves saudáveis para retomada diagnóstica: `trainers/AARON/resume-519e074e99e1f13b.state`
(mapa 59, menu=0).

### Confirmado por RL independente (2026-08-11)

Rodei a política treinada do PokemonRedExperiments (`v2/runs/poke_26214400.zip`,
26M passos, chegou ao S.S. Anne) em cima do save do AARON via `RedGymEnv`:

- Do save `resume-519e...` (1F, perto da escada 25,15): cruzou 1F→B1F em 158
  passos pela escada **(25,15)** e **parou no bolsão cego em (20,27)** por
  50.000+ passos. A política conhece o jogo e mesmo assim desceu para o mesmo
  beco que a medição manual encontrou.
- Conclusão: a escada (25,15) do 1F é comprovadamente um **beco sem saída**
  (medição por sonda + confirmação independente por RL treinada).
- A política treinada não destrava o cruzamento a partir de um estado
  arbitrário: ela foi treinada na própria trajetória, que cruza Mt. Moon por
  outro caminho. Usá-la como oráculo de rota exigiria reiniciar da trajetória
  dela (init.state), o que perde a jornada do AARON.

**A fazer antes de declarar Mt. Moon resolvido:**
1. Investigar a inconsistência de colisão no oeste do 1F (tileset × jogo real):
   em (10,22) o passo L para (9,22) não move no cartucho, mas `TileCollision`,
   `static_maps.json` e `terrain.json` todos dizem caminhável. É o que separa a
   entrada sul da escada NW (5,5).
2. Medir a travessia real por andares com a sonda a partir de um save limpo —
   o cruzamento 1F→B1F→B2F→B1F norte→saída (27,3) usa escadas que ainda não
   foram medidas. Candidatas reais: (13,27)/(23,3) do B1F (que conectam ao B2F
   norte, onde ficam as escadas de volta ao B1F perto da saída), ou a NW (5,5)
   do 1F (bloqueada pela inconsistência do item 1).
3. O sprite em **(24,15)** — `_follow_route` espera 6 passos de paciência e
   depois o fallback anda contra o sprite (abre diálogo, o NPC não sai). É o
   **travamento aberto nº 1 do handoff** revisitado.

## Continuar daqui (2026-08-08)

O bot chega ao Ginásio de Pewter em ~2 minutos de relógio partindo de save novo.
A navegação está resolvida. O que falta ver é a **primeira insígnia**.

### Onde estava a corrida quando esta sessão acabou

Corrida de save limpo, 1 slot (AARON, arquétipo `speedrunner`, Bulbasaur), com o
conserto do adaptador já dentro. Ainda não tinha reencontrado o Brock — precisa
refazer o caminho e treinar até o Vine Whip.

```bash
tail -f runtime/journey.log                      # a corrida
tail -f runtime/marcos.log                       # marcos com tempo de parede
cd blue-agents && ../.venv/bin/python tools/watch_milestones.py AARON --until 3
```

### O que observar

1. **O Vine Whip é usado contra o Geodude?** Era o bug do dia. Se voltar a sair
   Growl, o sintoma é `battle_decision` com `candidates` vazio — procure isso no
   diário antes de qualquer outra hipótese.
2. **O treino para quando o golpe chega?** O portão é o golpe, não o nível.
3. **O apagão devolve para Pewter, não para Pallet?** `0xD719` tem de valer 2
   depois da primeira visita ao Centro de Pewter.

### O Growl ainda não está resolvido na raiz

Dois consertos já entraram e nenhum ataca a causa:

1. `EmulatorAdapter` ganhou `read_rom` — a tabela de golpes chegava vazia;
2. no desempate, golpe de dano passa à frente de Growl.

**A causa real:** o controlador de batalha é chamado com **texto ainda na
tela**. Medido em 10 decisões seguidas do mesmo encontro:

```
battle_text: 1   em 10 de 10
battle_menu:     172, 10, 54, 95, 247, 144, 54, 54, 10 ...
column:          15, 5, 12, 1 ...
```

Nesse estado `0xD01C` não é o menu de golpes — é o que estiver na memória —, a
leitura de `player_moves` sai lixo, a lista de candidatos fica vazia e a escolha
inteira cai no desempate. Os valores de `battle_menu` não são de um menu
desenhado; são de uma tela de texto.

**O conserto certo:** `_choose_move` só deve rodar quando o menu de golpes
estiver de fato aberto. Enquanto houver texto, a única ação válida é avançá-lo.
O sintoma para confirmar é sempre o mesmo — `battle_decision` com `move: {}` e
`candidates` vazio.

### O que ainda trava, em ordem

| # | o quê | onde |
|---|---|---|
| 1 | **Sprite parado bloqueia corredor.** No lab do Oak o corredor tem duas casas e as duas ficam ocupadas por gente; o controlador espera em vez de andar contra o NPC para abrir diálogo. Mesmo caso do CARON parado 450 passos em Mt. Moon. | `_tile_truth`, `SPRITE_PATIENCE_STEPS` |
| 2 | **Saguão do Indigo (174)** precisa de tratamento próprio: tileset e planta diferentes, o controlador genérico de Centro não serve. | `_run_pokemon_center` |
| 3 | **Ownership por corrida em `trainers/`** — item 2 da auditoria, nunca feito. | `run_journeys.py` |
| 4 | **7 executores até o Champion**, mais o Mewtwo fora do caminho crítico. | `docs/QUEST_GRAPH.md` |

## 2026-08-08 — o adaptador de batalha não sabia ler a ROM

O bot chegou ao Brock **com Vine Whip aprendido** e passou a batalha inteira
usando Growl. Não era escolha errada: o seletor de golpe nunca rodou.

`EmulatorAdapter` — o objeto que o controlador de batalha recebe — tinha
`read_byte` e não tinha `read_rom`. `MoveTable.from_memory` devolvia tabela
vazia, e a cadeia inteira desanda a partir daí:

```
tabela vazia → toda potência desconhecida
             → nenhum golpe passa pelo filtro de dano
             → lista de candidatos vazia
             → cai no desempate de status
             → Growl vale 9; Tackle e Vine Whip caem no padrão 50
             → Growl ganha por ser o menor
```

| medido no Brock | |
|---|---|
| decisões de batalha | 203 |
| decisões **com dados de golpe** | **0** |
| Growl escolhido | 110× |
| Vine Whip escolhido | 5× |
| PP de Vine Whip gastos | **0 de 10** |
| HP do Geodude | 33/33, intacto |

Tabela vazia passa a **avisar**. Era o pior modo de falha possível: silencioso e
plausível — o bot parecia estar decidindo, e não estava.

**Lição que vale além deste bug:** um adaptador que implementa parte de uma
interface degrada calado. `EmulatorAdapter` responde `read_byte` e o resto do
sistema assume que ele é uma `Memory`. Ao acrescentar leitura de ROM em
`blue_gym_env`, o adaptador ficou para trás e ninguém notou por um dia inteiro.

## 2026-08-08 — treinar até ter o golpe, não até um nível

Bulbasaur nível 10 perdeu **269 vezes** para o Brock, sempre chegando curado do
Centro — o apagão restaura o time e o log confirma "cura automática". O HP nunca
foi o problema: Tackle é Normal, Rocha resiste, e não existia vitória possível.

O portão é o golpe. Grama, Água ou Luta **com potência** encerra o treino; o
nível 14 é só teto de paciência, para um time que nunca aprende o golpe certo
não ficar preso na grama. Um número de nível é fácil de errar de cabeça — tentei
ler o learnset da ROM nesta sessão e **errei o endereço da tabela**, saiu lixo. O
slot de golpe na RAM não tem esse risco.

### Onde treinar, enfim medido

Era o que tinha errado cinco vezes. A grama e a posição de cada treinador saem de
`static_maps.json`. Na Floresta: **365 células de mato**, todas alcançáveis da
porta sul, e o par escolhido fica a 6-7 passos da porta com os três bug catchers
a mais de vinte casas.

O par é fixado uma vez e não se refaz. "Pisar na grama mais próxima" é rumo fixo
disfarçado — foi assim que uma versão anterior subiu quatorze casas pela coluna
de mato até esbarrar no treinador.

## 2026-08-08 — a ROM está versionada (temporário)

Decisão do operador: repositório privado (confirmado por `gh`: `isPrivate: true`),
só ele e um colega mexem. A regra 1 do `AGENTS.md` fica suspensa e anotada.

**Ao reverter:** tirar `roms/*.gb` do **histórico**, não só do índice. Remover
num commit seguinte deixa o arquivo acessível em todo clone.

A ROM rápida e suas ferramentas (`measure_rom.py`, `patch_rom.py`,
`verify_save_compat.py`, `benchmarks/`) vivem em **`feat/rom-fast-blue`**, não no
master.

## 2026-08-08 — grafo de conhecimento do repositório

`/graphify .` gera `graphify-out/` (ignorado pelo git): **2.299 nós, 4.364
arestas, 140 comunidades**, sendo 2.011 do AST determinístico.

God nodes: `HybridGymEnv` (175 arestas), `ScriptedAgent` (133), `SimpleBattleAgent`
(51). Aparecem **dois `RedGymEnv` distintos** com 48 e 43 arestas — duplicação
real, a mesma classe de problema que fez escrever um `_planned_step` que já
existia.

Serve para perguntar antes de mexer, em vez de ler um bloco e concluir sobre o
arquivo. Aviso registrado: **463 arestas com ponta solta** — os subagentes
geraram ids que o AST não criou.


Este documento registra o estado executável do projeto. Progresso só é
considerado real quando confirmado na RAM de Pokémon Blue e persistido no save.

## 2026-08-07 — cura cancelada, e o que isso arrastou junto

Ordem do operador: **a viagem de volta ao Centro está cancelada; fica até
morrer.** A dança da enfermeira travava o personagem, e um apagão durante o
treino não é problema — o cartucho já devolve o time inteiro, com PP, num
Centro. O que não pode se perder é o **Centro como ponto de retomada**.

Isso derrubou uma cadeia inteira de regras que só existiam para sustentar a
cura:

| saiu | por quê |
|---|---|
| desvio até a porta do Centro por HP baixo | era a viagem de cura |
| desvios de Rota 4, Cerulean (bill e ginásio) e volta a Viridian na Floresta | idem |
| `_next_escape_action` — fugir de selvagem | fugir era a alternativa **barata à viagem**; sem viagem, sobra só ficar preso |
| `FLEE_HP_FRACTION`, `_party_is_worn_out` | só alimentavam a fuga |

E forçou desacoplar o checkpoint, que dependia de cura confirmada mais time
cheio. Sem cura o time nunca mais fica cheio, então a exigência não deixaria
sobrar nenhum ponto de retomada. Agora **estar dentro de um Centro basta**, e a
gravação rearma ao sair — antes era uma vez por Centro por jornada, o que
congelava a retomada na primeira visita.

### O travamento que originou tudo isso, medido

AARON, dentro de Mt. Moon (mapa 59), lido do diário e do relatório:

| sinal | valor |
|---|---|
| eventos no diário | 14.275, **0 ids duplicados** |
| fugas por `no_pokeballs` | **2.093** |
| Zubats (espécie 41) | 1.643 |
| `steps_without_progress` | **2.176** |
| HP do Ivysaur | **1 / 59** |
| `path_to_target` | `RRRRRRRRUURRRRRRRRRRUUUUUUUR` — existia |

A rota do mapa 59 nunca foi o problema: o bot jamais chegou a andá-la. A 1 HP
ele estava abaixo do limiar de 50%, fugia de todo encontro, e não havia Centro
alcançável de dentro de uma caverna. O "diário em loop" era sintoma fiel disso,
não bug de log — zero ids duplicados.

O diário agora **colapsa repetição idêntica em sequência**: a primeira sai na
hora, as seguintes viram uma linha `<tipo>_repeated` com o total.

## 2026-08-07 — treino na Floresta removido, e o que ele deixa em aberto

Saiu a pedido do operador. Estava desligado por padrão (`POKEAI_FOREST_TRAINING`),
e o motivo está no próprio código: o portão de nível era sólido — time cujo
melhor é 8 perde para o primeiro bug catcher, medido duas vezes — mas **onde**
treinar errou cinco vezes na ROM, e cada erro custou uma corrida.

| onde se tentou treinar | resultado |
|---|---|
| linha em y=43 | 1 encontro / 225 passos |
| pernas sul da travessia | 1 / 3765 |
| grama mais distante à vista | andou até o bug catcher |
| grama a 3 tiles | desviou ao norte, idem |
| vaivém de dois tiles | 0 / 1200, preso em 8 tiles |

O que fica provado e vale guardar: `wGrassTile` (`0xD535`) diz qual tile rola
encontro, e `TileCollision.grass_offsets()` acha na tela. O que falta é um
trecho de grama **medido a partir de um save** — alcançável e fora da linha de
visão de treinador.

### O bloqueio que isto não resolve

Removê-lo é limpeza, não conserto. Medido nesta sessão, um bot sozinho partindo
de save novo:

| | |
|---|---|
| lab do Oak → Ginásio de Pewter | **36 segundos** |
| derrotas seguidas depois disso | **1.047** |
| mortes | **1.045** |
| nível do ativo | nunca passa de **10** |

Bulbasaur aprende Vine Whip no 13, e é ele que resolve contra os tipos Terra do
ginásio. Sem treino o ciclo é o previsto na auditoria: *treinador obrigatório →
apagão → mesmo treinador*. A navegação está resolvida; a progressão não.

## 2026-08-07 — `warps.json` estava envenenado, e eu piorei antes de ver

`WarpMemory.record` gravava "o tile onde o bot estava quando o mapa mudou". A
regra parece boa e se envenena sozinha: num apagão o mapa muda sem que ninguém
tenha pisado em porta, e o chão vira porta para sempre.

| | portas |
|---|---|
| Mt. Moon 1F, arquivo aprendido | **62** |
| Mt. Moon 1F, cartucho | **5** |
| Kanto inteiro, arquivo aprendido | 205 em 30 mapas |
| Kanto inteiro, cartucho | **963 em 224 mapas** |

Tiles de chão como `(7,24)`, `(6,21)` e `(10,23)` estavam registrados como
portas para a Rota 4 — e são exatamente onde BARON e CARON ficavam parados.

O agravante foi meu: a correção de "em cima da porta, atravessar" passou a
apertar para baixo em cima desses tiles inventados. Dado envenenado virou
movimento, e daí saiu o vaivém 15↔59.

`blue-agents/tools/extract_warps.py` lê os warps do bloco de objetos de cada
cabeçalho de mapa — quantidade e depois `{y, x, índice, mapa de destino}`, com
`0xFF` gravado como `-1` para o destino que o cartucho resolve em tempo de
execução. Conferido contra cinco portas conhecidas.

A regra nova: **onde há porta é fato de ROM; a observação só resolve para onde
vai um warp dinâmico.** `record` recusa tile que o cartucho não lista.

```bash
cd blue-agents && ../.venv/bin/python tools/extract_warps.py --write
```

## 2026-08-07 — retomada que sobrevive a um kill

A ordem antiga era renomear `current.state` e depois o manifesto. Morrer entre
os dois deixava estado novo com manifesto velho, o sha256 não batia, a retomada
era recusada e o emulador caía no estado de partida. CARON perdeu a jornada
assim duas vezes num dia, as duas quando derrubei a corrida para aplicar
conserto.

Agora o estado vai para `resume-<sha16>.state` e o **manifesto é o único ponto
de commit**: enquanto ele não troca, o par antigo continua inteiro e válido.
`current.state` continua sendo escrito para ferramentas e sondas, mas deixou de
ser autoridade. Estados antigos são podados, os três mais recentes ficam.

## 2026-08-07 — o renascimento é o checkpoint que faltava

Sem parar num Centro, todo apagão devolve a corrida a **Pallet**, e o jogo vira
roguelite. Quem decide isso é `wLastBlackoutMap` (**0xD719**), que guarda o mapa
*de fora* do último Centro usado — 1 para Viridian, 15 para a Rota 4.

**Medido no cartucho, não deduzido:** entrar no Centro **não** move o endereço.
Dirigindo um save de Viridian para dentro do Centro 41, o valor seguiu em 0;
só virou 1 depois de chegar ao balcão em (3,3) e falar com a enfermeira.

Consequência: a cura voltou, mas o gatilho **não é HP**. É "esta cidade ainda
não é meu ponto de renascimento", lido da RAM. A cura é efeito colateral da
única interação que grava o checkpoint interno do jogo. Nenhum limiar de HP
participa, e nenhuma viagem entre cidades acontece — só a caminhada até a porta
que já está neste mapa.

Quem decide que acabou é o cartucho: enquanto `0xD719` não apontar para cá, a
conversa continua. A versão anterior usava um flag `já curei` de processo, que
sumia no reinício e criava o ciclo de entrar e sair.

### Os Centros vêm da ROM agora

`blue-agents/tools/extract_centers.py` gera
`knowledge/maps/pokemon_centers.json`. Como o cartucho responde: **tileset 6**,
**4×7**, e ponteiro de texto seis bytes depois do de script. A porta de cada um
sai da tabela de warps do mapa de fora — nenhuma coordenada medida à mão.

A lista escrita à mão errava dos dois lados:

| | |
|---|---|
| faltava | **81** — Centro da Rota 10, antes do Túnel da Rocha |
| sobrava | **174** — saguão do Indigo: tileset 2, 6×8, sem enfermeira em (3,3) |
| armadilha evitada | **140** — Hotel de Celadon: mesmo tileset e mesmo 4×7, mas texto a +3, 3 NPCs e planta de blocos própria |

| Centro | cidade | porta |
|---|---|---|
| 41 | Viridian (1) | (23,25) |
| 58 | Pewter (2) | (13,25) |
| 64 | Cerulean (3) | (19,17) |
| 68 | Rota 4 (15) | (11,5) |
| 81 | Rota 10 (21) | (11,19) |
| 89 | Vermilion (5) | (11,3) |
| 133 | Celadon (6) | (41,9) |
| 141 | Lavender (4) | (3,5) |
| 154 | Fuchsia (7) | (19,27) |
| 171 | Cinnabar (8) | (11,11) |
| 182 | Saffron (10) | (9,29) |

O saguão do Indigo precisa de tratamento próprio quando a rota chegar lá: a
planta é outra, então o controlador genérico não serve.

## 2026-08-07 — dois escritores em `warps.json`, e um truncava

`knowledge/maps/warps.json` tinha dois escritores com garantias diferentes:

| escritor | como gravava |
|---|---|
| `WarpMemory.save` | relê, funde, `os.replace` — atômico |
| `HiveMind._save_json` | `open(path,'w')` direto — **trunca ao abrir** |

`open(path, 'w')` esvazia o arquivo no instante em que abre. Um `SIGKILL` por
falta de memória no meio — que esta máquina de 8 GB dá sem rastro — deixava o
conhecimento compartilhado de todas as corridas vazio. E o `HiveMind` guardava
a cópia carregada na partida, então com dois agentes no mesmo processo o
segundo a gravar apagava as portas do primeiro.

`HiveMind` passou a delegar para `WarpMemory`: um escritor só, que funde. O
`_save_json` virou atômico de qualquer forma.

### Trava de corrida

`blue-agents/tasks/journey.lock` guarda o PID do dono. Uma segunda corrida é
recusada com o PID e o comando para matar a primeira. Trava de processo morto é
assumida automaticamente — uma trava que sobrevive ao dono trocaria um problema
por outro nesta máquina.

## 2026-08-07 — o diário colapsa ciclo, não só repetição

O primeiro filtro só via repetição **consecutiva** e não pegava o formato que um
bot preso realmente produz: um punhado de eventos *diferentes* em ordem
repetida. Em Mt. Moon eram seis — `battle_started → capture_decision →
battle_decision → battle_end → capture_outcome → battle_escaped` — 2.093 voltas,
12.558 linhas, nenhuma assinatura consecutiva igual.

`blue-agents/event_stream.py` detecta período de 2 a 8. As duas primeiras voltas
saem por extenso, para quem lê ver o padrão; o resto vira uma linha
`ciclo_repetido` com o total. Nenhum evento some da contagem, e progresso real
no meio de um ciclo nunca é suprimido.

O vaivém entre dois mapas é ciclo de período 2 e passa a colapsar também — é a
mesma assinatura que o relatório de travamento procura.

## 2026-08-07 — dados de golpe vêm do cartucho

`MOVE_POWER`/`MOVE_TYPES` escritos à mão tinham 30 golpes de 165. Quem faltava
valia potência 0, e potência 0 é lido como "não serve para atacar" — o golpe era
descartado e a vez ia para um de status. Um Pikachu com Thundershock escolhia
Growl, porque a tabela tinha o 85 (Thunderbolt) e não o 84.

`src/move_data.py` lê o banco `0x0E`, 6 bytes por golpe, `{animação, efeito,
potência, tipo, precisão, PP}`. Conferido contra dez golpes canônicos e contra o
próprio PyBoy. Desconhecido responde `None`, não 0: 0 é afirmação do cartucho,
`None` é ausência de leitura.

## 2026-08-07 — conclusão de quest carimbada por geração

`journey.json` e o checkpoint andavam em relógios separados, e a conclusão era
sticky. Morrer entre "quest confirmada na RAM" e "checkpoint gravado" devolvia
um emulador antes de Mt. Moon com o journey jurando a caverna atravessada.

Cada checkpoint carimba `generation` no manifesto; cada conclusão guarda a
geração em que foi observada. Na retomada só continua de pé quem tem checkpoint
numerado acima. Isso tornou desnecessário o `DURABLE_QUEST_PREDICATES`, que
deixava `map_in` e `pokeballs_stocked` de fora — **cinco nós de navegação nunca
eram rechecados** e viravam verdade permanente.

### Limitação declarada

Os testes provam a lógica de selagem em nível de unidade, com estado falso. O
teste de SIGKILL real no emulador, nos três momentos (antes do feito, depois do
feito e antes do Centro, depois do Centro), **ainda não foi rodado**.

## A rota à mão é o caminho principal

Definido com o operador em 2026-08-06. **O caminho feito à mão é o que leva a
história para frente e é o foco.** Exploração, trilha minerada e trilha densa
são aceleração opcional. O objetivo é zerar o jogo e ter um caminho
determinístico para zerar, no qual o bot possa **entrar em qualquer ponto e
seguir**.

Consequência direta no código: `_follow_route` deixou de deixar a trilha
sobrepor a rota. Trilha continua sendo **gravada e publicada** — é a medida do
que uma travessia custou — mas *segui-la* é opt-in por `POKEAI_FOLLOW_TRAILS=1`.
Uma trilha errada só precisa acertar uma vez para custar uma hora: um único
ponto minerado na Rota 4, em `(27,3)`, apontava para leste, o que tornou o eixo
de desvio vertical, e ao sul daquele tile é a Rota 3.

### Até onde o caminho determinístico chega

| | |
|---|---|
| nós do grafo | 19 |
| com rota à mão | **11** (2 via `walkthrough.json`, 9 via `_run_*`) |
| último validado | `cerulean_gym_quest` — Misty |

Faltam **8 executores**, e é isso que separa o projeto de zerar:

| # | nó | executor ausente |
|---|---|---|
| 1 | `vermilion_gym_quest` | Lt. Surge |
| 2 | `celadon_story_quest` | Erika / Rocket |
| 3 | `fuchsia_story_quest` | Koga |
| 4 | `saffron_story_quest` | Sabrina / Silph |
| 5 | `cinnabar_story_quest` | Blaine |
| 6 | `viridian_gym_quest` | Giovanni |
| 7 | `pokemon_league_quest` | Elite Four |
| 8 | `mewtwo_postgame` | Cerulean Cave |

Cada um precisa de waypoints **medidos**, não deduzidos. Cinco palpites de
geometria nesta sessão erraram cinco vezes; `tools/probe_route.py` a partir de
um save é a ferramenta que responde.

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
laços e publica a melhor de cada em `knowledge/routes/`. E **corta tudo o que
veio antes da última morte no trecho**, justamente para não ensinar o desvio da
derrota como rota. O que sai dele é âncora esparsa, e perde para uma travessia
gravada passo a passo assim que alguém andar aquele trecho (ver "Trilha densa").

### O que atacar, na ordem

1. ~~**Menos passos por quest.**~~ Feito — ver "Trilha densa" abaixo.
2. ~~**Ciclo de morte explícito.**~~ Feito — ver "O ciclo de morte" abaixo.
3. **Treinar antes de entrar.** Não existe nó de treino: nível sobe por
   acidente, nas batalhas do caminho. Um predicado `party_max_level >= X` antes
   da Floresta e antes de Mt. Moon evitaria metade das mortes.

## Trilha densa: o caminho inteiro, não os carimbos

Implementado em 2026-08-06. O gravador já rodava a cada passo — o que se perdia
estava depois dele, em dois lugares.

`legs()` comprimia a travessia em pontos de virada antes de publicar. Isso é
reversível enquanto um passo é um tile, mas some assim que existe um pulo
(ledge, warp, whiteout). Agora publica **uma posição por tile pisado**, com os
laços desfeitos: ir até uma parede e voltar não é caminho, e um seguidor que
herdasse o laço o andaria de novo de propósito. `legs(dense=False)` continua
existindo para quem só quer as viradas.

O segundo lugar é o que travava tudo: **`publish` guardava a mais curta**. As
dez trilhas publicadas hoje são todas mineradas de log, de 2 a 15 pontos, e sob
essa regra nenhuma travessia real jamais as substituiria. Pior, elas mal são
trilhas — o log só grava coordenada quando acontece um evento, então quase toda
perna tem **um ponto só**:

| Trilha publicada | pernas (mapa, pontos) | mapas que dizem algo |
|---|---|---|
| `viridian_forest_nav` | 9 pernas, **todas de 1 ponto** | 0 |
| `route_2_nav` | 7 pernas, todas de 1 ponto | 0 |
| `mt_moon_nav`, `start` | idem | 0 |
| `brock_quest` | 10 pernas, três com 2+ | 3 |

Uma perna de um ponto é carimbo de passagem: `waypoints_from` devolve um item,
o seguidor pisa nele e devolve o passo para a rota desenhada. O critério novo
ordena por **alcance, densidade, brevidade** — e alcance conta só as pernas com
dois pontos ou mais, senão um monte de carimbos venceria uma travessia que sabe
cada tile. Brevidade em último lugar é literalmente "menos passos por quest":
entre duas travessias andadas, a mais curta ganha.

`mine_trails.py` deixou de publicar com `force`. Ele continua sendo o que existe
enquanto ninguém andou o trecho gravando; deixou de poder derrubar quem andou.

**Medido no cartucho**, a partir de `states/viridian-passed-AARON.state`, 900
decisões, duas batalhas selvagens no caminho:

| | antes | depois |
|---|---|---|
| `viridian_forest_nav` publicada | 9 pontos, 9 pernas de 1 ponto | **95 pontos, uma perna** |
| saltos entre pontos consecutivos | — | **0** (caminho fechado) |
| tiles andados / pontos guardados | — | 97 / 95 (dois laços desfeitos) |

## Largada escalonada: como a trilha vira medida

Montado em 2026-08-06. Três bots largando juntos descobrem o mesmo mapa três
vezes: ninguém pode herdar uma trilha que ainda não foi publicada, e o caminho
publicado nunca é testado. Escalonados, o primeiro atravessa às cegas e os de
trás partem do que ele provou — e o custo de cada travessia fica registrado.

```bash
POKEAI_STAGGER_STEPS=1500 python3 start.py --slots 2 \
    --init-state states/viridian-passed-AARON.state
```

**Dois slots, não três.** `--slots 3` levou `SIGKILL` duas vezes em 2026-08-06,
nas duas o worker morreu com código `-9` sem deixar rastro no log — foi o que
fez uma corrida anterior "sumir" sem erro nenhum e deixar os treinadores
congelados no meio do mapa. A máquina tem 8 GB e o swap estava em 5,4 GB de 6.
O aviso do `run_journeys.py` ("2 é o limite térmico seguro num laptop sem
ventoinha") vale para memória também. Dois bastam para o experimento: um
atravessa às cegas, o outro herda.

| Peça | O que faz |
|---|---|
| `POKEAI_STAGGER_STEPS=N` | slot *k* espera *k·N* decisões, **na ordem dos slots** |
| `--init-state <save>` | todo treinador sem retomada começa no mesmo tile |
| `directives.py set <A> --stop-at <nó>` | mesmo objetivo para os três |

O escalonamento antigo (`POKEAI_STAGGER_START=1`) era um atraso **aleatório** de
0 a 10s, e continua onde estava. Aleatório não serve aqui: a ordem é o
experimento.

**A vantagem é paga uma vez.** Um chunk é um processo novo com `steps_elapsed`
zerado, então sem memória o último slot pagaria o atraso de novo a cada chunk e
nunca alcançaria os outros. `head_start_served` fica em `journey.json`, gravado
no instante em que a espera termina.

O que medir, tudo já no log: `trail_published` traz `steps`, `points`, `maps` e
`death_cycle` da travessia que venceu; `death` traz `death_cycle`, `quest_id` e
`steps_in_cycle` do que aquela tentativa custou. Comparar o primeiro bot (às
cegas) com os de trás (com a trilha) é subtrair dois números do mesmo evento.

Corrida montada nesta sessão: AARON e BARON saindo de `viridian-passed-AARON`,
`stop_at = mt_moon_nav` (9 dos 19 nós), 1500 passos de intervalo. As jornadas
anteriores estão preservadas em `trainers/.reset/`.

### Já medido em produção: trilha densa por cima de carimbo

Antes de a corrida certa subir, uma corrida de jogo novo publicou três trilhas
gravadas passo a passo por cima das mineradas:

| trilha | antes | depois |
|---|---|---|
| `parcel_event` | 6 pontos minerados | **79 pontos andados** |
| `start` | 4 pontos minerados | **31 pontos andados** |
| `oak_event` | 2 pontos minerados | 5 pontos andados |

`parcel_event` é a prova do critério novo: 79 pontos substituindo 6. Pela regra
antiga — "a mais curta ganha" — essa travessia real teria sido **recusada**, e
os seis carimbos ficariam publicados para sempre.

## Treinar antes da Floresta: cinco tentativas, nenhuma serve (desligado)

**Estado: desligado.** Liga com `POKEAI_FOREST_TRAINING=1`. O portão em si está
certo — time cujo melhor é nível 8 perde para o primeiro apanhador de insetos,
medido duas vezes, dez passos depois de entrar. O que nunca acertei foi **onde
treinar**, e cada erro custou uma corrida:

| onde | resultado no cartucho |
|---|---|
| linha em `y=43` | 1 encontro em 225 passos |
| pernas sul da travessia | 1 em 3765 |
| mato mais distante à vista | andou até o apanhador de insetos |
| mato mais próximo em 3 tiles | contornou pelo norte, mesmo lugar |
| vaivém de duas casas | 0 em 1200, preso em 8 tiles |

O padrão é sempre o mesmo e é o erro que este documento já nomeia: **decidi onde
ficava o mato em vez de perguntar**. As três primeiras foram geometria
adivinhada; a quarta e a quinta liam o mato certo e mesmo assim andavam, porque
qualquer caminho traçado ali passa por onde o apanhador está.

**O que ficou provado e vale manter:**

| Fonte | Endereço | O que dá |
|---|---|---|
| tile de mato do tileset | `0xD535` | qual tile gera encontro |
| mapa de tiles da tela | `0xC3A0` | onde esses tiles estão |

`TileCollision.grass_offsets()` junta os dois e funciona. Também ficou provado
que a rota da travessia **segue o caminho de terra** — por isso pacear em cima
dela não encontra nada — e que a entrada sul da Floresta é toda warp
(`(15,47)` a `(18,47)`), o que quebrou uma das versões contra a regra "porta é
destino, nunca atalho".

**O que falta:** um trecho de mato medido a partir de um save, sabidamente
alcançável e sem treinador no caminho. `tools/probe_route.py` é a ferramenta
para isso. Cinco palpites dizem que precisa ser medido, não deduzido da rota.

## Onde fica o mato, e por que a rota não passa nele

Implementado em 2026-08-06 (item 3 da lista de "o que atacar"). Os dois
treinadores morreram para o **mesmo** treinador da Floresta, dez passos depois
de entrar, com o time do save de referência (melhor nível 8). O Caterpie
selvagem daquele mato é nível 3; os níveis estão ali para pegar.

`_run_viridian_forest_nav` agora treina antes de atravessar enquanto
`party_max_level < FOREST_MIN_LEVEL` (12). Com orçamento
(`FOREST_TRAINING_STEPS`): portão sem saída é pior que morte, então se o mato
não entregar os níveis, atravessa assim mesmo.

### O corredor escolhido a olho não é mato

Foram duas tentativas erradas antes da certa, e o cartucho reprovou as duas:

| corredor | passos de treino | batalhas |
|---|---|---|
| linha em y=43, "parecia a entrada" | 225 | 1 |
| pernas sul da própria travessia | 3765 | 1 |
| **mato lido de `wGrassTile`** | **27** | **1** |

A rota da travessia **segue o caminho de terra** — é para isso que ela foi
desenhada. Pacear em cima dela não encontra nada.

Quem responde é o cartucho, como sempre:

| Fonte | Endereço | O que dá |
|---|---|---|
| tile de mato do tileset | `0xD535` | qual tile gera encontro |
| mapa de tiles da tela | `0xC3A0` | onde esses tiles estão |

`TileCollision.grass_offsets()` junta os dois. O treino anda até o tile de mato
**mais distante à vista** — longe o bastante para a ida ser uma caminhada dentro
do mato — e mantém o alvo até chegar nele ou ele deixar de ser mato, porque
reescolher a cada passo é como um plano começa a quicar entre dois tiles.

Medido a partir de `viridian-passed-AARON.state`: `wGrassTile` = 32, e havia uma
coluna de mato em **x=27, y 20..28**, nove tiles a oeste do corredor que eu
tinha escolhido.

### Porta é destino, e o treino tinha furado essa regra

Visto rodando, minutos depois de entrar: BARON atravessava portão ↔ Floresta
**a cada frame**. `_follow_route` só bloqueia passo em warp enquanto **não** está
mirando o último waypoint — rotas terminam em porta de propósito. Um alvo de
treino é sempre o último waypoint, então em cima de `(17,47)` o passo de volta
pela porta ficava livre.

E a entrada sul da Floresta é toda warp: `(15,47)`, `(16,47)`, `(17,47)`,
`(18,47)`. Agora o treino recusa escolher porta como mato, e em cima de uma
porta devolve o passo para a rota, que sabe sair de soleira.

**Não validado ponta a ponta:** o harness headless de validação trava dentro de
uma batalha (`0xD057` continua 1 até o fim dos passos), então não dá para
confirmar ali que o nível sobe até 12 — só que o mato é encontrado e a batalha
começa. Vale olhar no cartucho de verdade se a luta longa é do harness ou é
real; uma corrida anterior mostrou AARON com `switch_intent` repetido numa luta
demorada.

## 4067 paredes que nunca existiram

Achado em 2026-08-06, e é a causa maior desta sessão. BARON passou **4260
passos** no tile (6,30) da Floresta. O relatório de travamento explicava sem
rodeio: `caminho até o alvo: nenhum | fronteira: nenhuma`.

Não era o waypoint nem a colisão ao vivo. O mapa acumulado
(`knowledge/maps/terrain.json`, compartilhado por todos os treinadores) tinha a
Floresta partida em **quatro pedaços sem ligação entre si**:

| componente | tiles | faixa |
|---|---|---|
| onde BARON estava | 300 | y 23..47 |
| nordeste | 215 | y 1..19 |
| noroeste, com o alvo `(7,3)` | 160 | y 0..29 |
| órfão | 1 | — |

676 tiles caminháveis contra **1144 paredes**. `find_path` respondia "nenhum"
corretamente: o alvo estava do outro lado de uma parede inventada.

E não era só a Floresta. **14 dos 17 mapas conhecidos estavam partidos** — Rota
2 em 12 pedaços, Rota 1 em 8, Rota 3 com o dobro de paredes que de chão livre.

### A causa estava escrita no código, e o conserto tinha ficado pela metade

Um comentário em `_planned_step` já descrevia tudo — inclusive o tile:

> *"In a battle the tile map holds the battle graphics, and every tile reads as
> a wall: those readings were stored as permanent geometry, and after a few
> fights in tall grass the Forest was remembered as a closed pocket — from
> (6,30) the map offered no path to any waypoint."*

A trava foi posta (só lê terreno fora de batalha e fora de menu) e **os dados
gravados antes dela nunca foram limpos**. Nada no projeto desaprende uma parede:
o planejador desvia dela para sempre e o bot nunca mais olha aquele tile.

**A assimetria é o ponto.** Um tile marcado caminhável por engano custa uma
esbarrada — o passo falha, a leitura ao vivo recusa, segue o jogo. Um tile
marcado parede por engano é permanente e invisível.

### As duas metades do conserto

**Os dados.** `blue-agents/tools/forget_walls.py` descarta as paredes e preserva
os caminháveis, com cópia do anterior em `knowledge/maps/.envenenado/`:

```bash
./blue-agents/tools/forget_walls.py --dry-run   # mostra quais mapas estão partidos
./blue-agents/tools/forget_walls.py             # esquece as paredes
```

Depois disso, `(6,30) -> (7,3)` responde em 28 passos. Desconhecido conta como
livre, então esquecer parede não cega o planejador: ele volta a ser otimista e
cada passo troca otimismo por leitura.

**A leitura.** `terrain_grid()` agora devolve `{}` quando a tela não é o mapa.
Duas perguntas, as duas ao cartucho, nenhuma a um flag:

| Fonte | Endereço | O que responde |
|---|---|---|
| janela do LCD | `0xFF4A` | tem algo desenhado por cima do mapa? `144` = não |
| tile sob o jogador | `wTileMap` na linha 9 | é lugar onde dá para estar de pé? |

A **primeira é a que cobre conversa forçada**. Uma caixa de texto não impede o
tile do próprio jogador de continuar sendo mapa, então a segunda verificação
passa direto por uma cutscene enquanto a caixa sobrescreve os tiles embaixo
dela. Medido no cartucho: abrir o menu START transformou **duas colunas de mapa
em parede** neste mesmo tilemap. Batalha, menu, loja e diálogo de cutscene
baixam a janela; só o mapa a deixa estacionada fora da tela.

A segunda é a rede de segurança para o que a janela deixar passar.

Medido no cartucho, nas três telas:

| tela | `WY` | regra antiga | regra nova |
|---|---|---|---|
| mapa limpo | 144 | 80 tiles | **80 tiles** |
| menu START aberto | 0 | 2 colunas viram parede | **0 gravados** |
| em batalha | 0 | **78 paredes inventadas** | **0 gravados** |

### O furo que sobrou: ler no meio do passo

As duas verificações acima não bastaram. Duas horas depois da primeira limpeza,
**1075 paredes novas** e a Floresta partida em dois de novo, com `(7,22)` — um
waypoint da rota à mão — encalhado do lado inacessível.

`0xCFC5` é o contador de passo: `0` parado, `7..1` enquanto o passo toca. As
coordenadas do jogador só alcançam no fim, mas **a tela já rolou meio tile**.
Então a leitura está certa e a origem está errada: os 80 tiles são gravados uma
linha fora. Medido de `(31,24)`:

| | tiles livres lidos |
|---|---|
| parado em `(31,24)` | 24 |
| no meio do passo, ainda reportando `(31,24)` | **27** — que é a resposta de `(31,23)` |

Um mapa costurado com leituras cada uma um tile fora cria paredes que nunca
existiram, e elas parecem plausíveis. Agora `terrain_grid()` devolve `{}`
enquanto `0xCFC5 != 0`. Conferido no cartucho: dos 25 frames de um passo, 21
são recusados e os 4 alinhados devolvem 24 e 27 livres, cada um na sua casa.

| Fonte | Endereço | O que responde |
|---|---|---|
| janela do LCD | `0xFF4A` | tem algo por cima do mapa? `144` = não |
| contador de passo | `0xCFC5` | o passo terminou? `0` = sim |
| tile sob o jogador | `wTileMap` linha 9 | é lugar onde dá para estar de pé? |

## Centro e Mart mais próximos: a porta é pergunta, não medida

Implementado em 2026-08-06, e fecha a pendência que este documento carregava:
*"o `buy_pokeballs` só sabe voltar ao Mart de Viridian... Um controlador de
'reabastecer no Mart mais próximo' ainda não existe."*

O que forçou: AARON gastou a última Poké Bola na Rota 1 e passou o resto da
corrida com `choice: defeat, reason_code: no_pokeballs`. A política estava
certa; faltava caminho de volta.

### O quarto byte do warp

A tabela de warps tem 4 bytes por entrada e o projeto só lia os dois primeiros —
**onde** a porta está. O quarto diz **para onde ela vai**:

| Fonte | Endereço | O que dá |
|---|---|---|
| número de warps | `0xD3AE` | quantas portas |
| tabela de warps (y, x, destino, mapa) | `0xD3AF` | onde estão **e para onde vão** |

`TileCollision.warp_destinations()` devolve `{(x,y): mapa}`. Com isso, "andar
até o Mart" deixa de ser uma rota medida à mão para uma cidade e vira uma
pergunta que o cartucho responde em qualquer uma.

A outra metade é que **Gen I constrói o mesmo prédio em toda cidade**: enfermeira
em `(3,3)`, capacho em `(3,7)`, balconista atrás do balcão superior esquerdo,
aproximação em `(2,5)`. O interior nunca precisou ser medido por cidade — só
ninguém tinha separado "achar a porta" de "usar o prédio".

### Medido no cartucho

Dirigindo da Floresta até Viridian e lendo a tabela da cidade:

```
portas de Viridian: {(23,25): 41, (29,19): 42, (21,15): 43, (21,9): 44, (32,7): 45}
porta do Centro : (23, 25)
porta do Mart   : (29, 19)
```

`(23,25)` é exatamente onde a rota medida à mão (`viridian-center-door`)
termina. O mecanismo genérico reproduziu sozinho o número que alguém mediu.

### Ligado como rede, não como substituto

Nada foi trocado: as rotas que já funcionam continuam ganhando. O controlador
novo só entra onde o bot antes se perdia — `buy_pokeballs` fora do mapa 42
pergunta se *esta* cidade tem Mart antes de desistir, e a cura procura porta de
Centro em qualquer mapa que as ramificações medidas não cobrem. Sem porta, devolve
`None` e o comportamento antigo segue igual.

`POKE_MART_MAP_IDS = {42}` — só o de Viridian, que é o único em que este projeto
entrou e comprou. Um id errado manda o treinador pela porta errada, então o
conjunto cresce por medição, nunca por memória.

`POKEMON_CENTER_MAP_IDS` era declarado **duas vezes**, em `hybrid_agent.py` e
implicitamente nas rotas. Agora vive num lugar só e o outro importa — duas
cópias do mesmo conjunto é como elas divergem em silêncio, o mesmo erro que já
custou o contador de ciclo de morte e a vantagem de largada nesta sessão.

### O cérebro compartilhado se perdia numa morte no meio da escrita

`latest_policy.zip` era gravado direto por cima de si mesmo. Um `SIGKILL` no
meio — e três slots em 8 GB levam `SIGKILL` — deixa um zip pela metade, e toda
corrida seguinte recusa com `wasn't a zip-file`. O aviso aparece uma vez no
início do bloco e some no meio do log; o cérebro compartilhado fica ausente até
alguém apagar os destroços à mão.

Agora grava ao lado e move por cima, como todo arquivo compartilhado deste
projeto. Um detalhe custa uma corrida se passar batido: `model.save` só
acrescenta `.zip` quando o caminho **não tem sufixo**, então o nome de estágio
não pode ter ponto — `latest_policy.next` seria gravado literalmente e o move
procuraria um arquivo que não existe.

## DOWN eterno no menu de golpes: linha 0 não é linha

Visto rodando em 2026-08-06. AARON ficou **dois minutos apertando DOWN** contra
um Rattata nível 2, segurando um Tackle com 35 de PP no slot 0. O operador
descreveu como "bugou na mochila"; a mochila estava certa — `capture_decision`
respondeu `choice: defeat`, `reason_code: no_pokeballs`, porque o inventário
estava zerado. Quem travou foi o menu de golpes.

A lista de golpes é numerada **a partir de 1**, então o slot 0 quer a linha 1.
Quando `0xCC26` devolve `0` — o byte do cursor segurando algo que não é esta
tela — `0 < 1` é verdade, o comparador responde `DOWN`, a tecla não muda nada, e
o passo seguinte lê `0` de novo. Para sempre.

É o mesmo erro que o menu 2x2 já tinha corrigido ("coluna inválida → `B`") e que
esta tabela do documento nomeia: *aperta DOWN eternamente na luta*. Agora linha
fora de `1..4` não navega — devolve avanço de texto, que nunca escolhe um golpe
por acidente.

**E o evento não sabia dizer por quê.** `battle_decision` gravava
`action: DOWN` sem os bytes que produziram a decisão; `last_decision["menu"]`
tinha `battle_menu`, `column`, `row` e `desired_row`, e ninguém publicava. Agora
publica. Regra 6 deste documento: evento observável, com motivo **e dado bruto**.

## Três travamentos vistos rodando, e o que cada um era

Registrado em 2026-08-06, com os três treinadores da corrida `--slots 3`
(AARON, BARON, CAARON). Nenhum dos dois primeiros aparecia no
`stuck_report.py`, e o motivo de não aparecer faz parte do diagnóstico.

### Carimbo não é trilha — AARON atravessava a fronteira a cada 0,6 s

AARON ficou uma hora indo e voltando entre Rota 3 e Rota 4:

```text
Route 4 [10,17] → Route 3 [61,0] → Route 4 [9,17] → Route 3 [60,0] → …
```

Não era a fronteira, e não era colisão. A trilha `mt_moon_nav` publicada é
minerada de log e tem **uma perna com um ponto só** no mapa 15: `(27,3)`. Um
ponto sozinho ainda vence a rota desenhada — e é longe, a leste. Com o alvo a
leste, o eixo principal vira horizontal; com o eixo principal horizontal, o
desvio vira **vertical**; e para o sul, dali, é a Rota 3.

Reproduzido com a trilha real em disco, no mesmo tile, mudando só se a trilha
existe:

| bloqueio em (10,17) | com a trilha | sem a trilha |
|---|---|---|
| nada | `R` (alvo `(27,3)`) | `U` (alvo `(11,6)`) |
| `U` parede | `R` | `R` |
| `U` e `R` parede | **`D` → volta para a Rota 3** | `L` |

`waypoints_from` agora **ignora perna com menos de dois pontos**. É o mesmo
critério que o `publish` usa para medir alcance, e desarma de uma vez as dez
trilhas mineradas que estão em disco sem apagar arquivo nenhum. Quatro delas
(`viridian_forest_nav`, `route_2_nav`, `mt_moon_nav`, `start`) são **só**
carimbos e passam a não dizer nada; as outras seis mantêm as pernas de verdade.

### Caixa de texto sem fim — CAARON parado em Oaks Lab

CAARON ficou em `(5,1)` do mapa 40 com os passos correndo e a posição fixa, por
mais de dez minutos, sem escrever uma linha de `stuck.jsonl`. As duas coisas têm
a mesma causa: com `0xCFC4` de pé, `_follow_route` devolve `B`/`A` e **retorna
antes** de `_report_if_stuck`. Um bot preso em texto é invisível para o relatório
de travamento, por construção.

`MENU_PRESS_LIMIT = 12` existia para isso e **não era lido por ninguém** — a
correção descrita em "Três travas que só aparecem no cartucho" sobreviveu como
constante e sumiu como comportamento. Agora são 12 toques, 12 passos andando
assim mesmo, e de novo. O D-pad é ignorado enquanto há texto de verdade, então
tentar andar é de graça; o que não pode é ler o passo falhado como parede, e a
memória de esbarrão já se recusa a gravar com o flag de pé.

### `map_entry_tiles`: lido, nunca escrito

`_leave_unknown_map` documenta sair pela porta por onde entrou, e lia
`self.map_entry_tiles` — um atributo que **nenhuma linha do projeto escrevia**.
A estratégia principal era código morto; sobravam a porta conhecida em
`warps.json` e o palpite cego para o sul. Agora a chegada é gravada onde a troca
de mapa já é detectada, em `_follow_route`.

### O que isso deixa em aberto

O `stuck_report.py` não viu nenhum dos dois. Vaivém entre mapas reseta a chave
de progresso a cada travessia, então "passos sem encurtar a distância" nunca
cresce; e o laço de texto retorna antes do relatório. Duas formas de travar que
o detector não enxerga.

## O ciclo de morte

Implementado em 2026-08-06. O whiteout já era detectado; o que faltava era
tratá-lo como **começo**, não como tropeço no meio.

`_close_death_cycle()` numera a tentativa que acabou e começa a seguinte. O
evento `death` passou a carregar `death_cycle`, `quest_id` e `steps_in_cycle` —
quantos tiles aquela tentativa custou antes de morrer. O evento
`trail_published` carrega os mesmos números do lado que deu certo: qual ciclo
virou rota, quantos passos, quantos pontos, quais mapas.

**O número tem que sobreviver ao processo.** Um chunk é um env novo com o
contador zerado, e a primeira versão guardava o ciclo só na memória do processo:
quatro mortes seguidas se registraram como "ciclo 1", e "tentativa 1 contra
tentativa 2" — o motivo inteiro de numerar — nunca ficou mensurável. O contador
agora vive em `journey.json`, gravado no instante da morte, ao lado de
`head_start_served`, que tinha exatamente o mesmo problema.

Junto com o número, a gravação recomeça: tudo o que foi andado até a morte
pertence à tentativa que morreu — a aproximação que perdeu a luta e, antes
dela, a rota que levou até lá. O cartucho já devolveu o treinador ao Centro, e o
próximo tile é o primeiro tile de uma travessia nova. O minerador já cortava por
esse critério; o gravador ao vivo, não, e publicava a derrota junto com a volta.

### Centro no caminho: entra sempre, e o prêmio é o checkpoint

Redefinido com o operador em 2026-08-07, depois de AARON atravessar a Floresta,
chegar a Pewter, entrar no Centro com **53% de HP** e parar de andar.

`_run_pewter_city_nav` só entra no ramo do Centro quando o limite de emergência
(20%) diz sim. A 53% nada casava, e o executor caía no fallback de mapa
desconhecido. **Todo executor tinha o mesmo buraco** — o ramo do Centro estava
escrito cidade por cidade, atrás de um limite pensado para outra pergunta.

A regra agora é uma só, em `_center_first_action`, à frente de todos os
executores:

| Situação | Ação |
|---|---|
| dentro de um Centro, faltando qualquer HP | cura |
| porta de Centro **neste mapa**, faltando qualquer HP | entra |
| time inteiro | segue a rota |
| Centro a uma cidade de distância | é viagem, continua com o executor |

**O limite de 20% não some — ele responde outra pergunta.** Vinte por cento é
"vale atravessar uma cidade?". Aqui não há travessia: a porta está neste mapa.

E o motivo de entrar não é o HP. Uma cura confirmada dentro de um Centro é a
**única coisa neste projeto que grava checkpoint**. Passar por um sem entrar é
jogar fora a única defesa contra whiteout: com checkpoint, morrer custa o
trecho; sem ele, custa a corrida inteira de volta a Pallet.

Os dois lados usarem **o mesmo número** é também o que impede a porta giratória
registrada abaixo: entrar e curar decididos por limites diferentes foi o que
fez um time a 55% entrar, não curar e sair.

A porta vem de `_door_to`, lida da tabela de warps — nenhuma coordenada de
Centro é medida à mão em cidade nenhuma.

**Dentro de um Centro a entrega é incondicional, curado ou não.** A primeira
versão desta regra condicionou o controlador inteiro a "falta HP", e ele é quem
sabe **sair** também: AARON curou, ficou em `(4,7)` — o capacho — com o time
cheio, e aí nada mais o chamava. O executor não tem ramo para "time inteiro
dentro de um Centro", então o passo caiu no fallback de mapa desconhecido e
parou de novo, no mesmo lugar, por outro motivo.

Curar e sair são o mesmo controlador. Só o "andar até a porta vindo de fora"
depende do HP.

### O Centro de Mt. Moon não estava na lista

Visto em 2026-08-07: BARON chegava à Rota 4, ia e voltava da porta do Centro,
entrava em Mt. Moon e **nunca pegava checkpoint**.

O mapa **68** é o Centro da Rota 4, na boca da caverna. Ele estava fora de
`POKEMON_CENTER_MAP_IDS`, enquanto `_run_mt_moon_nav` falava com a enfermeira
dele num ramo próprio — cópia da dança que o controlador genérico já faz. E
essa cópia era o motivo do checkpoint ausente: ela curava o time mas nunca
setava `last_center_healed_map_id`, que é o que o gravador de checkpoint
espera. O flag `mt_moon_center_healed` que ela deixava era escrito e **nunca
lido por ninguém**.

Estar fora do conjunto não é cosmético: o gravador recusa qualquer mapa que não
esteja nele. O trecho mais difícil já alcançado — o que vem logo antes da
caverna — era justamente o único sem ponto de retomada.

O ramo dedicado saiu; o 68 entrou no conjunto e usa o mesmo controlador que os
outros. E para esta classe de erro parar de ser silenciosa, uma cura confirmada
numa sala que o jogo chama de Centro mas que não está no conjunto passa a
emitir `unknown_center` no diário, dizendo que nenhum checkpoint foi gravado
ali.

## Regras de cura, como ficaram

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

O arquivo guarda a travessia inteira, separada em pernas por mapa — um waypoint
só significa alguma coisa dentro do mapa em que foi medido:

```json
{"quest": "route_2_nav", "recorded_by": "AARON", "dense": true,
 "death_cycle": 0, "steps": 97,
 "legs": [{"map": 1, "points": [[29, 20], [29, 19], ...]}, {"map": 13, ...}]}
```

**Entrar na trilha em qualquer altura é o requisito, não um detalhe.** Existe
mais de um caminho certo por um mapa; o que importa é que o caminho escrito
possa ser retomado de onde quer que o bot tenha ido parar — jogado para trás por
um whiteout, empurrado por um NPC, enfiado num bolsão. É isso que a densidade
compra: com quatro âncoras, o ponto mais próximo fica a vinte tiles e a
reentrada é uma caminhada; com um ponto por tile, o mais próximo é o tile do
lado. A propriedade está fixada em teste (`JoinAnywhereTests`): de qualquer tile
do mapa, a trilha responde com o resto do caminho, e o resto nunca cresce.

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
