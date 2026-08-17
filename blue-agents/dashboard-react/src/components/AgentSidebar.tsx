import React, { useEffect, useState } from 'react';
import { X, MapPin, Award, Activity, MessageSquare, Zap, Brain, Target, Crosshair, BookOpen } from 'lucide-react';
import { moveLabel, speciesLabel } from '../pokemonNames';

interface AgentSidebarProps {
  agent: any | null;
  onClose: () => void;
  onManualGuide?: (agentName: string, steps: string[]) => void;
  onManualMode?: (agentName: string, enabled: boolean) => void;
  onToggleAgent?: (agentName: string) => void;
  controls?: { agents: Record<string, { paused?: boolean; manual_mode?: boolean }> };
}

const AgentSidebar: React.FC<AgentSidebarProps> = ({ agent, onClose, onManualGuide, onManualMode, onToggleAgent, controls }) => {
  const [pokemonData, setPokemonData] = useState<any[]>([]);
  const manualOn = Boolean(controls?.agents?.[agent?.user]?.manual_mode);

  useEffect(() => {
    if (!agent || !agent.party) return;

    const fetchPokemon = async () => {
      const promises = agent.party.map(async (p: any) => {
        // Map internal ID to PokeAPI ID (Simplified 1-to-1 for Gen 1)
        // Note: Internal IDs in Gen 1 are weird (Rhydon is 1). 
        // We need a mapping table. For now, assuming p.species_id is correct dex number 
        // (which it isn't in Gen 1 internals, but let's assume we fixed it or use a fallback).
        // Actually, PyBoy's party info usually gives internal index.
        // I'll use a direct fetch for now, but might need a mapping later.
        try {
          // Using a placeholder ID if 0 or missing
          const id = p.species_id || 1;
          const res = await fetch(`https://pokeapi.co/api/v2/pokemon/${id}`);
          const data = await res.json();
          return { ...p, sprite: data.sprites.front_default, types: data.types };
        } catch (e) {
          return p;
        }
      });

      const results = await Promise.all(promises);
      setPokemonData(results);
    };

    fetchPokemon();
  }, [agent?.user]);

  if (!agent) return null;

  return (
    <div className="fixed top-4 right-4 w-80 bg-black/80 backdrop-blur-md border border-white/10 rounded-2xl shadow-2xl text-white overflow-hidden transition-all duration-300 z-50 flex flex-col max-h-[90vh]">
      {/* Header */}
      <div className="p-4 border-b border-white/10 flex justify-between items-center bg-gradient-to-r from-blue-900/50 to-transparent">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-blue-500/20 flex items-center justify-center border border-blue-400/30">
            <Activity size={20} className="text-blue-400" />
          </div>
          <div>
            <h2 className="font-bold text-lg leading-tight">{agent.user}</h2>
            <div className="text-xs text-blue-300/70 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              Online
            </div>
          </div>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-white/10 rounded-full transition-colors">
          <X size={18} className="text-gray-400" />
        </button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-6 overflow-y-auto custom-scrollbar">

        {/* Guia Manual — destaque: controle individual do agente */}
        {(onManualGuide || onManualMode) && agent && (
          <div className={`rounded-xl border p-3 transition ${manualOn ? 'border-emerald-400/50 bg-emerald-500/10' : 'border-cyan-400/30 bg-cyan-500/10'}`}>
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="text-[10px] font-bold uppercase tracking-wider text-cyan-300">
                Guia manual — {agent.user}
              </div>
              <div className="flex items-center gap-1">
                {onManualMode && (
                  <button
                    onClick={() => onManualMode(agent.user, !manualOn)}
                    className={`rounded-full border px-2 py-0.5 text-[9px] font-bold transition ${manualOn ? 'border-emerald-400/50 bg-emerald-500/25 text-emerald-100' : 'border-white/15 bg-white/5 text-slate-300 hover:bg-white/15'}`}
                  >
                    {manualOn ? '🟢 guiando' : '⏻ modo guia'}
                  </button>
                )}
                {onToggleAgent && (
                  <button
                    onClick={() => onToggleAgent(agent.user)}
                    className={`rounded-full border px-2 py-0.5 text-[9px] font-bold transition ${agent.paused ? 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200' : 'border-amber-400/40 bg-amber-500/15 text-amber-200'}`}
                  >
                    {agent.paused ? '▶ retomar' : '⏸ pausar'}
                  </button>
                )}
              </div>
            </div>
            <div className="flex items-center justify-center gap-1">
              <div className="grid grid-cols-3 gap-1">
                <div />
                <button
                  onClick={() => onManualGuide?.(agent.user, ['U'])}
                  disabled={!manualOn}
                  className={`rounded-md border px-2.5 py-1.5 text-sm font-bold transition active:scale-95 ${manualOn ? 'border-cyan-400/40 bg-cyan-500/15 text-cyan-200 hover:bg-cyan-500/30' : 'border-white/5 bg-white/0 text-slate-600 cursor-not-allowed'}`}
                >▲</button>
                <div />
                <button
                  onClick={() => onManualGuide?.(agent.user, ['L'])}
                  disabled={!manualOn}
                  className={`rounded-md border px-2.5 py-1.5 text-sm font-bold transition active:scale-95 ${manualOn ? 'border-cyan-400/40 bg-cyan-500/15 text-cyan-200 hover:bg-cyan-500/30' : 'border-white/5 bg-white/0 text-slate-600 cursor-not-allowed'}`}
                >◀</button>
                <button
                  onClick={() => onManualGuide?.(agent.user, ['A'])}
                  disabled={!manualOn}
                  className={`rounded-md border px-2.5 py-1.5 text-sm font-bold transition active:scale-95 ${manualOn ? 'border-emerald-400/50 bg-emerald-500/20 text-emerald-200 hover:bg-emerald-500/35' : 'border-white/5 bg-white/0 text-slate-600 cursor-not-allowed'}`}
                >A</button>
                <button
                  onClick={() => onManualGuide?.(agent.user, ['R'])}
                  disabled={!manualOn}
                  className={`rounded-md border px-2.5 py-1.5 text-sm font-bold transition active:scale-95 ${manualOn ? 'border-cyan-400/40 bg-cyan-500/15 text-cyan-200 hover:bg-cyan-500/30' : 'border-white/5 bg-white/0 text-slate-600 cursor-not-allowed'}`}
                >▶</button>
                <div />
                <button
                  onClick={() => onManualGuide?.(agent.user, ['D'])}
                  disabled={!manualOn}
                  className={`rounded-md border px-2.5 py-1.5 text-sm font-bold transition active:scale-95 ${manualOn ? 'border-cyan-400/40 bg-cyan-500/15 text-cyan-200 hover:bg-cyan-500/30' : 'border-white/5 bg-white/0 text-slate-600 cursor-not-allowed'}`}
                >▼</button>
                <div />
                <button
                  onClick={() => onManualGuide?.(agent.user, ['B'])}
                  disabled={!manualOn}
                  className={`rounded-md border px-2.5 py-1.5 text-sm font-bold transition active:scale-95 ${manualOn ? 'border-rose-400/50 bg-rose-500/20 text-rose-200 hover:bg-rose-500/35' : 'border-white/5 bg-white/0 text-slate-600 cursor-not-allowed'}`}
                >B</button>
              </div>
            </div>
            <div className="mt-1.5 text-center text-[8px] italic text-cyan-500/70">
              {manualOn
                ? 'Guiando: o bot fica parado e cada toque move 1 passo (1×). Ao desligar, o caminho vira trail e o bot aprende.'
                : 'Ative o modo guia para dirigir este bot manualmente.'}
            </div>
          </div>
        )}

        {/* Location */}
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wider text-gray-500 font-semibold flex items-center gap-1">
            <MapPin size={12} /> Location
          </div>
          <div className="bg-white/5 rounded-lg p-3 border border-white/5">
            <div className="text-sm font-medium text-gray-200">{agent.map_name || agent.journey?.map_name || `Map ID: ${agent.map_id ?? 'Unknown'}`}</div>
            <div className="text-xs text-gray-500 mt-1">Map ID: {agent.map_id ?? agent.journey?.map_id ?? 'Unknown'} · Coordinates: {agent.coords_current ? `(${agent.coords_current[0]}, ${agent.coords_current[1]})` : agent.journey?.coords ? `(${agent.journey.coords[0]}, ${agent.journey.coords[1]})` : 'Unknown'}</div>
          </div>
        </div>

        {/* Real journey counters */}
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wider text-gray-500 font-semibold flex items-center gap-1">
            <Target size={12} /> Real journey
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            {[
              ['Objective', agent.journey?.task || agent.current_task || '—'],
              ['Milestone', agent.journey?.milestone || '—'],
              ['Battles', agent.journey?.battles ?? '0'],
              ['Captures', agent.journey?.captures ?? '0'],
              ['Level ups', agent.journey?.level_ups ?? '0'],
              ['Deaths', agent.journey?.deaths ?? '0'],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-lg border border-white/5 bg-white/5 p-2">
                <div className="text-gray-500">{label}</div>
                <div className="mt-1 truncate font-bold text-gray-200">{value}</div>
              </div>
            ))}
          </div>
          {agent.decision_log && <div className="break-all text-[9px] text-gray-600">Log: {agent.decision_log}</div>}
        </div>

        {/* Party with PokeAPI Data */}
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wider text-gray-500 font-semibold flex items-center gap-1">
            <Zap size={12} /> Party
          </div>
          <div className="grid grid-cols-1 gap-2">
            {pokemonData.length > 0 ? pokemonData.map((p: any, i: number) => (
              <div key={i} className="bg-white/5 rounded-lg border border-white/5 flex items-center p-2 gap-3 hover:bg-white/10 transition-colors">
                <div className="w-10 h-10 bg-gray-800/50 rounded-full flex items-center justify-center overflow-hidden border border-white/10">
                  {p.sprite ? (
                    <img src={p.sprite} alt="pkmn" className="w-12 h-12 object-contain pixelated" />
                  ) : (
                    <div className="w-6 h-6 bg-gray-600 rounded-full" />
                  )}
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-bold capitalize">
                      {p.name || speciesLabel(p.species_id)}
                      {Number(p.hp) <= 0 && <span className="ml-1 text-[9px] text-red-400 font-bold uppercase">caído</span>}
                    </span>
                    <span className="text-xs font-mono text-yellow-400">Lv.{p.level}</span>
                  </div>
                  <div className="flex gap-1 mt-1">
                    {p.types && p.types.map((t: any, ti: number) => (
                      <span key={ti} className="text-[9px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-300 uppercase tracking-wider">
                        {t.type.name}
                      </span>
                    ))}
                  </div>
                  <div className="mt-1.5">
                    <div className="flex justify-between text-[9px] text-gray-400 mb-0.5">
                      <span>HP</span>
                      <span className="font-mono">{p.hp ?? '?'}/{p.max_hp ?? '?'}</span>
                    </div>
                    <div className="h-1.5 bg-gray-700/50 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all ${Number(p.hp) <= 0 ? 'bg-red-500' : Number(p.hp) / Math.max(Number(p.max_hp), 1) < 0.3 ? 'bg-yellow-400' : 'bg-green-500'}`}
                        style={{ width: `${Math.max(0, Math.min(100, (Number(p.hp) / Math.max(Number(p.max_hp), 1)) * 100))}%` }}
                      />
                    </div>
                  </div>
                  {(p.moves || []).length > 0 && (
                    <div className="mt-1.5 grid grid-cols-2 gap-x-2 gap-y-0.5">
                      {(p.moves).map((m: any, mi: number) => (
                        <div key={mi} className="flex items-center gap-1 text-[9px]">
                          <span className="text-gray-400 truncate flex-1">{moveLabel(m.id)}</span>
                          <span className={`font-mono ${Number(m.pp) <= 0 ? 'text-red-400' : 'text-gray-300'}`}>{m.pp}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )) : (
              <div className="text-xs text-gray-600 italic text-center py-4">No Pokemon data</div>
            )}
          </div>
        </div>

        {/* Badges */}
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wider text-gray-500 font-semibold flex items-center gap-1">
            <Award size={12} /> Badges
          </div>
        <div className="flex gap-1">
            {[...Array(8)].map((_, i) => (
              <div key={i} className={`w-6 h-6 rounded-full border ${i < (agent.badges || 0) ? 'bg-yellow-500/20 border-yellow-500/50' : 'bg-gray-800/50 border-gray-700'} flex items-center justify-center transition-all`}>
                {i < (agent.badges || 0) && <div className="w-3 h-3 bg-yellow-500 rounded-full shadow-[0_0_5px_rgba(234,179,8,0.5)]" />}
              </div>
            ))}
          </div>
        </div>

        {/* Recent decisions from the real emulator */}
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wider text-gray-500 font-semibold flex items-center gap-1">
            <Brain size={12} /> Marcos e decisões
          </div>
          <div className="space-y-1.5">
            {(agent.recent_events || []).filter((event: any) => [
              'capture_decision', 'capture', 'level_up', 'training_target',
              'battle_win', 'battle_loss', 'story_milestone',
              'location_discovered', 'rare_encounter', 'objective_changed',
            ].includes(event.type)).slice(-8).reverse().map((event: any, index: number) => (
              <div key={String(event.id || index)} className="rounded-lg border border-white/5 bg-white/5 p-2 text-[10px] text-gray-300">
                <div className="flex items-center gap-1.5 font-bold text-gray-200">
                  {event.type === 'capture_decision'
                    ? <Crosshair size={11} className="text-yellow-300" />
                    : event.type === 'story_milestone' || event.type === 'location_discovered'
                      ? <BookOpen size={11} className="text-blue-300" />
                      : <Zap size={11} className="text-blue-300" />}
                  {event.type === 'capture_decision'
                    ? `${event.data?.choice === 'capture' ? 'capturar' : 'derrotar'} #${event.data?.enemy_species_id || '?'}`
                    : event.data?.title || event.type}
                  <span className="ml-auto text-[9px] font-normal text-gray-600">step {event.step}</span>
                </div>
                <div className="mt-1 text-gray-500">{event.data?.reason || event.map_name || ''}</div>
              </div>
            ))}
            {!(agent.recent_events || []).some((event: any) => [
              'capture_decision', 'capture', 'level_up', 'training_target',
              'story_milestone', 'location_discovered', 'rare_encounter',
            ].includes(event.type)) && (
              <div className="text-[10px] italic text-gray-600">Nenhum marco importante registrado ainda.</div>
            )}
          </div>
        </div>

      </div>

      {/* Chat Interface */}
      <div className="mt-auto border-t border-white/10 bg-black/20 p-3">
        <div className="text-xs uppercase tracking-wider text-gray-500 font-semibold mb-2 flex items-center gap-1">
          <MessageSquare size={12} /> Mission Control
        </div>
        <div className="h-24 bg-black/40 rounded-lg border border-white/5 mb-2 p-2 overflow-y-auto text-xs space-y-2 custom-scrollbar">
          <div className="bg-blue-500/10 text-blue-200 p-2 rounded-lg rounded-tl-none border border-blue-500/10">
            Objetivo atual: {agent.journey?.task || agent.current_task || 'início da jornada'}.
          </div>
        </div>
        <div className="flex gap-2">
          <input type="text" placeholder="Send command..." className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500/50 transition-colors" />
          <button className="bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded-lg text-xs font-medium transition-colors">Send</button>
        </div>
      </div>
    </div>
  );
};

export default AgentSidebar;
