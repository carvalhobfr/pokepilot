import random

try:
    # PyBoy exposes Gen I internal index numbers in battle RAM.  The type
    # table below is keyed by National Dex IDs, so use the project's canonical
    # conversion whenever the full runtime is available.  The fallback keeps
    # this small controller usable in isolated unit tests.
    from pokemon_ids import get_national_id
except ImportError:
    def get_national_id(internal_id):
        return internal_id

# Gen 1 Type Chart (0.5 = Not Very Effective, 2.0 = Super Effective, 0.0 = No Effect)
# Types: Normal, Fighting, Flying, Poison, Ground, Rock, Bug, Ghost, Steel(X), Fire, Water, Grass, Electric, Psychic, Ice, Dragon
# Mapping based on in-game indices usually, but simplified here for logic

TYPE_NAMES = [
    "NORMAL", "FIGHTING", "FLYING", "POISON", "GROUND", "ROCK", "BUG", "GHOST", "STEEL",
    "FIRE", "WATER", "GRASS", "ELECTRIC", "PSYCHIC", "ICE", "DRAGON"
]

# Native type ids stored in the battle structs. Reading these values is more
# reliable than maintaining a partial species table and keeps the controller
# correct for dual-type Pokémon it has never seen before. The mapping lives
# with the move table because the cartridge uses one set of ids for both.
from src.move_data import GEN1_TYPE_NAMES, MoveTable

# Pokemon Type Mapping (Species ID -> Types)
POKEMON_TYPES = {
    # Starters
    1: ["GRASS", "POISON"],  # Bulbasaur
    4: ["FIRE"],             # Charmander
    7: ["WATER"],            # Squirtle
    # Brock's Team
    74: ["ROCK", "GROUND"],  # Geodude
    95: ["ROCK", "GROUND"],  # Onix
    # Common early game
    16: ["NORMAL", "FLYING"], # Pidgey
    19: ["NORMAL"],          # Rattata
    25: ["ELECTRIC"],        # Pikachu
}

# Simplified effectiveness map (Attacker -> Defender -> Multiplier)
EFFECTIVENESS = {
    "NORMAL": {"ROCK": 0.5, "GHOST": 0.0},
    "FIGHTING": {"NORMAL": 2.0, "FLYING": 0.5, "POISON": 0.5, "ROCK": 2.0, "BUG": 0.5, "GHOST": 0.0, "PSYCHIC": 0.5, "ICE": 2.0},
    "FLYING": {"FIGHTING": 2.0, "ROCK": 0.5, "BUG": 2.0, "GRASS": 2.0, "ELECTRIC": 0.5},
    "POISON": {"POISON": 0.5, "GROUND": 0.5, "ROCK": 0.5, "BUG": 2.0, "GHOST": 0.5, "GRASS": 2.0},
    "GROUND": {"FLYING": 0.0, "POISON": 2.0, "ROCK": 2.0, "BUG": 0.5, "FIRE": 2.0, "GRASS": 0.5, "ELECTRIC": 2.0},
    "ROCK": {"FIGHTING": 0.5, "FLYING": 2.0, "GROUND": 0.5, "BUG": 2.0, "FIRE": 2.0, "ICE": 2.0},
    "BUG": {"FIGHTING": 0.5, "FLYING": 0.5, "POISON": 2.0, "GHOST": 0.5, "FIRE": 0.5, "GRASS": 2.0, "PSYCHIC": 2.0},
    "GHOST": {"NORMAL": 0.0, "PSYCHIC": 0.0, "GHOST": 2.0},
    "FIRE": {"ROCK": 0.5, "BUG": 2.0, "FIRE": 0.5, "WATER": 0.5, "GRASS": 2.0, "ICE": 2.0, "DRAGON": 0.5},
    "WATER": {"GROUND": 2.0, "ROCK": 2.0, "FIRE": 2.0, "WATER": 0.5, "GRASS": 0.5, "DRAGON": 0.5},
    "GRASS": {"FLYING": 0.5, "POISON": 0.5, "GROUND": 2.0, "ROCK": 2.0, "BUG": 0.5, "FIRE": 0.5, "WATER": 2.0, "GRASS": 0.5, "DRAGON": 0.5},
    "ELECTRIC": {"FLYING": 2.0, "GROUND": 0.0, "WATER": 2.0, "GRASS": 0.5, "ELECTRIC": 0.5, "DRAGON": 0.5},
    "PSYCHIC": {"FIGHTING": 2.0, "POISON": 2.0, "PSYCHIC": 0.5},
    "ICE": {"FLYING": 2.0, "GROUND": 2.0, "WATER": 0.5, "GRASS": 2.0, "ICE": 0.5, "DRAGON": 2.0},
    "DRAGON": {"DRAGON": 2.0}
}

# Gen I refuses to delete these moves from the level-up move replacement
# screen. Protect them before choosing a slot so the controller cannot enter
# the "HM can't be deleted" loop.
HM_MOVE_IDS = {15, 19, 57, 70, 148}

LEECH_SEED_MOVE_ID = 73

# Ordem de preferência quando nenhum golpe de dano tem PP. Menor é melhor.
# Leech Seed drena todo turno depois de plantada — vale uma vez. Sono e
# paralisia valem uma. Rebaixar atributo já no mínimo não vale nenhuma.
STATUS_MOVE_PRIORITY = {
    73: 0,    # Leech Seed
    79: 1,    # Sleep Powder
    147: 1,   # Spore
    95: 1,    # Hypnosis
    78: 2,    # Stun Spore
    86: 2,    # Thunder Wave
    77: 3,    # Poison Powder
    45: 9,    # Growl
    39: 9,    # Tail Whip
    106: 9,   # Harden
    43: 9,    # Leer
}

# Golpe de status vale **uma vez por batalha**, e só isso.
#
# Dormir já está dormindo; paralisado já está lento; a semente já drena todo
# turno depois de plantada. Repetir não acrescenta nada e gasta o turno. Com
# rebaixamento de atributo é pior: Growl tem 40 PP e o estágio de ataque para
# de descer no mínimo, então o bot passava a batalha inteira baixando um
# atributo que já estava no fundo, perdia, e não subia de nível. Foi o que o
# operador viu em 2026-08-08.
#
# Fica de fora quem some sozinho do jogo: nada aqui precisa de exceção hoje,
# mas a regra é essa — só entra o que o cartucho torna redundante na segunda vez.
ONE_SHOT_STATUS_MOVES = frozenset(STATUS_MOVE_PRIORITY)

# A Gen I Pokémon holds at most four moves, so the move list has at most four
# rows and they are numbered from one. Anything outside that is the cursor byte
# holding something that is not this menu.
MOVE_LIST_ROWS = 4


class SimpleBattleAgent:
    def __init__(self):
        self.move_selection = 0  # Currently selected move (0-3)
        self.last_move_used = -1
        self.text_advance_with_a = False
        self.move_learning = None
        self.leech_seed_used = False
        # Golpes de status já gastos nesta batalha. Cada um vale uma vez.
        self.status_moves_used = set()
        # Preenchida no primeiro turno, direto do banco 0x0E. Vazia significa
        # que ninguém perguntou ao cartucho ainda, não que os golpes valem zero.
        self.move_table = MoveTable()
        self.move_table_warned = False
        self.last_decision = {
            "kind": "uninitialized",
            "reason": "battle controller has not observed a turn yet",
        }

    def reset_battle(self):
        """Forget menu state from the previous encounter."""
        self.move_selection = 0
        self.last_move_used = -1
        self.text_advance_with_a = False
        self.move_learning = None
        self.leech_seed_used = False
        self.status_moves_used = set()

    def _advance_text(self):
        """Alternate B/A like the cartridge-aware PokeBot text handler.

        Some Gen I prompts ignore B while others accept it. Alternating keeps
        ordinary battle text fast and can confirm move-learning questions
        without freezing forever on a defeated opponent.
        """
        self.text_advance_with_a = not self.text_advance_with_a
        return "A" if self.text_advance_with_a else "B"

    @staticmethod
    def _live_move_ids(emulator):
        return tuple(int(emulator.read_byte(0xD01C + index)) for index in range(4))

    def _load_move_table(self, emulator):
        """Ler o banco 0x0E uma vez por batalha-controlador e guardar.

        É ROM: não muda enquanto o jogo roda. Reler a cada turno seria mil
        acessos por encontro para receber sempre a mesma resposta.

        Tabela vazia é bug, não estado válido, e degrada em silêncio da pior
        maneira: sem potência nenhuma, todo golpe some do filtro de dano e a
        escolha cai no desempate de status, onde Growl vale 9 e Vine Whip cai
        no padrão 50. Foi assim que um Bulbasaur nível 14 encarou o Geodude do
        Brock 203 vezes com os 10 PP de Vine Whip intactos. O aviso sai uma vez
        por controlador, para não virar ruído dentro do laço de batalha.
        """
        if not len(self.move_table):
            self.move_table = MoveTable.from_memory(emulator)
            if not len(self.move_table) and not self.move_table_warned:
                self.move_table_warned = True
                print(
                    "[batalha] AVISO: tabela de golpes vazia — "
                    f"{type(emulator).__name__} não sabe ler ROM. "
                    "Todo golpe vai contar como status."
                )
        return self.move_table

    def _replacement_slot(self, player_moves):
        """Pick the least useful deletable move from the active build.

        Damaging moves are ordered by their canonical base power. Status moves
        come first, while unknown moves receive a conservative middle score so
        a partially populated move table does not delete them blindly.
        """
        choices = []
        for slot, move_id, _pp in player_moves:
            if move_id in HM_MOVE_IDS:
                continue
            power = self.move_table.power(move_id)
            utility = 45 if power is None else power
            choices.append((utility, slot, move_id))
        if not choices:
            return None
        _utility, slot, move_id = min(choices)
        return slot, move_id

    def _post_battle_action(self, emulator, player_moves, battle_text):
        """Resolve level-up move learning and evolution on the real cartridge.

        LearnMove uses the standard Gen I menu fields: the YES/NO prompt is
        exposed through battle text 20, and the four-move list sets the top
        menu coordinates to y=8/x=5 with a zero-based row at CC26. The text
        immediately before the list needs two confirmations; a directional
        input then opens the list without accidentally accepting its first row.
        """
        self._load_move_table(emulator)
        battle_menu = int(emulator.read_byte(0xCC50))
        menu_top_y = int(emulator.read_byte(0xCC24))
        menu_column = int(emulator.read_byte(0xCC25))
        menu_row = int(emulator.read_byte(0xCC26))
        live_moves = self._live_move_ids(emulator)

        # B cancels evolution in Red/Blue. It is never safe in this state.
        if int(emulator.read_byte(0xCC51)) == 144:
            self.last_decision = {
                "kind": "evolution",
                "reason": "confirm evolution; B would cancel it",
            }
            return "A"

        if self.move_learning is not None:
            learning = self.move_learning
            if live_moves != learning["original_moves"]:
                added = next(
                    (move_id for move_id in live_moves if move_id not in learning["original_moves"]),
                    None,
                )
                self.last_decision = {
                    "kind": "move_learned",
                    "reason": "new build confirmed in battle RAM",
                    "learned_move_id": added,
                    "replaced_move_id": learning["replaced_move_id"],
                    "replaced_move_slot": learning["target_slot"],
                    "moves_before": list(learning["original_moves"]),
                    "moves_after": list(live_moves),
                }
                self.move_learning = None
                return "A"

            stage = learning["stage"]
            if stage == "move_menu":
                desired_row = learning["target_slot"]
                if menu_row < desired_row:
                    return "DOWN"
                if menu_row > desired_row:
                    return "UP"
                learning["stage"] = "confirming"
                return "A"

            # The menu coordinates are written only when the real four-move
            # selector is visible. This avoids navigating unrelated text.
            if stage == "opening_menu" and menu_top_y == 8 and menu_column == 5:
                learning["stage"] = "move_menu"
                return self._post_battle_action(emulator, player_moves, battle_text)

            if stage == "accepted":
                if learning["text_confirms"] < 2:
                    learning["text_confirms"] += 1
                    return "A"
                learning["stage"] = "opening_menu"
                return "DOWN"

            # Once a row is confirmed, advance the forgetting/learning text.
            # Using A also remains safe if evolution starts in the same call.
            return "A"

        # TryingToLearn's YES/NO prompt appears only when all four slots are
        # occupied. Restricting the signature keeps capture nickname prompts
        # and other post-battle questions out of this controller.
        if battle_text == 20 and battle_menu == 95 and all(live_moves):
            replacement = self._replacement_slot(player_moves)
            if replacement is None:
                # Every slot is an HM. Select NO (row 1) and preserve the build.
                self.last_decision = {
                    "kind": "move_learning_declined",
                    "reason": "all four existing moves are protected HMs",
                }
                return "DOWN" if menu_row == 0 else "A"

            target_slot, replaced_move_id = replacement
            self.move_learning = {
                "stage": "accepted",
                "text_confirms": 0,
                "target_slot": target_slot,
                "replaced_move_id": replaced_move_id,
                "original_moves": live_moves,
            }
            self.last_decision = {
                "kind": "move_learning",
                "reason": "accept level-up move and replace lowest-utility deletable move",
                "replaced_move_id": replaced_move_id,
                "replaced_move_slot": target_slot,
                "moves_before": list(live_moves),
            }
            return "A"

        return self._advance_text()
    
    def get_type_effectiveness(self, attacker_type, defender_types):
        """Calculate type effectiveness (can be 4x if dual-type)"""
        multiplier = 1.0
        for def_type in defender_types:
            if attacker_type in EFFECTIVENESS and def_type in EFFECTIVENESS[attacker_type]:
                multiplier *= EFFECTIVENESS[attacker_type][def_type]
        return multiplier

    @staticmethod
    def _battle_types(emulator, first_address, fallback):
        types = []
        for address in (first_address, first_address + 1):
            type_name = GEN1_TYPE_NAMES.get(emulator.read_byte(address))
            if type_name and type_name not in types:
                types.append(type_name)
        return types or fallback

    def _select_move_from_live_menu(self, emulator, desired_zero_based, player_moves):
        """Reach FIGHT and select a move using the ROM's actual menu RAM.

        Gen I persists menu cursors between turns and battles. An internal
        counter therefore diverges after a whiteout, a cancelled menu or a
        forced switch. These predicates mirror the real Blue battle menu used
        by PokeBot: 94 is the battle selector, 106/the column-5 variant is the
        move list, and CC26 is the live one-based row.
        """
        battle_menu = int(emulator.read_byte(0xCC50))
        menu_column = int(emulator.read_byte(0xCC25))
        menu_row = int(emulator.read_byte(0xCC26))
        battle_text = int(emulator.read_byte(0xD125))
        opponent_hp = (
            (int(emulator.read_byte(0xCFE6)) << 8)
            + int(emulator.read_byte(0xCFE7))
        )
        desired_row = desired_zero_based + 1
        self.move_selection = desired_zero_based

        self.last_decision["menu"] = {
            "battle_menu": battle_menu,
            "column": menu_column,
            "row": menu_row,
            "desired_row": desired_row,
            "battle_text": battle_text,
        }

        if opponent_hp == 0:
            return self._post_battle_action(emulator, player_moves, battle_text)
        if battle_text == 1:
            return self._advance_text()

        move_list_open = battle_menu == 106 or (
            battle_menu == 94 and menu_column == 5
        )
        if move_list_open:
            # The move list rows are one-based, so a zero is not a row — it is
            # the cursor byte holding something that is not this menu, the same
            # way an invalid column means the 2x2 selector is not drawn. Read
            # literally it also happens to be *below* every desired row, so the
            # comparison below answers DOWN, the press changes nothing, and the
            # next step reads zero again: AARON pressed DOWN for two minutes
            # against a level 2 Rattata with a full-PP Tackle in slot 0.
            #
            # B is the honest answer to a menu that is not there: it advances
            # text and can never pick a move by accident.
            if not 1 <= menu_row <= MOVE_LIST_ROWS:
                return self._advance_text()
            if menu_row > desired_row:
                return "UP"
            if menu_row < desired_row:
                return "DOWN"
            return "A"

        if battle_menu == 94:
            # On the two-column battle selector, FIGHT is the upper-left item.
            if menu_column == 9:
                return "UP" if menu_row == 1 else "A"
            return "LEFT"

        # Advance animations/text and close unrelated submenus until Blue
        # exposes one of the two recognized battle menu states.
        return "B"

    def get_action(self, emulator):
        """
        Returns the best action based on type matchup and move power.
        Strategy:
        1. If super effective move available -> use it
        2. Else if neutral/disadvantage -> use highest power move
        3. Avoid using status moves in important battles
        """
        try:
            # Battle RAM stores Gen I internal indexes, not National Dex IDs.
            # Keep both forms in telemetry, but use National IDs for matchup
            # logic (e.g. internal 177 is Squirtle #007).
            opponent_internal_id = emulator.read_byte(0xCFE5)
            opponent_species = get_national_id(opponent_internal_id) or opponent_internal_id
            opponent_types = self._battle_types(
                emulator,
                0xCFEA,
                POKEMON_TYPES.get(opponent_species, ["NORMAL"]),
            )
            
            # Read player's current Pokemon species
            player_internal_id = emulator.read_byte(0xD014)
            if player_internal_id in (0, 0xFF):
                # Blue can expose battle status a few frames before D014 is
                # populated. Slot zero is the safe fallback for the current
                # single-Pokémon baseline and improves early telemetry.
                player_internal_id = emulator.read_byte(0xD16B)
            player_species = get_national_id(player_internal_id) or player_internal_id
            player_types = self._battle_types(
                emulator,
                0xD019,
                POKEMON_TYPES.get(player_species, ["NORMAL"]),
            )
            
            # Read the active battle Pokémon's moves. Party slot 1 starts at
            # 0xD173, but that becomes wrong as soon as the game forces or the
            # controller performs a switch.
            player_moves = []
            for i in range(4):
                move_id = emulator.read_byte(0xD01C + i)
                if move_id > 0:
                    # wBattleMonPP begins at D02D in Pokémon Blue. The low
                    # six bits are the remaining PP; the high bits contain
                    # PP-Up bonuses. Never select a move the cartridge has
                    # already exhausted, or Blue will keep reopening the
                    # "no PP left" textbox forever.
                    pp = int(emulator.read_byte(0xD02D + i)) & 0x3F
                    player_moves.append((i, move_id, pp))
            
            # Calculate effectiveness and power for each move. Keep the
            # calculation in a structured record so the real run can explain
            # why it attacked instead of exposing only a button press.
            best_move_idx = 0
            best_score = 0
            candidates = []
            # wPlayerDisabledMoveNumber is an actual move id at CCEE. It is
            # separate from the packed Disable turn/slot counter used by the
            # ROM internally. Selecting it simply redraws the move menu and
            # can otherwise create an infinite loop.
            disabled_move_id = int(emulator.read_byte(0xCCEE))
            
            moves = self._load_move_table(emulator)
            for slot, move_id, pp in player_moves:
                move_type = moves.type_of(move_id) or "NORMAL"
                move_power = moves.power(move_id) or 0

                # Skip status moves and exhausted attacks. "Potência zero"
                # agora vem do cartucho: antes vinha de o golpe faltar na
                # tabela, e era assim que Thundershock virava status e perdia
                # a vez para Growl.
                if move_power == 0 or pp == 0 or move_id == disabled_move_id:
                    continue
                
                effectiveness = self.get_type_effectiveness(move_type, opponent_types)
                stab = 1.5 if move_type in player_types else 1.0
                
                # Score the actual Gen I type product and STAB. This preserves
                # resistances and immunities instead of treating them as neutral.
                score = move_power * effectiveness * stab
                candidates.append({
                    "slot": slot,
                    "move_id": move_id,
                    "pp": pp,
                    "type": move_type,
                    "power": move_power,
                    "effectiveness": effectiveness,
                    "stab": stab,
                    "score": score,
                })
                
                if score > best_score:
                    best_score = score
                    best_move_idx = slot

            # Gen I only forces Struggle when *every* move is exhausted. With
            # damage moves at 0 PP but a status move still available, the game
            # keeps the menu open — and the old fallback of "slot 0" selected an
            # exhausted move, reopening the "no PP" textbox forever. Two bots sat
            # in Viridian Forest doing exactly that.
            if not candidates:
                # Not every status move is worth the same turn. Leech Seed
                # keeps draining after it lands, so it is worth exactly one
                # cast; a sleep or a paralysis is worth one too. Growl and Tail
                # Whip do nothing at all once the stage is already at the
                # bottom, and repeating them is how a trainer spent an
                # afternoon lowering an Attack that could not go lower.
                com_pp = [
                    (slot, move_id)
                    for slot, move_id, pp in player_moves
                    if pp > 0 and move_id != disabled_move_id
                ]
                preferidos = [
                    (slot, move_id) for slot, move_id in com_pp
                    if move_id not in self.status_moves_used
                    and not (
                        move_id == LEECH_SEED_MOVE_ID
                        and "GRASS" in opponent_types
                    )
                ]
                # A preferência é sobre *qual* golpe de status vale o turno. Ela
                # nunca pode esvaziar a lista: um golpe repetido de graça é ruim,
                # e escolher um slot com 0 PP é fatal. Com Tackle e Growl zerados
                # e só Leech Seed de pé, o filtro tirava a única opção, a escolha
                # caía no slot 0 exausto, e o cartucho reabria "no PP" para
                # sempre. AARON ficou 7.650 passos assim.
                #
                # A fuga cobria isto antes e foi removida em 2026-08-07: sem
                # golpe utilizável o bot não vence nem perde, e "ficar até
                # morrer" precisa que morrer seja possível.
                usable = preferidos or com_pp
                fallback = None
                if usable:
                    # Golpe de dano nunca perde para um de status aqui. A
                    # tabela de prioridade ordena *entre* golpes de status —
                    # Growl vale 9, e um golpe de ataque sem entrada cai no
                    # padrão 50, então Growl ganhava de Tackle e de Vine Whip.
                    #
                    # Isso só importa quando a lista de candidatos veio vazia
                    # por leitura ruim: o controlador é chamado com texto ainda
                    # na tela, `0xD01C` não é o menu de golpes ainda, e a
                    # escolha inteira desanda. Ordenar dano primeiro faz o
                    # desempate errar para o lado certo.
                    def rank(entry):
                        move_id = entry[1]
                        damaging = bool(moves.power(move_id))
                        return (
                            0 if damaging else 1,
                            -(moves.power(move_id) or 0) if damaging
                            else STATUS_MOVE_PRIORITY.get(move_id, 50),
                        )

                    fallback = min(usable, key=rank)[0]
                # None means every move is spent: the cartridge substitutes
                # Struggle on its own, so confirming the menu is correct.
                best_move_idx = fallback if fallback is not None else best_move_idx

            selected_move_id = next(
                (
                    move_id
                    for slot, move_id, pp in player_moves
                    if slot == best_move_idx and pp > 0
                ),
                0,
            )
            if selected_move_id in ONE_SHOT_STATUS_MOVES:
                # Vale uma vez por batalha. A semente drena sozinha depois de
                # plantada; quem dorme já está dormindo; e o estágio de atributo
                # para de descer no mínimo — Growl tem 40 PP e o bot gastava a
                # batalha inteira baixando um ataque que já estava no fundo.
                self.status_moves_used.add(selected_move_id)
                if selected_move_id == LEECH_SEED_MOVE_ID:
                    self.leech_seed_used = True
            selected_candidate = next(
                (candidate for candidate in candidates if candidate["slot"] == best_move_idx),
                None,
            )
            self.last_decision = {
                "kind": "attack",
                "reason": "highest power × type effectiveness",
                "opponent_internal_id": opponent_internal_id,
                "opponent_species": opponent_species,
                "player_internal_id": player_internal_id,
                "player_species": player_species,
                "selected_move_slot": best_move_idx,
                "selected_move_id": selected_move_id,
                "disabled_move_id": disabled_move_id,
                "selected": selected_candidate,
                "candidates": candidates,
            }
            
            action = self._select_move_from_live_menu(
                emulator,
                best_move_idx,
                player_moves,
            )
            if action == "A":
                self.last_move_used = selected_move_id
            return action

        except Exception as e:
            self.last_decision = {
                "kind": "fallback_attack",
                "reason": "battle memory read failed",
                "error": str(e),
            }

        # Default: Attack most of the time
        r = random.random()
        if r < 0.7:
            return "A"
        elif r < 0.85:
            return "DOWN"
        else:
            return "UP"
