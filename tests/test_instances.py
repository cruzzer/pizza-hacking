"""One Juice Shop per player, reachable only by that player (and the admin)."""

import pytest


def is_juice_shop(resp):
    return resp.status_code == 200 and "OWASP Juice Shop" in resp.text


@pytest.mark.stage1
def test_one_player_one_instance(login, new_session, url, env):
    assert is_juice_shop(login("player1").get(url("player1"), timeout=30))
    assert "PLAYER2_PASSWORD" not in env
    # No router exists for a second player: ask Traefik directly (the name has
    # no DNS alias in a one-player stack).
    resp = new_session().get(url("auth"), headers={"Host": f"player2.{env['DOMAIN']}"}, timeout=30)
    assert resp.status_code == 404


@pytest.mark.stage2
@pytest.mark.parametrize("player", ["player1", "player2"])
def test_two_players_two_instances(login, url, player):
    assert is_juice_shop(login(player).get(url(player), timeout=30))


@pytest.mark.stage2
@pytest.mark.parametrize("player,other", [("player1", "player2"), ("player2", "player1")])
def test_player_cannot_open_another_players_instance(login, url, player, other):
    assert login(player).get(url(other), allow_redirects=False, timeout=30).status_code == 403


@pytest.mark.stage2
def test_admin_can_open_every_instance(login, url, env):
    admin = login(env["TINYAUTH_ADMIN_USER"])
    for player in ("player1", "player2"):
        assert is_juice_shop(admin.get(url(player), timeout=30))


@pytest.mark.stage1
def test_juice_shop_uses_configured_theme(login, url, env):
    resp = login("player1").get(url("player1", "/rest/admin/application-configuration"), timeout=30)
    config = resp.json()["config"]
    assert config["application"]["theme"] == env["JUICE_THEME"]
    # The theme override must not drop the CTF settings from NODE_ENV=ctf.
    assert config["ctf"]["showFlagsInNotifications"] is True


@pytest.mark.stage1
@pytest.mark.stage2
def test_landing_sends_player_to_own_instance(login, url):
    resp = login("player1").get(url("juice"), allow_redirects=False, timeout=30)
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("https://player1.")


@pytest.mark.stage2
def test_landing_ignores_spoofed_remote_user(login, url):
    resp = login("player1").get(url("juice"), headers={"Remote-User": "player2"}, allow_redirects=False, timeout=30)
    assert resp.headers["Location"].startswith("https://player1.")


@pytest.mark.stage1
@pytest.mark.stage2
def test_admin_has_own_instance(login, url, env):
    admin = env["TINYAUTH_ADMIN_USER"]
    s = login(admin)
    assert is_juice_shop(s.get(url(admin), timeout=30))
    # juice.<domain> sends the organiser to their own demo shop.
    resp = s.get(url("juice"), allow_redirects=False, timeout=30)
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith(f"https://{admin}.")


@pytest.mark.stage1
@pytest.mark.stage2
def test_players_cannot_open_admin_instance(login, url, env):
    resp = login("player1").get(url(env["TINYAUTH_ADMIN_USER"]), allow_redirects=False, timeout=30)
    assert resp.status_code == 403
