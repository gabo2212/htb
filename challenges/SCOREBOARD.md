# HTB Challenge Scoreboard

Free tier: 198 active challenges. Submission route: **POST /api/v4/challenge/own** `{"challenge_id":ID,"flag":"..."}`. Container spawn: **POST /api/v4/container/start** `{"containerable_id":ID}`.

| ID | Name | Category | Difficulty | Pts | Status |
|----|------|----------|-----------|-----|--------|
| 228 | BabyEncryption | Crypto | Very Easy | 10 | **solved** |
| 389 | The Last Dance | Crypto | Very Easy | 10 | **solved** |
| 365 | Baby Time Capsule | Crypto | Very Easy | 10 | **solved** |
| 824 | Low Logic | Hardware | Very Easy | 10 | **solved** |
| 207 | Debugging Interface | Hardware | Very Easy | 10 | **solved** |
| 220 | The Needle | Hardware | Very Easy | 10 | **solved** |
| 302 | CubeMadness1 | AI/ML | Very Easy | 10 | **solved** |
| 235 | RSAisEasy | Crypto | Easy | 20 | **solved** |
| 84 | Obscure | Forensics | Easy | 20 | **solved** |
| 114 | Bypass | Reversing | Easy | 20 | **solved** |
| 306 | Partial Encryption | Reversing | Easy | 20 | **solved** |
| 497 | Rhome | Crypto | Easy | 20 | queued (remote) |
| 299 | Quantum-Safe | Crypto | Easy | 20 | queued |
| 364 | Embryonic Plant | Crypto | Easy | 20 | queued (remote) |
| 250 | Protein Cookies | Crypto | Easy | 20 | queued (remote) |
| 1419 | Noise Codex | Crypto | Easy | 20 | queued |
| 121 | Exatlon | Reversing | Easy | 20 | queued |
| 231 | RAuth | Reversing | Easy | 20 | queued |
| 536 | Cyberpsychosis | Reversing | Easy | 20 | queued |
| 593 | ARMs Race | Reversing | Easy | 20 | queued |
| 360 | Diagnostic | Forensics | Easy | 20 | download failed (no file on server) |
| 188 | emo | Forensics | Easy | 20 | queued |
| 746 | Suspicious Threat | Forensics | Easy | 20 | queued |
| 446 | TrueSecrets | Forensics | Easy | 20 | queued |
| 644 | Fishy HTTP | Forensics | Easy | 20 | queued |
| 132 | Mission Pinpossible | Hardware | Easy | 20 | queued |
| 239 | Wander | Hardware | Easy | 20 | queued |
| 450 | RFlag | Hardware | Easy | 20 | queued |
| 977 | The Puppet Master | Mobile | Very Easy | 10 | download failed (no file on server) |
| 975 | Social Media Investigation Hub | Mobile | Very Easy | 10 | queued |
| 973 | The Suspicious Domain | Mobile | Very Easy | 10 | queued |
| 974 | WebVault Time Machine | Mobile | Easy | 20 | queued |
| 976 | Follow The Money | Mobile | Easy | 20 | queued |
| 252 | Micro Storage | Misc | Easy | 20 | queued |
| 115 | Cat | OSINT | Easy | 20 | queued |
| 240 | APKey | OSINT | Easy | 20 | queued |

## Points earned: 150

### Solved flags
| ID | Flag |
|----|------|
| 228 | `HTB{l00k_47_y0u_r3v3rs1ng_3qu4710n5_c0ngr475}` |
| 389 | `HTB{und3r57AnD1n9_57R3aM_C1PH3R5_15_51mPl3_a5_7Ha7}` |
| 235 | `HTB{1_m1ght_h4v3_m3ss3d_uP_jU?}` |
| 365 | `HTB{03d01b9b837357da023ba56f0d697181}` |
| 824 | `HTB{4_G00d_Cm05_3x4mpl3}` |
| 84 | `HTB{pr0tect_y0_shellZ}` |
| 207 | `HTB{d38u991n9_1n732f4c35_c4n_83_f0und_1n_41m057_3v32y_3m83dd3d_d3v1c3!!52}` |
| 220 | `HTB{4_hug3_blund3r_d289a1_!!}` |
| 302 | `HTB{CU83_M4DN355_UNM4DD3N3D}` |
| 114 | `HTB{SuP3rC00lFL4g}` |
| 306 | `HTB{W3iRd_RUnT1m3_DEC}` |

### Session notes
- **This session (+50 pts):** Bypass, CubeMadness1, The Needle, Baby Time Capsule
- **Prior total:** 100 pts (7 solved); **running total: 150 pts (11 solved)**
- Container API discovered: `POST /api/v4/container/start` with `containerable_id`
- Baby Time Capsule: Håstad broadcast attack (e=5, 5 ciphertexts) — flag rotated from old writeups
