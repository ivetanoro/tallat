"""Engega un servidor de prova per projecte (fora del port de la persona) i passa la pàgina pels navegadors.

    python tanda_pagina.py RESULTATS.json --video CARPETA --motor chrome --exe CAMI --cpu 1,4,6 --escenaris fred,calent,edita --segons 60
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ARREL = Path(__file__).resolve().parent.parent.parent
AQUI = Path(__file__).resolve().parent
sys.path[:0] = [str(ARREL), str(AQUI)]

import analitza  # noqa: E402
import cami  # noqa: E402
import mesura  # noqa: E402


def engega(projecte: Path, port: int, fre: float | None = None) -> tuple[subprocess.Popen, str, float]:
    t0 = time.time()
    ordre = [sys.executable, str(ARREL / "tallat.py"), "revisa", "--projecte", str(projecte), "--port", str(port), "--sense-navegador"]
    if fre:  # el servidor i els seus ffmpeg, frenats; el navegador no, perquè el so aturat a batzegades no s'assembla a res de debò
        ordre = [sys.executable, str(AQUI / "freno.py"), str(fre), "--", *ordre]
    s = subprocess.Popen(ordre, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    for linia in s.stdout:
        m = re.search(r"http://127\.0\.0\.1:\d+/", linia)
        if m:
            return s, m.group(0), time.time() - t0
    raise RuntimeError("La pàgina no s'ha engegat")


class Memoria(threading.Thread):
    """La memòria més alta del navegador, sumant tots els seus processos (Mac i Linux)."""
    daemon = True

    def __init__(self):
        super().__init__()
        self.para, self.pic = False, None

    def run(self):
        if sys.platform == "win32":
            return
        while not self.para:
            sortida = subprocess.run(["ps", "-A", "-o", "rss=,command="], capture_output=True, text=True, errors="replace").stdout
            # Només els navegadors de la prova, mai el Chrome o el Safari de la persona (a GitHub no n'hi ha cap més).
            noms = r"Chrome for Testing|ms-playwright|navegadors/|playwright_" + (r"|Google Chrome|Safari|com\.apple\.WebKit" if os.environ.get("GITHUB_ACTIONS") else "")
            kb = sum(int(l.split(None, 1)[0]) for l in sortida.splitlines() if re.search(noms, l))
            self.pic = max(self.pic or 0, kb // 1024)
            time.sleep(2)


def carrega() -> float | None:
    """Com d'ocupat està l'ordinador: una mesura de velocitat amb l'ordinador ple no val."""
    return round(os.getloadavg()[0], 1) if hasattr(os, "getloadavg") else None


def compta_registre(fitxer: Path) -> dict:
    """Què diu el propi reproductor que ha fet (el registre que desa la pàgina)."""
    comptes: dict[str, int] = {}
    if fitxer.exists():
        for linia in fitxer.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(r'"tipus":\s*"([^"]+)"', linia)
            if m:
                comptes[m.group(1)] = comptes.get(m.group(1), 0) + 1
    return {k: comptes[k] for k in ("play-rebutjat", "espera-continu", "espera-massa", "previa-error", "congelat", "salt-encallat", "salt-continu-encallat", "no-sincronitza", "sincronitzat", "continu", "salta", "error-js", "promesa-rebutjada") if k in comptes}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("resultats", type=Path)
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--motor", default="chrome")
    ap.add_argument("--exe")
    ap.add_argument("--canal")
    ap.add_argument("--cpu", default="1")
    ap.add_argument("--escenaris", default="calent")
    ap.add_argument("--segons", type=int, default=60)
    ap.add_argument("--port", type=int, default=8901)
    ap.add_argument("--repeticions", type=int, default=1)
    ap.add_argument("--sense-captura", action="store_true")
    ap.add_argument("--capta-tard", action="store_true", help="Només Safari: connecta la captura quan el vídeo ja té alguna cosa carregada")
    ap.add_argument("--torna-a-clicar", action="store_true", help="Només Safari: si no arrenca sol, es torna a prémer el play")
    ap.add_argument("--etiqueta", default="")
    ap.add_argument("--amb-finestra", action="store_true")
    ap.add_argument("--fre-servidor", type=float)
    a = ap.parse_args()

    font = mesura.Font(a.video)
    projecte = a.video / "projecte-pagina"
    if not (projecte / "transcripcio.json").exists():
        cami.crea_projecte(font, projecte, 0.35, font.dades["llavor"])
    sortida = a.resultats.with_suffix("")
    tots = json.loads(a.resultats.read_text(encoding="utf-8")) if a.resultats.exists() else []
    for cpu in a.cpu.split(","):
        for escenari in a.escenaris.split(","):
            for rep in range(a.repeticions):
                nom = f"{a.video.name}-{a.motor}{a.etiqueta}-cpu{cpu}-{escenari}-{rep}"
                carpeta = sortida / nom
                if carpeta.exists():
                    shutil.rmtree(carpeta)
                if escenari == "fred":  # que la còpia contínua s'hagi de fer de nou
                    shutil.rmtree(projecte / "previa", ignore_errors=True)
                edicio_abans = (projecte / "edicio.json").read_bytes()
                registre = projecte / "registre-pagina.log"
                registre.unlink(missing_ok=True)
                servidor, url, arrenca = engega(projecte, a.port, a.fre_servidor)
                ordre = ["node", str(AQUI / "pagina.mjs"), url, str(carpeta), "--motor", a.motor, "--cpu", cpu, "--escenari", escenari, "--segons", str(a.segons)]
                if a.motor == "safari":
                    ordre = [sys.executable, str(AQUI / "safari.py"), url, str(carpeta), "--escenari", escenari, "--segons", str(a.segons)]
                if a.exe:
                    ordre += ["--exe", a.exe]
                if a.canal:
                    ordre += ["--canal", a.canal]
                if a.sense_captura:
                    ordre.append("--sense-captura")
                if a.capta_tard:
                    ordre.append("--capta-tard")
                if a.torna_a_clicar:
                    ordre.append("--torna-a-clicar")
                if a.amb_finestra:
                    ordre.append("--amb-finestra")
                mem = Memoria()
                mem.start()
                carrega_abans = carrega()
                try:
                    t = subprocess.run(ordre, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=a.segons + 700)
                except subprocess.TimeoutExpired as e:  # un navegador encallat no ha d'aturar els altres
                    t = subprocess.CompletedProcess(ordre, 1, "", f"Encallat: {e}")
                mem.para = True
                carregues = {"carrega_abans": carrega_abans, "carrega_despres": carrega()}
                servidor.terminate()
                try:
                    servidor.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    servidor.kill()
                if registre.exists() and carpeta.exists():
                    shutil.copy(registre, carpeta / "registre.log")
                (projecte / "edicio.json").write_bytes(edicio_abans)  # la paraula treta, enrere: cada prova parteix del mateix
                if t.returncode != 0 or not (carpeta / "dades.json").exists():
                    tots.append({"nom": nom, "error_driver": (t.stdout[-500:] + t.stderr[-800:])})
                else:
                    tots.append({"nom": nom, "servidor_arrenca_s": round(arrenca, 2), "memoria_navegador_mb": mem.pic, **carregues, **analitza.analitza(font, carpeta), "reproductor": compta_registre(registre)})
                    (carpeta / "so.f32").unlink(missing_ok=True)
                a.resultats.write_text(json.dumps(tots, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
                print(_linia(tots[-1]), flush=True)


def _linia(r: dict) -> str:
    if "error_driver" in r:
        return f"{r['nom']}: ERROR {r['error_driver'][-300:]}"
    claus = ("carrega_abans", "carrega_despres", "fcp_ms", "text_ms", "video_llest_ms", "continu_llest_ms", "del_clic_a_playing_ms", "del_clic_a_so_ms", "preparant_s", "carregant_s", "continu_sonant_des_de_ms", "waiting", "encallades_audibles",
             "encallades_ms_total", "encallada_max_ms", "paraules_tretes_buscades", "paraules_tretes_que_sonen", "paraules_que_tocava_i_no_sonen", "talls_passats", "fuita_max_ms", "treta_sona_despres", "muntatge_sentit_s", "error")
    return r["nom"] + ": " + " ".join(f"{k}={r.get(k)}" for k in claus if r.get(k) is not None)


if __name__ == "__main__":
    main()
