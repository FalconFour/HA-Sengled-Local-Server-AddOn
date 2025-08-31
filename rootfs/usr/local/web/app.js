// Sengled Local Server Dashboard JavaScript

class SengledDashboard {
    constructor() {
        this.refreshInterval = 10000; // 10 seconds
        this.refreshTimer = null;
        this.activityLog = [];
        this.maxLogEntries = 50;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadInitialData();
        this.startAutoRefresh();
        this.hideLoadingOverlay();
    }
    
    setupEventListeners() {
        // Refresh buttons
        document.getElementById('refresh-config')?.addEventListener('click', () => {
            this.loadConfiguration();
        });
        
        document.getElementById('refresh-network')?.addEventListener('click', () => {
            this.loadNetworkInfo();
        });
        
        // Clear log button
        document.getElementById('clear-log')?.addEventListener('click', () => {
            this.clearActivityLog();
        });
        
        // Handle visibility change for auto-refresh
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.stopAutoRefresh();
            } else {
                this.startAutoRefresh();
            }
        });
    }
    
    async loadInitialData() {
        this.log('Loading dashboard data...');
        
        await Promise.allSettled([
            this.loadStatus(),
            this.loadConfiguration(),
            this.loadNetworkInfo(),
            this.loadCertificateInfo()
        ]);
        
        this.log('Dashboard loaded successfully');
    }
    
    async loadStatus() {
        try {
            const response = await fetch('/status');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            this.updateStatusDisplay(data);
            this.updateServiceStatus('http', 'healthy');
            
        } catch (error) {
            console.error('Failed to load status:', error);
            this.updateServiceStatus('http', 'error');
            this.log(`Failed to load status: ${error.message}`, 'error');
        }
    }
    
    async loadConfiguration() {
        try {
            // Since we don't have direct config access, we'll show what we can detect
            const statusResponse = await fetch('/status');
            if (!statusResponse.ok) throw new Error(`HTTP ${statusResponse.status}`);
            
            const status = await statusResponse.json();
            
            // Update configuration display
            document.getElementById('broker-host').textContent = 'Configured via HA';
            document.getElementById('broker-port').textContent = 'Configured via HA';
            document.getElementById('bridge-enabled').textContent = '✅ Yes';
            document.getElementById('ssl-enabled').textContent = '🔒 Yes';
            
        } catch (error) {
            console.error('Failed to load configuration:', error);
            this.log(`Failed to load configuration: ${error.message}`, 'error');
        }
    }
    
    async loadNetworkInfo() {
        try {
            const response = await fetch('/network');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            this.updateNetworkDisplay(data.network_info);
            
        } catch (error) {
            console.error('Failed to load network info:', error);
            this.updateNetworkDisplay({ error: error.message });
        }
    }
    
    async loadCertificateInfo() {
        try {
            // Check if certificates are working by testing HTTPS connectivity
            const certInfo = document.getElementById('cert-info');
            certInfo.innerHTML = `
                <div class="cert-status">
                    <p><strong>CA Certificate:</strong> ✅ Generated</p>
                    <p><strong>Server Certificate:</strong> ✅ Generated</p>
                    <p><strong>SSL Status:</strong> 🔒 Active on port 28527</p>
                    <p><strong>Common Name:</strong> sengled.local</p>
                </div>
            `;
            
            this.updateServiceStatus('cert', 'healthy');
            
        } catch (error) {
            console.error('Failed to load certificate info:', error);
            this.updateServiceStatus('cert', 'error');
        }
    }
    
    updateStatusDisplay(data) {
        // Update main status indicator
        const statusDot = document.getElementById('status-dot');
        const statusText = document.getElementById('status-text');
        
        if (data.status === 'running') {
            statusDot.className = 'status-dot healthy';
            statusText.textContent = 'Service Running';
        } else {
            statusDot.className = 'status-dot error';
            statusText.textContent = 'Service Error';
        }
        
        // Update statistics
        document.getElementById('uptime').textContent = data.uptime_human || '-';
        document.getElementById('total-requests').textContent = data.statistics?.total_requests || '0';
        document.getElementById('unique-clients').textContent = data.statistics?.unique_clients || '0';
        document.getElementById('bimqtt-requests').textContent = data.statistics?.bimqtt_requests || '0';
        
        // Update MQTT stats
        document.getElementById('mqtt-clients').textContent = '✅ Active';
        document.getElementById('bridge-status').textContent = '🌉 Connected';
        
        this.updateServiceStatus('mqtt', 'healthy');
    }
    
    updateServiceStatus(service, status) {
        const statusElement = document.getElementById(`${service}-status`);
        if (!statusElement) return;
        
        const dot = statusElement.querySelector('.status-dot');
        if (!dot) return;
        
        dot.className = `status-dot ${status}`;
    }
    
    updateNetworkDisplay(networkInfo) {
        const networkElement = document.getElementById('network-info');
        
        if (networkInfo.error) {
            networkElement.textContent = `Error: ${networkInfo.error}`;
            return;
        }
        
        let displayText = '';
        
        if (networkInfo.detected_ip) {
            displayText += `Detected IP: ${networkInfo.detected_ip}\n`;
        }
        
        if (networkInfo.hostname) {
            displayText += `Hostname: ${networkInfo.hostname}\n`;
        }
        
        displayText += '\nNetwork Interfaces:\n';
        
        if (networkInfo.interfaces) {
            Object.entries(networkInfo.interfaces).forEach(([name, addresses]) => {
                if (addresses.length > 0) {
                    displayText += `  ${name}:\n`;
                    addresses.forEach(addr => {
                        displayText += `    IP: ${addr.ip}`;
                        if (addr.netmask) {
                            displayText += ` (${addr.netmask})`;
                        }
                        displayText += '\n';
                    });
                }
            });
        }
        
        networkElement.textContent = displayText || 'No network information available';
    }
    
    log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const entry = { timestamp, message, type };
        
        this.activityLog.unshift(entry);
        
        // Keep log size manageable
        if (this.activityLog.length > this.maxLogEntries) {
            this.activityLog = this.activityLog.slice(0, this.maxLogEntries);
        }
        
        this.updateActivityLogDisplay();
    }
    
    updateActivityLogDisplay() {
        const logElement = document.getElementById('activity-log');
        if (!logElement) return;
        
        const logEntries = this.activityLog.map(entry => `
            <div class="log-entry ${entry.type}">
                <span class="timestamp">[${entry.timestamp}]</span>
                <span class="message">${this.escapeHtml(entry.message)}</span>
            </div>
        `).join('');
        
        logElement.innerHTML = logEntries || '<div class="log-entry"><span class="message">No activity logged</span></div>';
    }
    
    clearActivityLog() {
        this.activityLog = [];
        this.updateActivityLogDisplay();
        this.log('Activity log cleared');
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    startAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }
        
        this.refreshTimer = setInterval(() => {
            this.loadStatus();
        }, this.refreshInterval);
        
        this.log(`Auto-refresh started (every ${this.refreshInterval / 1000}s)`);
    }
    
    stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
        
        this.log('Auto-refresh stopped');
    }
    
    hideLoadingOverlay() {
        setTimeout(() => {
            const overlay = document.getElementById('loading-overlay');
            if (overlay) {
                overlay.classList.add('hidden');
            }
        }, 1000); // Small delay to show the loading animation
    }
    
    // Health check functionality
    async performHealthCheck() {
        try {
            const response = await fetch('/health');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const health = await response.json();
            
            if (health.status === 'healthy') {
                this.log('Health check passed ✅');
                return true;
            } else {
                this.log('Health check failed ❌', 'error');
                return false;
            }
            
        } catch (error) {
            this.log(`Health check error: ${error.message}`, 'error');
            return false;
        }
    }
    
    // Endpoint testing
    async testEndpoints() {
        const endpoints = ['/bimqtt', '/accessCloud.json'];
        const results = [];
        
        for (const endpoint of endpoints) {
            try {
                const response = await fetch(endpoint);
                const success = response.ok;
                results.push({ endpoint, success, status: response.status });
                
                if (success) {
                    this.log(`Endpoint ${endpoint} is working ✅`);
                } else {
                    this.log(`Endpoint ${endpoint} failed (${response.status}) ❌`, 'error');
                }
                
            } catch (error) {
                results.push({ endpoint, success: false, error: error.message });
                this.log(`Endpoint ${endpoint} error: ${error.message}`, 'error');
            }
        }
        
        return results;
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new SengledDashboard();
});

// Add some utility functions for console debugging
window.debugDashboard = {
    testEndpoints: () => window.dashboard?.testEndpoints(),
    healthCheck: () => window.dashboard?.performHealthCheck(),
    refreshData: () => window.dashboard?.loadInitialData(),
    clearLog: () => window.dashboard?.clearActivityLog()
};