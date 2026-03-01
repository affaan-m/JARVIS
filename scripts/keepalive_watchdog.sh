#!/bin/bash
# =============================================================================
# Keepalive Watchdog — runs on the Mac Mini, pings both services every 10s.
# Restarts sandbox / Fly machines if either goes down.
#
# Install as launchd agent:
#   cp com.specter.keepalive.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.specter.keepalive.plist
#
# Or run directly: bash scripts/keepalive_watchdog.sh
# =============================================================================

SANDBOX_ID="human-detection-persistent"
SANDBOX_URL="https://8765-lmj1waztb18al1vu.proxy.daytona.works/api/health"
SIGNAL_URL="https://visionclaw-signal.fly.dev/"
FLY_APP="visionclaw-signal"
LOG_FILE="/tmp/specter-watchdog.log"
CHECK_INTERVAL=10

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_sandbox() {
  local resp
  resp=$(curl -s --max-time 8 -o /dev/null -w "%{http_code}" "$SANDBOX_URL" 2>/dev/null)
  if [ "$resp" = "200" ]; then
    return 0
  else
    return 1
  fi
}

check_signal() {
  local resp
  resp=$(curl -s --max-time 8 -o /dev/null -w "%{http_code}" "$SIGNAL_URL" 2>/dev/null)
  if [ "$resp" = "200" ] || [ "$resp" = "101" ] || [ "$resp" = "301" ] || [ "$resp" = "302" ]; then
    return 0
  else
    return 1
  fi
}

recover_sandbox() {
  log "SANDBOX DOWN — attempting recovery..."

  # Check if sandbox is stopped
  local state
  state=$(daytona sandbox info "$SANDBOX_ID" 2>/dev/null | grep "State" | awk '{print $2}')

  if [ "$state" = "STOPPED" ] || [ "$state" = "ARCHIVED" ]; then
    log "Sandbox state: $state — starting..."
    daytona sandbox start "$SANDBOX_ID" 2>&1 | tee -a "$LOG_FILE"
    sleep 5
  fi

  # Pull latest code
  log "Pulling latest code..."
  daytona exec "$SANDBOX_ID" -- git -C /home/daytona/app pull origin human-detection 2>&1 | tee -a "$LOG_FILE"

  # Start the process watchdog (which starts uvicorn)
  log "Starting process watchdog..."
  daytona exec "$SANDBOX_ID" -- python3 /home/daytona/app/scripts/process_watchdog.py 2>&1 | tee -a "$LOG_FILE"

  # Wait for server to come up
  sleep 20

  if check_sandbox; then
    log "SANDBOX RECOVERED"
  else
    log "SANDBOX STILL DOWN — will retry next cycle"
  fi
}

recover_signal() {
  log "SIGNAL SERVER DOWN — attempting recovery..."

  # Start any stopped machines
  local machines
  machines=$(fly machine list -a "$FLY_APP" 2>/dev/null | grep "stopped" | awk '{print $1}')

  for mid in $machines; do
    log "Starting Fly machine $mid..."
    fly machine start "$mid" -a "$FLY_APP" 2>&1 | tee -a "$LOG_FILE"
  done

  # Ping the URL to trigger auto-start
  curl -s --max-time 10 "$SIGNAL_URL" > /dev/null 2>&1

  sleep 5

  if check_signal; then
    log "SIGNAL SERVER RECOVERED"
  else
    log "SIGNAL SERVER STILL DOWN — will retry next cycle"
  fi
}

# ---- Main loop ----
log "========================================="
log "Keepalive watchdog started"
log "Sandbox: $SANDBOX_URL"
log "Signal:  $SIGNAL_URL"
log "Interval: ${CHECK_INTERVAL}s"
log "========================================="

sandbox_fail_count=0
signal_fail_count=0

while true; do
  # Check sandbox
  if check_sandbox; then
    if [ "$sandbox_fail_count" -gt 0 ]; then
      log "Sandbox back online after $sandbox_fail_count failures"
    fi
    sandbox_fail_count=0
  else
    sandbox_fail_count=$((sandbox_fail_count + 1))
    log "Sandbox check failed ($sandbox_fail_count consecutive)"
    # Recover after 2 consecutive failures (20s of downtime) to avoid false positives
    if [ "$sandbox_fail_count" -ge 2 ]; then
      recover_sandbox
      sandbox_fail_count=0
    fi
  fi

  # Check signal server
  if check_signal; then
    if [ "$signal_fail_count" -gt 0 ]; then
      log "Signal server back online after $signal_fail_count failures"
    fi
    signal_fail_count=0
  else
    signal_fail_count=$((signal_fail_count + 1))
    log "Signal check failed ($signal_fail_count consecutive)"
    if [ "$signal_fail_count" -ge 2 ]; then
      recover_signal
      signal_fail_count=0
    fi
  fi

  sleep "$CHECK_INTERVAL"
done
