#!/usr/bin/env bash
# usage: log_status.sh "message"
# Appends "ISO8601_timestamp message" to htb/status.log (creates it if needed).
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: log_status.sh \"message\"" >&2
  exit 1
fi

DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$DIR/status.log"
mkdir -p "$DIR"

printf '%s %s\n' "$(date -Iseconds)" "$*" >> "$LOG"
