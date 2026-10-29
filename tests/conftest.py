"""Shared fixtures for the pizza-hacking end-to-end tests.

The tests run inside the stack's `edge` network (./pizza.sh test), where every
public hostname is a network alias of Traefik, so requests go through exactly
the same TLS + tinyauth + routing path a browser would — just on port 443
instead of the published host port. TLS is verified against the generated CA.
"""

import hashlib
import hmac
import os
import re

import pytest
import requests

ENV_FILE = os.environ.get("PIZZA_ENV_FILE", "/state/.env")
CA_FILE = os.environ.get("PIZZA_CA", "/state/certs/ca.crt")


def read_env(path):
    values = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
    return values


@pytest.fixture(scope="session")
def env():
    return read_env(ENV_FILE)


@pytest.fixture(scope="session")
def stage1_env():
    path = os.environ.get("PIZZA_STAGE1_ENV")
    if not path:
        pytest.skip("only available in stage 2")
    return read_env(path)


@pytest.fixture(scope="session")
def url(env):
    def build(host, path="/"):
        return f"https://{host}.{env['DOMAIN']}{path}"
    return build


@pytest.fixture
def new_session():
    sessions = []

    def make():
        s = requests.Session()
        s.verify = CA_FILE
        sessions.append(s)
        return s

    yield make
    for s in sessions:
        s.close()


def tinyauth_login(session, url, username, password):
    return session.post(
        url("auth", "/api/user/login"),
        json={"username": username, "password": password},
        timeout=30,
    )


@pytest.fixture
def login(new_session, url, env):
    """Session already logged in to tinyauth as the given user."""

    def make(username):
        password = (
            env["TINYAUTH_ADMIN_PASSWORD"]
            if username == env["TINYAUTH_ADMIN_USER"]
            else env[f"{username.upper()}_PASSWORD"]
        )
        s = new_session()
        resp = tinyauth_login(s, url, username, password)
        assert resp.status_code == 200, f"tinyauth login for {username}: {resp.status_code} {resp.text}"
        return s

    return make


# --- CTFd -----------------------------------------------------------------

def form_nonce(html):
    m = re.search(r'name="nonce"(?:[^>]*?)value="([^"]+)"', html)
    assert m, "CTFd form nonce not found"
    return m.group(1)


def csrf_nonce(html):
    m = re.search(r"csrfNonce['\"]?\s*:\s*\"([^\"]+)\"", html)
    assert m, "CTFd CSRF nonce not found"
    return m.group(1)


class CTFd:
    def __init__(self, session, url):
        self.s = session
        self.url = url

    def get(self, path, **kw):
        return self.s.get(self.url("ctf", path), timeout=30, **kw)

    def login(self, name, password):
        nonce = form_nonce(self.get("/login").text)
        return self.s.post(
            self.url("ctf", "/login"),
            data={"name": name, "password": password, "nonce": nonce},
            timeout=30,
        )

    def register(self, name, email, password):
        nonce = form_nonce(self.get("/register").text)
        return self.s.post(
            self.url("ctf", "/register"),
            data={"name": name, "email": email, "password": password, "nonce": nonce},
            timeout=30,
        )

    def api(self, method, path, **kw):
        headers = {"CSRF-Token": csrf_nonce(self.get("/challenges").text)}
        return self.s.request(method, self.url("ctf", f"/api/v1{path}"), headers=headers, timeout=30, **kw)


@pytest.fixture
def ctfd(login, url, env):
    """CTFd client behind a tinyauth session (the IdP admin's)."""

    def make(idp_user=None):
        return CTFd(login(idp_user or env["TINYAUTH_ADMIN_USER"]), url)

    return make


def derived_secret(env, label):
    """Deterministic per-deployment value, so stage 2 can find stage 1's data."""
    return hmac.new(env["CTF_KEY"].encode(), label.encode(), hashlib.sha1).hexdigest()[:20]


@pytest.fixture(scope="session")
def scorer(env):
    """The CTFd player account the test suite registers in stage 1."""
    return {
        "name": "pizza-tester",
        "email": "pizza-tester@pizza.invalid",
        "password": derived_secret(env, "ctfd-scorer"),
    }


@pytest.fixture(scope="session")
def juice_user(env):
    return {"email": "alice@pizza.invalid", "password": derived_secret(env, "juice-alice")}


def juice_register(session, url, player, user):
    return session.post(
        url(player, "/api/Users"),
        json={"email": user["email"], "password": user["password"], "passwordRepeat": user["password"]},
        timeout=30,
    )


def juice_login(session, url, player, user):
    return session.post(
        url(player, "/rest/user/login"),
        json={"email": user["email"], "password": user["password"]},
        timeout=30,
    )
