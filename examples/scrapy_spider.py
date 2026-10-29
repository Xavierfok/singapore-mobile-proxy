"""A self-contained spider: every request goes out through the Singapore mobile line.

    pip install "singapore-mobile-proxy[scrapy]"
    export SMP_PROXY="host:port:user:pass"          # HTTP line from your dashboard
    export SMP_ROTATE_URL="https://.../rotate/..."  # rotation link from your dashboard
    scrapy runspider scrapy_spider.py -O out.json

In a project, put the two settings below in settings.py instead of custom_settings.
"""

import json
import os

import scrapy


class ExitIpSpider(scrapy.Spider):
    name = "exit_ip"
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {"singapore_mobile_proxy.scrapy.SingaporeProxyMiddleware": 740},
        "SMP_ROTATE_ON_STATUS": [403, 429],
    }
    start_urls = [os.environ.get("SMP_IP_INFO_URL", "https://ipinfo.io/json")]

    def parse(self, response):
        data = json.loads(response.text)
        yield {"ip": data.get("ip"), "country": data.get("country"), "org": data.get("org")}
