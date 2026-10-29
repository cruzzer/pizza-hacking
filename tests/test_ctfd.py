"""CTFd: generated admin works, players can register, challenges are imported."""

import pytest

pytestmark = pytest.mark.stage1


def test_ctfd_admin_can_log_in(ctfd, env):
    c = ctfd()
    resp = c.login(env["CTFD_ADMIN_USER"], env["CTFD_ADMIN_PASSWORD"])
    assert resp.status_code == 200 and not resp.url.endswith("/login"), "admin login failed"
    admin = c.get("/admin/challenges", allow_redirects=False)
    assert admin.status_code == 200


def test_player_can_register(ctfd, scorer):
    c = ctfd("player1")
    resp = c.register(scorer["name"], scorer["email"], scorer["password"])
    assert resp.status_code == 200 and not resp.url.endswith("/register"), resp.text[:500]
    me = c.api("GET", "/users/me").json()["data"]
    assert me["name"] == scorer["name"]
    # A self-registered player is not an admin.
    assert c.get("/admin/challenges", allow_redirects=False).status_code != 200


def test_all_juice_shop_challenges_are_imported(ctfd, env, login, url):
    juice = login("player1").get(url("player1", "/api/Challenges"), timeout=30).json()["data"]
    c = ctfd()
    c.login(env["CTFD_ADMIN_USER"], env["CTFD_ADMIN_PASSWORD"])
    imported = c.api("GET", "/challenges?view=admin").json()["data"]
    assert {ch["name"] for ch in imported} == {ch["name"] for ch in juice}
    hints = c.api("GET", "/hints").json()["data"]
    assert len(hints) > len(imported), "expected several hints per challenge"
