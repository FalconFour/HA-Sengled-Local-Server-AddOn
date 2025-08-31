#!/bin/bash
# Health check script for Sengled Local Server
# This script is used by Docker's HEALTHCHECK directive

set -e

# Configuration
HTTP_PORT=54448
MQTT_PORT=28527
TIMEOUT=5

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_error() {
    log "${RED}ERROR: $1${NC}"
}

log_success() {
    log "${GREEN}SUCCESS: $1${NC}"
}

log_warning() {
    log "${YELLOW}WARNING: $1${NC}"
}

# Health check functions

check_http_server() {
    log "Checking HTTP server on port $HTTP_PORT..."
    
    # Check if the health endpoint responds
    if curl -f -s --max-time $TIMEOUT "http://localhost:$HTTP_PORT/health" > /dev/null; then
        log_success "HTTP server is responding"
        return 0
    else
        log_error "HTTP server is not responding"
        return 1
    fi
}

check_critical_endpoints() {
    log "Checking critical Sengled endpoints..."
    
    local endpoints=("/bimqtt" "/accessCloud.json")
    local failed=0
    
    for endpoint in "${endpoints[@]}"; do
        if curl -f -s --max-time $TIMEOUT "http://localhost:$HTTP_PORT$endpoint" > /dev/null; then
            log_success "Endpoint $endpoint is working"
        else
            log_error "Endpoint $endpoint is not working"
            failed=$((failed + 1))
        fi
    done
    
    if [ $failed -eq 0 ]; then
        return 0
    else
        return 1
    fi
}

check_mqtt_broker() {
    log "Checking MQTT broker on port $MQTT_PORT..."
    
    # Check if Mosquitto process is running
    if pgrep mosquitto > /dev/null; then
        log_success "Mosquitto process is running"
        
        # Check if port is listening
        if netstat -ln | grep -q ":$MQTT_PORT "; then
            log_success "MQTT broker is listening on port $MQTT_PORT"
            return 0
        else
            log_error "MQTT broker is not listening on port $MQTT_PORT"
            return 1
        fi
    else
        log_error "Mosquitto process is not running"
        return 1
    fi
}

check_certificates() {
    log "Checking SSL certificates..."
    
    local cert_dir="/data/certs"
    local required_files=("ca.crt" "server.crt" "server.key")
    local missing=0
    
    for file in "${required_files[@]}"; do
        if [ -f "$cert_dir/$file" ]; then
            log_success "Certificate file $file exists"
        else
            log_warning "Certificate file $file is missing"
            missing=$((missing + 1))
        fi
    done
    
    if [ $missing -eq 0 ]; then
        return 0
    else
        log_warning "$missing certificate files are missing"
        return 1
    fi
}

check_disk_space() {
    log "Checking disk space..."
    
    local usage=$(df /data | tail -1 | awk '{print $5}' | sed 's/%//')
    
    if [ "$usage" -lt 90 ]; then
        log_success "Disk usage is $usage% (healthy)"
        return 0
    elif [ "$usage" -lt 95 ]; then
        log_warning "Disk usage is $usage% (warning)"
        return 0
    else
        log_error "Disk usage is $usage% (critical)"
        return 1
    fi
}

check_memory_usage() {
    log "Checking memory usage..."
    
    # Get memory usage percentage
    local mem_usage=$(free | grep Mem | awk '{printf("%.0f", $3/$2 * 100.0)}')
    
    if [ "$mem_usage" -lt 80 ]; then
        log_success "Memory usage is $mem_usage% (healthy)"
        return 0
    elif [ "$mem_usage" -lt 90 ]; then
        log_warning "Memory usage is $mem_usage% (warning)"
        return 0
    else
        log_error "Memory usage is $mem_usage% (critical)"
        return 1
    fi
}

# Main health check
main() {
    log "=== Sengled Local Server Health Check ==="
    
    local failed_checks=0
    local total_checks=0
    
    # Essential checks (these must pass)
    essential_checks=(
        "check_http_server"
        "check_critical_endpoints"
        "check_mqtt_broker"
    )
    
    # Optional checks (warnings only)
    optional_checks=(
        "check_certificates"
        "check_disk_space"
        "check_memory_usage"
    )
    
    # Run essential checks
    log "Running essential health checks..."
    for check in "${essential_checks[@]}"; do
        total_checks=$((total_checks + 1))
        if ! $check; then
            failed_checks=$((failed_checks + 1))
        fi
        echo # Add blank line for readability
    done
    
    # Run optional checks
    log "Running optional health checks..."
    for check in "${optional_checks[@]}"; do
        $check || true  # Don't fail on optional checks
        echo # Add blank line for readability
    done
    
    # Summary
    log "=== Health Check Summary ==="
    if [ $failed_checks -eq 0 ]; then
        log_success "All essential checks passed ($total_checks/$total_checks)"
        log_success "Service is healthy! 🎉"
        exit 0
    else
        log_error "$failed_checks out of $total_checks essential checks failed"
        log_error "Service is unhealthy! 💥"
        exit 1
    fi
}

# Handle command line options
case "${1:-health}" in
    "health")
        main
        ;;
    "http")
        check_http_server
        ;;
    "mqtt")
        check_mqtt_broker
        ;;
    "certs")
        check_certificates
        ;;
    "endpoints")
        check_critical_endpoints
        ;;
    "quick")
        # Quick check - just the essentials
        log "Quick health check..."
        if check_http_server && check_mqtt_broker; then
            log_success "Quick health check passed"
            exit 0
        else
            log_error "Quick health check failed"
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 [health|http|mqtt|certs|endpoints|quick]"
        echo "  health    - Full health check (default)"
        echo "  http      - Check HTTP server only"
        echo "  mqtt      - Check MQTT broker only"
        echo "  certs     - Check certificates only"
        echo "  endpoints - Check critical endpoints only"
        echo "  quick     - Quick essential checks only"
        exit 1
        ;;
esac