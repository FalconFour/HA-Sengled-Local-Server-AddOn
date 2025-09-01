# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Sengled Local Server** - A complete Home Assistant add-on that provides HTTP and MQTT infrastructure to keep Sengled WiFi bulbs local and secure, eliminating cloud dependencies.

## Architecture

### Core Services
- **HTTP Server (Simple)** - Port 54448 ("light") - Serves bulb provisioning endpoints
- **MQTT Broker (Mosquitto)** - Port 28527 ("bulbs") - SSL-enabled broker with bridge to HA
- **Certificate Manager** - Auto-generates CA and server certificates
- **Web Dashboard** - Real-time monitoring interface

### Key Components
- `rootfs/usr/local/src/simple_http_server.py` - Simple HTTP server with integrated MQTT listener and device API
- `rootfs/usr/local/src/device_storage.py` - JSON-based device storage with persistence and limits
- `rootfs/usr/local/src/mqtt_listener.py` - MQTT listener for automatic device discovery
- `rootfs/usr/local/src/cert_manager.py` - SSL certificate generation and management  
- `rootfs/usr/local/src/config_manager.py` - Dynamic Mosquitto configuration from Jinja2 templates
- `rootfs/usr/local/src/network_utils.py` - Intelligent IP detection for containerized environments
- `rootfs/usr/local/mosquitto/mosquitto.conf.j2` - Mosquitto configuration template with bridge support
- `rootfs/usr/local/web/` - Modern responsive dashboard with real-time updates
- `rootfs/etc/services.d/sengled/run` - s6-overlay service manager (replaces custom run.sh)
- `rootfs/usr/src/app/translations/` - Home Assistant UI translations

## Development Commands

### Building & Testing
```bash
# Build Docker image (multi-arch support)
docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7 -t sengled-local .

# Test HTTP endpoints locally
curl http://localhost:54448/bimqtt
curl http://localhost:54448/accessCloud.json
curl http://localhost:54448/health
curl http://localhost:54448/api/devices
curl http://localhost:54448/api/mqtt/status

# Test certificate generation
python3 src/cert_manager.py --generate --output-dir ./test_certs

# Validate Mosquitto config
mosquitto -t -c mosquitto/test.conf

# Run health checks
./scripts/healthcheck.sh quick
```

### Configuration Management
```bash
# Generate Mosquitto config from template
python3 src/config_manager.py --template mosquitto/mosquitto.conf.j2 \
    --output /tmp/mosquitto.conf --config /data/options.json \
    --certs-dir /data/certs

# Backup configuration and certificates
./scripts/backup.sh backup

# Restore from backup
./scripts/backup.sh restore /data/backups/sengled_backup_20250830_143000.tar.gz
```

## Code Architecture

### HTTP Server (Simple)  
- **Core Endpoints**: `/bimqtt`, `/accessCloud.json`, `/health`, `/status`, `/network`
- **Device API**: `/api/devices`, `/api/device/{mac}`, `/api/mqtt/status`
- **Features**: Dynamic IP detection, malformed URL handling, request tracking, CORS support
- **Monitoring**: Built-in statistics and activity logging with clear debugging

### Device Discovery System
- **MQTT Listener**: Connects to local broker using SSL certificates
- **Automatic Discovery**: Processes `wifielement/{mac}/status` messages from bulb power-up
- **Smart Filtering**: Ignores short status messages, captures comprehensive device data
- **JSON Persistence**: Stores devices in `/data/devices/devices.json` with atomic writes
- **Storage Limits**: 200 devices max, 1MB per device, 10MB total to prevent unbounded growth

### MQTT Infrastructure
- **Mosquitto Broker**: SSL-enabled on port 28527 with ACL security
- **Native Bridge**: Forwards `wifielement/*` topics to HA MQTT broker
- **Certificate Chain**: CA + server certificates with proper SAN entries
- **Security**: Topic-based access control, anonymous bulb authentication

### Configuration System
- **Home Assistant Integration**: Full HA add-on framework support
- **Template-Based**: Jinja2 templates for dynamic configuration
- **Validation**: Schema validation and error handling
- **Bridge Configuration**: Automatic MQTT broker discovery and setup

## Port Strategy

- **28527** ("bulbs" on phone keypad) - MQTT Broker
- **54448** ("light" on phone keypad) - HTTP Server

Creative port numbering provides:
- **Configurability** - You control which ports bulbs connect to during setup
- **Easy memorization** via word mapping ("bulbs" = 28527, "light" = 54448)  
- **Conflict avoidance** - No common service port collisions

## Security Features

- **SSL/TLS**: Auto-generated CA certificates with proper chains
- **Access Control**: MQTT ACL with topic-based permissions restricting bulbs to own topics
- **Configurable Ports**: Full control over port assignment during bulb WiFi setup
- **Local Operation**: No external dependencies or cloud connections
- **Certificate Validation**: Proper hostname/IP SAN entries for SSL verification
- **Network Isolation**: Can be restricted to local network segments for additional security

## Testing & Validation

### Manual Testing
1. **HTTP Endpoints**: Verify both critical endpoints return proper JSON
2. **Certificate Generation**: Ensure CA and server certs are valid
3. **MQTT Connectivity**: Test SSL connections on port 28527
4. **Bridge Operation**: Verify topic forwarding to HA broker
5. **Dashboard**: Check web interface at port 54448

### Health Monitoring
- Docker HEALTHCHECK integration
- Multi-level health validation (HTTP, MQTT, certificates)
- Real-time service monitoring
- Comprehensive diagnostics API

## Common Development Tasks

### Adding New Features
1. Update `config.yaml` schema if needed
2. Modify templates in `mosquitto/` or `src/` as appropriate  
3. Update web dashboard in `web/` for new monitoring
4. Add translations to `translations/en.yaml`
5. Update README.md and CHANGELOG.md

### Debugging Issues
1. Check add-on logs in Home Assistant
2. Use dashboard at port 54448 for real-time diagnostics
3. Run health checks: `./scripts/healthcheck.sh`
4. Test individual components with provided Python scripts
5. Verify network connectivity and certificate validity

### Configuration Changes
- Always test configuration generation with `config_manager.py`
- Validate Mosquitto config with `mosquitto -t`
- Check certificate validity dates and SAN entries
- Test bridge connectivity to target MQTT broker

## File Structure Understanding
```
├── config.yaml              # HA add-on metadata and schema
├── Dockerfile               # Multi-stage Alpine build
├── run.sh                   # Service orchestrator  
├── src/                     # Python application code
├── mosquitto/               # MQTT broker configuration templates
├── web/                     # Dashboard UI (HTML/CSS/JS)
├── scripts/                 # Utility and management scripts
├── translations/            # HA UI localization
└── requirements.txt         # Python dependencies
```

This is a production-ready Home Assistant add-on with enterprise-grade features, comprehensive monitoring, and security best practices.

## 🏆 Docker Hell Survival Guide - Lessons Learned

### Critical HA Add-on Architecture Requirements

**MUST follow the official HA add-on template structure:**
- Use `rootfs/` directory for ALL application files
- Use `build.yaml` for multi-architecture base images  
- Use s6-overlay services in `rootfs/etc/services.d/`
- Use official HA base images (e.g., `ghcr.io/home-assistant/amd64-base:3.15`)

**GitHub Actions Builder Requirements:**
```yaml
- name: Build add-on
  uses: home-assistant/builder@2025.03.0  # Use specific version, not @master
  with:
    args: |
      --${{ matrix.arch }} \
      --target /data \
      --image "sengled-local-server-{arch}" \
      --docker-hub "ghcr.io/${{ github.repository_owner }}" \
      --addon
```

### Python pip "externally-managed-environment" Solutions

**Problem:** Modern Alpine/Debian systems prevent system pip installs
**Solution:** Use virtual environments in containers:
```dockerfile
RUN python3 -m venv /opt/venv \
    && . /opt/venv/bin/activate \
    && pip3 install --no-cache-dir -r /tmp/requirements.txt
```
Then in service scripts: `export PATH="/opt/venv/bin:$PATH"`

### GitHub Container Registry (GHCR) Permissions

**Problem:** "Upload failed" errors despite successful builds
**Solution:** Enable GitHub Actions permissions:
1. Repo Settings → Actions → General
2. Workflow permissions → "Read and write permissions"  
3. Check "Allow GitHub Actions to create and approve pull requests"

### Architecture Support Strategy

**Modern approach (2025):**
- ✅ `amd64` - Intel/AMD 64-bit (majority of installs)
- ✅ `aarch64` - ARM 64-bit (Raspberry Pi 4+, modern ARM)
- ❌ `armv7`, `armhf`, `i386` - Deprecated (<1.5% usage, build issues)

### Common Pitfalls Avoided

1. **Never use `--break-system-packages`** - Use virtual environments instead
2. **Don't skip the builder parameters** - Need `--image`, `--docker-hub`, `--target`
3. **Always use specific builder versions** - `@master` can break unexpectedly
4. **Copy everything to `rootfs/`** - Don't leave files in project root
5. **Test GitHub Actions permissions early** - Most "mysterious" failures are auth issues

### File Structure Template
```
├── config.yaml          # HA add-on metadata
├── build.yaml           # Multi-arch base images  
├── Dockerfile           # Simple: install deps + copy rootfs
├── requirements.txt     # Python dependencies
├── .github/workflows/   # HA builder workflow
└── rootfs/             # Everything the container needs
    ├── etc/services.d/  # s6-overlay services
    ├── usr/local/src/   # Application code
    ├── usr/local/web/   # Web dashboard
    └── usr/src/app/translations/  # HA translations
```

This guide represents 10+ iterations of trial-and-error to get from "Docker Hell" to successful multi-architecture builds. Follow this template and you'll avoid the pain! 🎯