#!/usr/bin/env python3
"""HTB v4 API helper — spawn/stop machines, submit flags, list targets.

Token: create at https://app.hackthebox.com/profile/settings (API Tokens section),
then either `export HTB_TOKEN=...` or paste it into htb/.htb_token
"""
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

BASE = "https://labs.hackthebox.com/api/v4"
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(HERE, "..", ".htb_token")


def token():
    t = os.environ.get("HTB_TOKEN", "").strip()
    if not t and os.path.exists(TOKEN_FILE):
        t = open(TOKEN_FILE).read().strip()
    if not t:
        sys.exit("No token. Set HTB_TOKEN or create htb/.htb_token (see docstring).")
    return t


def api(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "htb-cli-helper",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        sys.exit(f"HTTP {e.code} on {path}: {body}")


def curl_post(path, payload):
    """v4 urllib POSTs get Cloudflare-blocked on some routes; curl with a real UA works."""
    out = subprocess.run(
        ["curl", "-s", "-m", "30", "-X", "POST", "https://labs.hackthebox.com" + path,
         "-H", f"Authorization: Bearer {token()}",
         "-H", "Content-Type: application/json",
         "-H", "Accept: application/json",
         "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
         "-d", json.dumps(payload)],
        capture_output=True, text=True)
    try:
        return json.dumps(json.loads(out.stdout), indent=2)
    except json.JSONDecodeError:
        return (out.stdout or out.stderr)[:500]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "me":
        print(json.dumps(api("GET", "/user/info"), indent=2))

    elif cmd == "active":
        print(json.dumps(api("GET", "/machine/active"), indent=2))

    elif cmd == "list":
        show_all = len(sys.argv) > 2 and sys.argv[2] == "all"
        page = api("GET", "/machine/paginated?per_page=100")
        rows = page.get("data", [])
        rows.sort(key=lambda m: (not m.get("free"), m.get("difficulty", 99)))
        for m in rows:
            if not show_all and not m.get("free"):
                continue
            free = "FREE" if m.get("free") else "vip "
            ret = "retired" if m.get("retired") else "active "
            print(f'{m["id"]:>5}  {m["name"]:<22} {m["os"]:<8} {m["difficultyText"]:<8} {free} {ret} pts={m.get("static_points")}')

    elif cmd == "challs":
        page = api("GET", "/challenge/list/active")
        rows = [c for c in page.get("challenges", []) if not c.get("retired")]
        rows.sort(key=lambda c: (c.get("challenge_category_id", 99), c.get("avg_difficulty", 99)))
        for c in rows:
            print(f'{c["id"]:>5}  cat={c["challenge_category_id"]:>2}  {c["name"]:<28} {c["difficulty"]:<8} pts={c.get("static_points")} solves={c.get("solves")}')

    elif cmd == "find" and len(sys.argv) > 2:
        q = " ".join(sys.argv[2:])
        res = api("GET", f"/search/fetch?query={urllib.parse.quote(q)}")
        print(json.dumps(res, indent=2))

    elif cmd == "spawn" and len(sys.argv) > 2:
        print(json.dumps(api("POST", "/vm/spawn", {"machine_id": int(sys.argv[2])}), indent=2))
        print("Wait ~30s, then run: htb_api.py active   (to get the IP)")

    elif cmd == "stop" and len(sys.argv) > 2:
        print(json.dumps(api("POST", "/vm/terminate", {"machine_id": int(sys.argv[2])}), indent=2))

    elif cmd == "own" and len(sys.argv) > 3:
        # HTB removed v4 machine/own; v5 requires a difficulty rating (10-100, steps of 10)
        print(curl_post("/api/v5/machine/own", {"id": int(sys.argv[2]), "flag": sys.argv[3], "difficulty": 10}))

    elif cmd == "chown" and len(sys.argv) > 3:
        # verified working route: v4 with challenge_id field
        print(curl_post("/api/v4/challenge/own", {"challenge_id": int(sys.argv[2]), "flag": sys.argv[3]}))

    else:
        print("""usage: htb_api.py <command>
  me                 your profile, rank, points
  list [all]         machines sorted free-first by difficulty (all = include VIP)
  challs             active (non-retired) challenges by category
  find <name>        search machines/challenges by name
  active             currently spawned machine + its IP
  spawn <id>         boot a machine
  stop <id>          shut it down
  own <id> <flag>    submit a machine flag (user or root)
  chown <id> <flag>  submit a challenge flag""")


if __name__ == "__main__":
    main()
