import React, { useEffect, useState } from 'react';

type LLMMessage = {
  type: string;
  event: string;
  payload: any;
};

export const LLMPanel: React.FC = () => {
  const [messages, setMessages] = useState<LLMMessage[]>([]);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8765');
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        setMessages((prev) => [...prev, msg]);
      } catch (_) { }
    };
    ws.onclose = () => console.log('LLM WS closed');
    return () => ws.close();
  }, []);

  return (
    <div style={{ padding: '1rem', background: '#1e1e1e', color: '#fff', height: '100%', overflowY: 'auto' }}>
      <h3>🤖 LLM Log</h3>
      {messages.map((msg, i) => (
        <div key={i} style={{ marginBottom: '0.5rem' }}>
          {msg.event === 'llm_guide' && (
            <div style={{ color: '#ffdd57' }}>
              <strong>Guia LLM:</strong> {msg.payload.agent} – {msg.payload.stage}
            </div>
          )}
          {msg.event !== 'llm_guide' && (
            <div>
              <strong>{msg.event}</strong>: <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify(msg.payload, null, 2)}</pre>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};
