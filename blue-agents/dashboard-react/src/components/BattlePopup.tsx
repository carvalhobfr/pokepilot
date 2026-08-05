import React from 'react';
import { X, Swords } from 'lucide-react';

interface BattlePopupProps {
  battleInfo: any;
  agentName: string;
  onClose: () => void;
}

const BattlePopup: React.FC<BattlePopupProps> = ({ battleInfo, agentName, onClose }) => {
  if (!battleInfo || !battleInfo.is_battle) return null;

  const enemyHp = Number(battleInfo.enemy_hp || 0);
  const enemyMaxHp = Math.max(Number(battleInfo.enemy_max_hp || 1), 1);
  const hpPercent = Math.max(0, Math.min(100, (enemyHp / enemyMaxHp) * 100));
  const party = Array.isArray(battleInfo.party) ? battleInfo.party : [];
  let barColor = '#2ecc71'; // Green
  if (hpPercent < 50) barColor = '#f1c40f'; // Yellow
  if (hpPercent < 20) barColor = '#e74c3c'; // Red

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-[180] flex items-center justify-center p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-xl bg-gradient-to-br from-gray-950 via-black to-red-950/30 border border-red-500/40 rounded-2xl shadow-[0_0_60px_rgba(239,68,68,0.25)] text-white overflow-hidden">
        <div className="bg-red-900/30 p-4 border-b border-red-500/20 flex justify-between items-center">
          <div>
            <span className="font-bold text-red-300 text-sm tracking-wider flex items-center gap-2">
              <Swords size={18} /> BATALHA EM ANDAMENTO
            </span>
            <span className="text-xs text-gray-400">Agente {agentName}</span>
          </div>
          <button
            onClick={onClose}
            aria-label="Fechar batalha"
            className="p-2 rounded-lg hover:bg-white/10 transition-colors"
          >
            <X size={18} className="text-gray-400 hover:text-white" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-xl bg-red-500/10 border border-red-500/20 p-4">
              <div className="text-[10px] uppercase tracking-wider text-red-300/70">Oponente</div>
              <div className="text-xl font-bold mt-1">Pokémon #{battleInfo.enemy_id ?? '?'}</div>
              <div className="text-sm text-yellow-300 font-mono mt-1">Lv.{battleInfo.enemy_level ?? '?'}</div>
              <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden border border-white/10 mt-4">
                <div
                  className="h-full transition-all duration-500 ease-out"
                  style={{ width: `${hpPercent}%`, backgroundColor: barColor }}
                />
              </div>
              <div className="text-right text-xs font-mono text-gray-400 mt-1">
                {enemyHp} / {enemyMaxHp} HP
              </div>
            </div>

            <div className="rounded-xl bg-blue-500/10 border border-blue-500/20 p-4">
              <div className="text-[10px] uppercase tracking-wider text-blue-300/70">Time de {agentName}</div>
              <div className="space-y-2 mt-3">
                {party.length > 0 ? party.map((pokemon: any, index: number) => {
                  const hp = Number(pokemon.hp || 0);
                  const maxHp = Math.max(Number(pokemon.max_hp || 1), 1);
                  return (
                    <div key={`${pokemon.species_id}-${index}`} className="flex items-center gap-2 text-xs">
                      <span className="w-5 h-5 rounded-full bg-blue-500/20 border border-blue-400/30 flex items-center justify-center text-[9px]">{index + 1}</span>
                      <span className="flex-1">#{pokemon.species_id ?? '?'}</span>
                      <span className="text-yellow-300">Lv.{pokemon.level ?? '?'}</span>
                      <span className="text-gray-400 font-mono">{hp}/{maxHp}</span>
                    </div>
                  );
                }) : (
                  <div className="text-xs text-gray-500 italic">Time ainda não disponível</div>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between text-xs text-gray-500 border-t border-white/10 pt-4">
            <span>Dados lidos diretamente do emulador local</span>
            <span className="text-red-300 animate-pulse">● AO VIVO</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BattlePopup;
