#!/usr/bin/env bash
# usage: recon.sh <target-ip> <box-name>
set -euo pipefail
IP=$1
NAME=$2
DIR="$(cd "$(dirname "$0")/.." && pwd)/boxes/$NAME"
mkdir -p "$DIR/nmap" "$DIR/loot"
cd "$DIR"

LOG_STATUS="$(cd "$(dirname "$0")/.." && pwd)/scripts/log_status.sh"
"$LOG_STATUS" "recon: start $NAME ($IP)"

NMAP="nmap"
if [ "$(id -u)" -ne 0 ] && [ -z "$(getcap "$(command -v nmap)" 2>/dev/null)" ]; then
  NMAP="sudo nmap"
fi

echo "[*] Phase 1: full TCP sweep on $IP"
$NMAP -p- --min-rate 2000 -T4 -oN nmap/allports.txt "$IP"

PORTS=$(awk -F/ '/\/tcp +open/{print $1}' nmap/allports.txt | paste -sd, -)
if [ -z "$PORTS" ]; then
  echo "[!] No open TCP ports found. Box up? VPN connected? (scripts/vpn-up.sh)"
  exit 1
fi
echo "[*] Open ports: $PORTS"
"$LOG_STATUS" "recon: port sweep done on $IP — open: $PORTS"

echo "[*] Phase 2: service/version scan"
$NMAP -sC -sV -p "$PORTS" -oN nmap/services.txt "$IP"
cat nmap/services.txt
"$LOG_STATUS" "recon: service scan done on $IP ($PORTS)"

HTTP_PORTS=$(awk -F'[ /]' '/\/tcp +open/ && ($4 ~ /http/ || $1 ~ /^(80|443|8000|8080|8443|3000|5000)$/) {print $1}' nmap/services.txt)
for p in $HTTP_PORTS; do
  scheme="http"; [ "$p" = "443" ] || [ "$p" = "8443" ] && scheme="https"
  echo "[*] Phase 3: ffuf directory brute on $scheme://$IP:$p"
  "$LOG_STATUS" "recon: ffuf start $scheme://$IP:$p"
  ffuf -u "$scheme://$IP:$p/FUZZ" \
       -w /usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt \
       -mc 200,204,301,302,307,401,403 \
       -o "ffuf-$p.json" -of json -s || true
  "$LOG_STATUS" "recon: ffuf done $scheme://$IP:$p"
done

echo "[*] Recon done -> $DIR"
"$LOG_STATUS" "recon: complete $NAME ($IP) -> $DIR"
