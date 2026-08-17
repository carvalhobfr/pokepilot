# pokepilot

[English](README.md) · **Português**

Bots jogando **Pokémon Blue de verdade** — a ROM original num emulador, não uma
simulação. Você acompanha pelo navegador: o mapa de Kanto com os treinadores se
movendo, o time de cada um, e um diário explicando por que cada decisão foi
tomada.

A ideia é um bot que **entende objetivos**, não um script que decora botões. Hoje
ele já atravessa meia Kanto sozinho; o rumo é receber ordens em português —
*"captura um Pikachu"* — e descobrir sozinho onde ir e o que fazer.

O que garante que nada é inventado: **todo progresso é conferido na memória do
cartucho**. Nenhum script pode dizer "consegui a insígnia" — o bit dela precisa
aparecer na RAM.

> ### 🚧 Projeto em desenvolvimento
>
> Nada aqui é versão final e o jogo não está zerado. O que aparece como ✅ foi
> **reproduzido do zero**, mais de uma vez, dando o mesmo resultado. O resto é
> BETA ou ainda não funciona — e está marcado assim em cada seção, em vez de
> escondido atrás de uma promessa.

## Estado de cada peça

| Peça | Estado |
|---|---|
| navegação por grafo e quests, de Pallet até o Cut | ✅ testado, reproduzível do zero |
| batalha (sistema especialista lendo a RAM) | ✅ testado |
| painel, mapa ao vivo, arena e replays | ✅ funciona |
| **arquétipos** (as quatro personalidades) | 🟡 **BETA** — rodam, mas nenhuma corrida completa comparou os quatro até o fim |
| **aprendizado por reforço (PPO)** | 🟡 **BETA** — treina, mas decide **0%** das ações hoje ([medido](#aprendizado-medido-e-não-estimado)) |
| **ordens em português via LLM** | ⛔ **em breve** — não funciona ainda; hoje o LLM só responde o botão "Ask AI" |
| do ginásio do Lt. Surge até a Liga | ⛔ sem executor |

---

## Até onde os bots chegam

Um bot começando um jogo novo, sem ninguém ajudando, em **menos de duas horas**:

| | |
|---|---|
| sai de casa, escolhe o inicial, entrega a encomenda do Oak | ✅ |
| compra Poké Bolas, atravessa Viridian e a Floresta | ✅ |
| treina até o inicial evoluir | ✅ |
| **vence o Brock — 1ª insígnia** | ✅ |
| cruza a Rota 3 e **Mt. Moon inteira** (três andares) | ✅ |
| chega a Cerulean, resolve o quebra-cabeça do Bill | ✅ |
| **vence a Misty — 2ª insígnia** | ✅ |
| chega a Vermilion, entra no S.S. Anne, ganha o HM01 | ✅ |
| **aprende Cut** | ✅ |
| ginásio do Lt. Surge (puzzle das lixeiras) | ⛔ ainda não |

Isso foi reproduzido por **dois bots independentes** no mesmo dia, cada um
partindo do zero. Onze dos 19 objetivos do jogo estão fechados; o que falta está
listado, com nome e causa, no [handoff](docs/HANDOFF.md).

## O que você vê na tela

- **o mapa de Kanto** com cada bot andando em tempo real (arrastar move, roda do
  mouse dá zoom, clicar num bot trava a câmera nele);
- **o time de cada treinador** — espécie, nível, HP, golpes;
- **o diário**: "escolhi Vine Whip porque é 4× contra Rocha", "não capturei
  porque não tenho bola", "travei nesta tela";
- **a arena**, quando você clica: até quatro batalhas ao vivo, com replay das
  últimas de cada bot.

Cada bot tem uma **personalidade fixa** e joga diferente de propósito: um
completista que quer registrar tudo, um rushador que só para pelo que vale a
parada, um construtor de time, e um temático que só usa fogo e dragão. Mesmas
regras, mesmo mapa, respostas diferentes.

## Como rodar

Funciona em **Windows, macOS e Linux**. Você precisa de três coisas: Python
3.11+, Node.js e a sua cópia de Pokémon Blue.

1. Instale [Python 3.11+](https://www.python.org/downloads/) e
   [Node.js LTS](https://nodejs.org). **No Windows, marque "Add python.exe to
   PATH"** — é o erro mais comum.
2. Ponha a **sua** cópia legal em `roms/PokemonBlue.gb` (Red também serve).
3. Inicie:

   | Sistema | Como |
   |---|---|
   | **Windows** | dois cliques em `start.bat` |
   | **macOS** | dois cliques em `start.command` |
   | qualquer um | `python start.py` no terminal |

Ele instala o que faltar, sobe o painel, abre o navegador e começa a jogar. A
primeira vez demora alguns minutos baixando dependências; as seguintes sobem em
segundos. `Ctrl+C` encerra **salvando** o progresso.

Útil saber: `--slots 1` roda um bot só (mais leve), `--no-browser` não abre o
navegador. **Dois bots é o teto num laptop de 8 GB** — com três, o sistema mata
um sem avisar (falta de memória, não calor).

> **macOS:** se o sistema bloquear na primeira vez, botão direito → *Abrir*.
> **Windows:** se o SmartScreen avisar, *Mais informações* → *Executar assim mesmo*.

## Perguntas que todo mundo faz

**Isso é IA de verdade?** Sim, mas não a que a palavra sugere hoje. Não é um
modelo que aprendeu a jogar assistindo, nem um LLM apertando botões. É um agente
com quatro peças clássicas de IA — busca em grafo, planejamento com
pré-condições, um sistema especialista de batalha e detecção de anomalia — mais
uma rede de aprendizado por reforço que, medida, hoje decide **0%** das ações.
Detalhe honesto na [parte técnica](#parte-técnica).

**Ele aprende ou está tudo escrito?** As duas coisas, e a divisão é medida. O
caminho vem de um mapa **extraído do cartucho** e de busca — não de rota decorada
—, e o bot recalcula de onde estiver. O que está escrito à mão são os objetivos e
alguns trechos difíceis. A rede neural existe, mas quem joga hoje é a busca.

**É trapaça ler a memória do jogo?** É o contrário: é o que impede a trapaça. O
bot não pode alegar progresso — a insígnia, a captura, o golpe aprendido, tudo
tem de aparecer na RAM. Nada é escrito na memória para forçar resultado.

**Preciso da ROM?** Sim, a sua. Pokémon Blue é software comercial e não vem no
repositório.

**Por que Pokémon?** Porque é um mundo grande, com regras fechadas e um juiz
imparcial: o próprio cartucho diz se você venceu.

## Para onde vai: ordens em português (em breve)

**Nada desta seção funciona hoje.** É o rumo do projeto, escrito com as peças que
já existem — não uma funcionalidade que você vai encontrar rodando.

O objetivo do projeto não é terminar o jogo mais rápido — é o bot **entender uma
ordem**. *"Captura um Pikachu"* deveria bastar: ele sabe que Pikachu aparece na
Floresta de Viridian a 5%, que precisa de Poké Bolas, e calcula o caminho até
lá de onde estiver.

O desenho para isso, com as peças que já existem:

1. **um vocabulário de objetivos** — estar em tal lugar, ter tal espécie, ter tal
   item, ter N insígnias — cada um verificável na RAM (é o que o QuestGraph já
   faz com os 19 nós do jogo);
2. **um solucionador**: dado o objetivo, o grafo de Kanto responde o caminho e as
   pré-condições dizem o que falta antes (bola na mochila, insígnia que libera a
   área);
3. **a LLM como tradutora** — só isso: converter a frase em objetivo, uma vez por
   ordem. Ela nunca decide passo a passo, onde é lenta e erra; quem executa é a
   busca, e quem confere é o cartucho.

Zerar o jogo, nesse desenho, é só uma ordem entre outras: "consiga as oito
insígnias".

---

# Parte técnica

Daqui para baixo é detalhe de implementação: arquitetura, o que foi medido, e as
armadilhas que custaram caro. Se você só quer ver os bots jogando, a parte de
cima já basta.

## Que IA tem aqui, exatamente

| peça | o que é | onde |
|---|---|---|
| **busca** | Kanto como grafo — 49.412 células, 2.152 portas, 106 bordas — e busca em largura de qualquer ponto a qualquer ponto | `src/kanto_graph.py` |
| **planejamento** | 19 objetivos com pré-condições verificadas na RAM; nada é "concluído" por tempo ou por botão apertado | `blue-agents/quest_graph.py` |
| **sistema especialista** | política de batalha lendo tipo, potência e PP da tabela do próprio cartucho | `src/simple_battle.py` |
| **detecção de anomalia** | impressão digital do cartucho a cada passo; estado que não muda, ou volta repetida com o plano parado, viram save + tela gravados | `src/life_watchdog.py` |
| **aprendizado por reforço** 🟡 BETA | PPO (stable-baselines3) sobre a exploração — decide 0% das ações hoje | `blue-agents/hybrid_agent.py` |

**A parte de LLM não funciona ainda.** Existe um `src/llm_agent.py`, mas hoje ele
só responde ao botão "Ask AI" do painel — não decide nada na jornada, que não
depende dele e não acessa a rede. Traduzir uma ordem em português para objetivo
verificável é o
[próximo passo do projeto](#para-onde-vai-ordens-em-português-em-breve), não algo
que já esteja de pé.

## Aprendizado, medido e não estimado

Instrumentando a origem de cada ação numa travessia real até o Brock, em 471
passos:

```
battle_controller : 252  (53.5%)   heurística lendo a RAM
quest_controller  : 219  (46.5%)   busca e rotas medidas
ppo               :   0   (0.0%)
transições treináveis: nenhuma
```

O PPO só recebe o passo quando nenhum controlador quer agir. Além disso,
`ScriptAwarePPO` descarta o rollout inteiro se **qualquer** passo foi
sobrescrito por script — creditar recompensa a uma ação que a rede não tomou
seria treinar com dado falso.

**O caminho honesto para o aprendizado pesar mais** é o inverso do que se
costuma tentar: usar as travessias gravadas como **demonstrações** (behavior
cloning) e deixar o reforço refinar onde não existe executor, em vez de disputar
o volante com o script.

### Arquétipos 🟡 BETA

Os **arquétipos** (`blue-agents/archetypes.py`) fixam traços, inicial e o que
fazer com um selvagem capturável. São a variável do experimento: mesmo mapa,
mesmas rotas, decisões diferentes.

Estão em BETA porque a parte fácil está pronta e a difícil não: os quatro rodam
e cada um decide diferente na captura, mas **nenhuma corrida completa comparou
os quatro até o mesmo ponto**. Sem isso, a tabela abaixo é o desenho pretendido,
não resultado medido — ao contrário dos números de PPO acima, que são contagem
de uma travessia real.

| Arquétipo | Postura diante de uma captura possível |
|---|---|
| Completista | 100% do alcançável em cada área; raridade nunca escapa |
| Rushador | reserva e Pokémon forte; o resto é turno perdido |
| Construtor de time | o que ocupa vaga ou melhora a linha de frente |
| Fogo e dragão | só fogo e dragão no time; a corrida mais difícil de Kanto |

A meta do completista é 100% do que é **alcançável**, que não é 100% da área:
Surf e as varas trancam tabelas inteiras de encontro, então o conjunto cobrado
cresce conforme as insígnias chegam (`knowledge/maps/encounters.json`). Raridade
vem antes da cota — Pikachu é 5% da Floresta contra 45% de Caterpie, e nenhuma
meta cumprida faz o bot passar batido por ele.

## Como os bots acham o caminho

**A geometria vem do cartucho, não de esbarrar.** `tools/extract_map_data.py` lê
parede, mato, treinador, item e porta dos 248 mapas direto da ROM: 238 mapas e
49.412 células em `knowledge/maps/static_maps.json`. A versão anterior aprendia
paredes esbarrando, e isso rendeu 21 mapas e **4.067 paredes que nunca
existiram** — um NPC parado é indistinguível de parede, e uma batalha na tela faz
todo tile ler como parede.

Desde 2026-08-17 as três ligações do mundo estão no mesmo grafo: passo dentro do
mapa, **borda** entre mapas e **porta**, as duas últimas extraídas do cabeçalho
de mapa e da tabela de warps (`tools/extract_connections.py`). Com isso, "ir de
onde estou até `(mapa, tile)`" é uma busca só — de Pallet até o Brock são 371
passos cruzando dez mapas, sem uma coordenada escrita à mão. O grafo modela até
o pulo de penhasco, como aresta de mão única, e acha atalhos que nenhuma rota
escrita tinha (Vermilion pela Diglett's Cave).

A ordem de autoridade é fixa, e cada inversão dela custou horas:
**leitura ao vivo > estático do ROM > trilha gravada**. A rota medida dirige
enquanto alcança; o grafo é a rede quando ela não alcança. Trilha gravada nunca
dirige onde existe executor — isso causou quatro travamentos num único dia.

Quem vigia é a **impressão digital do cartucho**: a cada passo, mapa, posição,
equipe, mochila, insígnias e HP de batalha. Estado que não cresce em 600 passos,
ou a mesma volta repetida com o plano parado, é congelamento — e aí o save e a
tela decodificada são gravados sozinhos, para o defeito virar teste em vez de
virar madrugada.

## Rede de proteção

```bash
cd blue-agents && MPLCONFIGDIR=tasks/matplotlib ../.venv/bin/python -m unittest discover -s tests -q
cd blue-agents && ../.venv/bin/python tools/replay_check.py
```

O primeiro são os testes de unidade (632). O segundo é o que importa mais: cada
trecho já vencido virou um **save real** em `states/replay/` mais o que o
cartucho tem de responder depois de N passos. Teste de unidade não pisa no
cartucho — a suíte já esteve verde com 548 testes enquanto três bots novos
quebravam em quatro pontos seguidos.

## Estrutura

- `blue-agents/`: ambiente PPO, agentes, WebSocket e dashboard.
- `blue-agents/knowledge/`: QuestGraph, mapas extraídos da ROM, conexões,
  encontros por área e os 8 ginásios.
- `blue-agents/tools/`: extratores (mapa, warps, conexões, Centros), sonda de
  rotas, replay dos trechos vencidos e minerador de trilha.
- `src/`: emulador, memória, grafo de Kanto, navegação, batalha e watchdog.
- `roms/`: sua cópia legal, ignorada pelo git.
- `states/`: estados de partida e os saves de replay.
- `trainers/<AGENTE>/`: save, journey e diário de decisões de cada treinador.
- `archives/<data>-<AGENTE>/`: jornadas encerradas, com manifesto de hashes.

## A ROM

Pokémon Blue é software comercial e **não faz parte deste repositório**. Cada
pessoa traz a própria cópia legal em `roms/PokemonBlue.gb`. O histórico do git
também não a contém: as ROMs que ficaram versionadas enquanto o repositório era
privado foram apagadas de todos os commits antes de ele virar público.

`blue-agents/rom_identity.py` identifica o cartucho pelo **cabeçalho**: Red ou
Blue servem, porque compartilham mapas, endereços de RAM e o QuestGraph inteiro.
Yellow não, e é recusada de propósito. Não há conferência de SHA-1 — cartuchos
legais são dumpados por pessoas diferentes com ferramentas diferentes, e exigir
um arquivo idêntico só forçaria uma equipe a passar ROM de mão em mão. O digest
continua sendo calculado e gravado nos arquivos gerados, para uma jornada
arquivada dizer de qual dump ela veio.

## Velocidade e desempenho

O controle no topo do painel começa em `1×`, o ritmo do Game Boy, e vai a `0.5×`,
`2×` e `TREINO` (sem limite). **Com nenhum painel aberto o limite some sozinho**
— ele existe só para a arena ser assistível, e custa caro: o mesmo binário fez 4
passos por segundo com `1×` e **446** sem limite, no mesmo M1.

Os ambientes rodam **em sequência dentro de um processo só**, então a vazão
satura por volta de 4 bots:

| Bots | Passos/s no total | Por bot | Vezes o ritmo do Game Boy |
|---|---|---|---|
| 2 | 285 | 143 | ~57× |
| 4 | 377 | 94 | ~38× |
| 6 | 381 | 64 | ~25× |
| 8 | 390 | 49 | ~20× |

Reduzir o número de bots **não apaga ninguém**: o treinador sai da lista ativa
mas mantém save, diário e progresso em `trainers/`, e volta de onde parou.

## Rever as batalhas

O botão **Replays** abre as últimas batalhas de cada treinador, com play, pausa e
passo a passo. A gravação só acontece com o painel aberto e até `2×` — acima
disso as batalhas terminam mais rápido do que alguém assistiria. Não custa
desempenho: são exatamente os quadros que a arena já codifica.

## Telemetria da jornada

Cada agente lê a RAM do PyBoy e registra em `trainers/<AGENTE>/logs/`:

- mapas, objetivos e checkpoints alcançados;
- início/fim de batalha, vitória, derrota e whiteout;
- golpe escolhido, efetividade, motivo e Pokémon ativo;
- capturas confirmadas pela party/Pokédex, inclusive envio ao PC;
- level up, evolução, depósito no PC e alvo real de XP;
- congelamentos, com a tela decodificada e o save anexado.

Em batalhas selvagens, a captura só é considerada disponível depois do evento
real `EVENT_GOT_POKEDEX` e quando existe uma Poké Bola de verdade na mochila. O
agente explica se capturou por perfil colecionador, por melhoria do time ou por
raridade; caso contrário, explica que derrotou o encontro para treinar. Batalhas
de treinador nunca tentam captura, e o log distingue decisão, tentativa e
captura confirmada pela RAM.

## Continuidade do desenvolvimento

Colaboradores (humanos ou agentes) começam por [AGENTS.md](AGENTS.md) e pelo
[handoff canônico](docs/HANDOFF.md), que registra o estado real do save, o
travamento em andamento e o comando seguro para continuar sem reiniciar uma
jornada. O [mapa do QuestGraph](docs/QUEST_GRAPH.md) separa o que já foi
validado no cartucho, o que tem executor e o que é só planejamento.

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
8×8 com duas cores — e não apagou nenhum elemento de jogo.
