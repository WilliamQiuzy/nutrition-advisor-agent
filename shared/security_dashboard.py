"""
Security Monitoring Dashboard for Healthcare AI System
Provides real-time visibility into security metrics and events
"""

import json
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from .integrated_security import IntegratedSecuritySystem, get_security_system

logger = logging.getLogger(__name__)


class SecurityDashboard:
    """Real-time security monitoring dashboard"""
    
    def __init__(self, security_system: Optional[IntegratedSecuritySystem] = None):
        self.security = security_system or get_security_system()
        self.app = FastAPI(title="Security Monitoring Dashboard")
        self.active_connections: List[WebSocket] = []
        
        # Setup routes
        self._setup_routes()
        
        # Start background metric collection
        self.metric_task = None
    
    def _setup_routes(self):
        """Setup dashboard routes"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard():
            """Serve the main dashboard HTML"""
            return self._get_dashboard_html()
        
        @self.app.get("/api/metrics/current")
        async def get_current_metrics():
            """Get current security metrics"""
            return JSONResponse(content=self.security.get_security_metrics())
        
        @self.app.get("/api/metrics/historical")
        async def get_historical_metrics(hours: int = 24):
            """Get historical metrics"""
            # This would typically query from time-series database
            return JSONResponse(content={
                "message": "Historical metrics would be retrieved from time-series DB",
                "hours_requested": hours
            })
        
        @self.app.get("/api/alerts/active")
        async def get_active_alerts():
            """Get active security alerts"""
            if hasattr(self.security, 'cost_monitor') and self.security.cost_monitor:
                budget_status = self.security.cost_monitor.get_budget_status()
                alerts = []
                
                # Check for budget alerts
                if budget_status["hourly"]["spent"] > budget_status["hourly"]["limit"] * 0.8:
                    alerts.append({
                        "id": "hourly_budget_warning",
                        "type": "cost",
                        "severity": "warning",
                        "message": f"Hourly budget at {(budget_status['hourly']['spent'] / budget_status['hourly']['limit'] * 100):.1f}%",
                        "timestamp": datetime.now().isoformat()
                    })
                
                return JSONResponse(content={"alerts": alerts})
            
            return JSONResponse(content={"alerts": []})
        
        @self.app.get("/api/events/recent")
        async def get_recent_events(limit: int = 100):
            """Get recent security events"""
            if hasattr(self.security, 'audit_logger') and self.security.audit_logger:
                events = await self.security.audit_logger.search_events(
                    start_time=datetime.now() - timedelta(hours=1),
                    end_time=datetime.now(),
                    limit=limit
                )
                return JSONResponse(content={"events": events})
            
            return JSONResponse(content={"events": []})
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket for real-time updates"""
            await websocket.accept()
            self.active_connections.append(websocket)
            
            try:
                # Send initial metrics
                metrics = self.security.get_security_metrics()
                await websocket.send_json({"type": "metrics", "data": metrics})
                
                # Keep connection alive and send updates
                while True:
                    # Wait for any message from client (heartbeat)
                    try:
                        await asyncio.wait_for(websocket.receive_text(), timeout=30)
                    except asyncio.TimeoutError:
                        # Send ping to keep connection alive
                        await websocket.send_json({"type": "ping"})
                    
            except WebSocketDisconnect:
                self.active_connections.remove(websocket)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if websocket in self.active_connections:
                    self.active_connections.remove(websocket)
    
    async def broadcast_metrics(self):
        """Broadcast metrics to all connected clients"""
        if not self.active_connections:
            return
        
        metrics = self.security.get_security_metrics()
        
        # Send to all connected clients
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json({"type": "metrics", "data": metrics})
            except:
                disconnected.append(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            self.active_connections.remove(conn)
    
    async def start_metric_collection(self, interval: int = 30):
        """Start background metric collection"""
        while True:
            await self.broadcast_metrics()
            await asyncio.sleep(interval)
    
    def _get_dashboard_html(self) -> str:
        """Generate dashboard HTML"""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>NutriRec AI Security Dashboard</title>
    <meta charset="utf-8">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
        }
        
        .header {
            background: #1a73e8;
            color: white;
            padding: 1rem 2rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        
        .metric-card {
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .metric-title {
            font-size: 0.875rem;
            color: #666;
            margin-bottom: 0.5rem;
        }
        
        .metric-value {
            font-size: 2rem;
            font-weight: 600;
            color: #1a73e8;
        }
        
        .metric-change {
            font-size: 0.875rem;
            margin-top: 0.5rem;
        }
        
        .metric-change.positive {
            color: #0f9d58;
        }
        
        .metric-change.negative {
            color: #ea4335;
        }
        
        .chart-container {
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }
        
        .alerts-container {
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .alert-item {
            padding: 1rem;
            border-radius: 4px;
            margin-bottom: 0.5rem;
        }
        
        .alert-warning {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
        }
        
        .alert-critical {
            background: #f8d7da;
            border-left: 4px solid #dc3545;
        }
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 0.5rem;
        }
        
        .status-healthy {
            background: #0f9d58;
        }
        
        .status-warning {
            background: #ffc107;
        }
        
        .status-critical {
            background: #ea4335;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🛡️ NutriRec AI Security Dashboard</h1>
        <p style="margin-top: 0.5rem; opacity: 0.9;">Real-time Security Monitoring</p>
    </div>
    
    <div class="container">
        <!-- System Status -->
        <div class="metric-card" style="margin-bottom: 2rem;">
            <h3>System Status</h3>
            <div style="margin-top: 1rem;">
                <span class="status-indicator status-healthy"></span>
                <span id="system-status">All Systems Operational</span>
            </div>
        </div>
        
        <!-- Key Metrics -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-title">Total Requests (24h)</div>
                <div class="metric-value" id="total-requests">0</div>
                <div class="metric-change positive">▲ 0%</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-title">Blocked Requests</div>
                <div class="metric-value" id="blocked-requests">0</div>
                <div class="metric-change negative">▲ 0%</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-title">Total Cost (USD)</div>
                <div class="metric-value" id="total-cost">$0.00</div>
                <div class="metric-change">Today</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-title">Active Threats</div>
                <div class="metric-value" id="active-threats">0</div>
                <div class="metric-change">Last Hour</div>
            </div>
        </div>
        
        <!-- Component Status -->
        <div class="chart-container">
            <h3>Security Components</h3>
            <div id="component-status" style="margin-top: 1rem;">
                <div style="padding: 0.5rem 0;">
                    <span class="status-indicator status-healthy"></span>
                    Rate Limiting: <strong>Active</strong>
                </div>
                <div style="padding: 0.5rem 0;">
                    <span class="status-indicator status-healthy"></span>
                    Cost Monitoring: <strong>Active</strong>
                </div>
                <div style="padding: 0.5rem 0;">
                    <span class="status-indicator status-healthy"></span>
                    Audit Logging: <strong>Active</strong>
                </div>
                <div style="padding: 0.5rem 0;">
                    <span class="status-indicator status-healthy"></span>
                    Content Filtering: <strong>Active</strong>
                </div>
                <div style="padding: 0.5rem 0;">
                    <span class="status-indicator status-healthy"></span>
                    Agent Isolation: <strong>Active</strong>
                </div>
                <div style="padding: 0.5rem 0;">
                    <span class="status-indicator status-healthy"></span>
                    Response Validation: <strong>Active</strong>
                </div>
            </div>
        </div>
        
        <!-- Active Alerts -->
        <div class="alerts-container">
            <h3>Active Alerts</h3>
            <div id="alerts-list" style="margin-top: 1rem;">
                <p style="color: #666;">No active alerts</p>
            </div>
        </div>
    </div>
    
    <script>
        // WebSocket connection
        let ws = null;
        
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            
            ws.onopen = () => {
                console.log('Connected to dashboard');
                updateStatus('Connected', 'healthy');
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'metrics') {
                    updateMetrics(data.data);
                }
            };
            
            ws.onclose = () => {
                console.log('Disconnected from dashboard');
                updateStatus('Disconnected', 'critical');
                // Reconnect after 5 seconds
                setTimeout(connectWebSocket, 5000);
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }
        
        function updateStatus(message, level) {
            const statusEl = document.getElementById('system-status');
            const indicatorEl = statusEl.previousElementSibling;
            
            statusEl.textContent = message;
            indicatorEl.className = `status-indicator status-${level}`;
        }
        
        function updateMetrics(metrics) {
            // Update system metrics
            if (metrics.system) {
                document.getElementById('total-requests').textContent = 
                    metrics.system.requests_processed || 0;
                document.getElementById('blocked-requests').textContent = 
                    metrics.system.requests_blocked || 0;
                document.getElementById('total-cost').textContent = 
                    `$${(metrics.system.total_cost || 0).toFixed(2)}`;
                document.getElementById('active-threats').textContent = 
                    metrics.system.security_events || 0;
            }
            
            // Update component status
            if (metrics.components) {
                updateComponentStatus(metrics.components);
            }
        }
        
        function updateComponentStatus(components) {
            const statusHtml = Object.entries(components).map(([name, data]) => {
                const isActive = data && Object.keys(data).length > 0;
                const status = isActive ? 'healthy' : 'warning';
                const displayName = name.replace(/_/g, ' ')
                    .replace(/\b\w/g, l => l.toUpperCase());
                
                return `
                    <div style="padding: 0.5rem 0;">
                        <span class="status-indicator status-${status}"></span>
                        ${displayName}: <strong>${isActive ? 'Active' : 'Inactive'}</strong>
                    </div>
                `;
            }).join('');
            
            document.getElementById('component-status').innerHTML = 
                '<h3>Security Components</h3><div style="margin-top: 1rem;">' + 
                statusHtml + '</div>';
        }
        
        // Fetch alerts periodically
        async function fetchAlerts() {
            try {
                const response = await fetch('/api/alerts/active');
                const data = await response.json();
                updateAlerts(data.alerts);
            } catch (error) {
                console.error('Failed to fetch alerts:', error);
            }
        }
        
        function updateAlerts(alerts) {
            const alertsList = document.getElementById('alerts-list');
            
            if (!alerts || alerts.length === 0) {
                alertsList.innerHTML = '<p style="color: #666;">No active alerts</p>';
                return;
            }
            
            const alertsHtml = alerts.map(alert => `
                <div class="alert-item alert-${alert.severity}">
                    <strong>${alert.type.toUpperCase()}</strong>: ${alert.message}
                    <div style="font-size: 0.875rem; margin-top: 0.25rem; opacity: 0.8;">
                        ${new Date(alert.timestamp).toLocaleString()}
                    </div>
                </div>
            `).join('');
            
            alertsList.innerHTML = alertsHtml;
        }
        
        // Initialize
        connectWebSocket();
        fetchAlerts();
        setInterval(fetchAlerts, 30000); // Refresh alerts every 30 seconds
    </script>
</body>
</html>
"""


def create_dashboard_app(security_system: Optional[IntegratedSecuritySystem] = None) -> FastAPI:
    """Create dashboard FastAPI app"""
    dashboard = SecurityDashboard(security_system)
    
    # Start background tasks
    @dashboard.app.on_event("startup")
    async def startup_event():
        dashboard.metric_task = asyncio.create_task(
            dashboard.start_metric_collection()
        )
    
    @dashboard.app.on_event("shutdown")
    async def shutdown_event():
        if dashboard.metric_task:
            dashboard.metric_task.cancel()
    
    return dashboard.app


# Standalone dashboard runner
if __name__ == "__main__":
    # Create and run dashboard
    app = create_dashboard_app()
    uvicorn.run(app, host="0.0.0.0", port=9090)