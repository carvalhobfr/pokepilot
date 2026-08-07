# PokeAI 2026 — dossiê para auditoria externa

Documento autocontido: descreve o que o projeto é, as regras que o governam e
os limites conhecidos. No fim há um **prompt pronto** para entregar a um
auditor.

Números conferidos em 2026-08-07 rodando o código, não de memória.

---

## 1. O que é

Bots jogam **Pokémon Blue** num emulador real (PyBoy), no cartucho de verdade,
sem editar RAM para forçar progresso. Dois bots rodam ao mesmo tempo, cada um
com seu emulador e seu save. O objetivo declarado é **zerar o jogo** e, mais
que isso, **ter um caminho determinístico para zerar** — um caminho em que um
bot possa entrar em qualquer ponto e seguir.

| | |
|---|---|
| ROM | Pokémon Blue (identidade verificada por hash) |
| Emulador | PyBoy, headless |
| Linguagem | Python |
| Testes | **326**, em 26 arquivos |
| Endereços de RAM/ROM distintos lidos | ~107 |

Não é aprendizado por reforço na prática. Existe um PPO (Stable-Baselines3)
herdado do projeto de origem, mas **enquanto houver executor de quest ele não
dirige**. O que joga é um controlador determinístico.

Linhagem: fork de [PokemonRedExperiments (PWhiddy)](https://github.com/PWhiddy/PokemonRedExperiments)
— de lá vêm o ambiente Gym, o mapa de Kanto e o visualizador.

---

## 2. A regra que governa tudo

> **Pergunte ao cartucho. Não guarde na memória do processo o que a RAM
> responde.**

Todo congelamento sério deste projeto teve a mesma forma: um valor guardado no
processo em vez de lido, ou uma sequência de teclas tocada às cegas.

| Sintoma no jogo | O que estava guardado | O que responde de verdade |
|---|---|---|
| Sai do Centro e volta na hora | flag "já curei" | HP da party na RAM |
| Some da rota e nunca volta | lista de teclas | rota andada com colisão lida |
| Fica na porta piscando | warp tratado como tile comum | porta é destino, nunca atalho |
| Aperta DOWN eternamente | posição do menu decorada | linha/coluna do cursor lidas |
| Joga bola e nada acontece | slot da bola decorado | id do item sob o cursor |
| Pokémon cai e ninguém entra | espera o aviso de troca | a lista da equipe se identifica sozinha |

Corolário aprendido em 2026-08-07: **um número que decide entrar e outro que
decide o que fazer lá dentro criam porta giratória.** Aconteceu três vezes
(Centro de Viridian, portão de nível, curar-mas-não-sair).

---

## 3. Arquitetura em camadas

```
run_journeys.py      supervisor: blocos ("chunks") de 8192 passos, arquiva quem termina
  └─ train_hybrid.py  monta N emuladores, roster, política PPO compartilhada
       └─ hybrid_agent.py   orquestração: RAM, QuestGraph, eventos, captura, checkpoints
            ├─ scripted_agent.py   executores de quest, rotas, navegação
            ├─ simple_battle.py    escolhas e menus de batalha
            └─ tile_collision.py   colisão, terreno, warps, mato — tudo lido do cartucho
```

Estado por treinador em `trainers/<AGENTE>/`; conhecimento compartilhado entre
todos em `blue-agents/knowledge/`.

---

## 4. O caminho: QuestGraph e executores

19 nós, cada um com **predicado verificável na RAM**. Um nó só é dado como
concluído quando o cartucho concorda.

Tipos de predicado em uso: `event_flag`, `badge`, `bag_item`, `map_in`,
`pokeballs_stocked` (e, disponíveis para diretivas, `party_max_level`,
`species_owned`, `party_species`).

**Cobertura atual: 11 dos 19 nós têm executor.** O caminho determinístico
termina na Misty. Faltam 8:

`vermilion_gym_quest`, `celadon_story_quest`, `fuchsia_story_quest`,
`saffron_story_quest`, `cinnabar_story_quest`, `viridian_gym_quest`,
`pokemon_league_quest`, `mewtwo_postgame`.

A conclusão é *sticky* em `journey.json`: quem já concluiu um nó não o
reexecuta, mesmo que o predicado mude depois.

---

## 5. Navegação

### 5.1 O que o cartucho responde

| Fonte | Endereço | O que dá |
|---|---|---|
| lista de tiles caminháveis do tileset | ponteiro em `0xD530` | terreno, verdade permanente |
| mapa de tiles da tela (20×18) | `0xC3A0` | o que está em volta |
| tabela de sprites (16 bytes cada) | `0xC100` | onde está a gente, agora |
| número de warps / tabela de warps | `0xD3AE` / `0xD3AF` | portas: onde estão **e para onde vão** |
| tile de mato do tileset | `0xD535` | qual tile gera encontro selvagem |
| janela do LCD | `0xFF4A` | tem algo desenhado por cima do mapa? |
| contador de passo | `0xCFC5` | o passo terminou? |

Terreno é permanente e pode ser lembrado; **sprites nunca são lembrados**, são
lidos ao vivo. Essa distinção é o ponto inteiro: um NPC parado é indistinguível
de parede naquele passo, e gente virava geometria permanente compartilhada.

### 5.2 Quando é proibido lembrar terreno

`terrain_grid()` devolve vazio, e cada trava custou um dia de depuração:

1. **`0xFF4A != 144`** — batalha, menu, loja ou caixa de texto desenham sobre o
   mesmo tilemap. Medido: 78 paredes inventadas por tela de batalha.
2. **`0xCFC5 != 0`** — no meio do passo a tela já rolou meio tile enquanto as
   coordenadas ainda nomeiam a casa que está sendo deixada; os 80 tiles entram
   uma linha fora. Medido de `(31,24)`: 24 livres parado, 27 no meio do passo,
   e 27 é a resposta de `(31,23)`.
3. **tile sob o jogador não é caminhável** — rede de segurança para o resto.

Sem essas travas: **4067 paredes falsas em 17 mapas**, com a Floresta de
Viridian partida em quatro bolsões sem ligação.

**Assimetria que justifica o rigor:** um tile marcado caminhável por engano
custa uma esbarrada; um tile marcado parede por engano é permanente, invisível
e compartilhado — o planejador desvia dele para sempre e nunca mais olha.
Ferramenta de reparo: `tools/forget_walls.py`.

### 5.3 Como o passo é escolhido

Ordem em `_follow_route`:

1. menu/texto aberto → alterna `B`/`A`, com limite (`MENU_PRESS_LIMIT = 12`) e
   depois anda assim mesmo;
2. anda na direção do waypoint, eixo mais longo primeiro;
3. plano por busca em largura sobre o terreno já visto (desconhecido conta como
   livre — otimismo que cada passo corrige);
4. lado ocupado por **gente** → espera alguns passos (pessoa anda, parede não);
5. memória de 8 tiles desencoraja voltar por onde acabou de vir;
6. warp no meio da rota é bloqueado; só o último waypoint pode ser porta.

### 5.4 Trilhas (opcional, desligado por padrão)

Cada travessia é gravada tile a tile e publicada quando o predicado da quest é
confirmado. Publicação escolhe por **alcance → densidade → brevidade**.

**Seguir trilha é opt-in** (`POKEAI_FOLLOW_TRAILS=1`). A rota feita à mão é o
caminho principal e dirige. Motivo: um único ponto minerado na Rota 4 fez um bot
cruzar a fronteira a cada 0,6 s por uma hora.

---

## 6. Cura, checkpoint e morte

| Situação | Limite | Ação |
|---|---|---|
| dentro de um Centro | qualquer HP faltando | cura |
| porta de Centro **neste mapa** | qualquer HP faltando | entra |
| viajando (Centro a uma cidade) | HP total < 20% | vai ao Centro |
| selvagem com o time machucado | HP total < 50% | foge |

O prêmio de entrar num Centro **não é o HP, é o checkpoint**: cura confirmada
dentro de um Centro é a única coisa no projeto que grava ponto de retomada.
Sem ele, morrer custa a corrida de volta a Pallet; com ele, custa o trecho.

**Morrer não rebobina.** O whiteout é evento real do cartucho; nada recarrega
estado por causa disso. O ciclo de morte é numerado e persistido em
`journey.json`, e a gravação de trilha recomeça — a aproximação que perdeu a
luta não é o caminho.

---

## 7. Batalha e captura

- golpe escolhido por potência × efetividade × STAB, lendo o menu real
  (`0xCC25` coluna, `0xCC26` linha); **coluna inválida → `B`**, nunca escolhe
  golpe por acidente;
- sem golpe de dano com PP, foge de selvagem (só o Centro devolve PP na Gen I);
- trocar Pokémon vem **antes** de fugir;
- captura: política ordenada (autopreservação → enfraquecer antes → espécie
  duplicada → vaga livre → personalidade), e a bola é escolhida **por id na
  mochila**, nunca por posição decorada.

---

## 8. Operação

```bash
POKEAI_STAGGER_STEPS=1500 python3 start.py --slots 2 \
    --init-state states/viridian-passed-AARON.state
```

| Variável | Efeito |
|---|---|
| `POKEAI_STAGGER_STEPS=N` | slot *k* espera *k·N* decisões, em ordem — para o de trás herdar trilha |
| `POKEAI_FOLLOW_TRAILS=1` | liga o seguimento de trilha (padrão: desligado) |
| `--init-state <save>` | de onde parte quem não tem retomada válida |

**Limite de 2 slots.** A máquina tem 8 GB e o swap vive perto do cheio; três
emuladores levam `SIGKILL` sem rastro no log. Duas corridas simultâneas também
se sobrescrevem, porque escrevem nos mesmos `trainers/`.

Diagnóstico:

```bash
python3 blue-agents/tools/stuck_report.py     # por que travou, com o motivo
python3 blue-agents/tools/forget_walls.py     # esquece paredes inventadas
python3 blue-agents/tools/measure_route.py    # save -> waypoints medidos
python3 blue-agents/tools/probe_route.py      # o que é alcançável de um save
```

---

## 9. Limitações conhecidas (declaradas, não descobertas pelo auditor)

1. **O jogo não é zerado.** 11 de 19 nós têm executor; o caminho para na Misty.
   Os 8 restantes precisam de waypoints medidos.
2. **Não há treino deliberado.** O nível sobe por acidente. O portão de nível
   antes da Floresta existe mas está **desligado**: cinco tentativas de decidir
   *onde* treinar erraram no cartucho (corredores que eram caminho de terra, ou
   que levavam o bot para dentro do treinador que os níveis existiam para
   sobreviver).
3. **Reabastecer Poké Bolas só funciona onde há Mart conhecido.**
   `POKE_MART_MAP_IDS = {42}` — só Viridian, o único em que o projeto entrou e
   comprou. O mecanismo é geral (lê a porta da tabela de warps); a lista é que
   cresce por medição.
4. **Tabela de golpes escrita à mão e incompleta.** Thundershock, Quick Attack,
   Leech Life e outros não estão nela, e golpe desconhecido não pontua — por
   isso um Pikachu prefere Growl a um golpe de dano. A tabela real está na ROM
   (banco `0x0E`, 6 bytes por golpe) e ainda não é lida.
5. **`POKEMON_CENTER_MAP_IDS` é lista fixa.** O Centro de Mt. Moon (mapa 68)
   ficou de fora por meses e por isso o trecho mais difícil alcançado era o
   único sem checkpoint. Hoje há um evento `unknown_center` que denuncia o caso,
   mas a lista continua sendo dado escrito à mão.
6. **Rotas são medidas por mapa, à mão.** Não há geração automática de rota; a
   ferramenta `measure_route.py` mede, mas alguém decide o alvo.
7. **PPO herdado praticamente não é usado**, e `latest_policy.zip` tem espaço de
   observação próprio deste fork (campo `personality`), então pesos de outros
   projetos não carregam.
8. **Pausa global usa `SIGSTOP`/`SIGCONT`**, que não existem no Windows. A pausa
   por agente é portátil.
9. **O detector de travamento tem pontos cegos conhecidos**: bot preso em caixa
   de texto retorna antes de o relatório ser escrito. O vaivém entre mapas era
   outro, corrigido em 2026-08-07.
10. **Rota 2 é dividida em duas metades sem ligação direta**, então reabastecer
    vindo do norte é impossível hoje.

---

## 10. Prompt para o auditor

Copie daqui para baixo.

---

> Você é um engenheiro sênior auditando um projeto de automação de jogo. O
> sistema faz bots jogarem **Pokémon Blue** num emulador real, sem editar
> memória para forçar progresso, com o objetivo de zerar o jogo por um caminho
> determinístico em que um bot possa entrar em qualquer ponto e seguir.
>
> O documento anexo descreve a arquitetura, as regras de decisão, os endereços
> de RAM lidos e as limitações que a equipe já reconhece. Leia-o como
> **afirmação da equipe, não como verdade verificada** — parte do seu trabalho é
> dizer onde a descrição e o código provavelmente divergem.
>
> **O que eu quero de você, nesta ordem:**
>
> 1. **Riscos de correção.** Onde este desenho pode produzir progresso falso —
>    isto é, o sistema declarar concluído algo que o jogo não concluiu — ou
>    perder progresso real? Preste atenção especial ao que é persistido, ao que
>    é compartilhado entre agentes e ao que é irreversível.
>
> 2. **A regra central sustenta?** A equipe afirma governar-se por "pergunte ao
>    cartucho, não guarde no processo". Aponte onde ela é violada na prática, e
>    onde seguir a regra ao pé da letra custa caro demais para valer.
>
> 3. **Conhecimento compartilhado.** Vários agentes escrevem nos mesmos arquivos
>    de conhecimento (terreno, portas, trilhas). Avalie corrida de escrita,
>    envenenamento de dado, e o fato de que um dado errado ali é permanente e
>    invisível. Proponha o mínimo que tornaria isso auto-corrigível.
>
> 4. **O caminho para zerar.** Faltam 8 executores de história, cada um hoje
>    exigindo waypoints medidos à mão. Existe abordagem melhor que medir cidade
>    por cidade? Considere explicitamente o custo/benefício de: gerar rota por
>    busca sobre o mapa, aproveitar rotas de speedrun/TAS existentes, ou colher
>    o traçado de um agente de RL que já termina o jogo (por exemplo
>    `pokemonred_puffer`) e converter em waypoints.
>
> 5. **O que está superdimensionado.** Diga o que remover. O projeto acumulou
>    camadas para compensar problemas que depois foram resolvidos na raiz;
>    suspeito que haja código morto e conceitos redundantes.
>
> 6. **Limitações que a equipe não listou.** A seção 9 é a autoavaliação deles.
>    O que falta nela?
>
> **Formato da resposta:** para cada achado, diga (a) o sintoma observável no
> jogo, (b) a causa provável no desenho, (c) o conserto mínimo, e (d) como
> verificar que o conserto funcionou **no cartucho**, não só em teste. Ordene
> por dano esperado. Seja específico e direto; se algo estiver certo, diga que
> está certo e siga.
>
> Se precisar do código para responder, diga exatamente quais arquivos e
> funções quer ver, em vez de supor.
