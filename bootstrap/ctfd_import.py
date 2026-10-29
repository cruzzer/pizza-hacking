"""Finish CTFd setup and import the Juice Shop challenges.

Runs as a one-shot container on the stack's internal network (see the
ctfd-bootstrap service). Safe to re-run: setup is only submitted while CTFd
still shows /setup, and challenges that already exist (by name) are skipped.

Flags: Juice Shop in CTF mode shows HMAC-SHA1(CTF_KEY, challenge name) as the
flag code when a challenge is solved (lib/utils.ts ctfFlag), so the same
value is stored as a static CTFd flag.

Standard library only, so the container needs no pip install.
"""

import hashlib
import hmac
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CTFD = os.environ["CTFD_URL"].rstrip("/")
JUICE = os.environ["JUICE_URL"].rstrip("/")
CTF_KEY = os.environ["CTF_KEY"]
ADMIN_USER = os.environ["CTFD_ADMIN_USER"]
ADMIN_EMAIL = os.environ["CTFD_ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["CTFD_ADMIN_PASSWORD"]
CTF_NAME = os.environ.get("CTF_NAME", "Pizza Hacking")
HINT_COST_PERCENT = int(os.environ.get("HINT_COST_PERCENT", "10"))
JUICE_PUBLIC_URL = os.environ.get("JUICE_PUBLIC_URL", "")
META_FILE = "/data/challenges-meta.json"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def log(msg):
    print(f"[ctfd-bootstrap] {msg}", flush=True)


def request(method, url, data=None, headers=None, form=False):
    headers = dict(headers or {})
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=30) as resp:
            return resp.status, resp.geturl(), resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, url, err.read().decode(errors="replace")


def wait_for(url, what, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _, _ = request("GET", url)
            if status < 500:
                return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(3)
    sys.exit(f"[ctfd-bootstrap] {what} not reachable at {url} after {timeout}s")


def form_nonce(html):
    m = re.search(r'name="nonce"(?:[^>]*?)value="([^"]+)"', html)
    if not m:
        sys.exit("[ctfd-bootstrap] no form nonce found")
    return m.group(1)


def csrf_nonce(html):
    m = re.search(r"csrfNonce['\"]?\s*:\s*\"([^\"]+)\"", html)
    if not m:
        sys.exit("[ctfd-bootstrap] no CSRF nonce found")
    return m.group(1)


def setup_or_login():
    status, final_url, html = request("GET", f"{CTFD}/setup")
    if status == 200 and final_url.endswith("/setup"):
        log("CTFd not set up yet, creating admin account")
        fields = {
            "ctf_name": CTF_NAME,
            "ctf_description": "OWASP Juice Shop challenges. Solve them in your own Juice Shop, submit the flag codes here.",
            "user_mode": "users",
            "name": ADMIN_USER,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "challenge_visibility": "private",
            "account_visibility": "public",
            "score_visibility": "public",
            "registration_visibility": "public",
            "verify_emails": "false",
            "team_size": "",
            "ctf_theme": "core",
            "theme_color": "",
            "start": "",
            "end": "",
            "social_shares": "false",
            "nonce": form_nonce(html),
        }
        status, final_url, html = request("POST", f"{CTFD}/setup", fields, form=True)
        if final_url.endswith("/setup"):
            errors = re.findall(r'alert-danger[^>]*>(.*?)<', html, re.S)
            sys.exit(f"[ctfd-bootstrap] setup failed (HTTP {status}): {errors}")
    else:
        status, _, html = request("GET", f"{CTFD}/login")
        fields = {"name": ADMIN_USER, "password": ADMIN_PASSWORD, "nonce": form_nonce(html)}
        status, final_url, html = request("POST", f"{CTFD}/login", fields, form=True)
        if final_url.endswith("/login"):
            sys.exit("[ctfd-bootstrap] admin login failed — does .env still match the CTFd database?")
    _, _, html = request("GET", f"{CTFD}/admin/challenges")
    return csrf_nonce(html)


def api(method, path, nonce, data=None):
    status, _, body = request(method, f"{CTFD}/api/v1{path}", data, {"CSRF-Token": nonce})
    if status >= 300:
        sys.exit(f"[ctfd-bootstrap] {method} {path} -> HTTP {status}: {body[:500]}")
    return json.loads(body)["data"]


def flag_for(name):
    return hmac.new(CTF_KEY.encode(), name.encode(), hashlib.sha1).hexdigest()


def description(chal):
    stars = "⭐" * int(chal["difficulty"])
    where = f"[your own Juice Shop]({JUICE_PUBLIC_URL})" if JUICE_PUBLIC_URL else "your own Juice Shop"
    return (
        f"{chal['description']}\n\n"
        f"**Difficulty:** {stars}\n\n"
        f"Solve it in {where}, then submit the flag code from the green "
        f"\"challenge solved\" notification."
    )


def main():
    wait_for(f"{CTFD}/healthcheck", "CTFd")
    wait_for(f"{JUICE}/rest/admin/application-version", "Juice Shop")

    with open(META_FILE) as fh:
        hints = {c["key"]: c.get("hints") or [] for c in json.load(fh)}

    _, _, body = request("GET", f"{JUICE}/api/Challenges")
    challenges = json.loads(body)["data"]
    log(f"Juice Shop reports {len(challenges)} challenges")

    nonce = setup_or_login()
    existing = {c["name"] for c in api("GET", "/challenges?view=admin", nonce)}

    created = 0
    for chal in sorted(challenges, key=lambda c: (c["difficulty"], c["name"])):
        if chal["name"] in existing:
            continue
        value = 100 * int(chal["difficulty"])
        new = api("POST", "/challenges", nonce, {
            "name": chal["name"],
            "category": chal["category"],
            "description": description(chal),
            "value": value,
            "state": "visible",
            "type": "standard",
        })
        api("POST", "/flags", nonce, {
            "challenge": new["id"],
            "content": flag_for(chal["name"]),
            "type": "static",
            "data": "case_insensitive",
        })
        cost = max(1, value * HINT_COST_PERCENT // 100)
        for text in hints.get(chal["key"], []):
            api("POST", "/hints", nonce, {"challenge": new["id"], "content": text, "cost": cost})
        created += 1

    log(f"imported {created} new challenges ({len(existing)} already present)")


if __name__ == "__main__":
    main()
