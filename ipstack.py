"""
IPStack geolocation integration for pocketSearch.

Provides a lightweight, cache-aware client for resolving public IP metadata
while keeping the implementation optional and failure-tolerant.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

logger = logging.getLogger("webscope.ipstack")

_IPSTACK_BASE_URL = os.environ.get("IPSTACK_BASE_URL", "https://api.ipstack.com")
_IPSTACK_ACCESS_KEY = os.environ.get("IPSTACK_ACCESS_KEY", "").strip()
_IPSTACK_TIMEOUT = float(os.environ.get("IPSTACK_TIMEOUT", "5"))
_IPSTACK_CACHE_TTL = int(os.environ.get("IPSTACK_CACHE_TTL", "3600"))

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; WebScope/1.0)"})
_cache: dict[str, tuple[dict[str, Any], float]] = {}


@dataclass(frozen=True)
class IpstackResult:
    ip: str
    available: bool
    data: dict[str, Any]
    error: Optional[str] = None


def _is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
        return not (ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast)
    except ValueError:
        return False


def _cache_get(key: str) -> Optional[dict[str, Any]]:
    item = _cache.get(key)
    if not item:
        return None
    payload, ts = item
    if time.time() - ts > _IPSTACK_CACHE_TTL:
        _cache.pop(key, None)
        return None
    return payload


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    _cache[key] = (payload, time.time())


def lookup_ip(ip: str) -> IpstackResult:
    ip = (ip or "").strip()
    if not ip:
        return IpstackResult(ip="", available=False, data={}, error="empty ip")
    if not _is_public_ip(ip):
        return IpstackResult(ip=ip, available=False, data={}, error="non-public ip")
    if not _IPSTACK_ACCESS_KEY:
        return IpstackResult(ip=ip, available=False, data={}, error="ipstack not configured")

    cached = _cache_get(ip)
    if cached is not None:
        return IpstackResult(ip=ip, available=True, data=cached)

    url = f"{_IPSTACK_BASE_URL.rstrip('/')}/{ip}"
    params = {"access_key": _IPSTACK_ACCESS_KEY, "format": 1}
    try:
        resp = _session.get(url, params=params, timeout=_IPSTACK_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("success") is False:
            return IpstackResult(ip=ip, available=False, data=payload, error=payload.get("error", {}).get("info", "ipstack error"))
        if not isinstance(payload, dict):
            return IpstackResult(ip=ip, available=False, data={}, error="invalid response")
        _cache_set(ip, payload)
        return IpstackResult(ip=ip, available=True, data=payload)
    except Exception as exc:
        logger.debug("ipstack lookup failed for %s: %s", ip, exc)
        return IpstackResult(ip=ip, available=False, data={}, error=str(exc))


def enrich_result(result: dict[str, Any]) -> dict[str, Any]:
    ip = result.get("ip") or result.get("address") or result.get("host") or ""
    lookup = lookup_ip(ip)
    enriched = dict(result)
    enriched["ipstack"] = {
        "available": lookup.available,
        "error": lookup.error,
        "data": lookup.data,
    }
    if lookup.available:
        enriched.setdefault("geo", {})
        enriched["geo"].update({
            "country": lookup.data.get("country_name"),
            "region": lookup.data.get("region_name"),
            "city": lookup.data.get("city"),
            "latitude": lookup.data.get("latitude"),
            "longitude": lookup.data.get("longitude"),
            "timezone": lookup.data.get("time_zone", {}).get("id") if isinstance(lookup.data.get("time_zone"), dict) else None,
            "asn": lookup.data.get("connection", {}).get("asn") if isinstance(lookup.data.get("connection"), dict) else None,
            "isp": lookup.data.get("connection", {}).get("isp") if isinstance(lookup.data.get("connection"), dict) else None,
        })
    return enriched
