"""La mateixa mesura de la pàgina (sonda.js), al Safari de debò, amb safaridriver.
Només si la persona ha activat el permís: «safaridriver --enable» i Desenvolupador → Permet l'automatització remota.

    python safari.py URL CARPETA_SORTIDA --escenari calent --segons 60
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PORT = 4471


def crida(metode: str, ruta: str, cos=None, temps: int = 120):
    dades = json.dumps(cos).encode() if cos is not None else None
    r = urllib.request.Request(f"http://127.0.0.1:{PORT}{ruta}", data=dades, method=metode, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=temps) as resposta:
            return json.loads(resposta.read())["value"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(e.read().decode("utf-8", "replace")[:600]) from None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("sortida", type=Path)
    ap.add_argument("--escenari", default="calent")
    ap.add_argument("--segons", type=int, default=60)
    ap.add_argument("--espera-continu", type=int, default=180)
    a = ap.parse_args()
    a.sortida.mkdir(parents=True, exist_ok=True)
    conductor = subprocess.Popen(["safaridriver", "-p", str(PORT)])
    resultat = {"motor": "safari", "cpu": 1, "escenari": a.escenari, "url": a.url}
    sessio = None
    inici = time.time()
    try:
        for _ in range(40):
            try:
                crida("GET", "/status")
                break
            except (OSError, RuntimeError):
                time.sleep(0.25)
        s = crida("POST", "/session", {"capabilities": {"alwaysMatch": {"browserName": "safari"}}})
        sessio = s["sessionId"]
        resultat["versio"] = s["capabilities"].get("browserVersion")
        crida("POST", f"/session/{sessio}/window/rect", {"width": 1440, "height": 900})
        executa = lambda codi, *arg: crida("POST", f"/session/{sessio}/execute/sync", {"script": codi, "args": list(arg)})  # noqa: E731
        t0 = time.time()
        crida("POST", f"/session/{sessio}/url", {"url": a.url}, temps=300)
        resultat["goto_ms"] = round((time.time() - t0) * 1000)
        # El Safari no deixa injectar res abans de carregar: les marques del principi surten de performance.
        executa((AQUI / "sonda.js").read_text(encoding="utf-8"))
        resultat["pot"] = executa("""const v=document.createElement('video');return {h264:v.canPlayType('video/mp4; codecs="avc1.640028"'),aac:v.canPlayType('audio/mp4; codecs="mp4a.40.2"')}""")
        fi = time.time() + 120
        while time.time() < fi and not executa("return !!window.__sonda.marques.text"):
            time.sleep(0.1)
        if a.escenari != "fred":
            t1 = time.time()
            fi = time.time() + a.espera_continu
            while time.time() < fi and not executa("return !!window.__sonda.marques.continu"):
                time.sleep(0.2)
            resultat["espera_continu_ms"] = round((time.time() - t1) * 1000)
        # El so es comença a enregistrar en el mateix clic: el Safari només el deixa engegar així.
        executa("""const b=document.getElementById('play');b.addEventListener('pointerdown',()=>{window.__sonda.capta().then(s=>window.__sonda.estatCaptura=s).catch(e=>window.__sonda.estatCaptura='error: '+e)},{capture:true,once:true});""")
        boto = crida("POST", f"/session/{sessio}/element", {"using": "css selector", "value": "#play"})
        element = next(iter(boto.values()))
        crida("POST", f"/session/{sessio}/element/{element}/click", {})
        fi = time.time() + a.segons
        while time.time() < fi:
            time.sleep(1)
            if executa("try{return !R.reproduint && !R.espera && tempsMuntatge()>duradaFinal-0.4}catch(e){return false}"):
                resultat["ha_arribat_al_final"] = True
                break
        executa("window.__sonda.marca('fi')")
        r = executa("return window.__sonda.resum()")
        resultat.update(r)
        resultat["estat_captura"] = executa("return window.__sonda.estatCaptura||null")
        with (a.sortida / "so.f32").open("wb") as f:
            for i in range(r.get("nParts") or 0):
                b = executa("return window.__sonda.treu(arguments[0])", i)
                if b:
                    f.write(base64.b64decode(b))
        foto = crida("GET", f"/session/{sessio}/screenshot")
        (a.sortida / "final.png").write_bytes(base64.b64decode(foto))
    except Exception as e:  # noqa: BLE001
        resultat["error"] = str(e)[:1000]
    finally:
        resultat["total_ms"] = round((time.time() - inici) * 1000)
        (a.sortida / "dades.json").write_text(json.dumps(resultat), encoding="utf-8")
        if sessio:
            try:
                crida("DELETE", f"/session/{sessio}")
            except (OSError, RuntimeError):
                pass
        conductor.terminate()
    print(json.dumps({"motor": "safari", "error": resultat.get("error"), "versio": resultat.get("versio")}))


if __name__ == "__main__":
    main()
