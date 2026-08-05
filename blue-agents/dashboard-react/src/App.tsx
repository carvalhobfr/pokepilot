import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import MapViz from './components/MapViz';
import AgentSidebar from './components/AgentSidebar';
import BattleArena from './components/BattleArena';
import EventFeed from './components/EventFeed';
import ControlPanel from './components/ControlPanel';
import BattleReplays from './components/BattleReplays';
import JourneyControls, { type RuntimeControls } from './components/JourneyControls';
import { useAgentStream } from './hooks/useAgentStream';
import { LayoutGrid, Swords, Film } from 'lucide-react';
import AIStrategyModal from './components/AIStrategyModal';

function App() {
  const [selectedAgent, setSelectedAgent] = useState<any | null>(null);
  const [showBattleArena, setShowBattleArena] = useState(false);
  const [showControlPanel, setShowControlPanel] = useState(false);
  const [showReplays, setShowReplays] = useState(false);
  const [allAgents, setAllAgents] = useState<Record<string, any>>({});
  const [runtimeControls, setRuntimeControls] = useState<RuntimeControls>({
    global: { paused: false, speed: 1 },
    agents: {},
  });
  const [aiModalData, setAiModalData] = useState<{ agentName: string; agentData: any; response: string | null; isLoading: boolean } | null>(null);

  const { stats, ws, connected } = useAgentStream("ws://localhost:3344/receive");
  const agentUpdateBatchRef = useRef<Record<string, any>>({});

  // Memoize agent click handler
  const handleAgentClick = useCallback((agent: any) => {
    setSelectedAgent(agent);
  }, []);

  const handleSaveAll = useCallback(() => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        type: 'command',
        action: 'save_all'
      }));
      alert('Save command sent to all agents!');
    } else {
      alert('WebSocket not connected.');
    }
  }, [ws]);

  const sendRuntimeControl = useCallback((command: Record<string, unknown>) => {
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) return false;
    ws.current.send(JSON.stringify({ type: 'control', ...command }));
    return true;
  }, [ws]);

  const handleToggleGlobal = useCallback(() => {
    sendRuntimeControl({
      scope: 'global',
      action: runtimeControls.global.paused ? 'play' : 'pause',
    });
  }, [runtimeControls.global.paused, sendRuntimeControl]);

  const handleSpeedChange = useCallback((speed: number) => {
    sendRuntimeControl({ scope: 'global', action: 'speed', value: speed });
  }, [sendRuntimeControl]);

  const handleToggleAgent = useCallback((agentName: string) => {
    const paused = Boolean(runtimeControls.agents[agentName]?.paused);
    sendRuntimeControl({
      scope: 'agent',
      agent: agentName,
      action: paused ? 'play' : 'pause',
    });
  }, [runtimeControls.agents, sendRuntimeControl]);

  const handleAskAI = useCallback(async (agentName: string, agentData: any) => {
    // Open modal in loading state
    setAiModalData({
      agentName,
      agentData,
      response: null,
      isLoading: true
    });

    try {
      const response = await fetch('http://localhost:5002/api/ask-ai', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          agent_name: agentName,
          agent_state: agentData
        })
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();

      // Update modal with response
      setAiModalData(prev => prev ? {
        ...prev,
        response: data.strategy,
        isLoading: false
      } : null);
    } catch (error) {
      console.error('Error calling AI API:', error);
      setAiModalData(prev => prev ? {
        ...prev,
        response: `❌ Failed to connect to AI server.\n\nMake sure the AI API server is running:\npython3 blue-agents/ai_api_server.py\n\nError: ${error}`,
        isLoading: false
      } : null);
    }
  }, []);

  const handleResetAgent = useCallback(async (agentName: string) => {
    try {
      const response = await fetch(`http://localhost:5002/api/reset-agent/${agentName}`, {
        method: 'POST'
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      console.log(`✅ Reset ${agentName}:`, data);
      alert(`🗑️ ${agentName} has been reset! They will start from scratch on next restart.`);
    } catch (error) {
      console.error('Error resetting agent:', error);
      alert(`❌ Failed to reset ${agentName}. Make sure the AI API server is running.`);
    }
  }, []);

  // Memoize agents array for ControlPanel
  const agentsArray = useMemo(() => Object.values(allAgents), [allAgents]);

  // Batch agent updates for better performance
  useEffect(() => {
    if (!connected || !ws.current) return;

    const handleMessage = async (event: MessageEvent) => {
      let data;

      // Handle Blob or ArrayBuffer data
      if (event.data instanceof Blob) {
        const text = await event.data.text();
        data = JSON.parse(text);
      } else if (typeof event.data === 'string') {
        data = JSON.parse(event.data);
      } else {
        console.error('Unknown WebSocket data type:', typeof event.data);
        return;
      }

      if (data.type === 'runtime_control_state' && data.controls) {
        setRuntimeControls(data.controls);
        return;
      }
      
      // Batch agent updates
      if (!data.stats && data.metadata) {
        const now = Date.now();
        agentUpdateBatchRef.current[data.metadata.user] = {
          ...data.metadata,
          last_seen: now
        };
      }
    };

    // Flush batched updates every 200ms for smoother updates
    const flushInterval = setInterval(() => {
      if (Object.keys(agentUpdateBatchRef.current).length > 0) {
        const completedBatch = agentUpdateBatchRef.current;
        agentUpdateBatchRef.current = {};
        setAllAgents(prev => ({
          ...prev,
          ...completedBatch
        }));
      }
    }, 200);

    ws.current.addEventListener('message', handleMessage);
    return () => {
      ws.current?.removeEventListener('message', handleMessage);
      clearInterval(flushInterval);
    };
  }, [connected, ws]);

  return (
    <div className="w-screen h-screen bg-black overflow-hidden relative font-sans selection:bg-blue-500/30">
      {/* Map Visualization */}
      <MapViz ws={ws} connected={connected} onAgentClick={handleAgentClick} />

      {/* UI Overlays */}
      <div className="absolute top-4 left-4 pointer-events-none select-none z-10">
        <h1 className="text-3xl font-black text-white drop-shadow-lg tracking-tighter italic">
          POKE<span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-cyan-300">AI</span> BLUE
        </h1>
        <div className="flex gap-3 mt-2 text-[10px] font-mono text-gray-400 bg-black/60 p-2 rounded-lg backdrop-blur-md border border-white/10 inline-flex pointer-events-auto">
          <span className="flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full bg-green-500" /> ENVS: <span className="text-white font-bold">{stats.envs}</span></span>
          <span className="flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full bg-blue-500" /> VIEWERS: <span className="text-white font-bold">{stats.viewers}</span></span>
          <span className="flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full bg-yellow-500" /> AGENTS: <span className="text-white font-bold">{agentsArray.length}</span></span>
        </div>
      </div>

      {/* Optional observers */}
      <div className="absolute top-4 right-4 z-10 flex gap-2">
        <button
          onClick={() => setShowBattleArena(prev => !prev)}
          title="Abrir arena de batalhas"
          className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/10 p-3 text-white backdrop-blur-md transition-all hover:scale-105 hover:bg-red-500/20 active:scale-95"
        >
          <Swords size={20} className={showBattleArena ? 'text-red-300' : 'text-slate-200'} />
          <span className="hidden text-[10px] font-bold uppercase tracking-wider sm:inline">Arena</span>
        </button>
        <button
          onClick={() => setShowReplays(true)}
          title="Rever as últimas batalhas"
          className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/10 p-3 text-white backdrop-blur-md transition-all hover:scale-105 hover:bg-fuchsia-500/20 active:scale-95"
        >
          <Film size={20} className={showReplays ? 'text-fuchsia-300' : 'text-slate-200'} />
          <span className="hidden text-[10px] font-bold uppercase tracking-wider sm:inline">Replays</span>
        </button>
        <button
          onClick={() => setShowControlPanel(true)}
          title="Abrir painel de agentes"
          className="rounded-xl border border-white/10 bg-white/10 p-3 text-white backdrop-blur-md transition-all hover:scale-105 hover:bg-white/20 active:scale-95 group"
        >
          <LayoutGrid size={20} className="group-hover:text-blue-400 transition-colors" />
        </button>
      </div>

      <JourneyControls
        connected={connected}
        agentCount={Math.max(stats.envs, agentsArray.length)}
        controls={runtimeControls}
        onToggleGlobal={handleToggleGlobal}
        onSpeedChange={handleSpeedChange}
      />

      {/* Event Feed */}
      <EventFeed ws={ws} connected={connected} />

      <BattleReplays
        ws={ws}
        connected={connected}
        open={showReplays}
        onClose={() => setShowReplays(false)}
      />

      {/* LLM Log Panel - Disabled temporarily (wrong ws://localhost:8765 port) */}
      {/*
      <div style={{ position: 'absolute', top: '80px', right: '20px', width: '300px', height: '400px', zIndex: 10, background: '#1e1e1e', borderRadius: '8px', overflow: 'hidden' }}>
        <LLMPanel />
      </div>
      */}

      {/* Sidebar */}
      {selectedAgent && (
        <AgentSidebar
          agent={selectedAgent}
          onClose={() => setSelectedAgent(null)}
        />
      )}

      {/* Optional battle observer. It never opens automatically. */}
      <BattleArena
        agents={allAgents}
        open={showBattleArena}
        onClose={() => setShowBattleArena(false)}
      />

      {/* Control Panel Modal */}
      {showControlPanel && (
        <ControlPanel
          agents={allAgents}
          onClose={() => setShowControlPanel(false)}
          onSaveAll={handleSaveAll}
          onAskAI={handleAskAI}
          onResetAgent={handleResetAgent}
          controls={runtimeControls}
          onToggleAgent={handleToggleAgent}
        />
      )}

      {/* AI Strategy Modal */}
      {aiModalData && (
        <AIStrategyModal
          agentName={aiModalData.agentName}
          agentData={aiModalData.agentData}
          response={aiModalData.response}
          isLoading={aiModalData.isLoading}
          onClose={() => setAiModalData(null)}
        />
      )}
    </div>
  );
}

export default App;
