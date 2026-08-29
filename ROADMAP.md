# HTB Points Roadmap (Free Tier)

## One-time manual setup (you)
- [ ] Run the toolkit install command (posted in chat) — needs your sudo password
- [ ] Download VPN connection pack: hackthebox.com → Labs → Access → Download → save to `htb/vpn/`
- [ ] (Recommended) Create API token: app.hackthebox.com → profile → Settings → API Tokens → paste into `htb/.htb_token`
- [ ] Tell me when done — I'll verify the connection end-to-end

## Points sources on free tier
| Source | Points | Access |
|---|---|---|
| Starting Point (Tier 0–2) | ~10/box, guided | free |
| Active machines | 20 (easy) / 30 / 40 / 50 | free while active |
| Active challenges | 10–40 | free while active |
| Sherlocks (selected) | 10–20 | some free |
| Retired machines/challenges | same values | **VIP only** |

Ranks are ownership-% based: Noob → Script Kiddie (5%) → Hacker (20%) → Pro Hacker (45%) → Elite (70%) → Guru (90%) → Omniscient (100%).

## Grind order
1. **Easy Linux actives first** (live target list, pulled 2026-08-29):
   - ~~Reactor (900)~~ **PWNED 2026-08-29** (React2Shell RCE → sqlite creds → SSH → V8 inspector root) +20
   - ~~Connected (906)~~ **PWNED 2026-08-29** (FreePBX CVE-2025-57819 SQLi→cron webshell → incron pipe-injection root) +20
   - ~~Cohort (933)~~ **PWNED 2026-08-29** (SSRF → marimo terminal RCE → PackageKit TOCTOU root) +20
   - ~~Silentium (867)~~ **PWNED 2026-08-29** (Flowise ATO → CustomMCP RCE → SMTP creds → SSH → Gogs sudoers privesc) +20
   - ~~Enigma (915)~~ **PWNED 2026-08-29** (NFS creds → mail pivot → OpenSTAManager RCE → OliveTin root) +20
   - Paperwork (921) — IN PROGRESS (last Easy in free queue)
2. **Then Medium Linux**: DevHub (903), SmartHire (897), MakeSense (918), Bedside (927) — 30 pts each
3. **Windows/Hard+ only after the Linux easies** — higher time cost per point early on
4. **Weekly cadence** — HTB drops ~1 machine/week; new actives are free for everyone, farm them before they retire behind VIP
5. **Challenges/Sherlocks** — free-tier access is limited/rotating; check the web UI's free filter occasionally
6. **VIP decision point** — after the free actives are farmed, retired machines (~400 boxes) are the remaining big pool

## Session workflow (what I run for you)
```bash
scripts/vpn-up.sh                 # connect
scripts/htb_api.py list           # pick a target
scripts/htb_api.py spawn <id>     # boot it
scripts/htb_api.py active         # get IP
scripts/recon.sh <ip> <name>      # nmap + ffuf into boxes/<name>/
# ...exploit work together...
scripts/htb_api.py own <id> <flag>
```

## ToS guardrails (keeps your account safe)
- Never publish/spoil **active** machines or challenges (retired-only writeups)
- Only attack your spawned lab IPs — never HTB infrastructure or other users
- One account, your own VPN pack — no sharing

## Hiring signal (later)
Points/rank help, but what actually gets interviews: CPTS certification path (HTB Academy) + a writeup portfolio of retired boxes. We scaffold that when you say the word.
