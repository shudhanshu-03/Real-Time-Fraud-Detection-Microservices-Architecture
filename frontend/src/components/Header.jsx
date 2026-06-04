import React from 'react';
import './Header.css';

const Header = () => {
  return (
    <header className="glass-panel topbar">
      <div className="flex items-center gap-4">
        <div className="logo-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="url(#gradient)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <defs>
              <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="hsl(252, 80%, 65%)" />
                <stop offset="100%" stopColor="hsl(190, 90%, 50%)" />
              </linearGradient>
            </defs>
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
        </div>
        <div>
          <h1 className="text-xl text-gradient">SentinelPlatform</h1>
          <span className="text-sm text-muted">Real-Time Fraud Detection</span>
        </div>
      </div>
      
      <div className="flex items-center gap-6">
        <div className="status-indicator">
          <span className="dot pulse-green"></span>
          <span className="text-sm font-medium">All Systems Operational</span>
        </div>
        <div className="user-profile">
          <img src="https://ui-avatars.com/api/?name=Admin+User&background=3b82f6&color=fff" alt="Admin" className="avatar" />
        </div>
      </div>
    </header>
  );
};

export default Header;
