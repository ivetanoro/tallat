"""Al Mac no es pot limitar de debò la memòria ni els processadors d'un programa. Això n'és una aproximació: atura i
engega el programa i tots els seus fills moltes vegades per segon, i només li deixa fer servir una part del temps.
    python freno.py 0.25 -- ordre...
Una aproximació pessimista per a una sola feina (cada fil també va a la quarta part) i no limita gens la memòria.
"""
import os
import signal
import subprocess
import sys
import threading
import time


def fills(arrel: int) -> list[int]:
    sortida = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pgid="], capture_output=True, text=True).stdout
    per_pare: dict[int, list[int]] = {}
    for l in sortida.splitlines():
        p, pp, _ = l.split()
        per_pare.setdefault(int(pp), []).append(int(p))
    tots, cua = [], [arrel]
    while cua:
        x = cua.pop()
        tots.append(x)
        cua.extend(per_pare.get(x, []))
    return tots


def main() -> int:
    part = float(sys.argv[1])
    ordre = sys.argv[sys.argv.index("--") + 1:]
    p = subprocess.Popen(ordre)
    arbre = [p.pid]
    para = threading.Event()

    def refresca():
        nonlocal arbre
        while not para.is_set():
            arbre = fills(p.pid)
            time.sleep(0.5)
    threading.Thread(target=refresca, daemon=True).start()
    cicle = 0.05
    try:
        while p.poll() is None:
            for x in arbre:
                try:
                    os.kill(x, signal.SIGSTOP)
                except OSError:
                    pass
            time.sleep(cicle * (1 - part))
            for x in arbre:
                try:
                    os.kill(x, signal.SIGCONT)
                except OSError:
                    pass
            time.sleep(cicle * part)
    finally:
        para.set()
        for x in fills(p.pid):
            try:
                os.kill(x, signal.SIGCONT)
            except OSError:
                pass
    return p.returncode or 0


if __name__ == "__main__":
    sys.exit(main())
