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
  global: { paused: false, speed: 1 },
  agents: {},
};

function writeControls() {
  const temporary = `${CONTROL_FILE}.tmp`;
  fs.writeFileSync(temporary, JSON.stringify(controls, null, 2));
  fs.renameSync(temporary, CONTROL_FILE);
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
  const pid = readTrainingPid();
  if (!pid) return { ok: false, error: 'training process not available' };
  try {
    process.kill(pid, signal);
    return { ok: true, pid };
  } catch (error) {
    return { ok: false, error: error.message };
  }
}

writeControls();

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
    const signalResult = signalTraining(paused ? 'SIGSTOP' : 'SIGCONT');
    if (!signalResult.ok) {
      sendJson(ws, { type: 'command_result', ok: false, error: signalResult.error });
      return;
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
  }
}

wss.on('connection', function connection(ws, req) {
  const url = req.url;

  if (url === '/receive') {
    console.log(`📊 Dashboard client connected. Total: ${dashboardClients.length + 1}`);
    dashboardClients.push(ws);
    sendJson(ws, { type: 'runtime_control_state', controls });
    broadcastStats();

    ws.on('message', message => handleDashboardCommand(ws, message));
    ws.on('close', () => {
      dashboardClients = dashboardClients.filter(client => client !== ws);
      console.log('📉 Dashboard client disconnected');
      broadcastStats();
    });
  } else if (url === '/broadcast') {
    console.log('🤖 Agent broadcaster connected');
    agents.push(ws);
    broadcastStats();

    ws.on('message', function incoming(message) {
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
