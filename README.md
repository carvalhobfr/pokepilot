# PokeAI 2026

Dois bots jogando **Pokémon Blue de verdade** — a ROM original rodando num
emulador, não uma simulação. Você acompanha pelo navegador: o mapa de Kanto com
os treinadores se movendo, o time de cada um, e o diário explicando por que cada
decisão foi tomada.

O que garante que nada é inventado: **todo progresso é confirmado lendo a
memória do cartucho**. Um script nunca declara que terminou; a insígnia só conta
quando o bit dela aparece na RAM.

## Começando do zero

Você precisa de três coisas: um Mac, a sua cópia de Pokémon Blue, e um clique.

1. **Coloque a ROM** em `roms/PokemonBlue.gb` (veja [Rodar](#rodar) para o SHA-1).
2. **Dê dois cliques em `start.command`.**

Ele instala o que faltar, sobe o dashboard, abre o navegador e começa a jogar.
A primeira execução demora alguns minutos baixando dependências; as seguintes
sobem em segundos. `Ctrl+C` encerra e salva o progresso dos bots.

> Se o macOS bloquear o arquivo na primeira vez, clique com o botão direito →
> *Abrir* → *Abrir*. É o aviso padrão para scripts baixados.

Na tela: arrastar move o mapa, roda do mouse ou pinça dá zoom, e clicar num bot
trava a câmera para acompanhá-lo.

## Continuidade do desenvolvimento

Agentes e novos colaboradores devem começar por [AGENTS.md](AGENTS.md) e pelo
[handoff canônico](docs/HANDOFF.md). Esses arquivos registram o estado real do
save, o limite atual da automação, o bloqueio em andamento e o comando seguro
para continuar sem reiniciar a jornada.

O [mapa visual do QuestGraph](docs/QUEST_GRAPH.md) mostra os 19 objetivos até
Mewtwo e separa claramente o que já foi validado no cartucho, o que possui
executor em validação e o que ainda é apenas planejamento.

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

As personalidades alteram starter, limiares de decisão e metadados; elas ainda
não produzem times diferentes por política própria.

## Estrutura

- `blue-agents/`: ambiente PPO, agentes, WebSocket e dashboard.
- `src/`: emulador, memória, navegação e batalha.
- `dashboard/`: interface React dentro de `blue-agents/dashboard-react`.
- `roms/`: ROM local fornecida pelo workspace.
- `states/`: estados inicial e preparado para começar com Pokédex.

## Rodar

### 1. A ROM (única coisa que você precisa trazer)

Pokémon Blue é software comercial protegido por direitos autorais e **não faz
parte deste repositório**. Coloque sua própria cópia legal em `roms/`:

    roms/PokemonBlue.gb

O arquivo precisa ser exatamente esta ROM — o SHA-1 é conferido na
inicialização por `blue-agents/rom_identity.py`, que recusa qualquer outra:

| ROM | SHA-1 |
|---|---|
| Pokémon Blue (obrigatória) | `d7037c83e1ae5b39bde3c30787637ba1d4c48ce2` |

Confira a sua com:

    shasum roms/PokemonBlue.gb

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

## Controles da jornada

O controle no topo do dashboard começa em `1×`, equivalente ao ritmo normal
do Game Boy. As opções são `0.5×`, `1×`, `2×` e `TREINO` (sem limite de
velocidade). O botão principal pausa ou continua o processo inteiro; essa pausa
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
