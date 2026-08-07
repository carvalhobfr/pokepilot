from src import memory_map

class Memory:
    def __init__(self, pyboy):
        self.pyboy = pyboy

    def read_byte(self, address):
        return self.pyboy.memory[address]

    def read_rom(self, bank, address):
        """A byte from a ROM bank, for tables the cartridge already holds."""
        return self.pyboy.memory[bank, address]

    def read_word(self, address):
        # Little endian
        return self.pyboy.memory[address] + (self.pyboy.memory[address + 1] << 8)
    
    def read_bit(self, address, bit):
        """Read a specific bit from a byte (0-7)"""
        byte = self.read_byte(address)
        return (byte >> bit) & 1
    
    def read_event_flag(self, addr, bit):
        """
        Read event flag at (address, bit).
        Returns 1 if flag is set, 0 otherwise.
        """
        return self.read_bit(addr, bit)

    def get_player_pos(self):
        return self.read_byte(memory_map.X_POS), self.read_byte(memory_map.Y_POS)

    def get_map_id(self):
        return self.read_byte(memory_map.MAP_N)

    def get_party_count(self):
        return self.read_byte(memory_map.PARTY_COUNT)

    def get_badges(self):
        return self.read_byte(memory_map.BADGES)
    
    def is_in_battle(self):
        # 0xD057 is non-zero during battle (usually)
        # Also check if enemy HP is valid or other flags
        status = self.read_byte(memory_map.BATTLE_STATUS)
        return status != 0

    def get_battle_state(self):
        """
        Returns a dictionary with current battle state for the LLM.
        """
        return {
            "my_pokemon": "Unknown", # TODO: Read species name from ID
            "my_hp": self.read_word(memory_map.PARTY_MON1_HP),
            "enemy_pokemon": "Unknown", # TODO: Read species name from ID
            "enemy_hp": self.read_word(memory_map.ENEMY_MON_HP),
            # "moves": ... # TODO: Read moves
        }

    def get_party_info(self):
        count = self.get_party_count()
        party = []
        # TODO: Loop through party structure
        return party
