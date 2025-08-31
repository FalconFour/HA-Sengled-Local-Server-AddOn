#!/usr/bin/with-contenv bashio
set -e

# ==============================================================================
# Sengled Local Server - Startup Orchestrator
# Coordinates HTTP server, MQTT broker, and certificate management
# ==============================================================================

# Configuration paths
CONFIG_PATH=/data/options.json
MOSQUITTO_CONFIG_DIR=/data/mosquitto
CERTS_DIR=/data/certs
LOG_LEVEL=$(bashio::config 'log_level')

# Set logging level
bashio::log.level "${LOG_LEVEL}"

# ==============================================================================
# Helper Functions
# ==============================================================================

setup_directories() {
    bashio::log.info "Setting up directory structure..."
    mkdir -p "${MOSQUITTO_CONFIG_DIR}" "${CERTS_DIR}" /data/config
    chown -R mosquitto:mosquitto "${MOSQUITTO_CONFIG_DIR}"
}

generate_certificates() {
    if [[ $(bashio::config 'auto_generate_certs') == true ]]; then
        if [[ ! -f "${CERTS_DIR}/ca.crt" ]] || [[ ! -f "${CERTS_DIR}/server.crt" ]]; then
            bashio::log.info "Generating SSL certificates..."
            python3 /app/src/cert_manager.py --generate --output-dir "${CERTS_DIR}" \
                --common-name "$(bashio::config 'cert_common_name')"
        else
            bashio::log.info "SSL certificates already exist, skipping generation"
        fi
    fi
}

configure_mosquitto() {
    bashio::log.info "Configuring Mosquitto MQTT broker..."
    python3 /app/src/config_manager.py \
        --template /app/mosquitto/mosquitto.conf.j2 \
        --output "${MOSQUITTO_CONFIG_DIR}/mosquitto.conf" \
        --config "${CONFIG_PATH}" \
        --certs-dir "${CERTS_DIR}"
}

start_mosquitto() {
    bashio::log.info "Starting Mosquitto MQTT broker on port 28527..."
    mosquitto -c "${MOSQUITTO_CONFIG_DIR}/mosquitto.conf" &
    MOSQUITTO_PID=$!
    
    # Wait for Mosquitto to start
    sleep 3
    
    if kill -0 $MOSQUITTO_PID 2>/dev/null; then
        bashio::log.info "Mosquitto started successfully (PID: $MOSQUITTO_PID)"
    else
        bashio::log.error "Failed to start Mosquitto!"
        exit 1
    fi
}

start_http_server() {
    bashio::log.info "Starting HTTP server on port 54448..."
    cd /app/src
    python3 -m uvicorn http_server:app \
        --host 0.0.0.0 \
        --port 54448 \
        --log-level "${LOG_LEVEL,,}" \
        --access-log &
    HTTP_PID=$!
    
    # Wait for HTTP server to start
    sleep 2
    
    if kill -0 $HTTP_PID 2>/dev/null; then
        bashio::log.info "HTTP server started successfully (PID: $HTTP_PID)"
    else
        bashio::log.error "Failed to start HTTP server!"
        exit 1
    fi
}

# ==============================================================================
# Cleanup handler
# ==============================================================================

cleanup() {
    bashio::log.info "Shutting down services..."
    
    if [[ -n $HTTP_PID ]] && kill -0 $HTTP_PID 2>/dev/null; then
        bashio::log.info "Stopping HTTP server..."
        kill $HTTP_PID
        wait $HTTP_PID 2>/dev/null || true
    fi
    
    if [[ -n $MOSQUITTO_PID ]] && kill -0 $MOSQUITTO_PID 2>/dev/null; then
        bashio::log.info "Stopping Mosquitto..."
        kill $MOSQUITTO_PID
        wait $MOSQUITTO_PID 2>/dev/null || true
    fi
    
    bashio::log.info "Cleanup complete"
    exit 0
}

trap cleanup SIGTERM SIGINT SIGQUIT

# ==============================================================================
# Main execution
# ==============================================================================

bashio::log.info "Starting Sengled Local Server v1.0.0..."
bashio::log.info "🔦 Vibe-coded in Claude Code by Matt Falcon 💡"
bashio::log.info "🏠 Light up your local network!"

# Display configuration
bashio::log.info "Configuration:"
bashio::log.info "  MQTT Broker: $(bashio::config 'mqtt_broker_host'):$(bashio::config 'mqtt_broker_port')"
bashio::log.info "  Bridge Enabled: $(bashio::config 'enable_bridge')"
bashio::log.info "  Auto Certs: $(bashio::config 'auto_generate_certs')"
bashio::log.info "  Log Level: ${LOG_LEVEL}"

# Setup
setup_directories
generate_certificates
configure_mosquitto

# Start services
start_mosquitto
start_http_server

# Service monitoring and status
bashio::log.info "🚀 All services started successfully!"
bashio::log.info "📡 HTTP endpoints available at port 54448"
bashio::log.info "🔌 MQTT broker listening on port 28527"
bashio::log.info "📊 Monitoring services..."

# Keep the container running and monitor services
while true; do
    # Check if services are still running
    if ! kill -0 $MOSQUITTO_PID 2>/dev/null; then
        bashio::log.error "Mosquitto process died! Restarting..."
        start_mosquitto
    fi
    
    if ! kill -0 $HTTP_PID 2>/dev/null; then
        bashio::log.error "HTTP server process died! Restarting..."
        start_http_server
    fi
    
    sleep 30
done