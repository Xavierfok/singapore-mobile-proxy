import pytest

from singapore_mobile_proxy import ConfigError, ProxyConfig


def test_dashboard_line():
    c = ProxyConfig.from_env({"SMP_PROXY": "sg1.example.com:8221:alice:s3cret"})
    assert (c.host, c.http_port, c.username, c.password) == ("sg1.example.com", 8221, "alice", "s3cret")
    assert c.http_url == "http://alice:s3cret@sg1.example.com:8221"


def test_password_with_colon_and_at_is_kept_and_escaped():
    c = ProxyConfig.from_env({"SMP_PROXY": "h:8221:u:p@ss:w/rd"})
    assert c.password == "p@ss:w/rd"
    assert c.http_url == "http://u:p%40ss%3Aw%2Frd@h:8221"


def test_url_form_and_socks_line():
    c = ProxyConfig.from_env({"SMP_PROXY": "http://u:p%40x@h:8221", "SMP_SOCKS_PROXY": "h:5221:u:p@x"})
    assert c.password == "p@x"
    assert c.socks5_url() == "socks5h://u:p%40x@h:5221"
    assert c.socks5_url(remote_dns=False).startswith("socks5://")
    assert c.requests_proxies(socks=True) == {"http": c.socks5_url(), "https": c.socks5_url()}


def test_separate_parts():
    c = ProxyConfig.from_env({"SMP_HOST": "h", "SMP_HTTP_PORT": "8221", "SMP_SOCKS_PORT": "5221",
                              "SMP_USERNAME": "u", "SMP_PASSWORD": "p"})
    assert (c.http_port, c.socks_port) == (8221, 5221)


def test_socks_only_line():
    c = ProxyConfig.from_env({"SMP_SOCKS_PROXY": "h:5221:u:p"})
    assert c.socks_port == 5221 and c.http_port is None
    with pytest.raises(ConfigError):
        c.http_url


def test_playwright_dict_has_no_credentials_in_server():
    c = ProxyConfig.from_env({"SMP_PROXY": "h:8221:u:p"})
    assert c.playwright() == {"server": "http://h:8221", "username": "u", "password": "p"}


def test_ip_whitelist_line_without_credentials():
    c = ProxyConfig.from_env({"SMP_PROXY": "h:8221"})
    assert c.http_url == "http://h:8221"
    assert c.playwright() == {"server": "http://h:8221"}


def test_missing_config_points_to_trial():
    with pytest.raises(ConfigError, match="utm_source=python_package"):
        ProxyConfig.from_env({})


@pytest.mark.parametrize("bad", ["h", "h:port:u:p", "h:8221:u", ":8221:u:p"])
def test_malformed_lines(bad):
    with pytest.raises(ConfigError):
        ProxyConfig.from_env({"SMP_PROXY": bad})


def test_repr_hides_password():
    assert "s3cret" not in repr(ProxyConfig.from_env({"SMP_PROXY": "h:1:u:s3cret"}))
