# Changelog

All notable changes to the Sengled Local Server add-on will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.8] - 2025-08-31

### Fixes
- **Actually Intelligent IP Detection** - Ask HA Supervisor for the IP address
- **Fix POST to accessCloud.json** - It's POSTed, not GETten
- **Handle Mangled URLs** - Sengled firmware (maybe only some) mangles HTTP requests
- **Mosquitto broker config fix** - we don't need to specify 256MB when default & max is 256MB-1byte.
- **Killing Uvicorns** - woefully complex, overkill, and can't handle mangled URLs. Sorry friend!

## [1.0.0] - 2025-08-30

### Added
- 🚀 **Initial release** of Sengled Local Server Home Assistant add-on
- **HTTP Provisioning Server** on port 54448 ("light") serving critical Sengled endpoints
  - `/bimqtt` - Returns MQTT broker connection details for bulbs
  - `/accessCloud.json` - Static page so the bulb connects successfully
- **MQTT Broker with SSL** on port 28527 ("bulbs") so stock firmware can connect openly
- **Native MQTT Bridge** - Automatically forwards `wifielement/*` topics to Home Assistant MQTT broker
- **Automatic SSL Certificate Generation** - Creates CA and server certificates on first run
- **Intelligent IP Detection** - Multi-method IP discovery for containerized environments
- **Real-time Web Dashboard** - Comprehensive monitoring interface at port 54448
  - Service status indicators
  - Connection statistics and activity logs
  - Certificate information display
  - Network diagnostics
  - Configuration overview
- **Health Monitoring**
  - Docker health checks
  - HTTP endpoint validation
  - MQTT broker connectivity tests
  - SSL certificate validation
- **Flexible Configuration Options**
  - MQTT broker settings (host, port, credentials, SSL)
  - Bridge enable/disable toggle
  - Certificate common name customization
  - Adjustable logging levels
- **Multi-architecture Support** - ARM64, ARM7, AMD64, i386
  
### Technical Details
- **Mosquitto** MQTT broker with dynamic configuration generation
- **Jinja2** template-based configuration management
- **Python cryptography** for SSL certificate generation
- **Multi-stage Docker build** with Alpine Linux base
- **Bashio** integration for Home Assistant add-on framework
- **Responsive web UI** with real-time updates via JavaScript

### Documentation
- Comprehensive README with setup instructions
- API documentation with endpoint examples
- Troubleshooting guide with common issues and solutions
- Architecture diagrams showing data flow
- Security considerations and best practices
- Complete translation file for Home Assistant UI

### Port Assignments
- **28527** - MQTT Broker ("bulbs" on phone keypad) 
- **54448** - HTTP Server ("light" on phone keypad)

Both port numbers chosen for:
- Memorability through phone keypad word mapping
- Avoidance of common service conflicts
- Security through non-standard port usage

---

## Future Releases

### Planned for v1.1.0
- [ ] Mobile-responsive dashboard improvements
- [ ] MQTT message filtering and transformation options

### Planned for v1.2.0
- [ ] Advanced monitoring and alerting capabilities
- [ ] Performance optimizations for high bulb counts
- [ ] External "app" for bulb WiFi setup via phone browser

### Community Requests
- [ ] Docker and HA Add-On experience for optimization
- [ ] Additional manufacturer support (research needed)
- [ ] Multi-language support for web dashboard

---

## Contributing

We welcome contributions! Please see the [README.md](README.md) for areas where you can help improve the project.

## Support

If you encounter issues:

1. Check the [Troubleshooting section](README.md#troubleshooting) in the README
2. Visit the dashboard at port 54448 for diagnostics
3. Review add-on logs in Home Assistant
4. Open an issue on GitHub with detailed logs and configuration

**🔦 Thank you for helping us light up local networks everywhere! 💡**