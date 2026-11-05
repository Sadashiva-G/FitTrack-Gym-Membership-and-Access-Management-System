"""FitTrack Application Launcher.

Starts the FastAPI backend and Streamlit frontend together.
"""

import os
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_PORT = 8501


def wait_for_backend(host: str, port: int, timeout: int = 15) -> bool:
    """Poll backend health check until available or timeout."""
    url = f"http://{host}:{port}/health"
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (URLError, ConnectionResetError, OSError):
            time.sleep(0.5)
    return False


def main():
    """Launch backend and frontend processes concurrently."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)

    print("=" * 60)
    print("🏋️  Starting FitTrack: Gym Membership & Access Management System")
    print("=" * 60)

    python_executable = sys.executable

    # 1. Start FastAPI Backend via uvicorn
    backend_cmd = [
        python_executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        BACKEND_HOST,
        "--port",
        str(BACKEND_PORT),
    ]

    print(f"\n[1/2] Launching Backend on http://{BACKEND_HOST}:{BACKEND_PORT} ...")
    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=project_root,
        stdout=None,
        stderr=None,
    )

    # Wait for backend to be ready
    print("Waiting for backend API to initialize...")
    if wait_for_backend(BACKEND_HOST, BACKEND_PORT, timeout=15):
        print("✅ Backend API is ready!")
    else:
        print("⚠️ Backend check timed out, proceeding with frontend launch...")

    # 2. Start Streamlit Frontend
    frontend_cmd = [
        python_executable,
        "-m",
        "streamlit",
        "run",
        "frontend/app.py",
        "--server.port",
        str(FRONTEND_PORT),
        "--server.headless",
        "true",
    ]

    print(f"\n[2/2] Launching Streamlit UI on http://127.0.0.1:{FRONTEND_PORT} ...")
    frontend_proc = subprocess.Popen(
        frontend_cmd,
        cwd=project_root,
        stdout=None,
        stderr=None,
    )

    print("\n" + "=" * 60)
    print("🎉 FitTrack is now running!")
    print(f"   👉 Streamlit Web App : http://127.0.0.1:{FRONTEND_PORT}")
    print(f"   👉 FastAPI API Docs   : http://{BACKEND_HOST}:{BACKEND_PORT}/docs")
    print(f"   👉 API Health Check   : http://{BACKEND_HOST}:{BACKEND_PORT}/health")
    print("=" * 60)
    print("Press Ctrl+C to stop both servers gracefully.\n")

    def terminate_subprocesses(signum=None, frame=None):
        print("\nStopping FitTrack services...")
        for name, proc in [("Frontend", frontend_proc), ("Backend", backend_proc)]:
            if proc.poll() is None:
                print(f"Terminating {name} (PID: {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("All FitTrack services stopped. Goodbye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, terminate_subprocesses)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, terminate_subprocesses)

    # Monitor processes
    try:
        while True:
            b_code = backend_proc.poll()
            f_code = frontend_proc.poll()
            if b_code is not None:
                print(f"\nBackend process exited with code {b_code}.")
                terminate_subprocesses()
                break
            if f_code is not None:
                print(f"\nFrontend process exited with code {f_code}.")
                terminate_subprocesses()
                break
            time.sleep(1)
    except KeyboardInterrupt:
        terminate_subprocesses()


if __name__ == "__main__":
    main()
