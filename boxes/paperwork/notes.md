# Paperwork (HTB #921) — 10.129.248.117

**Date:** 2026-08-29  
**Phase:** Recon complete → enumeration / exploit

---

## Port summary

| Port | Service | Notes |
|------|---------|-------|
| 22 | OpenSSH 10.0p2 (Ubuntu) | Standard SSH |
| 80 | nginx 1.28.0 | **Requires vhost** `paperwork.htb` — bare IP redirects everything |
| 1515 | Custom LPD (RFC 1179) | Banner: `Archive_Printer is ready and printing.` |

---

## Discovery

| Signal | Detail |
|--------|--------|
| IP `:80` without Host | 301 → `http://paperwork.htb/` for all paths |
| Vhost `paperwork.htb` | 200 — **Intranet \| Document Archiving Service** |
| ffuf on IP | ~29k hits, all 301 redirects — **use Host header or run against `paperwork.htb`** |
| `/download/archive` | `paperwork-archive-v1.02.zip` (1.1 KB) — contains `server.py` (LPD listener source) |

---

## Web — paperwork.htb

Static intranet portal (“Department of Records & Archives”):

- **Protocol:** Compliance Level RFC 1179 (Line Printer Daemon)
- **Target queue:** `archive_intake`
- **Spooler:** `PRN-ARCHIVE-01` (management console offline per advisory)
- **Artifact:** `/download/archive` → `web/server.py`

---

## LPD service (`server.py` highlights)

Custom Python TCP listener on **1515**:

- Commands `0x03` / `0x04` → readiness banner
- Command `0x02` → print job for queue name after byte 1
- Valid queue from env `LPD_QUEUE` (portal says `archive_intake`)
- Job content parsed for line starting with `J` → **job name**
- **Sink:** `subprocess.Popen(f"echo 'Archive: {job_name}' >> /tmp/archive.log", shell=True)` — **command injection via job name** (unescaped in shell string)

---

## Attack surface (next steps)

1. Add hosts entry: `10.129.248.117 paperwork.htb` (sudo required)
2. Craft RFC 1179 print job to `:1515` with queue `archive_intake` and malicious `J` line → RCE
3. Enumerate foothold → privesc → `user.txt` / `root.txt`

---

## Artifacts

- `nmap/allports.txt`, `nmap/services.txt`
- `ffuf-80.json` (IP-based; mostly redirect noise)
- `web/server.py` (from `/download/archive`)
