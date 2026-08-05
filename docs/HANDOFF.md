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
