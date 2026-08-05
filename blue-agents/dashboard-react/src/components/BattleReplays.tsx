import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Film, Play, Pause, X, ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Watching four bots fight live is impossible; watching one fight afterwards is
 * not. The relay keeps the last battles of each trainer and only sends the
 * frames when someone actually presses play.
 */

interface ReplaySummary {
  id: string;
  agent: string;
  enemy_species_id?: number;
  started_at?: number;
  ended_at?: number;
  frame_count: number;
}

interface Replay extends ReplaySummary {
  frames: string[];
}

const FRAME_MS = 220;

const BattleReplays: React.FC<{
  ws: React.MutableRefObject<WebSocket | null>;
  connected: boolean;
  open: boolean;
  onClose: () => void;
}> = ({ ws, connected, open, onClose }) => {
  const [summaries, setSummaries] = useState<ReplaySummary[]>([]);
  const [replay, setReplay] = useState<Replay | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const timer = useRef<number | null>(null);

  const handleMessage = useCallback(async (event: MessageEvent) => {
    let data: any;
    const raw = event.data instanceof Blob ? await event.data.text() : event.data;
    if (typeof raw !== 'string') return;
    try {
      data = JSON.parse(raw);
    } catch {
      return;
    }
    if (data.type === 'battle_replay_added') setSummaries(data.replays || []);
    if (data.type === 'battle_replay_frames') {
      setReplay(data.replay);
      setFrameIndex(0);
      setPlaying(true);
    }
  }, []);

  useEffect(() => {
    if (!connected || !ws.current) return;
    ws.current.addEventListener('message', handleMessage);
    return () => ws.current?.removeEventListener('message', handleMessage);
  }, [ws, connected, handleMessage]);

  useEffect(() => {
    if (!open || !connected || ws.current?.readyState !== WebSocket.OPEN) return;
    ws.current.send(JSON.stringify({ type: 'command', action: 'list_replays' }));
  }, [open, connected, ws]);

  useEffect(() => {
    if (timer.current) window.clearInterval(timer.current);
    if (!playing || !replay || replay.frames.length === 0) return;
    timer.current = window.setInterval(() => {
      setFrameIndex(current => (current + 1) % replay.frames.length);
    }, FRAME_MS);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [playing, replay]);

  if (!open) return null;

  const request = (id: string) => {
    if (ws.current?.readyState !== WebSocket.OPEN) return;
    ws.current.send(JSON.stringify({ type: 'command', action: 'get_replay', id }));
  };

  const step = (delta: number) => {
    if (!replay) return;
    setPlaying(false);
    setFrameIndex(current => (current + delta + replay.frames.length) % replay.frames.length);
  };

  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/70 backdrop-blur-sm p-6">
      <div className="flex max-h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#0b0f1a] shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 bg-white/5 p-3">
          <div className="flex items-center gap-2">
            <Film size={16} className="text-fuchsia-300" />
            <span className="text-xs font-bold uppercase tracking-wider text-gray-200">
              Últimas batalhas
            </span>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-gray-400 hover:bg-white/10 hover:text-white">
            <X size={16} />
          </button>
        </div>

        <div className="flex min-h-0 flex-1">
          <div className="w-56 shrink-0 overflow-y-auto border-r border-white/10 p-2">
            {summaries.length === 0 ? (
              <div className="p-3 text-[10px] italic leading-relaxed text-gray-500">
                Nenhuma batalha gravada ainda. A gravação só acontece com o painel
                aberto e em 0.5×, 1× ou 2× — acima disso as batalhas saem mais
                rápido do que alguém conseguiria assistir.
              </div>
            ) : (
              summaries.map(item => (
                <button
                  key={item.id}
                  onClick={() => request(item.id)}
                  className={`mb-1 w-full rounded-lg border p-2 text-left transition ${
                    replay?.id === item.id
                      ? 'border-fuchsia-400/40 bg-fuchsia-500/10'
                      : 'border-white/5 bg-white/5 hover:border-white/20'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {item.enemy_species_id ? (
                      <img
                        src={`https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/${item.enemy_species_id}.png`}
                        alt=""
                        className="h-7 w-7 pixelated"
                      />
                    ) : null}
                    <div className="min-w-0">
                      <div className="truncate text-[11px] font-bold text-white">{item.agent}</div>
                      <div className="text-[9px] text-gray-500">
                        {item.frame_count} quadros
                        {item.ended_at
                          ? ` · ${new Date(item.ended_at * 1000).toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}`
                          : ''}
                      </div>
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>

          <div className="flex min-w-0 flex-1 flex-col items-center justify-center gap-3 p-4">
            {replay && replay.frames.length > 0 ? (
              <>
                <img
                  src={replay.frames[frameIndex]}
                  alt={`Quadro ${frameIndex + 1}`}
                  className="pixelated w-full max-w-md rounded-lg border border-white/10"
                />
                <div className="flex items-center gap-3">
                  <button onClick={() => step(-1)} className="rounded-lg bg-white/10 p-2 text-gray-200 hover:bg-white/20">
                    <ChevronLeft size={16} />
                  </button>
                  <button
                    onClick={() => setPlaying(value => !value)}
                    className="rounded-lg bg-fuchsia-500/20 p-2 text-fuchsia-200 hover:bg-fuchsia-500/30"
                  >
                    {playing ? <Pause size={16} /> : <Play size={16} />}
                  </button>
                  <button onClick={() => step(1)} className="rounded-lg bg-white/10 p-2 text-gray-200 hover:bg-white/20">
                    <ChevronRight size={16} />
                  </button>
                  <span className="font-mono text-[10px] text-gray-500">
                    {frameIndex + 1}/{replay.frames.length}
                  </span>
                </div>
              </>
            ) : (
              <div className="text-xs italic text-gray-500">Escolha uma batalha à esquerda.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default BattleReplays;
