"""Launch Chromium through a Singapore mobile line, check the exit IP, rotate, check again.

    pip install "singapore-mobile-proxy[playwright]" && python -m playwright install chromium
    export SMP_PROXY="host:port:user:pass"          # HTTP line from your dashboard
    export SMP_ROTATE_URL="https://.../rotate/..."  # rotation link from your dashboard
    python playwright_rotate.py
"""

import json
import os
import time

from playwright.sync_api import sync_playwright

from singapore_mobile_proxy import ProxyConfig, RotationError, Rotator

IP_INFO_URL = os.environ.get("SMP_IP_INFO_URL", "https://ipinfo.io/json")


def exit_ip(browser):
    # A fresh context per check: an old one can keep a connection open to the pre-rotation IP.
    context = browser.new_context()
    try:
        page = context.new_page()
        page.goto(IP_INFO_URL, timeout=30_000)
        return json.loads(page.inner_text("body"))
    finally:
        context.close()


def main():
    proxy = ProxyConfig.from_env()
    rotator = Rotator.from_env()
    with sync_playwright() as p:
        browser = p.chromium.launch(proxy=proxy.playwright())
        before = exit_ip(browser)
        print("before:", before.get("ip"), before.get("country"), before.get("org"))

        try:
            rotator.rotate()
        except RotationError as e:  # includes RotationCooldown
            print("could not rotate:", e)
            return

        # The modem takes a few seconds to redial. Poll until the proxy answers again.
        for _ in range(30):
            try:
                after = exit_ip(browser)
                break
            except Exception:
                time.sleep(3)
        else:
            raise SystemExit("the proxy did not come back within 90s")
        print("after: ", after.get("ip"), after.get("country"), after.get("org"))
        if after.get("ip") == before.get("ip"):
            print("the carrier handed back the same IP; rotate again after the cooldown")
        browser.close()


if __name__ == "__main__":
    main()
