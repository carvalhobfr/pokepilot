const WebSocket = require('ws');

const MAP_NAMES = {
  0: 'Pallet Town',
  1: 'Viridian City',
  12: 'Route 1',
  51: 'Viridian Forest',
};

const agents = [
  {
    user: 'AARON',
    color: '#ff6b00',
    personality: 'Chaos Explorer',
    starter: 'Charmander',
    meta_score: 20,
    exploration: 85,
    collector: 45,
    mission_focus: 55,
    x: 5,
    y: 8,
    map_id: 0,
    party: [{ species_id: 4, level: 5, hp: 20, max_hp: 20, moves: [{ id: 10, pp: 35 }, { id: 45, pp: 40 }] }],
    path: [],
    tick: 0,
  },
  {
    user: 'BARON',
    color: '#ff0000',
    personality: 'Strategic Warrior',
    starter: 'Squirtle',
    meta_score: 75,
    exploration: 60,
    collector: 50,
    mission_focus: 80,
    x: 7,
    y: 4,
    map_id: 0,
    party: [{ species_id: 7, level: 5, hp: 21, max_hp: 21, moves: [{ id: 55, pp: 25 }, { id: 45, pp: 40 }] }],
    path: [],
    tick: 0,
  },
  {
    user: 'CARON',
    color: '#0000ff',
    personality: 'Balanced Explorer',
    starter: 'Squirtle',
    meta_score: 50,
    exploration: 85,
    collector: 60,
    mission_focus: 50,
    x: 11,
    y: 7,
    map_id: 0,
    party: [{ species_id: 7, level: 5, hp: 21, max_hp: 21, moves: [{ id: 55, pp: 25 }, { id: 45, pp: 40 }] }],
    path: [],
    tick: 0,
  },
  {
    user: 'DARON',
    color: '#ffe000',
    personality: 'Meta Collector',
    starter: 'Bulbasaur',
    meta_score: 85,
    exploration: 40,
    collector: 85,
    mission_focus: 80,
    x: 9,
    y: 5,
    map_id: 0,
    party: [{ species_id: 1, level: 5, hp: 21, max_hp: 21, moves: [{ id: 33, pp: 35 }, { id: 45, pp: 40 }] }],
    path: [],
    tick: 0,
  },
];

function battleInfo(agent) {
  const active = agent.tick % 18 >= 8 && agent.tick % 18 <= 13;
  if (!active) return { is_battle: false };
  const hit = agent.tick % 6;
  const enemyId = agent.user === 'AARON' || agent.user === 'CARON' ? 74 : 19;
  return {
    is_battle: true,
    enemy_id: enemyId,
    enemy_level: agent.user === 'AARON' || agent.user === 'CARON' ? 8 : 6,
    enemy_hp: Math.max(1, 30 - hit * 6),
    enemy_max_hp: 30,
  };
}

function battleFrame(agent) {
  const enemy = agent.user === 'AARON' || agent.user === 'CARON' ? '#d9534f' : '#5bc0de';
  const player = agent.color;
  const enemyId = agent.user === 'AARON' || agent.user === 'CARON' ? 74 : 19;
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="160" height="144" viewBox="0 0 160 144">
      <rect width="160" height="144" fill="#10141f"/>
      <rect y="92" width="160" height="52" fill="#1c2635"/>
      <ellipse cx="120" cy="48" rx="22" ry="10" fill="#29364a"/>
      <circle cx="120" cy="36" r="13" fill="${enemy}"/>
      <ellipse cx="42" cy="108" rx="25" ry="9" fill="#29364a"/>
      <circle cx="42" cy="94" r="15" fill="${player}"/>
      <text x="8" y="14" fill="#f8fafc" font-family="monospace" font-size="8">${agent.user} • BATTLE</text>
      <text x="8" y="28" fill="#cbd5e1" font-family="monospace" font-size="7">enemy #${enemyId}</text>
      <text x="106" y="78" fill="#f8fafc" font-family="monospace" font-size="7">HP</text>
      <rect x="116" y="72" width="32" height="4" rx="2" fill="#334155"/>
      <rect x="116" y="72" width="${Math.max(4, 32 - (agent.tick % 6) * 5)}" height="4" rx="2" fill="#4ade80"/>
      <text x="8" y="136" fill="#facc15" font-family="monospace" font-size="7">ACTIVE • LIVE FRAME</text>
    </svg>`;
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`;
}

function updateAgent(agent) {
  agent.tick += 1;
  agent.x += agent.tick % 2 === 0 ? 1 : 0;
  if (agent.x > 14) {
    agent.x = 4;
    agent.y = (agent.y + 1) % 10;
  }

  // Keep the demo visually plausible: after leaving Pallet Town, agents pass
  // Route 1/Viridian City. CARON only reaches Viridian Forest before the
  // Pikachu capture, instead of receiving one while still at map 0.
  if (agent.tick === 6) agent.map_id = 12;
  if (agent.tick === 12) agent.map_id = 1;
  if (agent.user === 'CARON' && agent.tick === 15) agent.map_id = 51;

  const captureTick = agent.user === 'CARON' ? 18 : 6;
  if (agent.tick === captureTick) {
    const capturedSpecies = {
      AARON: 19,
      BARON: 16,
      CARON: 25,
      DARON: 19,
    }[agent.user] || 19;
    agent.party.push({
      species_id: capturedSpecies,
      level: 3,
      hp: 15,
      max_hp: 15,
      moves: [{ id: 33, pp: 35 }],
    });
  }
  if (agent.tick === 15) {
    agent.party[0].level = 6;
    agent.party[0].max_hp += 2;
    agent.party[0].hp = agent.party[0].max_hp;
  }

  agent.path.push([agent.x, agent.y, agent.map_id]);
  agent.path = agent.path.slice(-12);
  const events = [];
  if (agent.tick === captureTick) events.push({ type: 'capture', timestamp: Date.now() / 1000, pokemon: agent.party[1], data: { count: 2 } });
  if (agent.tick === 15) events.push({ type: 'level_up', timestamp: Date.now() / 1000, data: { new_level: agent.party[0].level, pokemon: agent.party[0] } });
  const battle = battleInfo(agent);
  return {
    metadata: {
      user: agent.user,
      color: agent.color,
      personality: agent.personality,
      starter: agent.starter,
      meta_score: agent.meta_score,
      exploration: agent.exploration,
      collector: agent.collector,
      mission_focus: agent.mission_focus,
      map_id: agent.map_id,
      map_name: MAP_NAMES[agent.map_id] || `Map ${agent.map_id}`,
      demo: true,
      coords_current: [agent.x, agent.y],
      badges: agent.tick > 24 ? 1 : 0,
      pokedex_owned: agent.party.length,
      pokedex_seen: agent.party.length + 1,
      step_count: agent.tick * 24,
      current_task: battle.is_battle ? 'BATTLE' : 'EXPLORE',
      status: battle.is_battle ? 'battle' : 'running',
      party: agent.party,
      battle_info: { ...battle, party: agent.party },
      battle_frame: battle.is_battle ? battleFrame(agent) : null,
      build: {
        personality: agent.personality,
        starter: agent.starter,
        traits: {
          meta_score: agent.meta_score,
          exploration: agent.exploration,
          collector: agent.collector,
          mission_focus: agent.mission_focus,
        },
        policy: 'PPO navigation + SimpleBattleAgent',
        battle_strategy: 'type effectiveness + move power',
        team: agent.party,
        active_pokemon: battle.is_battle ? agent.party[0] : null,
      },
      recent_events: events,
      last_update: Date.now() / 1000,
    },
    coords: agent.path,
  };
}

function connect() {
  const socket = new WebSocket('ws://127.0.0.1:3344/broadcast');
  socket.on('open', () => {
    console.log('Demo agents connected to the local relay');
    setInterval(() => {
      for (const agent of agents) {
        if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(updateAgent(agent)));
      }
    }, 500);
  });
  socket.on('close', () => setTimeout(connect, 1000));
  socket.on('error', () => {});
}

connect();
