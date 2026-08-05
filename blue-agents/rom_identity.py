"""ROM identification for supported Gen I games.

The check used to be an allowlist of two SHA-1 digests. That is the right rule
for a reproducible archive and the wrong one for a team: three developers with
three legal cartridges may hold different dumps, and "send me your file" is not
an acceptable answer — the ROM is theirs and stays theirs.

Identity now comes from the cartridge header, which is what actually decides
whether the RAM addresses and map ids in this project apply. The SHA-1 is still
computed and recorded in every archive, and `POKEAI_STRICT_ROM=1` restores the
old exact-match behaviour for a reproduction run.
"""

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path


@dataclass(frozen=True)
class RomIdentity:
    game: str
    region: str
    revision: str
    sha1: str
    title: str
    verified: bool = False

    def as_dict(self):
        return asdict(self)


# Dumps this project has actually run. A match means a journey is comparable to
# the archived ones tile for tile; anything else is merely compatible.
KNOWN_ROMS = {
    "d7037c83e1ae5b39bde3c30787637ba1d4c48ce2": ("pokemon_blue", "usa_europe", "1.0"),
    "ea9bcae617fdf159b045185467ae58b2e4a48b9a": ("pokemon_red", "usa_europe", "1.0"),
}

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
    known = KNOWN_ROMS.get(digest)

    if known is not None:
        game, region, revision = known
        return RomIdentity(
            game=game,
            region=region,
            revision=revision,
            sha1=digest,
            title=title or game.replace("_", " ").upper(),
            verified=True,
        )

    if os.getenv("POKEAI_STRICT_ROM", "0") == "1":
        raise ValueError(
            f"POKEAI_STRICT_ROM=1 e a ROM {rom_path} não é um dump registrado "
            f"(título={title!r}, sha1={digest}). Use um dump conhecido ou "
            "desligue o modo estrito."
        )

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
        verified=False,
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
            f"PokeAI 2026 exige Pokémon Red ou Blue; recebido {identity.title} "
            f"({identity.sha1})."
        )
    if not identity.verified:
        print(
            f"⚠️  ROM não registrada ({identity.title}, sha1={identity.sha1[:12]}…). "
            "Rodando assim mesmo; comparações com jornadas arquivadas podem diferir."
        )
    return identity
