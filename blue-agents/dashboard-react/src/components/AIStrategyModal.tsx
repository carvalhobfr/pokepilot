import React from 'react';
import { X, Sparkles, Loader2 } from 'lucide-react';

interface AIStrategyModalProps {
  agentName: string;
  agentData: any;
  response: string | null;
  isLoading: boolean;
  onClose: () => void;
}

const AIStrategyModal: React.FC<AIStrategyModalProps> = ({
  agentName,
  agentData,
  response,
  isLoading,
  onClose
}) => {
  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-md z-[200] flex items-center justify-center p-6 animate-in fade-in duration-200">
      <div className="bg-gradient-to-br from-gray-900 to-black border border-purple-500/30 rounded-2xl max-w-3xl w-full max-h-[80vh] overflow-hidden shadow-2xl shadow-purple-500/20">
        {/* Header */}
        <div className="p-6 border-b border-white/10 bg-gradient-to-r from-purple-900/20 to-blue-900/20">
          <div className="flex justify-between items-start">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <div className="p-2 bg-purple-500/20 rounded-lg border border-purple-400/30">
                  <Sparkles size={20} className="text-purple-400" />
                </div>
                <h2 className="text-2xl font-bold text-white">AI Strategy Assistant</h2>
              </div>
              <div className="text-sm text-gray-400">
                Analyzing <span className="text-purple-400 font-bold">{agentName}</span>'s current situation...
              </div>
              <div className="mt-2 flex gap-3 text-xs text-gray-500">
                <span>Map ID: <span className="text-white">{agentData.map_id}</span></span>
                <span>•</span>
                <span>Badges: <span className="text-yellow-400">{agentData.badges || 0}</span></span>
                <span>• </span>
                <span>Party: <span className="text-green-400">{agentData.party?.length || 0}/6</span></span>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-white/10 rounded-full transition-colors group"
            >
              <X size={20} className="text-gray-400 group-hover:text-white" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(80vh-180px)] custom-scrollbar">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Loader2 size={48} className="text-purple-400 animate-spin mb-4" />
              <p className="text-white font-medium">Consulting AI...</p>
              <p className="text-gray-500 text-sm mt-2">Analyzing game state and generating strategy...</p>
            </div>
          ) : response ? (
            <div className="prose prose-invert max-w-none">
              <div className="bg-white/5 border border-purple-500/20 rounded-xl p-6">
                <div className="whitespace-pre-wrap text-gray-300 leading-relaxed">
                  {response}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              No response yet. Click "Ask AI" to get started.
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/10 bg-black/40">
          <div className="flex justify-between items-center text-xs text-gray-500">
            <div>
              <span className="text-purple-400">💡 Tip:</span> AI recommendations are suggestions only
            </div>
            <div>
              Powered by GPT-4o-mini
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AIStrategyModal;
