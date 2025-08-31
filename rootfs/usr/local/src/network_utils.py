#!/usr/bin/env python3
"""
Network utilities for IP detection and validation
"""
import socket
import subprocess
import logging
from typing import Optional, List
import psutil

logger = logging.getLogger(__name__)


def get_addon_ip() -> str:
    """
    Intelligent IP detection for the add-on container.
    Tries multiple methods to find the best IP address to advertise to bulbs.
    
    Returns:
        str: The IP address that bulbs should use to connect back to this add-on
    """
    methods = [
        _get_ip_from_default_route,
        _get_ip_from_docker_network,
        _get_ip_from_hostname_resolution,
        _get_ip_from_network_interfaces,
        _get_ip_from_test_connection
    ]
    
    for method in methods:
        try:
            ip = method()
            if ip and _validate_ip(ip) and not _is_loopback_ip(ip):
                logger.info(f"Detected add-on IP using {method.__name__}: {ip}")
                return ip
        except Exception as e:
            logger.debug(f"IP detection method {method.__name__} failed: {e}")
            continue
    
    # Fallback to a reasonable default
    logger.warning("Could not detect add-on IP, using fallback: 172.30.32.1")
    return "172.30.32.1"


def _get_ip_from_default_route() -> Optional[str]:
    """Get IP from the default route interface"""
    try:
        # Get the default route
        result = subprocess.run(['ip', 'route', 'show', 'default'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return None
        
        # Parse the output to get the interface
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if 'default via' in line:
                parts = line.split()
                if 'dev' in parts:
                    interface = parts[parts.index('dev') + 1]
                    return _get_ip_from_interface(interface)
        return None
    except Exception:
        return None


def _get_ip_from_docker_network() -> Optional[str]:
    """Get IP from Docker bridge network (common in HA add-ons)"""
    try:
        # Check for Docker bridge interfaces
        for interface_name in ['docker0', 'br-+', 'hassio']:
            ip = _get_ip_from_interface(interface_name)
            if ip:
                return ip
        return None
    except Exception:
        return None


def _get_ip_from_hostname_resolution() -> Optional[str]:
    """Get IP by resolving the container hostname"""
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)
    except Exception:
        return None


def _get_ip_from_network_interfaces() -> Optional[str]:
    """Get IP from network interfaces, prioritizing non-loopback"""
    try:
        interfaces = psutil.net_if_addrs()
        
        # Priority order for interface types
        preferred_prefixes = ['eth', 'en', 'wlan', 'docker', 'br-', 'hassio']
        
        candidates = []
        
        for interface_name, addresses in interfaces.items():
            for addr in addresses:
                if addr.family == socket.AF_INET:  # IPv4
                    ip = addr.address
                    if _validate_ip(ip) and not _is_loopback_ip(ip):
                        # Score based on interface name preference
                        score = 0
                        for i, prefix in enumerate(preferred_prefixes):
                            if interface_name.startswith(prefix):
                                score = len(preferred_prefixes) - i
                                break
                        candidates.append((score, ip, interface_name))
        
        # Return the highest scored IP
        if candidates:
            candidates.sort(reverse=True, key=lambda x: x[0])
            best_ip = candidates[0][1]
            best_interface = candidates[0][2]
            logger.info(f"Selected IP {best_ip} from interface {best_interface}")
            return best_ip
        
        return None
    except Exception:
        return None


def _get_ip_from_test_connection() -> Optional[str]:
    """Get local IP by creating a test connection to a public DNS server"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(5)
            # Connect to Google's DNS (doesn't actually send data)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


def _get_ip_from_interface(interface_name: str) -> Optional[str]:
    """Get IP address from a specific network interface"""
    try:
        interfaces = psutil.net_if_addrs()
        if interface_name in interfaces:
            for addr in interfaces[interface_name]:
                if addr.family == socket.AF_INET:  # IPv4
                    return addr.address
        return None
    except Exception:
        return None


def _validate_ip(ip: str) -> bool:
    """Validate that the string is a proper IPv4 address"""
    try:
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        for part in parts:
            if not (0 <= int(part) <= 255):
                return False
        return True
    except (ValueError, AttributeError):
        return False


def _is_loopback_ip(ip: str) -> bool:
    """Check if IP is a loopback address (127.x.x.x)"""
    return ip.startswith('127.')


def get_network_info() -> dict:
    """
    Get comprehensive network information for diagnostics
    
    Returns:
        dict: Network information including interfaces, IPs, and routes
    """
    info = {
        'detected_ip': get_addon_ip(),
        'hostname': socket.gethostname(),
        'interfaces': {},
        'routes': []
    }
    
    try:
        # Get all network interfaces
        interfaces = psutil.net_if_addrs()
        for name, addresses in interfaces.items():
            info['interfaces'][name] = []
            for addr in addresses:
                if addr.family == socket.AF_INET:  # IPv4
                    info['interfaces'][name].append({
                        'ip': addr.address,
                        'netmask': addr.netmask,
                        'broadcast': addr.broadcast
                    })
    except Exception as e:
        logger.error(f"Failed to get interface info: {e}")
    
    try:
        # Get routing table
        result = subprocess.run(['ip', 'route', 'show'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            info['routes'] = result.stdout.strip().split('\n')
    except Exception as e:
        logger.debug(f"Failed to get route info: {e}")
    
    return info