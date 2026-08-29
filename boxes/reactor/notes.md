# Reactor (HTB #900, Easy, 20 pts)

IP: 10.129.106.68 | Spawned: 2026-08-29 | Lab expiry: 21:19 UTC

## Recon
- 22/tcp — OpenSSH 9.6p1 Ubuntu 3ubuntu13.16 (Ubuntu 24.04)
- 3000/tcp — Next.js app (X-Powered-By: Next.js, RSC enabled, prerendered)

## App: ReactorWatch Core Monitoring System v3.2.1
- Fake nuclear reactor monitoring dashboard, "Nuclear Dynamics Corp.", Facility SITE-7
- Personnel (potential usernames for SSH):
  - Dr. Elena Rodriguez — Lead Nuclear Engineer (ONLINE)
  - Marcus Kim — Senior Technician (ONLINE)
  - James Thompson — Safety Officer (OFFLINE)
- Username candidates: erodriguez, elena.rodriguez, mkim, marcus.kim, jthompson, james.thompson, rodriguez, kim, thompson

## Attack surface hypotheses
- [ ] ffuf directory results (running)
- [ ] /api/* routes — enumerate from JS chunks
- [ ] Next.js middleware auth bypass (CVE-2025-29927, x-middleware-subrequest) if /admin or similar exists
- [ ] JS chunk analysis for secrets/endpoints: /_next/static/chunks/*.js

## JS/App-layer findings (2026-08-29, see loot/endpoints.md + loot/js-analysis.txt)
- Stack: **Next.js 15.0.3** + **React 19.0.0-rc-66855b96-20241106** (react-server-dom-webpack), buildId `L3bimJe_3LvBcFWAnK5L4`
- Route surface: ONLY `/` (prerendered, cache HIT) + `/_not-found`. Router filter static numItems=2, dynamic=0.
- 30+ common/themed/API paths probed → all stock 404, zero info leaks. No /api/*, no /_next/data, no source maps, no .env.
- Client JS contains NO app code (pure RSC) → no secrets, no fetch calls, no internal hosts. Nothing to grep that ffuf missed.
- **CVE-2025-29927 (middleware bypass): NEGATIVE** — no middleware manifest emitted; x-middleware-subrequest (all 4 variants) on /,/admin,/dashboard,/login → byte-identical responses. App has no middleware/protected routes.
- **TOP LEAD — CVE-2025-55182 "React2Shell" (unauth RCE, CVSS 10)**: React 19.0.0-rc + Next 15.0.3 are squarely in vulnerable range (fixed: React 19.0.1+, Next 15.0.5+). RSC flight deserializer is exposed at POST / (multipart/form-data, malicious server-function reference). Box name "Reactor" + RSC-enabled recon note strongly suggest this is the intended vector. NOT yet tested (exploitation, outside enum boundaries).

## Recommended next steps (ranked)
1. CVE-2025-55182 React2Shell PoC → reverse shell as nextjs user (highest likelihood)
2. Await ffuf results for any non-obvious route (low expectation: router filter says 2 static routes)
3. SSH (22) password spray with erodriguez/mkim/jthompson variants — only if web path stalls
4. Post-exploit: check /home/*, nextjs app dir for env secrets; sudo -l; kernel 7.1.9-arch? (container?) — enumerate privesc

## Exploitation (2026-08-29) — FULL CHAIN

### 1. RCE — CVE-2025-55182 "React2Shell" (unauthenticated)
- Exploit: `loot/exploit.py` — multipart/form-data POST to `http://10.129.106.68:3000/` with header `Next-Action: x` (any value; Flight decoder runs before action-ID validation).
- Field `0` = fake chunk: `then: $1:__proto__:then` (Chunk.prototype.then), `status: resolved_model`, `value: {"then":"$B0"}` → `$B` blob handler calls `response._formData.get(response._prefix + id)`; `_formData.get` hijacked to `Function` via `$1:constructor:constructor`; `_prefix` = arbitrary JS → executed in the Node server process.
- Output exfil inline: payload throws `NEXT_REDIRECT` error with `encodeURIComponent(stdout)` in the digest → reflected in `x-action-redirect` / flight body (HTTP 303). Command is base64-wrapped + `exit 0` appended so `execSync` never throws early.
- Result: RCE as `node` (uid=999), cwd `/opt/reactor-app`. Confirmed with `id`.

### 2. node → engineer (user flag)
- `/opt/reactor-app/.env` → `DB_PATH=/opt/reactor-app/reactor.db` (sqlite3, readable by node).
- `users` table: `engineer:39d97110eafe2a9a68639812cd271e8e` (MD5), `admin:a203b22191d744a4e70ada5c101b17b8` (not in rockyou).
- hashcat `-m 0` + rockyou → **engineer:reactor1**.
- SSH (22) as engineer → `cat /home/engineer/user.txt` → **user flag: `02215790ba967ed71c705bf911627373`** (submitted, accepted).

### 3. engineer → root (root flag)
- Enum (`loot/privesc-enum.txt`): no sudo for engineer; stock SUID; no cron jobs; lxd group is a DECOY (`/usr/sbin/lxc` is a broken snap shim, no daemon).
- `ps aux` → root process `/usr/bin/node --inspect=127.0.0.1:9229 /opt/uptime-monitor/worker.js` (V8 inspector exposed on loopback).
- V8 inspector = debugger protocol on a root process → CDP `Runtime.evaluate` executes JS as root.
- Exploit: `loot/inspector-root-rce.js` — fetches `http://127.0.0.1:9229/json/list` for the WS URL, connects (`node --experimental-websocket`, box runs Node v20.20.2), evaluates `process.getBuiltinModule("child_process").execSync(cmd)` → `uid=0(root)`.
- `cat /root/root.txt` → **root flag: `48de3837d84fe54c7cca4bfaf385912f`** (submitted, accepted; `machine_pwned: true`).

### HTB API note
- `POST labs.hackthebox.com/api/v4/machine/own` is GONE (404 HTML). Working endpoint: `POST https://labs.hackthebox.com/api/v5/machine/own` with `{"id":900,"flag":"<flag>","difficulty":10}` (difficulty = multiple of 10). Responses: `Reactor user/root is now owned.`

## Flags
- [x] user.txt — `02215790ba967ed71c705bf911627373` (owned 2026-08-29)
- [x] root.txt — `48de3837d84fe54c7cca4bfaf385912f` (owned 2026-08-29)
