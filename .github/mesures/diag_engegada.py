"""Per què la pàgina triga a engegar-se: cronometra els passos sospitosos i, si s'encalla, diu on.

    python diag_engegada.py [CARPETA_DEL_VIDEO PORT]
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ARREL = Path(__file__).resolve().parents[2]


def cron(nom: str, f) -> None:
    t = time.time()
    try:
        r = f()
    except OSError as e:
        r = f"error: {e}"
    print(f"{time.time() - t:7.2f} s  {nom}: {r}", flush=True)


def servidor() -> str:
    s = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    nom = s.server_name
    s.server_close()
    return nom


def revisa(projecte: str, port: str) -> None:
    """L'ordre de debò, i cada 8 s on és. Es para quan diu l'adreça."""
    codi = ("import faulthandler, runpy, sys; faulthandler.dump_traceback_later(8, repeat=True); "
            f"sys.argv = ['tallat.py', 'revisa', '--projecte', {projecte!r}, '--port', {port!r}, '--sense-navegador']; "
            f"runpy.run_path({str(ARREL / 'tallat.py')!r}, run_name='__main__')")
    t = time.time()
    s = subprocess.Popen([sys.executable, "-c", codi], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", cwd=ARREL)
    for linia in s.stdout:
        print("    " + linia.rstrip()[:160], flush=True)
        if "http://127.0.0.1" in linia:
            break
    print(f"{time.time() - t:7.2f} s  ordre revisa, fins que diu l'adreça", flush=True)
    s.kill()


for i in range(3):
    cron("gethostname", socket.gethostname)
    cron("getfqdn de 127.0.0.1 (el que fa el servidor en engegar-se)", lambda: socket.getfqdn("127.0.0.1"))
    cron("gethostbyaddr de 127.0.0.1", lambda: socket.gethostbyaddr("127.0.0.1")[0])
    cron("gethostbyname de localhost", lambda: socket.gethostbyname("localhost"))
    cron("crear el servidor", servidor)
if len(sys.argv) > 2:
    import cami
    import mesura
    font = mesura.Font(Path(sys.argv[1]))
    projecte = Path(sys.argv[1]) / "projecte-diag"
    if not (projecte / "transcripcio.json").exists():
        cami.crea_projecte(font, projecte, 0.35, font.dades["llavor"])
    revisa(str(projecte), sys.argv[2])  # la primera fa la còpia lleugera; la segona és només engegar-se
    revisa(str(projecte), sys.argv[2])
