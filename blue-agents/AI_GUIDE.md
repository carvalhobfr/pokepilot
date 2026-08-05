# 🤖 Sistema de IA Sob Demanda - Guia Completo

## 📋 Visão Geral

Este sistema permite que você consulte uma LLM (GPT-4o-mini) para obter estratégias personalizadas para cada agente **apenas quando necessário**, economizando custos e recursos.

## 🎯 Como Usar

### 1. Iniciar o Servidor AI (se não estiver rodando)
```bash
cd blue-agents
./run_ai_api.sh
```

### 2. No Dashboard
1. Abra o **Control Panel** (botão no canto superior direito)
2. Encontre o agente que precisa de ajuda
3. Clique no botão **"Ask AI for Strategy"** (roxo/azul com ✨)
4. Aguarde alguns segundos
5. Leia a análise detalhada no modal

## 💰 Comparação de Custos

| Modelo | Custo (1M tokens) | Qualidade | Recomendado Para |
|--------|-------------------|-----------|------------------|
| **gpt-3.5-turbo** | ~$0.50 | Boa | Economia máxima |
| **gpt-4o-mini** ⭐ | ~$0.15 (input) / $0.60 (output) | Muito Boa | **Uso Padrão** |
| **gpt-4o** | ~$2.50 (input) / $10 (output) | Excelente | Estratégias complexas |

**Estimativa de custo por consulta:**
- gpt-4o-mini: ~$0.001 por consulta (< 1 centavo!)
- gpt-4o: ~$0.01 por consulta (1 centavo)

## ⚙️ Configuração

### Trocar de Modelo

Edite `blue-agents/ai_config.py`:

```python
# Para economia máxima (mais barato)
AI_MODEL = "gpt-3.5-turbo"

# Para melhor custo-benefício (recomendado) ⭐
AI_MODEL = "gpt-4o-mini"

# Para máxima qualidade (mais caro)
AI_MODEL = "gpt-4o"
```

### Ajustar Tamanho da Resposta

```python
# Menor = Mais barato, mas respostas mais curtas
MAX_TOKENS = 500  # Economiza ainda mais

# Padrão = Bom equilíbrio
MAX_TOKENS = 800  # Recomendado

# Maior = Respostas mais detalhadas
MAX_TOKENS = 1200  # Para estratégias complexas
```

### Ajustar Criatividade

```python
# Mais consistente e previsível
TEMPERATURE = 0.3

# Balanceado (recomendado)
TEMPERATURE = 0.7

# Mais criativo e variado
TEMPERATURE = 1.0
```

## 📊 O Que a IA Analisa

A IA recebe e analisa:
- **Mapa atual** (Map ID)
- **Progresso** (Badges, Pokedex)
- **Party completo** (Pokemon, níveis, HP)
- **Status de batalha** (se está lutando)
- **Personalidade do agente**

E fornece:
1. **Prioridade Imediata**: O que fazer AGORA
2. **Próximo Objetivo**: Próximo milestone
3. **Estratégia de Time**: Como otimizar party
4. **Navegação**: Para onde ir
5. **Dicas Específicas**: Items, encontros, táticas

## 🔧 Troubleshooting

### Erro "Failed to connect to AI server"
```bash
# Verificar se o servidor está rodando
lsof -i :5002

# Se não estiver, inicie:
cd blue-agents
./run_ai_api.sh
```

### Erro "OpenAI API Key"
Verifique se sua chave está em `.env`:
```bash
OPENAI_API_KEY=sk-...
```

### Erro "Quota exceeded"
Você excedeu a cota da OpenAI. Opções:
1. Espere o limite resetar
2. Adicione créditos na OpenAI
3. Use um modelo mais barato (gpt-3.5-turbo)

## 💡 Dicas de Uso

### Quando Consultar a IA?
- ✅ Agente travado no mesmo lugar
- ✅ Dúvida sobre próximo objetivo
- ✅ Composição de party ruim
- ✅ Precisa de estratégia de gym
- ❌ Não precisa consultar toda hora (custa dinheiro!)

### Como Economizar
1. Use **gpt-4o-mini** (padrão) ao invés de gpt-4o
2. Reduza **MAX_TOKENS** para 500-600
3. Consulte apenas quando necessário
4. Uma consulta resolve vários agentes similares

## 🚀 Próximos Passos

Possíveis melhorias futuras:
- [ ] Cache de respostas similares
- [ ] Histórico de consultas
- [ ] Comparação de estratégias entre agentes
- [ ] Export de estratégias em PDF
- [ ] Templates de prompts personalizados

## 📝 Exemplo de Uso Real

```
Agente: GARON
Situação: Travado em Oak's Lab (Map 40), 0 badges

Você clica em "Ask AI" →

IA Responde:
"🎯 IMMEDIATE PRIORITY: Leave Oak's Lab and START your journey!
You're still in Oak's Lab. Walk DOWN to exit...
[...detailed strategy...]"

Custo: ~$0.0008 (menos de 1 centavo)
```

---

**Desenvolvido com ❤️ para PokeAI Blue**
