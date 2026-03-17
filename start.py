"""
start.py — Sobe backend (FastAPI) e frontend (Vite) em um único comando.

Uso:
    python start.py
"""

import subprocess
import sys
import os
import signal
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.join(ROOT, "frontend")

def main():
    procs = []

    # Backend: uvicorn
    print("[AlphaCota] Iniciando backend (FastAPI) na porta 8000...")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--reload", "--port", "8000"],
        cwd=ROOT,
    )
    procs.append(backend)

    # Frontend: vite dev
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    print("[AlphaCota] Iniciando frontend (Vite) na porta 8080...")
    frontend = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=FRONTEND,
    )
    procs.append(frontend)

    print()
    print("=" * 50)
    print("  AlphaCota rodando!")
    print("  Frontend:  http://localhost:8080")
    print("  API Docs:  http://localhost:8000/docs")
    print("  Ctrl+C para parar tudo")
    print("=" * 50)
    print()

    try:
        # Wait for any process to exit
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[AlphaCota] Encerrando...")
    finally:
        for p in procs:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                p.kill()

    print("[AlphaCota] Encerrado.")


if __name__ == "__main__":
    main()
