import { Gauge, Pause, Play } from 'lucide-react';

export interface RuntimeControls {
  global: {
    paused: boolean;
    speed: number;
  };
  agents: Record<string, { paused?: boolean }>;
}

interface JourneyControlsProps {
  connected: boolean;
  agentCount: number;
  controls: RuntimeControls;
  onToggleGlobal: () => void;
  onSpeedChange: (speed: number) => void;
}

const SPEEDS = [
  { value: 0.5, label: '0.5×', title: 'Meia velocidade' },
  { value: 1, label: '1×', title: 'Velocidade normal do Game Boy' },
  { value: 2, label: '2×', title: 'Duas vezes mais rápido' },
  { value: 0, label: 'TREINO', title: 'Sem limite de velocidade' },
];

export default function JourneyControls({
  connected,
  agentCount,
  controls,
  onToggleGlobal,
  onSpeedChange,
}: JourneyControlsProps) {
  const paused = controls.global.paused;

  return (
    <div className="absolute left-1/2 top-4 z-20 flex -translate-x-1/2 items-center gap-2 rounded-2xl border border-white/10 bg-black/80 p-2 text-white shadow-2xl backdrop-blur-md">
      <button
        aria-label={paused ? 'Continuar todos os bots' : 'Pausar todos os bots'}
        disabled={!connected || agentCount === 0}
        onClick={onToggleGlobal}
        className={`flex h-9 items-center gap-2 rounded-xl px-3 text-[10px] font-black uppercase tracking-wider transition disabled:cursor-not-allowed disabled:opacity-40 ${paused ? 'bg-emerald-500/20 text-emerald-200 hover:bg-emerald-500/30' : 'bg-red-500/20 text-red-200 hover:bg-red-500/30'}`}
      >
        {paused ? <Play size={15} /> : <Pause size={15} />}
        {paused ? 'Continuar' : 'Pausar'}
      </button>

      <div className="hidden h-7 w-px bg-white/10 sm:block" />

      <div className="flex items-center gap-1">
        <Gauge size={14} className="hidden text-blue-300 sm:block" />
        {SPEEDS.map(option => (
          <button
            key={option.value}
            aria-label={`Velocidade ${option.label}`}
            title={option.title}
            disabled={!connected}
            onClick={() => onSpeedChange(option.value)}
            className={`rounded-lg px-2 py-1.5 text-[9px] font-bold transition disabled:opacity-40 ${controls.global.speed === option.value ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/20' : 'text-slate-400 hover:bg-white/10 hover:text-white'}`}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="hidden text-[9px] text-slate-500 lg:block">
        {paused ? 'jornada pausada' : controls.global.speed === 0 ? 'modo acelerado' : `${controls.global.speed}× · ${agentCount} bot${agentCount === 1 ? '' : 's'}`}
      </div>
    </div>
  );
}
