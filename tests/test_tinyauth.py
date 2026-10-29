"""tinyauth sits in front of every hostname and knows the generated users."""

import pytest

from conftest import tinyauth_login

pytestmark = [pytest.mark.stage1, pytest.mark.stage2]


def test_admin_can_log_in(new_session, url, env):
    resp = tinyauth_login(new_session(), url, env["TINYAUTH_ADMIN_USER"], env["TINYAUTH_ADMIN_PASSWORD"])
    assert resp.status_code == 200, resp.text
    assert any(c.name.startswith("tinyauth-session") for c in resp.cookies)


def test_first_player_can_log_in(new_session, url, env):
    resp = tinyauth_login(new_session(), url, "player1", env["PLAYER1_PASSWORD"])
    assert resp.status_code == 200, resp.text


def test_wrong_password_is_rejected(new_session, url):
    resp = tinyauth_login(new_session(), url, "player1", "not-the-password")
    assert resp.status_code == 401


def test_idp_admin_and_ctfd_admin_are_different(env):
    assert env["TINYAUTH_ADMIN_USER"] != env["CTFD_ADMIN_USER"]
    assert env["TINYAUTH_ADMIN_PASSWORD"] != env["CTFD_ADMIN_PASSWORD"]


@pytest.mark.parametrize("host", ["player1", "juice", "ctf"])
def test_unauthenticated_requests_are_sent_to_login(new_session, url, host):
    resp = new_session().get(url(host), allow_redirects=False, timeout=30)
    assert resp.status_code == 401
    assert "/login" in resp.headers.get("x-tinyauth-location", "")
