# OPPSEC Multi-Agent Workflow

## The constraint that shapes everything
HTB free tier = **1 spawned machine at a time**. The machine pipeline is serial per box.
But **challenges don't consume the machine slot** — they run as downloadable files or per-user dockers. That's a parallel points stream.

## Agent roster
| Agent | Type | Job |
|---|---|---|
| Coordinator | main chat | machine lifecycle (spawn/stop), routing, blockers, user comms |
| Recon shell | automated script | nmap sweep → service scan → ffuf/vhost/subdomain (3-5 min) |
| Enum worker | subagent | app-layer analysis: JS bundles, endpoints, auth model, versions |
| Exploit worker | subagent | foothold → user flag → privesc → root flag → submit |
| Hypothesis racers | subagents | ONLY when exploit worker stalls: 2-3 parallel attack attempts |
| Docs worker | subagent | walkthroughs + learning notes, async after each box |
| Challenge farmer | subagent | parallel stream: solves challenges while machines run |

## Per-box pipeline (target: < 30 min per Easy box)
1. T+0 — previous box's root flag lands → coordinator spawns next box IMMEDIATELY + launches recon shell
2. T+2 — "ports open" signal → enum worker launches (runs parallel to ffuf finishing)
3. T+8 — enum report → exploit worker launches with ranked hypotheses + any public PoC
4. Stall protocol — exploit worker reports blocked → coordinator launches 2-3 hypothesis racers on the distinct candidate vectors
5. Root flag → docs worker updates walkthrough (async) WHILE coordinator spawns next box (back to 1)

## Parallel points streams
- **Stream A: machines** — serial, 20 pts per Easy box (Reactor ✓ Connected ✓ Cohort user ✓ root pending)
- **Stream B: challenges** — parallel, **100 pts earned** (7 solved — see `challenges/SCOREBOARD.md`)
- **Stream C: docs** — parallel, zero points but compounds hiring value

## Handoff protocol
- Shared state: htb/objective.json (current target+stage), htb/flags.log, boxes/<name>/notes.md
- Every worker logs to htb/status.log → dashboard shows all streams live
- Flag submission: scripts/own.sh (v5 API, verified)
