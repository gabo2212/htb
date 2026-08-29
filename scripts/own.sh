#!/usr/bin/env bash
# usage: own.sh <machine_id> <machine_name> <user|root> <flag>
# Records the flag locally (htb/flags.log), submits it to HTB, and logs the result.
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: own.sh <machine_id> <machine_name> <user|root> <flag>" >&2
  exit 1
fi

MID="$1"
MNAME="$2"
FTYPE="$3"
FLAG="$4"

if [ "$FTYPE" != "user" ] && [ "$FTYPE" != "root" ]; then
  echo "error: flag_type must be 'user' or 'root' (got '$FTYPE')" >&2
  exit 1
fi

DIR="$(cd "$(dirname "$0")/.." && pwd)"
FLAGS="$DIR/flags.log"
LOG_STATUS="$DIR/scripts/log_status.sh"

printf '%s|%s|%s|%s|%s\n' "$(date -Iseconds)" "$MID" "$MNAME" "$FTYPE" "$FLAG" >> "$FLAGS"

if python3 "$DIR/scripts/htb_api.py" own "$MID" "$FLAG"; then
  "$LOG_STATUS" "own: $FTYPE flag for $MNAME (id $MID) accepted"
else
  "$LOG_STATUS" "own: $FTYPE flag for $MNAME (id $MID) REJECTED by HTB"
  exit 1
fi
