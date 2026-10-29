"""Re-running ./pizza.sh keeps every credential; CTFd keeps its data."""

import pytest

pytestmark = pytest.mark.stage2


def test_credentials_are_not_rotated(env, stage1_env):
    for key, value in stage1_env.items():
        if key == "PLAYERS":
            continue
        assert env.get(key) == value, f"{key} changed between deployments"
    assert env["PLAYERS"] == "2" and "PLAYER2_PASSWORD" in env


def test_ctfd_keeps_players_and_points_across_restart(ctfd, scorer):
    c = ctfd("player1")
    resp = c.login(scorer["name"], scorer["password"])
    assert not resp.url.endswith("/login"), "CTFd account from stage 1 is gone"
    me = c.api("GET", "/users/me").json()["data"]
    assert me["score"] > 0, "points from stage 1 are gone"


def test_challenges_are_not_imported_twice(ctfd, env):
    c = ctfd()
    c.login(env["CTFD_ADMIN_USER"], env["CTFD_ADMIN_PASSWORD"])
    names = [ch["name"] for ch in c.api("GET", "/challenges?view=admin").json()["data"]]
    assert len(names) == len(set(names))
