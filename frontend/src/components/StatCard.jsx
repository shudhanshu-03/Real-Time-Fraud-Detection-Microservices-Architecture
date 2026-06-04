import React from 'react';
import './StatCard.css';

const StatCard = ({ title, value, change, trend = 'up', icon }) => {
  const isPositive = trend === 'up';
  
  return (
    <div className="glass-panel stat-card">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-muted text-sm font-medium">{title}</h3>
        <div className="stat-icon">{icon}</div>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-2xl font-bold">{value}</div>
        {change && (
          <div className={`change-badge ${isPositive ? 'positive' : 'negative'}`}>
            {isPositive ? '↑' : '↓'} {change}
          </div>
        )}
      </div>
      <div className="stat-glow"></div>
    </div>
  );
};

export default StatCard;
