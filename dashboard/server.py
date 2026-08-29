#!/usr/bin/env python3
"""OPPSEC ops console — Hack The Box lab progress dashboard. Stdlib only.

Serves a single-page dark terminal UI on port 8888 that auto-refreshes
against /status.json every 2 seconds. All state is gathered live on each
request; HTB API calls are cached to avoid spamming the API.

Run:  python3 server.py            (foreground)
      nohup python3 server.py > server.log 2>&1 &   (background)
"""
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
HTB_ROOT = os.path.abspath(os.path.join(HERE, ".."))
API = os.path.join(HTB_ROOT, "scripts", "htb_api.py")
BOXES = os.path.join(HTB_ROOT, "boxes")
FLAGS_LOG = os.path.join(HTB_ROOT, "flags.log")
STATUS_LOG = os.path.join(HTB_ROOT, "status.log")
OBJECTIVE_JSON = os.path.join(HTB_ROOT, "objective.json")

PORT = 8888
MACHINE_CACHE_TTL = 15   # seconds
ACCOUNT_CACHE_TTL = 60   # seconds
MACHINE_TIMEOUT = 15     # subprocess timeout seconds
ACCOUNT_TIMEOUT = 20
LOG_TAIL = 30
REFRESH_MS = 2000

_cache_lock = threading.Lock()
_cache = {
    "machine": {"ts": 0.0, "data": None},
    "account": {"ts": 0.0, "data": None},
}


def iso_now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run_api(cmd):
    """Run htb_api.py <cmd>, return parsed JSON dict or raise."""
    out = subprocess.run(
        ["python3", API, cmd],
        capture_output=True, text=True, timeout=MACHINE_TIMEOUT if cmd == "active" else ACCOUNT_TIMEOUT,
    )
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout or "api error").strip()[:300])
    return json.loads(out.stdout or "{}")


def get_vpn():
    """VPN up/down via tun0, plus its IPv4 address if up."""
    try:
        link = subprocess.run(["ip", "link", "show", "tun0"],
                              capture_output=True, text=True, timeout=5)
        if link.returncode != 0:
            return {"up": False, "ip": None}
        addr = subprocess.run(["ip", "-4", "addr", "show", "tun0"],
                              capture_output=True, text=True, timeout=5)
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", addr.stdout)
        return {"up": True, "ip": m.group(1) if m else None}
    except Exception as e:
        return {"up": False, "ip": None, "error": str(e)[:200]}


def get_machine():
    """Currently spawned machine, cached 15s."""
    with _cache_lock:
        c = _cache["machine"]
        if time.time() - c["ts"] < MACHINE_CACHE_TTL and c["data"] is not None:
            return c["data"]
    try:
        raw = run_api("active")
        info = raw.get("info") or {}
        if not info:
            data = {"active": False, "name": None, "id": None, "ip": None, "expires_at": None}
        else:
            data = {
                "active": True,
                "name": info.get("name"),
                "id": info.get("id"),
                "ip": info.get("ip"),
                "expires_at": info.get("expires_at"),
                "type": info.get("type"),
                "isSpawning": info.get("isSpawning"),
            }
        data["error"] = None
    except Exception as e:
        # keep serving stale cache if we have it, else report the error
        with _cache_lock:
            stale = _cache["machine"]["data"]
        if stale is not None:
            stale = dict(stale)
            stale["stale"] = True
            return stale
        data = {"active": False, "name": None, "id": None, "ip": None,
                "expires_at": None, "error": str(e)[:300]}
    with _cache_lock:
        _cache["machine"] = {"ts": time.time(), "data": data}
    return data


def get_account():
    """Profile / rank / points, cached 60s."""
    with _cache_lock:
        c = _cache["account"]
        if time.time() - c["ts"] < ACCOUNT_CACHE_TTL and c["data"] is not None:
            return c["data"]
    try:
        raw = run_api("me")
        info = raw.get("info") or {}
        data = {
            "name": info.get("name"),
            "rank_id": info.get("rank_id"),
        }
        # pass through any points/ownership-ish fields that exist
        for k in ("points", "user_points", "ownership", "rank", "rank_name",
                  "system_owns", "user_owns", "root_owns", "challenge_owns",
                  "machines_owned", "subscriptionType", "isVip"):
            if k in info:
                data[k] = info.get(k)
        data["error"] = None
    except Exception as e:
        with _cache_lock:
            stale = _cache["account"]["data"]
        if stale is not None:
            stale = dict(stale)
            stale["stale"] = True
            return stale
        data = {"name": None, "rank_id": None, "error": str(e)[:300]}
    with _cache_lock:
        _cache["account"] = {"ts": time.time(), "data": data}
    return data


PORT_RE = re.compile(r"^(\d+)/(tcp|udp)\s+(\S+)\s+(\S+)\s*(.*)$")


def parse_services(path):
    """Extract open port lines from an nmap -oN services.txt."""
    ports = []
    try:
        with open(path, errors="replace") as f:
            for line in f:
                m = PORT_RE.match(line.strip())
                if not m:
                    continue
                port, proto, state, service, version = m.groups()
                if "open" not in state:
                    continue
                ports.append({
                    "port": int(port),
                    "proto": proto,
                    "state": state,
                    "service": service,
                    "version": version.strip(),
                })
    except OSError:
        pass
    return ports


def get_boxes():
    """Scan boxes/*/ for recon artifacts and parsed open ports."""
    boxes = []
    if not os.path.isdir(BOXES):
        return boxes
    for name in sorted(os.listdir(BOXES)):
        bdir = os.path.join(BOXES, name)
        if not os.path.isdir(bdir):
            continue
        nmap_dir = os.path.join(bdir, "nmap")
        artifacts = []
        if os.path.isfile(os.path.join(nmap_dir, "allports.txt")):
            artifacts.append("nmap/allports.txt")
        services_path = os.path.join(nmap_dir, "services.txt")
        if os.path.isfile(services_path):
            artifacts.append("nmap/services.txt")
        try:
            for fn in sorted(os.listdir(bdir)):
                if fn.startswith("ffuf-") and fn.endswith(".json"):
                    artifacts.append(fn)
        except OSError:
            pass
        boxes.append({
            "name": name,
            "ports": parse_services(services_path) if os.path.isfile(services_path) else [],
            "artifacts": artifacts,
        })
    return boxes


def mask_flag(flag):
    flag = flag or ""
    if len(flag) <= 6:
        return flag[0:1] + "…" if flag else ""
    return flag[:6] + "…"


def get_flags():
    """Read flags.log, masking all but first 6 chars of each flag."""
    flags = []
    if not os.path.isfile(FLAGS_LOG):
        return flags
    try:
        with open(FLAGS_LOG, errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                parts = line.split("|")
                # ISO_timestamp|machine_id|machine_name|flag_type|flag
                while len(parts) < 5:
                    parts.append("")
                flags.append({
                    "timestamp": parts[0],
                    "machine_id": parts[1],
                    "machine_name": parts[2],
                    "flag_type": parts[3],
                    "flag_masked": mask_flag(parts[4]),
                })
    except OSError:
        pass
    return flags


def get_log():
    """Last N lines of status.log."""
    if not os.path.isfile(STATUS_LOG):
        return []
    try:
        with open(STATUS_LOG, errors="replace") as f:
            lines = [l.rstrip("\n") for l in f if l.strip()]
        return lines[-LOG_TAIL:]
    except OSError:
        return []


STAGES = [
    ("recon", "Recon"),
    ("enumeration", "Enumeration"),
    ("foothold", "Foothold"),
    ("user", "User Flag"),
    ("root", "Root Flag"),
]
STAGE_KEYS = [k for k, _ in STAGES]
STAGE_LABEL = dict(STAGES)
STAGE_PHRASE = {
    "recon": "running recon",
    "enumeration": "enumerating attack surface",
    "foothold": "chasing initial foothold",
    "user": "chasing user.txt",
    "root": "chasing root.txt",
    "complete": "box pwned",
}


def _read_objective_override():
    """Manual override from htb/objective.json, or None."""
    if not os.path.isfile(OBJECTIVE_JSON):
        return None
    try:
        with open(OBJECTIVE_JSON, errors="replace") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return None
        stage = str(d.get("stage") or "").strip().lower() or None
        return {"box": d.get("box"), "stage": stage, "note": d.get("note")}
    except (OSError, ValueError):
        return None


def _box_has_ffuf(bdir):
    try:
        return any(fn.startswith("ffuf-") and fn.endswith(".json")
                   for fn in os.listdir(bdir))
    except OSError:
        return False


def get_objective(boxes, flags, machine):
    """Resolve the current objective + 5-stage pipeline progress."""
    override = _read_objective_override()
    source = "override" if override else "auto"

    box_dir = None
    display = None
    if override and override.get("box"):
        display = str(override["box"])
        box_dir = display
        for b in boxes:
            if b["name"].lower() == display.lower():
                box_dir = b["name"]
                break
    elif machine.get("active") and machine.get("name"):
        display = str(machine["name"])
        box_dir = display
        for b in boxes:
            if b["name"].lower() == display.lower():
                box_dir = b["name"]
                break
    elif boxes:
        def _mtime(b):
            p = os.path.join(BOXES, b["name"])
            return os.path.getmtime(p) if os.path.isdir(p) else 0
        latest = max(boxes, key=_mtime)
        box_dir = latest["name"]
        display = latest["name"]

    if box_dir is None:
        return {"active": False, "source": "none", "headline": "No active objective",
                "box": None, "stage": None, "stage_label": None, "note": None,
                "stages": [{"key": k, "label": l, "done": False, "current": False}
                           for k, l in STAGES],
                "completed": 0, "total": len(STAGES), "pct": 0}

    bdir = os.path.join(BOXES, box_dir)
    lname = box_dir.lower()
    derived = {
        "recon": os.path.isfile(os.path.join(bdir, "nmap", "services.txt")),
        "enumeration": _box_has_ffuf(bdir),
        "user": any(f.get("machine_name", "").lower() == lname and f.get("flag_type") == "user" for f in flags),
        "root": any(f.get("machine_name", "").lower() == lname and f.get("flag_type") == "root" for f in flags),
    }
    derived["foothold"] = derived["user"] or derived["root"]

    if override and override.get("stage") in STAGE_KEYS:
        current = override["stage"]
    else:
        current = "complete"
        for k in STAGE_KEYS:
            if not derived[k]:
                current = k
                break

    note = override.get("note") if override else None
    cur_idx = STAGE_KEYS.index(current) if current in STAGE_KEYS else len(STAGES)

    stages = []
    completed = 0
    for i, (k, label) in enumerate(STAGES):
        done = derived[k] or (i < cur_idx) or current == "complete"
        if done:
            completed += 1
        stages.append({"key": k, "label": label, "done": done,
                       "current": (k == current)})
    if current == "complete":
        completed = len(STAGES)
        for s in stages:
            s["current"] = False

    pct = int(round(100 * completed / len(STAGES)))
    headline = f"{display} — {note or STAGE_PHRASE.get(current, current)}"

    return {"active": True, "source": source, "box": display, "stage": current,
            "stage_label": STAGE_LABEL.get(current, "Complete"), "note": note,
            "headline": headline, "stages": stages, "completed": completed,
            "total": len(STAGES), "pct": pct}


def build_status():
    flags = get_flags()
    boxes = get_boxes()
    machine = get_machine()
    return {
        "generated_at": iso_now(),
        "vpn": get_vpn(),
        "machine": machine,
        "account": get_account(),
        "objective": get_objective(boxes, flags, machine),
        "boxes": boxes,
        "flags": flags,
        "flag_count": len(flags),
        "log": get_log(),
    }


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OPPSEC // ops console</title>
<style>
  :root{
    --bg:#050807; --panel:#0a0f0c; --panel2:#0d1410; --border:#123a22;
    --grn:#33ff77; --grn-dim:#1fae54; --grn-dark:#0f7a3a; --amber:#ffcc44;
    --red:#ff5555; --cyan:#3ee6d8; --mut:#4a7a5c; --txt:#b9f5cf;
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{
    background:var(--bg); color:var(--txt);
    font-family:"JetBrains Mono","Fira Code",Menlo,Consolas,"Courier New",monospace;
    font-size:14px; line-height:1.45; padding:18px; min-height:100vh;
    background-image:repeating-linear-gradient(0deg,rgba(51,255,119,.02) 0 1px,transparent 1px 3px);
  }
  a{color:var(--cyan)}
  .wrap{max-width:1180px;margin:0 auto}
  header.top{display:flex;align-items:baseline;justify-content:space-between;
    border-bottom:1px solid var(--border);padding-bottom:10px;margin-bottom:16px;flex-wrap:wrap;gap:8px}
  .logo{font-size:20px;font-weight:700;color:var(--grn);letter-spacing:1px;
    text-shadow:0 0 8px rgba(51,255,119,.5)}
  .logo .prompt{color:var(--mut)}
  .clock{color:var(--mut);font-size:12px}
  .grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}
  .card{background:linear-gradient(180deg,var(--panel),var(--panel2));
    border:1px solid var(--border);border-radius:8px;padding:14px 16px;
    box-shadow:0 0 0 1px rgba(0,0,0,.4), inset 0 1px 0 rgba(51,255,119,.04)}
  .card h2{margin:0 0 12px;font-size:12px;letter-spacing:2px;text-transform:uppercase;
    color:var(--grn-dim);font-weight:700;display:flex;align-items:center;gap:8px}
  .card h2::before{content:"▸";color:var(--grn)}
  .span4{grid-column:span 4}.span6{grid-column:span 6}.span8{grid-column:span 8}
  .span12{grid-column:span 12}
  @media(max-width:900px){.span4,.span6,.span8{grid-column:span 12}}
  .kv{display:flex;justify-content:space-between;gap:10px;padding:3px 0;font-size:13px}
  .kv .k{color:var(--mut)}
  .kv .v{color:var(--txt);text-align:right;word-break:break-all}
  .pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11px;
    font-weight:700;letter-spacing:1px;border:1px solid}
  .up{color:var(--grn);border-color:var(--grn-dark);background:rgba(51,255,119,.08);
    box-shadow:0 0 10px rgba(51,255,119,.25)}
  .down{color:var(--red);border-color:#5a1a1a;background:rgba(255,85,85,.08)}
  .wait{color:var(--amber);border-color:#5a4a1a;background:rgba(255,204,68,.06)}
  .big{font-size:22px;font-weight:700;color:var(--grn);text-shadow:0 0 10px rgba(51,255,119,.4)}
  .dim{color:var(--mut)}
  .opline{background:#071009;border:1px solid var(--border);border-left:3px solid var(--grn);
    border-radius:6px;padding:12px 14px;font-size:14px;color:var(--grn);
    text-shadow:0 0 6px rgba(51,255,119,.35);word-break:break-word}
  .opline .blink{display:inline-block;width:9px;height:16px;background:var(--grn);
    margin-left:6px;vertical-align:-2px;animation:blink 1s steps(1) infinite}
  @keyframes blink{50%{opacity:0}}
  .objhead{font-size:18px;font-weight:700;color:var(--grn);text-shadow:0 0 10px rgba(51,255,119,.4);margin-bottom:12px}
  .objhead .stagetag{margin-left:10px;vertical-align:2px}
  .objbar{display:flex;gap:6px;height:22px}
  .objseg{flex:1;background:#0a130d;border:1px solid var(--border);border-radius:4px;position:relative;overflow:hidden}
  .objseg .fill{position:absolute;inset:0;background:linear-gradient(90deg,var(--grn-dark),var(--grn));opacity:0;transition:opacity .4s}
  .objseg.done .fill{opacity:1;box-shadow:0 0 12px rgba(51,255,119,.5)}
  .objseg.current{border-color:var(--amber)}
  .objseg.current .fill{opacity:.35;background:linear-gradient(90deg,#5a4a1a,var(--amber));animation:segpulse 1.2s ease-in-out infinite}
  @keyframes segpulse{50%{opacity:.12}}
  .objlabels{display:flex;gap:6px;margin-top:6px}
  .objlabels .lab{flex:1;text-align:center;font-size:10.5px;letter-spacing:.5px;color:var(--mut);text-transform:uppercase}
  .objlabels .lab.done{color:var(--grn)}
  .objlabels .lab.current{color:var(--amber);font-weight:700}
  .objmeta{margin-top:10px;font-size:12px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #0f2417}
  th{color:var(--grn-dim);font-size:11px;letter-spacing:1px;text-transform:uppercase}
  td.port{color:var(--cyan);font-weight:700}
  td.svc{color:var(--grn)}
  .boxname{color:var(--amber);font-weight:700;margin:10px 0 4px;font-size:13px}
  .boxname .art{color:var(--mut);font-weight:400;font-size:11px;margin-left:8px}
  .logwin{background:#04070a;border:1px solid var(--border);border-radius:6px;
    padding:10px 12px;height:260px;overflow-y:auto;font-size:12.5px;white-space:pre-wrap}
  .logwin .ln{padding:1px 0;border-bottom:1px solid rgba(18,58,34,.25)}
  .logwin .ln:last-child{color:var(--grn)}
  .logwin::-webkit-scrollbar{width:8px}
  .logwin::-webkit-scrollbar-thumb{background:var(--border);border-radius:4px}
  .flagcount{font-size:30px;font-weight:700;color:var(--amber);text-shadow:0 0 12px rgba(255,204,68,.4)}
  .empty{color:var(--mut);font-style:italic;padding:8px 0}
  .foot{margin-top:16px;color:var(--mut);font-size:11px;text-align:center}
  .err{color:var(--red);font-size:12px}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="logo">OPPSEC<span class="prompt">:~#</span> ops_console <span style="color:var(--mut);font-size:12px;font-weight:400">// hack-the-box lab · live</span></div>
    <div class="clock" id="clock">—</div>
  </header>

  <div class="grid">
    <div class="card span12">
      <h2>Current Objective</h2>
      <div id="objnone" class="empty" style="display:none">No active objective — spawn a machine or run recon to begin.</div>
      <div id="objmain">
        <div class="objhead" id="objhead">…</div>
        <div class="objbar" id="objbar"></div>
        <div class="objlabels" id="objlabels"></div>
        <div class="objmeta dim" id="objmeta"></div>
      </div>
    </div>

    <div class="card span4">
      <h2>Connection</h2>
      <div class="kv"><span class="k">VPN (tun0)</span><span class="v" id="vpn">…</span></div>
      <div class="kv"><span class="k">VPN IP</span><span class="v" id="vpnip">…</span></div>
      <div class="kv"><span class="k">Target</span><span class="v" id="mname">…</span></div>
      <div class="kv"><span class="k">Target IP</span><span class="v" id="mip">…</span></div>
      <div class="kv"><span class="k">Lease expires</span><span class="v" id="mexp">…</span></div>
      <div class="kv"><span class="k">Countdown</span><span class="v big" id="mcd">…</span></div>
    </div>

    <div class="card span4">
      <h2>Account</h2>
      <div class="kv"><span class="k">Operator</span><span class="v" id="aname">…</span></div>
      <div class="kv"><span class="k">Rank</span><span class="v" id="arank">…</span></div>
      <div class="kv"><span class="k">Points</span><span class="v" id="apts">…</span></div>
      <div class="kv"><span class="k">Ownership</span><span class="v" id="aown">…</span></div>
      <div id="aextra"></div>
    </div>

    <div class="card span4">
      <h2>Flags Captured</h2>
      <div class="flagcount" id="fcount">0</div>
      <div id="flist"></div>
    </div>

    <div class="card span12">
      <h2>Current Operation</h2>
      <div class="opline" id="curop"><span class="dim">waiting for activity…</span><span class="blink"></span></div>
    </div>

    <div class="card span8">
      <h2>Open Ports</h2>
      <div id="ports"><div class="empty">no recon data yet — run scripts/recon.sh &lt;ip&gt; &lt;name&gt;</div></div>
    </div>

    <div class="card span4">
      <h2>Live Log Tail</h2>
      <div class="logwin" id="log"><div class="empty">status.log is empty</div></div>
    </div>
  </div>

  <div class="foot">refresh 2s · api cache: machine 15s / account 60s · stdlib http.server :8888</div>
</div>

<script>
const RANKS={1:"Noob",2:"Script Kiddie",3:"Hacker",4:"Pro Hacker",5:"Elite",6:"Guru",7:"Omniscient"};
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function pill(txt,cls){return `<span class="pill ${cls}">${txt}</span>`}

function fmtCountdown(exp){
  if(!exp) return {txt:"—",cls:"dim"};
  // HTB expires_at like "2026-08-29 21:19:45" (UTC)
  const t=Date.parse(exp.replace(" ","T")+"Z");
  if(isNaN(t)) return {txt:exp,cls:"dim"};
  let s=Math.floor((t-Date.now())/1000);
  if(s<=0) return {txt:"EXPIRED",cls:"err"};
  const h=Math.floor(s/3600),m=Math.floor(s%3600/60),ss=s%60;
  const pad=n=>String(n).padStart(2,"0");
  return {txt:`${pad(h)}:${pad(m)}:${pad(ss)}`,cls:s<600?"err":""};
}

function render(d){
  $("clock").textContent="updated "+(d.generated_at||"—");

  // VPN
  if(d.vpn && d.vpn.up){ $("vpn").innerHTML=pill("UP","up"); $("vpnip").textContent=d.vpn.ip||"—"; }
  else { $("vpn").innerHTML=pill("DOWN","down"); $("vpnip").textContent="—"; }

  // Machine
  const m=d.machine||{};
  if(m.active){
    $("mname").innerHTML=esc(m.name)+` <span class="dim">#${esc(m.id)}</span>`;
    $("mip").textContent=m.ip||"—";
    $("mexp").textContent=m.expires_at||"—";
    const cd=fmtCountdown(m.expires_at);
    $("mcd").textContent=cd.txt; $("mcd").className="v big "+cd.cls;
  } else {
    $("mname").innerHTML=pill("NO TARGET","wait");
    $("mip").textContent="—"; $("mexp").textContent="—"; $("mcd").textContent="—";
    $("mcd").className="v big dim";
  }

  // Account
  const a=d.account||{};
  $("aname").textContent=a.name||"—";
  $("arank").textContent=(a.rank_id!=null)?(RANKS[a.rank_id]||("rank "+a.rank_id))+" ("+a.rank_id+")":"—";
  $("apts").textContent=(a.points??a.user_points??"—");
  $("aown").textContent=(a.ownership!=null)?(a.ownership+"%"):"—";
  let ex="";
  for(const k of ["system_owns","user_owns","root_owns","challenge_owns","subscriptionType"]){
    if(a[k]!=null) ex+=`<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(a[k])}</span></div>`;
  }
  $("aextra").innerHTML=ex;

  // Objective
  const o=d.objective||{};
  if(!o.active){
    $("objnone").style.display="block";
    $("objmain").style.display="none";
  } else {
    $("objnone").style.display="none";
    $("objmain").style.display="block";
    let tag="";
    if(o.stage==="complete") tag=' <span class="pill up stagetag">PWNED</span>';
    else if(o.stage_label) tag=` <span class="pill wait stagetag">${esc(o.stage_label)}</span>`;
    $("objhead").innerHTML=esc(o.headline||"—")+tag;
    const stages=o.stages||[];
    $("objbar").innerHTML=stages.map(s=>{
      const cls="objseg"+(s.done?" done":"")+((s.current&&!s.done)?" current":"");
      return `<div class="${cls}"><div class="fill"></div></div>`;
    }).join("");
    $("objlabels").innerHTML=stages.map(s=>{
      const cls="lab"+(s.done?" done":"")+((s.current&&!s.done)?" current":"");
      return `<div class="${cls}">${esc(s.label)}</div>`;
    }).join("");
    $("objmeta").textContent=`${o.completed}/${o.total} stages · ${o.pct}% · `+(o.source==="override"?"manual override":"auto-derived");
  }

  // Flags
  const flags=d.flags||[];
  $("fcount").textContent=d.flag_count??flags.length;
  $("flist").innerHTML=flags.length? flags.slice().reverse().map(f=>
    `<div class="kv"><span class="k">${esc(f.machine_name)} · ${esc(f.flag_type)}</span><span class="v">${esc(f.flag_masked)}</span></div>`
  ).join("") : `<div class="empty">no flags yet — get owning</div>`;

  // Current operation = latest log line
  const log=d.log||[];
  if(log.length){
    $("curop").innerHTML=esc(log[log.length-1])+'<span class="blink"></span>';
  } else {
    $("curop").innerHTML='<span class="dim">waiting for activity…</span><span class="blink"></span>';
  }

  // Ports per box
  const boxes=d.boxes||[];
  if(!boxes.length){
    $("ports").innerHTML='<div class="empty">no recon data yet — run scripts/recon.sh &lt;ip&gt; &lt;name&gt;</div>';
  } else {
    $("ports").innerHTML=boxes.map(b=>{
      const art=b.artifacts.length?`<span class="art">[${b.artifacts.map(esc).join(", ")}]</span>`:"";
      let rows="";
      if(b.ports && b.ports.length){
        rows=`<table><thead><tr><th>Port</th><th>Proto</th><th>State</th><th>Service</th><th>Version</th></tr></thead><tbody>`+
          b.ports.map(p=>`<tr><td class="port">${esc(p.port)}</td><td>${esc(p.proto)}</td><td>${esc(p.state)}</td><td class="svc">${esc(p.service)}</td><td>${esc(p.version)}</td></tr>`).join("")+
          `</tbody></table>`;
      } else {
        rows=`<div class="empty">no open ports parsed yet</div>`;
      }
      return `<div class="boxname">▣ ${esc(b.name)}${art}</div>${rows}`;
    }).join("");
  }

  // Log tail
  if(log.length){
    $("log").innerHTML=log.map(l=>`<div class="ln">${esc(l)}</div>`).join("");
    const lw=$("log"); lw.scrollTop=lw.scrollHeight;
  } else {
    $("log").innerHTML='<div class="empty">status.log is empty</div>';
  }
}

async function tick(){
  try{
    const r=await fetch("/status.json",{cache:"no-store"});
    if(!r.ok) throw new Error("HTTP "+r.status);
    render(await r.json());
  }catch(e){
    $("clock").innerHTML='<span class="err">status fetch failed: '+esc(e.message)+"</span>";
  }
}
tick();
setInterval(tick, __REFRESH__);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "OPPSECOpsConsole/1.0"

    def _send(self, code, body, ctype):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE.replace("__REFRESH__", str(REFRESH_MS)), "text/html; charset=utf-8")
        elif self.path.startswith("/status.json"):
            try:
                payload = build_status()
            except Exception as e:
                payload = {"generated_at": iso_now(), "error": str(e)[:300],
                           "vpn": {"up": False, "ip": None}, "machine": {}, "account": {},
                           "boxes": [], "flags": [], "flag_count": 0, "log": []}
            self._send(200, json.dumps(payload), "application/json")
        elif self.path == "/healthz":
            self._send(200, '{"ok":true}', "application/json")
        else:
            self._send(404, '{"error":"not found"}', "application/json")

    def log_message(self, fmt, *args):
        pass  # keep stdout clean; nohup log only gets real errors


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[OPPSEC ops console] http://localhost:{PORT}  (root: {HTB_ROOT})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
