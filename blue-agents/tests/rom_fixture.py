"""O cartucho de verdade, para os testes também não decorarem tabela.

Os controladores agora leem potência, tipo e PP do banco 0x0E. Um duble que
não sabe ler ROM devolveria "golpe desconhecido" para tudo e os testes
passariam a medir o duble em vez do jogo. A ROM está no repositório: usar ela.
"""

from pathlib import Path

from src.move_data import MoveTable

ROM_PATH = Path(__file__).resolve().parents[2] / "roms" / "PokemonBlue.gb"
_RAW = ROM_PATH.read_bytes()

MOVES = MoveTable.from_rom_file(ROM_PATH)


def read_rom(bank, address):
    """Assinatura de ``Memory.read_rom``, servida pelo arquivo da ROM."""
    return _RAW[bank * 0x4000 + (address & 0x3FFF)]
