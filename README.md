# singapore-mobile-proxy

[![test](https://github.com/Xavierfok/singapore-mobile-proxy/actions/workflows/test.yml/badge.svg)](https://github.com/Xavierfok/singapore-mobile-proxy/actions/workflows/test.yml)

Route Scrapy spiders and Playwright browsers through a dedicated Singapore 4G mobile IP, and rotate
it when a site starts blocking you.

- **Scrapy downloader middleware**: one setting sends every request through the line, and it can
  rotate the IP on a status code (403, 429, ...), on a schedule, or when you ask for it
- **Playwright** helpers and examples for Python and Node: launch through the proxy, check the exit
  IP, rotate
- **`singapore-proxy` CLI**: print the exit IP and carrier, or rotate and wait for the new IP
- Plain `ProxyConfig` that hands the same credentials to requests, httpx, curl or anything else
- No dependencies beyond the standard library (Scrapy and Playwright are optional extras)

It is built for [Singapore Mobile Proxy](https://singaporemobileproxy.com/?utm_source=github&utm_medium=repo&utm_campaign=python_package)
lines: one physical 4G modem per port with a Singtel or M1 SIM card, HTTP and SOCKS5, so the sites
you scrape see a phone on a Singapore carrier network. The middleware works with any HTTP proxy that
has a rotation URL.

## Quickstart (Scrapy)

```bash
pip install "singapore-mobile-proxy[scrapy]"
export SMP_PROXY="host:port:user:pass"          # the HTTP line from your dashboard
export SMP_ROTATE_URL="https://.../rotate/..."  # the rotation link from your dashboard
```

```python
# settings.py
DOWNLOADER_MIDDLEWARES = {"singapore_mobile_proxy.scrapy.SingaporeProxyMiddleware": 740}
SMP_ROTATE_ON_STATUS = [403, 429]
```

That's it. Check the line is up before a long crawl:

```bash
singapore-proxy check
```

```json
{
  "ip": "...",
  "country": "SG",
  "org": "AS45143 ...",
  "asn": "AS45143",
  "carrier": "singtel",
  "mobile": true
}
```

No line yet? There is a [free 24-hour trial](https://singaporemobileproxy.com/client/trial?utm_source=github&utm_medium=repo&utm_campaign=python_package),
then from $4 a day, $13 a week or $40 a month.

## Rotating the IP

A rotation asks the modem to redial, and the carrier hands it a new IP. Each line allows one
rotation every 4 minutes through the rotation link, or every 5 minutes through the API. The
middleware knows this: it never rotates twice for one burst of blocked responses, and when the line
is still cooling down it passes the response on instead of retrying on the same IP.

| Setting | Default | What it does |
| --- | --- | --- |
| `SMP_ROTATE_ON_STATUS` | `[]` | Rotate and retry the request when the response has one of these codes |
| `SMP_ROTATE_EVERY` | `0` | Rotate every N seconds (0 = off). Use 240 or more |
| `SMP_ROTATE_MAX_RETRIES` | `2` | Rotations per request before the blocked response is passed on |
| `SMP_ROTATE_SETTLE` | `5` | Seconds to wait after a rotation before sending again |
| `SMP_ROTATE_MIN_INTERVAL` | `240` / `300` | Gap the middleware keeps between rotations (link / API). Only change it if your line has a different limit |
| `SMP_ENABLED` | `True` | Set to `False` to switch the middleware off |

Every `SMP_*` setting can also come from an environment variable of the same name, so credentials
stay out of your code. Settings win over the environment.

**Rotate by hand** from a callback:

```python
def parse(self, response):
    if "captcha" in response.text:
        yield response.request.replace(
            meta={**response.request.meta, "smp_rotate": True}, dont_filter=True)
```

**Skip the proxy** for one request with `meta={"smp_skip": True}`. A request that already has its own
`meta["proxy"]` is left alone.

The crawl stats show what happened: `smp/rotations`, `smp/retries`, `smp/rotation_cooldown`,
`smp/rotation_failed` and `smp/gave_up`.

**Using the API instead of the link:** set `SMP_API_KEY` and `SMP_LICENSE` (the license UUID of the
line) instead of `SMP_ROTATE_URL`.

## Playwright

Chromium can't log in to a SOCKS5 proxy, so browsers use the HTTP port.

```python
from playwright.sync_api import sync_playwright
from singapore_mobile_proxy import ProxyConfig

proxy = ProxyConfig.from_env()
with sync_playwright() as p:
    browser = p.chromium.launch(proxy=proxy.playwright())
    page = browser.new_page()
    page.goto("https://ipinfo.io/json")
    print(page.inner_text("body"))
```

Full examples that check the exit IP, rotate, and confirm the new IP:

- Python: [`examples/playwright_rotate.py`](examples/playwright_rotate.py)
- Node: [`examples/playwright_rotate.mjs`](examples/playwright_rotate.mjs) (no dependency on this package)
- Scrapy spider you can run with `scrapy runspider`: [`examples/scrapy_spider.py`](examples/scrapy_spider.py)

## Other clients

```python
from singapore_mobile_proxy import ProxyConfig, Rotator, rotate_and_wait

proxy = ProxyConfig.from_env()
proxy.http_url              # http://user:pass@host:port      (requests, httpx, curl, HTTPS_PROXY)
proxy.socks5_url()          # socks5h://user:pass@host:5xxx    (DNS resolved in Singapore too)
proxy.requests_proxies()    # {"http": ..., "https": ...}

rotate_and_wait(proxy, Rotator.from_env())   # {"old_ip": ..., "new_ip": ..., "changed": true}
```

Mobile carriers sometimes hand the same IP back after a redial. `changed` is `false` then; rotate
again once the cooldown has passed.

## Configuration

| Variable | Example | Notes |
| --- | --- | --- |
| `SMP_PROXY` | `host:8221:user:pass` | HTTP line, as shown in your dashboard. `http://user:pass@host:port` works too |
| `SMP_SOCKS_PROXY` | `host:5221:user:pass` | SOCKS5 line. HTTP and SOCKS5 are separate ports |
| `SMP_HOST`, `SMP_HTTP_PORT`, `SMP_SOCKS_PORT`, `SMP_USERNAME`, `SMP_PASSWORD` | | The same, as separate parts |
| `SMP_ROTATE_URL` | | Rotation link from your dashboard |
| `SMP_API_KEY`, `SMP_LICENSE` | | API rotation, instead of the link |

## Try it offline

`tests/mockproxy.py` runs a local stand-in for a line (proxy port, rotation link and an IP-info
page), so you can try the quickstart without an account:

```bash
python tests/mockproxy.py     # prints the SMP_* variables to export, then serves
```

## More

- [singapore-geo-testing](https://github.com/Xavierfok/singapore-geo-testing): recipes for checking
  what a visitor in Singapore sees (geo-redirects, currency, cookie banners)
- [setup-singapore-proxy](https://github.com/Xavierfok/setup-singapore-proxy): a GitHub Action that
  routes a CI job through a Singapore mobile IP
- [singapore-proxy-mcp](https://github.com/Xavierfok/singapore-proxy-mcp): the same lines as an MCP
  server for AI agents

MIT licensed. Not affiliated with Scrapy, Microsoft Playwright, or any carrier.
