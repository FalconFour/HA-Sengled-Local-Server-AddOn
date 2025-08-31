# network_utils.py
import os
import json
import socket
import ipaddress
import subprocess
import logging
from typing import Optional, Dict, Any, List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import psutil

logger = logging.getLogger(__name__)

SUPERVISOR_BASE = "http://supervisor"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")


# -------------------------
# Internal helpers (Supervisor)
# -------------------------

def _http_supervisor_get(path: str, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    """Minimal Supervisor GET helper. Returns parsed JSON 'data' or None."""
    if not SUPERVISOR_TOKEN:
        logger.debug("SUPERVISOR_TOKEN not set; skipping Supervisor lookup.")
        return None

    url = f"{SUPERVISOR_BASE}{path}"
    req = Request(url, headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                logger.debug(f"Supervisor GET {path} returned HTTP {resp.status}")
                return None
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            result = data.get("data") if isinstance(data, dict) else None
            if result is None:
                logger.debug(f"Supervisor GET {path} had unexpected payload: {raw[:200]}...")
            return result
    except (URLError, HTTPError, TimeoutError, ValueError) as e:
        logger.debug(f"Supervisor GET {path} failed: {e}")
        return None


def _pick_ipv4(addresses: List[str]) -> Optional[str]:
    """
    Given a list of CIDR strings, return a single IPv4 address (no CIDR).
    Prefer RFC1918 private space; else first IPv4.
    """
    ipv4s: List[ipaddress.IPv4Address] = []
    for cidr in addresses:
        try:
            ip_str = cidr.split("/", 1)[0]
            ip_obj = ipaddress.ip_address(ip_str)
            if isinstance(ip_obj, ipaddress.IPv4Address):
                ipv4s.append(ip_obj)
        except ValueError:
            continue

    if not ipv4s:
        return None

    for ip in ipv4s:
        if ip.is_private:
            return str(ip)
    return str(ipv4s[0])


def _get_ipv4_from_default_interface() -> Optional[str]:
    """Ask Supervisor for primary/default interface and pick an IPv4."""
    data = _http_supervisor_get("/network/interface/default/info")
    if not data:
        return None

    if not data.get("connected"):
        logger.debug("Supervisor default interface reports connected=false.")
        return None

    ipv4 = (data.get("ipv4") or {}).get("addresses") or []
    picked = _pick_ipv4(ipv4)
    if picked:
        logger.info(f"Supervisor default interface provided IPv4 {picked}")
        return picked

    logger.debug("Supervisor default interface had no usable IPv4.")
    return None


def _get_ipv4_from_network_info() -> Optional[str]:
    """Fallback: scan Supervisor /network/info for a primary+connected iface with IPv4."""
    data = _http_supervisor_get("/network/info")
    if not data:
        return None

    # First pass: primary+connected
    for iface in data.get("interfaces", []):
        if iface.get("primary") and iface.get("connected"):
            ipv4 = (iface.get("ipv4") or {}).get("addresses") or []
            picked = _pick_ipv4(ipv4)
            if picked:
                logger.info(f"Supervisor network info picked primary iface {iface.get('interface')} IPv4 {picked}")
                return picked

    # Second pass: any connected with IPv4
    for iface in data.get("interfaces", []):
        if iface.get("connected"):
            ipv4 = (iface.get("ipv4") or {}).get("addresses") or []
            picked = _pick_ipv4(ipv4)
            if picked:
                logger.info(f"Supervisor network info picked connected iface {iface.get('interface')} IPv4 {picked}")
                return picked

    logger.debug("Supervisor network info had no usable connected IPv4.")
    return None


# -------------------------
# Last-resort container heuristics
# -------------------------

def _container_guess_ipv4() -> Optional[str]:
    """
    Try to infer an outward-facing IPv4 from inside the container.
    This is deliberately last-resort behind Supervisor truth.
    """
    # UDP "connect" trick—no packets need to be sent
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("1.1.1.1", 53))
            ip = s.getsockname()[0]
            ip_obj = ipaddress.ip_address(ip)
            if isinstance(ip_obj, ipaddress.IPv4Address):
                logger.warning(f"Falling back to container IPv4 guess via UDP connect: {ip}")
                return ip
    except Exception as e:
        logger.debug(f"Container UDP connect trick failed: {e}")

    # Scan interfaces; prefer private IPv4
    try:
        for name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET:
                    try:
                        ip_obj = ipaddress.ip_address(a.address)
                        if isinstance(ip_obj, ipaddress.IPv4Address) and ip_obj.is_private:
                            logger.warning(f"Falling back to container interface {name} IPv4 {a.address}")
                            return a.address
                    except ValueError:
                        continue
    except Exception as e:
        logger.debug(f"Container interface scan failed: {e}")

    return None


# -------------------------
# Public API
# -------------------------

def get_addon_ip() -> str:
    """
    Robust IPv4 for LAN clients (bulbs). Prefers Supervisor's view of the host.
    """
    # 1) Preferred
    ip = _get_ipv4_from_default_interface()
    if ip:
        return ip

    # 2) Fallback via /network/info
    ip = _get_ipv4_from_network_info()
    if ip:
        return ip

    # 3) Last-resort: container heuristics
    ip = _container_guess_ipv4()
    if ip:
        return ip

    logger.error("No IPv4 address could be determined; returning 0.0.0.0")
    return "0.0.0.0"


def get_network_info() -> dict:
    """
    Container-centric diagnostics for add-on UI:
    - Enumerate interfaces (IPv4 only) as seen from inside the container
    - Show routing table from the container
    - Include the currently detected LAN IPv4 (via get_addon_ip) for convenience
    """
    info = {
        "detected_ip": get_addon_ip(),   # keep: handy to display in the UI
        "hostname": socket.gethostname(),
        "interfaces": {},
        "routes": []
    }

    # Interfaces (container view)
    try:
        interfaces = psutil.net_if_addrs()
        for name, addresses in interfaces.items():
            info["interfaces"][name] = []
            for addr in addresses:
                if addr.family == socket.AF_INET:  # IPv4 only for your bulbs
                    info["interfaces"][name].append({
                        "ip": addr.address,
                        "netmask": addr.netmask,
                        "broadcast": addr.broadcast
                    })
        logger.debug(f"Collected {len(info['interfaces'])} interfaces from container view.")
    except Exception as e:
        logger.error(f"Failed to get interface info: {e}")

    # Routing (container view)
    try:
        result = subprocess.run(
            ["ip", "route", "show"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info["routes"] = [line for line in result.stdout.strip().split("\n") if line]
            logger.debug(f"Collected {len(info['routes'])} routes from container view.")
        else:
            logger.debug(f"'ip route show' returned code {result.returncode}: {result.stderr.strip()}")
    except Exception as e:
        logger.debug(f"Failed to get route info: {e}")

    return info
