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


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(WATCHDOG_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


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
    log("Watchdog started (PID %d)" % os.getpid())

    # Ignore SIGHUP so we survive terminal close
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    proc = None
    last_signal_ping = 0
    last_heartbeat = 0

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

        # --- Signal server ping ---
        if now - last_signal_ping >= SIGNAL_PING_INTERVAL:
            ok = ping_signal_server()
            if not ok:
                log("Signal server ping failed")
            last_signal_ping = now

        # --- Heartbeat ---
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            log("Heartbeat — watchdog alive, uvicorn healthy=%s" % is_server_healthy())
            last_heartbeat = now

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
