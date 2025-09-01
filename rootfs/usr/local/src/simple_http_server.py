#!/usr/bin/env python3
"""
Simple HTTP server for Sengled bulb provisioning endpoints
Serves the two critical endpoints bulbs need during setup

No async, no middleware magic, just plain HTTP handling.
What you see is what you get.
"""
import json
import os
import time
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from collections import defaultdict

from network_utils import get_addon_ip, get_network_info
from mqtt_listener import SengledMQTTListener

# Configure logging with environment variable support
def get_log_level():
    """Get log level from environment or default to INFO"""
    level_name = os.environ.get('LOG_LEVEL', 'info').upper()
    return getattr(logging, level_name, logging.INFO)

logging.basicConfig(
    level=get_log_level(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
CONFIG = {
    'mqtt_port': 28527,
    'http_port': 54448,
    'cached_ip': None,
    'ip_cache_duration': 300,  # 5 minutes
    'last_ip_check': 0
}

# Statistics tracking  
STATS = {
    'start_time': time.time(),
    'bimqtt_requests': 0,
    'access_cloud_requests': 0,
    'total_requests': 0,
    'last_request': None,
    'client_ips': set(),
    'client_request_counts': defaultdict(int)
}

# Global MQTT listener instance
mqtt_listener = None

def get_current_ip():
    """Get current IP with caching to avoid excessive lookups"""
    current_time = time.time()
    
    if (CONFIG['cached_ip'] is None or 
        current_time - CONFIG['last_ip_check'] > CONFIG['ip_cache_duration']):
        
        CONFIG['cached_ip'] = get_addon_ip()
        CONFIG['last_ip_check'] = current_time
        logger.info(f"Refreshed cached IP: {CONFIG['cached_ip']}")
    
    return CONFIG['cached_ip']

class SengledHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Sengled bulb endpoints"""
    
    def log_message(self, format, *args):
        """Override to use our logger instead of stderr"""
        logger.debug(format % args)
    
    def send_cors_headers(self):
        """Add CORS headers for wide compatibility"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
    
    def send_json_response(self, data, status=200):
        """Send JSON response with proper headers"""
        json_data = json.dumps(data, indent=2)
        
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(json_data)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json_data.encode('utf-8'))
    
    def send_html_response(self, html, status=200):
        """Send HTML response with proper headers"""
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(html)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def track_request(self):
        """Track request statistics and detect repeated requests"""
        client_ip = self.client_address[0]
        
        # Update general stats
        STATS['total_requests'] += 1
        STATS['last_request'] = datetime.now().isoformat()
        STATS['client_ips'].add(client_ip)
        STATS['client_request_counts'][client_ip] += 1
        
        # Log the raw path exactly as received - this is what we need to debug!
        logger.info(f"Request from {client_ip}: {self.command} {self.path}")
        
        # Check for repeated bimqtt requests (indicates MQTT connection issues)
        if 'bimqtt' in self.path:
            count = STATS['client_request_counts'][client_ip]
            if count > 3:  # More than 3 requests from same client
                logger.warning(f"⚠️  Client {client_ip} has made {count} requests - likely MQTT connection issues!")
                logger.warning("   This usually means the bulb can't connect to MQTT broker on port 28527")
    
    def handle_bimqtt(self):
        """Handle MQTT broker information request"""
        STATS['bimqtt_requests'] += 1
        current_ip = get_current_ip()
        
        response_data = {
            "protocal": "mqtt",  # Intentional typo - matches Sengled firmware
            "host": current_ip,
            "port": CONFIG['mqtt_port']
        }
        
        logger.info(f"📡 Serving bimqtt to {self.client_address[0]}: {response_data}")
        self.send_json_response(response_data)
    
    def handle_access_cloud(self):
        """Handle cloud access status request"""
        STATS['access_cloud_requests'] += 1
        
        response_data = {
            "messageCode": "200",
            "info": "OK",
            "description": "正常",
            "success": True
        }
        
        logger.info(f"☁️  Serving accessCloud.json to {self.client_address[0]}")
        self.send_json_response(response_data)
    
    def handle_health(self):
        """Health check endpoint"""
        uptime = time.time() - STATS['start_time']
        
        response_data = {
            "status": "healthy",
            "uptime_seconds": round(uptime, 2),
            "version": "1.0.11",
            "service": "sengled-local-server"
        }
        
        self.send_json_response(response_data)
    
    def handle_status(self):
        """Detailed status endpoint with statistics"""
        uptime = time.time() - STATS['start_time']
        current_ip = get_current_ip()
        
        response_data = {
            "service": "Sengled Local Server",
            "version": "1.0.11",
            "status": "running",
            "uptime_seconds": round(uptime, 2),
            "uptime_human": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
            "current_ip": current_ip,
            "ports": {
                "http": CONFIG['http_port'],
                "mqtt": CONFIG['mqtt_port']
            },
            "statistics": {
                "total_requests": STATS['total_requests'],
                "bimqtt_requests": STATS['bimqtt_requests'],
                "access_cloud_requests": STATS['access_cloud_requests'],
                "unique_clients": len(STATS['client_ips']),
                "last_request": STATS['last_request']
            },
            "endpoints": {
                "bimqtt": f"http://{current_ip}:{CONFIG['http_port']}/bimqtt",
                "accessCloud": f"http://{current_ip}:{CONFIG['http_port']}/accessCloud.json"
            }
        }
        
        self.send_json_response(response_data)
    
    def handle_network(self):
        """Network diagnostics endpoint"""
        try:
            network_info = get_network_info()
            response_data = {
                "success": True,
                "network_info": network_info,
                "cache_info": {
                    "cached_ip": CONFIG['cached_ip'],
                    "last_check": CONFIG['last_ip_check'],
                    "cache_duration": CONFIG['ip_cache_duration']
                }
            }
            self.send_json_response(response_data)
        except Exception as e:
            logger.error(f"Failed to get network info: {e}")
            self.send_json_response({"success": False, "error": str(e)}, status=500)
    
    def handle_api_devices(self):
        """API endpoint for device discovery - returns all discovered devices"""
        global mqtt_listener
        
        try:
            if mqtt_listener is None:
                self.send_json_response({
                    "success": False, 
                    "error": "MQTT listener not initialized"
                }, status=503)
                return
            
            devices = mqtt_listener.get_devices()
            
            response_data = {
                "success": True,
                "device_count": len(devices),
                "devices": devices
            }
            
            logger.info(f"📱 API: Served {len(devices)} devices to {self.client_address[0]}")
            self.send_json_response(response_data)
            
        except Exception as e:
            logger.error(f"Failed to get devices: {e}")
            self.send_json_response({
                "success": False, 
                "error": str(e)
            }, status=500)
    
    def handle_api_device(self, mac: str):
        """API endpoint for single device by MAC address"""
        global mqtt_listener
        
        try:
            if mqtt_listener is None:
                self.send_json_response({
                    "success": False,
                    "error": "MQTT listener not initialized" 
                }, status=503)
                return
            
            device = mqtt_listener.get_device(mac)
            
            if device is None:
                self.send_json_response({
                    "success": False,
                    "error": f"Device {mac} not found"
                }, status=404)
                return
            
            response_data = {
                "success": True,
                "device": device
            }
            
            logger.info(f"📱 API: Served device {mac} to {self.client_address[0]}")
            self.send_json_response(response_data)
            
        except Exception as e:
            logger.error(f"Failed to get device {mac}: {e}")
            self.send_json_response({
                "success": False,
                "error": str(e)
            }, status=500)
    
    def handle_api_mqtt_status(self):
        """API endpoint for MQTT listener status"""
        global mqtt_listener
        
        try:
            if mqtt_listener is None:
                self.send_json_response({
                    "success": False,
                    "error": "MQTT listener not initialized"
                }, status=503)
                return
            
            status = mqtt_listener.get_status()
            
            response_data = {
                "success": True,
                "mqtt_status": status
            }
            
            self.send_json_response(response_data)
            
        except Exception as e:
            logger.error(f"Failed to get MQTT status: {e}")
            self.send_json_response({
                "success": False,
                "error": str(e)
            }, status=500)
    
    def handle_dashboard(self):
        """Simple HTML dashboard"""
        global mqtt_listener
        
        uptime = time.time() - STATS['start_time']
        current_ip = get_current_ip()
        
        # Get MQTT and device info
        mqtt_status = "Disconnected"
        device_count = 0
        mqtt_uptime = "N/A"
        
        if mqtt_listener:
            status = mqtt_listener.get_status()
            mqtt_status = "Connected" if status['connected'] else "Disconnected"
            device_count = status['storage']['total_devices']
            mqtt_uptime = f"{int(status['uptime_seconds'] // 3600)}h {int((status['uptime_seconds'] % 3600) // 60)}m {int(status['uptime_seconds'] % 60)}s"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Sengled Local Server</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .status {{ display: flex; justify-content: space-between; margin: 20px 0; }}
        .stat-box {{ background: #e8f4fd; padding: 15px; border-radius: 5px; text-align: center; flex: 1; margin: 0 10px; }}
        .endpoints {{ background: #f0f9ff; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .endpoint {{ margin: 10px 0; font-family: monospace; }}
        .green {{ color: #28a745; }}
        .red {{ color: #dc3545; }}
        .blue {{ color: #007bff; }}
        .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔦 Sengled Local Server 💡</h1>
            <p class="green">Status: Running (Simple HTTP)</p>
        </div>
        
        <div class="status">
            <div class="stat-box">
                <h3>HTTP Uptime</h3>
                <p>{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s</p>
            </div>
            <div class="stat-box">
                <h3>Total Requests</h3>
                <p>{STATS['total_requests']}</p>
            </div>
            <div class="stat-box">
                <h3>Discovered Devices</h3>
                <p>{device_count}</p>
            </div>
            <div class="stat-box">
                <h3>MQTT Status</h3>
                <p class="{'green' if mqtt_status == 'Connected' else 'red'}">{mqtt_status}</p>
            </div>
        </div>
        
        <div class="endpoints">
            <h3>📡 Active Endpoints</h3>
            <div class="endpoint"><strong>MQTT Info:</strong> <span class="blue">http://{current_ip}:{CONFIG['http_port']}/bimqtt</span></div>
            <div class="endpoint"><strong>Cloud Access:</strong> <span class="blue">http://{current_ip}:{CONFIG['http_port']}/accessCloud.json</span></div>
            <div class="endpoint"><strong>MQTT Broker:</strong> <span class="blue">{current_ip}:{CONFIG['mqtt_port']}</span> (SSL)</div>
        </div>
        
        <div class="endpoints">
            <h3>🔧 Management & API</h3>
            <div class="endpoint"><a href="/status">📊 Detailed Status</a></div>
            <div class="endpoint"><a href="/network">🌐 Network Info</a></div>
            <div class="endpoint"><a href="/health">❤️ Health Check</a></div>
            <div class="endpoint"><a href="/api/devices">📱 Device API</a></div>
            <div class="endpoint"><a href="/api/mqtt/status">📡 MQTT Status</a></div>
        </div>
        
        <div class="footer">
            <p>Sengled Local Server v1.0.11 - Simple HTTP | Keeping your bulbs local! 🏠</p>
        </div>
    </div>
</body>
</html>
        """
        
        self.send_html_response(html_content)
    
    def do_GET(self):
        """Handle GET requests - this is where all the URL magic happens"""
        start_time = time.time()
        
        # Track the request
        self.track_request()
        
        # The path as received - no processing, no interpretation
        raw_path = self.path
        
        # Handle all the crazy ways the bulbs might send requests
        # Check for bimqtt in any form
        if any(pattern in raw_path for pattern in ['/bimqtt', 'bimqtt']):
            self.handle_bimqtt()
        
        # Check for accessCloud in any form  
        elif any(pattern in raw_path for pattern in ['/accessCloud.json', 'accessCloud.json', 'accessCloud']):
            self.handle_access_cloud()
        
        # API endpoints for device management
        elif raw_path == '/api/devices':
            self.handle_api_devices()
        elif raw_path.startswith('/api/device/'):
            # Extract MAC from path like /api/device/B0:CE:18:C3:3A:A2
            mac = raw_path.split('/')[-1]
            self.handle_api_device(mac)
        elif raw_path == '/api/mqtt/status':
            self.handle_api_mqtt_status()
        
        # Management endpoints
        elif raw_path == '/health':
            self.handle_health()
        elif raw_path == '/status':
            self.handle_status()
        elif raw_path == '/network':
            self.handle_network()
        elif raw_path == '/' or raw_path == '':
            self.handle_dashboard()
        
        # 404 for anything else
        else:
            logger.warning(f"🚫 404 Not Found: {raw_path}")
            self.send_json_response({"error": "Not Found", "path": raw_path}, status=404)
        
        # Log processing time
        process_time = time.time() - start_time
        logger.debug(f"Request processed in {process_time:.3f}s")
    
    def do_POST(self):
        """Handle POST requests"""
        start_time = time.time()
        
        # Track the request
        self.track_request()
        
        raw_path = self.path
        
        # Read POST data (but usually ignore it for Sengled endpoints)
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 0:
            post_data = self.rfile.read(content_length)
            logger.debug(f"POST data received ({content_length} bytes): {post_data[:200]}...")
        
        # Handle POST to accessCloud
        if any(pattern in raw_path for pattern in ['/accessCloud.json', 'accessCloud.json', 'accessCloud']):
            self.handle_access_cloud()
        else:
            logger.warning(f"🚫 POST 404 Not Found: {raw_path}")
            self.send_json_response({"error": "Not Found", "path": raw_path}, status=404)
        
        # Log processing time
        process_time = time.time() - start_time
        logger.debug(f"POST request processed in {process_time:.3f}s")
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS"""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

def run_server():
    """Start the HTTP server and MQTT listener"""
    global mqtt_listener
    
    server_address = ('0.0.0.0', CONFIG['http_port'])
    
    logger.info("🚀 Sengled Local Server starting up...")
    logger.info(f"📡 HTTP server listening on port {CONFIG['http_port']}")
    logger.info(f"🔌 MQTT broker expected on port {CONFIG['mqtt_port']}")
    
    # Initial IP detection
    current_ip = get_current_ip()
    logger.info(f"🌐 Detected IP address: {current_ip}")
    
    # Initialize and start MQTT listener (connect to localhost broker)
    # TEMPORARILY DISABLED - debugging connection loop
    # try:
    #     mqtt_listener = SengledMQTTListener(broker_host="localhost", broker_port=CONFIG['mqtt_port'])
    #     mqtt_listener.start()
    #     logger.info("📡 MQTT listener started for device discovery")
    # except Exception as e:
    #     logger.error(f"Failed to start MQTT listener: {e}")
    #     logger.warning("Device discovery will not be available")
    
    logger.info("🔧 MQTT listener temporarily disabled for debugging")
    
    logger.info("✅ Sengled Local Server ready!")
    
    # Create and start HTTP server
    httpd = HTTPServer(server_address, SengledHandler)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("🛑 Sengled Local Server shutting down...")
        uptime = time.time() - STATS['start_time']
        logger.info(f"📊 Final stats - Uptime: {int(uptime)}s, Total requests: {STATS['total_requests']}")
    finally:
        # Clean shutdown
        if mqtt_listener:
            mqtt_listener.stop()
        httpd.server_close()

if __name__ == "__main__":
    run_server()