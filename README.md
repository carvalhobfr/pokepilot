# PokeAI 2026

Bots jogando **Pokémon Blue de verdade** — a ROM original rodando num emulador,
não uma simulação. Você acompanha pelo navegador: o mapa de Kanto com os
treinadores se movendo, o time de cada um, e o diário explicando por que cada
decisão foi tomada.

Cada bot tem um **arquétipo fixo** e joga diferente de propósito: um completista
que quer registrar tudo, um rushador que só para pelo que vale a parada, e um
construtor de time. Mesmas regras, mesmo mapa aprendido, respostas diferentes.

O que garante que nada é inventado: **todo progresso é confirmado lendo a
memória do cartucho**. Um script nunca declara que terminou; a insígnia só conta
quando o bit dela aparece na RAM.

## Quick start

```bash
python start.py
```

Windows: dois cliques em `start.bat`. macOS: `start.command`. Um comando só, e
ele faz tudo:

1. acha o Python do ambiente virtual (`.venv`), criando-o se não existir, e
   instala as dependências que faltarem;
2. libera as portas do dashboard e do WebSocket se sobrou processo de uma
   execução anterior;
3. sobe o relay WebSocket e o dashboard React (Vite) em `localhost:5173`;
4. inicia o supervisor da jornada, que roda blocos de 8192 passos por bot,
   salvando emulador e política entre blocos;
5. abre o navegador. `Ctrl+C` encerra tudo **salvando** o progresso.

Você precisa ter colocado a sua cópia legal da ROM em `roms/PokemonBlue.gb`
antes (Red também serve) — é a única coisa que o script não pode fazer por você.

Opções que valem saber:

| Comando | O que muda |
|---|---|
| `python start.py --slots 2` | quantos bots correm em paralelo |
| `python start.py --no-browser` | não abre o navegador sozinho |

**Dois bots é o teto num laptop de 8 GB.** Três levaram `SIGKILL` (código `-9`,
sem traceback) mais de uma vez: o limite é memória, não temperatura. Se um bot
"desaparecer" sem erro, procure `code -9` no log antes de suspeitar da lógica.

## Começando do zero

Roda em **Windows, macOS e Linux**. Você precisa de três coisas: Python 3.11+,
Node.js, e a sua cópia de Pokémon Blue.

1. Instale [Python 3.11+](https://www.python.org/downloads/) e
   [Node.js LTS](https://nodejs.org).
   **No Windows, marque "Add python.exe to PATH"** durante a instalação do
   Python — é o erro mais comum.
2. Coloque a **sua** cópia legal em `roms/PokemonBlue.gb` (Red também serve).
3. Inicie:

   | Sistema | Como |
   |---|---|
   | **Windows** | dois cliques em `start.bat` |
   | **macOS** | dois cliques em `start.command` |
   | qualquer um | `python start.py` no terminal |

Ele instala o que faltar, sobe o dashboard, abre o navegador e começa a jogar.
A primeira execução demora alguns minutos baixando dependências; as seguintes
sobem em segundos. `Ctrl+C` encerra e salva o progresso dos bots.

Opções úteis: `python start.py --slots 1` roda um bot só (mais leve),
`--no-browser` não abre o navegador sozinho.

> **macOS:** se o sistema bloquear o arquivo na primeira vez, clique com o botão
> direito → *Abrir* → *Abrir*. É o aviso padrão para scripts baixados.
>
> **Windows:** se o SmartScreen avisar, *Mais informações* → *Executar assim mesmo*.

Na tela: arrastar move o mapa, roda do mouse ou pinça dá zoom, e clicar num bot
trava a câmera para acompanhá-lo.

### Quantos bots rodar

O padrão é **2**; `--slots N` muda. O limite não é o número de cores: os
ambientes rodam **em sequência dentro de um processo só**, então a partir de uns
4 bots a vazão total satura e cada bot a mais só divide o mesmo laço.

Medido num MacBook Air M1, mesmo trecho, sem limite de velocidade:

| Bots | Passos/s no total | Por bot | Quantas vezes o ritmo do Game Boy |
|---|---|---|---|
| 2 | 285 | 143 | ~57× |
| 4 | 377 | 94 | ~38× |
| 6 | 381 | 64 | ~25× |
| 8 | 390 | 49 | ~20× |

Ou seja: 6 e 8 rodam bem, e mesmo o mais lotado joga 20 vezes mais rápido do que
alguém conseguiria assistir. Num chassi sem ventoinha, o que decide o limite
prático acaba sendo o calor, não a CPU.

Reduzir o número **não apaga ninguém**: o treinador sai da lista ativa mas
mantém save, diário e progresso em `trainers/`, e volta de onde parou se você
aumentar de novo.

## Continuidade do desenvolvimento

Agentes e novos colaboradores devem começar por [AGENTS.md](AGENTS.md) e pelo
[handoff canônico](docs/HANDOFF.md). Esses arquivos registram o estado real do
save, o limite atual da automação, o bloqueio em andamento e o comando seguro
para continuar sem reiniciar a jornada.

O [mapa visual do QuestGraph](docs/QUEST_GRAPH.md) mostra os 19 objetivos até
Mewtwo e separa claramente o que já foi validado no cartucho, o que possui
executor em validação e o que ainda é apenas planejamento.

## Até onde chega hoje

Medido em 2026-08-17, um bot novo do zero, headless, sem intervenção nenhuma —
e cada linha confirmada lendo a RAM, não o painel:

| marco | confirmação |
|---|---|
| sair de casa, laboratório, escolher o inicial | `party_count`, espécie na RAM |
| encomenda, Poké Bolas, atravessar Viridian | mochila e mapa |
| Floresta de Viridian, farm até evoluir | nível e espécie da equipe |
| **1ª insígnia (Brock)** | bit 0 de `wObtainedBadges` |
| Rota 3, Mt. Moon (1F → B1F → B2F), Rota 4 | sequência de mapas |
| Cerulean, Bill | `completed_quests` |
| **2ª insígnia (Misty)** | bit 1 de `wObtainedBadges` |
| Rota 5 → Underground → Rota 6 → Vermilion | mapas |
| S.S. Anne, capitão, **HM01 e Cut aprendido** | golpe 15 na equipe |

**~1h55 de relógio**, rodando sem plateia (com o painel aberto o emulador é
freado para ser assistível: 320 passos/s contra ~4). Onze dos 19 nós do
QuestGraph concluídos.

**O que ainda não passa:** o ginásio do Lt. Surge — o puzzle das lixeiras é
estado de RAM, não geometria, e não tem executor. Depois dele faltam seis nós
até a Liga. O [handoff](docs/HANDOFF.md) lista cada travamento aberto com o save
e a tela que o causou.

## Que IA tem aqui, exatamente

Vale dizer de frente, porque a expectativa costuma ser outra: **não é um modelo
que aprendeu a jogar Pokémon, e não é um LLM jogando.** É engenharia de agente,
com quatro peças que são IA clássica e uma que é aprendizado por reforço:

| peça | o que é | onde |
|---|---|---|
| **busca** | Kanto como grafo — 49.412 células, 2.152 portas, 106 bordas — e busca em largura de qualquer ponto a qualquer ponto | `src/kanto_graph.py` |
| **planejamento** | 19 objetivos com pré-condições verificadas na RAM; nada é "concluído" por tempo ou por botão apertado | `blue-agents/quest_graph.py` |
| **sistema especialista** | política de batalha lendo tipo, potência e PP da tabela do próprio cartucho | `src/simple_battle.py` |
| **detecção de anomalia** | impressão digital do cartucho a cada passo; estado que não muda, ou volta repetida com o plano parado, viram save + tela gravados | `src/life_watchdog.py` |
| **aprendizado por reforço** | PPO (stable-baselines3) sobre a exploração | `blue-agents/hybrid_agent.py` |

E o RL é a parte **menor**, medida e não estimada — a instrumentação está na
seção seguinte: numa travessia real até o Brock, 0% das ações vieram da rede.
Ela só recebe o passo quando nenhum controlador quer agir, e o rollout inteiro é
descartado se um script sobrescreveu qualquer passo, porque creditar recompensa a
uma ação que a rede não tomou é treinar com dado falso.

Um LLM opcional existe (`src/llm_agent.py`), usado só pelo botão "Ask AI" do
painel. A jornada não depende dele e não acessa a rede.

**O que este projeto demonstra de verdade**, e é o que ele tem de menos comum:
todo conhecimento do mundo é **extraído do cartucho** em vez de adivinhado, toda
afirmação de progresso é **conferida na RAM**, e todo travamento vira save + tela
decodificada + teste de regressão. O histórico disso está no
[handoff](docs/HANDOFF.md), com os erros que custaram mais caro nomeados —
inclusive **4.067 paredes que nunca existiram**, geradas pela versão que
aprendia geometria esbarrando.

## Como os bots acham o caminho

**A geometria vem do cartucho, não de esbarrar.** `tools/extract_map_data.py` lê
parede, mato, treinador, item e porta dos 248 mapas direto da ROM: 238 mapas e
49.412 células em `knowledge/maps/static_maps.json`. A versão anterior aprendia
paredes esbarrando, e isso rendeu 21 mapas e **4.067 paredes que nunca
existiram** — um NPC parado é indistinguível de parede, e uma batalha na tela faz
todo tile ler como parede.

Desde 2026-08-17 as três ligações do mundo estão no mesmo grafo
(`src/kanto_graph.py`): passo dentro do mapa, **borda** entre mapas e **porta**,
as duas últimas extraídas do cabeçalho de mapa e da tabela de warps. Com isso
"ir de onde estou até `(mapa, tile)`" é uma busca só — de Pallet até o Brock são
371 passos cruzando dez mapas, sem uma coordenada escrita à mão. O grafo modela
até o pulo de penhasco, como aresta de mão única.

A ordem de autoridade é fixa e existe porque cada inversão dela custou horas:
**leitura ao vivo > estático do ROM > trilha gravada**, e a rota medida dirige
enquanto alcança — o grafo é a rede quando ela não alcança.

Quem vigia é a **impressão digital do cartucho**: a cada passo, mapa, posição,
equipe, mochila, insígnias e HP de batalha. Conjunto que não cresce, ou a mesma
volta repetida cem vezes, é congelamento — e aí o save e a tela decodificada são
gravados sozinhos, para o defeito virar teste em vez de virar madrugada.

## O que é aprendizado de verdade aqui? (medido, não estimado)

Instrumentando a origem de cada ação numa travessia real até Brock, em 471
passos:

```
battle_controller : 252  (53.5%)   heurística lendo a RAM
quest_controller  : 219  (46.5%)   rotas determinísticas
ppo               :   0   (0.0%)
transições treináveis: nenhuma
```

**Não chame isto de agente que aprendeu a jogar.** É um speedrunner
determinístico com verificação por RAM: reproduzível, auditável e retomável.

O PPO existe no código e só recebe o passo quando nenhum controlador quer agir.
Além disso, `ScriptAwarePPO` descarta o rollout inteiro se **qualquer** passo
foi sobrescrito por script — creditar a recompensa a uma ação que a rede não
tomou seria treinar com dado falso. Como script e batalha dominam a história,
o cérebro praticamente não atualiza durante a campanha.

Os **arquétipos** (`blue-agents/archetypes.py`) fixam traços, starter e — o que
os traços nunca souberam dizer — o que fazer com um selvagem que se poderia
capturar. São a variável do experimento: mesmo mapa, mesmas rotas, decisões
diferentes.

| Arquétipo | Postura diante de uma captura possível |
|---|---|
| Completista | 100% do alcançável em cada área; raridade nunca escapa |
| Rushador | reserva e Pokémon forte; o resto é turno perdido |
| Construtor de time | o que ocupa vaga ou melhora a linha de frente |
| Fogo e dragão | só fogo e dragão no time; a corrida mais difícil de Kanto |

Antes eles eram sorteados a cada execução, e um sorteio ruim já deixou um
treinador abaixo de todo limiar de captura — a corrida inteira pareceu bug.

A meta do completista é **100% do que é alcançável** em cada área — que não é a
mesma coisa que 100% da área. Surf e as varas de pesca trancam tabelas inteiras
de encontro, então o que conta é o que a fase atual pode encontrar: o método de
cada espécie (andar, surfar, vara velha/boa/super) está em
`knowledge/maps/encounters.json`, e o conjunto alcançável cresce sozinho
conforme as insígnias chegam. A mesma área é cobrada de novo mais tarde, sem
nunca exigir o impossível.

Raridade vem antes da cota: Pikachu é 5% da Floresta de Viridian contra 45% de
Caterpie, e nenhuma meta cumprida faz o bot passar batido por ele.

## Estrutura

- `blue-agents/`: ambiente PPO, agentes, WebSocket e dashboard.
- `blue-agents/archetypes.py`: os estilos de jogo, fixos por slot.
- `blue-agents/knowledge/`: QuestGraph, mapa de colisão aprendido, encontros por
  área e os 8 ginásios.
- `blue-agents/tools/`: sonda de rotas e o gerador de conhecimento da PokéAPI.
- `src/`: emulador, memória, navegação (`collision_memory.py`) e batalha.
- `dashboard/`: interface React dentro de `blue-agents/dashboard-react`.
- `roms/`: sua cópia legal, nunca versionada.
- `states/`: estados inicial e preparado para começar com Pokédex.
- `trainers/<AGENTE>/`: save, journey e diário de decisões de cada treinador.
- `archives/<data>-<AGENTE>/`: jornadas encerradas, com manifesto de hashes.

## Rodar

### 1. A ROM (única coisa que você precisa trazer)

Pokémon Blue é software comercial protegido por direitos autorais e **não faz
parte deste repositório**. Cada pessoa traz a própria cópia legal:

    roms/PokemonBlue.gb

`blue-agents/rom_identity.py` identifica o cartucho pelo **cabeçalho**: Red ou
Blue servem, porque os dois compartilham mapas, endereços de RAM e o QuestGraph
inteiro. Yellow não, e é recusada de propósito.

Não há conferência de SHA-1: cartuchos legais são dumpados por pessoas
diferentes com ferramentas diferentes, e exigir um arquivo idêntico só forçaria
uma equipe a passar ROM de mão em mão. O digest continua sendo calculado e
gravado nos arquivos gerados, para uma jornada arquivada dizer de qual dump ela
veio — mas ele nunca decide se o jogo roda.

Todo o resto necessário para rodar está versionado, incluindo os save states de
partida em `states/` e o mapa de Kanto.

### 2. Ambiente

O projeto usa um ambiente virtual local. Se ele ainda não existir:

    cd poke-ai-2026
    python3 -m venv .venv
    .venv/bin/pip install -r requirements-local.txt

Para validar a interface com uma simulação de evoluções e batalhas:

    ./blue-agents/run_all.sh --demo

Abra http://localhost:5173. A arena mostra até quatro batalhas quando você
clicar no botão Arena; ela não abre automaticamente.

Para uma jornada contínua real com exatamente dois slots (padrão seguro para o MacBook Air):

    ./blue-agents/run_all.sh --journeys

O supervisor roda blocos de 8192 passos por agente. Entre blocos, salva a
política e os dois emuladores. Quando um treinador confirma todos os nós até
Mewtwo, ele é arquivado e apenas seu slot recebe o próximo nome; o outro
treinador retoma exatamente de `current.state`. Para uma validação limitada:

    ./blue-agents/run_all.sh --journeys --chunk-steps 1024 --max-chunks 1

Para executar apenas um bloco manual, sem supervisor:

    ./blue-agents/run_all.sh --agents 2 --steps 4096 --resume

Para usar o estado preparado com Pokédex e Pokébolas, apenas para testes mais rápidos:

    ./blue-agents/run_all.sh --state pokedex --fresh-model

Para continuar os estados salvos anteriormente, use explicitamente:

    ./blue-agents/run_all.sh --resume

O dashboard abre a arena de batalhas apenas quando você clica no botão Arena.

## Rever as batalhas

Ninguém acompanha quatro bots lutando ao vivo — mas dá para rever uma luta
depois. O botão **Replays** abre as últimas batalhas de cada treinador, com play,
pausa e passo a passo quadro a quadro.

A gravação só acontece com o painel aberto e em `0.5×`, `1×` ou `2×`. Acima
disso as batalhas terminam mais rápido do que alguém conseguiria assistir, e os
quadros seriam guardados para ninguém. Não custa desempenho: são exatamente os
quadros que a arena já codifica.

## Controles da jornada

O controle no topo do dashboard começa em `1×`, equivalente ao ritmo normal
do Game Boy. As opções são `0.5×`, `1×`, `2×` e `TREINO` (sem limite de
velocidade).

**Com nenhum painel aberto, o limite some sozinho.** Ele existe só para a arena
ser assistível, e custa caro: o mesmo binário fez 4 passos de PPO por segundo
com `1×` e **446** sem limite, no mesmo M1. Fechou a janela, virou treino. O botão principal pausa ou continua o processo inteiro; essa pausa
congela PPO e PyBoy e reduz a carga de CPU. No Command Center, cada treinador
também possui pausa individual sem avançar seus passos de jornada.

Os agentes publicam um `trainer_profile` com nome, starter, personalidade e os
quatro traços. Os dois slots ficam em `blue-agents/tasks/slot_roster.json`.
Concluídos ficam em `archives/<data>-<AGENTE>/`, com `.sav`, `.state`, memória,
decisões, checkpoints, QuestGraph, política compartilhada e manifesto de hashes.
Criação personalizada pelo usuário continua sendo uma fase posterior.

## Perfil recomendado para MacBook Air M1

O caminho padrão é otimizado para treino local: PPO em CPU, dois ambientes,
threads limitadas do PyTorch, sem escrita JSON a cada passo e com rollouts de 128
passos. A visualização continua ativa, mas em uma frequência menor que o loop
do emulador.

Para validar rapidamente sem reaproveitar um checkpoint antigo:

    POKEAI_NO_DELAY=1 ./blue-agents/run_all.sh --steps 512 --fresh-model

Para testar MPS explicitamente, primeiro compare com CPU:

    ./blue-agents/run_all.sh --steps 512 --fresh-model --device mps

O processo recusa MPS quando o PyTorch/macOS não o expõe. Em PPO pequeno, MPS
não é automaticamente mais rápido; o parâmetro fica opt-in para evitar uma
regressão silenciosa.

O frame opcional de batalha usa WebP por padrão para reduzir tráfego e memória.
Use `POKEAI_BATTLE_FRAME_FORMAT=png` apenas para compatibilidade com uma
ferramenta que não aceite WebP.

O QuestGraph é a fonte canônica da ordem da campanha. O detonado textual e os
arquivos em `docs/cidades/` servem como referência; progresso só é confirmado
por flags, itens, mapas e insígnias lidos da RAM real.

## Telemetria real da jornada

O modo real não usa os agentes sintéticos da demo. Cada agente lê a RAM do
PyBoy e registra em `blue-agents/tasks/decision_logs/<AGENTE>.jsonl`:

- mapas, objetivos e checkpoints alcançados;
- início/fim de batalha, vitória, derrota e whiteout;
- golpe escolhido, efetividade, motivo e Pokémon ativo;
- capturas confirmadas pela party/Pokédex, inclusive captura enviada ao PC;
- level up, evolução, depósito no PC e alvo real de XP.
- escolha do starter separada de uma captura normal.

Em batalhas selvagens, a captura só é considerada disponível depois do evento
real `EVENT_GOT_POKEDEX` (retorno da encomenda ao Professor Oak) e quando existe
uma Poké Bola de verdade na mochila. O agente explica se escolheu capturar por
perfil colecionador, por melhoria estratégica do time ou por prioridade rara;
caso contrário, explica que derrotou o encontro para treinar.

Pokémon Blue usa DVs e Stat Experience, não o sistema moderno de IV/EV. Esses
valores poderão alimentar objetivos de qualidade de time mais tarde; shiny não
é requisito específico do produto. Batalhas de treinador nunca tentam captura,
e o log distingue decisão, tentativa e captura confirmada pela RAM.

## Créditos e origem dos assets

Este projeto é um fork de trabalho anterior da comunidade. O crédito fica aqui,
por escrito, em vez de gravado dentro das imagens:

| Origem | O que veio de lá | Link |
|---|---|---|
| **Peter Whidden (PWhiddy)** — *PokemonRedExperiments* | Mapa completo de Kanto (`kanto_big_done1.png`), `map_data.json`, `global_map.py`, base do ambiente Gym e do visualizador | https://github.com/PWhiddy/PokemonRedExperiments |
| **Joseph Suárez (jsuarez5341) / PufferAI** | Ferramental de RL que acompanha o projeto original | https://github.com/PufferAI |
| **PyBoy** | Emulador de Game Boy usado para rodar a ROM real | https://github.com/Baekalfen/PyBoy |

As marcas d'água que vinham embutidas no PNG do mapa (três blocos, sobre a Route
1) foram removidas do asset e substituídas por esta atribuição textual. A
remoção foi feita reconstruindo o padrão de grama do próprio mapa — um tile de
8×8 com duas cores — e não apagou nenhum elemento de jogo. O backup do arquivo
original com as marcas está fora do repositório.

A ROM de Pokémon Blue **não** faz parte deste repositório e não deve ser
commitada. Cada usuário precisa da própria cópia legal; `blue-agents/rom_identity.py`
valida o SHA-1 antes de qualquer execução.
