import React from 'react';
import './RiskBadge.css';

const RiskBadge = ({ score }) => {
  let riskLevel = 'low';
  let label = 'Low Risk';

  if (score >= 80) {
    riskLevel = 'high';
    label = 'High Risk';
  } else if (score >= 40) {
    riskLevel = 'medium';
    label = 'Medium';
  }

  return (
    <div className={`risk-badge ${riskLevel}`}>
      <span className="risk-dot"></span>
      {label}
    </div>
  );
};

export default RiskBadge;
