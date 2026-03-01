#!/bin/bash
# One-time setup: installs the watchdog auto-start hooks inside the Daytona sandbox.
# Run via: daytona exec <sandbox-id> -- bash /home/daytona/app/scripts/setup_sandbox_watchdog.sh
set -e

APP_DIR="/home/daytona/app"
PROFILE_SCRIPT="/etc/profile.d/specter-watchdog.sh"
BASHRC="$HOME/.bashrc"
MARKER="# specter-watchdog-hook"

echo "=== Setting up sandbox self-healing watchdog ==="

# 1. Install /etc/profile.d/ hook (runs on every new login shell)
echo "Installing $PROFILE_SCRIPT ..."
sudo tee "$PROFILE_SCRIPT" > /dev/null << 'EOF'
#!/bin/bash
# Auto-start the Specter watchdog on every shell login
PID_FILE="/tmp/watchdog.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
  : # already running
else
  bash /home/daytona/app/scripts/start_watchdog.sh &
fi
EOF
sudo chmod +x "$PROFILE_SCRIPT"
echo "  -> done"

# 2. Append .bashrc hook as backup (for non-login shells)
if ! grep -q "$MARKER" "$BASHRC" 2>/dev/null; then
  echo "Appending watchdog hook to $BASHRC ..."
  cat >> "$BASHRC" << EOF

$MARKER
# Auto-start watchdog if not running (backup for non-login shells)
if [ -f /home/daytona/app/scripts/start_watchdog.sh ]; then
  bash /home/daytona/app/scripts/start_watchdog.sh &
fi
EOF
  echo "  -> done"
else
  echo "  -> .bashrc hook already present, skipping"
fi

# 3. Start the watchdog right now
echo "Starting watchdog now..."
bash "$APP_DIR/scripts/start_watchdog.sh"
sleep 2

if [ -f /tmp/watchdog.pid ] && kill -0 "$(cat /tmp/watchdog.pid)" 2>/dev/null; then
  echo "Watchdog running (PID $(cat /tmp/watchdog.pid))"
else
  echo "WARNING: Watchdog may not have started — check /tmp/watchdog.log"
fi

echo "=== Setup complete ==="
