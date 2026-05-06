#!/bin/bash
set -euo pipefail

# Resolve project root (directory containing this script)
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="${PROJECT_DIR}/data/outreach_cron.log"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$PROJECT_DIR"

{
  echo "------------------------------------------"
  echo "Starting daily outreach at $(date)"
  "$PYTHON_BIN" -u ghostwriter/daily_outreach.py --live
  echo "Completed daily outreach at $(date)"
  echo "------------------------------------------"
} >>"$LOG_FILE" 2>&1
