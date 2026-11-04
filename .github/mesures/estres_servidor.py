"""Repeteix el setUp de TestServidor moltes vegades: quant triga GET /api/projecte? Si passa de 3 s, bolca on és cada fil."""
import faulthandler, json, sys, tempfile, threading, time, http.client, socket, statistics, re
from pathlib import Path
from unittest import mock
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
import proves  # noqa
from motor import marca, servidor
from motor.projecte import Projecte

def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

def peticio(p, ruta, temps=30):
    c = http.client.HTTPConnection("127.0.0.1", p, timeout=temps)
    c.putrequest("GET", ruta, skip_host=True); c.putheader("Host", f"127.0.0.1:{p}"); c.putheader("Content-Length", "0"); c.endheaders()
    r = c.getresponse(); d = r.read(); c.close(); return r.status, d

N = int(sys.argv[1]); llindar = float(sys.argv[2]) if len(sys.argv) > 2 else 3
tp, ta = [], []; dolents = 0
for i in range(N):
    d, casa = tempfile.TemporaryDirectory(ignore_cleanup_errors=True), tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    peg = [mock.patch.object(marca, "KITS", Path(casa.name) / "kits"), mock.patch.object(marca, "USUARI", Path(casa.name) / "brand.json")]
    for x in peg: x.start()
    c = Path(d.name)
    par = [{"id": j, "text": t, "inici": j * .5, "final": j * .5 + .4, "frase": 0} for j, t in enumerate("Hola. Això és una prova.".split())]
    (c / "transcripcio.json").write_text(json.dumps({"video": str(c / "no.mov"), "fps": "30", "durada": 3.0, "paraules": par}), encoding="utf-8")
    p = port(); s = servidor.crea_servidor(Projecte(c), p)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    t0 = time.perf_counter(); peticio(p, "/"); t1 = time.perf_counter()
    faulthandler.dump_traceback_later(llindar, exit=False, file=sys.stderr)
    peticio(p, "/api/projecte"); t2 = time.perf_counter()
    faulthandler.cancel_dump_traceback_later()
    tp.append(t1 - t0); ta.append(t2 - t1)
    if t2 - t1 > llindar: dolents += 1; print(f"#{i}: {t2 - t1:.1f}s", flush=True)
    s.shutdown(); s.server_close()
    for x in peg: x.stop()
    d.cleanup(); casa.cleanup()
print(json.dumps({"n": N, "dolents": dolents, "pagina_mediana_ms": round(statistics.median(tp) * 1e3, 1), "projecte_mediana_ms": round(statistics.median(ta) * 1e3, 1),
                  "projecte_max_ms": round(max(ta) * 1e3, 1)}))
