import React, { useState, useEffect } from 'react';
import RiskBadge from './RiskBadge';
import './LiveFeed.css';

const LiveFeed = () => {
  const [transactions, setTransactions] = useState([]);
  const [status, setStatus] = useState('Connecting...');
  
  useEffect(() => {
    let ws;
    
    const connect = () => {
      ws = new WebSocket('ws://localhost:8000/api/v1/ws/live-feed');
      
      ws.onopen = () => {
        setStatus('Listening...');
      };
      
      ws.onmessage = (event) => {
        try {
          const newTx = JSON.parse(event.data);
          
          setTransactions((prev) => {
            // Keep last 15 items
            const updated = [newTx, ...prev];
            return updated.slice(0, 15);
          });
        } catch (err) {
          console.error("Failed to parse websocket message", err);
        }
      };
      
      ws.onclose = () => {
        setStatus('Disconnected. Reconnecting...');
        setTimeout(connect, 3000);
      };
      
      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
        ws.close();
      };
    };
    
    connect();
    
    return () => {
      if (ws) ws.close();
    };
  }, []);

  return (
    <div className="glass-panel feed-container">
      <div className="feed-header">
        <h2 className="text-lg font-medium">Live Transaction Feed</h2>
        <div className="pulse-indicator">
          <span className={`live-dot ${status === 'Listening...' ? '' : 'offline'}`}></span>
          <span className="text-sm text-muted">{status}</span>
        </div>
      </div>
      
      <div className="feed-list">
        {transactions.length === 0 && (
          <div className="text-center text-muted p-4">Waiting for transactions...</div>
        )}
        
        {transactions.map((tx, idx) => (
          <div key={tx.transaction_id || idx} className="feed-item" style={{ animationDelay: `${idx * 0.05}s` }}>
            <div className="tx-details">
              <div className="tx-icon">
                {tx.type === 'CREDIT' ? '↓' : '↑'}
              </div>
              <div>
                <div className="font-medium">{tx.merchant_name || 'Unknown'}</div>
                <div className="text-sm text-muted">{tx.type} • {new Date(tx.timestamp).toLocaleTimeString()}</div>
              </div>
            </div>
            
            <div className="tx-meta">
              <div className="font-bold">${tx.amount?.toFixed(2)}</div>
              <RiskBadge score={tx.final_score} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default LiveFeed;
