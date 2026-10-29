# 🍕 pizza-hacking

A self-hosted [OWASP Juice Shop](https://owasp.org/www-project-juice-shop/) CTF
you can start with one command — for workshops, meetups and talks.

```bash
git clone https://github.com/cruzzer/pizza-hacking.git
cd pizza-hacking
./pizza.sh up --players 10
```

You get:

- **One Juice Shop per player**, each in its own container and network. Players
  cannot see or touch each other's instance.
- **A login in front of everything** ([tinyauth](https://github.com/tinyauthapp/tinyauth)).
  Every player gets an account that opens only *their* Juice Shop.
- **A scoreboard** ([CTFd](https://ctfd.io)) preloaded with every Juice Shop
  challenge, its flag and its hints. Players register, solve challenges in
  their Juice Shop and submit the flag codes for points.
- **HTTPS out of the box** with a generated local CA. No Let's Encrypt or public
  DNS needed.

The first run generates every password, prints them, and stores them in `.env`:

```
================ Pizza Hacking ================
Scoreboard (CTFd):   https://ctf.127.0.0.1.nip.io/
Your Juice Shop:     https://juice.127.0.0.1.nip.io/   (redirects each player)

IdP login (tinyauth, needed for every page):
  admin      Xq3...                 (organiser: can open every instance)
  player1    k8T...                 https://player1.127.0.0.1.nip.io/
  player2    Pw2...                 https://player2.127.0.0.1.nip.io/

CTFd administrator (separate account, log in at the scoreboard):
  ctfadmin   9fR...
```

Hand each player a `playerN` login. That's it.

## Requirements

- Docker with the compose plugin (Docker Engine 24+ or Docker Desktop). Rootless
  Podman with its Docker API socket works too.
- `bash`. Every other tool (openssl, bcrypt, the importer) runs in a container.
- Memory: roughly 1 GB for the base stack plus ~300 MB per player.

## How it works

```
                    ┌──────────── Traefik :443 (self-signed CA) ────────────┐
 browser ──────────▶│ auth.D    → tinyauth (login page)                     │
                    │ ctf.D     → [tinyauth] → CTFd ── MariaDB, Redis       │
                    │ juice.D   → [tinyauth] → redirect to your playerN.D   │
                    │ playerN.D → [tinyauth: playerN + admin only]          │
                    └─────────────────────┬─────────────────────────────────┘
                                          │ one internal network per player
                         juice-player1   juice-player2   …   juice-playerN
```

- `D` is `DOMAIN` (default `127.0.0.1.nip.io`). Every hostname is a single
  label under it, so one wildcard certificate covers them all.
- tinyauth runs with a **default-deny** ACL policy. Each `playerN` host admits
  exactly `playerN` and the organiser.
- Each Juice Shop runs on an **internal** network that only Traefik joins. It has
  no internet access and no route to CTFd, tinyauth or other players, so a
  player who gets SSRF or RCE in their shop is still boxed in.
- Juice Shop runs in CTF mode (`NODE_ENV=ctf`) with a generated `CTF_KEY`. A
  solved challenge shows a flag code, `HMAC-SHA1(CTF_KEY, challenge name)`. The
  importer (`bootstrap/ctfd_import.py`) stores the same value as the CTFd flag.
  Hints are hidden in the shop and sold in CTFd instead, by default at 10% of
  the challenge value each (`HINT_COST_PERCENT`).
- No container gets the Docker socket. Routing and ACLs are generated files,
  not container labels.

**State.** Juice Shops are throwaway: a restart gives every player a fresh shop.
CTFd (accounts, solves, points) lives in Docker volumes and survives
`down`/`up`.

## Commands

| Command | What it does |
|---|---|
| `./pizza.sh up [--players N]` | Start. First run generates credentials, CA and certs. Re-run with another N to add or remove players; existing passwords never change. |
| `./pizza.sh creds` | Print all logins again (they also live in `.env`). |
| `./pizza.sh status` / `logs [svc]` | `docker compose ps` / follow logs. |
| `./pizza.sh reset-juice` | Give every player a fresh Juice Shop. |
| `./pizza.sh down` | Stop. CTFd data is kept. |
| `./pizza.sh down --wipe` | Stop and delete everything: CTFd data, `.env`, certificates. |
| `./pizza.sh test` | Run the end-to-end tests in a separate throwaway stack. |

## Running it for a room full of people

The default `127.0.0.1.nip.io` only works on the machine running the stack.
For players on the same network, set the domain on the **first** run:

```bash
DOMAIN=192.168.1.50.nip.io ./pizza.sh up --players 25
```

[nip.io](https://nip.io) resolves `anything.192.168.1.50.nip.io` to
`192.168.1.50`, so no DNS setup is needed. If you have your own domain, point a
wildcard record at the host and use `DOMAIN=ctf.example.org`.

Settings for the first run, all optional:

| Variable | Default | |
|---|---|---|
| `DOMAIN` | `127.0.0.1.nip.io` | Base hostname. |
| `HTTPS_PORT` | `443` | Published HTTPS port. |
| `HTTP_PORT` | `80` | Published HTTP port (it only redirects). `off` publishes none. |
| `PUBLIC_PORT` | `HTTPS_PORT` | The port players see in links. Only set it behind another proxy, see below. |
| `CTF_NAME` | `Pizza Hacking` | Shown in CTFd and on the login page. |

They are written into `.env` and reused afterwards. To change one later, edit
`.env`, delete `certs/` if you changed `DOMAIN`, and run `./pizza.sh up` again.

## Behind your own reverse proxy

If the host already runs a reverse proxy on 443 (with a real certificate),
pizza-hacking can sit behind it. Its Traefik has a third entrypoint, `proxy`
(plain HTTP on container port 8000, never published). It carries the same
routers and the same tinyauth gate, and it tells the apps the request was
HTTPS. Your proxy terminates TLS for `DOMAIN` and `*.DOMAIN` and forwards
everything to `traefik:8000`, keeping the `Host` header:

```bash
DOMAIN=pizza.example.org HTTPS_PORT=8443 HTTP_PORT=off PUBLIC_PORT=443 \
PIZZA_COMPOSE_OVERRIDE=/path/to/my-override.yml ./pizza.sh up --players 10
```

`PIZZA_COMPOSE_OVERRIDE` is an extra compose file applied last. Use it to attach
the `traefik` service to your proxy's network and add the labels your proxy
reads. Don't add your proxy's own login in front: tinyauth already gates every
host, and a second login breaks the redirects.

**Certificates.** The stack uses its own CA (`certs/ca.crt`). Either import that
file into the browsers as a trusted authority, or click through the warning once
per hostname (`auth.`, `ctf.`, `juice.` and the player's own host). Importing
the CA gives the smoothest login redirects.

**Router DNS rebinding protection** (common on home routers) blocks names that
resolve to private IPs, which breaks nip.io. Use a phone hotspot, an `/etc/hosts`
entry, or your own domain.

**Never expose this to the internet without the login in front.** Juice Shop is
deliberately vulnerable. Every route here goes through tinyauth. Keep it that
way.

## Tests

```bash
./pizza.sh test
```

This brings up an isolated stack (project `pizza-hacking-test`, ports
18080/18443, domain `pizza.test`, state in `.test-state/`) and runs the
[pytest](https://pytest.org) suite in `tests/` from a container on the stack's
network. The tests go through Traefik and verify TLS against the generated CA.
The stack is always torn down at the end.

1. **Stage 1, one player, fresh deployment.**
   - The tinyauth admin and `player1` can log in; a wrong password is
     rejected; unauthenticated requests are sent to the login page.
   - The CTFd admin can log in; a player can register in CTFd; every Juice
     Shop challenge and its hints were imported.
   - Exactly one Juice Shop is reachable.
   - A user registered in that Juice Shop can log in.
   - Solving a challenge produces a flag notification whose code CTFd accepts
     and scores.
2. **Stage 2, after `down` and `up --players 2`.**
   - Two instances are reachable, each only by its own player.
   - The Juice Shop user from stage 1 is gone (not persistent), and an account
     registered on instance 1 does not exist on instance 2 (independent).
   - CTFd still has the stage-1 player and their points.
   - No credential in `.env` was rotated.

Both stages also check the `proxy` entrypoint: it is gated, it serves a
logged-in player, and it keeps the per-player ACLs. `TEST_HTTP_PORT=off
./pizza.sh test` runs the suite without a published HTTP port.

Pass extra pytest arguments through, e.g. `./pizza.sh test -k flag -x`.

## Versions

Pinned for reproducibility:
- Juice Shop `v20.3.0`
- CTFd `3.8.9`
- tinyauth `v5.2.0`
- Traefik `v3.7.16`
- MariaDB `11.4`

The importer reads the challenge list from the running Juice Shop, so after
bumping Juice Shop, `down --wipe` and start fresh so that CTFd and the shop
agree.

## License

MIT. OWASP Juice Shop, CTFd, tinyauth and Traefik are separate projects under
their own licenses.
