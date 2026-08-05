# Brock Quest - First Gym Badge

## Objetivo
Vencer Brock, líder do ginásio de Pewter City, e conquistar o **Boulder Badge** (primeira badge).

## Localização
- **Pewter City Gym** (Map ID: 54)
- Localizada em Pewter City (norte de Viridian Forest)

## Requisitos para o Sucesso

### 1. Nível Mínimo Recomendado
- **Nível 12-14** para cada Pokémon do time
- Bônus de +200 pontos se o time tiver média de nível >= 12

### 2. Tipos Vantajosos
Brock usa Pokémon tipo **Pedra/Terra** (Rock/Ground):
- **Geodude** (Rock/Ground) - Level 10
- **Onix** (Rock/Ground) - Level 12

**Tipos Super Efetivos contra Brock:**
- 💧 **Água (Water)** - 4x damage contra Rock/Ground
- 🌿 **Grama (Grass)** - 4x damage contra Rock/Ground  
- 🥊 **Luta (Fighting)** - 2x damage contra Rock

**Pokémon Recomendados:**
- Squirtle/Wartortle (Água)
- Bulbasaur/Ivysaur (Grama)
- Mankey/Primeape (Luta) - disponível em Route 22

### 3. Caminho até Pewter City
1. Pallet Town (Map 0) -> Route 1 (Map 12)
2. Route 1 -> Viridian City (Map 1)
3. Viridian City -> Route 2 (Map 13)
4. Route 2 -> Viridian Forest (Map 51)
5. Viridian Forest -> Route 2 North (Map 13)
6. Route 2 North -> Pewter City (Map 2)
7. Pewter City -> Pewter Gym (Map 54)

## Recompensas

### Recompensas In-Game
- **Boulder Badge** (bit 0 de 0xD356)
- Permite usar Flash fora de batalha
- Pokémon até nível 20 obedecem

### Recompensas do Sistema de RL
- **500 pontos** base por vencer Brock
- **+200 pontos** se o time tiver média de nível >= 12
- **+200 pontos** por cada badge (recompensa geral)
- **Total máximo: 900 pontos** pela primeira badge!

## Estratégia Recomendada

1. **Escolher Squirtle ou Bulbasaur** como starter (vantagem de tipo)
2. **Treinar até nível 12-14** em:
   - Route 1 (Pidgey, Rattata)
   - Route 22 (Mankey, Spearow)
   - Viridian Forest (Caterpie, Weedle, Pikachu)

3. **Capturar Pokémon úteis:**
   - Mankey (Route 22) - tipo Luta
   - Nidoran M/F (Routes 1, 2, 22) - aprende Double Kick (Luta)

4. **Equipar movimentos efetivos:**
   - Squirtle: Bubble (Água)
   - Bulbasaur: Vine Whip (Grama)
   - Mankey: Low Kick / Karate Chop (Luta)

## Notas Técnicas

### Event Flags Relacionados
- 0xD356 bit 0: Boulder Badge obtido
- 0xD75E bit 0: Defeated Brock (evento da batalha)

### Detecção no Código
```python
has_boulder_badge = (self.read_m(0xD356) & 0b00000001) != 0
```

### Mapa IDs Importantes
- Map 2: Pewter City
- Map 54: Pewter Gym
- Map 51: Viridian Forest
