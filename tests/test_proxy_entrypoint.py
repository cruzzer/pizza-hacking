"""The plain-HTTP "proxy" entrypoint (for a TLS-terminating reverse proxy in
front of the stack) serves the same routers behind the same tinyauth gate."""

import pytest
import requests

PROXY = "http://traefik:8000"


def via_proxy(host, env, cookies=None, headers=None, **kw):
    headers = {**(headers or {}), "Host": f"{host}.{env['DOMAIN']}"}
    if cookies:
        headers["Cookie"] = "; ".join(f"{c.name}={c.value}" for c in cookies)
    return requests.get(PROXY + "/", headers=headers, allow_redirects=False, timeout=30, **kw)


@pytest.mark.stage1
@pytest.mark.stage2
@pytest.mark.parametrize("host", ["player1", "ctf", "juice"])
def test_proxy_entrypoint_is_gated(env, host):
    resp = via_proxy(host, env)
    assert resp.status_code == 401
    location = resp.headers.get("x-tinyauth-location", "")
    assert "/login" in location
    # The browser came in over HTTPS at the proxy: send it back there.
    assert f"redirect_uri=https%3A%2F%2F{host}." in location, location


@pytest.mark.stage1
@pytest.mark.stage2
def test_proxy_entrypoint_serves_logged_in_player(env, login):
    session = login("player1")
    resp = via_proxy("player1", env, cookies=session.cookies)
    assert resp.status_code == 200 and "OWASP Juice Shop" in resp.text
    # The landing redirect works the same way through the proxy.
    landing = via_proxy("juice", env, cookies=session.cookies)
    assert landing.status_code == 302
    assert landing.headers["Location"].startswith("https://player1.")


@pytest.mark.stage2
def test_proxy_entrypoint_keeps_player_acls(env, login):
    assert via_proxy("player2", env, cookies=login("player1").cookies).status_code == 403


@pytest.mark.stage2
@pytest.mark.parametrize("spoof", [
    {"X-Forwarded-Host": "player1"},
    {"X-Forwarded-Host": "player1", "X-Forwarded-Proto": "https", "X-Forwarded-Uri": "/"},
    {"Forwarded": "host=player1;proto=https"},
])
def test_proxy_entrypoint_ignores_client_forwarded_headers(env, login, spoof):
    """sso-proxied trusts X-Forwarded-*: only safe because the entrypoint drops
    whatever the client sent. A player must not borrow their own ACL."""
    headers = {k: v.replace("player1", f"player1.{env['DOMAIN']}") for k, v in spoof.items()}
    resp = via_proxy("player2", env, cookies=login("player1").cookies, headers=headers)
    assert resp.status_code == 403
