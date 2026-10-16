"""Subtítols animats paraula a paraula amb HyperFrames.

1. `grups()` agafa les paraules que es queden, en calcula el temps dins del muntatge
   i les agrupa en línies (d'una paraula sola a una frase, segons l'estil).
2. `composicio()` escriu una composició HyperFrames transparent (1080 × 1920).
3. `renderitza()` la dibuixa amb HyperFrames a un .mov amb transparència, que
   l'export superposa al vídeo. Es desa a la carpeta del projecte i es reaprofita
   mentre no canviïn ni els subtítols ni l'estil.
"""
from __future__ import annotations

import functools
import hashlib
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

VERSIO_HYPERFRAMES = "0.8.154"
VERSIO_GSAP = "3.14.2"
CODI_ANIMACIO = Path(__file__).resolve().parent.parent / "pagina" / "subtitols.js"
CODI_GRAFICS = CODI_ANIMACIO.with_name("grafics.js")  # els gràfics del pla (fa servir subtitols.js)
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


GENERIQUES = {"system-ui", "sans-serif", "serif", "monospace", "cursive", "fantasy"}
CONFIG = Path(__file__).resolve().parent.parent / "config"
EMOJIS_USUARI = Path.home() / ".tallat" / "emojis.json"

# Paraules que no poden ser «clau» (les que fan de pont: articles, preposicions, pronoms, verbs comuns…).
PARAULES_PONT = set("""
a al als amb ara així aquí aquest aquesta aquests aquestes aquell aquella aquells aquelles allò això
bé com con contra d de del dels des després doncs durant e el ella elles ells els em en encara entre
era eren es és et fa fan fer fins ha han hagi hauria havia he hem heu hi i ja jo l la les li llavors
lo m me mes més meu meva meus meves molt molta molts moltes n ne ni no nosaltres o on però per perquè
poc pot puc què qual quan que qui s sa se seu seva seus seves si sí sigui sóc sobre som són també tan
tant te tenen tenir tens tinc tot tota tots totes tu un una uns unes us va vam van vaig vosaltres vull
estar estic està estan ser sé sap saps dir dic diu cal pas gens res algú alguna algun alguns algunes
""".split())


def _pla(paraula: str) -> str:
    """La paraula en minúscules i sense signes (de «l'idea,» en queda «idea»)."""
    paraula = paraula.lower().replace("’", "'")
    paraula = paraula.rsplit("'", 1)[-1]
    return re.sub(r"[^\w·-]+", "", paraula).strip("-·")


@functools.lru_cache(maxsize=1)
def _emojis() -> tuple[dict, list]:
    """(paraula → emoji, [(prefix, emoji)]) de config/emojis.json i ~/.tallat/emojis.json."""
    exactes, prefixos = {}, []
    for path in (CONFIG / "emojis.json", EMOJIS_USUARI):
        try:
            dades = json.loads(path.read_text(encoding="utf-8")).get("emojis", {})
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        for emoji, paraules in dades.items():
            for p in paraules if isinstance(paraules, list) else []:
                p = str(p).lower()
                if p.endswith("*"):
                    prefixos.append((p[:-1], emoji))
                else:
                    exactes[p] = emoji
    return exactes, prefixos


def emoji_de(paraula: str) -> str | None:
    pla = _pla(paraula)
    if not pla:
        return None
    exactes, prefixos = _emojis()
    if pla in exactes:
        return exactes[pla]
    return next((e for prefix, e in prefixos if len(prefix) >= 3 and pla.startswith(prefix)), None)


def _marca_claus(linia: list[dict]) -> None:
    """Paraules clau d'una línia: els números i la paraula llarga més important (en sol quedar una).

    Les que s'han triat a mà (o les ha triat Claude) manen: «destacada» true sempre ho és, false mai.
    Si la línia ja en té alguna de triada a mà, no se n'hi afegeix cap més."""
    triades = any(m.get("destacada") is True for m in linia)
    candidates = [(len(_pla(m["text"])), k) for k, m in enumerate(linia)
                  if m.get("destacada") is None and _pla(m["text"]) not in PARAULES_PONT and len(_pla(m["text"])) >= 4]
    millor = max(candidates)[1] if candidates and not triades else None
    emoji_posat = False
    for k, m in enumerate(linia):
        if m.get("destacada") is not None:
            m["clau"] = m["destacada"]
        else:
            m["clau"] = k == millor or (not triades and bool(re.search(r"\d", m["text"])))
        m["emoji"] = None
        if not emoji_posat:  # com a molt un emoji per línia, perquè no n'hi hagi massa
            m["emoji"] = emoji_de(m["text"])
            emoji_posat = m["emoji"] is not None


def _familia(nom: str) -> str:
    """El nom de la font tal com l'espera el CSS: «system-ui» tal qual, «Avenir Next» entre cometes."""
    nom = re.sub(r"[\"'\\;{}<>]", "", nom).strip() or "system-ui"
    return nom if nom in GENERIQUES else f'"{nom}"'


def grups(paraules: list[dict], trams: list[tuple[float, float]], estil: dict) -> list[dict]:
    """Línies de subtítols en temps del muntatge: [{inici, final, paraules: [{text, inici, final}]}]."""
    acum, t = [], 0.0
    for a, b in trams:
        acum.append(t)
        t += b - a

    def al_muntatge(inici: float, final: float):
        """On cau la paraula al muntatge. Va al tros amb què se solapa més: els talls s'arrodoneixen a
        fotogrames i una paraula pot començar uns mil·lisegons abans que el seu tros."""
        millor, solapament = None, 0.0
        for k, (a, b) in enumerate(trams):
            s = min(final, b) - max(inici, a)
            if s > solapament or (millor is None and a - 0.01 <= inici < b):
                millor, solapament = k, max(s, 0.0)
        if millor is None:
            return None
        a, b = trams[millor]
        principi = acum[millor] + max(0.0, inici - a)
        return principi, max(principi, acum[millor] + min(final, b) - a)

    mots = []
    for p in paraules:
        if not p["conservada"]:
            continue
        temps = al_muntatge(p["inici"], p["final"])
        text = _neteja_text(p.get("correccio", p["text"]), estil.get("puntuacio", False))
        if temps and text:
            mots.append({"id": p["id"], "text": text, "inici": round(temps[0], 3), "final": round(max(temps), 3),
                         "fi_frase": bool(FI_DE_FRASE.search(p["text"])), "destacada": p.get("destacada")})

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
    for linia in linies:
        _marca_claus(linia)
    if estil.get("clau_grans") and estil.get("clau_sola"):
        linies = [tros for linia in linies for tros in _separa_claus(linia)]

    # Apilades: les línies d'una frase s'acumulen (un «bloc») fins que la frase acaba, hi ha una pausa
    # o ja no n'hi caben més; totes les del bloc es queden a la pantalla fins al final del bloc.
    apilat = estil.get("disposicio") in ("apilat", "escampat")  # escampades: també per frases
    maxim_b = max(1, int(estil.get("linies_max", 4)))
    blocs = []
    for linia in linies:
        if (apilat and blocs and len(blocs[-1]) < maxim_b and not blocs[-1][-1][-1]["fi_frase"]
                and linia[0]["inici"] - blocs[-1][-1][-1]["final"] <= PAUSA_LINIA):
            blocs[-1].append(linia)
        else:
            blocs.append([linia])

    final_video = acum[-1] + (trams[-1][1] - trams[-1][0]) if trams else None
    resultat = []
    for b, bloc in enumerate(blocs):
        darrera = bloc[-1]
        final = darrera[-1]["final"] + RETEN
        if b + 1 < len(blocs):
            seguent = blocs[b + 1][0][0]["inici"]
            final = seguent if seguent - darrera[-1]["final"] < ENGANXA else min(final, seguent)
        if final_video is not None:
            final = min(final, final_video)
        for i, linia in enumerate(bloc):
            # Sense apilar, cada línia s'acaba quan comença la següent (com sempre).
            fi = final if apilat or i + 1 == len(bloc) else bloc[i + 1][0]["inici"]
            resultat.append({"inici": linia[0]["inici"], "final": round(fi, 3), "bloc": b,
                             "paraules": [{k: m[k] for k in ("id", "text", "inici", "final", "clau", "emoji")}
                                          for m in linia]})
    return resultat


def _separa_claus(linia: list[dict]) -> list[list[dict]]:
    """Cada paraula destacada, sola a la seva línia: «is as ambitious or» → «is as» | «ambitious» | «or»."""
    trossos, actual = [], []
    for m in linia:
        if m["clau"]:
            if actual:
                trossos.append(actual)
            trossos.append([m])
            actual = []
        else:
            actual.append(m)
    if actual:
        trossos.append(actual)
    for tros in trossos[:-1]:  # el final de frase només és a l'últim tros
        tros[-1] = dict(tros[-1], fi_frase=False)
    return trossos


def familia_css(estil: dict) -> str:
    """La família de lletra dels subtítols, a punt per al CSS (les del kit es declaren amb @font-face)."""
    familia = _familia(estil.get("font") or "system-ui")
    return f"{familia}, sans-serif" if familia == "system-ui" else f"{familia}, system-ui, sans-serif"


def _font_face(fonts: list[dict]) -> str:
    """Les @font-face de les lletres del kit: [{familia, pes, src}] (src, el fitxer dins la composició)."""
    regles = []
    for f in fonts:
        pes = str(f["pes"]) if re.fullmatch(r"\d+( \d+)?", str(f["pes"])) else "100 1000"
        estil = "italic" if f.get("estil") == "italic" else "normal"
        regles.append(f"@font-face {{ font-family: {_familia(f['familia'])}; src: url('{html.escape(f['src'])}'); "
                      f"font-weight: {pes}; font-style: {estil}; font-display: block; }}")
    return "\n      ".join(regles)


def _js(dades) -> str:
    """JSON que es pot posar dins d'un <script> sense trencar-lo."""
    return json.dumps(dades, ensure_ascii=False).replace("</", "<\\/")


def composicio(linies: list[dict], estil: dict, durada: float, fonts: list[dict] | None = None,
               stickers: list[dict] | None = None, estil_stickers: dict | None = None,
               escala: float = 1.0, titol: dict | None = None, estil_titol: dict | None = None,
               grafics: list[dict] | None = None, paleta: dict | None = None) -> str:
    """HTML d'una composició HyperFrames transparent amb els subtítols, el títol, els gràfics i els stickers.

    Els subtítols i el títol els dibuixa `subtitols.js`, i els gràfics, `grafics.js`: el mateix codi que
    fa servir la vista prèvia de la pàgina de revisió (s'han de copiar al costat d'aquest index.html).
    `stickers`: [{"src": nom del fitxer dins la composició, "inici": s, "durada": s}]."""
    es = estil_stickers or {}
    et = estil_titol or {}
    amplada, alcada = round(AMPLADA * escala), round(ALCADA * escala)
    # Mentre hi ha el títol (si l'estil ho diu) o una frase clau, els subtítols no es veuen.
    amaga = ([[titol["inici"], titol["final"]]] if titol and et.get("amaga_subtitols") else []) + \
        [[g["inici"], g["final"]] for g in grafics or [] if g.get("amaga_subtitols")]
    grafics_js = (f'TallatGrafics.construeix(document.getElementById("grafics"), {_js(grafics)}, {_js(paleta or {})}, '
                  f'{{ tl }});' if grafics else "")
    titol_js = (f'TallatSubtitols.titol(document.getElementById("titol"), {_js(titol)}, {_js(et)}, '
                f'{{ tl, familia: {_js(familia_css({"font": et.get("font") or estil.get("font")}))} }});'
                if titol else "")
    if titol and linies and not et.get("amaga_subtitols"):  # els subtítols que toquen el títol s'aparten
        titol_js += (f'\n      TallatSubtitols.aparta(document.getElementById("subtitols"), '
                     f'document.getElementById("titol"), {_js(titol)}, tl);')
    font_face = _font_face(fonts or [])

    blocs, passos = [], []
    for k, st in enumerate(stickers or []):
        # Si n'hi ha més d'un, s'alternen a banda i banda perquè no quedin sempre al mateix lloc.
        x = es.get("x", 0.72) if k % 2 == 0 else 1 - es.get("x", 0.72)
        rot = es.get("rotacio", 8) * (1 if k % 2 == 0 else -1)
        blocs.append(f'      <div id="s{k}" class="clip enganxina" data-start="{st["inici"]:.3f}" '
                     f'data-duration="{st["durada"]:.3f}" data-track-index="2">'
                     f'<img id="si{k}" class="sticker" src="{html.escape(st["src"])}" alt="" '
                     f'style="left: {x * 100:.2f}%; top: {es.get("y", 0.3) * 100:.2f}%; '
                     f'width: {es.get("mida", 0.34) * 100:.2f}%;" /></div>')
        sel = f'"#si{k}"'
        if es.get("animacio", "pop") == "pop":
            passos.append(f"      tl.fromTo({sel}, {{ xPercent: -50, yPercent: -50, scale: 0, rotation: {rot - 18}, opacity: 0 }}, "
                          f"{{ xPercent: -50, yPercent: -50, scale: 1, rotation: {rot}, opacity: 1, duration: 0.38, "
                          f"ease: \"back.out(2.4)\" }}, {st['inici']:.3f});")
            passos.append(f"      tl.to({sel}, {{ scale: 0.7, opacity: 0, duration: 0.18, ease: \"power2.in\" }}, "
                          f"{max(st['inici'], st['inici'] + st['durada'] - 0.18):.3f});")
        else:
            passos.append(f"      tl.fromTo({sel}, {{ xPercent: -50, yPercent: -50, rotation: {rot}, opacity: 0 }}, "
                          f"{{ xPercent: -50, yPercent: -50, rotation: {rot}, opacity: 1, duration: 0.01 }}, {st['inici']:.3f});")
    ombra_sticker = (f"filter: drop-shadow(0 {18 * escala:.0f}px {28 * escala:.0f}px rgba(0, 0, 0, 0.35));"
                     if es.get("ombra", True) else "")

    return f"""<!doctype html>
<html lang="ca">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={amplada}, height={alcada}" />
    <title>Subtítols · tallat</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@{VERSIO_GSAP}/dist/gsap.min.js"></script>
    <script src="subtitols.js"></script>
    <script src="grafics.js"></script>
    <style>
      {font_face}
      html, body {{ margin: 0; background: transparent; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: transparent; }}
      #subtitols, #grafics, #titol {{ transform: scale({escala}); transform-origin: 0 0; }}
      .enganxina {{ position: absolute; inset: 0; }}
      .sticker {{ position: absolute; height: auto; {ombra_sticker} }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="subtitols" data-start="0"
         data-width="{amplada}" data-height="{alcada}" data-duration="{durada:.3f}">
      <div id="subtitols"></div>
      <div id="grafics"></div>
      <div id="titol"></div>
{chr(10).join(blocs)}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      TallatSubtitols.construeix(document.getElementById("subtitols"), {_js(linies)}, {_js(estil)},
                                 {{ tl, familia: {_js(familia_css(estil))}, amaga: {_js(amaga)} }});
      {grafics_js}
      {titol_js}
{chr(10).join(passos)}
      window.__timelines["subtitols"] = tl;
    </script>
  </body>
</html>
"""


def _empremta(fitxer) -> str | None:
    """Empremta del contingut d'un fitxer: si se substitueix per un altre amb el mateix nom, canvia."""
    path = Path(fitxer).expanduser()
    return hashlib.sha1(path.read_bytes()).hexdigest() if path.is_file() else None


def renderitza(linies: list[dict], estil: dict, durada: float, carpeta: Path, qualitat: str,
               avis=None, stickers: list[dict] | None = None, estil_stickers: dict | None = None,
               fonts: list[dict] | None = None, titol: dict | None = None, estil_titol: dict | None = None,
               grafics: list[dict] | None = None, paleta: dict | None = None, imatges: Path | None = None) -> Path:
    """Dibuixa subtítols i stickers amb HyperFrames en un .mov transparent (reaprofita el darrer si no ha canviat).

    `stickers`: [{"fitxer": Path, "inici": s, "durada": s}].
    `fonts`: les lletres del kit que fan servir els subtítols, [{familia, pes, fitxer}] (marca.fonts_de).
    `titol`: el títol del ganxo, {text, inici, final}, amb el seu estil (`estil_titol`).
    `grafics`: els gràfics del pla situats al muntatge (motor/grafics.py), amb els colors de `paleta`;
    les seves imatges (la web i el ventall) són a la carpeta `imatges`."""
    # L'esborrany es dibuixa a mitja mida (unes 3-4 vegades més ràpid); l'export final, a 1080 o en 4K.
    escala = {"4k": "4k", "esborrany": "540"}.get(qualitat, "1080")
    fonts = fonts or []
    empremta_st = [[str(st["fitxer"]), _empremta(st["fitxer"]), st["inici"], st["durada"]] for st in stickers or []]
    codi = [_empremta(CODI_ANIMACIO), _empremta(CODI_GRAFICS)]  # si canvien les animacions, cal tornar a dibuixar
    empremta_fonts = [[f["familia"], f["pes"], f.get("estil", "normal"), _empremta(f["fitxer"])] for f in fonts]
    clau = json.dumps([linies, estil, round(durada, 3), escala, VERSIO_HYPERFRAMES, empremta_st, estil_stickers, codi,
                       empremta_fonts, titol, estil_titol if titol else None, grafics or [],
                       paleta if grafics else None], sort_keys=True)
    nom = hashlib.sha1(clau.encode()).hexdigest()[:12]
    base = carpeta / "subtitols"
    sortida = base / f"subtitols_{escala}_{nom}.mov"
    if sortida.exists() and sortida.stat().st_size > 0:
        return sortida

    projecte = base / nom
    projecte.mkdir(parents=True, exist_ok=True)
    fonts_locals = []
    for k, f in enumerate(fonts):
        src = f"font{k}{Path(f['fitxer']).suffix.lower()}"
        shutil.copy(f["fitxer"], projecte / src)
        fonts_locals.append({"familia": f["familia"], "pes": f["pes"], "estil": f.get("estil", "normal"), "src": src})
    shutil.copy(CODI_ANIMACIO, projecte / "subtitols.js")
    shutil.copy(CODI_GRAFICS, projecte / "grafics.js")
    # Les imatges dels gràfics, a imatges/ (grafics.js les hi busca). El nom ja diu el contingut.
    noms = {g.get("imatge") for g in grafics or []} | {p.get("imatge") for g in grafics or [] for p in g.get("punts", [])}
    for nom_imatge in filter(None, noms) if imatges else ():
        (projecte / "imatges").mkdir(exist_ok=True)
        shutil.copy(Path(imatges) / nom_imatge, projecte / "imatges" / nom_imatge)
    locals_st = []
    for k, st in enumerate(stickers or []):
        nom = f"sticker{k}{Path(st['fitxer']).suffix.lower()}"
        shutil.copy(st["fitxer"], projecte / nom)
        locals_st.append({"src": nom, "inici": st["inici"], "durada": st["durada"]})
    (projecte / "index.html").write_text(composicio(linies, estil, durada, fonts_locals, locals_st, estil_stickers,
                                                    escala=0.5 if escala == "540" else 1.0,
                                                    titol=titol, estil_titol=estil_titol,
                                                    grafics=grafics, paleta=paleta), encoding="utf-8")

    temporal = sortida.with_suffix(".tmp.mov")
    ordre = ["npx", "--yes", f"hyperframes@{VERSIO_HYPERFRAMES}", "render", str(projecte),
             "--format", "mov", "--fps", str(FPS), "--output", str(temporal)]
    if escala == "4k":
        ordre += ["--resolution", "portrait-4k"]
    if avis:
        avis("Dibuixant subtítols, gràfics i stickers amb HyperFrames…")
    r = subprocess.run(ordre, capture_output=True, text=True)
    if r.returncode != 0 or not temporal.exists():
        raise RuntimeError("HyperFrames no ha pogut dibuixar els subtítols:\n" + (r.stderr or r.stdout)[-2000:])
    temporal.replace(sortida)
    for vell in base.glob(f"subtitols_{escala}_*.mov"):  # només en guardem un per mida
        if vell != sortida:
            vell.unlink(missing_ok=True)
    return sortida
