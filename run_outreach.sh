#!/usr/bin/env bash
# Run faculty outreach: pick best resume per faculty, send personalized email, update tracker.
# Usage:
#   ./run_outreach.sh           # dry run (no send)
#   ./run_outreach.sh 10        # send to 10 faculty (live)
#   ./run_outreach.sh live 10   # same as above

set -e
cd "$(dirname "$0")"

if [ "$1" = "live" ]; then
  LIMIT="${2:-10}"
else
  LIMIT="${1:-0}"
fi

if [ -z "$LIMIT" ] || [ "$LIMIT" = "0" ]; then
  echo "Dry run (no emails sent). To send to 10 faculty: ./run_outreach.sh 10"
  python ghostwriter/daily_outreach.py
else
  echo "Sending to $LIMIT faculty (live). You may be prompted for Gmail auth."
  python ghostwriter/daily_outreach.py --live --limit "$LIMIT"
fi
