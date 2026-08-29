# HTB Labs Toolkit

Personal Hack The Box **free-tier** grind: VPN + API helpers, recon scripts, a live ops dashboard, per-box notes, and a parallel challenge stream.

This is lab homework for **your own HTB account**. Spawn machines through HTB, connect with **your** VPN pack, and only hit **your** spawned IPs. Do not commit tokens, OpenVPN configs, or flags (those paths are gitignored).

Companion Juice Shop repo: [juice](https://github.com/gabo2212/juice).

---

## What this repo is

Two point streams that do not block each other:

| Stream | Slot | Notes |
|---|---|---|
| **Machines** | Serial on free tier (one spawned box at a time) | ~20 pts per Easy (user + root) |
| **Challenges** | Parallel (downloadable files / per-user containers) | Does not consume the machine slot |
| **Docs** | Parallel, 0 pts | Walkthroughs + learning notes |

The coordinator workflow (recon → enum → exploit → docs, with a challenge farmer on the side) is in [`WORKFLOW.md`](WORKFLOW.md). Points order and free-tier constraints are in [`ROADMAP.md`](ROADMAP.md). Methodology in plain English is in [`notes/LEARNING.md`](notes/LEARNING.md).

**HTB ToS:** only attack your spawned lab. Do not publish spoilers for **active** machines. Walkthroughs in this tree are personal notes — treat active-box writeups as private even though the repo is public.

---

## Prerequisites

- Linux, `sudo`, OpenVPN
- Python 3 (stdlib is enough for `htb_api.py` and the dashboard)
- `nmap` (optional `getcap` so you don’t need sudo for SYN scans)
- `ffuf` + SecLists (`/usr/share/seclists/...`) for the HTTP brute phase in `recon.sh`
- An HTB account (free tier is enough for active machines + rotating challenges)

---

## One-time setup

### 1. VPN pack (required)

Hack The Box → **Labs → Access → Download**. Drop the `.ovpn` file in `vpn/`.

```text
vpn/*.ovpn     # gitignored — never commit this
```

### 2. API token (recommended)

[app.hackthebox.com → Settings → API Tokens](https://app.hackthebox.com/profile/settings). Either:

```bash
export HTB_TOKEN='...'          # session
# or
printf '%s\n' '...' > .htb_token  # gitignored
```

`scripts/htb_api.py` reads `HTB_TOKEN`, then `.htb_token`.

### 3. Connect and sanity-check

```bash
scripts/vpn-up.sh                 # brings up tun0 (openvpn --daemon)
python3 scripts/htb_api.py me     # profile / rank / points
python3 scripts/htb_api.py list   # free machines, easy first
```

Disconnect with `scripts/vpn-down.sh`.

---

## Session workflow

Free tier: **one machine at a time**. As soon as root lands, stop the box and spawn the next.

```bash
scripts/vpn-up.sh
python3 scripts/htb_api.py list
python3 scripts/htb_api.py spawn <id>
python3 scripts/htb_api.py active          # wait ~30s for the IP

scripts/recon.sh <ip> <box-name>           # nmap -p- → -sC -sV → ffuf on HTTP

# ...enum / exploit against YOUR lab IP only...

scripts/own.sh <id> <box-name> user <flag>
scripts/own.sh <id> <box-name> root <flag>

python3 scripts/htb_api.py stop <id>
```

`own.sh` appends to local `flags.log` (gitignored), submits via the v5 machine-own API, and writes a line to `status.log`.

Challenge flags:

```bash
python3 scripts/htb_api.py chown <challenge_id> <flag>
```

Live board of challenge IDs and status: [`challenges/SCOREBOARD.md`](challenges/SCOREBOARD.md).

---

## CLI reference (`scripts/htb_api.py`)

Talks to `https://labs.hackthebox.com/api/v4` (machine own uses **v5** because v4 own was removed). Some POSTs go through `curl` with a browser UA because urllib gets Cloudflare-blocked.

| Command | What it does |
|---|---|
| `me` | Profile, rank, points |
| `list` | Paginated machines, **free first**, by difficulty |
| `list all` | Include VIP / non-free |
| `challs` | Active (non-retired) challenges |
| `find <name>` | Search machines / challenges |
| `active` | Currently spawned machine + IP |
| `spawn <id>` | Boot a VM |
| `stop <id>` | Terminate a VM |
| `own <id> <flag>` | Submit a **machine** flag (user or root) |
| `chown <id> <flag>` | Submit a **challenge** flag |

Other scripts:

| Script | Role |
|---|---|
| `vpn-up.sh` / `vpn-down.sh` | OpenVPN on `tun0` |
| `recon.sh <ip> <name>` | Full TCP sweep, service scan, ffuf → `boxes/<name>/` |
| `own.sh <id> <name> user\|root <flag>` | Local flag ledger + API submit |
| `log_status.sh "msg"` | Append to `status.log` (ISO-8601) |

`recon.sh` writes:

```text
boxes/<name>/
  nmap/allports.txt
  nmap/services.txt
  ffuf-<port>.json     # gitignored (bulky)
  loot/                # gitignored (flags, shells, dumps)
  notes.md             # keep this — that’s the durable record
```

---

## Ops dashboard

Stdlib-only HTTP server. No extra pip packages.

```bash
python3 dashboard/server.py
# or background:
nohup python3 dashboard/server.py > dashboard/server.log 2>&1 &
```

Open **http://127.0.0.1:8888**. The page refreshes `/status.json` every 2 seconds.

It shows VPN (`tun0`) state, the active machine (API, cached ~15s), account snapshot (cached ~60s), `objective.json`, tail of `status.log`, and flag **counts** (not the flag values).

---

## Layout

```text
.
├── ROADMAP.md              # free-tier points plan + grind order
├── WORKFLOW.md             # multi-agent pipeline
├── objective.json          # current box + stage (dashboard reads this)
├── status.log              # operator log (no flags)
├── flags.log               # gitignored
├── .htb_token              # gitignored
├── vpn/*.ovpn              # gitignored
├── scripts/                # API, VPN, recon, own, status
├── dashboard/server.py     # ops console on :8888
├── boxes/<name>/           # one folder per machine
│   ├── notes.md
│   ├── nmap/
│   └── loot/               # gitignored
├── challenges/
│   ├── SCOREBOARD.md
│   └── chal_<id>/          # downloads / working files
├── notes/
│   ├── LEARNING.md
│   ├── FLAGS.md            # gitignored
│   └── walkthrough-*.md
└── sherlocks/              # selected DFIR (when used)
```

Shared handoff state for agents: `objective.json`, `status.log`, `boxes/<name>/notes.md`. Flag values stay in `flags.log` / `notes/FLAGS.md` on disk only.

---

## Machines (this tree)

Free-tier Easy Linux queue from the 2026-08-29 session. Technical notes: `boxes/<name>/notes.md`. Narrative writeups: `notes/walkthrough-<name>.md`.

| Box | ID | Status in notes |
|---|---|---|
| Reactor | 900 | Pwned (user + root) |
| Connected | 906 | Pwned (user + root) |
| Cohort | 933 | Pwned (user + root) |
| Silentium | 867 | Pwned (user + root) |
| Enigma | 915 | Pwned (user + root) |
| Paperwork | 921 | In progress (recon done) |

Next on the roadmap after the remaining Easy: Medium Linux (DevHub, SmartHire, MakeSense, Bedside), then Windows / Hard. New weekly actives are free until they retire behind VIP — see `ROADMAP.md`.

---

## Challenges

Tracked in `challenges/SCOREBOARD.md`. Submit with `htb_api.py chown`. Containers: HTB `POST /api/v4/container/start` with `containerable_id`.

Solved in this session (names only): BabyEncryption, The Last Dance, Baby Time Capsule, Low Logic, Debugging Interface, The Needle, CubeMadness1, RSAisEasy, Obscure, Bypass, Partial Encryption.

Queued / blocked rows stay on the scoreboard (download failures, remote containers, etc.).

Large extracted blobs (`extracted/`, firmware `.bin`, Unity `.dll`) are gitignored so clones stay small. Re-extract from `dl.zip` locally if you need them.

---

## Per-box pipeline (target: &lt; 30 min on Easy)

From [`WORKFLOW.md`](WORKFLOW.md):

1. Previous root flag lands → spawn next box immediately + start `recon.sh`
2. Ports open → enum (app, JS, versions) in parallel with ffuf
3. Enum report → exploit worker with ranked hypotheses
4. Stall → 2–3 parallel hypothesis attempts on distinct vectors
5. Root → docs worker writes the walkthrough **while** the next box spawns

```text
Recon → Enumeration → Foothold → User flag → Root flag
```

---

## What is not in git

| Path | Why |
|---|---|
| `.htb_token` | Account secret |
| `vpn/*.ovpn` | Your VPN pack |
| `flags.log`, `notes/FLAGS.md` | Flag values |
| `boxes/*/loot/` | Shells, dumps, working exploits |
| `boxes/*/ffuf-*.json` | Large scan JSON |
| `.venv/`, `__pycache__/` | Local env |

---

## Guardrails

- One account, your own VPN pack — no sharing.
- Only the IP HTB gave **you** for the currently spawned machine.
- Never HTB infrastructure, other users, or hosts outside the lab VPN.
- Prefer retired-box writeups if you publish anything beyond this repo.

If `tun0` is down, `recon.sh` will look like “no ports” — run `vpn-up.sh` first.
