"""Scrapy downloader middleware: send every request through a Singapore mobile line.

    DOWNLOADER_MIDDLEWARES = {"singapore_mobile_proxy.scrapy.SingaporeProxyMiddleware": 740}

Settings (each falls back to the environment variable of the same name):

    SMP_PROXY               host:port:user:pass, the HTTP line from your dashboard
    SMP_ROTATE_URL          rotation link from your dashboard (or SMP_API_KEY + SMP_LICENSE)
    SMP_ROTATE_ON_STATUS    rotate and retry when a response has one of these codes, e.g. [403, 429]
    SMP_ROTATE_EVERY        rotate on a schedule, in seconds (0 = off)
    SMP_ROTATE_MAX_RETRIES  rotations per request before the response is passed on (default 2)
    SMP_ROTATE_SETTLE       seconds to pause after a rotation before sending again (default 5)
    SMP_ROTATE_MIN_INTERVAL client-side floor between rotations (default 240s link, 300s API)
    SMP_ENABLED             set False to turn the middleware off

Rotate by hand from a callback: `yield request.replace(meta={**request.meta, "smp_rotate": True}, dont_filter=True)`.
Skip the proxy for one request: `meta={"smp_skip": True}`.

Scrapy only speaks HTTP to proxies, so this uses the line's HTTP port.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from scrapy.exceptions import NotConfigured
from scrapy.utils.defer import maybe_deferred_to_future
from twisted.internet import defer, reactor, threads
from twisted.internet.task import deferLater

from .config import ConfigError, ProxyConfig
from .rotation import RotationCooldown, RotationError, Rotator

logger = logging.getLogger(__name__)


class SingaporeProxyMiddleware:
    def __init__(self, config: ProxyConfig, rotator: Optional[Rotator] = None, rotate_on_status=(),
                 rotate_every: float = 0, max_retries: int = 2, settle: float = 5, stats=None):
        self.config = config
        self.proxy_url = config.http_url
        # Scrapy's HttpProxyMiddleware moves the credentials into a header and leaves the bare URL in meta.
        self._ours = {self.proxy_url, f"http://{config.host}:{config.http_port}"}
        self.rotator = rotator
        self.rotate_on_status = frozenset(int(s) for s in rotate_on_status)
        self.rotate_every = rotate_every
        self.max_retries = max_retries
        self.settle = settle
        self.stats = stats
        self.generation = 0  # bumped on every successful rotation
        self._last_rotation = time.monotonic()
        self._rotating = False
        self._waiters: list = []

    @classmethod
    def from_crawler(cls, crawler):
        s = crawler.settings
        if not s.getbool("SMP_ENABLED", True):
            raise NotConfigured("SMP_ENABLED is False")

        def get(key):
            return s.get(key) or os.environ.get(key) or None

        try:
            config = ProxyConfig.from_getter(get)
        except ConfigError as e:
            raise NotConfigured(str(e)) from None
        if config.http_port is None:
            raise NotConfigured("Scrapy only talks HTTP to proxies: set SMP_PROXY to the line's HTTP port")
        rotate_on_status = s.getlist("SMP_ROTATE_ON_STATUS") or [
            x for x in (os.environ.get("SMP_ROTATE_ON_STATUS") or "").replace(",", " ").split() if x]
        rotate_every = s.getfloat("SMP_ROTATE_EVERY", float(os.environ.get("SMP_ROTATE_EVERY") or 0))
        rotator = None
        try:
            floor = s.get("SMP_ROTATE_MIN_INTERVAL") or os.environ.get("SMP_ROTATE_MIN_INTERVAL")
            rotator = Rotator.from_getter(get, min_interval=float(floor) if floor not in (None, "") else None)
        except ConfigError:
            if rotate_on_status or rotate_every:
                # Keep proxying: switching the whole middleware off would send the crawl out unproxied.
                logger.warning("Rotation is enabled but SMP_ROTATE_URL (or SMP_API_KEY + SMP_LICENSE) is not set; "
                               "requests still go through the proxy, without rotating")
        if rotator and rotate_every and rotate_every < rotator.min_interval:
            logger.warning("SMP_ROTATE_EVERY=%ss is shorter than the line's rotation limit (%ss); "
                           "rotations will be skipped until the cooldown passes", rotate_every, rotator.min_interval)
        mw = cls(config, rotator, rotate_on_status=rotate_on_status, rotate_every=rotate_every,
                 max_retries=s.getint("SMP_ROTATE_MAX_RETRIES", 2), settle=s.getfloat("SMP_ROTATE_SETTLE", 5),
                 stats=crawler.stats)
        logger.info("Routing requests through Singapore mobile proxy %s:%s (rotation: %s)",
                    config.host, config.http_port, rotator.mode if rotator else "off")
        return mw

    def _inc(self, key: str) -> None:
        if self.stats is not None:
            self.stats.inc_value(f"smp/{key}")

    async def _wait_for_rotation(self) -> bool:
        d = defer.Deferred()
        self._waiters.append(d)
        return await maybe_deferred_to_future(d)

    async def _rotate(self, reason: str) -> bool:
        """Rotate once, however many requests ask at the same moment. True if the IP was rotated."""
        if self.rotator is None:
            return False
        if self._rotating:
            return await self._wait_for_rotation()
        self._rotating = True
        ok = False
        try:
            await maybe_deferred_to_future(threads.deferToThread(self.rotator.rotate))
            ok = True
            self.generation += 1
            self._last_rotation = time.monotonic()
            self._inc("rotations")
            logger.info("Rotated the Singapore mobile IP (%s)", reason)
            if self.settle:
                await maybe_deferred_to_future(deferLater(reactor, self.settle, lambda: None))
        except RotationCooldown as e:
            self._inc("rotation_cooldown")
            logger.info("Wanted to rotate (%s) but the line is cooling down for %ss", reason, e.retry_after)
        except RotationError as e:
            self._inc("rotation_failed")
            logger.warning("Rotation failed (%s): %s", reason, e)
        finally:
            self._rotating = False
            waiters, self._waiters = self._waiters, []
            for d in waiters:
                d.callback(ok)
        return ok

    async def process_request(self, request, spider=None):
        if request.meta.get("smp_skip") or request.meta.get("proxy", self.proxy_url) not in self._ours:
            return None  # opted out, or another proxy was set on purpose
        if request.meta.pop("smp_rotate", False):
            await self._rotate("requested in meta")
        elif self.rotate_every and time.monotonic() - self._last_rotation >= self.rotate_every:
            await self._rotate(f"every {self.rotate_every:g}s")
        elif self._rotating:
            await self._wait_for_rotation()
        request.meta["proxy"] = self.proxy_url
        request.meta["smp_generation"] = self.generation
        return None

    async def process_response(self, request, response, spider=None):
        if response.status not in self.rotate_on_status or "smp_generation" not in request.meta:
            return response
        tries = request.meta.get("smp_rotations", 0)
        if tries >= self.max_retries:
            self._inc("gave_up")
            return response
        # Another request may have rotated since this one was sent: retry on the new IP, don't rotate again.
        if request.meta["smp_generation"] == self.generation:
            if not await self._rotate(f"HTTP {response.status} on {request.url}"):
                return response
        retry = request.copy()
        retry.meta["smp_rotations"] = tries + 1
        retry.dont_filter = True
        self._inc("retries")
        return retry

