import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import StatCard from './components/StatCard';
import LiveFeed from './components/LiveFeed';
import './index.css';

function App() {
  const [metrics, setMetrics] = useState({
    total_transactions: 0,
    fraud_transactions: 0,
    blocked_transactions: 0,
    total_volume: 0.0
  });

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/v1/metrics');
        if (res.ok) {
          const data = await res.json();
          setMetrics(data);
        }
      } catch (err) {
        console.error("Failed to fetch metrics", err);
      }
    };
    
    fetchMetrics();
    const intervalId = setInterval(fetchMetrics, 2000);
    return () => clearInterval(intervalId);
  }, []);
  return (
    <div className="dashboard-container">
      <Header />
      
      <div className="sidebar-left">
        <h2 className="text-xl mb-4 font-display text-gradient">Platform Metrics</h2>
        
        <StatCard 
          title="Total Transactions" 
          value={metrics.total_transactions.toLocaleString()} 
          change="Real-time" 
          trend="up"
          icon={
            <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
          }
        />
        
        <StatCard 
          title="Fraud Transactions" 
          value={metrics.fraud_transactions.toLocaleString()} 
          change="Detected" 
          trend="down"
          icon={
            <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          }
        />
        
        <StatCard 
          title="Fraud Detection Rate" 
          value={metrics.total_transactions > 0 ? ((metrics.fraud_transactions / metrics.total_transactions) * 100).toFixed(2) + '%' : '0.00%'} 
          change="Real-time" 
          trend="up"
          icon={
            <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          }
        />
        
        <StatCard 
          title="Total Volume Processed" 
          value={'$' + metrics.total_volume.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} 
          change="Total" 
          trend="up"
          icon={
            <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
          }
        />
      </div>
      
      <div className="main-content">
        <div className="glass-panel" style={{ flex: 1, padding: '24px', position: 'relative', overflow: 'hidden' }}>
          <h2 className="text-xl mb-4 font-display">Global Fraud Activity</h2>
          <div style={{ width: '100%', height: 'calc(100% - 40px)', background: 'radial-gradient(ellipse at center, rgba(30, 33, 43, 0) 0%, rgba(30, 33, 43, 0.8) 100%), url("https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=1472&auto=format&fit=crop") center/cover', borderRadius: '12px', position: 'relative' }}>
            <div className="live-dot" style={{ position: 'absolute', top: '30%', left: '40%', background: 'hsl(var(--accent-red))', boxShadow: '0 0 0 0 rgba(239, 68, 68, 0.4)' }}></div>
            <div className="live-dot" style={{ position: 'absolute', top: '60%', left: '70%', background: 'hsl(var(--accent-red))', boxShadow: '0 0 0 0 rgba(239, 68, 68, 0.4)', animationDelay: '0.5s' }}></div>
            <div className="live-dot" style={{ position: 'absolute', top: '45%', left: '20%', background: 'hsl(var(--accent-red))', boxShadow: '0 0 0 0 rgba(239, 68, 68, 0.4)', animationDelay: '1s' }}></div>
          </div>
          
          <div style={{ position: 'absolute', bottom: '40px', right: '40px', background: 'rgba(0,0,0,0.6)', padding: '16px', borderRadius: '12px', backdropFilter: 'blur(8px)' }}>
            <div className="text-sm text-muted mb-2">Active Threats</div>
            <div className="text-2xl font-bold text-gradient">3 Regions</div>
          </div>
        </div>
        
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', height: '240px' }}>
          <div className="glass-panel" style={{ padding: '24px' }}>
            <h3 className="text-sm text-muted mb-4 font-medium">Model Performance (XGBoost)</h3>
            <div className="flex items-center justify-center h-full pb-8">
               <svg viewBox="0 0 100 100" width="120" height="120">
                  <circle cx="50" cy="50" r="45" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="10"/>
                  <circle cx="50" cy="50" r="45" fill="none" stroke="hsl(var(--primary))" strokeWidth="10" strokeDasharray="283" strokeDashoffset="42" transform="rotate(-90 50 50)" style={{ transition: 'stroke-dashoffset 1s ease' }}/>
                  <text x="50" y="55" textAnchor="middle" fill="white" fontSize="20" fontWeight="bold">85%</text>
               </svg>
            </div>
          </div>
          <div className="glass-panel" style={{ padding: '24px' }}>
            <h3 className="text-sm text-muted mb-4 font-medium">Graph Analysis Cluster</h3>
            <div className="flex flex-col gap-4">
              <div className="flex justify-between items-center text-sm">
                <span>Neo4j Nodes</span>
                <span className="font-bold">14.2M</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span>Active Queries</span>
                <span className="font-bold">2,450/s</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span>Traversal Depth</span>
                <span className="font-bold">3 Hops</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <div className="sidebar-right">
        <LiveFeed />
      </div>
    </div>
  );
}

export default App;
