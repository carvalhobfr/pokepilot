import { useState, useEffect, useRef } from 'react';

export const useAgentStream = (url: string) => {
  const [agents] = useState<any[]>([]);
  const [stats, setStats] = useState({ envs: 0, viewers: 0 });
  const [connected, setConnected] = useState(false);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    const connect = () => {
      ws.current = new WebSocket(url);

      ws.current.onopen = () => {
        setConnected(true);
      };

      ws.current.onmessage = async (event) => {
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
        
        if ("stats" in data) {
          setStats(data.stats);
        } else {
          // Agent Update
          // We receive { coords: [...], metadata: {...} }
          // We want to accumulate these or just pass them to the visualizer
          // For React state, we might want to keep a map of "active agents"
          
          // NOTE: This might fire VERY fast (60fps * 8 agents). 
          // Updating React state this fast will kill performance.
          // Better to use a Ref for the raw data and a throttled state update,
          // OR just pass the Ref to the Map component which uses Pixi's ticker.
          
          // For this hook, let's just dispatch a custom event or callback
          // But since we want to use it in App, let's try a throttled approach or just return the raw socket/callback mechanism.
        }
      };

      ws.current.onclose = () => {
        setConnected(false);
        setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      ws.current?.close();
    };
  }, [url]);

  return { agents, stats, ws, connected };
};
