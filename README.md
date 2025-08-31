# 🔦 Sengled Local Server - Home Assistant Add-on 💡

**Keep your Sengled bulbs local and secure!** This add-on provides the essential HTTP and MQTT infrastructure needed to operate Sengled WiFi bulbs without cloud connectivity, seamlessly integrating with your Home Assistant setup.

## ✨ Features

- **🌐 HTTP Provisioning Server** - Serves critical endpoints on port 54448 ("light")
- **🔌 MQTT Broker with SSL** - Secure broker on port 28527 ("bulbs") 
- **🌉 Native MQTT Bridge** - Auto-forwards bulb data to your HA MQTT broker
- **🔒 Auto SSL Certificates** - Generates CA and server certificates for Sengled broker automatically
- **📊 Real-time Dashboard** - Monitor connections and activity at port 54448
- **🎯 Zero Configuration** - Works out of the box with intelligent defaults
- **🔧 Highly Configurable** - Fine-tune bridge settings through HA UI

## 🚀 Quick Start

### 1. Install the Add-on

1. Add this repository to your Home Assistant add-on store
2. Install the "Sengled Local Server" add-on
3. Configure your MQTT broker settings (see [Configuration](#configuration))
4. Start the add-on

### 2. Configure Your Bulbs

During WiFi setup, use your Home Assistant's IP address with these endpoints:

- **bimqtt endpoint**: `http://YOUR_HA_IP:54448/bimqtt`
- **accessCloud endpoint**: `http://YOUR_HA_IP:54448/accessCloud.json`

### 3. Monitor & Control

- **Dashboard**: Visit `http://YOUR_HA_IP:54448/` for real-time monitoring  
- **API Docs**: Check `http://YOUR_HA_IP:54448/docs` for full API documentation
- **Health Check**: Monitor service health at `http://YOUR_HA_IP:54448/health`

## ⚙️ Configuration

### Basic Configuration

```yaml
mqtt_broker_host: "core-mosquitto"    # Your MQTT broker hostname/IP
mqtt_broker_port: 1883                # MQTT broker port  
mqtt_username: ""                     # MQTT username (if required)
mqtt_password: ""                     # MQTT password (if required)
mqtt_ssl: false                       # Enable if your broker uses SSL
enable_bridge: true                   # Forward bulb topics to your broker
log_level: "info"                     # debug, info, warning, error
auto_generate_certs: true             # Auto-generate SSL certificates
cert_common_name: "sengled.local"     # Certificate common name
```

### Advanced Configuration

For most users, the default settings work perfectly. Advanced users can:

- Disable bridging for standalone operation
- Provide custom SSL certificates
- Adjust logging levels for troubleshooting
- Configure specific MQTT credentials

## 🌉 How the MQTT Bridge Works

```
Sengled Bulb --SSL--> Local MQTT (28527) --Bridge--> Your MQTT Broker ---> Home Assistant
```

1. **Bulbs connect** to the local MQTT broker on port 28527 using SSL
2. **Topics are bridged** - `wifielement/*` topics are forwarded to your HA broker
3. **HA integration** can subscribe to these topics for bulb control and status

### Topic Structure

Bulbs publish to topics like:
- `wifielement/B0:CE:18:12:34:56/status` - Bulb status and attributes
- `wifielement/B0:CE:18:12:34:56/consumption` - Power consumption data
- `wifielement/B0:CE:18:12:34:56/consumptionTime` - Energy usage over time

And subscribe to:
- `wifielement/B0:CE:18:12:34:56/update` - Commands from HA

## 🔍 Monitoring & Diagnostics

### Dashboard Features

Visit `http://YOUR_HA_IP:54448/` to access:

- **Service Status** - Real-time health of HTTP and MQTT services
- **Connection Stats** - Number of requests, unique clients, uptime
- **Certificate Info** - SSL certificate status and expiration
- **Network Details** - IP detection and interface information  
- **Activity Log** - Recent connections and events
- **Configuration View** - Current bridge settings

### Health Checks

The add-on includes comprehensive health monitoring:

```bash
# Quick health check
curl http://YOUR_HA_IP:54448/health

# Detailed service status  
curl http://YOUR_HA_IP:54448/status

# Network diagnostics
curl http://YOUR_HA_IP:54448/network
```

## 🛠️ Troubleshooting

### Bulbs Won't Connect

1. **Verify endpoints are accessible**:
   ```bash
   curl http://YOUR_HA_IP:54448/bimqtt
   curl http://YOUR_HA_IP:54448/accessCloud.json
   ```

2. **Check the dashboard** for connection attempts and errors

3. **Verify certificates** are generated (check add-on logs)

4. **Ensure network connectivity** between bulbs and Home Assistant

### Bridge Issues

1. **Test MQTT broker connectivity**:
   ```bash
   mosquitto_pub -h YOUR_MQTT_HOST -t test/topic -m "test"
   ```

2. **Check bridge status** in the dashboard

3. **Verify credentials** if using authenticated MQTT

4. **Review logs** for connection errors

### Certificate Problems

1. **Restart the add-on** to regenerate certificates
2. **Check certificate common name** matches your setup  
3. **Verify file permissions** in `/data/certs/`

## 🔒 Security Considerations

**Why non-standard ports?** Since Sengled bulbs don't implement authentication, we use several hardening measures:

- **Custom port assignment** - You control exactly which ports bulbs connect to during WiFi setup
- **SSL encryption** protects MQTT communication with encrypted messages
- **Access control lists** limit bulbs to only their own topics (`wifielement/{MAC}/...`) 
- **Local-only operation** eliminates cloud dependencies and external attack vectors
- **Network isolation** possible by restricting these ports to your local network only

The port strategy provides **configurability and control** rather than relying on obscurity.

## 📋 API Reference

### Core Endpoints

- `GET /bimqtt` - Returns MQTT broker connection details for bulbs
- `GET /accessCloud.json` - Returns cloud access status (success)
- `GET /health` - Service health check
- `GET /status` - Detailed service status and statistics
- `GET /network` - Network information and diagnostics
- `GET /` - Web dashboard interface

### Response Examples

**bimqtt endpoint**:
```json
{
  "protocal": "mqtt",
  "host": "192.168.1.100", 
  "port": 28527
}
```

**accessCloud endpoint**:
```json
{
  "messageCode": "200",
  "info": "OK",
  "description": "正常", 
  "success": true
}
```

## 🏗️ Architecture

```
┌─────────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
│   Sengled Bulbs     │    │  Local Server Add-on │    │  Home Assistant     │
│                     │    │                      │    │                     │
│ Power-On Setup ─────┼───▶│ HTTP Server :54448   │    │ MQTT Integration    │
│                     │    │ - /bimqtt            │    │                     │
│ MQTT Client ────────┼───▶│ - /accessCloud.json  │    │ Automation Rules    │
│                     │    │                      │    │                     │
│ SSL Connection ─────┼───▶│ MQTT Broker :28527   │───▶│ Dashboard & Control │
│                     │    │ - SSL/TLS enabled    │    │                     │
│ wifielement/* topics│    │ - Bridge to HA MQTT │    │                     │
└─────────────────────┘    └──────────────────────┘    └─────────────────────┘
```

## 🤝 Contributing

This project welcomes contributions! Areas for enhancement:

- Additional bulb manufacturer support
- Enhanced monitoring and alerting  
- Integration with Home Assistant energy dashboard
- Mobile-responsive dashboard improvements
- Multi-language translations

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [SengledTools](https://github.com/HamzaETTH/SengledTools) project
- Home Assistant add-on developers and documentation writers
- Mosquitto MQTT broker project
- FastAPI framework team

---

**🔦 Light up your local network! 💡** 

Vibe-coded in Claude Code by Matt Falcon - contribute if you can do better! Made with ❤️ for the Home Assistant community.