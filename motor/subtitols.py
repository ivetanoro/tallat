"""Subtítols animats paraula a paraula amb HyperFrames.

1. `grups()` agafa les paraules que es queden, en calcula el temps dins del muntatge
   i les agrupa en línies curtes (2-3 paraules).
2. `composicio()` escriu una composició HyperFrames transparent (1080 × 1920).
3. `renderitza()` la dibuixa amb HyperFrames a un .mov amb transparència, que
   l'export superposa al vídeo. Es desa a la carpeta del projecte i es reaprofita
   mentre no canviïn ni els subtítols ni l'estil.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

VERSIO_HYPERFRAMES = "0.8.154"
AMPLADA, ALCADA = 1080, 1920
FPS = 30
FI_DE_FRASE = re.compile(r"[.?!…»\"]$")
PAUSA_LINIA = 0.45      # un silenci més llarg que això obre una línia nova
ENGANXA = 0.6           # si la línia següent arriba abans d'això, l'actual s'hi queda fins llavors
RETEN = 0.25            # segons que una línia es queda en pantalla després de l'última paraula


def _neteja_text(text: str, puntuacio: bool) -> str:
    text = text.strip()
    if not puntuacio:
        text = re.sub(r"^[«\"'“]+|[»\"'”]+$", "", text)
        text = re.sub(r"[,.;:…-]+$", "", text)
    return text


def grups(paraules: list[dict], trams: list[tuple[float, float]], estil: dict) -> list[dict]:
    """Línies de subtítols en temps del muntatge: [{inici, final, paraules: [{text, inici, final}]}]."""
    acum, t = [], 0.0
    for a, b in trams:
        acum.append(t)
        t += b - a

    def al_muntatge(inici: float, final: float):
        for k, (a, b) in enumerate(trams):
            if a - 0.01 <= inici < b:
                return acum[k] + max(0.0, inici - a), acum[k] + min(final, b) - a
        return None

    mots = []
    for p in paraules:
        if not p["conservada"]:
            continue
        temps = al_muntatge(p["inici"], p["final"])
        text = _neteja_text(p.get("correccio", p["text"]), estil.get("puntuacio", False))
        if temps and text:
            mots.append({"text": text, "inici": round(temps[0], 3), "final": round(max(temps), 3),
                         "fi_frase": bool(FI_DE_FRASE.search(p["text"]))})

    mots.sort(key=lambda m: m["inici"])  # en un reel muntat, l'ordre és el del muntatge
    maxim_p = max(1, int(estil.get("paraules_per_linia", 3)))
    maxim_l = max(4, int(estil.get("lletres_per_linia", 18)))
    linies, actual = [], []
    for m in mots:
        if actual:
            lletres = sum(len(x["text"]) + 1 for x in actual) + len(m["text"])
            if (len(actual) >= maxim_p or lletres > maxim_l or actual[-1]["fi_frase"]
                    or m["inici"] - actual[-1]["final"] > PAUSA_LINIA):
                linies.append(actual)
                actual = []
        actual.append(m)
    if actual:
        linies.append(actual)

    resultat = []
    for i, linia in enumerate(linies):
        final = linia[-1]["final"] + RETEN
        if i + 1 < len(linies):
            seguent = linies[i + 1][0]["inici"]
            final = seguent if seguent - linia[-1]["final"] < ENGANXA else min(final, seguent)
        final = min(final, acum[-1] + (trams[-1][1] - trams[-1][0]) if trams else final)
        resultat.append({"inici": linia[0]["inici"], "final": round(final, 3),
                         "paraules": [{k: m[k] for k in ("text", "inici", "final")} for m in linia]})
    return resultat


def composicio(linies: list[dict], estil: dict, durada: float, font_local: str | None = None) -> str:
    """HTML d'una composició HyperFrames transparent amb els subtítols."""
    mida = estil["mida"] * AMPLADA
    familia = "'SubtitolsMarca', system-ui, sans-serif" if font_local else f"{estil['font']}, sans-serif"
    font_face = (f"@font-face {{ font-family: 'SubtitolsMarca'; src: url('{font_local}'); font-display: block; }}"
                 if font_local else "")
    ombra = "text-shadow: 0 0.06em 0.2em rgba(0, 0, 0, 0.45);" if estil.get("ombra") else ""
    contorn = estil.get("gruix_contorn", 0) or 0

    blocs = []
    for i, linia in enumerate(linies):
        paraules = " ".join(f'<span id="p{i}-{j}" class="p">{html.escape(w["text"])}</span>'
                            for j, w in enumerate(linia["paraules"]))
        blocs.append(f'      <div id="l{i}" class="clip linia" data-start="{linia["inici"]:.3f}" '
                     f'data-duration="{max(0.05, linia["final"] - linia["inici"]):.3f}" data-track-index="1">'
                     f'<p class="text">{paraules}</p></div>')

    passos = []
    pop = estil.get("animacio", "pop") == "pop"
    for i, linia in enumerate(linies):
        for j, w in enumerate(linia["paraules"]):
            sel = f'"#p{i}-{j}"'
            fi = linia["paraules"][j + 1]["inici"] if j + 1 < len(linia["paraules"]) else linia["final"]
            if pop:
                passos.append(f"  tl.fromTo({sel}, {{ opacity: 0, scale: 0.82, y: 10 }}, "
                              f"{{ opacity: 1, scale: 1, y: 0, duration: 0.14, ease: \"back.out(2.2)\" }}, {w['inici']:.3f});")
            else:
                passos.append(f"  tl.fromTo({sel}, {{ opacity: 0 }}, {{ opacity: 1, duration: 0.01 }}, {w['inici']:.3f});")
            passos.append(f"  tl.set({sel}, {{ color: ACTIU }}, {w['inici']:.3f});")
            passos.append(f"  tl.set({sel}, {{ color: BASE }}, {fi:.3f});")

    return f"""<!doctype html>
<html lang="ca">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={AMPLADA}, height={ALCADA}" />
    <title>Subtítols · tallat</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      {font_face}
      html, body {{ margin: 0; background: transparent; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: transparent; }}
      .linia {{ position: absolute; inset: 0; }}
      .text {{
        position: absolute; left: 50%; top: {estil['posicio_y'] * 100:.2f}%;
        width: {estil['amplada_maxima'] * 100:.2f}%; margin: 0 0 0 -{estil['amplada_maxima'] * 50:.2f}%;
        transform: translateY(-50%);
        text-align: center; line-height: 1.12;
        font-family: {familia}; font-weight: {int(estil['pes'])}; font-size: {mida:.1f}px;
        color: {estil['color']}; {"text-transform: uppercase;" if estil.get('majuscules') else ""}
        -webkit-text-stroke: {contorn * 2:.3f}em {estil['contorn']}; paint-order: stroke fill;
        {ombra}
      }}
      .p {{ display: inline-block; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="subtitols" data-start="0"
         data-width="{AMPLADA}" data-height="{ALCADA}" data-duration="{durada:.3f}">
{chr(10).join(blocs)}
    </div>
    <script>
      const BASE = {json.dumps(estil['color'])};
      const ACTIU = {json.dumps(estil['color_actiu'])};
      const tl = gsap.timeline({{ paused: true }});
{chr(10).join(passos)}
      window.__timelines["subtitols"] = tl;
    </script>
  </body>
</html>
"""


def renderitza(linies: list[dict], estil: dict, durada: float, carpeta: Path, qualitat: str,
               avis=None) -> Path:
    """Dibuixa els subtítols amb HyperFrames en un .mov transparent (reaprofita el darrer si no ha canviat)."""
    escala = "4k" if qualitat == "4k" else "1080"
    font = estil.get("font_fitxer")
    clau = json.dumps([linies, estil, round(durada, 3), escala, VERSIO_HYPERFRAMES], sort_keys=True)
    nom = hashlib.sha1(clau.encode()).hexdigest()[:12]
    base = carpeta / "subtitols"
    sortida = base / f"subtitols_{escala}_{nom}.mov"
    if sortida.exists() and sortida.stat().st_size > 0:
        return sortida

    projecte = base / nom
    projecte.mkdir(parents=True, exist_ok=True)
    font_local = None
    if font:
        origen = Path(font).expanduser()
        if not origen.exists():
            raise FileNotFoundError(f"No trobo la font dels subtítols: {origen}")
        font_local = "font" + origen.suffix.lower()
        shutil.copy(origen, projecte / font_local)
    (projecte / "index.html").write_text(composicio(linies, estil, durada, font_local), encoding="utf-8")

    temporal = sortida.with_suffix(".tmp.mov")
    ordre = ["npx", "--yes", f"hyperframes@{VERSIO_HYPERFRAMES}", "render", str(projecte),
             "--format", "mov", "--fps", str(FPS), "--output", str(temporal)]
    if escala == "4k":
        ordre += ["--resolution", "portrait-4k"]
    if avis:
        avis("Dibuixant els subtítols amb HyperFrames…")
    r = subprocess.run(ordre, capture_output=True, text=True)
    if r.returncode != 0 or not temporal.exists():
        raise RuntimeError("HyperFrames no ha pogut dibuixar els subtítols:\n" + (r.stderr or r.stdout)[-2000:])
    temporal.replace(sortida)
    for vell in base.glob(f"subtitols_{escala}_*.mov"):  # només en guardem un per mida
        if vell != sortida:
            vell.unlink(missing_ok=True)
    return sortida
