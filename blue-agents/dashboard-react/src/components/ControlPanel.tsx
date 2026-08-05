import React, { useMemo } from 'react';
import { X, Users, Map, Zap, Sparkles, Pause, Play } from 'lucide-react';
import type { RuntimeControls } from './JourneyControls';

interface ControlPanelProps {
  agents: Record<string, any>;
  onClose: () => void;
  onSaveAll: () => void;
  onAskAI?: (agentName: string, agentData: any) => void;
  onResetAgent?: (agentName: string) => void;
  controls: RuntimeControls;
  onToggleAgent: (agentName: string) => void;
}

const ControlPanel: React.FC<ControlPanelProps> = ({ agents, onClose, onSaveAll, onAskAI, onResetAgent, controls, onToggleAgent }) => {
  // Memoize agent list and stats calculations
  const { agentList, totalBadges, activeBattles } = useMemo(() => {
    const list = Object.values(agents);
    const badges = list.reduce((acc, a) => acc + (a.badges || 0), 0);
    const battles = list.filter(a => a.battle_info?.is_battle).length;
    return { agentList: list, totalBadges: badges, activeBattles: battles };
  }, [agents]);

  const gridColumns = agentList.length <= 2
    ? 'grid-cols-1 lg:grid-cols-2'
    : agentList.length === 3
      ? 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3'
      : 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4';

  // Helper to get Pokemon Sprite (simplified)
  const getSprite = (id: number) => `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/${id}.png`;

  return (
    <div className="fixed inset-0 bg-black/90 backdrop-blur-xl z-[100] overflow-hidden flex flex-col animate-in fade-in duration-200">
      {/* Header */}
      <div className="p-6 border-b border-white/10 flex justify-between items-center bg-gradient-to-r from-blue-900/20 to-transparent">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-blue-500/20 rounded-xl border border-blue-400/30">
            <Users size={24} className="text-blue-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Command Center</h1>
            <div className="text-sm text-gray-400 flex gap-4">
              <span>Active Agents: <span className="text-white font-mono">{agentList.length}</span></span>
              <span>Total Badges: <span className="text-yellow-400 font-mono">{totalBadges}</span></span>
              <span>In Battle: <span className="text-red-400 font-mono">{activeBattles}</span></span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={onSaveAll}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-bold text-sm transition-colors flex items-center gap-2"
          >
            <Zap size={16} /> Save All Agents
          </button>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-full transition-colors group"
          >
            <X size={24} className="text-gray-400 group-hover:text-white" />
          </button>
        </div>
      </div>

      {/* Grid Content */}
      <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
        <div className={`grid gap-6 ${gridColumns}`}>
          {agentList.map((agent) => {
            const paused = Boolean(controls.agents[agent.user]?.paused || agent.runtime_control?.paused);
            return (
            <div key={agent.user} className="bg-white/5 border border-white/10 rounded-xl overflow-hidden hover:border-blue-500/30 transition-all group">
              {/* Agent Header */}
              <div className="p-4 bg-white/5 border-b border-white/5 flex justify-between items-start">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-600 to-blue-800 flex items-center justify-center font-bold text-lg shadow-lg">
                    {agent.user.substring(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <div className="font-bold text-white group-hover:text-blue-400 transition-colors">{agent.user}</div>
                    <div className="text-xs text-gray-400 flex items-center gap-1">
                      <Map size={10} /> Map: {agent.map_id}
                    </div>
                    {agent.personality && (
                      <div className="text-[9px] text-gray-500 mt-0.5">
                        🎭 {agent.personality}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <div className={`text-[10px] px-2 py-0.5 rounded-full border ${paused ? 'bg-amber-500/20 border-amber-500 text-amber-300' : agent.battle_info?.is_battle ? 'bg-red-500/20 border-red-500 text-red-400' : 'bg-green-500/20 border-green-500 text-green-400'}`}>
                    {paused ? 'PAUSED' : agent.battle_info?.is_battle ? 'IN BATTLE' : 'EXPLORING'}
                  </div>
                  {agent.meta_score !== undefined && (
                    <div className={`text-[9px] px-1.5 py-0.5 rounded ${agent.meta_score >= 80 ? 'bg-blue-500/20 text-blue-300' :
                      agent.meta_score >= 40 ? 'bg-yellow-500/20 text-yellow-300' :
                        'bg-red-500/20 text-red-300'
                      }`}>
                      Meta: {agent.meta_score}
                    </div>
                  )}
                  <div className="text-[10px] text-gray-500 font-mono">
                    Step: {agent.step_count}
                  </div>
                </div>
              </div>

              {/* Stats Row */}
              <div className="grid grid-cols-3 divide-x divide-white/5 border-b border-white/5 bg-black/20">
                <div className="p-2 text-center">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider">Badges</div>
                  <div className="text-lg font-mono text-yellow-400">{agent.badges || 0}</div>
                </div>
                <div className="p-2 text-center">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider">Seen</div>
                  <div className="text-lg font-mono text-blue-400">{agent.pokedex_seen || 0}</div>
                </div>
                <div className="p-2 text-center">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider">Owned</div>
                  <div className="text-lg font-mono text-green-400">{agent.pokedex_owned || 0}</div>
                </div>
              </div>

              {/* Real journey summary */}
              <div className="p-3 border-b border-white/5 bg-blue-950/10">
                <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2 flex items-center justify-between">
                  <span>Real journey</span>
                  <span className="text-blue-300">{agent.journey?.map_name || `Map ${agent.map_id ?? '?'}`}</span>
                </div>
                <div className="grid grid-cols-2 gap-1.5 text-[9px]">
                  <div className="rounded bg-white/5 p-1.5"><span className="text-gray-500">Objective</span><div className="truncate text-gray-200">{agent.journey?.task || '—'}</div></div>
                  <div className="rounded bg-white/5 p-1.5"><span className="text-gray-500">Milestone</span><div className="truncate text-gray-200">{agent.journey?.milestone || '—'}</div></div>
                  <div className="rounded bg-white/5 p-1.5"><span className="text-gray-500">Battles / decisions</span><div className="text-gray-200">{agent.journey?.battles ?? 0} / {agent.journey?.decision_count ?? 0}</div></div>
                  <div className="rounded bg-white/5 p-1.5"><span className="text-gray-500">Captures / levels</span><div className="text-gray-200">{agent.journey?.captures ?? 0} / {agent.journey?.level_ups ?? 0}</div></div>
                </div>
              </div>

              {/* Party Grid */}
              <div className="p-3">
                <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1">
                  <Zap size={10} /> Current Party
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {agent.party && agent.party.length > 0 ? (
                    agent.party.map((p: any, i: number) => (
                      <div key={i} className="bg-black/40 rounded p-1.5 flex flex-col items-center border border-white/5 relative group/poke">
                        <img
                          src={getSprite(p.species_id || 1)}
                          alt=""
                          className="w-10 h-10 object-contain pixelated"
                          onError={(e) => (e.currentTarget.style.display = 'none')}
                        />
                        <div className="text-[9px] font-bold text-gray-300 mt-1">Lv.{p.level}</div>
                        <div className="text-[8px] text-gray-500 truncate max-w-full" title={`Internal ID: ${p.internal_id ?? '?'} · National ID: ${p.species_id ?? '?'}`}>
                          #{p.species_id ?? '?'} · {p.hp}/{p.max_hp}
                        </div>
                        <div className="w-full h-1 bg-gray-700 rounded-full mt-1 overflow-hidden">
                          <div className="h-full bg-green-500 w-[80%]" />
                        </div>

                        <div className="hidden group-hover/poke:block absolute left-full ml-2 top-0 z-20 w-36 rounded bg-black border border-white/20 p-2 text-[9px] text-gray-300">
                          <div className="font-bold text-white mb-1">Build #{p.species_id ?? '?'}</div>
                          <div>HP {p.hp}/{p.max_hp}</div>
                          <div className="mt-1 text-gray-500">Moves</div>
                          {(p.moves || []).map((move: any, moveIndex: number) => (
                            <div key={moveIndex}>#{move.id} · PP {move.pp ?? '?'}</div>
                          ))}
                        </div>

                        {/* Tooltip */}
                        <div className="absolute bottom-full mb-2 bg-black border border-white/20 px-2 py-1 rounded text-[10px] whitespace-nowrap hidden group-hover/poke:block z-10">
                          HP: {p.hp}/{p.max_hp}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="col-span-3 text-center py-4 text-xs text-gray-600 italic">
                      No Pokemon
                    </div>
                  )}
                  {/* Empty Slots */}
                  {[...Array(Math.max(0, 6 - (agent.party?.length || 0)))].map((_, i) => (
                    <div key={`empty-${i}`} className="bg-white/5 rounded border border-white/5 aspect-square flex items-center justify-center">
                      <div className="w-2 h-2 rounded-full bg-white/5" />
                    </div>
                  ))}
                </div>

                {/* Decision trail */}
                <div className="mt-3 border-t border-white/5 pt-2">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Recent decisions</div>
                  {(agent.recent_events || []).filter((event: any) => [
                    'capture_decision', 'capture', 'level_up', 'training_target',
                    'battle_win', 'battle_loss', 'story_milestone', 'location_discovered',
                  ].includes(event.type)).slice(-3).reverse().map((event: any, eventIndex: number) => (
                    <div key={String(event.id || eventIndex)} className="text-[9px] text-gray-400 truncate" title={event.data?.reason || ''}>
                      <span className="text-violet-300">{event.type}</span>{' · '}
                      {event.type === 'capture_decision'
                        ? `${event.data?.choice === 'capture' ? 'capturar' : 'derrotar'} #${event.data?.enemy_species_id || '?'} · ${event.data?.motivation || 'treino'}`
                        : event.data?.title || event.data?.reason || 'confirmed'}
                    </div>
                  ))}
                  {!(agent.recent_events || []).some((event: any) => [
                    'capture_decision', 'capture', 'level_up', 'training_target',
                    'battle_win', 'battle_loss', 'story_milestone', 'location_discovered',
                  ].includes(event.type)) && <div className="text-[9px] italic text-gray-600">Nenhum marco importante ainda.</div>}
                </div>

                <div className="mt-3 border-t border-white/5 pt-3">
                  <button
                    aria-label={paused ? `Continuar ${agent.user}` : `Pausar ${agent.user}`}
                    onClick={() => onToggleAgent(agent.user)}
                    className={`flex w-full items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-bold transition ${paused ? 'border-emerald-400/30 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/25' : 'border-amber-400/30 bg-amber-500/15 text-amber-200 hover:bg-amber-500/25'}`}
                  >
                    {paused ? <Play size={14} /> : <Pause size={14} />}
                    {paused ? 'Continuar jornada' : 'Pausar este bot'}
                  </button>
                </div>

                {/* AI Assistant Button */}
                {onAskAI && (
                  <div className="p-3 pt-0">
                    <button
                      onClick={() => onAskAI(agent.user, agent)}
                      className="w-full px-3 py-2 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white rounded-lg font-bold text-xs transition-all flex items-center justify-center gap-2 shadow-lg hover:shadow-purple-500/50 group"
                    >
                      <Sparkles size={14} className="group-hover:rotate-12 transition-transform" />
                      Ask AI for Strategy
                    </button>
                  </div>
                )}

                {/* Reset Agent Button */}
                {onResetAgent && (
                  <div className="p-3 pt-0">
                    <button
                      onClick={() => {
                        if (confirm(`⚠️ Reset ${agent.user}? This will delete their save and restart from zero!`)) {
                          onResetAgent(agent.user);
                        }
                      }}
                      className="w-full px-3 py-1.5 bg-red-600/20 hover:bg-red-600/40 border border-red-500/30 hover:border-red-500 text-red-400 hover:text-red-300 rounded-lg font-bold text-xs transition-all flex items-center justify-center gap-2"
                    >
                      🗑️ Reset Agent
                    </button>
                  </div>
                )}
              </div>
            </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default ControlPanel;
