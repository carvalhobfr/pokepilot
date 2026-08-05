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

## Retomada mínima

```bash
sed -n '1,400p' docs/HANDOFF.md
sed -n '1,320p' docs/QUEST_GRAPH.md
cd blue-agents && MPLCONFIGDIR=tasks/matplotlib ../.venv/bin/python -m unittest discover -s tests -q
```

Não presuma que todos os 19 nós do QuestGraph possuem executor. O grafo define o
roteiro completo; o executor ausente mais próximo está anotado no handoff.

## Como este projeto navega

É o que mais confunde quem chega: **não existe leitura de colisão da RAM**. As
paredes são aprendidas jogando — apertou uma direção e não saiu do lugar, logo
aquela aresta é bloqueada — e o caminho até o próximo waypoint sai de uma busca
em largura sobre esse conhecimento.

| Caminho | Papel |
|---|---|
| `src/collision_memory.py` | arestas bloqueadas + BFS |
| `blue-agents/knowledge/maps/collision.json` | mapa aprendido, **compartilhado entre treinadores** |
| `src/scripted_agent.py` | executores de quest e `_follow_route` |

Regras que custaram caro para descobrir e são fáceis de quebrar de novo:

- aresta desconhecida conta como **livre**; o primeiro plano num mapa novo é a
  linha reta, e cada colisão o estreita;
- **o plano é guardado e seguido tile a tile.** Recalcular a cada passo faz o
  bot oscilar entre dois desvios de custo igual, nunca colidir e, portanto,
  nunca aprender;
- atravessar uma aresta bloqueada a **esquece**: NPC parado é indistinguível de
  parede enquanto está lá;
- deslocamento diferente do esperado (ledge) e troca de mapa no meio da rota
  (warp) viram aresta bloqueada — o planejador só modela passo unitário;
- mapa sem rota não é motivo para apertar `A`: sai-se pela porta de entrada;
- o flag de menu (`0xCFC4`) já ficou preso em `1`; o orçamento de `A` só é
  reposto por deslocamento real.

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
| `completionist` | espécie nova até fechar a meta da área (50%, 100% pós-Liga) |
| `speedrunner` | só reserva e Pokémon forte; o resto é turno perdido |
| `team_builder` | o que ocupa vaga ou melhora a linha de frente |

O arquétipo vive no campo `archetype` de cada slot em
`blue-agents/tasks/slot_roster.json`.

## Conhecimento gerado, não escrito à mão

`blue-agents/tools/build_pokeapi_knowledge.py` monta da PokéAPI:

- `knowledge/maps/encounters.json` — espécies por área em Blue, com faixa de
  nível. É o que permite afirmar "faltam 3 nesta área" como fato;
- `knowledge/gyms.json` — os 8 ginásios com tipo, líder e o que bate neles.

`blue-agents/area_knowledge.py` traduz nome de mapa da RAM para área da PokéAPI
e responde "quanto desta área já está registrado". É o que dá sentido à meta do
completista, que é **50% por área durante a campanha e 100% depois da Liga**:
Surf e as varas trancam tabelas inteiras, e exigir tudo cedo estacionaria o bot
antes das ferramentas que o destravariam.

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
