import pytest

from singapore_mobile_proxy import ConfigError, RotationCooldown, RotationError, Rotator, exit_ip, rotate_and_wait
from singapore_mobile_proxy import ProxyConfig


def test_needs_link_or_api_key():
    with pytest.raises(ConfigError):
        Rotator.from_env({})
    with pytest.raises(ConfigError):
        Rotator.from_env({"SMP_API_KEY": "sk"})  # license missing


def test_link_rotates_and_starts_local_cooldown(line):
    state, env = line
    r = Rotator.from_env(env)
    assert r.mode == "link" and r.min_interval == 240
    assert r.rotate()["success"] is True
    assert state.rotations == 1
    with pytest.raises(RotationCooldown) as e:
        r.rotate()  # refused locally, never reaches the server
    assert 230 < e.value.retry_after <= 241
    assert state.rotations == 1


def test_server_429_is_a_cooldown_with_retry_after(line):
    state, env = line
    state.cooldown = 100
    Rotator.from_env(env, min_interval=0).rotate()
    r2 = Rotator.from_env(env, min_interval=0)  # e.g. a second process on the same line
    with pytest.raises(RotationCooldown) as e:
        r2.rotate()
    assert 90 < e.value.retry_after <= 101
    assert r2.seconds_until_allowed > 90


def test_api_mode_sends_key_and_license(line):
    state, env = line
    base = env["SMP_ROTATE_URL"].split("/rotate/")[0] + "/api/v1"
    r = Rotator(api_key="sk_test", license="lic-uuid", api_base=base)
    assert r.mode == "api" and r.min_interval == 300
    r.rotate()
    assert state.rotations == 1
    with pytest.raises(RotationError, match="401"):
        Rotator(api_key="wrong", license="x", api_base=base).rotate()


def test_dead_link_is_an_error(line):
    _, env = line
    with pytest.raises(RotationError, match="410"):
        Rotator(rotate_url=env["SMP_ROTATE_URL"].replace("tok123", "gone")).rotate()


def test_rotation_ignores_proxy_env_vars(line, monkeypatch):
    _, env = line
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")  # nothing listens there
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    Rotator.from_env(env).rotate()


def test_exit_ip_through_the_proxy(line):
    state, env = line
    info = exit_ip(ProxyConfig.from_env(env), url=env["SMP_IP_INFO_URL"])
    assert info == {"ip": "203.0.113.1", "country": "SG", "org": "AS45143 Singtel Mobile",
                    "asn": "AS45143", "carrier": "singtel", "mobile": True}
    assert state.proxied == [("203.0.113.1", "/json")]


def test_wrong_password_is_rejected(line):
    _, env = line
    bad = ProxyConfig.from_env({"SMP_PROXY": env["SMP_PROXY"].rsplit(":", 1)[0] + ":nope"})
    with pytest.raises(OSError, match="407"):
        exit_ip(bad, url=env["SMP_IP_INFO_URL"])


def test_rotate_and_wait(line, monkeypatch):
    _, env = line
    monkeypatch.setenv("SMP_IP_INFO_URL", env["SMP_IP_INFO_URL"])
    out = rotate_and_wait(ProxyConfig.from_env(env), Rotator.from_env(env))
    assert out == {"old_ip": "203.0.113.1", "new_ip": "203.0.113.2", "changed": True}


def test_cli_check_and_rotate(line, monkeypatch, capsys):
    from singapore_mobile_proxy.__main__ import main

    state, env = line
    state.cooldown = 100
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert main(["check"]) == 0
    assert '"carrier": "singtel"' in capsys.readouterr().out
    assert main(["rotate"]) == 0
    assert '"changed": true' in capsys.readouterr().out
    assert main(["rotate"]) == 1  # second rotation inside the cooldown window
    assert "cooling down" in capsys.readouterr().err


def test_cli_without_config_points_to_trial(monkeypatch, capsys):
    from singapore_mobile_proxy.__main__ import main

    for k in ("SMP_PROXY", "SMP_SOCKS_PROXY", "SMP_HOST"):
        monkeypatch.delenv(k, raising=False)
    assert main(["check"]) == 1
    assert "/client/trial?utm_source=python_package" in capsys.readouterr().err
