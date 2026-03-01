"""
Self-healing watchdog for the Daytona sandbox.
Monitors uvicorn AND pings the Fly.io signal server to keep it awake.
Uses a PID file to prevent duplicate instances.

Usage: python3 scripts/process_watchdog.py
"""
import atexit
import os
import signal
import subprocess
import sys
import time
import urllib.request

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = "/tmp/server.log"
WATCHDOG_LOG = "/tmp/watchdog.log"
PID_FILE = "/tmp/watchdog.pid"
HEALTH_URL = "http://localhost:8765/api/health"
SIGNAL_URL = "https://visionclaw-signal.fly.dev/"
CHECK_INTERVAL = 10  # seconds between uvicorn health checks
SIGNAL_PING_INTERVAL = 30  # seconds between signal server pings
HEARTBEAT_INTERVAL = 300  # 5 minutes between heartbeat log entries
LOG_MAX_BYTES = 1_000_000  # 1 MB max log size


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(WATCHDOG_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def rotate_log():
    """Truncate log file if it exceeds LOG_MAX_BYTES by keeping the last half."""
    try:
        if not os.path.exists(WATCHDOG_LOG):
            return
        size = os.path.getsize(WATCHDOG_LOG)
        if size <= LOG_MAX_BYTES:
            return
        # Keep the last half of the file
        with open(WATCHDOG_LOG, "r") as f:
            f.seek(size // 2)
            f.readline()  # skip partial line
            remaining = f.read()
        with open(WATCHDOG_LOG, "w") as f:
            f.write("--- log rotated ---\n")
            f.write(remaining)
        log("Log rotated (was %d bytes)" % size)
    except Exception:
        pass


def get_proxy_url():
    """Try to get the current Daytona proxy URL."""
    try:
        result = subprocess.run(
            ["daytona", "preview-url", "8765"],
            capture_output=True, text=True, timeout=10,
        )
        url = result.stdout.strip()
        if url and url.startswith("http"):
            return url
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return None


def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(cleanup_pid)


def cleanup_pid():
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f:
                if int(f.read().strip()) == os.getpid():
                    os.remove(PID_FILE)
    except Exception:
        pass


def is_already_running():
    """Check if another watchdog is already running via PID file."""
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # signal 0 = check if process exists
        return True
    except (OSError, ValueError):
        # Process doesn't exist or PID file is corrupt — stale PID file
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
        return False


def is_server_healthy():
    try:
        resp = urllib.request.urlopen(HEALTH_URL, timeout=5)
        return resp.getcode() == 200
    except Exception:
        return False


def ping_signal_server():
    """HTTP GET to Fly.io signal server to keep the machine from auto-stopping."""
    try:
        urllib.request.urlopen(SIGNAL_URL, timeout=10)
        return True
    except Exception:
        return False


def start_server():
    log("Starting uvicorn server...")
    with open(LOG_PATH, "a") as logf:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "stream_processor:app",
             "--host", "0.0.0.0", "--port", "8765"],
            stdout=logf,
            stderr=logf,
            cwd=APP_DIR,
        )
    log(f"Server started with PID {proc.pid}")
    return proc


def main():
    if is_already_running():
        print("Watchdog already running, exiting.")
        sys.exit(0)

    # Double-fork to daemonize
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)

    # Redirect stdin/stdout/stderr to /dev/null for clean daemon
    sys.stdin = open(os.devnull, "r")
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

    write_pid()
    start_time = time.time()
    log("Watchdog started (PID %d)" % os.getpid())

    # Log the current proxy URL on startup
    proxy_url = get_proxy_url()
    if proxy_url:
        log("Proxy URL: %s" % proxy_url)
    else:
        log("Proxy URL: could not detect (daytona CLI not available or failed)")
    last_known_proxy = proxy_url

    # Ignore SIGHUP so we survive terminal close
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    proc = None
    last_signal_ping = 0
    last_heartbeat = 0
    last_log_rotate_check = 0
    signal_was_ok = True  # Track state for change-only logging

    while True:
        now = time.time()

        # --- Uvicorn health check ---
        if not is_server_healthy():
            log("Server unhealthy — checking process...")

            if proc and proc.poll() is None:
                log(f"Killing old process {proc.pid}")
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass

            proc = start_server()
            time.sleep(15)

            if is_server_healthy():
                log("Server recovered successfully")
            else:
                log("Server still unhealthy after restart — will retry next cycle")

        # --- Signal server ping (only log on state change) ---
        if now - last_signal_ping >= SIGNAL_PING_INTERVAL:
            ok = ping_signal_server()
            if not ok and signal_was_ok:
                log("Signal server ping FAILED (was OK)")
            elif ok and not signal_was_ok:
                log("Signal server ping recovered (was failing)")
            signal_was_ok = ok
            last_signal_ping = now

        # --- Heartbeat with uptime ---
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            uptime_min = round((now - start_time) / 60, 1)
            log("Heartbeat — uptime=%.1fmin uvicorn_healthy=%s signal_ok=%s" % (
                uptime_min, is_server_healthy(), signal_was_ok))
            last_heartbeat = now

        # --- Log rotation check (every 5 minutes) ---
        if now - last_log_rotate_check >= 300:
            rotate_log()
            last_log_rotate_check = now

        # --- Proxy URL change detection (every heartbeat) ---
        if now - last_heartbeat < CHECK_INTERVAL:  # runs right after heartbeat
            new_proxy = get_proxy_url()
            if new_proxy and last_known_proxy and new_proxy != last_known_proxy:
                log("WARNING: Proxy URL changed! old=%s new=%s" % (last_known_proxy, new_proxy))
            if new_proxy:
                last_known_proxy = new_proxy

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
