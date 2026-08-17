const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');

const AGENT_ROOT = path.resolve(__dirname, '..');
const TASKS_DIR = path.join(AGENT_ROOT, 'tasks');
const CONTROL_FILE = path.join(TASKS_DIR, 'runtime_controls.json');
const TRAINING_PID_FILE = path.join(TASKS_DIR, 'training.pid');
const SAVE_SIGNAL_FILE = path.join(TASKS_DIR, 'save_state_signal');
const ALLOWED_SPEEDS = new Set([0, 0.5, 1, 2]);

fs.mkdirSync(TASKS_DIR, { recursive: true });

let controls = {
  // `viewers` is written by the relay, never by the dashboard: the throttle
  // that makes the arena watchable is pure waste when nobody is watching, and
  // the number of open dashboards is the only honest way to know.
  global: { paused: false, speed: 1, viewers: 0 },
  agents: {},
};

function writeControls() {
  // The hybrid persists the manual queue back to this same file, and both
  // sides used the same ".tmp" name — one rename could steal the other's
  // temporary and crash the relay with ENOENT. A unique temporary per
  // writer makes the race harmless: the loser's rename just replaces the
  // winner's file, and the file is always complete.
  //
  // The in-memory copy of each agent's manual queue goes stale the moment
  // the hybrid consumes a step and persists the remainder: any later
  // writeControls — a viewer connecting, a speed change — would rewrite the
  // full queue and the bot would walk the consumed steps again. Re-read the
  // file first and let its queue win, so a broadcast never resurrects a
  // step that was already taken.
  try {
    const stored = JSON.parse(fs.readFileSync(CONTROL_FILE, 'utf8'));
    for (const [name, agent] of Object.entries(stored.agents || {})) {
      if (!controls.agents[name]) continue;
      // O modo guia e o pause são do OPERADOR e vivem no arquivo; a memória
      // não pode reescrevê-los como false por engano. Se o arquivo tem o
      // campo (mesmo false), ele manda; se não tem, preserva a memória —
      // um boot com o arquivo a meio não pode derrubar o guia ativo
      // (medido 2026-08-13: o manual_mode sumia a cada restart).
      const agentHasGuide = Object.prototype.hasOwnProperty.call(agent, 'manual_mode');
      const agentHasPause = Object.prototype.hasOwnProperty.call(agent, 'paused');
      // A fila da MEMÓRIA vence: o handler manual acabou de adicionar o
      // passo do operador; a fila do arquivo pode estar desatualizada (o
      // hybrid persistiu o resto após consumir). Se a memória tem fila,
      // mantém; senão usa a do arquivo.
      const memQueue = controls.agents[name].manual?.queue;
      controls.agents[name] = {
        ...controls.agents[name],
        ...(agentHasGuide ? { manual_mode: Boolean(agent.manual_mode) } : {}),
        ...(agentHasPause ? { paused: Boolean(agent.paused) } : {}),
        manual: {
          ...(controls.agents[name].manual || {}),
          ...(agent.manual || {}),
          ...(memQueue ? { queue: memQueue } : {}),
        },
      };
    }
    console.log(
      '💾 writeControls: AARON manual_mode=',
      controls.agents?.AARON?.manual_mode,
      'paused=', controls.agents?.AARON?.paused,
    );
  } catch (_error) {
    // No file yet, or unreadable: keep the in-memory state as is.
  }
  const temporary = `${CONTROL_FILE}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, JSON.stringify(controls, null, 2));
  fs.renameSync(temporary, CONTROL_FILE);
}

// Replays live in the relay, not in the agents: a bot that finishes its block
// and restarts should not take the last fights with it.
const REPLAYS_PER_AGENT = 5;
const replays = new Map();

function storeReplay(replay) {
  if (!replay || !replay.agent) return;
  const list = replays.get(replay.agent) || [];
  list.unshift(replay);
  replays.set(replay.agent, list.slice(0, REPLAYS_PER_AGENT));
}

function replayIndex() {
  // The list without the frames: a dashboard asks for the heavy part only when
  // someone actually clicks play.
  const entries = [];
  for (const [agent, list] of replays) {
    for (const replay of list) {
      entries.push({
        id: replay.id,
        agent,
        enemy_species_id: replay.enemy_species_id,
        started_at: replay.started_at,
        ended_at: replay.ended_at,
        frame_count: (replay.frames || []).length,
      });
    }
  }
  return entries.sort((a, b) => (b.ended_at || 0) - (a.ended_at || 0));
}

function findReplay(id) {
  for (const list of replays.values()) {
    const found = list.find(replay => replay.id === id);
    if (found) return found;
  }
  return null;
}

function loadControls() {
  // The relay used to boot at 1x no matter what the file said, so a run left in
  // TREINO came back as 1x — or worse, a viewer connecting rewrote the file and
  // silently changed the speed of a running journey.
  try {
    const stored = JSON.parse(fs.readFileSync(CONTROL_FILE, 'utf8'));
    if (stored && stored.global) {
      controls.global = { ...controls.global, ...stored.global };
      controls.agents = stored.agents || {};
    }
  } catch (_error) {
    // No file yet, or unreadable: the defaults above are already correct.
  }
}

function publishViewerCount() {
  const viewers = dashboardClients.length;
  if (controls.global.viewers === viewers) return;
  controls.global.viewers = viewers;
  writeControls();
}

function readTrainingPid() {
  try {
    const pid = Number(fs.readFileSync(TRAINING_PID_FILE, 'utf8').trim());
    return Number.isInteger(pid) && pid > 1 ? pid : null;
  } catch (_error) {
    return null;
  }
}

function signalTraining(signal) {
  // The pid file holds the supervisor, and the supervisor does not run a
  // single emulator: `run_journeys.py` spawns `train_hybrid.py`, and that is
  // where the Game Boys live. Stopping only the parent left every bot playing
  // while the dashboard showed "paused". Signal the whole process group, and
  // fall back to the single pid when the group is not available.
  const pid = readTrainingPid();
  if (!pid) return { ok: false, error: 'training process not available' };
  try {
    process.kill(-pid, signal);
    return { ok: true, pid, scope: 'group' };
  } catch (groupError) {
    try {
      process.kill(pid, signal);
      return { ok: true, pid, scope: 'process' };
    } catch (error) {
      return { ok: false, error: error.message };
    }
  }
}

writeControls();

loadControls();

const wss = new WebSocket.Server({ port: 3344 });

console.log('🚀 Visualization Relay Server running on port 3344');

let dashboardClients = [];
let agents = [];

function sendJson(client, payload) {
  if (client.readyState === WebSocket.OPEN) {
    client.send(JSON.stringify(payload));
  }
}

function broadcastDashboards(payload) {
  dashboardClients.forEach(client => sendJson(client, payload));
}

function broadcastStats() {
  broadcastDashboards({
    stats: { envs: agents.length, viewers: dashboardClients.length },
  });
}

function broadcastControlState() {
  broadcastDashboards({ type: 'runtime_control_state', controls });
}

function handleDashboardCommand(ws, rawMessage) {
  let command;
  try {
    command = JSON.parse(rawMessage.toString());
  } catch (_error) {
    sendJson(ws, { type: 'command_result', ok: false, error: 'invalid JSON' });
    return;
  }
  if (command && (command.scope || command.type === 'command')) {
    console.log('📩 comando:', JSON.stringify(command).slice(0, 200));
  }

  if (command.type === 'command' && command.action === 'get_replay') {
    const replay = findReplay(command.id);
    if (!replay) {
      sendJson(ws, { type: 'command_result', ok: false, error: 'replay not found' });
      return;
    }
    sendJson(ws, { type: 'battle_replay_frames', replay });
    return;
  }

  if (command.type === 'command' && command.action === 'list_replays') {
    sendJson(ws, { type: 'battle_replay_added', replays: replayIndex() });
    return;
  }

  if (command.type === 'command' && command.action === 'save_all') {
    fs.writeFileSync(SAVE_SIGNAL_FILE, String(Date.now()));
    sendJson(ws, { type: 'command_result', ok: true, action: 'save_all' });
    return;
  }

  if (command.type !== 'control') return;

  if (command.scope === 'global' && command.action === 'speed') {
    const speed = Number(command.value);
    if (!ALLOWED_SPEEDS.has(speed)) {
      sendJson(ws, { type: 'command_result', ok: false, error: 'invalid speed' });
      return;
    }
    controls.global.speed = speed;
    writeControls();
    broadcastControlState();
    sendJson(ws, { type: 'command_result', ok: true, action: 'speed', value: speed });
    return;
  }

  if (command.scope === 'global' && ['pause', 'play'].includes(command.action)) {
    const paused = command.action === 'pause';
    // Pausing every agent through the control file is the portable half of
    // this: the trainers read it themselves, it works when the signal lands on
    // the wrong process, and it works on Windows, where SIGSTOP does not
    // exist. The signal stays as the instant half.
    for (const name of Object.keys(controls.agents || {})) {
      controls.agents[name] = { ...(controls.agents[name] || {}), paused };
    }
    for (const agent of agents) {
      const name = String(agent?.metadata?.user || '').toUpperCase();
      if (name) {
        controls.agents[name] = { ...(controls.agents[name] || {}), paused };
      }
    }
    const signalResult = signalTraining(paused ? 'SIGSTOP' : 'SIGCONT');
    if (!signalResult.ok) {
      console.warn('pause signal failed, control file still applies:', signalResult.error);
    }
    controls.global.paused = paused;
    writeControls();
    broadcastControlState();
    sendJson(ws, { type: 'command_result', ok: true, action: command.action });
    return;
  }

  if (command.scope === 'agent' && ['pause', 'play'].includes(command.action)) {
    const agentName = String(command.agent || '').toUpperCase();
    if (!/^[A-Z0-9_-]{1,24}$/.test(agentName)) {
      sendJson(ws, { type: 'command_result', ok: false, error: 'invalid agent' });
      return;
    }
    controls.agents[agentName] = {
      ...(controls.agents[agentName] || {}),
      paused: command.action === 'pause',
    };
    writeControls();
    broadcastControlState();
    sendJson(ws, { type: 'command_result', ok: true, action: command.action, agent: agentName });
    return;
  }

  if (command.scope === 'agent' && command.action === 'replan') {
    const agentName = String(command.agent || '').toUpperCase();
    if (!/^[A-Z0-9_-]{1,24}$/.test(agentName)) {
      sendJson(ws, { type: 'command_result', ok: false, error: 'invalid agent' });
      return;
    }
    controls.agents[agentName] = {
      ...(controls.agents[agentName] || {}),
      replan: {
        id: String(command.request_id || `${agentName}-${Date.now()}`),
        reason: String(command.reason || 'loop detectado pelo worker'),
        signature: String(command.signature || ''),
        requested_at: Date.now(),
      },
    };
    writeControls();
    broadcastControlState();
    sendJson(ws, { type: 'command_result', ok: true, action: command.action, agent: agentName });
    return;
  }

  // Guia manual: o operador envia uma fila de direções e o agente a consome
  // antes de qualquer decisão própria. Cada envio adiciona à fila existente;
  // `clear` zera. A fila fica em runtime_controls.json, então sobrevive a
  // restart e é a mesma fonte que os agentes já leem a cada 30 passos.
  if (command.scope === 'agent' && command.action === 'manual_mode') {
    const agentName = String(command.agent || '').toUpperCase();
    if (!/^[A-Z0-9_-]{1,24}$/.test(agentName)) {
      sendJson(ws, { type: 'command_result', ok: false, error: 'invalid agent' });
      return;
    }
    const enabled = Boolean(command.enabled);
    controls.agents[agentName] = {
      ...(controls.agents[agentName] || {}),
      manual_mode: enabled,
      // Ligar o modo guia pausa o agente na hora: o operador assume o
      // controle e o autopilot (batalha, quest, exploração, PPO) não pode
      // disputar o D-pad. Desligar volta ao estado anterior.
      paused: enabled ? true : (controls.agents[agentName]?.paused_before_guide ?? false),
      paused_before_guide: enabled
        ? Boolean(controls.agents[agentName]?.paused)
        : undefined,
      manual: { queue: enabled ? (controls.agents[agentName]?.manual?.queue || []) : [], requested_at: Date.now() },
    };
    writeControls();
    broadcastControlState();
    sendJson(ws, { type: 'command_result', ok: true, action: 'manual_mode', agent: agentName, enabled });
    return;
  }

  if (command.scope === 'agent' && command.action === 'manual') {
    const agentName = String(command.agent || '').toUpperCase();
    if (!/^[A-Z0-9_-]{1,24}$/.test(agentName)) {
      sendJson(ws, { type: 'command_result', ok: false, error: 'invalid agent' });
      return;
    }
    const steps = command.steps;
    if (command.clear) {
      controls.agents[agentName] = {
        ...(controls.agents[agentName] || {}),
        manual: { queue: [], requested_at: Date.now() },
      };
    } else if (Array.isArray(steps)) {
      const valid = steps.filter(step => ['U', 'D', 'L', 'R', 'A', 'B'].includes(String(step)));
      if (!valid.length) {
        sendJson(ws, { type: 'command_result', ok: false, error: 'no valid steps' });
        return;
      }
      // The hybrid consumes the queue one step at a time and persists the
      // remainder back to the file. The in-memory copy here goes stale the
      // moment the first step is taken, so re-reading the file before
      // appending is what keeps a consumed "L" from coming back as a ghost
      // step on the next click — the operator would watch the bot walk
      // sideways on its own.
      let existing = [];
      try {
        const stored = JSON.parse(fs.readFileSync(CONTROL_FILE, 'utf8'));
        existing = stored?.agents?.[agentName]?.manual?.queue || [];
        // Keep the in-memory copy honest too: the broadcast below reflects
        // the file, so a consumed step must not reappear in the dashboard.
        if (stored?.agents?.[agentName]) {
          controls.agents[agentName] = {
            ...(controls.agents[agentName] || {}),
            ...stored.agents[agentName],
          };
        }
      } catch (_error) {
        existing = controls.agents[agentName]?.manual?.queue || [];
      }
      controls.agents[agentName] = {
        ...(controls.agents[agentName] || {}),
        manual: { queue: existing.concat(valid), requested_at: Date.now() },
      };
    } else {
      sendJson(ws, { type: 'command_result', ok: false, error: 'steps must be an array' });
      return;
    }
    writeControls();
    broadcastControlState();
    sendJson(ws, { type: 'command_result', ok: true, action: 'manual', agent: agentName });
    return;
  }
}

wss.on('connection', function connection(ws, req) {
  const url = req.url;

  if (url === '/receive') {
    console.log(`📊 Dashboard client connected. Total: ${dashboardClients.length + 1}`);
    dashboardClients.push(ws);
    publishViewerCount();
    sendJson(ws, { type: 'runtime_control_state', controls });
    sendJson(ws, { type: 'battle_replay_added', replays: replayIndex() });
    broadcastStats();

    ws.on('message', message => handleDashboardCommand(ws, message));
    ws.on('close', () => {
      dashboardClients = dashboardClients.filter(client => client !== ws);
      console.log('📉 Dashboard client disconnected');
      publishViewerCount();
      broadcastStats();
    });
  } else if (url === '/broadcast') {
    console.log('🤖 Agent broadcaster connected');
    agents.push(ws);
    broadcastStats();

    ws.on('message', function incoming(message) {
      let payload = null;
      try {
        payload = JSON.parse(message.toString());
      } catch (_error) {
        payload = null;
      }
      if (payload && payload.battle_replay) {
        storeReplay(payload.battle_replay);
        const announcement = JSON.stringify({ type: 'battle_replay_added', replays: replayIndex() });
        dashboardClients.forEach(client => {
          if (client.readyState === WebSocket.OPEN) client.send(announcement);
        });
        return;
      }
      dashboardClients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) client.send(message);
      });
    });

    ws.on('close', () => {
      console.log('🤖 Agent disconnected');
      agents = agents.filter(agent => agent !== ws);
      broadcastStats();
    });
  } else {
    console.log(`❓ Unknown connection to ${url}`);
  }
});
