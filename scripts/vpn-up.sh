#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

OVPN=$(ls vpn/*.ovpn 2>/dev/null | head -n1 || true)
if [ -z "${OVPN:-}" ]; then
  echo "No .ovpn pack found in htb/vpn/"
  echo "-> Log into hackthebox.com, go to Labs > Access, download your connection pack, drop it in htb/vpn/"
  exit 1
fi

if ip link show tun0 &>/dev/null; then
  echo "tun0 already up:"
  ip -4 addr show tun0 | grep inet
  exit 0
fi

sudo openvpn --config "$OVPN" --daemon --writepid /tmp/htb-vpn.pid --log /tmp/htb-vpn.log
for _ in $(seq 1 20); do
  ip link show tun0 &>/dev/null && break
  sleep 1
done

if ip link show tun0 &>/dev/null; then
  ip -4 addr show tun0 | grep inet
  echo "HTB VPN connected (log: /tmp/htb-vpn.log)"
else
  echo "tun0 never came up — check /tmp/htb-vpn.log"
  exit 1
fi
