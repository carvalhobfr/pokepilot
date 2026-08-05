"""ROM identification and compatibility checks for supported Gen I games."""

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


SUPPORTED_ROMS = {
    # Pokémon Blue (USA/Europe), the canonical runtime for PokeAI 2026.
    "d7037c83e1ae5b39bde3c30787637ba1d4c48ce2": RomIdentity(
        game="pokemon_blue",
        region="usa_europe",
        revision="1.0",
        sha1="d7037c83e1ae5b39bde3c30787637ba1d4c48ce2",
        title="POKEMON BLUE",
    ),
    # Kept as an explicit compatibility fixture, never as the default.
    "ea9bcae617fdf159b045185467ae58b2e4a48b9a": RomIdentity(
        game="pokemon_red",
        region="usa_europe",
        revision="1.0",
        sha1="ea9bcae617fdf159b045185467ae58b2e4a48b9a",
        title="POKEMON RED",
    ),
}


def identify_rom(path):
    rom_path = Path(path)
    digest = hashlib.sha1(rom_path.read_bytes()).hexdigest()
    identity = SUPPORTED_ROMS.get(digest)
    if identity is None:
        header = rom_path.read_bytes()[0x134:0x144]
        title = header.split(b"\0", 1)[0].decode("ascii", errors="replace").strip()
        raise ValueError(
            f"ROM não suportada: {rom_path} (título={title!r}, sha1={digest}). "
            "Use Pokémon Blue USA/Europe v1.0 para manter RAM, mapas e QuestGraph compatíveis."
        )
    return identity


def require_blue(path):
    identity = identify_rom(path)
    if identity.game != "pokemon_blue":
        raise ValueError(
            f"PokeAI 2026 exige Pokémon Blue; recebido {identity.title} ({identity.sha1})."
        )
    return identity
