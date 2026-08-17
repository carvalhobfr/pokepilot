"""Real walkability, read from the cartridge instead of learned by bumping.

The project navigated by memory of its own failures: press a direction, fail to
move, write that edge down as a wall. It worked, and it was fragile in one very
specific way — an NPC standing still is indistinguishable from a wall for that
one step, so people got recorded as geometry and never forgiven. A trainer spent
a night beside a Route 3 tile whose only obstacle had walked away hours before.

The cartridge knows better, and it turns out to be cheap to ask:

* ``wTilesetCollisionPtr`` (0xD530) points at the list of walkable tile ids for
  the current tileset. It lives in bank 0, so no bank switching is needed —
  which is what made this look expensive before.
* the visible tile map (0xC3A0, 20x18) says which tile is where on screen.
* the sprite table (0xC100, 16 bytes per sprite) says where the people are, and
  it is read fresh every step, so somebody walking away stops blocking.

Terrain is permanent truth; sprites are true right now. Neither has to be
remembered, and neither can be learned wrong.
"""

from __future__ import annotations

# Screen geometry: the player is drawn at a fixed spot and the world scrolls
# under it. Everything else is measured from there, in 16-pixel tiles.
PLAYER_SCREEN_X = 64
PLAYER_SCREEN_Y = 60
TILE_PIXELS = 16

# O tilemap que o jogo desenha na tela é o video map do Game Boy (0x9800 ou
# 0x9C00, conforme o LCDC), 32x32 células de 8px, com a janela visível
# selecionada por SCX/SCY (0xFF43/0xFF42). O 0xC3A0 (wTileMap) é outro buffer
# (metatiles de 16px) e não bate com a colisão real medida no cartucho
# (2026-08-12: AARON em Cerulean (39,17) — U aberto no jogo, "parede" no
# wTileMap; a leitura certa está no video map com o scroll).
VIDEO_MAP_BASE = 0x9800
# O buffer que o jogo usa para a colisão do overworld: 20x18 tiles de 8px com
# o jogador em posição de tela fixa (o mundo rola, ele não). Medido contra o
# cartucho (2026-08-13): na célula do pé do sprite (9,9), os vizinhos batem
# 4/4 com o movimento real na Rota 9 e no Cerulean; o video map (0x9800)
# dessincroniza em transições e mentia paredes.
W_TILE_MAP_ADDRESS = 0xC3A0
W_TILE_MAP_COLUMNS = 20
W_TILE_MAP_ROWS = 18
VIDEO_MAP_ALT = 0x9C00
VIDEO_MAP_COLUMNS = 32
VIDEO_MAP_ROWS = 32
SCROLL_X_ADDRESS = 0xFF43
SCROLL_Y_ADDRESS = 0xFF42
LCDC_ADDRESS = 0xFF40
# A janela visível é 20x18 células de 8px; o jogador fica centralizado
# (10,9) quando a câmera pode rolar.
PLAYER_TILEMAP_COLUMN = 8
PLAYER_TILEMAP_ROW = 9

COLLISION_POINTER_ADDRESS = 0xD530
# Which tile id is tall grass in the current tileset — the one that produces
# wild encounters. It changes per tileset, and the cartridge keeps it here.
GRASS_TILE_ADDRESS = 0xD535
# The LCD window register. Every screen the game draws over the map — a battle,
# a menu, a shop, the text box of a forced conversation — brings the window
# down; parking it at the screen height is how the game hides it. Reading it is
# how the terrain memory knows the map is really what is on screen.
WINDOW_Y_ADDRESS = 0xFF4A
WINDOW_HIDDEN_Y = 144
# Counts a step down while it plays: 0 standing, 7..1 walking. The player's map
# coordinates only catch up at the end, so anything read from the screen before
# then belongs to a tile the game has not admitted arriving at yet.
WALK_COUNTER_ADDRESS = 0xCFC5
SPRITE_TABLE_ADDRESS = 0xC100
SPRITE_ENTRY_SIZE = 0x10
SPRITE_SLOTS = 16

# Warps are invisible to the tileset: a door tile is not in the walkable list,
# yet stepping onto (or off of) it is exactly how you leave the building. The
# map's own warp table says where they are.
PLAYER_X_ADDRESS = 0xD362
PLAYER_Y_ADDRESS = 0xD361
WARP_COUNT_ADDRESS = 0xD3AE
WARP_TABLE_ADDRESS = 0xD3AF
WARP_ENTRY_SIZE = 4

DIRECTION_STEPS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}


class TileCollision:
    """Walkability around the player, straight from the running cartridge."""

    def __init__(self, emulator):
        self.emulator = emulator

    def _byte(self, address):
        return int(self.emulator.memory[address])

    def _rom_byte(self, address):
        # Bank 0 is always mapped, so this needs no bank switching.
        return int(self.emulator.memory[0, address])

    def _video_map_base(self):
        """Which 0x9800/0x9C00 block the LCDC points the background at."""
        try:
            lcdc = self._byte(LCDC_ADDRESS)
        except Exception:
            return VIDEO_MAP_BASE
        return VIDEO_MAP_ALT if lcdc & 0x08 else VIDEO_MAP_BASE

    def _player_tilemap_cell(self):
        """Cell of the screen tile map the player actually stands on.

        O sprite do jogador (OAM slot 0) diz onde ele está na tela — em
        mapas grandes o scroll o mantém em (64,60) (célula (9,9) do wTileMap
        20x18), mas em mapas pequenos (um Centro 14x8) o mapa não rola e o
        jogador anda pela tela. O pé do sprite de 16px é a célula de colisão:
        (screen_x+8)//8, (screen_y+16)//8. Medido contra o cartucho em
        2026-08-13: Rota 9 (3,9) e Cerulean (39,17) batem 4/4 com a colisão
        real; o scroll (SCX/SCY) e uma célula fixa falharam em mapas
        pequenos (GARON preso no Centro 64 lendo paredes onde o jogo abre).
        """
        try:
            screen_x = self._byte(SPRITE_TABLE_ADDRESS + 6)
            screen_y = self._byte(SPRITE_TABLE_ADDRESS + 4)
        except Exception:
            return PLAYER_TILEMAP_COLUMN, PLAYER_TILEMAP_ROW
        column = (screen_x + 8) // 8
        row = (screen_y + 16) // 8
        if not (0 <= column < W_TILE_MAP_COLUMNS and 0 <= row < W_TILE_MAP_ROWS):
            return PLAYER_TILEMAP_COLUMN, PLAYER_TILEMAP_ROW
        return column, row

    def _video_tile(self, column, row):
        base = self._video_map_base()
        return self._byte(base + (row % VIDEO_MAP_ROWS) * VIDEO_MAP_COLUMNS
                          + (column % VIDEO_MAP_COLUMNS))

    def _w_tile(self, column, row):
        """Tile id in the overworld collision buffer (0xC3A0, 20x18)."""
        if not (0 <= column < W_TILE_MAP_COLUMNS and 0 <= row < W_TILE_MAP_ROWS):
            return 0xFF
        return self._byte(W_TILE_MAP_ADDRESS + row * W_TILE_MAP_COLUMNS + column)

    def walkable_tiles(self):
        """Tile ids the current tileset lets the player stand on."""
        pointer = self._byte(COLLISION_POINTER_ADDRESS) + (
            self._byte(COLLISION_POINTER_ADDRESS + 1) << 8
        )
        tiles = set()
        for offset in range(256):
            value = self._rom_byte(pointer + offset)
            if value == 0xFF:
                break
            tiles.add(value)
        return tiles

    def occupied_offsets(self):
        """Tile offsets, relative to the player, where a sprite is standing."""
        occupied = set()
        for slot in range(1, SPRITE_SLOTS):
            base = SPRITE_TABLE_ADDRESS + slot * SPRITE_ENTRY_SIZE
            if self._byte(base) == 0:
                continue
            screen_y = self._byte(base + 4)
            screen_x = self._byte(base + 6)
            dx, remainder_x = divmod(screen_x - PLAYER_SCREEN_X, TILE_PIXELS)
            dy, remainder_y = divmod(screen_y - PLAYER_SCREEN_Y, TILE_PIXELS)
            if remainder_x or remainder_y:
                # Mid-step: the sprite is between tiles and will settle on one
                # of them. Rounding here would invent an obstacle.
                continue
            occupied.add((dx, dy))
        return occupied

    def warp_offsets(self):
        """Tile offsets, relative to the player, that hold a warp."""
        offsets = set()
        player_x = self._byte(PLAYER_X_ADDRESS)
        player_y = self._byte(PLAYER_Y_ADDRESS)
        for slot in range(self._byte(WARP_COUNT_ADDRESS)):
            base = WARP_TABLE_ADDRESS + slot * WARP_ENTRY_SIZE
            offsets.add((self._byte(base + 1) - player_x, self._byte(base) - player_y))
        return offsets

    def warp_tiles(self):
        """Every warp on this map, in map coordinates."""
        tiles = set()
        for slot in range(self._byte(WARP_COUNT_ADDRESS)):
            base = WARP_TABLE_ADDRESS + slot * WARP_ENTRY_SIZE
            tiles.add((self._byte(base + 1), self._byte(base)))
        return tiles

    def warp_destinations(self):
        """Every door on this map and the map it leads to.

        The warp entry is four bytes and only the first two were ever read:
        where the door is. The fourth says where it goes, and that is what
        turns "walk to the Mart" into a question the cartridge can answer
        instead of a route measured by hand for one city.
        """
        doors = {}
        for slot in range(self._byte(WARP_COUNT_ADDRESS)):
            base = WARP_TABLE_ADDRESS + slot * WARP_ENTRY_SIZE
            tile = (self._byte(base + 1), self._byte(base))
            doors[tile] = self._byte(base + 3)
        return doors

    def on_warp(self):
        """True when the player is standing on a warp tile."""
        return (0, 0) in self.warp_offsets()

    def terrain_grid(self):
        """Walkability of the visible tiles, ignoring who is standing on them.

        This is the version worth remembering. People move, so recording them
        would rebuild the exact disease this module was written to cure: an NPC
        turned into permanent geometry.

        Empty when the screen is not showing the map. The tile map is shared
        with every other screen the game draws — a battle, a shop, a Pokédex
        page — and none of their tiles belong to the walkable set, so a reading
        taken over one of them says "wall" about eighty tiles at once. Stored,
        that is permanent: nothing in the project ever unlearns a wall. It cost
        4067 invented walls across seventeen maps, the Forest remembered as four
        sealed pockets, and a trainer that stood on (6,30) for four thousand
        steps because its own map offered nowhere to go.

        Two questions, both put to the cartridge rather than to a flag:

        The window register has to say nothing is drawn over the map. This is
        the one that covers a **forced conversation**: a text box does not stop
        the player's own tile from being map, so the second check below sails
        straight through one while the box quietly overwrites the tiles beneath
        it. Measured on the cartridge, opening the START menu turned two map
        columns into walls in this very tile map. Battles, menus, shops and
        cutscene dialogue all bring the window down; only the map leaves it
        parked off screen.

        And the tile the player is standing on has to read as somewhere a
        player can stand. That is the backstop for whatever the window misses.
        """
        walkable = self.walkable_tiles()
        warps = self.warp_offsets()
        # Mid-step the screen has already scrolled half a tile while the player
        # coordinates still report the tile being left. The reading is fine and
        # the origin is wrong, so all eighty tiles get written one row off —
        # and a map stitched from readings that are each one tile out grows
        # walls that were never there. Measured from (31,24): 24 walkable
        # standing still, 27 mid-step, which is the answer for (31,23).
        #
        # This is the hole the other two checks left open. It survived the
        # first cleanup: 1075 fresh walls in two hours, and the Forest split in
        # two again with a route waypoint stranded on the far side.
        if self._byte(WALK_COUNTER_ADDRESS) != 0:
            return {}
        if self._byte(WINDOW_Y_ADDRESS) != WINDOW_HIDDEN_Y:
            return {}
        standing_col, standing_row = self._player_tilemap_cell()
        standing = self._w_tile(standing_col, standing_row)
        if standing not in walkable and (0, 0) not in warps:
            return {}
        grid = {}
        for dy in range(-(standing_row // 2), (W_TILE_MAP_ROWS - standing_row) // 2):
            for dx in range(
                -(standing_col // 2),
                (W_TILE_MAP_COLUMNS - standing_col) // 2,
            ):
                tile = self._w_tile(standing_col + dx, standing_row + dy)
                grid[(dx, dy)] = tile in walkable or (dx, dy) in warps
        grid[(0, 0)] = True
        return grid

    def grass_offsets(self):
        """Visible tiles that produce wild encounters, as player offsets.

        Which tile is tall grass changes with the tileset, and the cartridge
        keeps the answer in one byte. Guessing instead cost two training loops:
        a line at y=43 and then the crossing's own southern legs, both chosen
        because they looked like the entrance, both measured at **one**
        encounter in three to four thousand steps. They are the dirt path. The
        grass was a column nine tiles to the west the whole time.
        """
        grass = self._byte(GRASS_TILE_ADDRESS)
        standing_col, standing_row = self._player_tilemap_cell()
        offsets = []
        for dy in range(-(standing_row // 2), (W_TILE_MAP_ROWS - standing_row) // 2):
            for dx in range(
                -(standing_col // 2),
                (W_TILE_MAP_COLUMNS - standing_col) // 2,
            ):
                if self._w_tile(standing_col + dx, standing_row + dy) == grass:
                    offsets.append((dx, dy))
        return offsets

    def local_grid(self):
        """Walkability of every tile visible on screen, relative to the player.

        The four adjacent tiles are enough to avoid walking into a wall, and
        not enough to walk *around* one: a bot whose waypoint sat north of a
        cliff paced between two tiles forever, because each single step looked
        equally good. The screen shows about ten by nine map tiles — enough to
        find the way around what is in front.
        """
        walkable = self.walkable_tiles()
        occupied = self.occupied_offsets()
        warps = self.warp_offsets()
        standing_col, standing_row = self._player_tilemap_cell()
        grid = {}
        for dy in range(-(standing_row // 2), (W_TILE_MAP_ROWS - standing_row) // 2):
            for dx in range(
                -(standing_col // 2),
                (W_TILE_MAP_COLUMNS - standing_col) // 2,
            ):
                tile = self._w_tile(standing_col + dx, standing_row + dy)
                walkable_here = tile in walkable or (dx, dy) in warps
                grid[(dx, dy)] = walkable_here and (dx, dy) not in occupied
        grid[(0, 0)] = True
        return grid

    def path_step(self, target_dx, target_dy):
        """First direction of the shortest visible path toward that offset.

        Only the screen is considered, so this never pretends to know the map.
        When the target is off screen it walks to the visible tile closest to
        it, which is the same thing a person does.
        """
        try:
            grid = self.local_grid()
        except Exception:
            return None
        if not grid:
            return None
        from collections import deque

        came = {(0, 0): None}
        queue = deque([(0, 0)])
        while queue:
            tile = queue.popleft()
            for direction, (dx, dy) in DIRECTION_STEPS.items():
                neighbour = (tile[0] + dx, tile[1] + dy)
                if neighbour in came or not grid.get(neighbour, False):
                    continue
                came[neighbour] = (tile, direction)
                queue.append(neighbour)

        reachable = [tile for tile in came if tile != (0, 0)]
        if not reachable:
            return None

        def rank(tile):
            return (
                abs(tile[0] - target_dx) + abs(tile[1] - target_dy),
                abs(tile[0]) + abs(tile[1]),
            )

        goal = min(reachable, key=rank)
        if rank(goal)[0] >= abs(target_dx) + abs(target_dy):
            # Nothing visible gets closer and nowhere new to try; let the
            # caller decide.
            return None
        node = goal
        while came[node][0] != (0, 0):
            node = came[node][0]
        return came[node][1]

    def blocked_directions(self):
        """Which of the four steps the game would refuse right now, and why.

        Lê o wTileMap (0xC3A0, 20x18 tiles de 8px) — o buffer que o jogo usa
        para a colisão do overworld — na célula do pé do sprite do jogador.
        O jogador fica em tela fixa (64,60) e o mundo rola sob ele; o pé do
        sprite (16px) é a célula (9,9). Medido contra o cartucho em
        2026-08-13: a célula (9,9) bate 4/4 com o movimento real na Rota 9
        (beco: U/L move, R/D parede) e no Cerulean (39,17: U/L/R move, D
        parede). O video map (0x9800) dessincroniza em transições de mapa e
        mentia paredes — o bot ficava parado no beco com L aberto no jogo.
        """
        try:
            walkable = self.walkable_tiles()
            occupied = self.occupied_offsets()
            warps = self.warp_offsets()
        except Exception:
            # Anything unreadable means "no opinion"; the caller keeps its own
            # learned map rather than inventing walls.
            return {}
        # Standing on a door, the way out is the step the tileset calls a wall:
        # the lab exit reads as blocked terrain and four trainers sat on it.
        # On a warp tile, terrain has no say — only people can still be in front.
        on_warp = (0, 0) in warps
        # A célula de colisão do jogador no wTileMap vem do scroll (SCX/SCY),
        # como o video map: o jogador em pixel (x*16+8, y*16+8) menos o scroll,
        # dividido por 8px. Uma célula fixa só funcionava em mapas grandes —
        # em um Centro (14x8) o jogador anda pela tela e (9,9) apontava para o
        # tile errado, lendo paredes onde o jogo abre (medido 2026-08-13:
        # GARON preso no Centro 64 oscilando entre (2,3) e (3,3)).
        standing_col, standing_row = self._player_tilemap_cell()
        blocked = {}
        for direction, (dx, dy) in DIRECTION_STEPS.items():
            if (dx, dy) in occupied:
                blocked[direction] = "sprite"
                continue
            if on_warp or (dx, dy) in warps:
                continue
            col = standing_col + dx
            row = standing_row + dy
            if not (0 <= col < 20 and 0 <= row < 18):
                continue
            tile = self._byte(W_TILE_MAP_ADDRESS + row * 20 + col)
            if tile not in walkable:
                blocked[direction] = "terrain"
        return blocked
