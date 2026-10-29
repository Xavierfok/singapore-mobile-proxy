"""Proxy credentials: parse them once, hand them to any client in the shape it wants."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Mapping, Optional
from urllib.parse import quote, unquote, urlsplit

TRIAL_URL = "https://singaporemobileproxy.com/client/trial?utm_source=python_package&utm_medium=error_message&utm_campaign=python_package"

Getter = Callable[[str], Optional[str]]


class ConfigError(ValueError):
    """The proxy settings are missing or malformed."""


def _parse_line(value: str, name: str) -> tuple[str, int, str, str]:
    """Accept `host:port:user:pass` (the dashboard format) or `scheme://user:pass@host:port`."""
    value = value.strip()
    if "://" in value:
        parts = urlsplit(value)
        if not parts.hostname or not parts.port:
            raise ConfigError(f"{name} must include a host and a port, got {value!r}")
        return parts.hostname, parts.port, unquote(parts.username or ""), unquote(parts.password or "")
    bits = value.split(":", 3)  # the password may itself contain ':'
    if len(bits) not in (2, 4):
        raise ConfigError(f"{name} should look like host:port:user:pass, got {len(bits)} field(s)")
    host, port = bits[0], bits[1]
    if not host or not port.isdigit():
        raise ConfigError(f"{name} should look like host:port:user:pass, got {value!r}")
    user, password = (bits[2], bits[3]) if len(bits) == 4 else ("", "")
    return host, int(port), user, password


def _port(value: Optional[str], name: str) -> Optional[int]:
    if value in (None, ""):
        return None
    if not str(value).isdigit():
        raise ConfigError(f"{name} must be a port number, got {value!r}")
    return int(value)


def _env_getter(environ: Optional[Mapping[str, str]] = None) -> Getter:
    env = os.environ if environ is None else environ
    return lambda key: env.get(key) or None


@dataclass(frozen=True)
class ProxyConfig:
    """One Singapore Mobile Proxy line.

    HTTP and SOCKS5 are separate ports on the same line, so they are stored separately.
    """

    host: str
    http_port: Optional[int] = None
    username: str = ""
    password: str = ""
    socks_port: Optional[int] = None
    socks_host: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.host:
            raise ConfigError("proxy host is empty")
        if self.http_port is None and self.socks_port is None:
            raise ConfigError("set at least one of the HTTP or SOCKS5 ports")

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "ProxyConfig":
        """Read SMP_PROXY / SMP_SOCKS_PROXY, or SMP_HOST + SMP_HTTP_PORT + SMP_SOCKS_PORT + SMP_USERNAME + SMP_PASSWORD."""
        return cls.from_getter(_env_getter(environ))

    @classmethod
    def from_getter(cls, get: Getter) -> "ProxyConfig":
        host = get("SMP_HOST")
        user = get("SMP_USERNAME") or ""
        password = get("SMP_PASSWORD") or ""
        http_port = _port(get("SMP_HTTP_PORT"), "SMP_HTTP_PORT")
        socks_port = _port(get("SMP_SOCKS_PORT"), "SMP_SOCKS_PORT")
        socks_host = None

        line = get("SMP_PROXY")
        if line:
            host, http_port, user, password = _parse_line(line, "SMP_PROXY")
        socks_line = get("SMP_SOCKS_PROXY")
        if socks_line:
            s_host, socks_port, s_user, s_pass = _parse_line(socks_line, "SMP_SOCKS_PROXY")
            if not host:
                host, user, password = s_host, s_user, s_pass
            elif s_host != host:
                socks_host = s_host

        if not host:
            raise ConfigError(
                "No proxy configured. Set SMP_PROXY to the HTTP line from your dashboard "
                f"(host:port:user:pass). No line yet? Free 24h trial: {TRIAL_URL}"
            )
        return cls(host=host, http_port=http_port, username=user, password=password,
                   socks_port=socks_port, socks_host=socks_host)

    def _auth(self) -> str:
        if not self.username:
            return ""
        return f"{quote(self.username, safe='')}:{quote(self.password, safe='')}@"

    @property
    def http_url(self) -> str:
        """`http://user:pass@host:port`, for Scrapy, requests, httpx, curl, HTTPS_PROXY."""
        if self.http_port is None:
            raise ConfigError("no HTTP port configured (set SMP_PROXY or SMP_HTTP_PORT)")
        return f"http://{self._auth()}{self.host}:{self.http_port}"

    def socks5_url(self, remote_dns: bool = True) -> str:
        """`socks5h://...` by default, so DNS is resolved in Singapore too, not on your machine."""
        if self.socks_port is None:
            raise ConfigError("no SOCKS5 port configured (set SMP_SOCKS_PROXY or SMP_SOCKS_PORT)")
        scheme = "socks5h" if remote_dns else "socks5"
        return f"{scheme}://{self._auth()}{self.socks_host or self.host}:{self.socks_port}"

    def requests_proxies(self, socks: bool = False) -> dict:
        """The `proxies=` dict for requests. SOCKS5 needs `pip install requests[socks]`."""
        url = self.socks5_url() if socks else self.http_url
        return {"http": url, "https": url}

    def playwright(self) -> dict:
        """The `proxy=` dict for Playwright. Uses the HTTP port: Chromium can't authenticate to SOCKS5."""
        if self.http_port is None:
            raise ConfigError("Playwright needs the HTTP port (set SMP_PROXY or SMP_HTTP_PORT)")
        proxy = {"server": f"http://{self.host}:{self.http_port}"}
        if self.username:
            proxy.update(username=self.username, password=self.password)
        return proxy

    def __repr__(self) -> str:
        return (f"ProxyConfig(host={self.host!r}, http_port={self.http_port}, socks_port={self.socks_port}, "
                f"username={self.username!r}, password={'***' if self.password else ''!r})")
