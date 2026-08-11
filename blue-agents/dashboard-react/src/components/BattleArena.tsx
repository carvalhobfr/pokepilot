import { useEffect, useMemo, useState } from 'react';
import { Activity, Crosshair, Eye, Maximize2, Shield, Swords, X, ZoomIn, ZoomOut } from 'lucide-react';
import { speciesLabel, moveLabel as moveName } from '../pokemonNames';

interface BattleArenaProps {
  agents: Record<string, any>;
  open: boolean;
  onClose: () => void;
}

const spriteUrl = (id: number) =>
  id > 0 ? 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/' + id + '.png' : '';

const enemySpeciesId = (battle: any) => Number(battle?.enemy_species_id || battle?.enemy_id || 0);

const activeSpeciesId = (agent: any) => Number(
  agent?.battle_info?.active_pokemon?.species_id || agent?.party?.[0]?.species_id || 0,
);

const encounterLabel = (battle: any) => {
  if (battle?.encounter_label) return battle.encounter_label;
  return battle?.is_trainer || Number(battle?.battle_status) === 2
    ? 'Duelo de treinador'
    : 'Encontro selvagem';
};

const encounterTone = (type: string) => {
  if (type === 'gym') return 'border-yellow-300/40 bg-yellow-400/15 text-yellow-100';
  if (type === 'league') return 'border-violet-300/40 bg-violet-400/15 text-violet-100';
  if (type === 'story') return 'border-blue-300/40 bg-blue-400/15 text-blue-100';
  if (String(type).startsWith('trainer')) return 'border-orange-300/40 bg-orange-400/15 text-orange-100';
  return 'border-emerald-300/40 bg-emerald-400/15 text-emerald-100';
};

const moveLabel = (move: any) => {
  const id = Number(move?.id || 0);
  const name = moveName(id);
  return move?.pp == null ? name : name + ' · PP ' + move.pp;
};

const hpPercent = (pokemon: any) => {
  const hp = Number(pokemon?.hp || 0);
  const max = Math.max(Number(pokemon?.max_hp || 1), 1);
  return Math.max(0, Math.min(100, (hp / max) * 100));
};

function PokemonMatchup({ agent, compact = false }: { agent: any; compact?: boolean }) {
  const battle = agent.battle_info || {};
  const activeId = activeSpeciesId(agent);
  const enemyId = enemySpeciesId(battle);
  const imageClass = compact ? 'h-10 w-10' : 'h-20 w-20';

  return (
    <div className={`grid grid-cols-[1fr_auto_1fr] items-center ${compact ? 'gap-1' : 'gap-4'} rounded-xl border border-white/10 bg-slate-950/70 ${compact ? 'p-1.5' : 'p-4'}`}>
      <div className="min-w-0 text-center">
        <div className="text-[8px] font-bold uppercase tracking-wider text-blue-300">Seu Pokémon</div>
        <div className="flex justify-center">
          {activeId > 0 ? <img src={spriteUrl(activeId)} alt={`Pokémon ativo #${activeId}`} className={`${imageClass} object-contain pixelated`} /> : <div className={imageClass} />}
        </div>
        <div className="truncate text-[9px] font-bold text-white">{speciesLabel(activeId)} · Lv.{battle.active_pokemon?.level || agent.party?.[0]?.level || '?'}</div>
      </div>
      <div className={`${compact ? 'text-[9px]' : 'text-sm'} font-black text-red-300`}>VS</div>
      <div className="min-w-0 text-center">
        <div className="text-[8px] font-bold uppercase tracking-wider text-red-300">Adversário</div>
        <div className="flex justify-center">
          {enemyId > 0 ? <img src={spriteUrl(enemyId)} alt={`Pokémon adversário ${speciesLabel(enemyId)}`} className={`${imageClass} object-contain pixelated`} /> : <div className={imageClass} />}
        </div>
        <div className="truncate text-[9px] font-bold text-white">{speciesLabel(enemyId)} · Lv.{battle.enemy_level || '?'}</div>
      </div>
    </div>
  );
}

function BuildModal({ agent, onClose }: { agent: any; onClose: () => void }) {
  const build = agent.build || {};
  const traits = build.traits || {};
  const team = Array.isArray(build.team) && build.team.length > 0
    ? build.team
    : (agent.party || []);
  const active = build.active_pokemon || agent.battle_info?.active_pokemon || team[0];

  return (
    <div className="fixed inset-0 z-[260] flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-hidden rounded-2xl border border-blue-400/30 bg-slate-950 text-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 bg-blue-950/30 p-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-black uppercase tracking-wider text-blue-200">
              <Shield size={17} /> Build de {agent.user}
            </div>
            <div className="mt-1 text-xs text-slate-400">
              {build.personality || agent.personality || 'Personalidade não informada'} · starter {build.starter || agent.starter || '?'}
            </div>
          </div>
          <button aria-label="Fechar build" onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-white/10 hover:text-white">
            <X size={18} />
          </button>
        </div>

        <div className="max-h-[calc(90vh-74px)] space-y-5 overflow-y-auto p-5 custom-scrollbar">
          <div className="grid gap-4 md:grid-cols-[1fr_1.35fr]">
            <section className="rounded-xl border border-white/10 bg-white/5 p-4">
              <div className="mb-3 text-[10px] font-bold uppercase tracking-wider text-slate-400">Perfil e política</div>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between gap-3"><span className="text-slate-400">Personalidade</span><span className="font-bold text-blue-200">{build.personality || agent.personality || '?'}</span></div>
                <div className="flex justify-between gap-3"><span className="text-slate-400">Starter</span><span className="font-bold text-yellow-300">{build.starter || agent.starter || '?'}</span></div>
                <div className="flex justify-between gap-3"><span className="text-slate-400">Política</span><span className="text-right text-slate-200">{build.policy || 'PPO'}</span></div>
                <div className="flex justify-between gap-3"><span className="text-slate-400">Batalha</span><span className="text-right text-slate-200">{build.battle_strategy || 'Regras'}</span></div>
              </div>
              <div className="mt-4 space-y-2">
                {[
                  ['Meta', traits.meta_score],
                  ['Exploração', traits.exploration],
                  ['Coleção', traits.collector],
                  ['Missão', traits.mission_focus],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <div className="mb-1 flex justify-between text-[10px] text-slate-400"><span>{label}</span><span>{Number(value || 0)}</span></div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
                      <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-300" style={{ width: Math.max(0, Math.min(100, Number(value || 0))) + '%' }} />
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-xl border border-red-400/20 bg-red-950/10 p-4">
              <div className="mb-3 flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-red-200">
                <Crosshair size={14} /> Pokémon usado agora
              </div>
              {active ? (
                <div className="flex gap-4">
                  <div className="flex h-24 w-24 items-center justify-center rounded-xl bg-black/40">
                    {spriteUrl(Number(active.species_id)) && <img src={spriteUrl(Number(active.species_id))} alt="Pokémon ativo" className="h-20 w-20 object-contain pixelated" />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-lg font-black">{speciesLabel(active.species_id)}</div>
                    <div className="text-xs text-yellow-300">Lv.{active.level || '?'}</div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800">
                      <div className="h-full rounded-full bg-green-400" style={{ width: hpPercent(active) + '%' }} />
                    </div>
                    <div className="mt-1 text-[10px] text-slate-400">{active.hp ?? '?'} / {active.max_hp ?? '?'} HP</div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(active.moves || []).map((move: any, index: number) => (
                        <span key={String(move.id) + '-' + index} className="rounded bg-red-400/10 px-1.5 py-1 text-[9px] text-red-100">
                          {moveLabel(move)}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-xs italic text-slate-500">O Pokémon ativo aparece quando a luta estiver em estado legível.</div>
              )}
            </section>
          </div>

          <section>
            <div className="mb-3 flex items-center justify-between">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Time escolhido · {team.length}/6</div>
              <div className="text-[10px] text-slate-500">IDs e golpes vêm do estado do emulador</div>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              {team.map((pokemon: any, index: number) => (
                <div key={String(pokemon.species_id) + '-' + index} className="flex gap-3 rounded-xl border border-white/10 bg-white/5 p-3">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-black/30">
                    {spriteUrl(Number(pokemon.species_id)) && <img src={spriteUrl(Number(pokemon.species_id))} alt={'Pokémon #' + pokemon.species_id} className="h-11 w-11 object-contain pixelated" />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold">{speciesLabel(pokemon.species_id)}</span>
                      <span className="text-yellow-300">Lv.{pokemon.level || '?'}</span>
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-800">
                      <div className="h-full rounded-full bg-green-400" style={{ width: hpPercent(pokemon) + '%' }} />
                    </div>
                    <div className="mt-1 text-[10px] text-slate-400">{pokemon.hp ?? '?'} / {pokemon.max_hp ?? '?'} HP</div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(pokemon.moves || []).length > 0 ? pokemon.moves.map((move: any, moveIndex: number) => (
                        <span key={String(move.id) + '-' + moveIndex} className="rounded bg-blue-400/10 px-1.5 py-1 text-[9px] text-blue-100">
                          {moveLabel(move)}
                        </span>
                      )) : <span className="text-[9px] italic text-slate-600">Golpes ainda não lidos</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function BattleFocus({ agent, onClose, onBuild }: { agent: any; onClose: () => void; onBuild: () => void }) {
  const [zoom, setZoom] = useState<1 | 2>(2);
  const frame = agent.battle_frame;
  const battle = agent.battle_info || {};

  return (
    <div className="fixed inset-0 z-[240] flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm">
      <div className="w-full max-w-4xl overflow-hidden rounded-2xl border border-red-400/30 bg-slate-950 text-white shadow-[0_0_80px_rgba(239,68,68,0.2)]">
        <div className="flex items-center justify-between border-b border-white/10 bg-red-950/30 p-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-black uppercase tracking-wider text-red-200"><Swords size={17} /> {agent.user} · batalha ao vivo</div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span className={`rounded-full border px-2 py-0.5 font-bold ${encounterTone(battle.encounter_type)}`}>{encounterLabel(battle)}</span>
              <span>{battle.map_name || agent.journey?.map_name || 'Local não identificado'}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setZoom(zoom === 1 ? 2 : 1)} className="flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1.5 text-xs text-slate-200 hover:bg-white/10">
              {zoom === 1 ? <ZoomIn size={14} /> : <ZoomOut size={14} />} {zoom}×
            </button>
            <button onClick={onBuild} className="flex items-center gap-1 rounded-lg border border-blue-400/30 bg-blue-500/10 px-2 py-1.5 text-xs text-blue-100 hover:bg-blue-500/20">
              <Eye size={14} /> Ver build
            </button>
            <button aria-label="Fechar visão ampliada" onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-white/10 hover:text-white"><X size={18} /></button>
          </div>
        </div>
        <div className="flex max-h-[78vh] flex-col items-center justify-center gap-4 overflow-auto bg-black/50 p-6">
          {frame ? (
            <img src={frame} alt={'Frame da batalha de ' + agent.user} style={{ width: (160 * zoom) + 'px', height: (144 * zoom) + 'px', imageRendering: 'pixelated' }} className="max-w-none rounded border border-white/10 shadow-2xl" />
          ) : (
            <div className="flex h-72 w-full max-w-2xl items-center justify-center rounded-xl border border-dashed border-white/10 text-sm italic text-slate-500">Frame da batalha indisponível neste update.</div>
          )}
          <div className="w-full max-w-lg">
            <PokemonMatchup agent={agent} />
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <Activity size={14} className="text-red-300" /> {battle.active_pokemon ? 'Ativo ' + speciesLabel(battle.active_pokemon.species_id) : 'Time carregado'} · {agent.party?.length || 0}/6 Pokémon
          </div>
        </div>
      </div>
    </div>
  );
}

export default function BattleArena({ agents, open, onClose }: BattleArenaProps) {
  const [focusedName, setFocusedName] = useState<string | null>(null);
  const [focusedSnapshot, setFocusedSnapshot] = useState<any | null>(null);
  const [buildName, setBuildName] = useState<string | null>(null);
  // Sometimes you want one bot's fight, sometimes everyone's. An empty set
  // means "whoever is fighting", which is the useful default.
  const [watching, setWatching] = useState<Set<string>>(new Set());

  const everyone = useMemo(
    () => Object.values(agents).sort((a: any, b: any) =>
      String(a.user).localeCompare(String(b.user))),
    [agents],
  );

  const activeBattles = useMemo(() => everyone
    .filter((agent: any) => agent.battle_info?.is_battle)
    .filter((agent: any) => watching.size === 0 || watching.has(String(agent.user)))
    .slice(0, 4), [everyone, watching]);

  const toggleWatching = (name: string) => setWatching(current => {
    const next = new Set(current);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    return next;
  });

  const currentFocusedAgent = focusedName ? agents[focusedName] : null;
  const focusedAgent = focusedName && focusedSnapshot ? {
    ...focusedSnapshot,
    ...(currentFocusedAgent || {}),
    battle_frame: currentFocusedAgent?.battle_frame || focusedSnapshot.battle_frame,
    battle_info: currentFocusedAgent?.battle_info?.is_battle
      ? currentFocusedAgent.battle_info
      : focusedSnapshot.battle_info,
  } : currentFocusedAgent;
  const buildAgent = buildName ? agents[buildName] : null;

  useEffect(() => {
    if (focusedName && !focusedAgent && !focusedSnapshot) setFocusedName(null);
    if (buildName && !buildAgent) setBuildName(null);
  }, [buildAgent, buildName, focusedAgent, focusedName, focusedSnapshot]);

  if (!open) return null;

  return (
    <>
      <div className="fixed bottom-4 left-4 z-[130] w-[min(780px,calc(100vw-2rem))] rounded-2xl border border-red-400/30 bg-black/85 p-3 text-white shadow-2xl backdrop-blur-md">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-black uppercase tracking-wider text-red-200"><Swords size={15} /> Arena opcional</div>
            <div className="mt-1 text-[10px] text-slate-500">Clique numa miniatura para ampliar; a arena não abre sozinha.</div>
            <div className="mt-2 flex flex-wrap items-center gap-1">
              <button
                onClick={() => setWatching(new Set())}
                className={`rounded-full border px-2 py-0.5 text-[9px] font-bold transition ${
                  watching.size === 0
                    ? 'border-red-300/60 bg-red-500/20 text-red-100'
                    : 'border-white/10 bg-white/5 text-slate-400 hover:border-white/30'
                }`}
              >
                TODOS
              </button>
              {everyone.map((agent: any) => (
                <button
                  key={`watch-${agent.user}`}
                  onClick={() => toggleWatching(String(agent.user))}
                  title={`Ver a arena de ${agent.user}`}
                  className={`rounded-full border px-2 py-0.5 text-[9px] font-bold transition ${
                    watching.has(String(agent.user))
                      ? 'border-red-300/60 bg-red-500/20 text-red-100'
                      : 'border-white/10 bg-white/5 text-slate-400 hover:border-white/30'
                  }`}
                >
                  {agent.user}
                  {agent.battle_info?.is_battle ? ' ⚔' : ''}
                </button>
              ))}
            </div>
          </div>
          <button aria-label="Fechar arena" onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-white/10 hover:text-white"><X size={17} /></button>
        </div>

        {activeBattles.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-xs italic text-slate-500">
            {watching.size > 0
              ? 'Nenhum dos bots escolhidos está em batalha agora. Clique em TODOS para acompanhar quem estiver lutando.'
              : 'Nenhuma batalha ativa agora. O painel fica parado até um agente entrar em combate.'}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {activeBattles.map((agent: any) => (
              <article key={agent.user} onClick={() => { setFocusedSnapshot(agent); setFocusedName(agent.user); }} className="group cursor-pointer overflow-hidden rounded-xl border border-white/10 bg-white/5 transition hover:border-red-300/60 hover:bg-white/10">
                <div className="relative aspect-[10/9] bg-black">
                  {agent.battle_frame ? <img src={agent.battle_frame} alt={'Miniatura da batalha de ' + agent.user} className="h-full w-full object-contain pixelated" /> : <div className="flex h-full items-center justify-center text-[10px] text-slate-600">sem frame</div>}
                  <div className="absolute left-1 top-1 rounded bg-black/70 px-1.5 py-1 text-[9px] font-bold text-red-100">{agent.user}</div>
                  <div className={`absolute right-1 top-1 max-w-[70%] truncate rounded-full border px-1.5 py-1 text-[8px] font-bold ${encounterTone(agent.battle_info?.encounter_type)}`}>{encounterLabel(agent.battle_info)}</div>
                  <div className="absolute bottom-1 right-1 rounded bg-black/70 px-1.5 py-1 text-[9px] text-white opacity-0 transition group-hover:opacity-100"><Maximize2 size={12} /></div>
                </div>
                <div className="p-2">
                  <PokemonMatchup agent={agent} compact />
                  <div className="mt-1 truncate text-center text-[8px] text-slate-500">{agent.battle_info?.map_name || agent.journey?.map_name || 'Local desconhecido'}</div>
                  <button onClick={(event) => { event.stopPropagation(); setBuildName(agent.user); }} className="mt-2 w-full rounded bg-blue-500/10 px-2 py-1.5 text-[9px] font-bold text-blue-100 hover:bg-blue-500/20">VER BUILD</button>
                </div>
              </article>
            ))}
          </div>
        )}
        {Object.values(agents).length > 0 && (
          <div className="mt-3 border-t border-white/10 pt-3">
            <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Builds dos bots</div>
            <div className="flex flex-wrap gap-2">
              {Object.values(agents).sort((a: any, b: any) => String(a.user).localeCompare(String(b.user))).map((agent: any) => (
                <button key={agent.user} onClick={() => setBuildName(agent.user)} className="rounded-lg border border-blue-400/20 bg-blue-500/10 px-2 py-1.5 text-[10px] font-bold text-blue-100 hover:bg-blue-500/20">
                  {agent.user} · {agent.party?.length || 0}/6
                </button>
              ))}
            </div>
          </div>
        )}
        {Object.values(agents).filter((agent: any) => agent.battle_info?.is_battle).length > 4 && <div className="mt-2 text-center text-[10px] text-slate-500">Mostrando 4 de {Object.values(agents).filter((agent: any) => agent.battle_info?.is_battle).length} batalhas. Escolha quais observar na próxima rodada.</div>}
      </div>

      {focusedAgent && <BattleFocus agent={focusedAgent} onClose={() => { setFocusedName(null); setFocusedSnapshot(null); }} onBuild={() => setBuildName(focusedAgent.user)} />}
      {buildAgent && <BuildModal agent={buildAgent} onClose={() => setBuildName(null)} />}
    </>
  );
}
