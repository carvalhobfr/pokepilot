from pathlib import Path
import tempfile
import unittest

from rom_identity import identify_rom


class RomIdentityTests(unittest.TestCase):
    def test_unknown_rom_reports_header_and_hash(self):
        payload = bytearray(0x150)
        payload[0x134:0x13E] = b"FAKE BLUE\0"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake.gb"
            path.write_bytes(payload)
            with self.assertRaisesRegex(ValueError, "ROM não suportada"):
                identify_rom(path)


if __name__ == "__main__":
    unittest.main()
