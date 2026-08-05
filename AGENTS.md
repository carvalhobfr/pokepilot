# PokeAI 2026 — instruções para agentes

Antes de alterar este projeto, leia **por inteiro** `docs/HANDOFF.md` e consulte
`docs/QUEST_GRAPH.md`. O handoff é a fonte canônica de continuidade; o mapa
visual mostra a ordem da jornada, o fluxo técnico e a diferença entre objetivo
planejado, executor implementado e trecho validado no cartucho.

## Regras obrigatórias

1. O alvo é a ROM real e exata de Pokémon Blue. Não substitua progressão real
   por dados sintéticos, salvo no modo de demonstração da interface.
2. Preserve `trainers/<AGENT>/current.state`, `current.sav`, `journey.json` e
   `logs/decisions.jsonl`. Nunca reinicie uma jornada sem pedido explícito.
3. No MacBook Air M1, mantenha **dois agentes no máximo por padrão**. Para
   depurar progressão, use apenas um agente.
4. Leia estado e eventos da RAM; não declare vitória, captura, evolução ou
   objetivo concluído apenas porque um botão foi enviado.
5. Scripts controlam história e batalha; PPO só deve aprender transições
   realmente controladas pela política. Não treine PPO com passos roteirizados.
6. Rode os testes antes e depois de alterações de jogabilidade. Faça primeiro
   revisão de código e validação curta; validação visual ampla fica para o fim.
7. Preserve mudanças existentes. O projeto está dentro de um repositório pai
   com muito conteúdo não relacionado; não use limpeza/reset global do Git.
8. Ao terminar uma sessão relevante, atualize a seção **Checkpoint mais
   recente** de `docs/HANDOFF.md`, incluindo fatos verificados, arquivos
   alterados, testes, comando de retomada e próximo bloqueio exato. Se a
   cobertura de uma quest mudou, atualize também o estado do nó em
   `docs/QUEST_GRAPH.md`.

## Retomada mínima

```bash
cd /Users/matheuscarvalho/Dev/2025/cursor/poke-ai-2026
sed -n '1,320p' docs/HANDOFF.md
sed -n '1,320p' docs/QUEST_GRAPH.md
cd blue-agents
MPLCONFIGDIR=tasks/matplotlib ../.venv/bin/python -m unittest discover -s tests -v
```

Não presuma que todos os 18 nós do QuestGraph possuem executor. O grafo define
o roteiro completo, mas a automação real validada ainda termina em Mt. Moon.
