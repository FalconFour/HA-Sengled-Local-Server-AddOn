#!/usr/bin/env python3
"""
FastAPI HTTP server for Sengled bulb provisioning endpoints
Serves the two critical endpoints bulbs need during setup
"""
import json
import os
import time
import logging
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import aiofiles

from network_utils import get_addon_ip, get_network_info

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

# Initialize FastAPI app
app = FastAPI(
    title="Sengled Local Server",
    description="HTTP endpoints for local Sengled bulb provisioning",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Statistics tracking
stats = {
    'start_time': time.time(),
    'bimqtt_requests': 0,
    'access_cloud_requests': 0,
    'total_requests': 0,
    'last_request': None,
    'client_ips': set()
}

# Configuration cache
config_cache = {
    'mqtt_port': 28527,
    'http_port': 54448,
    'last_ip_check': 0,
    'cached_ip': None,
    'ip_cache_duration': 300  # 5 minutes
}


def get_current_ip() -> str:
    """Get current IP with caching to avoid excessive lookups"""
    current_time = time.time()
    
    # Check if we need to refresh the IP cache
    if (config_cache['cached_ip'] is None or 
        current_time - config_cache['last_ip_check'] > config_cache['ip_cache_duration']):
        
        config_cache['cached_ip'] = get_addon_ip()
        config_cache['last_ip_check'] = current_time
        logger.info(f"Refreshed cached IP: {config_cache['cached_ip']}")
    
    return config_cache['cached_ip']


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Middleware to track requests and add CORS headers"""
    start_time = time.time()
    
    # Update statistics
    stats['total_requests'] += 1
    stats['last_request'] = datetime.now().isoformat()
    
    client_ip = request.client.host
    if client_ip:
        stats['client_ips'].add(client_ip)
        logger.info(f"Request from {client_ip}: {request.method} {request.url.path}")
    
    # Process request
    response = await call_next(request)
    
    # Add CORS headers for wide compatibility
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    
    # Log processing time
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    
    logger.debug(f"Request processed in {process_time:.3f}s")
    
    return response


@app.get("/bimqtt", 
         summary="MQTT Broker Information",
         description="Returns MQTT broker connection details for Sengled bulbs",
         response_model=Dict[str, Any])
async def get_bimqtt(request: Request):
    """
    Critical endpoint: Returns MQTT broker information for Sengled bulbs
    
    This endpoint tells the bulb where to connect for MQTT communication.
    Note: The typo 'protocal' is intentional - it matches the bulb firmware.
    """
    stats['bimqtt_requests'] += 1
    
    current_ip = get_current_ip()
    
    response_data = {
        "protocal": "mqtt",  # Intentional typo - matches Sengled firmware
        "host": current_ip,
        "port": config_cache['mqtt_port']
    }
    
    logger.info(f"Serving bimqtt to {request.client.host}: {response_data}")
    
    return response_data


@app.get("/accessCloud.json",
         summary="Access Cloud Status", 
         description="Returns cloud access status for Sengled bulbs",
         response_model=Dict[str, Any])
@app.post("/accessCloud.json",
          summary="Access Cloud Status (POST)", 
          description="Returns cloud access status for Sengled bulbs via POST",
          response_model=Dict[str, Any])
async def get_access_cloud(request: Request):
    """
    Critical endpoint: Returns cloud access status for Sengled bulbs
    
    Handles both GET and POST requests. POST data from bulbs is ignored.
    Always returns success to allow the bulb to complete its setup process.
    """
    stats['access_cloud_requests'] += 1
    
    response_data = {
        "messageCode": "200",
        "info": "OK", 
        "description": "正常",
        "success": True
    }
    
    logger.info(f"Serving accessCloud.json to {request.client.host}")
    
    return response_data


@app.get("/health",
         summary="Health Check",
         description="Health check endpoint for service monitoring")
async def health_check():
    """Health check endpoint for service monitoring"""
    uptime = time.time() - stats['start_time']
    
    return {
        "status": "healthy",
        "uptime_seconds": round(uptime, 2),
        "version": "1.0.0",
        "service": "sengled-local-server"
    }


@app.get("/status",
         summary="Service Status",
         description="Detailed service status and statistics")
async def get_status():
    """Comprehensive status endpoint with statistics"""
    uptime = time.time() - stats['start_time']
    current_ip = get_current_ip()
    
    return {
        "service": "Sengled Local Server",
        "version": "1.0.0",
        "status": "running",
        "uptime_seconds": round(uptime, 2),
        "uptime_human": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
        "current_ip": current_ip,
        "ports": {
            "http": config_cache['http_port'],
            "mqtt": config_cache['mqtt_port']
        },
        "statistics": {
            "total_requests": stats['total_requests'],
            "bimqtt_requests": stats['bimqtt_requests'],
            "access_cloud_requests": stats['access_cloud_requests'],
            "unique_clients": len(stats['client_ips']),
            "last_request": stats['last_request']
        },
        "endpoints": {
            "bimqtt": f"http://{current_ip}:{config_cache['http_port']}/bimqtt",
            "accessCloud": f"http://{current_ip}:{config_cache['http_port']}/accessCloud.json"
        }
    }


@app.get("/network",
         summary="Network Information",
         description="Network diagnostics and IP detection details")
async def get_network_info_endpoint():
    """Network diagnostics endpoint"""
    try:
        network_info = get_network_info()
        return {
            "success": True,
            "network_info": network_info,
            "cache_info": {
                "cached_ip": config_cache['cached_ip'],
                "last_check": config_cache['last_ip_check'],
                "cache_duration": config_cache['ip_cache_duration']
            }
        }
    except Exception as e:
        logger.error(f"Failed to get network info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve network information")


@app.get("/",
         response_class=HTMLResponse,
         summary="Dashboard",
         description="Simple web dashboard showing service status")
async def dashboard():
    """Simple HTML dashboard for service overview"""
    uptime = time.time() - stats['start_time']
    current_ip = get_current_ip()
    
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
            .blue {{ color: #007bff; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔦 Sengled Local Server 💡</h1>
                <p class="green">Status: Running</p>
            </div>
            
            <div class="status">
                <div class="stat-box">
                    <h3>Uptime</h3>
                    <p>{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s</p>
                </div>
                <div class="stat-box">
                    <h3>Total Requests</h3>
                    <p>{stats['total_requests']}</p>
                </div>
                <div class="stat-box">
                    <h3>Unique Clients</h3>
                    <p>{len(stats['client_ips'])}</p>
                </div>
            </div>
            
            <div class="endpoints">
                <h3>📡 Active Endpoints</h3>
                <div class="endpoint"><strong>MQTT Info:</strong> <span class="blue">http://{current_ip}:{config_cache['http_port']}/bimqtt</span></div>
                <div class="endpoint"><strong>Cloud Access:</strong> <span class="blue">http://{current_ip}:{config_cache['http_port']}/accessCloud.json</span></div>
                <div class="endpoint"><strong>MQTT Broker:</strong> <span class="blue">{current_ip}:{config_cache['mqtt_port']}</span> (SSL)</div>
            </div>
            
            <div class="endpoints">
                <h3>🔧 Management</h3>
                <div class="endpoint"><a href="/status">📊 Detailed Status</a></div>
                <div class="endpoint"><a href="/network">🌐 Network Info</a></div>
                <div class="endpoint"><a href="/docs">📚 API Documentation</a></div>
                <div class="endpoint"><a href="/health">❤️ Health Check</a></div>
            </div>
            
            <div class="footer">
                <p>Sengled Local Server v1.0.0 | Keeping your bulbs local! 🏠</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


# === Workarounds for Sengled firmware URL parsing bugs ===

@app.get("/{mangled_path:path}",
         summary="Catch-all for mangled bulb URLs",
         description="Handles malformed URLs from Sengled bulbs with broken HTTP clients")
@app.post("/{mangled_path:path}",
          summary="Catch-all for mangled bulb URLs (POST)",
          description="Handles malformed POST URLs from Sengled bulbs with broken HTTP clients")
async def handle_mangled_urls(mangled_path: str, request: Request):
    """
    Workaround for Sengled bulb firmware that incorrectly uses full URLs as paths
    
    Bulbs send requests like: GET //10.0.1.31:54448/bimqtt or GET http://10.0.1.31:54448/bimqtt
    This catches those and redirects to the correct endpoint.
    """
    logger.debug(f"Caught mangled path: {mangled_path}")
    
    # Handle mangled bimqtt requests
    if "bimqtt" in mangled_path.lower():
        logger.info(f"Redirecting mangled bimqtt request from {request.client.host}: {mangled_path}")
        return await get_bimqtt(request)
    
    # Handle mangled accessCloud requests  
    if "accesscloud" in mangled_path.lower():
        logger.info(f"Redirecting mangled accessCloud request from {request.client.host}: {mangled_path}")
        return await get_access_cloud(request)
    
    # Log unrecognized patterns for debugging
    logger.warning(f"Unrecognized mangled path from {request.client.host}: {mangled_path}")
    raise HTTPException(status_code=404, detail="Not Found")


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup"""
    logger.info("🚀 Sengled Local Server starting up...")
    logger.info(f"📡 HTTP server will listen on port {config_cache['http_port']}")
    logger.info(f"🔌 MQTT broker expected on port {config_cache['mqtt_port']}")
    
    # Initial IP detection
    current_ip = get_current_ip()
    logger.info(f"🌐 Detected IP address: {current_ip}")
    
    logger.info("✅ HTTP server ready for bulb provisioning!")


@app.on_event("shutdown") 
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Sengled Local Server shutting down...")
    uptime = time.time() - stats['start_time']
    logger.info(f"📊 Final stats - Uptime: {int(uptime)}s, Total requests: {stats['total_requests']}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=54448, log_level="info")