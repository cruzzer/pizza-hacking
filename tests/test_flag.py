"""A flag code shown by Juice Shop is accepted by CTFd and scores points."""

import hashlib
import hmac
import threading

import pytest
import socketio

CHALLENGE = "Confidential Document"  # solved by fetching /ftp/acquisitions.md


def solve_and_capture_flag(session, url):
    """Solve a challenge on player1 and return the flag from the
    'challenge solved' notification, exactly as a player would see it."""
    solved = threading.Event()
    notes = []
    sio = socketio.Client(http_session=session)

    @sio.on("challenge solved")
    def on_solved(data):
        notes.append(data)
        solved.set()

    # Polling transport: it reuses the requests session, so tinyauth's
    # cookie and the CA bundle apply.
    sio.connect(url("player1"), transports=["polling"], wait_timeout=30)
    try:
        assert session.get(url("player1", "/ftp/acquisitions.md"), timeout=30).status_code == 200
        assert solved.wait(30), "no 'challenge solved' notification received"
    finally:
        sio.disconnect()
    note = next(n for n in notes if n["name"] == CHALLENGE)
    return note["flag"]


@pytest.mark.stage1
def test_juice_shop_flag_is_accepted_by_ctfd(login, ctfd, url, env, scorer):
    flag = solve_and_capture_flag(login("player1"), url)
    expected = hmac.new(env["CTF_KEY"].encode(), CHALLENGE.encode(), hashlib.sha1).hexdigest()
    assert flag == expected, "Juice Shop is not using the generated CTF_KEY"

    c = ctfd("player1")
    resp = c.login(scorer["name"], scorer["password"])
    assert not resp.url.endswith("/login"), "scorer account missing (test_ctfd must run first)"
    challenges = c.api("GET", "/challenges").json()["data"]
    chal = next(ch for ch in challenges if ch["name"] == CHALLENGE)

    wrong = c.api("POST", "/challenges/attempt", json={"challenge_id": chal["id"], "submission": "0" * 40})
    assert wrong.json()["data"]["status"] == "incorrect"

    right = c.api("POST", "/challenges/attempt", json={"challenge_id": chal["id"], "submission": flag})
    assert right.json()["data"]["status"] == "correct", right.text
    me = c.api("GET", "/users/me").json()["data"]
    assert me["score"] == chal["value"]
