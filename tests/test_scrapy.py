"""Real crawls, in a subprocess (Twisted's reactor can't restart), against the mock line."""

import json
import os
import subprocess
import sys

import pytest

pytest.importorskip("scrapy")

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)


def crawl(env, tmp_path, spider, *settings, urls="", chain=False):
    out, stats = tmp_path / "items.json", tmp_path / "stats.json"
    cmd = [sys.executable, "-m", "scrapy", "runspider", spider, "-O", str(out)]
    for s in settings:
        cmd += ["-s", s]
    run_env = {**os.environ, **env, "TEST_URLS": urls, "STATS_FILE": str(stats),
               "TEST_CHAIN": "1" if chain else ""}
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        run_env.pop(k, None)
    proc = subprocess.run(cmd, env=run_env, cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-3000:]
    items = json.loads(out.read_text())
    return items, (json.loads(stats.read_text()) if stats.exists() else {}), proc.stderr


def test_readme_example_spider(line, tmp_path):
    state, env = line
    items, _, log = crawl(env, tmp_path, os.path.join(ROOT, "examples", "scrapy_spider.py"))
    assert items == [{"ip": "203.0.113.1", "country": "SG", "org": "AS45143 Singtel Mobile"}]
    assert state.proxied == [("203.0.113.1", "/json")]
    assert "Routing requests through Singapore mobile proxy 127.0.0.1" in log


def test_burst_of_403s_rotates_once_and_retries_all(line, tmp_path):
    state, env = line
    state.blocked = {"203.0.113.1"}
    urls = " ".join(f"http://shop.test/page{i}" for i in range(6))
    items, stats, _ = crawl(env, tmp_path, os.path.join(HERE, "crawl_spider.py"),
                            "SMP_ROTATE_ON_STATUS=403,429", urls=urls)
    assert state.rotations == 1
    assert sorted(i["status"] for i in items) == [200] * 6
    assert {i["body"] for i in items} == {"ok from 203.0.113.2"}
    # Requests that reached the middleware mid-rotation waited for it instead of going out on the old IP.
    on_old_ip = sum(1 for ip, _ in state.proxied if ip == "203.0.113.1")
    assert stats["smp/rotations"] == 1 and stats["smp/retries"] == on_old_ip


def test_cooldown_passes_the_blocked_response_on(line, tmp_path):
    state, env = line
    state.blocked = {"203.0.113.1", "203.0.113.2"}
    items, stats, _ = crawl(env, tmp_path, os.path.join(HERE, "crawl_spider.py"),
                            "SMP_ROTATE_ON_STATUS=403", urls="http://shop.test/page")
    assert state.rotations == 1  # the second rotation was refused locally, inside the 240s window
    assert [(i["status"], i["rotations"]) for i in items] == [(403, 1)]
    assert stats["smp/rotation_cooldown"] == 1


def test_max_retries(line, tmp_path):
    state, env = line
    state.blocked = {f"203.0.113.{n}" for n in range(1, 10)}
    items, stats, _ = crawl(env, tmp_path, os.path.join(HERE, "crawl_spider.py"),
                            "SMP_ROTATE_ON_STATUS=403", "SMP_ROTATE_MIN_INTERVAL=0", "SMP_ROTATE_MAX_RETRIES=3",
                            urls="http://shop.test/page")
    assert state.rotations == 3
    assert [(i["status"], i["rotations"]) for i in items] == [(403, 3)]
    assert stats["smp/gave_up"] == 1


def test_manual_rotation_from_a_callback(line, tmp_path):
    state, env = line
    items, _, _ = crawl(env, tmp_path, os.path.join(HERE, "crawl_spider.py"), urls="http://shop.test/page-manual")
    assert state.rotations == 1
    assert [i["body"] for i in items] == ["ok from 203.0.113.1", "ok from 203.0.113.2"]


def test_scheduled_rotation(line, tmp_path):
    state, env = line
    state.latency = 0.05  # well above Windows' ~16ms clock tick, so every gap counts as "due"
    urls = " ".join(f"http://shop.test/page{i}" for i in range(3))
    crawl(env, tmp_path, os.path.join(HERE, "crawl_spider.py"),
          "SMP_ROTATE_EVERY=0.001", "SMP_ROTATE_MIN_INTERVAL=0", urls=urls, chain=True)
    assert state.rotations == 3
    assert [ip for ip, _ in state.proxied] == ["203.0.113.2", "203.0.113.3", "203.0.113.4"]


def test_skip_and_disable(line, tmp_path):
    state, env = line
    crawl(env, tmp_path, os.path.join(HERE, "crawl_spider.py"), "SMP_ENABLED=False", urls="http://127.0.0.1:9/x")
    assert state.proxied == []


def test_missing_proxy_disables_with_a_clear_log(line, tmp_path):
    _, env = line
    _, _, log = crawl({"SMP_PROXY": ""}, tmp_path, os.path.join(HERE, "crawl_spider.py"), urls="")
    assert "No proxy configured" in log


def test_rotation_settings_without_a_link_still_proxy(line, tmp_path):
    state, env = line
    state.blocked = {"203.0.113.1"}
    _, _, log = crawl({"SMP_PROXY": env["SMP_PROXY"]}, tmp_path, os.path.join(HERE, "crawl_spider.py"),
                      "SMP_ROTATE_ON_STATUS=403", urls="http://shop.test/page")
    assert "without rotating" in log
    assert state.proxied == [("203.0.113.1", "/page")] and state.rotations == 0


def test_socks_only_line_explains_scrapy_needs_http(tmp_path):
    _, _, log = crawl({"SMP_PROXY": "", "SMP_SOCKS_PROXY": "h:5221:u:p"}, tmp_path,
                      os.path.join(HERE, "crawl_spider.py"), urls="")
    assert "Scrapy only talks HTTP to proxies" in log
