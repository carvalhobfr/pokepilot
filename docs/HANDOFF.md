# PokeAI 2026 — handoff canônico

Última atualização: **2026-08-04 23:00 (Europe/Madrid)**.

Este documento registra o estado executável do projeto. Progresso só é
considerado real quando confirmado na RAM de Pokémon Blue e persistido no save.

## Objetivo atual

Executar duas jornadas reais simultâneas em um MacBook Air M1, observar jogo,
times e decisões, chegar à Liga/Mewtwo e produzir saves recuperáveis. Login,
monetização, criador de personagem, favoritos, times-alvo, importação de save e
parser de metas PT/EN vêm depois da campanha completa.

O sistema é híbrido:

- PyBoy executa a ROM real;
- QuestGraph + ScriptedAgent controlam história e navegação determinística;
- SimpleBattleAgent opera batalhas pela RAM;
- PPO aprende apenas com transições não roteirizadas;
- React + WebSocket exibem jornada, eventos, time e arena opcional.

Não chamar o projeto de agente puramente aprendido.

## Estado real comprovado

AARON executou no cartucho:

```text
novo jogo → Oak → Squirtle → rival → encomenda → Pokédex → Poké Bolas
→ Viridian Forest → Brock → Mt. Moon → Cerulean → rival
→ Nugget Bridge → Route 25 → Bill/S.S. Ticket → Misty
```

Snapshot persistido em `trainers/AARON/current.state` às 23:00:12:

```text
Mapa: 65 — Cerulean Gym, posição (5, 2)
Quest ativa: vermilion_gym_quest
Insígnias: 2
Party: Wartortle nível 26, 56/78 HP
Golpes: Tackle, Bite, Bubble, Water Gun
Poké Bolas: 1
Nós concluídos: 11 de 19
```

O JSONL confirma a vitória contra Misty, a segunda insígnia e a transição para
`vermilion_gym_quest`. Bill foi concluído pelo evento real e o S.S. Ticket
`0x3F` está na mochila. Rotas de ida/volta em Route 24/25 e recuperação após
whiteout foram exercitadas no emulador.

BARON ainda não possui jornada canônica em `trainers/BARON`; o snapshot antigo
do dashboard não substitui um trainer save. No primeiro bloco do supervisor ele
começa do estado inicial com seu próprio SRAM.

## Próximo bloqueio de jogabilidade

`vermilion_gym_quest` existe no grafo, mas ainda não possui executor. O próximo
trabalho é automatizar e validar:

1. saída do ginásio/cura em Cerulean;
2. casa assaltada, Rocket e TM28;
3. Route 5, Underground Path, Route 6 e Vermilion;
4. S.S. Anne, rival, capitão e HM01 Cut;
5. ensinar/usar Cut, puzzle do ginásio e Lt. Surge;
6. whiteout e retomada em cada trecho.

Depois, repetir o padrão por Celadon/Erika, Fuchsia/Koga, Saffron/Sabrina,
Cinnabar/Blaine, Giovanni, Liga e Mewtwo.

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



Corrigido em 2026-08-05 depois de dois treinadores ficarem permanentemente com
um único Pokémon. Eram três causas somadas, todas em `hybrid_agent.py`:

1. Os ramos de captura exigiam `collector >= 55` ou `meta_score >= 45`. Os
   traços são sorteados por execução; BARON tirou 42 e CARON 52/41, então
   nenhum dos dois alcançava os limiares. CARON não conseguia capturar nada.
2. `upgrade_candidate` julgava só por nível. Um starter nível 9 faz todo
   Caterpie da Floresta parecer pior do que o time atual.
3. `_run_buy_pokeballs` comprava **uma** Poké Bola. Uma tentativa falha
   esgotava o inventário.

Ordem de decisão agora (`_capture_policy`), do mais forte ao mais fraco:

| # | Regra | Código |
|---|---|---|
| 1 | Treinador / captura desativada / história travada / sem bolas | vários |
| 2 | Candidato a shiny da Geração II | `shiny_priority` |
| 3 | **Espécie já na Pokédex → nunca capturar** | `duplicate_species` |
| 4 | **Vaga livre no time + espécie nova → capturar** | `party_slot_new_species` |
| 5 | Time cheio: personalidade decide | `collector_new_species`, `team_upgrade` |
| 6 | Nada disso | `training_value` |

As regras 3 e 4 são novas. A 4 ignora personalidade de propósito: com menos de
`PARTY_TARGET = 6` no time, uma vaga vazia é fraqueza maior que qualquer
preferência. Personalidade volta a mandar só com o time completo.

`STRATEGIC_CAPTURE_VALUE` passou a valer pela **linha evolutiva**, não pela
forma encontrada no mato: Metapod vale 70 porque Butterfree segura as primeiras
horas de Kanto. O que não estiver na tabela continua em 50.

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

## BUG ABERTO: `_follow_route` não replaneja — a causa raiz

Registrado em 2026-08-05. **Bloqueia BARON e CARON.**

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

### Cura antes da Floresta (pendente)

O Bulbasaur do BARON atravessa com `1/25` HP. `_run_pokemon_center` existe e o
Centro de Viridian é o **mapa 41**, mas nenhum passo do `route_2_nav` ou do
`viridian_forest_nav` desvia para curar. O whiteout cura de graça e devolve o
bot ao Centro, então isso não trava a jornada — só desperdiça uma travessia
inteira por vez. Falta a rota da cidade (mapa 1) até a porta do Centro.

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
| `blue-agents/hybrid_agent.py` | orquestração, RAM, eventos, captura e autosave |
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
