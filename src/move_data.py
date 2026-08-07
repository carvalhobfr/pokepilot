"""Dados de golpe lidos do cartucho, não decorados.

A tabela escrita à mão tinha trinta golpes de cento e sessenta e cinco. Quem
não estava nela valia potência zero, e potência zero é o mesmo que "não serve
para atacar": um Pikachu com Thundershock (id 84 — a tabela só tinha o 85,
Thunderbolt) descartava o único golpe de dano que tinha e escolhia Growl.

O cartucho carrega tudo isso no banco 0x0E, seis bytes por golpe, na ordem
{animação, efeito, potência, tipo, precisão, PP}.
"""

MOVE_BANK = 0x0E
MOVE_ENTRY_BYTES = 6
# Gen I vai de Pound (1) a Struggle (165). O índice 0 não é golpe: é o slot
# vazio, e ler seis bytes antes do início da tabela devolveria lixo.
MOVE_COUNT = 165

# Os ids de tipo como o cartucho os guarda. Os buracos (6, 9-19) não são tipos
# em Gen I.
GEN1_TYPE_NAMES = {
    0: "NORMAL", 1: "FIGHTING", 2: "FLYING", 3: "POISON",
    4: "GROUND", 5: "ROCK", 7: "BUG", 8: "GHOST",
    20: "FIRE", 21: "WATER", 22: "GRASS", 23: "ELECTRIC",
    24: "PSYCHIC", 25: "ICE", 26: "DRAGON",
}

# A precisão é guardada em 255 avos: 255 é 100%, 242 é 95%, 204 é 80%.
ACCURACY_FULL = 255


class Move:
    """Uma linha da tabela do cartucho."""

    __slots__ = ("move_id", "effect", "power", "type", "accuracy", "pp")

    def __init__(self, move_id, effect, power, type_name, accuracy, pp):
        self.move_id = move_id
        self.effect = effect
        self.power = power
        self.type = type_name
        self.accuracy = accuracy
        self.pp = pp

    @property
    def accuracy_fraction(self):
        return self.accuracy / ACCURACY_FULL

    def __repr__(self):
        return (
            f"Move(id={self.move_id}, power={self.power}, "
            f"type={self.type!r}, pp={self.pp})"
        )


class MoveTable:
    """Os 165 golpes, lidos uma vez e consultados sempre.

    Ler a ROM é barato mas não é de graça, e a tabela não muda durante a
    partida: é ROM, não RAM. Cachear o derivado é permitido; o que não vale é
    inventar o número quando a leitura falha — daí o ``None``, que diz
    "desconhecido" em vez de mentir "potência zero".
    """

    def __init__(self, moves=()):
        self.moves = {move.move_id: move for move in moves}

    def __len__(self):
        return len(self.moves)

    def __contains__(self, move_id):
        return int(move_id) in self.moves

    def get(self, move_id):
        return self.moves.get(int(move_id))

    def power(self, move_id):
        """Potência base, ou ``None`` se o golpe não foi lido do cartucho."""
        move = self.get(move_id)
        return None if move is None else move.power

    def type_of(self, move_id):
        move = self.get(move_id)
        return None if move is None else move.type

    def is_damaging(self, move_id):
        """Só é golpe de ataque o que o cartucho diz ter potência.

        Desconhecido não é o mesmo que status: sem dado, a resposta é ``False``
        aqui e quem pergunta decide. O que não pode acontecer de novo é um
        golpe real virar status por ausência de linha na tabela.
        """
        power = self.power(move_id)
        return bool(power)

    @classmethod
    def from_bytes(cls, raw, base=0):
        """A tabela a partir dos bytes crus do banco 0x0E."""
        moves = []
        for move_id in range(1, MOVE_COUNT + 1):
            offset = base + (move_id - 1) * MOVE_ENTRY_BYTES
            entry = raw[offset:offset + MOVE_ENTRY_BYTES]
            if len(entry) < MOVE_ENTRY_BYTES:
                break
            _animation, effect, power, type_id, accuracy, pp = entry
            moves.append(Move(
                move_id=move_id,
                effect=int(effect),
                power=int(power),
                type_name=GEN1_TYPE_NAMES.get(int(type_id), "NORMAL"),
                accuracy=int(accuracy),
                pp=int(pp),
            ))
        return cls(moves)

    @classmethod
    def from_rom_file(cls, path):
        """Direto do arquivo da ROM, para ferramentas e testes fora do emulador."""
        with open(path, "rb") as rom_file:
            raw = rom_file.read()
        return cls.from_bytes(raw, base=MOVE_BANK * 0x4000)

    @classmethod
    def from_memory(cls, memory):
        """Do cartucho montado no emulador.

        Devolve uma tabela vazia se o objeto não souber ler ROM — um controlador
        de teste, por exemplo. Vazia responde ``None`` a tudo, que é a verdade:
        ninguém perguntou ao cartucho.
        """
        read_rom = getattr(memory, "read_rom", None)
        if read_rom is None:
            return cls()
        try:
            raw = bytes(
                read_rom(MOVE_BANK, 0x4000 + offset)
                for offset in range(MOVE_COUNT * MOVE_ENTRY_BYTES)
            )
        except Exception:
            return cls()
        return cls.from_bytes(raw)
