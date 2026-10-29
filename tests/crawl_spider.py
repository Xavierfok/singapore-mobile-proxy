"""Spider driven by env vars, used by test_scrapy.py. Writes its stats to $STATS_FILE when it closes."""

import json
import os

import scrapy


class TestSpider(scrapy.Spider):
    name = "t"
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {"singapore_mobile_proxy.scrapy.SingaporeProxyMiddleware": 740},
        "SMP_ROTATE_SETTLE": 0,
        "HTTPERROR_ALLOW_ALL": True,
        "RETRY_ENABLED": False,
        "LOG_LEVEL": "INFO",
    }

    async def start(self):  # Scrapy >= 2.13
        for request in self.start_requests():
            yield request

    def start_requests(self):  # older Scrapy
        urls = os.environ["TEST_URLS"].split()
        if os.environ.get("TEST_CHAIN"):  # one at a time: each page queues the next
            urls = urls[:1]
        for url in urls:
            yield scrapy.Request(url, meta={"manual": url.endswith("manual")})

    def parse(self, response):
        yield {"url": response.url, "status": response.status, "body": response.text,
               "rotations": response.meta.get("smp_rotations", 0)}
        urls = os.environ["TEST_URLS"].split()
        if os.environ.get("TEST_CHAIN") and response.url in urls[:-1]:
            yield scrapy.Request(urls[urls.index(response.url) + 1])
        if response.meta.get("manual") and not response.meta.get("again"):
            yield response.request.replace(meta={**response.request.meta, "smp_rotate": True, "again": True},
                                           dont_filter=True)

    def closed(self, reason):
        with open(os.environ["STATS_FILE"], "w") as f:
            json.dump({k: v for k, v in self.crawler.stats.get_stats().items() if k.startswith("smp/")}, f)
