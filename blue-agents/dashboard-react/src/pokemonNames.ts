// Nomes de Pokémon e golpes da Gen I para a interface.
// O bot lê ids do cartucho; ninguém que assiste entende "#25" ou "move 33".
// Estes mapas traduzem para Pikachu, Tackle etc.

export const SPECIES_NAMES: Record<number, string> = {
  1: 'Bulbasaur', 2: 'Ivysaur', 3: 'Venusaur', 4: 'Charmander', 5: 'Charmeleon', 6: 'Charizard',
  7: 'Squirtle', 8: 'Wartortle', 9: 'Blastoise', 10: 'Caterpie', 11: 'Metapod', 12: 'Butterfree',
  13: 'Weedle', 14: 'Kakuna', 15: 'Beedrill', 16: 'Pidgey', 17: 'Pidgeotto', 18: 'Pidgeot',
  19: 'Rattata', 20: 'Raticate', 21: 'Spearow', 22: 'Fearow', 23: 'Ekans', 24: 'Arbok',
  25: 'Pikachu', 26: 'Raichu', 27: 'Sandshrew', 28: 'Sandslash', 29: 'Nidoran♀', 30: 'Nidorina',
  31: 'Nidoqueen', 32: 'Nidoran♂', 33: 'Nidorino', 34: 'Nidoking', 35: 'Clefairy', 36: 'Clefable',
  37: 'Vulpix', 38: 'Ninetales', 39: 'Jigglypuff', 40: 'Wigglytuff', 41: 'Zubat', 42: 'Golbat',
  43: 'Oddish', 44: 'Gloom', 45: 'Vileplume', 46: 'Paras', 47: 'Parasect', 48: 'Venonat', 49: 'Venomoth',
  50: 'Diglett', 51: 'Dugtrio', 52: 'Meowth', 53: 'Persian', 54: 'Psyduck', 55: 'Golduck',
  56: 'Mankey', 57: 'Primeape', 58: 'Growlithe', 59: 'Arcanine', 60: 'Poliwag', 61: 'Poliwhirl',
  62: 'Poliwrath', 63: 'Abra', 64: 'Kadabra', 65: 'Alakazam', 66: 'Machop', 67: 'Machoke',
  68: 'Machamp', 69: 'Bellsprout', 70: 'Weepinbell', 71: 'Victreebel', 72: 'Tentacool', 73: 'Tentacruel',
  74: 'Geodude', 75: 'Graveler', 76: 'Golem', 77: 'Ponyta', 78: 'Rapidash', 79: 'Slowpoke',
  80: 'Slowbro', 81: 'Magnemite', 82: 'Magneton', 83: "Farfetch'd", 84: 'Doduo', 85: 'Dodrio',
  86: 'Seel', 87: 'Dewgong', 88: 'Grimer', 89: 'Muk', 90: 'Shellder', 91: 'Cloyster', 92: 'Gastly',
  93: 'Haunter', 94: 'Gengar', 95: 'Onix', 96: 'Drowzee', 97: 'Hypno', 98: 'Krabby', 99: 'Kingler',
  100: 'Voltorb', 101: 'Electrode', 102: 'Exeggcute', 103: 'Exeggutor', 104: 'Cubone', 105: 'Marowak',
  106: 'Hitmonlee', 107: 'Hitmonchan', 108: 'Lickitung', 109: 'Koffing', 110: 'Weezing',
  111: 'Rhyhorn', 112: 'Rhydon', 113: 'Chansey', 114: 'Tangela', 115: 'Kangaskhan', 116: 'Horsea',
  117: 'Seadra', 118: 'Goldeen', 119: 'Seaking', 120: 'Staryu', 121: 'Starmie', 122: 'Mr. Mime',
  123: 'Scyther', 124: 'Jynx', 125: 'Electabuzz', 126: 'Magmar', 127: 'Pinsir', 128: 'Tauros',
  129: 'Magikarp', 130: 'Gyarados', 131: 'Lapras', 132: 'Ditto', 133: 'Eevee', 134: 'Vaporeon',
  135: 'Jolteon', 136: 'Flareon', 137: 'Porygon', 138: 'Omanyte', 139: 'Omastar', 140: 'Kabuto',
  141: 'Kabutops', 142: 'Aerodactyl', 143: 'Snorlax', 144: 'Articuno', 145: 'Zapdos', 146: 'Moltres',
  147: 'Dratini', 148: 'Dragonair', 149: 'Dragonite', 150: 'Mewtwo', 151: 'Mew',
};

// Golpes da Gen I (ids do cartucho) — os que aparecem nas jornadas e mais.
export const MOVE_NAMES: Record<number, string> = {
  1: 'Pound', 2: 'Karate Chop', 3: 'Doubleslap', 4: 'Comet Punch', 5: 'Mega Punch',
  6: 'Pay Day', 7: 'Fire Punch', 8: 'Ice Punch', 9: 'Thunderpunch', 10: 'Scratch',
  11: 'Vicegrip', 12: 'Guillotine', 13: 'Razor Wind', 14: 'Swords Dance', 15: 'Cut',
  16: 'Gust', 17: 'Wing Attack', 18: 'Whirlwind', 19: 'Fly', 20: 'Bind', 21: 'Slam',
  22: 'Vine Whip', 23: 'Stomp', 24: 'Double Kick', 25: 'Mega Kick', 26: 'Jump Kick',
  27: 'Rolling Kick', 28: 'Sand-attack', 29: 'Headbutt', 30: 'Horn Attack', 31: 'Fury Attack',
  32: 'Horn Drill', 33: 'Tackle', 34: 'Body Slam', 35: 'Wrap', 36: 'Take Down', 37: 'Thrash',
  38: 'Double-edge', 39: 'Tail Whip', 40: 'Poison Sting', 41: 'Twineedle', 42: 'Pin Missile',
  43: 'Leer', 44: 'Bite', 45: 'Growl', 46: 'Roar', 47: 'Sing', 48: 'Supersonic', 49: 'Sonicboom',
  50: 'Disable', 51: 'Acid', 52: 'Ember', 53: 'Flamethrower', 54: 'Mist', 55: 'Water Gun',
  56: 'Hydro Pump', 57: 'Surf', 58: 'Ice Beam', 59: 'Blizzard', 60: 'Psybeam', 61: 'Bubblebeam',
  62: 'Aurora Beam', 63: 'Hyper Beam', 64: 'Peck', 65: 'Drill Peck', 66: 'Submission',
  67: 'Low Kick', 68: 'Counter', 69: 'Seismic Toss', 70: 'Strength', 71: 'Absorb', 72: 'Mega Drain',
  73: 'Leech Seed', 74: 'Growth', 75: 'Razor Leaf', 76: 'Solarbeam', 77: 'Poisonpowder',
  78: 'Stun Spore', 79: 'Sleep Powder', 80: 'Petal Dance', 81: 'String Shot', 82: 'Dragon Rage',
  83: 'Fire Spin', 84: 'Thundershock', 85: 'Thunderbolt', 86: 'Thunder Wave', 87: 'Thunder',
  88: 'Rock Throw', 89: 'Earthquake', 90: 'Fissure', 91: 'Dig', 92: 'Toxic', 93: 'Confusion',
  94: 'Psychic', 95: 'Hypnosis', 96: 'Meditate', 97: 'Agility', 98: 'Quick Attack', 99: 'Rage',
  100: 'Teleport', 101: 'Night Shade', 102: 'Mimic', 103: 'Screech', 104: 'Double Team',
  105: 'Recover', 106: 'Harden', 107: 'Minimize', 108: 'Smokescreen', 109: 'Confuse Ray',
  110: 'Withdraw', 111: 'Defense Curl', 112: 'Barrier', 113: 'Light Screen', 114: 'Haze',
  115: 'Reflect', 116: 'Focus Energy', 117: 'Bide', 118: 'Metronome', 119: 'Mirror Move',
  120: 'Selfdestruct', 121: 'Egg Bomb', 122: 'Lick', 123: 'Smog', 124: 'Sludge', 125: 'Bone Club',
  126: 'Fire Blast', 127: 'Waterfall', 128: 'Clamp', 129: 'Swift', 130: 'Skull Bash', 131: 'Spike Cannon',
  132: 'Constrict', 133: 'Amnesia', 134: 'Kinesis', 135: 'Softboiled', 136: 'Hi Jump Kick',
  137: 'Glare', 138: 'Dream Eater', 139: 'Poison Gas', 140: 'Barrage', 141: 'Leech Life',
  142: 'Lovely Kiss', 143: 'Sky Attack', 144: 'Transform', 145: 'Bubble', 146: 'Dizzy Punch',
  147: 'Spore', 148: 'Flash', 149: 'Psywave', 150: 'Splash', 151: 'Acid Armor', 152: 'Crabhammer',
  153: 'Explosion', 154: 'Fury Swipes', 155: 'Bonemerang', 156: 'Rest', 157: 'Rock Slide',
  158: 'Hyper Fang', 159: 'Sharpen', 160: 'Conversion', 161: 'Tri Attack', 162: 'Super Fang',
  163: 'Slash', 164: 'Substitute', 165: 'Struggle',
};

export function speciesLabel(id: number | string | null | undefined): string {
  const n = Number(id || 0);
  if (n <= 0) return '???';
  return `${SPECIES_NAMES[n] || `#${n}`} (#${n})`;
}

export function moveLabel(id: number | string | null | undefined): string {
  const n = Number(id || 0);
  return MOVE_NAMES[n] || `Golpe #${n}`;
}
