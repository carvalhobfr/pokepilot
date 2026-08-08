# PokeAI 2026 — instruções para agentes e colaboradores

Antes de alterar este projeto, leia **por inteiro** `docs/HANDOFF.md` e consulte
`docs/QUEST_GRAPH.md`. O handoff é a fonte canônica de continuidade; o mapa
visual mostra a ordem da jornada, o fluxo técnico e a diferença entre objetivo
planejado, executor implementado e trecho validado no cartucho.

## Regras obrigatórias

1. O alvo é a ROM real de Pokémon Red/Blue rodando no PyBoy. Não substitua
   progressão real por dados sintéticos, salvo no modo de demonstração da
   interface. Cada pessoa traz a própria cópia legal; ninguém compartilha ROM.
2. **Progresso só conta quando confirmado na RAM.** Nunca escrever na RAM para
   forçar resultado; nunca declarar vitória, captura, evolução, cura ou
   objetivo concluído porque um botão foi enviado ou porque passou tempo.
3. Preserve `trainers/<AGENTE>/current.state`, `current.sav`, `journey.json` e
   `logs/decisions.jsonl`. Nunca reinicie uma jornada sem pedido explícito.
   Para aposentar um treinador, arquive com
   `journey_roster.archive_completed_agent` e tire-o do roster — o diretório
   dele fica intacto.
4. Scripts controlam história e batalha; PPO só deve aprender transições
   realmente controladas pela política. Não treine PPO com passos roteirizados.
5. Rode os testes antes e depois de qualquer alteração de jogabilidade.
6. Preserve mudanças existentes. Não use limpeza ou reset global do Git.
7. Atualize `docs/HANDOFF.md` **junto do commit**, sempre. Se a cobertura de uma
   quest mudou, atualize também `docs/QUEST_GRAPH.md`.
8. Sem `Co-Authored-By` nas mensagens de commit.
9. **Confira a branch antes de commitar.** `git branch --show-current`. Uma
   sessão inteira de trabalho foi para `feat/rom-fast-blue` em vez do `master`
   por ninguém ter olhado (2026-08-08).
10. **Nunca `git add -A`.** Adicione caminhos explícitos. Um `add -A` levou
    junto trabalho de outra pessoa que estava sem versionar, com uma ROM de
    1 MB dentro. O guarda de pré-commit barra o caso óbvio, mas ele é rede,
    não regra:

    ```bash
    cd blue-agents && ../.venv/bin/python tools/pre_commit_guard.py --install
    ```
11. **Antes de ensinar o bot a aprender algo, veja se o cartucho já responde.**
    É a regra que mais rendeu neste projeto. Aprender geometria esbarrando deu
    21 mapas e 4067 paredes inventadas em dias; ler a ROM deu 238 mapas e
    49.412 células em segundos. O mesmo valeu para golpes, Centros e portas.
    Quando o bot erra sobre o **mundo**, a pergunta é onde o cartucho já diz
    isso — não como fazer o palpite errar menos. Extratores em
    `blue-agents/tools/extract_*.py`.
12. **Antes de escrever uma função nova num arquivo grande, pergunte ao grafo.**
    `scripted_agent.py` tem 3.100 linhas e `hybrid_agent.py` 4.200. Um
    `_planned_step` foi escrito do zero sem ver que já existia um mais
    completo, e o seguidor de rota foi diagnosticado como guloso quando já
    consultava a busca em largura — os dois por ler um bloco e concluir sobre o
    arquivo.

    ```bash
    /graphify .                                  # constrói (uma vez)
    graphify explain "_planned_step"
    graphify path "_follow_route" "find_path"
    ```

## Retomada mínima

```bash
sed -n '1,400p' docs/HANDOFF.md
sed -n '1,320p' docs/QUEST_GRAPH.md
cd blue-agents && MPLCONFIGDIR=tasks/matplotlib ../.venv/bin/python -m unittest discover -s tests -q
```

Não presuma que todos os 19 nós do QuestGraph possuem executor. O grafo define o
roteiro completo; o executor ausente mais próximo está anotado no handoff.

## Como este projeto navega

**A geometria vem do cartucho, não de esbarrar.** Isto mudou em 2026-08-08 e a
descrição antiga — "as paredes são aprendidas jogando" — está morta: ela rendeu
21 mapas e 4067 paredes que nunca existiram, porque NPC parado vira parede e uma
batalha na tela faz todo tile ler como parede.

| Caminho | Papel |
|---|---|
| `blue-agents/tools/extract_map_data.py` | lê parede, mato, treinador, item e porta dos 248 mapas |
| `blue-agents/knowledge/maps/static_maps.json` | 238 mapas, 49.412 células — **autoridade**, versionado |
| `src/map_memory.py` | carrega o estático e faz a busca em largura |
| `src/scripted_agent.py` | executores de quest, `_follow_route`, `_planned_step` |

A leitura de tela ainda existe para o que **muda**: sprites são lidos ao vivo,
nunca guardados. Onde o cartucho já respondeu, `observe()` não escreve.

Regras que custaram caro para descobrir e são fáceis de quebrar de novo:

- **o plano é guardado e seguido tile a tile.** Recalcular a cada passo faz o
  bot oscilar entre dois desvios de custo igual e nunca comprometer-se;
- **waypoint já passado é waypoint gasto.** O índice da rota não retrocede ao
  reentrar num mapa — sair e voltar zerava o avanço, e deu 18 travessias de
  Mt. Moon sem progresso. Mas ele **solta** depois de 120 passos sem encurtar
  distância, senão quem sai da rota mira para sempre o que não alcança;
- **porta nunca é alvo de rota, exceto a última.** A rota de um interior começa
  no tile da porta, e mirar isso de dentro é sair do prédio;
- **o mais perto tem de ser o mais perto alcançável.** Distância em linha reta
  escolhe pontos do outro lado da parede;
- mapa sem rota não é motivo para apertar `A`: sai-se pela porta de entrada, e
  em cima da porta se **atravessa** (para baixo), não se anda para outra porta;
- o flag de menu (`0xCFC4`) já ficou preso em `1`; o orçamento de `A` só é
  reposto por deslocamento real;
- **sprite não é parede** e não se aprende: é lido ao vivo. Pessoa parada na
  frente é o travamento aberto mais antigo — ver o handoff.

Para separar controlador de geometria, use a sonda em vez de adivinhar:

```bash
cd blue-agents && ../.venv/bin/python tools/probe_route.py \
    ../trainers/DARON/current.state --target-x 17 --target-y 43
```

## Arquétipos

Personalidade fixa por slot, sem sorteio (`blue-agents/archetypes.py`). Um
sorteio de ±10 já deixou um treinador abaixo de todo limiar de captura, e a
corrida inteira pareceu bug de política.

| Arquétipo | O que faz com um selvagem que poderia capturar |
|---|---|
| `completionist` | 100% do que é alcançável em cada área, raridade sempre |
| `speedrunner` | só reserva e Pokémon forte; o resto é turno perdido |
| `team_builder` | o que ocupa vaga ou melhora a linha de frente |
| `fire_dragon` | só fogo e dragão; o resto é experiência, nunca vaga |

O arquétipo vive no campo `archetype` de cada slot em
`blue-agents/tasks/slot_roster.json`, e escolhe também o inicial — cada um com
motivo, não por índice: Bulbasaur para completista e rushador (Brock e Misty
caem para grama, e Sleep Powder deixa encontro longo barato), Squirtle para o
construtor, Charmander para o temático, cujo time é montado em volta do
Charizard.

## Replay de batalha

`stream_agent_wrapper` guarda os quadros que a arena **já codifica**, então
gravar não custa encode a mais. Duas condições, ambas reais: painel aberto
(`viewers > 0`) e velocidade até 2× — acima disso as batalhas saem mais rápido
do que alguém assistiria, e seriam quadros queimados para ninguém. O relay
mantém as 5 últimas de cada treinador e só envia os quadros quando alguém
aperta play.

## Conhecimento gerado, não escrito à mão

`blue-agents/tools/build_pokeapi_knowledge.py` monta da PokéAPI:

- `knowledge/maps/encounters.json` — espécies por área em Blue, com faixa de
  nível. É o que permite afirmar "faltam 3 nesta área" como fato;
- `knowledge/gyms.json` — os 8 ginásios com tipo, líder e o que bate neles.

`blue-agents/area_knowledge.py` traduz nome de mapa da RAM para área da PokéAPI
e responde "quanto do que dá para alcançar aqui já está registrado". A meta do
completista é **100% do alcançável**, não uma fração: o método do encontro
(andar, surfar, vara velha/boa/super) diz o que a fase atual pode encontrar, e
as insígnias são a régua legível na RAM — vara velha na 3ª, Surf e vara boa na
5ª, super vara na 6ª. O conjunto cresce sozinho, então a mesma área é cobrada de
novo mais tarde sem nunca exigir o impossível.

Raridade tem prioridade sobre a cota: Pikachu é 5% da Floresta contra 45% de
Caterpie, e nenhuma meta cumprida pode fazer o bot passar batido por ele.

A jornada nunca acessa a rede; rode a ferramenta quando quiser atualizar.

## Desempenho

O throttle de reprodução existe para a arena ser assistível e some sozinho
quando nenhum painel está aberto: o mesmo binário foi de **4 para 446** passos
de PPO por segundo num M1. Com plateia valem `0.5×`, `1×` e `2×`; sem plateia é
modo treino.

Os agentes rodam em `DummyVecEnv`, **em sequência num processo só**. Medido num
M1 Air, sem limite: 2 bots 285 passos/s no total, 4 bots 377, 6 bots 381, 8 bots
390. A vazão satura por volta de 4; daí em diante cada bot novo só divide o
mesmo laço (49 passos/s por bot com 8, ainda ~20× o ritmo do Game Boy). Passar
disso exige `SubprocVecEnv`, e aí o limite vira térmico.
