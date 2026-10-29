"""See where traffic actually leaves from, and wait for a fresh IP after rotating."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Optional

from .config import ProxyConfig
from .rotation import Rotator

IP_INFO_URL = "https://ipinfo.io/json"

# Mobile-data ASNs first, then each carrier's company/fixed-line ASNs.
ASNS = {
    45143: ("singtel", True),
    7473: ("singtel", False),
    4773: ("m1", True),
    17547: ("m1", False),
    9874: ("starhub", True),
    4657: ("starhub", False),
    55430: ("starhub", False),
}


def exit_ip(config: ProxyConfig, url: Optional[str] = None, timeout: float = 20.0) -> dict:
    """Fetch an IP-info page through the proxy's HTTP port.

    Returns `{"ip", "country", "org", "asn", "carrier", "mobile"}`.
    """
    url = url or os.environ.get("SMP_IP_INFO_URL") or IP_INFO_URL
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": config.http_url, "https": config.http_url}))
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "curl/8"})
    with opener.open(req, timeout=timeout) as resp:
        data = json.load(resp)
    org = data.get("org") or ""
    first = org.split()[0] if org else ""
    asn = int(first[2:]) if first.startswith("AS") and first[2:].isdigit() else None
    carrier, mobile = ASNS.get(asn, ("unknown", False))
    return {"ip": data.get("ip"), "country": data.get("country"), "org": org,
            "asn": f"AS{asn}" if asn else None, "carrier": carrier, "mobile": mobile}


def rotate_and_wait(config: ProxyConfig, rotator: Rotator, timeout: float = 90.0,
                    poll_every: float = 3.0) -> dict:
    """Rotate, then poll until the proxy answers again.

    Returns `{"old_ip", "new_ip", "changed"}`. Mobile carriers sometimes hand the same
    IP back; `changed` is False then, and you can rotate again after the cooldown.
    """
    try:
        old_ip = exit_ip(config)["ip"]
    except OSError:
        old_ip = None
    rotator.rotate()
    deadline = time.monotonic() + timeout
    while True:
        try:
            new_ip = exit_ip(config, timeout=min(20.0, timeout))["ip"]
            break
        except OSError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"the proxy did not answer within {timeout:g}s after rotating") from None
            time.sleep(poll_every)
    return {"old_ip": old_ip, "new_ip": new_ip, "changed": bool(old_ip) and new_ip != old_ip}
