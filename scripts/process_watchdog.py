"""
Process watchdog for the sandbox — keeps uvicorn alive.
Runs inside the Daytona sandbox as a daemon.
If uvicorn dies, restarts it immediately.

Usage: python3 scripts/process_watchdog.py
"""
import os
import subprocess
import sys
import time
import urllib.request

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = "/tmp/server.log"
WATCHDOG_LOG = "/tmp/watchdog.log"
HEALTH_URL = "http://localhost:8765/api/health"
CHECK_INTERVAL = 10  # seconds


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(WATCHDOG_LOG, "a") as f:
        f.write(line + "\n")


def is_server_healthy():
    try:
        resp = urllib.request.urlopen(HEALTH_URL, timeout=5)
        return resp.getcode() == 200
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
    log("Watchdog started")

    # Double-fork to daemonize
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)

    proc = None

    while True:
        if not is_server_healthy():
            log("Server unhealthy — checking process...")

            # Kill zombie process if any
            if proc and proc.poll() is None:
                log(f"Killing old process {proc.pid}")
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass

            proc = start_server()
            # Wait for startup
            time.sleep(15)

            if is_server_healthy():
                log("Server recovered successfully")
            else:
                log("Server still unhealthy after restart — will retry next cycle")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
