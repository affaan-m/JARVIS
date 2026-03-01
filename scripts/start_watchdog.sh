#!/bin/bash
# Idempotent watchdog starter — safe to call from .bashrc / /etc/profile.d/
# Checks PID file before starting to avoid duplicate instances.
PID_FILE="/tmp/watchdog.pid"
APP_DIR="/home/daytona/app"

# Already running? Exit silently.
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
  exit 0
fi

# Start the watchdog (it daemonizes itself via double-fork)
cd "$APP_DIR" 2>/dev/null || exit 0
nohup python3 scripts/process_watchdog.py > /dev/null 2>&1 &
