"""
Daemonize the uvicorn server so it persists after the parent process exits.
Usage: python3 scripts/daemonize_server.py
"""
import os
import subprocess
import sys
import time

LOG_PATH = "/tmp/server.log"
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Double-fork to fully detach
pid = os.fork()
if pid > 0:
    # Parent waits briefly then checks if server started
    time.sleep(15)
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://localhost:8765/api/health", timeout=5)
        print(f"Server healthy: {resp.read().decode()}")
    except Exception as e:
        print(f"Health check failed: {e}")
        with open(LOG_PATH) as f:
            print(f"Log:\n{f.read()[-2000:]}")
    sys.exit(0)

os.setsid()

pid2 = os.fork()
if pid2 > 0:
    sys.exit(0)

# Child: start uvicorn
os.chdir(APP_DIR)
with open(LOG_PATH, "w") as log:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "stream_processor:app",
         "--host", "0.0.0.0", "--port", "8765"],
        stdout=log,
        stderr=log,
        cwd=APP_DIR,
    )
    proc.wait()
