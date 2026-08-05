import React, { useEffect, useState, useCallback } from 'react';
import { Scroll, ArrowUpCircle, Archive, Zap, MapPin, Swords, Crosshair, Skull, Target, Sparkles, BookOpen, Award } from 'lucide-react';

interface EventLog {
  agent: string;
  type: string;
  data: any;
  timestamp: number;
  pokemon?: {
    species_id: number;
    level: number;
    hp: number;
    max_hp: number;
  };
}

const EventFeed: React.FC<{ ws: React.MutableRefObject<WebSocket | null>; connected: boolean }> = ({ ws, connected }) => {
  const [events, setEvents] = useState<EventLog[]>([]);

  // Memoize event handler
  const handleMessage = useCallback(async (event: MessageEvent) => {
    let data;

    // Handle Blob or ArrayBuffer data
    if (event.data instanceof Blob) {
      const text = await event.data.text();
      data = JSON.parse(text);
    } else if (typeof event.data === 'string') {
      data = JSON.parse(event.data);
    } else {
      console.error('[EventFeed] Unknown WebSocket data type:', typeof event.data);
      return;
    }

    // Check if this update contains event logs
    if (data.metadata && data.metadata.recent_events && data.metadata.recent_events.length > 0) {
      const newEvents = data.metadata.recent_events;

      setEvents(prev => {
        // Filter out duplicates based on timestamp + agent + type
        const existingKeys = new Set(prev.map(e => `${e.agent}-${e.type}-${e.timestamp}`));
        const uniqueNew = newEvents
          .map((e: any) => ({ ...e, agent: data.metadata.user }))
          .filter((e: any) => !existingKeys.has(`${data.metadata.user}-${e.type}-${e.timestamp}`));

        if (uniqueNew.length === 0) return prev;
        return [...uniqueNew, ...prev].slice(0, 50); // Keep last 50 global events
      });
    }
  }, []);

  useEffect(() => {
    if (!connected || !ws.current) return;

    ws.current.addEventListener('message', handleMessage);
    return () => ws.current?.removeEventListener('message', handleMessage);
  }, [ws, handleMessage, connected]);

  // The live feed is a journey diary. Low-level map transitions and every
  // battle-menu input remain available in JSONL, without flooding this view.
  const relevantEvents = events.filter(e => {
    if (e.type === 'battle_started' || e.type === 'battle_win') {
      return e.data?.battle === 'trainer' || e.data?.type === 'trainer';
    }
    return [
      'location_discovered', 'story_milestone', 'rare_encounter',
      'capture_decision', 'capture_outcome', 'capture', 'capture_attempt', 'starter_selected',
      'level_up', 'move_learned', 'training_target', 'evolution', 'badge', 'pc_deposit',
      'battle_loss', 'death', 'objective_changed',
    ].includes(e.type);
  });

  return (
    <div className="absolute bottom-4 right-4 w-80 max-h-80 bg-black/80 backdrop-blur-md border border-white/10 rounded-xl overflow-hidden flex flex-col shadow-2xl pointer-events-auto">
      <div className="p-3 border-b border-white/10 bg-white/5 flex items-center gap-2">
        <Scroll size={14} className="text-blue-400" />
        <span className="text-xs font-bold text-gray-200 uppercase tracking-wider">Diário da jornada</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
        {relevantEvents.length === 0 ? (
          <div className="text-xs text-gray-500 text-center py-4 italic">Aguardando um marco importante...</div>
        ) : (
          relevantEvents.map((e, i) => (
            <div key={i} className="flex gap-3 items-center p-2 rounded-lg bg-white/5 border border-white/5 hover:border-white/20 transition-colors animate-in slide-in-from-right-2 duration-300">
              <div className="shrink-0">
                {e.type === 'level_up' && <ArrowUpCircle size={20} className="text-green-400" />}
                {e.type === 'move_learned' && <Zap size={20} className="text-cyan-300" />}
                {e.type === 'pc_deposit' && <Archive size={20} className="text-blue-400" />}
                {e.type === 'battle_win' && <Zap size={20} className="text-orange-400" />}
                {e.type === 'battle_loss' && <Skull size={20} className="text-red-400" />}
                {e.type === 'battle_started' && <Swords size={20} className="text-red-300" />}
                {e.type === 'capture_decision' && (e.data.enemy_species_id || e.data.enemy_id) && (
                  <div className="relative h-9 w-9 rounded-lg bg-white/5">
                    <img
                      src={`https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/${e.data.enemy_species_id || e.data.enemy_id}.png`}
                      alt={`Pokémon #${e.data.enemy_species_id || e.data.enemy_id}`}
                      className="h-9 w-9 pixelated"
                    />
                    <Crosshair size={12} className={`absolute -bottom-1 -right-1 rounded-full bg-black ${e.data.choice === 'capture' ? 'text-yellow-300' : 'text-orange-300'}`} />
                  </div>
                )}
                {e.type === 'capture_attempt' && <Crosshair size={20} className="text-amber-300" />}
                {e.type === 'capture_outcome' && (
                  e.data.outcome === 'captured'
                    ? <Sparkles size={20} className="text-yellow-300" />
                    : e.data.outcome === 'defeated'
                      ? <Swords size={20} className="text-orange-300" />
                      : <Skull size={20} className="text-gray-400" />
                )}
                {e.type === 'starter_selected' && <Target size={20} className="text-green-300" />}
                {e.type === 'training_target' && <Target size={20} className="text-cyan-300" />}
                {e.type === 'location_discovered' && <MapPin size={20} className="text-emerald-300" />}
                {e.type === 'story_milestone' && <BookOpen size={20} className="text-blue-300" />}
                {e.type === 'rare_encounter' && <Sparkles size={20} className="text-fuchsia-300" />}
                {e.type === 'objective_changed' && <Crosshair size={20} className="text-yellow-300" />}
                {e.type === 'evolution' && <ArrowUpCircle size={20} className="text-fuchsia-300" />}
                {e.type === 'badge' && <Award size={20} className="text-yellow-300" />}
                {e.type === 'capture' && e.pokemon?.species_id ? (
                  <div className="relative">
                    <img
                      src={`https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/${e.pokemon.species_id}.png`}
                      alt="Pokemon"
                      className="w-8 h-8 pixelated"
                    />
                    <div className="absolute -bottom-1 -right-1 bg-yellow-500 text-black text-[8px] font-bold px-1 rounded-full">NEW</div>
                  </div>
                ) : e.type === 'capture' && (
                  <div className="w-8 h-8 rounded-full bg-red-500 border-2 border-white/20 flex items-center justify-center">
                    <div className="w-2 h-2 bg-white rounded-full" />
                  </div>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex justify-between items-baseline">
                  <div className="text-xs font-bold text-white truncate">{e.agent}</div>
                  <div className="text-[9px] text-gray-500">{new Date(e.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
                </div>
                <div className="text-[10px] text-gray-300 leading-tight mt-0.5">
                  {e.type === 'level_up' && (
                    <span className="text-green-300">
                      Leveled up to <span className="font-bold">Lv.{e.data.new_level}</span>!
                      {e.data.pokemon && <span className="text-gray-400"> (ID: {e.data.pokemon.species_id})</span>}
                    </span>
                  )}
                  {e.type === 'move_learned' && (
                    <span className="text-cyan-200">
                      Aprendeu o golpe <span className="font-bold">#{e.data.learned_move_id || '?'}</span>
                      {e.data.replaced_move_id && (
                        <span className="text-gray-400"> no lugar de #{e.data.replaced_move_id}</span>
                      )}
                      <div className="text-gray-500">Build: {(e.data.moves_after || []).map((id: number) => `#${id}`).join(' · ')}</div>
                    </span>
                  )}
                  {e.type === 'capture' && (
                    <>
                      Capturou <span className="text-yellow-300 font-bold">{e.pokemon?.species_id ? `#${e.pokemon.species_id}` : 'Pokémon'}</span>!
                      <div className="text-gray-500">{e.data.reason}</div>
                      <div className="text-gray-600">Pokédex: {e.data.count} · destino: {e.data.result === 'pc' ? 'PC' : 'time'}</div>
                      {e.data.shiny_candidate && <div className="font-bold text-fuchsia-300">Prioridade shiny confirmada</div>}
                    </>
                  )}
                  {e.type === 'starter_selected' && (
                    <span className="text-green-200">
                      Starter escolhido: <span className="font-bold">#{e.data.pokemon?.species_id || '?'}</span>
                    </span>
                  )}
                  {e.type === 'pc_deposit' && (
                    <span className="text-blue-300">
                      Deposited Pokemon in PC. <span className="text-gray-400">Party: {e.data.size}</span>
                    </span>
                  )}
                  {e.type === 'battle_win' && (
                    <span className="text-orange-300">
                      Won a battle! <span className="text-gray-400">XP Gained</span>
                    </span>
                  )}
                  {e.type === 'battle_started' && (
                    <span className="text-red-200">
                      {e.data.encounter_label || 'Batalha iniciada'} contra <span className="font-bold">#{e.data.enemy_species_id || e.data.enemy_id}</span>
                      <span className="text-gray-500"> · {e.data.map_name || e.data.battle}</span>
                    </span>
                  )}
                  {e.type === 'capture_decision' && (
                    <span className={e.data.choice === 'capture' ? 'text-yellow-200' : 'text-orange-200'}>
                      {e.data.choice === 'capture' ? 'Decidiu capturar' : 'Decidiu derrotar'}{' '}
                      <span className="font-bold">#{e.data.enemy_species_id || e.data.enemy_id}</span>
                      <div className="text-gray-400">{e.data.reason}</div>
                      <div className="text-gray-600">
                        motivo: {e.data.motivation || 'treino'} · Poké Balls: {e.data.pokeballs ?? 0}
                      </div>
                    </span>
                  )}
                  {e.type === 'capture_outcome' && (
                    <span className={e.data.outcome === 'captured' ? 'text-yellow-200' : 'text-gray-300'}>
                      {e.data.intent === 'capture' ? 'Quis capturar' : 'Quis derrotar'}{' '}
                      <span className="font-bold">#{e.data.enemy_species_id}</span>
                      {' → '}
                      <span className="font-bold">
                        {e.data.outcome === 'captured' && 'capturou'}
                        {e.data.outcome === 'defeated' && 'derrotou'}
                        {e.data.outcome === 'fled' && 'fugiu'}
                        {e.data.outcome === 'fainted' && 'desmaiou'}
                      </span>
                      <div className="text-gray-500">
                        bolas usadas: {e.data.balls_thrown ?? 0} · restam {e.data.pokeballs ?? 0}
                        {e.data.outcome === 'captured' && ` · time: ${e.data.party_size}`}
                      </div>
                    </span>
                  )}
                  {e.type === 'battle_loss' && (
                    <span className="text-red-300">Battle lost. <span className="text-gray-500">{e.data.reason}</span></span>
                  )}
                  {e.type === 'capture_attempt' && (
                    <span className="text-amber-200">
                      Capture attempt: <span className="font-bold">{e.data.result}</span>
                      <div className="text-gray-500">{e.data.reason}</div>
                    </span>
                  )}
                  {e.type === 'training_target' && (
                    <span className="text-cyan-200">
                      Training target: <span className="font-bold">#{e.data.active_pokemon?.species_id || '?'}</span>
                      <div className="text-gray-500">{e.data.reason}</div>
                    </span>
                  )}
                  {e.type === 'location_discovered' && (
                    <span className="text-emerald-200">
                      Primeira chegada a <span className="font-bold">{e.data.location_name}</span>
                      <div className="text-gray-500">{e.data.reason}</div>
                    </span>
                  )}
                  {e.type === 'story_milestone' && (
                    <span className="text-blue-200">
                      <span className="font-bold">{e.data.title}</span>
                      <div className="text-gray-400">{e.data.reason}</div>
                      {e.data.milestone === 'capture_unlocked' && (
                        <div className="font-bold text-yellow-300">Capturas disponíveis · {e.data.pokeballs} Poké Balls</div>
                      )}
                    </span>
                  )}
                  {e.type === 'rare_encounter' && (
                    <span className="text-fuchsia-200">
                      <span className="font-bold">Compatível com shiny: #{e.data.enemy_species_id || e.data.enemy_id}</span>
                      <div className="text-gray-400">{e.data.reason}</div>
                      {!e.data.capture_unlocked && <div className="text-red-300">Captura ainda bloqueada pela história ou sem Poké Balls</div>}
                    </span>
                  )}
                  {e.type === 'objective_changed' && (
                    <span className="text-yellow-200">
                      Objective changed to <span className="font-bold">{e.data.to}</span>
                    </span>
                  )}
                  {e.type === 'evolution' && (
                    <span className="text-fuchsia-200">
                      Evolution: <span className="font-bold">#{e.data.old_pokemon?.species_id}</span> → <span className="font-bold">#{e.data.new_pokemon?.species_id}</span>
                    </span>
                  )}
                  {e.type === 'badge' && (
                    <span className="text-yellow-200">Conquistou a insígnia #{e.data.count}</span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default EventFeed;
