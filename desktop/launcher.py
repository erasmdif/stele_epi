"""
Stele Desktop — launcher unico cross-platform.

Cosa fa:
  1. determina la cartella dati dell'utente (fuori dall'app, sopravvive agli aggiornamenti);
  2. crea il progetto epigrafico al primo avvio (con dati demo);
  3. avvia il server Flask locale su una porta libera di 127.0.0.1;
  4. apre il browser sull'applicazione;
  5. resta in ascolto finché non chiudi la finestra del launcher (Ctrl+C).

Esecuzione:
  python launcher.py                      # avvio normale
  python launcher.py --no-browser         # non aprire il browser (server headless)
  python launcher.py --port 8080          # forza una porta
  python launcher.py --data-dir /path     # forza cartella dati (utile per QA)
  python launcher.py --reset-demo         # ricrea il progetto demo (cancella il precedente)

Se le dipendenze mancano (Flask), il launcher tenta un'installazione locale
via `pip install -r requirements.txt --user` — così un utente che ha solo
Python di sistema può comunque partire con un doppio clic. Se `uv` è
presente lo preferisce (più veloce e affidabile).
"""
from __future__ import annotations
import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

APP_NAME = "Stele Desktop"
APP_SLUG = "stele-desktop"          # per XDG / macOS
DEFAULT_PORT_START = 5000            # cerca la prima porta libera da qui in poi
HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Cartella dati utente (fuori dall'app, per sopravvivere agli aggiornamenti)
# ---------------------------------------------------------------------------
def user_data_dir() -> Path:
    """Cartella standard per i dati dell'utente, per convenzione OS."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    # Linux/BSD: seguo XDG Base Directory
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / APP_SLUG


def project_db_path(data_dir: Path) -> Path:
    return data_dir / "MyEpigraphicProject" / "database" / "project.gpkg"


# ---------------------------------------------------------------------------
# Setup ambiente Python (venv locale, dipendenze)
# ---------------------------------------------------------------------------
def has_uv() -> bool:
    """`uv` è il modo più affidabile per gestire Python locale.
    Nel bundle di release sarà accanto al launcher; se non c'è si cerca nel PATH."""
    if (HERE / ("uv.exe" if sys.platform == "win32" else "uv")).exists():
        return True
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _pip_install():
    """Fallback quando uv non è disponibile: pip --user."""
    req = HERE / "requirements.txt"
    if not req.exists():
        return
    print("[launcher] Installing dependencies with pip; this may take a minute…", flush=True)
    cmd = [sys.executable, "-m", "pip", "install", "--user",
           "--disable-pip-version-check", "-q", "-r", str(req)]
    subprocess.check_call(cmd)


def _uv_install():
    """Setup via uv: crea .venv locale e installa deps.
    Usa il python di sistema per bootstrap se non c'è ancora un venv."""
    venv = HERE / ".venv"
    if not venv.exists():
        print("[launcher] Preparing the Python environment with uv…", flush=True)
        subprocess.check_call(["uv", "venv", str(venv)])
    print("[launcher] Installing dependencies…", flush=True)
    subprocess.check_call(["uv", "pip", "install",
                            "--python", str(venv / ("Scripts" if sys.platform == "win32" else "bin") / "python"),
                            "-r", str(HERE / "requirements.txt")])


def ensure_deps():
    """Assicura che flask sia importabile. Se no, installa."""
    try:
        import flask  # noqa
        return
    except ImportError:
        pass
    if has_uv():
        try:
            _uv_install()
        except Exception as e:
            print(f"[launcher] uv failed ({e}); trying pip.", flush=True)
            _pip_install()
    else:
        _pip_install()
    # riprova
    try:
        import flask  # noqa
    except ImportError:
        raise SystemExit(
            "[launcher] Flask could not be installed. "
            "Try installing it manually: pip install -r requirements.txt")


# ---------------------------------------------------------------------------
# Porta libera + server Flask
# ---------------------------------------------------------------------------
def find_free_port(start: int = DEFAULT_PORT_START, max_tries: int = 200) -> int:
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port between {start} and {start + max_tries}.")


def wait_for_server(port: int, timeout: float = 20.0) -> bool:
    """Attende che il server risponda sulla porta locale."""
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                return True
            except (OSError, socket.timeout):
                time.sleep(0.15)
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(prog="stele-desktop",
                                 description=f"Start {APP_NAME}.")
    p.add_argument("--port", type=int, default=None,
                   help="Port to use; default is the first free port from 5000.")
    p.add_argument("--no-browser", action="store_true",
                   help="Do not open the browser automatically.")
    p.add_argument("--data-dir", type=Path, default=None,
                   help="Data directory; default is the standard OS location.")
    p.add_argument("--reset-demo", action="store_true",
                   help="Delete and recreate the sample project.")
    p.add_argument("--host", default="127.0.0.1",
                   help="Bind host; default is 127.0.0.1.")
    return p.parse_args()


def main():
    args = parse_args()

    # 1. dipendenze
    ensure_deps()

    # 2. cartella dati e path db
    data_dir = args.data_dir or user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "MyEpigraphicProject" / "database" / "project.gpkg"

    # reset opzionale
    if args.reset_demo and db_path.exists():
        db_path.unlink()
        print(f"[launcher] Sample project deleted: {db_path}", flush=True)

    # 3. env per l'app Flask
    os.environ["STELE_PROJECT_DB"] = str(db_path)
    os.environ["STELE_HOST"] = args.host
    port = args.port or find_free_port()
    os.environ["STELE_PORT"] = str(port)

    # 4. importa e avvia Flask in un thread
    #    (import qui perché ensure_deps() dev'essere già passato)
    sys.path.insert(0, str(HERE))
    try:
        from stele_app import create_app  # type: ignore
    except Exception as e:
        raise SystemExit(f"[launcher] Could not import stele_app: {e}")

    app = create_app(str(db_path))

    # inizializzazione del progetto (crea demo al primo avvio)
    from stele_app.db import project as project_mod
    if not db_path.exists():
        print(f"[launcher] First run: creating the sample project at\n           {db_path}", flush=True)
        project_mod.create_project(str(db_path), with_demo=True, overwrite=False)

    url = f"http://{args.host}:{port}/"
    bar = "─" * 52
    print(f"\n┌{bar}┐", flush=True)
    print(f"│  {APP_NAME}", flush=True)
    print(f"│  URL:  {url}", flush=True)
    print(f"│  Data: {db_path}", flush=True)
    print(f"└{bar}┘", flush=True)
    print("\nPress Ctrl+C in this window to stop Stele Desktop.\n", flush=True)

    def _run():
        # use_reloader=False è essenziale in un launcher (altrimenti fork doppio)
        app.run(host=args.host, port=port, debug=False, use_reloader=False, threaded=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    if not wait_for_server(port):
        raise SystemExit("[launcher] The local server did not respond in time.")

    if not args.no_browser:
        webbrowser.open(url)

    # mantengo il processo vivo finché l'utente non ferma
    try:
        while t.is_alive():
            t.join(timeout=1.0)
    except KeyboardInterrupt:
        print(f"\n[launcher] Stopping {APP_NAME}.", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
