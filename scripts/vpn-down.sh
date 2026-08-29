#!/usr/bin/env bash
set -euo pipefail
if [ -f /tmp/htb-vpn.pid ]; then
  sudo kill "$(cat /tmp/htb-vpn.pid)" 2>/dev/null || true
  rm -f /tmp/htb-vpn.pid
else
  sudo pkill -f "openvpn --config" 2>/dev/null || true
fi
echo "HTB VPN disconnected"
