/**
 * Dashboard Application Logic
 */

class DashboardApp {
    constructor() {
        this.demoMode = false;
        this.maxTxnRows = 50;
        this.maxAlertRows = 20;
        
        // State
        this.kpiValues = {
            total: 1245000,
            fraud: 4200,
            alerts: 125,
            latency: 42
        };
        
        this.sparklineData = {
            total: Array(20).fill(100),
            fraud: Array(20).fill(5),
            latency: Array(20).fill(40)
        };
        
        // DOM Elements
        this.els = {
            clock: document.getElementById('clock'),
            connStatus: document.getElementById('connection-status'),
            connText: document.getElementById('connection-text'),
            feed: document.getElementById('transaction-feed'),
            timeline: document.getElementById('alert-timeline'),
            heatmap: document.getElementById('velocity-heatmap'),
            health: document.getElementById('health-grid'),
            kpi: {
                total: document.getElementById('val-total-txn'),
                fraud: document.getElementById('val-fraud'),
                fraudRate: document.getElementById('val-fraud-rate'),
                alerts: document.getElementById('val-alerts'),
                latency: document.getElementById('val-latency'),
                p99: document.getElementById('val-p99')
            }
        };

        this.init();
    }

    init() {
        this.startClock();
        this.initCharts();
        this.initHeatmap();
        this.initHealth();
        
        // Try connecting to SSE
        this.connectSSE();
    }

    startClock() {
        setInterval(() => {
            const now = new Date();
            this.els.clock.textContent = now.toISOString().split('T')[1].split('.')[0] + ' UTC';
        }, 1000);
    }
    
    animateValue(element, start, end, duration = 1000) {
        if (start === end) return;
        const range = end - start;
        let current = start;
        const increment = end > start ? 1 : -1;
        const stepTime = Math.abs(Math.floor(duration / range));
        
        const obj = element;
        const timer = setInterval(() => {
            current += increment;
            obj.innerHTML = current.toLocaleString();
            if (current == end) {
                clearInterval(timer);
            }
        }, Math.max(10, stepTime));
    }

    updateKPIs(newData) {
        if (newData.total) {
            this.animateValue(this.els.kpi.total, this.kpiValues.total, newData.total);
            this.kpiValues.total = newData.total;
        }
        if (newData.fraud) {
            this.animateValue(this.els.kpi.fraud, this.kpiValues.fraud, newData.fraud);
            this.kpiValues.fraud = newData.fraud;
        }
        if (newData.alerts) {
            this.animateValue(this.els.kpi.alerts, this.kpiValues.alerts, newData.alerts);
            this.kpiValues.alerts = newData.alerts;
        }
        if (newData.latency) {
            this.animateValue(this.els.kpi.latency, this.kpiValues.latency, newData.latency);
            this.kpiValues.latency = newData.latency;
            this.els.kpi.p99.textContent = (newData.latency * 1.5).toFixed(0);
        }
        
        const rate = ((this.kpiValues.fraud / this.kpiValues.total) * 100).toFixed(2);
        this.els.kpi.fraudRate.textContent = rate + '%';
    }

    addTransaction(txn) {
        const tr = document.createElement('tr');
        tr.className = 'new-row';
        
        const time = new Date().toISOString().split('T')[1].substring(0, 8);
        const score = parseFloat(txn.risk_score).toFixed(2);
        
        let statusClass = 'approve';
        let statusText = 'Approve';
        if (score > 0.85) { statusClass = 'block'; statusText = 'Block'; }
        else if (score > 0.6) { statusClass = 'decline'; statusText = 'Decline'; }
        else if (score > 0.3) { statusClass = 'review'; statusText = 'Review'; }
        
        // Risk bar color
        let barColor = '#10b981';
        if (score > 0.8) barColor = '#ef4444';
        else if (score > 0.4) barColor = '#f59e0b';
        
        tr.innerHTML = `
            <td class="font-mono">${time}</td>
            <td class="font-mono">${txn.id.substring(0, 8)}</td>
            <td>${txn.customer_id.substring(0, 8)}</td>
            <td class="font-mono">$${parseFloat(txn.amount).toFixed(2)}</td>
            <td>${txn.merchant}</td>
            <td>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span class="font-mono">${score}</span>
                    <div class="risk-bar-container">
                        <div class="risk-bar" style="width: ${score * 100}%; background-color: ${barColor}"></div>
                    </div>
                </div>
            </td>
            <td><span class="status ${statusClass}">${statusText}</span></td>
        `;
        
        this.els.feed.prepend(tr);
        
        if (this.els.feed.children.length > this.maxTxnRows) {
            this.els.feed.removeChild(this.els.feed.lastChild);
        }
        
        // Update Sparklines occasionally
        if (Math.random() > 0.5) {
            this.sparklineData.total.shift();
            this.sparklineData.total.push(100 + Math.random() * 20);
            this.drawSparkline('sparkline-total', this.sparklineData.total, '#00d4ff');
        }
    }

    addAlert(alert) {
        const div = document.createElement('div');
        div.className = 'timeline-item';
        
        let dotClass = 'dot-low';
        if (alert.severity === 'CRITICAL') dotClass = 'dot-critical';
        else if (alert.severity === 'HIGH') dotClass = 'dot-high';
        else if (alert.severity === 'MEDIUM') dotClass = 'dot-medium';
        
        const time = new Date().toISOString().split('T')[1].substring(0, 5);
        
        div.innerHTML = `
            <div class="timeline-dot ${dotClass}"></div>
            <div class="timeline-content">
                <div class="timeline-time">${time}</div>
                <div class="timeline-title">${alert.title}</div>
                <div class="timeline-desc">${alert.desc}</div>
            </div>
        `;
        
        this.els.timeline.prepend(div);
        
        if (this.els.timeline.children.length > this.maxAlertRows) {
            this.els.timeline.removeChild(this.els.timeline.lastChild);
        }
    }

    initCharts() {
        const canvas = document.getElementById('score-chart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight;
        
        // Draw static histogram for now
        const buckets = [120, 80, 45, 20, 10, 8, 15, 25, 40, 75];
        const max = Math.max(...buckets);
        
        const w = canvas.width;
        const h = canvas.height;
        const padding = 30;
        const barWidth = (w - padding * 2) / 10 - 4;
        
        ctx.clearRect(0, 0, w, h);
        
        // Gradient
        const grad = ctx.createLinearGradient(0, h, w, 0);
        grad.addColorStop(0, '#10b981');
        grad.addColorStop(0.5, '#f59e0b');
        grad.addColorStop(1, '#ef4444');
        
        buckets.forEach((val, i) => {
            const barH = (val / max) * (h - padding * 2);
            const x = padding + i * (barWidth + 4);
            const y = h - padding - barH;
            
            ctx.fillStyle = grad;
            ctx.fillRect(x, y, barWidth, barH);
            
            // Label
            ctx.fillStyle = '#94a3b8';
            ctx.font = '10px Inter';
            ctx.fillText(`0.${i}`, x + 5, h - 10);
        });
        
        // Draw sparklines
        this.drawSparkline('sparkline-total', this.sparklineData.total, '#00d4ff');
        this.drawSparkline('sparkline-fraud', this.sparklineData.fraud, '#ef4444');
        this.drawSparkline('sparkline-latency', this.sparklineData.latency, '#7c3aed');
    }
    
    drawSparkline(id, data, color) {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        const w = canvas.width = canvas.parentElement.clientWidth;
        const h = canvas.height = canvas.parentElement.clientHeight;
        
        ctx.clearRect(0, 0, w, h);
        
        const max = Math.max(...data);
        const min = Math.min(...data);
        const range = max - min || 1;
        
        ctx.beginPath();
        data.forEach((val, i) => {
            const x = (i / (data.length - 1)) * w;
            const y = h - ((val - min) / range) * (h - 10) - 5;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();
        
        // Fill
        ctx.lineTo(w, h);
        ctx.lineTo(0, h);
        const grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, color + '40'); // 25% opacity
        grad.addColorStop(1, color + '00'); // 0% opacity
        ctx.fillStyle = grad;
        ctx.fill();
    }

    initHeatmap() {
        const rows = ['Cust', 'Card', 'IP', 'Device'];
        const cols = ['1m', '5m', '1h', '24h'];
        
        this.els.heatmap.innerHTML = '';
        
        // Empty top-left
        this.els.heatmap.appendChild(document.createElement('div'));
        
        // Headers
        cols.forEach(c => {
            const d = document.createElement('div');
            d.className = 'hm-header';
            d.textContent = c;
            this.els.heatmap.appendChild(d);
        });
        
        // Grid
        rows.forEach((r, i) => {
            const label = document.createElement('div');
            label.className = 'hm-label';
            label.textContent = r;
            this.els.heatmap.appendChild(label);
            
            cols.forEach((c, j) => {
                const cell = document.createElement('div');
                cell.className = 'hm-cell';
                cell.id = `hm-${i}-${j}`;
                this.els.heatmap.appendChild(cell);
            });
        });
        
        // Randomize initial heatmap
        this.updateHeatmap();
        setInterval(() => this.updateHeatmap(), 5000);
    }
    
    updateHeatmap() {
        for(let i=0; i<4; i++) {
            for(let j=0; j<4; j++) {
                const cell = document.getElementById(`hm-${i}-${j}`);
                if (cell) {
                    const val = Math.random();
                    let color = 'rgba(255,255,255,0.05)';
                    if (val > 0.9) color = 'rgba(239, 68, 68, 0.8)'; // Red
                    else if (val > 0.7) color = 'rgba(245, 158, 11, 0.6)'; // Amber
                    else if (val > 0.4) color = 'rgba(16, 185, 129, 0.4)'; // Green
                    cell.style.backgroundColor = color;
                }
            }
        }
    }

    initHealth() {
        const services = ['API Gateway', 'Txn Service', 'Orchestrator', 'Stream Proc', 'Notification'];
        this.els.health.innerHTML = '';
        
        services.forEach(s => {
            const card = document.createElement('div');
            card.className = 'health-card up';
            card.innerHTML = `
                <div class="dot"></div>
                <div>
                    <div class="health-name">${s}</div>
                    <div class="health-uptime">Uptime: 99.9%</div>
                </div>
            `;
            this.els.health.appendChild(card);
        });
    }

    connectSSE() {
        // Simulating SSE for this implementation
        this.startDemoMode();
    }
    
    startDemoMode() {
        this.demoMode = true;
        this.els.connStatus.style.backgroundColor = 'var(--accent-amber)';
        this.els.connStatus.style.boxShadow = 'none';
        this.els.connText.textContent = 'Demo Mode (Simulated)';
        
        const merchants = ['Amazon', 'Walmart', 'Apple Store', 'Steam', 'Starbucks', 'Uber', 'Target'];
        
        // Transaction simulator
        setInterval(() => {
            if (Math.random() > 0.3) {
                const isFraud = Math.random() > 0.95;
                this.addTransaction({
                    id: Math.random().toString(36).substring(2),
                    customer_id: 'CUST_' + Math.floor(Math.random() * 10000),
                    amount: (Math.random() * (isFraud ? 5000 : 500)).toFixed(2),
                    merchant: merchants[Math.floor(Math.random() * merchants.length)],
                    risk_score: isFraud ? (0.7 + Math.random() * 0.3).toFixed(2) : (Math.random() * 0.3).toFixed(2)
                });
                
                this.updateKPIs({
                    total: this.kpiValues.total + 1,
                    fraud: isFraud ? this.kpiValues.fraud + 1 : this.kpiValues.fraud,
                    latency: 35 + Math.floor(Math.random() * 20)
                });
            }
        }, 1500);
        
        // Alert simulator
        setInterval(() => {
            if (Math.random() > 0.7) {
                const isCritical = Math.random() > 0.8;
                const severities = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
                const sev = isCritical ? 'CRITICAL' : severities[Math.floor(Math.random() * 3)];
                
                const titles = {
                    'CRITICAL': 'Velocity Threshold Breach',
                    'HIGH': 'ML Model High Risk',
                    'MEDIUM': 'New Device Login',
                    'LOW': 'Profile Updated'
                };
                
                this.addAlert({
                    severity: sev,
                    title: titles[sev],
                    desc: 'Detected unusual activity pattern for customer CUST_' + Math.floor(Math.random() * 1000)
                });
                
                if (isCritical || sev === 'HIGH') {
                    this.updateKPIs({ alerts: this.kpiValues.alerts + 1 });
                }
            }
        }, 8000);
    }
}

// Start app
window.onload = () => {
    window.app = new DashboardApp();
    
    // Handle window resize for charts
    window.addEventListener('resize', () => {
        window.app.initCharts();
    });
};
