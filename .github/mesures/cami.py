"""El camí sencer amb un vídeo inventat, mesurant-ho tot: còpia lleugera, exports, trossos per a CapCut, XML de Premiere.

    python cami.py CARPETA_DEL_VIDEO RESULTATS.json [--qualitats esborrany,1080] [--amb-subtitols]

S'ha d'engegar amb HOME apuntant a una casa de proves i TALLAT_PREFERENCIES a una carpeta temporal.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

ARREL = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ARREL))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mesura  # noqa: E402
from motor import edicio, entorn, exporta  # noqa: E402
from motor.projecte import Projecte  # noqa: E402

entorn.prepara()
if "tallat" in str(exporta.PREFERENCIES) and str(Path.home()) in str(exporta.PREFERENCIES) and not os.environ.get("TALLAT_PREFERENCIES"):
    sys.exit("Falta TALLAT_PREFERENCIES: no toco la configuració de ningú.")


def crea_projecte(font: mesura.Font, carpeta: Path, proporcio: float, llavor: int) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    dades = {"versio": 1, "video": str(font.video.resolve()), "font": "prova inventada", **exporta.info_video(font.video),
             "paraules": font.paraules}
    (carpeta / "transcripcio.json").write_text(json.dumps(dades, ensure_ascii=False, indent=1), encoding="utf-8")
    p = Projecte(carpeta)
    atzar = random.Random(llavor)
    ids = [w["id"] for w in font.paraules]
    i = 3
    while i < len(ids) - 3:
        if atzar.random() < proporcio:
            for _ in range(atzar.choice((1, 1, 2, 3))):
                if i < len(ids) - 2:
                    p.estat["esborrades"][ids[i]] = "usuari"
                    i += 1
        i += atzar.randint(2, 6)
    p.desa()


def ordre(*args: str, temps: int = 7200) -> dict:
    """Una ordre de tallat: quant triga i quanta memòria fa servir el procés més gros."""
    inici = time.time()
    resum = {}
    if sys.platform != "win32":
        codi = ("import resource,subprocess,sys;r=subprocess.run(sys.argv[1:]).returncode;"
                "print('@mem',resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss);sys.exit(r)")
        cmd = [sys.executable, "-c", codi, sys.executable, str(ARREL / "tallat.py"), *args]
    else:
        cmd = [sys.executable, str(ARREL / "tallat.py"), *args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=temps)
    mem = re.search(r"@mem (\d+)", r.stdout)
    if mem:
        resum["memoria_mb"] = round(int(mem.group(1)) / (1024 * 1024 if sys.platform == "darwin" else 1024))
    resum.update(ordre=" ".join(args[:1] + args[2:] if len(args) > 2 else args), segons=round(time.time() - inici, 1), ok=r.returncode == 0)
    if r.returncode != 0:
        resum["error"] = (r.stdout[-800:] + r.stderr[-1500:]).strip()
    return resum


def obre_pagina(projecte: Path, port: int) -> dict:
    """La primera vegada que s'obre: fa la còpia lleugera i, quan és a punt, diu on és la pàgina."""
    inici = time.time()
    s = subprocess.Popen([sys.executable, str(ARREL / "tallat.py"), "revisa", "--projecte", str(projecte), "--port", str(port), "--sense-navegador"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    try:
        dites = []
        for linia in s.stdout:
            dites.append(linia)
            if re.search(r"http://127\.0\.0\.1:(\d+)/", linia):
                return {"segons_fins_que_es_pot_obrir": round(time.time() - inici, 1), "ok": True}
        return {"ok": False, "error": "".join(dites)[-1500:]}
    finally:
        s.terminate()
        try:
            s.wait(timeout=15)
        except subprocess.TimeoutExpired:
            s.kill()


def trams_del_fitxer(fitxer: Path) -> list:
    return json.loads(fitxer.with_suffix(".talls.json").read_text(encoding="utf-8"))


def mesura_premiere(xml: Path, font: mesura.Font, esperats: list) -> dict:
    """Els clips de l'XML: quins segons de l'original agafen, comparats amb els trossos que tocarien."""
    arrel = ET.parse(xml).getroot()
    pistes = {}
    errors = []
    for tipus in ("video", "audio"):
        for pista_i, pista in enumerate(arrel.iter("track")):
            pass
    for medi in arrel.iter("media"):
        for tipus in ("video", "audio"):
            node = medi.find(tipus)
            if node is None:
                continue
            for n, pista in enumerate(node.findall("track")):
                clips = []
                for c in pista.findall("clipitem"):
                    tb = int(c.findtext("rate/timebase"))
                    ntsc = (c.findtext("rate/ntsc") or "FALSE").upper() == "TRUE"
                    r = Fraction(tb * 1000, 1001) if ntsc else Fraction(tb)
                    clips.append({"in": int(c.findtext("in")), "out": int(c.findtext("out")), "start": int(c.findtext("start")), "end": int(c.findtext("end")),
                                  "rate": r, "ruta": c.findtext("file/pathurl")})
                if clips:
                    pistes[f"{tipus}{n}"] = clips
    camins = set()
    resum = {}
    for nom, clips in pistes.items():
        if len(clips) != len(esperats):
            resum[nom] = {"clips": len(clips), "esperats": len(esperats)}
            continue
        forats = 0
        for k, (c, t) in enumerate(zip(clips, esperats)):
            e_in = float(c["in"] / c["rate"]) - t[0]
            e_out = float(c["out"] / c["rate"]) - t[1]
            errors.extend([e_in * 1000, e_out * 1000])
            if k and c["start"] != clips[k - 1]["end"]:
                forats += 1
            if c["out"] - c["in"] != c["end"] - c["start"]:
                forats += 1
            if c["ruta"]:
                camins.add(c["ruta"])
        resum[nom] = {"clips": len(clips), "forats_o_durades_diferents": forats, "rate": float(clips[0]["rate"])}
    url = next(iter(camins), None)
    cami_ok = None
    for adreca in camins:
        cami = Path(urllib.parse.unquote(urllib.parse.urlparse(adreca).path))
        cami_ok = cami.exists()
    return {"pistes": resum, "error_max_ms": round(max(abs(x) for x in errors), 2) if errors else None,
            "error_mitja_ms": round(sum(abs(x) for x in errors) / len(errors), 2) if errors else None, "cami_existeix": cami_ok, "url": url}


def mesura_fcpxml(fitxer: Path, esperats: list) -> dict:
    text = fitxer.read_text(encoding="utf-8")
    arrel = ET.fromstring(text)

    def segons(v: str) -> float:
        if not v:
            return 0.0
        return float(Fraction(v.rstrip("s")))
    clips = []
    espina = next(arrel.iter("spine"), None)
    if espina is None:
        return {"error": "sense spine"}
    for c in list(espina):
        clips.append((segons(c.get("start", "0s")), segons(c.get("duration", "0s")), segons(c.get("offset", "0s"))))
    if len(clips) != len(esperats):
        return {"clips": len(clips), "esperats": len(esperats)}
    errors = []
    for (s, d, _), t in zip(clips, esperats):
        errors += [(s - t[0]) * 1000, (s + d - t[1]) * 1000]
    return {"clips": len(clips), "error_max_ms": round(max(abs(x) for x in errors), 2)}


def mesura_trossos(carpeta: Path, font: mesura.Font, esperats: list) -> dict:
    """Els clips per a CapCut, un per un: de quin punt de l'original venen la imatge i el so de cadascun."""
    clips = sorted(c for c in carpeta.iterdir() if re.fullmatch(r"\d+\.mp4", c.name))
    if len(clips) != len(esperats):
        return {"clips": len(clips), "esperats": len(esperats)}
    err_img, err_so, baixes, dif_durada, total_v, total_a, total_e = [], [], 0, [], 0.0, 0.0, 0.0
    so_cap = 0
    for c, t in zip(clips, esperats):
        im = mesura.imatges_de(c)
        vals = im["numeros"][im["numeros"] >= 0]
        if len(vals):
            err_img.append((font.temps[vals[0]] - t[0]) * 1000)
            err_img.append((font.temps[vals[-1]] + 1 / font.fps - t[1]) * 1000)
        inf = mesura.info(c)
        v = float(inf["video"]["duration"])
        a = float(inf.get("audio", {}).get("duration") or 0)
        total_v += v
        total_a += a
        total_e += t[1] - t[0]
        dif_durada.append((v - a) * 1000)
        if a == 0:
            so_cap += 1
            continue
        so_, comenca = mesura.so_de(c)
        so_ = mesura.banda(so_)
        a0, b0, sa, sb = t
        finestra = min(0.25, (sb - sa) - 0.024)
        if finestra < 0.05:
            continue
        e1, n1 = mesura.error_so(so_, font.ref, (sa - a0) + 0.012 - comenca, sa + 0.012, finestra)
        e2, n2 = mesura.error_so(so_, font.ref, (sb - a0) - 0.012 - finestra - comenca, sb - 0.012 - finestra, finestra)
        for e, n in ((e1, n1), (e2, n2)):
            if n >= 0.3:
                err_so.append(e)
            else:
                baixes += 1
    a_ms = lambda x: round(max(abs(v) for v in x), 2) if x else None  # noqa: E731
    return {"clips": len(clips), "imatge_error_max_ms": a_ms(err_img), "so_error_max_ms": a_ms(err_so), "so_sense_coincidencia": baixes, "clips_sense_so": so_cap,
            "imatge_menys_so_max_ms": a_ms(dif_durada), "suma_imatge_s": round(total_v, 3), "suma_so_s": round(total_a, 3), "suma_esperada_s": round(total_e, 3),
            "desviacio_acumulada_so_ms": round((total_a - total_e) * 1000, 1), "desviacio_acumulada_imatge_ms": round((total_v - total_e) * 1000, 1)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("resultats", type=Path)
    ap.add_argument("--qualitats", default="esborrany,1080")
    ap.add_argument("--amb-subtitols", action="store_true")
    ap.add_argument("--proporcio", type=float, default=0.35)
    ap.add_argument("--port", type=int, default=8891)
    ap.add_argument("--nom-projecte", default="projecte")
    a = ap.parse_args()

    font = mesura.Font(a.carpeta)
    projecte = a.carpeta / a.nom_projecte
    if not (projecte / "transcripcio.json").exists():
        crea_projecte(font, projecte, a.proporcio, font.dades["llavor"])
    res: dict = {"video": font.video.name, "durada": font.dades["durada"], "passos": []}
    p = Projecte(projecte)
    trams = p.trams()
    json_trams = edicio.trams_json(trams)
    res["talls"] = max(0, len(trams) - 1)
    res["durada_muntatge"] = round(sum(t[1] - t[0] for t in trams), 2)
    res["esborrades"] = len(p.estat["esborrades"])

    # La referència: el mateix instrument sobre l'original (hauria de ser 0, si no, és soroll de l'eina).
    if not font.dades["vfr"]:
        base = mesura.imatges_de(font.video, retalla=_mes_ample(font))
        res["referencia_original"] = {"sincronisme": mesura.sincronisme(font.video, font, [], base)}
        res["referencia_original"]["sincronisme"].pop("punts", None)

    res["pagina_primera_vegada"] = obre_pagina(projecte, a.port)
    res["pagina_segona_vegada"] = obre_pagina(projecte, a.port)
    p = Projecte(projecte)
    if p.proxy.exists():
        res["copia_lleugera"] = {"mb": round(p.proxy.stat().st_size / 1e6, 1)}
        # La còpia contínua, la que sona a la pàgina
        previa = p.previa(trams)
        t0 = time.time()
        exporta.fes_previa(p.proxy, trams, previa)
        res["copia_continua"] = {"segons": round(time.time() - t0, 1), **_lleuger(mesura.mesura_fitxer(previa, font, json_trams))}
        previa.unlink(missing_ok=True)

    res["exports"] = {}
    for q in a.qualitats.split(","):
        res["passos"].append(ordre("exporta", "--projecte", str(projecte), "--qualitat", q, "--sense-subtitols"))
        fitxers = sorted((projecte / "exports").glob(f"*_{q}_*.mp4"), key=lambda f: f.stat().st_mtime)
        if not fitxers:
            res["exports"][q] = {"error": "cap fitxer"}
            continue
        res["exports"][q] = mesura.mesura_fitxer(fitxers[-1], font, json_trams)
    if a.amb_subtitols:
        res["passos"].append(ordre("exporta", "--projecte", str(projecte), "--qualitat", "esborrany"))
        fitxers = sorted((projecte / "exports").glob("*_esborrany_*.mp4"), key=lambda f: f.stat().st_mtime)
        res["exports"]["esborrany-amb-subtitols"] = mesura.mesura_fitxer(fitxers[-1], font, json_trams)

    # Per a altres editors: l'XML de Premiere i els clips de CapCut
    res["passos"].append(ordre("editors", "--projecte", str(projecte)))
    carpetes = sorted((c for c in (projecte / "exports").iterdir() if c.is_dir() and "editors" in c.name), key=lambda c: c.stat().st_mtime)
    if carpetes:
        cap = edicio.cap_endins(trams, float(p.fps))
        res["premiere"] = mesura_premiere(next(carpetes[-1].glob("*.xml")), font, [[t[0], t[1]] for t in cap])
        res["fcpxml"] = mesura_fcpxml(next(carpetes[-1].glob("*.fcpxml")), [[t[0], t[1]] for t in cap])
    antes = set(c.name for c in (projecte / "exports").iterdir() if c.is_dir())
    res["passos"].append(ordre("editors", "--projecte", str(projecte), "--trossos"))
    noves = [c for c in (projecte / "exports").iterdir() if c.is_dir() and c.name not in antes]
    if noves:
        res["trossos_capcut"] = mesura_trossos(noves[0], font, json_trams)

    a.resultats.parent.mkdir(parents=True, exist_ok=True)
    a.resultats.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(_resum(res), ensure_ascii=False, indent=1, default=str))


def _mes_ample(font: mesura.Font) -> bool:
    w, h = (int(x) for x in font.dades["mida"].split("x"))
    return w * 16 > h * 9


def _lleuger(d: dict) -> dict:
    return json.loads(json.dumps(d, default=str))


def _resum(res: dict) -> dict:
    """El mateix sense el detall per tall."""
    def treu(x):
        if isinstance(x, dict):
            return {k: treu(v) for k, v in x.items() if k not in ("detall", "punts")}
        return x
    return treu(res)


if __name__ == "__main__":
    main()
