"""Ask for a new IP, through the rotation link or the authenticated API."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Mapping, Optional
from urllib.parse import quote

from .config import ConfigError, Getter, _env_getter

API_BASE = "https://singaporemobileproxy.com/api/v1"

# The server enforces these per line. Checking them here first saves a round trip
# and gives a clear error instead of a 429.
LINK_MIN_INTERVAL = 240  # rotation link: once every 4 minutes
API_MIN_INTERVAL = 300   # /proxy/change-ip: once every 5 minutes


class RotationError(RuntimeError):
    """The rotation request failed."""


class RotationCooldown(RotationError):
    """This line rotated too recently. `retry_after` is in seconds."""

    def __init__(self, retry_after: int, message: str = ""):
        self.retry_after = max(0, int(retry_after))
        super().__init__(message or f"rotation is cooling down, try again in {self.retry_after}s")


class Rotator:
    """Rotate one line's IP.

    Give it either the rotation link from your dashboard (`rotate_url`), or an API key
    plus the license UUID of the line (`api_key` + `license`).
    """

    def __init__(
        self,
        rotate_url: Optional[str] = None,
        api_key: Optional[str] = None,
        license: Optional[str] = None,
        api_base: str = API_BASE,
        min_interval: Optional[float] = None,
        timeout: float = 45.0,
    ):
        if rotate_url:
            self.mode = "link"
        elif api_key and license:
            self.mode = "api"
        else:
            raise ConfigError(
                "No rotation configured. Set SMP_ROTATE_URL to the rotation link from your dashboard, "
                "or SMP_API_KEY plus SMP_LICENSE."
            )
        self.rotate_url = rotate_url
        self.api_key = api_key
        self.license = license
        self.api_base = api_base.rstrip("/")
        default = LINK_MIN_INTERVAL if self.mode == "link" else API_MIN_INTERVAL
        self.min_interval = default if min_interval is None else min_interval
        self.timeout = timeout
        self._next_allowed = 0.0
        # Always go direct: if HTTPS_PROXY points at this very line, rotating through it
        # would cut the request off mid-redial.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None, **kwargs) -> "Rotator":
        return cls.from_getter(_env_getter(environ), **kwargs)

    @classmethod
    def from_getter(cls, get: Getter, **kwargs) -> "Rotator":
        return cls(rotate_url=get("SMP_ROTATE_URL"), api_key=get("SMP_API_KEY"),
                   license=get("SMP_LICENSE"), api_base=get("SMP_API_BASE") or API_BASE, **kwargs)

    @property
    def seconds_until_allowed(self) -> float:
        return max(0.0, self._next_allowed - time.monotonic())

    def _request(self) -> urllib.request.Request:
        if self.mode == "link":
            return urllib.request.Request(self.rotate_url, headers={"User-Agent": "singapore-mobile-proxy"})
        url = f"{self.api_base}/proxy/change-ip?license={quote(self.license, safe='')}"
        return urllib.request.Request(url, headers={"x-api-key": self.api_key, "User-Agent": "singapore-mobile-proxy"})

    def rotate(self) -> dict:
        """Rotate now. Blocks until the server answers (a modem redial can take ~20s).

        Raises RotationCooldown if the line rotated too recently, RotationError on any other failure.
        """
        wait = self.seconds_until_allowed
        if wait > 0:
            raise RotationCooldown(int(wait) + 1)
        try:
            with self._opener.open(self._request(), timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 429:
                retry_after = e.headers.get("Retry-After", "")
                retry_after = int(retry_after) if retry_after.isdigit() else int(self.min_interval)
                self._next_allowed = time.monotonic() + retry_after
                raise RotationCooldown(retry_after, f"rotation is cooling down: {detail}") from None
            # The server starts the cooldown window before it calls the modem, so a
            # failed attempt still counts against it.
            self._next_allowed = time.monotonic() + self.min_interval
            raise RotationError(f"rotation failed with HTTP {e.code}: {detail}") from None
        except (TimeoutError, socket.timeout):
            # The modem may well be redialling already, so this counts as an attempt.
            self._next_allowed = time.monotonic() + self.min_interval
            raise RotationError(f"rotation timed out after {self.timeout:g}s; the modem may still be redialling") from None
        except (urllib.error.URLError, OSError) as e:
            raise RotationError(f"could not reach the rotation endpoint: {e}") from None
        self._next_allowed = time.monotonic() + self.min_interval
        try:
            return json.loads(body)
        except ValueError:
            return {"message": body}
