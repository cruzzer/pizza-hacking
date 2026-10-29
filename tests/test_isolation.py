"""Juice Shop instances are independent of each other and not persistent."""

import pytest

from conftest import juice_login, juice_register


@pytest.mark.stage1
def test_register_on_instance_one(login, url, juice_user):
    s = login("player1")
    assert juice_register(s, url, "player1", juice_user).status_code == 201
    assert juice_login(s, url, "player1", juice_user).status_code == 200


@pytest.mark.stage2
def test_instances_are_independent_and_reset_on_restart(login, url, juice_user):
    s1, s2 = login("player1"), login("player2")
    # Stage 1 registered this e-mail on player1. Between the stages the stack
    # was stopped and started; registering again only succeeds (201, not 400
    # "email must be unique") because Juice Shop state is not persisted.
    assert juice_register(s1, url, "player1", juice_user).status_code == 201
    assert juice_login(s1, url, "player1", juice_user).status_code == 200
    # The account exists on instance one only.
    assert juice_login(s2, url, "player2", juice_user).status_code == 401
