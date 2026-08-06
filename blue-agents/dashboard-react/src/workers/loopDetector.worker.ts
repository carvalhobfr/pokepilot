type RouteSample = {
  agent: string;
  map: number;
  x: number;
  y: number;
  task: string;
  battle?: boolean;
};

type LoopMessage = RouteSample & {
  type: 'loop_detected';
  signature: string;
  period: number;
  reason: string;
};

const history = new Map<string, RouteSample[]>();
const lastReported = new Map<string, string>();
const HISTORY_LIMIT = 30;

function key(sample: RouteSample): string {
  return `${sample.map}:${sample.x},${sample.y}:${sample.task}`;
}

function detect(samples: RouteSample[]): { period: number; signature: string } | null {
  if (samples.length < 6) return null;

  // One repeated tile is often a legitimate dialogue, door or NPC wait. Only
  // report a spatial cycle with at least two distinct positions.
  for (let period = 2; period <= 8; period += 1) {
    const needed = period * 3;
    if (samples.length < needed) continue;
    const tail = samples.slice(-needed);
    const first = tail.slice(0, period).map(key).join('|');
    const second = tail.slice(period, period * 2).map(key).join('|');
    const third = tail.slice(period * 2).map(key).join('|');
    if (first === second && second === third) {
      return { period, signature: third };
    }
  }
  return null;
}

self.onmessage = (event: MessageEvent<RouteSample>) => {
  const sample = event.data;
  if (
    !sample ||
    !sample.agent ||
    !Number.isFinite(sample.map) ||
    !Number.isFinite(sample.x) ||
    !Number.isFinite(sample.y)
  ) {
    return;
  }

  // A stationary battle sprite is expected; only route states participate in
  // cycle detection.
  if (sample.battle) {
    history.delete(sample.agent);
    lastReported.delete(sample.agent);
    return;
  }

  const samples = [...(history.get(sample.agent) || []), sample].slice(-HISTORY_LIMIT);
  history.set(sample.agent, samples);
  const loop = detect(samples);
  if (!loop) return;

  const reportKey = `${loop.period}:${loop.signature}`;
  if (lastReported.get(sample.agent) === reportKey) return;
  lastReported.set(sample.agent, reportKey);

  const message: LoopMessage = {
    ...sample,
    type: 'loop_detected',
    signature: loop.signature,
    period: loop.period,
    reason: `ciclo de rota detectado (${loop.period} estado(s) repetido(s) 3 vezes)`,
  };
  self.postMessage(message);
};

export {};
