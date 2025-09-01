#!/usr/bin/env python3
"""
MQTT Listener for Sengled Local Server

Connects to the local MQTT broker using generated SSL certificates
and listens for device status messages to update the device storage.
"""

import os
import ssl
import time
import logging
import threading
from pathlib import Path
from typing import Optional

import paho.mqtt.client as mqtt

from device_storage import DeviceStorage
from network_utils import get_addon_ip

logger = logging.getLogger(__name__)

class SengledMQTTListener:
    """MQTT listener for Sengled device status messages"""
    
    def __init__(self, broker_host: Optional[str] = None, broker_port: int = 28527, 
                 storage_dir: str = "/data/devices", certs_dir: str = "/data/certs"):
        """
        Initialize MQTT listener
        
        Args:
            broker_host: MQTT broker host (auto-detected if None)
            broker_port: MQTT broker port 
            storage_dir: Directory for device storage
            certs_dir: Directory containing SSL certificates
        """
        self.broker_host = broker_host or get_addon_ip()
        self.broker_port = broker_port
        self.certs_dir = Path(certs_dir)
        
        # Initialize device storage
        self.storage = DeviceStorage(storage_dir)
        
        # MQTT client setup
        self.client = mqtt.Client(
            client_id="sengled-server-listener",
            protocol=mqtt.MQTTv311,
            transport="tcp"
        )
        
        # Connection state
        self.connected = False
        self.running = False
        self.listener_thread = None
        
        # Statistics
        self.stats = {
            'messages_received': 0,
            'messages_processed': 0,
            'connection_attempts': 0,
            'last_message': None,
            'start_time': time.time()
        }
        
        self._setup_mqtt_client()
        
    def _setup_mqtt_client(self):
        """Configure MQTT client with SSL and callbacks"""
        # Set up SSL/TLS
        try:
            ca_cert = self.certs_dir / "ca.crt"
            client_cert = self.certs_dir / "server.crt"
            client_key = self.certs_dir / "server.key"
            
            if all(cert.exists() for cert in [ca_cert, client_cert, client_key]):
                context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                context.check_hostname = False  # Allow self-signed certificates
                context.verify_mode = ssl.CERT_REQUIRED
                context.load_verify_locations(str(ca_cert))
                context.load_cert_chain(str(client_cert), str(client_key))
                
                self.client.tls_set_context(context)
                logger.info("SSL/TLS configured with generated certificates")
            else:
                logger.warning("SSL certificates not found, attempting insecure connection")
                
        except Exception as e:
            logger.error(f"Failed to setup SSL: {e}")
        
        # Set up callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_log = self._on_log
        
        # Connection settings
        self.client.reconnect_delay_set(min_delay=1, max_delay=120)
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for successful MQTT connection"""
        if rc == 0:
            self.connected = True
            logger.info(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}")
            
            # Subscribe to all device status topics
            topics = [
                ("wifielement/+/status", 0),           # Device status messages
                ("wifielement/+/consumptionTime", 0),  # Optional consumption data
                ("wifielement/+/consumption", 0),      # Optional consumption data
            ]
            
            for topic, qos in topics:
                result = client.subscribe(topic, qos)
                logger.info(f"Subscribed to {topic} (result: {result})")
                
        else:
            self.connected = False
            logger.error(f"Failed to connect to MQTT broker: {mqtt.connack_string(rc)}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection"""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected MQTT disconnection: {mqtt.error_string(rc)}")
        else:
            logger.info("MQTT client disconnected")
    
    def _on_message(self, client, userdata, msg):
        """Callback for received MQTT messages"""
        try:
            self.stats['messages_received'] += 1
            self.stats['last_message'] = time.time()
            
            topic = msg.topic
            payload = msg.payload.decode('utf-8', errors='ignore')
            
            logger.debug(f"Received message on {topic}: {payload[:100]}...")
            
            # Process the message through device storage
            if self.storage.process_mqtt_message(topic, payload):
                self.stats['messages_processed'] += 1
                logger.debug(f"Successfully processed message from {topic}")
            
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
    
    def _on_log(self, client, userdata, level, buf):
        """Callback for MQTT client logging"""
        if level == mqtt.MQTT_LOG_DEBUG:
            logger.debug(f"MQTT: {buf}")
        elif level == mqtt.MQTT_LOG_INFO:
            logger.debug(f"MQTT: {buf}")
        elif level == mqtt.MQTT_LOG_WARNING:
            logger.warning(f"MQTT: {buf}")
        elif level == mqtt.MQTT_LOG_ERR:
            logger.error(f"MQTT: {buf}")
    
    def start(self):
        """Start the MQTT listener in a separate thread"""
        if self.running:
            logger.warning("MQTT listener is already running")
            return
        
        self.running = True
        self.listener_thread = threading.Thread(target=self._run_listener, daemon=True)
        self.listener_thread.start()
        logger.info("MQTT listener started")
    
    def stop(self):
        """Stop the MQTT listener"""
        if not self.running:
            return
        
        logger.info("Stopping MQTT listener...")
        self.running = False
        
        if self.connected:
            self.client.disconnect()
        
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=5.0)
        
        logger.info("MQTT listener stopped")
    
    def _run_listener(self):
        """Main listener loop (runs in separate thread)"""
        retry_delay = 10  # Start with 10 second delay
        max_retry_delay = 120  # Max 2 minutes between retries
        
        while self.running:
            try:
                if not self.connected:
                    logger.info(f"Attempting to connect to MQTT broker at {self.broker_host}:{self.broker_port}")
                    self.stats['connection_attempts'] += 1
                    
                    # Use loop_forever with retry_first_connection=False to prevent automatic retries
                    # We want to control the retry logic ourselves
                    try:
                        result = self.client.connect(self.broker_host, self.broker_port, 60)
                        if result == 0:
                            logger.debug("Connection initiated, starting network loop...")
                            # Use blocking loop_forever but with our own retry control
                            self.client.loop_forever(retry_first_connection=False)
                            # If we get here, connection was lost
                            self.connected = False
                            logger.warning("MQTT connection lost")
                        else:
                            logger.error(f"Failed to connect: {mqtt.error_string(result)}")
                            raise ConnectionError(f"MQTT connect failed: {result}")
                            
                    except Exception as conn_error:
                        logger.error(f"Connection error: {conn_error}")
                        if self.connected:
                            self.client.disconnect()
                            self.connected = False
                        
                        if self.running:  # Only retry if we're still supposed to be running
                            logger.info(f"Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, max_retry_delay)
                        continue
                
            except Exception as e:
                logger.error(f"MQTT listener error: {e}")
                if self.running:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry_delay)
    
    def get_status(self) -> dict:
        """Get current status of the MQTT listener"""
        uptime = time.time() - self.stats['start_time']
        
        return {
            'connected': self.connected,
            'running': self.running,
            'broker': f"{self.broker_host}:{self.broker_port}",
            'uptime_seconds': round(uptime, 2),
            'statistics': {
                'messages_received': self.stats['messages_received'],
                'messages_processed': self.stats['messages_processed'],
                'connection_attempts': self.stats['connection_attempts'],
                'last_message': self.stats['last_message']
            },
            'storage': self.storage.get_storage_stats()
        }
    
    def get_devices(self) -> dict:
        """Get all stored devices"""
        return self.storage.get_all_devices()
    
    def get_device(self, mac: str) -> Optional[dict]:
        """Get single device by MAC address"""
        return self.storage.get_device(mac)


def main():
    """Standalone script to run MQTT listener"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    listener = SengledMQTTListener()
    
    try:
        logger.info("Starting Sengled MQTT Listener...")
        listener.start()
        
        # Keep running until interrupted
        while True:
            time.sleep(10)
            status = listener.get_status()
            logger.info(f"Status: Connected={status['connected']}, "
                       f"Messages={status['statistics']['messages_received']}, "
                       f"Devices={status['storage']['total_devices']}")
                       
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        listener.stop()


if __name__ == "__main__":
    main()