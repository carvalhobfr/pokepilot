"""Kanto como um grafo só: nó é `(mapa, x, y)`, aresta é um passo possível.

`MapMemory.find_path` responde dentro de **um** mapa. Atravessar Kanto virou,
por isso, onze executores escritos à mão com as coordenadas de cada travessia
decoradas — e cada travessia nova custa medição, cada erro de digitação custa
uma corrida. Foi assim que a rota do vermilion apontou para a Rota 9 por dias.

Aqui as três ligações que o cartucho tem viram arestas do mesmo grafo:

| aresta | de onde vem | o que é |
|---|---|---|
| vizinho | `static_maps.json` | um passo dentro do mapa |
| borda | `connections.json` | sair pela borda e o jogo carregar o vizinho |
| porta | `connections.json` | pisar num warp e chegar no warp de destino |

Com isso, "ir de onde estou até `(mapa, tile)`" é **uma busca**, de qualquer
ponto para qualquer ponto, e sair da rota deixa de precisar de reentrada: a
busca seguinte já parte de onde o bot está. É o que o trail tentava ser sem
saber o que é porta nem o que é parede — e o trail dirigindo por cima do
executor foi a causa dos três travamentos de 2026-08-17.

O que este módulo **não** faz: decidir objetivo, falar com NPC, lutar. Ele
responde caminho. Quem escolhe o alvo continua sendo o executor da quest.
"""

from __future__ import annotations

from collections import deque
import json
from pathlib import Path

from src.map_memory import MapMemory

CONNECTIONS_PATH = (
    Path(__file__).resolve().parents[1]
    / "blue-agents" / "knowledge" / "maps" / "connections.json"
)

# Passo por direção, na convenção deste projeto: y cresce para o sul.
STEPS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}
# Para onde se anda para sair por cada borda.
BORDER_STEP = {"north": "U", "south": "D", "west": "L", "east": "R"}


class KantoGraph:
    """Busca em largura sobre `(mapa, x, y)` com borda e porta como aresta."""

    def __init__(self, map_memory=None, connections_path=CONNECTIONS_PATH,
                 avoid_objects=True):
        self.maps = map_memory or MapMemory()
        # Objeto do ROM (treinador parado, item ball, NPC de planta) é sólido no
        # plano normal — a mesma regra do `_planned_step`. Quem quiser o
        # caminho que a luta abre desliga isto.
        self.avoid_objects = bool(avoid_objects)
        self._passable = {}
        self.borders, self.warps = self._load(connections_path)
        self._returns = self._resolve_dynamic_returns()

    # --- dados -----------------------------------------------------------

    @staticmethod
    def _load(path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}, {}
        borders, warps = {}, {}
        for key, entry in (data.get("maps") or {}).items():
            map_id = int(key)
            borders[map_id] = list(entry.get("borders") or [])
            warps[map_id] = list(entry.get("warps") or [])
        return borders, warps

    def _resolve_dynamic_returns(self):
        """Para onde vai uma porta com destino `-1`, pelo **par mútuo**.

        `0xFF` no destino é "volta para o mapa de onde vim", que o cartucho
        resolve em tempo de execução. Estaticamente o par resolve sozinho, sem
        palpite: a porta `i` do mapa A que aponta para o warp `k` só pode ir
        para o mapa B cuja porta `k` aponta de volta para a porta `i` de A.

        Medido no portão norte da Floresta, onde um palpite por "quem aponta
        para cá" ficaria ambíguo entre a Rota 2 e a Floresta: a porta 1 do
        portão 47 é `(5,0)` com `to_warp=1`, e a porta 1 da Rota 2 é `(3,11)`
        com `to_warp=1` apontando para o 47 — par mútuo. A porta 1 da Floresta
        aponta para o warp 3, então ela não é o par e sai da conta.

        Sem esta resolução o grafo parava na Floresta: Kanto inteiro ao norte
        de Pewter ficava inalcançável, porque todo portão tem as duas portas de
        fora dinâmicas.
        """
        pairs = {}
        for map_id, doors in self.warps.items():
            for index, door in enumerate(doors):
                key = (int(door.get("to", -1)), int(door.get("to_warp", 0)), index)
                pairs.setdefault(key, []).append(map_id)
        resolved = {}
        for map_id, doors in self.warps.items():
            for index, door in enumerate(doors):
                if int(door.get("to", -1)) >= 0:
                    continue
                target_index = int(door.get("to_warp", 0))
                candidates = pairs.get((map_id, index, target_index), [])
                if len(candidates) != 1:
                    continue
                other = candidates[0]
                arrivals = self.warps.get(other) or []
                if target_index >= len(arrivals):
                    continue
                arrival = arrivals[target_index]
                resolved[(map_id, int(door["x"]), int(door["y"]))] = (
                    other, int(arrival["x"]), int(arrival["y"])
                )
        return resolved

    def _cells(self, map_id):
        """Onde se pode estar de pé — **incluindo as portas**.

        O estático do ROM não marca tile de warp como andável, e é por isso que
        `_planned_step` precisa de uma exceção para a porta: `find_path` acha
        que a soleira é parede. Aqui a porta tem de ser nó, porque **pisar nela
        é como se atravessa** — sem isso não existe caminho para dentro de
        prédio nenhum, e a busca respondia "sem caminho" para tudo.
        """
        map_id = int(map_id)
        cached = self._passable.get(map_id)
        if cached is None:
            cached = set(self.maps.static.get(map_id) or set())
            cached |= {
                (int(door["x"]), int(door["y"]))
                for door in self.warps.get(map_id, [])
            }
            self._passable[map_id] = cached
        return cached

    def _blocked(self, map_id):
        if not self.avoid_objects:
            return set()
        try:
            return set(self.maps.object_positions(int(map_id)))
        except Exception:
            return set()

    def _size(self, map_id):
        cells = self._cells(map_id)
        if not cells:
            return (0, 0)
        return (max(x for x, _ in cells) + 1, max(y for _, y in cells) + 1)

    # --- arestas ---------------------------------------------------------

    def warp_arrival(self, map_id, door):
        """Onde uma porta chega: o warp de índice `to_warp` no mapa de destino."""
        destination = int(door.get("to", -1))
        if destination < 0:
            return self._returns.get(
                (int(map_id), int(door["x"]), int(door["y"]))
            )
        doors = self.warps.get(destination) or []
        index = int(door.get("to_warp", 0))
        if index >= len(doors):
            return None
        arrival = doors[index]
        return (destination, int(arrival["x"]), int(arrival["y"]))

    def border_arrival(self, map_id, border, x, y):
        """Onde uma borda deixa o jogador, pela conta dos alinhamentos."""
        destination = int(border["to"])
        if border["dir"] in ("north", "south"):
            return (
                destination,
                x + int(border["x_align"]),
                int(border["y_align"]),
            )
        return (
            destination,
            int(border["x_align"]),
            y + int(border["y_align"]),
        )

    def jumps(self, map_id, x, y):
        """Pulos de penhasco a partir daqui: aresta de **mão única**.

        O penhasco é o que parte um mapa no estático: o tile do meio lê como
        parede, então `find_path` diz "sem caminho" e a Rota 4 fica em dois
        pedaços — foi ela que segurou o grafo na saída de Mt. Moon, com a borda
        leste (x=89) inalcançável do lado de Mt. Moon.

        A assinatura é geométrica: pisável aqui, sólido a um tile, pisável a
        dois. **E é a mesma assinatura de parede com chão atrás** — este projeto
        já pagou por confundir as duas (250 passos batendo `R` contra a parede
        da Rota 5 com a porta do Underground atrás). Por isso o pulo é a última
        opção da busca (`path` tenta primeiro sem nenhum) e vem marcado com `J`,
        para o executor saber que aquele passo é um pulo e não um passo comum.
        """
        cells = self._cells(map_id)
        found = []
        # Em Gen I não se pula para cima: o penhasco é descida, e há versões
        # para os lados.
        for key, (dx, dy) in (("D", (0, 1)), ("L", (-1, 0)), ("R", (1, 0))):
            middle = (x + dx, y + dy)
            landing = (x + dx * 2, y + dy * 2)
            if middle in cells or landing not in cells:
                continue
            found.append(("J" + key, (map_id, landing[0], landing[1])))
        return found

    def neighbors(self, node, allow_jumps=False):
        """Todo passo possível a partir de um nó, com a tecla que o produz."""
        map_id, x, y = node
        cells = self._cells(map_id)
        blocked = self._blocked(map_id)
        width, height = self._size(map_id)
        found = []

        for key, (dx, dy) in STEPS.items():
            target = (x + dx, y + dy)
            if target in cells and target not in blocked:
                found.append((key, (map_id, target[0], target[1])))

        if allow_jumps:
            found.extend(self.jumps(map_id, x, y))

        for border in self.borders.get(map_id, []):
            key = BORDER_STEP[border["dir"]]
            on_edge = (
                (border["dir"] == "north" and y == 0)
                or (border["dir"] == "south" and y == height - 1)
                or (border["dir"] == "west" and x == 0)
                or (border["dir"] == "east" and x == width - 1)
            )
            if not on_edge or (x, y) not in cells:
                continue
            arrival = self.border_arrival(map_id, border, x, y)
            if arrival[1:] in self._cells(arrival[0]):
                found.append((key, arrival))

        for door in self.warps.get(map_id, []):
            if (int(door["x"]), int(door["y"])) != (x, y):
                continue
            arrival = self.warp_arrival(map_id, door)
            # A porta consome o passo: quem está em cima dela atravessa, e a
            # tecla é irrelevante para o grafo — o executor é que decide como
            # atravessar (em Gen I, andar contra a soleira).
            if arrival is not None and arrival[1:] in self._cells(arrival[0]):
                found.append(("W", arrival))
        return found

    # --- busca -----------------------------------------------------------

    def path(self, start, goal, limit=200_000, allow_jumps=None):
        """Lista de nós de `start` a `goal`, ou `None`. Nó é `(mapa, x, y)`.

        Sem heurística de propósito: a distância em linha reta não significa
        nada entre mapas diferentes, e "o mais perto" medido em linha reta é o
        erro que este projeto já pagou três vezes. Kanto tem ~49 mil células, e
        uma busca em largura sobre isso é barata.

        `allow_jumps=None` (o padrão) busca **primeiro sem pulo de penhasco** e
        só tenta com pulo quando não há caminho andando. É a mesma ordem de
        autoridade do executor — quem tem caminho andando não pula —, e aqui ela
        também protege contra o falso pulo: parede com chão atrás tem a mesma
        assinatura no estático.
        """
        if allow_jumps is None:
            walking = self.path(start, goal, limit, allow_jumps=False)
            if walking is not None:
                return walking
            return self.path(start, goal, limit, allow_jumps=True)
        start = tuple(int(v) for v in start)
        goal = tuple(int(v) for v in goal)
        if start == goal:
            return [start]
        queue = deque([start])
        came_from = {start: None}
        while queue and len(came_from) < limit:
            node = queue.popleft()
            for _key, neighbour in self.neighbors(node, allow_jumps=allow_jumps):
                if neighbour in came_from:
                    continue
                came_from[neighbour] = node
                if neighbour == goal:
                    return self._rebuild(came_from, neighbour)
                queue.append(neighbour)
        return None

    def steps(self, path, allow_jumps=True):
        """As teclas de um caminho — `J*` marca pulo de penhasco.

        É o que separa "andar" de "pular" para quem executa: um pulo é um passo
        que atravessa dois tiles, e tratá-lo como passo comum foi o que fez o
        bot bater contra a parede por 250 passos na Rota 5.
        """
        keys = []
        for current, following in zip(path or [], (path or [])[1:]):
            for key, neighbour in self.neighbors(current, allow_jumps=allow_jumps):
                if neighbour == following:
                    keys.append(key)
                    break
            else:
                keys.append("?")
        return keys

    @staticmethod
    def _rebuild(came_from, node):
        path = [node]
        while came_from[path[-1]] is not None:
            path.append(came_from[path[-1]])
        path.reverse()
        return path

    def maps_crossed(self, path):
        """A sequência de mapas de um caminho, sem repetir vizinho."""
        crossed = []
        for map_id, _x, _y in path or ():
            if not crossed or crossed[-1] != map_id:
                crossed.append(map_id)
        return crossed

    def legs(self, path):
        """O caminho quebrado por mapa: `[(mapa, [(x,y), ...]), ...]`.

        É a forma que o executor consome: cada perna é uma lista de tiles de um
        mapa só, que é exatamente o que `_follow_route` já sabe andar.
        """
        legs = []
        for map_id, x, y in path or ():
            if not legs or legs[-1][0] != map_id:
                legs.append((map_id, []))
            legs[-1][1].append((x, y))
        return legs
