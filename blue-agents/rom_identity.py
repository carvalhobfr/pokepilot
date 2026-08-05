"""ROM identification for supported Gen I games.

The check used to be an allowlist of two SHA-1 digests, which refused every
dump but one. That is a rule for a museum, not for a team: legal cartridges get
dumped by different people with different tools, and "send me your file" is not
an acceptable answer — the ROM is theirs and stays theirs.

Identity comes from the cartridge header, which is what actually decides whether
the RAM addresses and map ids in this project apply. The SHA-1 is still computed
and recorded in every archive so a finished journey can say which dump produced
it, but it never decides whether the game runs.
"""

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path


@dataclass(frozen=True)
class RomIdentity:
    game: str
    region: str
    revision: str
    sha1: str
    title: str

    def as_dict(self):
        return asdict(self)


# Header titles the controllers understand. Red and Blue share maps, RAM layout
# and the whole QuestGraph; Yellow does not, and is rejected on purpose.
SUPPORTED_TITLES = {
    "POKEMON BLUE": "pokemon_blue",
    "POKEMON RED": "pokemon_red",
}


def _header_title(payload):
    header = payload[0x134:0x144]
    return header.split(b"\0", 1)[0].decode("ascii", errors="replace").strip()


def identify_rom(path):
    """Identify a Gen I ROM by its header, recording the digest either way."""
    rom_path = Path(path)
    payload = rom_path.read_bytes()
    digest = hashlib.sha1(payload).hexdigest()
    title = _header_title(payload)

    game = SUPPORTED_TITLES.get(title.upper())
    if game is None:
        raise ValueError(
            f"ROM não suportada: {rom_path} (título={title!r}, sha1={digest}). "
            "Este projeto lê a RAM de Pokémon Red/Blue; traga sua própria cópia "
            "legal de um desses."
        )
    return RomIdentity(
        game=game,
        region="unknown",
        revision="unknown",
        sha1=digest,
        title=title,
    )


def require_blue(path):
    """Accept any Red/Blue cartridge; only the family has to match.

    Blue is the canonical runtime and the one every archived journey used, but
    Red shares the maps, the RAM layout and the QuestGraph, so refusing it only
    sent people hunting for one specific file.
    """
    identity = identify_rom(path)
    if identity.game not in SUPPORTED_TITLES.values():
        raise ValueError(
            f"PokeAI 2026 exige Pokémon Red ou Blue; recebido {identity.title}."
        )
    return identity
