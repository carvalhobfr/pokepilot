# Pokemon Red/Blue Memory Map - Verified Addresses
# Extracted from: https://github.com/PWhiddy/PokemonRedExperiments
# Source: https://datacrystal.romhacking.net/wiki/Pokémon_Red/Blue:RAM_map

# CORE GAME STATE
X_POS = 0xD362
Y_POS = 0xD361  
MAP_N = 0xD35E

# PARTY
PARTY_COUNT = 0xD163
PARTY_MON1_SPECIES = 0xD164
PARTY_MON2_SPECIES = 0xD165
PARTY_MON3_SPECIES = 0xD166
PARTY_MON4_SPECIES = 0xD167
PARTY_MON5_SPECIES = 0xD168
PARTY_MON6_SPECIES = 0xD169

# LEVELS (for each party member)
PARTY_MON1_LEVEL = 0xD18C
PARTY_MON2_LEVEL = 0xD1B8
PARTY_MON3_LEVEL = 0xD1E4
PARTY_MON4_LEVEL = 0xD210
PARTY_MON5_LEVEL = 0xD23C
PARTY_MON6_LEVEL = 0xD268

# HP (current)
PARTY_MON1_HP = 0xD16C  # 2 bytes
PARTY_MON2_HP = 0xD198
PARTY_MON3_HP = 0xD1C4
PARTY_MON4_HP = 0xD1F0
PARTY_MON5_HP = 0xD21C
PARTY_MON6_HP = 0xD248

# HP (max)
PARTY_MON1_MAX_HP = 0xD18D  # 2 bytes
PARTY_MON2_MAX_HP = 0xD1B9
PARTY_MON3_MAX_HP = 0xD1E5
PARTY_MON4_MAX_HP = 0xD211
PARTY_MON5_MAX_HP = 0xD23D
PARTY_MON6_MAX_HP = 0xD269

# OPPONENT (in battle)
OPPONENT_MON1_LEVEL = 0xD8C5
OPPONENT_MON2_LEVEL = 0xD8F1
OPPONENT_MON3_LEVEL = 0xD91D
OPPONENT_MON4_LEVEL = 0xD949
OPPONENT_MON5_LEVEL = 0xD975
OPPONENT_MON6_LEVEL = 0xD9A1

# BATTLE
BATTLE_STATUS = 0xD057  # Non-zero if in battle

# BADGES
BADGES = 0xD356  # Bit flags: 0=Boulder, 1=Cascade, 2=Thunder, etc.

# MONEY
MONEY_1 = 0xD347  # BCD format
MONEY_2 = 0xD348
MONEY_3 = 0xD349

# EVENT FLAGS (Story progression)
EVENT_FLAGS_START = 0xD747
EVENT_FLAGS_END = 0xD886

# KEY EVENT FLAGS (from events.json)
# These are addr-bit pairs from the events.json
FOLLOWED_OAK_INTO_LAB = (0xD747, 0)          # Intro done
OAK_ASKED_TO_CHOOSE_MON = (0xD74B, 1)        # Ready to choose starter
GOT_STARTER = (0xD74B, 2)                    # Starter chosen
BATTLED_RIVAL_IN_OAKS_LAB = (0xD74B, 3)      # First rival fight
GOT_POKEDEX = (0xD74B, 5)                    # Got pokedex
GOT_OAKS_PARCEL = (0xD74E, 1)                # Viridian Mart quest
BEAT_BROCK = (0xD755, 7)                     # Boulder Badge
BEAT_MISTY = (0xD75E, 7)                     # Cascade Badge
BEAT_LT_SURGE = (0xD773, 7)                  # Thunder Badge
BEAT_ERIKA = (0xD77C, 1)                     # Rainbow Badge
BEAT_KOGA = (0xD792, 1)                      # Soul Badge
BEAT_BLAINE = (0xD79A, 1)                    # Volcano Badge
BEAT_SABRINA = (0xD7B3, 7)                   # Marsh Badge (need to check)
BEAT_GIOVANNI = (0xD751, 1)                  # Earth Badge

# ITEMS
ITEM_COUNT = 0xD31D
ITEMS_START = 0xD31E

# TEXT/MENU
TEXT_SPEED = 0xD355
OPTIONS = 0xD355

# MUSEUM
MUSEUM_TICKET = 0xD754

# MapIDs and names for reference
MAP_NAMES = {
    0: "Pallet Town",
    1: "Viridian City",
    2: "Pewter City",
    3: "Cerulean City",
    12: "Route 1",
    37: "Player's House (1F)",
    38: "Player's House (2F - Bedroom)",
    39: "Rival's House",
    40: "Oak's Lab",
    # ... many more
}
