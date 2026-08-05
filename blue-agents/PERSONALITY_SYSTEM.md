# Sistema de Personalidade dos Agentes - PokeAI Blue

## 📊 Atributos de Personalidade (0-100)

Cada agente tem 4 atributos principais que definem seu comportamento:

### 1. **Meta Score** (Estratégia)
- **100**: Ultra Meta - Escolhe pokémons ótimos, evita desvantagens de tipo
- **50**: Balanceado - Mix de estratégia e variedade
- **0**: Caótico - Recusa "easy mode", busca desafio

### 2. **Exploration** (Exploração)
- **100**: Explorador nato - Prioriza descobrir novos mapas e áreas
- **50**: Balanceado - Explora quando conveniente
- **0**: Focado - Vai direto ao objetivo, ignora desvios

### 3. **Collector** (Colecionador)
- **100**: Completista - Tenta capturar todos os pokémons possíveis
- **50**: Balanceado - Captura quando necessário
- **0**: Minimalista - Só captura o essencial para missões

### 4. **Mission Focus** (Foco em Missão)
- **100**: Laser-focused - Prioriza badges e story progression
- **50**: Balanceado - Mix de missões e exploração
- **0**: Livre - Ignora missões, joga por diversão

## 🎭 Perfis dos 9 Agentes

### AARON - "Chaos Incarnate"
- Meta: 0 (Puro caos, recusa Bulbasaur)
- Exploration: 90 (Adora explorar)
- Collector: 30 (Só captura se interessante)
- Mission: 20 (Ignora missões, joga por diversão)
- **Starter**: Charmander (Hard mode!)

### Khalliss - "Ultra Meta Optimizer"
- Meta: 100 (Estratégia perfeita)
- Exploration: 40 (Explora só o necessário)
- Collector: 70 (Coleta estrategicamente)
- Mission: 100 (Foco total em badges)
- **Starter**: Bulbasaur (Optimal)

### BARON - "Strategic Warrior"
- Meta: 75 (Muito estratégico)
- Exploration: 60 (Explora moderadamente)
- Collector: 50 (Balanceado)
- Mission: 80 (Alto foco em missões)
- **Starter**: Charmander

### CARON - "Balanced Explorer"
- Meta: 50 (Perfeitamente balanceado)
- Exploration: 85 (Adora explorar)
- Collector: 60 (Coleta bastante)
- Mission: 50 (Balanceado)
- **Starter**: Squirtle

### DARON - "Meta Optimizer"
- Meta: 85 (Muito meta)
- Exploration: 30 (Pouca exploração)
- Collector: 90 (Completista!)
- Mission: 75 (Alto foco)
- **Starter**: Bulbasaur

### EARON - "Challenge Seeker"
- Meta: 25 (Busca desafio)
- Exploration: 70 (Explora bastante)
- Collector: 40 (Coleta pouco)
- Mission: 60 (Foco moderado)
- **Starter**: Charmander

### FARON - "Tactical Adventurer"
- Meta: 60 (Levemente estratégico)
- Exploration: 95 (Explorador máximo!)
- Collector: 55 (Balanceado)
- Mission: 45 (Baixo foco em missões)
- **Starter**: Squirtle

### GARON - "Min-Maxer"
- Meta: 90 (Quase perfeito)
- Exploration: 25 (Ignora exploração)
- Collector: 80 (Coleta muito)
- Mission: 95 (Quase 100% foco)
- **Starter**: Bulbasaur

### HARON - "Hard Mode Enthusiast"
- Meta: 10 (Quase puro caos)
- Exploration: 80 (Explora muito)
- Collector: 35 (Coleta pouco)
- Mission: 30 (Baixo foco)
- **Starter**: Charmander (Hard mode!)

## ⚖️ Regras de Balanceamento

1. **Nenhum agente pode ter todos os atributos abaixo de 30**
2. **Cada agente deve ter pelo menos 1 atributo acima de 70**
3. **A soma dos 4 atributos deve estar entre 180-280** (média 45-70 por atributo)
4. **Pelo menos 3 agentes devem ter Charmander** (desafio)
5. **Pelo menos 3 agentes devem ter Bulbasaur** (meta)
6. **Pelo menos 2 agentes devem ter Squirtle** (balanceado)

## 🎯 Impacto no Gameplay

### Meta Score
- **Alto**: Bonus em batalhas estratégicas, escolhe tipos vantajosos
- **Baixo**: Bonus massivo ao vencer com desvantagem (+1000 pts)

### Exploration
- **Alto**: +50% recompensa por descobrir novos mapas
- **Baixo**: +30% recompensa por progression rápida

### Collector
- **Alto**: +40% recompensa por capturar pokémons
- **Baixo**: +20% recompensa por eficiência (menos capturas)

### Mission Focus
- **Alto**: +50% recompensa por badges e eventos
- **Baixo**: +30% recompensa por exploração livre

## 📈 Validação dos Perfis

| Agente   | Meta | Expl | Coll | Miss | Total | Válido? |
|----------|------|------|------|------|-------|---------|
| AARON    | 0    | 90   | 30   | 20   | 140   | ❌ Baixo |
| Khalliss | 100  | 40   | 70   | 100  | 310   | ❌ Alto  |
| BARON    | 75   | 60   | 50   | 80   | 265   | ✅       |
| CARON    | 50   | 85   | 60   | 50   | 245   | ✅       |
| DARON    | 85   | 30   | 90   | 75   | 280   | ✅       |
| EARON    | 25   | 70   | 40   | 60   | 195   | ✅       |
| FARON    | 60   | 95   | 55   | 45   | 255   | ✅       |
| GARON    | 90   | 25   | 80   | 95   | 290   | ❌ Alto  |
| HARON    | 10   | 80   | 35   | 30   | 155   | ❌ Baixo |

**Precisa ajustar**: AARON, Khalliss, GARON e HARON
