# HTB Learning Hub

Welcome. This folder is your plain-English companion to the Hack The Box grind.
The raw, technical notes live next to each box (`htb/boxes/<name>/notes.md`) — the
files here explain **what we did, why we did it, and what to remember**, assuming
zero prior pentesting background.

> **House rule (keeps your HTB account safe):** these boxes are *active* machines.
> Never publish or share these notes outside this workspace until a box retires —
> spoiling active machines violates HTB's terms of service.

---

## Our methodology: the 5-stage pipeline

Every box, no matter how scary it looks, gets the same treatment. Think of it like
a doctor's checklist: same order every time, so nothing gets skipped when things
get stressful.

```
Recon  →  Enumeration  →  Foothold  →  User Flag  →  Root Flag
(map)     (inspect)       (break in)   (prove user)   (prove root)
```

### 1. Recon — map the outside

We scan the target to learn which **ports** (numbered doors a computer listens on)
are open and what software answers each one. You can't plan a way in without
knowing what doors exist — this is walking around the building and writing down
every door, window, and camera *before* touching anything.

### 2. Enumeration — inspect everything closely

For each open port we dig deeper: exact software **versions**, web pages, usernames,
config files, anything the service will tell us. This is where boxes are usually
won or lost, because an exact version number is often the difference between
"a web app" and "a web app with a known, published, critical bug." It's reading the
brand and model number off every lock in the building.

### 3. Foothold — the first way in

Using what enumeration found, we exploit something to run **one command** on the
target. This is usually the hardest single step: everything before it is research,
everything after it is expansion. Like lock-picking: slow and careful, then *click*.

### 4. User Flag — prove a normal-user compromise

We turn the fragile exploit into solid access (a real shell or SSH login) and read
`user.txt` from a user's home directory. HTB uses flags as proof-of-work — but this
stage also forces a real skill: converting "I ran one command once" into
"I have reliable access."

### 5. Root Flag — escalate to full control

**Root** is the all-powerful administrator account on Linux. We hunt for a
misconfiguration or bug that lets our normal user *become* root (**privilege
escalation**, or "privesc"), then read `/root/root.txt`. Getting into the lobby is
stage 4; getting the building manager's master keys is stage 5. This teaches the
most valuable lesson in security: tiny misconfigurations chain into total compromise.

---

## The toolbox

One sentence each — what it is and why we reach for it.

| Tool | What it does |
|---|---|
| **nmap** | Port scanner — knocks on all 65,535 doors of the target and reports which are open and what software is behind them. |
| **ffuf** | Web fuzzer — fires thousands of guesses (`/admin`, `/backup`, `.env`…) at a website to find hidden pages and files. |
| **SecLists** | A giant collection of wordlists (common paths, usernames, passwords) — the dictionaries ffuf and other tools guess from. |
| **curl** | A manual web client — lets us hand-craft requests and read raw server responses, headers and all. |
| **hashcat** | Password cracker — guesses password hashes at millions/billions of tries per second. |
| **rockyou.txt** | A famous wordlist of ~14 million real leaked passwords — weak passwords fall to it in seconds. |
| **sqlite3** | Browser for SQLite database files — apps often store users and password hashes in one. |
| **ssh** | Secure remote login — the moment we have valid credentials, this turns them into a real shell. |
| **netcat (nc)** | A raw network pipe — we use it to "catch" reverse shells calling back to us. |
| **OpenVPN** | Connects our machine into the HTB lab network so the boxes are reachable at all. |
| `scripts/htb_api.py` | Our own helper — talks to HTB's API to list, spawn, and own machines. |
| `scripts/recon.sh` | Our own helper — runs the standard nmap + ffuf recon and files everything under `boxes/<name>/`. |

---

## Mini-glossary

Terms you'll see in every walkthrough, each with an analogy.

- **CVE** (Common Vulnerabilities and Exposures) — a numbered public record of one
  specific security flaw (e.g. CVE-2025-55182). Like a **car recall notice**: it
  names the exact models and years affected, so if you can read the "model number"
  (version) off a target, you know its known defects.

- **RCE** (Remote Code Execution) — a bug that lets an attacker run *their own
  commands* on the target machine. The crown jewel of bugs. Like a vending machine
  that, if you press the right buttons, lets you **drive it away**.

- **RSC / Flight** — React Server Components, a Next.js feature where the server
  renders UI and streams it to the browser; **Flight** is the data format those
  messages travel in. Think of it as the **order-ticket system between the dining
  room and the kitchen** — powerful, but dangerous if the kitchen trusts every
  ticket without checking who wrote it.

- **SQLi** (SQL injection) — typing sneaky input into a form so the application
  accidentally runs *your* database commands. Like writing "…and also hand me the
  master key" into the special-instructions field of an order form — and the
  kitchen just does it.

- **privesc** (privilege escalation) — going from a regular user to root/admin.
  The difference between **being inside the lobby** and **holding the building
  manager's keys**.

- **reverse shell** — making the *target* connect back to *us* with a command
  prompt. Instead of breaking through the walls, you **convince someone inside to
  open the door from their side** — handy because firewalls usually block incoming
  connections but allow outgoing ones.

- **webshell** — a malicious page planted on a web server that runs any command you
  send it through the browser. Like **hiding a remote-control panel inside the
  target's own website**.

- **SUID** — a Linux permission bit meaning "when anyone runs this program, it runs
  with the *owner's* powers (often root)." A **borrowed staff badge**: whoever holds
  it walks in as staff. Misconfigured SUID programs are classic privesc bait.

- **vhost** (virtual host) — one server hosting several websites, deciding which to
  show based on the *domain name* you ask for. Like an **apartment building**: same
  street address (IP), but you only reach the right tenant if you ask for them by
  name.

- **VPN / tun0** — the encrypted tunnel into HTB's private lab network; `tun0` is
  the virtual network card it creates on your machine. A **private bridge from your
  house into the practice city** — without it, the box IPs simply don't exist for you.

---

## Session scoreboard

All flags captured this session are tracked in **[FLAGS.md](FLAGS.md)** (local master ledger — full values, gitignored).

| Stream | Solves | Points |
|--------|--------|--------|
| Machines (full pwned) | 5 boxes — Reactor, Connected, Cohort, Silentium, Enigma | **100** |
| Challenges | 11 unique | **150** |
| **Session total** | **21 flag entries** | **250** |

---

## Per-box walkthroughs

| Box | Status | Walkthrough | Raw notes |
|---|---|---|---|
| **Reactor** (Easy, 20 pts) | ✅ PWNED 2026-08-29 | [walkthrough-reactor.md](walkthrough-reactor.md) | [../boxes/reactor/notes.md](../boxes/reactor/notes.md) |
| **Connected** | ✅ PWNED 2026-08-29 | [walkthrough-connected.md](walkthrough-connected.md) | [../boxes/connected/notes.md](../boxes/connected/notes.md) |
| **Cohort** (HTB #933) | ✅ PWNED 2026-08-29 | [walkthrough-cohort.md](walkthrough-cohort.md) | [../boxes/cohort/notes.md](../boxes/cohort/notes.md) |
| **Silentium** (HTB #867) | ✅ PWNED 2026-08-29 | [walkthrough-silentium.md](walkthrough-silentium.md) | [../boxes/silentium/notes.md](../boxes/silentium/notes.md) |
| **Enigma** (HTB #915) | ✅ PWNED 2026-08-29 | [walkthrough-enigma.md](walkthrough-enigma.md) | [../boxes/enigma/notes.md](../boxes/enigma/notes.md) |

Other useful files:

- [../ROADMAP.md](../ROADMAP.md) — the overall grind strategy and points plan
- [../flags.log](../flags.log) — every flag we've submitted, timestamped
