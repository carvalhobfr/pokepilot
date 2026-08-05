from pathlib import Path
import tempfile
import unittest

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
            self.assertEqual(40, len(identity.sha1), "o digest continua registrado")

    def test_red_runs_too_because_it_shares_maps_and_ram(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = require_blue(self.write(directory, "POKEMON RED"))
            self.assertEqual("pokemon_red", identity.game)

    def test_another_game_is_still_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "ROM não suportada"):
                identify_rom(self.write(directory, "ZELDA"))

    def test_the_digest_never_decides_whether_the_game_runs(self):
        # The hash is recorded so an archived journey can say which dump made
        # it. It is not a gate: no allowlist, no environment flag, no refusal.
        with tempfile.TemporaryDirectory() as directory:
            first = identify_rom(self.write(directory, "POKEMON BLUE", "a.gb"))
            second = identify_rom(self.write(directory, "POKEMON BLUE", "b.gb"))
            self.assertEqual(first.game, second.game)
            self.assertEqual(first.sha1, second.sha1)


if __name__ == "__main__":
    unittest.main()
