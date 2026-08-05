from pathlib import Path
import tempfile
import unittest
from unittest import mock

from rom_identity import identify_rom, require_blue


def fake_rom(title):
    """A minimal cartridge image carrying a header title."""
    payload = bytearray(0x150)
    encoded = title.encode("ascii")
    payload[0x134:0x134 + len(encoded)] = encoded
    return bytes(payload)


class RomIdentityTests(unittest.TestCase):
    def write(self, directory, title, name="rom.gb"):
        path = Path(directory) / name
        path.write_bytes(fake_rom(title))
        return path

    def test_a_developer_dump_is_accepted_by_its_header(self):
        # Three developers with three legal cartridges may hold different
        # dumps, and "send me your file" is not an acceptable answer.
        with tempfile.TemporaryDirectory() as directory:
            identity = identify_rom(self.write(directory, "POKEMON BLUE"))
            self.assertEqual("pokemon_blue", identity.game)
            self.assertFalse(identity.verified, "dump desconhecido não é reprodutível")
            self.assertEqual(40, len(identity.sha1))

    def test_red_runs_too_because_it_shares_maps_and_ram(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = require_blue(self.write(directory, "POKEMON RED"))
            self.assertEqual("pokemon_red", identity.game)

    def test_another_game_is_still_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "ROM não suportada"):
                identify_rom(self.write(directory, "ZELDA"))

    def test_strict_mode_restores_the_exact_match_for_reproductions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, "POKEMON BLUE")
            with mock.patch.dict("os.environ", {"POKEAI_STRICT_ROM": "1"}):
                with self.assertRaisesRegex(ValueError, "STRICT"):
                    identify_rom(path)


if __name__ == "__main__":
    unittest.main()
