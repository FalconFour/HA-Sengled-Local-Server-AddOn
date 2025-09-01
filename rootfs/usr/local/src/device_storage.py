#!/usr/bin/env python3
"""
Device Storage Manager for Sengled Local Server

Handles persistent storage of device information from MQTT status messages.
Stores device data as JSON files in /data/devices/ for HA add-on persistence.
"""

import json
import os
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class DeviceStorage:
    """Manages persistent device storage and retrieval"""
    
    # Storage limits to prevent unbounded growth
    MAX_DEVICES = 200
    MAX_DEVICE_SIZE_BYTES = 1024 * 1024  # 1MB per device
    MAX_TOTAL_SIZE_BYTES = 10 * 1024 * 1024  # 10MB total storage
    
    def __init__(self, storage_dir: str = "/data/devices"):
        """Initialize device storage with specified directory"""
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.devices_file = self.storage_dir / "devices.json"
        
        # In-memory cache for quick access
        self._devices = {}
        self._load_devices()
        
        logger.info(f"Device storage initialized at {self.storage_dir}")
        logger.info(f"Storage limits: {self.MAX_DEVICES} devices, {self.MAX_DEVICE_SIZE_BYTES//1024}KB per device")
    
    def _load_devices(self):
        """Load devices from persistent storage"""
        try:
            if self.devices_file.exists():
                with open(self.devices_file, 'r') as f:
                    self._devices = json.load(f)
                logger.info(f"Loaded {len(self._devices)} devices from storage")
            else:
                self._devices = {}
                logger.info("No existing device storage found, starting fresh")
        except Exception as e:
            logger.error(f"Failed to load devices: {e}")
            self._devices = {}
    
    def _save_devices(self):
        """Save devices to persistent storage"""
        try:
            # Write to temporary file first, then atomic rename
            temp_file = self.devices_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self._devices, f, indent=2)
            
            # Atomic rename on Unix systems
            temp_file.replace(self.devices_file)
            logger.debug(f"Saved {len(self._devices)} devices to storage")
        except Exception as e:
            logger.error(f"Failed to save devices: {e}")
    
    def parse_status_message(self, payload: str) -> Optional[Dict[str, Any]]:
        """
        Parse MQTT status message payload into structured data
        
        Expected format: [{"dn":"MAC","type":"brightness","value":"25","time":"41"}, ...]
        Returns: {"brightness": "25", "switch": "1", ...} or None if invalid
        """
        try:
            # Parse JSON array
            status_list = json.loads(payload)
            
            if not isinstance(status_list, list) or not status_list:
                return None
            
            # Convert list of status items to dictionary
            parsed_data = {}
            mac = None
            
            for item in status_list:
                if not isinstance(item, dict):
                    continue
                
                # Extract MAC from first item
                if mac is None:
                    mac = item.get('dn')
                
                # Add type/value pairs
                type_key = item.get('type')
                value = item.get('value')
                
                if type_key and value is not None:
                    parsed_data[type_key] = value
            
            return {
                'mac': mac,
                'attributes': parsed_data,
                'timestamp': int(time.time() * 1000)  # milliseconds
            }
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse status message: {e}")
            return None
    
    def update_device(self, mac: str, status_data: Dict[str, Any]):
        """Update device information from parsed status data"""
        if not mac:
            logger.warning("Cannot update device without MAC address")
            return False
        
        mac = mac.upper()  # Normalize MAC address format
        current_time = int(time.time() * 1000)
        
        # Check device count limit (only for new devices)
        is_new_device = mac not in self._devices
        if is_new_device and len(self._devices) >= self.MAX_DEVICES:
            logger.warning(f"Device limit reached ({self.MAX_DEVICES}), ignoring new device {mac}")
            return False
        
        # Get existing device or create new one
        device = self._devices.get(mac, {
            'mac': mac,
            'first_seen': current_time,
            'last_seen': current_time,
            'capabilities': [],
            'attributes': {}
        })
        
        # Update last seen timestamp
        device['last_seen'] = current_time
        
        # Update attributes from status data with size checking
        if 'attributes' in status_data:
            # Create updated attributes dict
            updated_attributes = device['attributes'].copy()
            updated_attributes.update(status_data['attributes'])
            
            # Check device size limit
            device_json = json.dumps(updated_attributes)
            if len(device_json.encode('utf-8')) > self.MAX_DEVICE_SIZE_BYTES:
                logger.warning(f"Device {mac} data too large ({len(device_json)} chars), skipping update")
                return False
            
            device['attributes'] = updated_attributes
        
        # Extract capabilities from supportAttributes if present
        if 'supportAttributes' in device['attributes']:
            caps_str = device['attributes']['supportAttributes']
            device['capabilities'] = [cap.strip() for cap in caps_str.split(',')]
        
        # Store updated device
        self._devices[mac] = device
        self._save_devices()
        
        logger.info(f"Updated device {mac} with {len(status_data.get('attributes', {}))} attributes")
        return True
    
    def process_mqtt_message(self, topic: str, payload: str) -> bool:
        """
        Process incoming MQTT message and update device storage
        
        Args:
            topic: MQTT topic (e.g., "wifielement/B0:CE:18:C3:3A:A2/status")
            payload: Message payload
            
        Returns:
            True if processed successfully, False otherwise
        """
        try:
            # Extract MAC from topic
            topic_parts = topic.split('/')
            if len(topic_parts) < 3 or topic_parts[0] != 'wifielement':
                logger.debug(f"Ignoring non-device topic: {topic}")
                return False
            
            mac = topic_parts[1]
            message_type = topic_parts[2]
            
            # Only process status messages (ignore individual attribute updates)
            if message_type != 'status':
                logger.debug(f"Ignoring non-status message: {topic}")
                return False
            
            # Parse the status payload
            parsed = self.parse_status_message(payload)
            if not parsed:
                logger.warning(f"Failed to parse status message from {mac}")
                return False
            
            # Only process comprehensive status messages (not single attributes)
            # This filters out the short "supportAttributes" messages
            if len(parsed['attributes']) < 5:  # Threshold for "comprehensive" status
                logger.debug(f"Skipping short status message from {mac} ({len(parsed['attributes'])} attributes)")
                return False
            
            # Update device storage
            return self.update_device(mac, parsed)
            
        except Exception as e:
            logger.error(f"Error processing MQTT message {topic}: {e}")
            return False
    
    def get_device(self, mac: str) -> Optional[Dict[str, Any]]:
        """Get single device by MAC address"""
        mac = mac.upper()
        return self._devices.get(mac)
    
    def get_all_devices(self) -> Dict[str, Dict[str, Any]]:
        """Get all devices grouped by MAC address"""
        return dict(self._devices)
    
    def get_device_count(self) -> int:
        """Get total number of stored devices"""
        return len(self._devices)
    
    def cleanup_old_devices(self, max_age_days: int = 30):
        """Remove devices not seen for specified number of days"""
        cutoff_time = int((time.time() - (max_age_days * 24 * 3600)) * 1000)
        
        old_devices = [
            mac for mac, device in self._devices.items()
            if device.get('last_seen', 0) < cutoff_time
        ]
        
        for mac in old_devices:
            del self._devices[mac]
            logger.info(f"Removed old device {mac}")
        
        if old_devices:
            self._save_devices()
        
        return len(old_devices)
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics and health info"""
        try:
            file_size = self.devices_file.stat().st_size if self.devices_file.exists() else 0
        except:
            file_size = 0
        
        # Calculate storage usage
        total_devices = len(self._devices)
        device_usage_pct = (total_devices / self.MAX_DEVICES) * 100 if self.MAX_DEVICES > 0 else 0
        storage_usage_pct = (file_size / self.MAX_TOTAL_SIZE_BYTES) * 100 if self.MAX_TOTAL_SIZE_BYTES > 0 else 0
        
        return {
            'total_devices': total_devices,
            'max_devices': self.MAX_DEVICES,
            'device_usage_percent': round(device_usage_pct, 1),
            'storage_file': str(self.devices_file),
            'file_size_bytes': file_size,
            'max_file_size_bytes': self.MAX_TOTAL_SIZE_BYTES,
            'storage_usage_percent': round(storage_usage_pct, 1),
            'last_updated': max([dev.get('last_seen', 0) for dev in self._devices.values()] or [0]),
            'limits': {
                'max_devices': self.MAX_DEVICES,
                'max_device_size_bytes': self.MAX_DEVICE_SIZE_BYTES,
                'max_total_size_bytes': self.MAX_TOTAL_SIZE_BYTES
            }
        }