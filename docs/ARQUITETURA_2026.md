# Arquitetura PokeAI 2026

## Estado atual

O caminho ativo é:

```text
PyBoy headless
  -> RedGymEnv (emulação, observação, recompensa)
  -> HybridGymEnv (quest, batalha, personalidade, checkpoints)
  -> StreamWrapper (amostragem WebSocket)
  -> relay Node
  -> dashboard React/Pixi
```

O PPO é compartilhado pelos dois agentes ativos e recebe a personalidade como parte
da observação. As lutas e etapas críticas da história ainda são híbridas: regras
e scripts assumem o controle quando a navegação precisa ser determinística.
Cada agente mantém um estado PyBoy por processo entre limites de rollout, então
o treino contínuo não reinicia a jornada no mesmo estado inicial a cada lote.
Eventos completos ficam em JSONL por agente; o feed compartilhado é apenas uma
janela curta para a UI.

## Decisões de performance já aplicadas

- CPU é o padrão para PPO; MPS é opt-in porque o runtime precisa reportar MPS
  disponível e PPO pequeno pode não ganhar com a GPU integrada.
- O ambiente usa janela `headless`, sem render durante o `tick` de treino.
- Downsample e bits de eventos usam NumPy; o transformador de imagem pesado não
  roda mais a cada passo.
- O estado JSON, comandos e sinais de salvamento são consultados em cadências
  discretas, não em todas as ações.
- O stream de exploração é amostrado e o frame opcional de batalha usa WebP.
- Modelos novos compartilham o extrator de features entre ator e crítico.
- Histórico de TensorBoard, logs e artefatos de treino ficam fora de commits por
  meio do `.gitignore`.

## Próximas fases recomendadas

### Fase 1 — Observabilidade confiável

Adicionar métricas de `env_steps/s`, tempo de emulação, tempo de recompensa,
tempo de inferência, tamanho médio dos frames e uso de memória. O dashboard deve
receber um snapshot agregado por lote, não quatro listeners independentes lendo
o mesmo WebSocket.

### Fase 2 — Política de navegação mais barata

Separar a observação de navegação da imagem completa. Posição, mapa, tiles
visitados, eventos e objetivo podem ser uma política MLP; a imagem fica para
uma política visual usada somente quando o estado de memória é ambíguo. Isso
reduz bastante as convoluções sem tirar a visão da arena.

### Fase 3 — Ambiente de jogo modular

Separar em módulos:

- `GameState`: leitura tipada da RAM;
- `BattleController`: menu, golpes, troca, itens e captura;
- `QuestController`: detonado por marcos verificáveis;
- `NavigationController`: mapa de warps e caminho;
- `AgentPolicy`: PPO, regras ou modo manual;
- `TelemetryWriter`: fila assíncrona para dashboard/SQLite.

Assim, adicionar a próxima cidade não exige alterar o loop de emulação inteiro.

### Fase 4 — Paralelismo medido

Manter dois agentes como padrão no Air M1 e aumentar apenas após medir temperatura.
Depois comparar `DummyVecEnv` com
`SubprocVecEnv` usando o mesmo seed e medir temperatura, memória e passos por
segundo. Só adotar subprocessos se o ganho compensar o custo de serializar
observações e manter conexões de stream adicionais.

### Fase 5 — Pokémon Blue completo

Transformar cada ginásio, rival, HM, rivalidade e Elite Four em um marco com
pré-condições, ação, verificação e checkpoint. O arquivo de Brock é apenas a
primeira fatia do detonado; ele não torna o agente capaz de terminar o jogo.
