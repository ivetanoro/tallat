"""El format únic de l'estil (vegeu ESTIL.md).

Un estil és una carpeta amb `estil.json` (els paràmetres), `fonts/` (les lletres) i, si en té,
`receptes/`, `so/` i `NOTES.md`. El fan personalitza i matcha, i el fa servir tallat. Totes tres el
llegeixen i l'escriuen igual, i es passa d'una a l'altra en un `.estil.zip`.

Aquest mòdul no sap on viu res: qui el crida li passa les carpetes. Res d'aquí escriu a disc tret
de `importa`, i només dins de la carpeta que li diuen.
"""
from __future__ import annotations

import copy
import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path

FORMAT = "estil/1"          # el que diu `format` a estil.json
FITXER = "estil.json"       # dins del zip (tallat, a disc, encara en diu kit.json)
FITXERS_VELLS = ("kit.json",)
NEUTRE = Path(__file__).resolve().parent / "estil_neutre.json"
MIDA_MAXIMA = 60 * 1024 * 1024
FORMATS_FONT = {".ttf", ".otf", ".woff", ".woff2"}
# Carpetes opcionals que viatgen amb l'estil, i quins fitxers s'hi accepten.
CARPETES = {
    "fonts": FORMATS_FONT | {".json"},
    "receptes": {".html", ".json", ".css", ".js"},
    "so": {".json", ".wav", ".mp3", ".m4a", ".ogg"},
    "imatges": {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"},
}
NOTES = "NOTES.md"

# --- L'esquema: què es pot canviar i entre quins límits -------------------------------------
SECCIONS = {"subtitols", "titol", "broll", "stickers", "talls", "so", "marca"}
RANGS = {
    "subtitols": {"mida": (0.03, 0.16), "pes": (100, 900), "gruix_contorn": (0.0, 0.2), "posicio_y": (0.05, 0.95),
                  "amplada_maxima": (0.4, 0.98), "paraules_per_linia": (1, 12), "lletres_per_linia": (4, 60),
                  "espaiat": (-0.12, 0.3), "interlineat": (0.75, 1.6), "linies_max": (2, 8), "clau_mida": (1.0, 3.5)},
    "titol": {"mida": (0.03, 0.2), "pes": (100, 900), "clau_mida": (1.0, 4.0), "espaiat": (-0.12, 0.3),
              "interlineat": (0.75, 1.6), "gruix_contorn": (0.0, 0.2), "posicio_y": (0.05, 0.95),
              "amplada_maxima": (0.4, 0.98), "durada": (0.5, 10.0), "corba": (-1.0, 1.0)},
    "broll": {"durada": (0.5, 4.0), "mida": (0.25, 1.0), "posicio_x": (0.0, 1.0), "posicio_y": (0.0, 1.0),
              "radi": (0.0, 0.5), "vora": (0.0, 0.04), "rotacio": (-15, 15)},
    "stickers": {"durada": (0.5, 6.0), "mida": (0.08, 0.8), "x": (0.0, 1.0), "y": (0.0, 1.0), "rotacio": (-30, 30)},
    "talls": {"pausa_maxima": (0.1, 2.0)},
    "so": {"volum_efectes": (0.0, 1.0)},
}
OPCIONS = {
    "subtitols": {"animacio": {"pop", "fos", "cap", "impacte", "cortina", "pes"}, "apareixen": {"paraula", "linia"},
                  "destacat": {"color", "caixa", "karaoke", "gran"}, "aspecte": {"normal", "neo", "degradat"},
                  "fons": {"cap", "pindola"}, "disposicio": {"linia", "apilat", "escampat"},
                  "alineacio": {"centre", "esquerra", "dreta", "esglao"}},
    "stickers": {"animacio": {"pop", "cap"}},
    "so": {"soroll": {"suau", "mitja", "fort"}, "efectes": {"cap", "pocs", "molts"}},
    "marca": {"grafics": {"pocs", "normal", "molts"}},
    "broll": {"disposicio": {"pantalla", "targeta", "partida", "carrusel"},
              "proporcio": {"9:16", "3:4", "4:5", "1:1", "16:9"},
              "animacio": {"pop", "puja", "llisca", "fos", "cap"}},
    "titol": {"alineacio": {"centre", "esquerra", "dreta", "esglao"},
              "animacio": {"puja", "pop", "fos", "cortina", "maquina", "cap"}, "fons": {"cap", "enfosquit", "pindola"},
              "corba_linies": {"primera", "totes", "darrera"}},
}
COLORS = {"color", "color_actiu", "contorn", "fons_color", "clau_color", "vora_color",
          "color_text", "color_principal", "color_destacat", "color_secundari", "color_clar", "color_fosc"}
LLISTES = {"marca": {"energia": {"net", "mac", "scrapbook", "editorial"}}}
MIDA_TEXT = 600
# La marca s'escampa: cada color i cada lletra fa la seva feina a la resta de l'estil.
ENLLACOS_MARCA = {
    "color_text": [("subtitols", "color"), ("titol", "color")],
    "color_fosc": [("subtitols", "contorn"), ("titol", "contorn")],
    "color_destacat": [("subtitols", "color_actiu"), ("subtitols", "clau_color"), ("titol", "clau_color")],
    "color_principal": [("broll", "vora_color")],
    "lletra_text": [("subtitols", "font")],
    "lletra_titols": [("titol", "font")],
    "lletra_accent": [("subtitols", "clau_font"), ("titol", "clau_font")],
}
NOM_DE_FONT = re.compile(r"^[\w][\w .-]{0,60}$")
COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
EINES = {"tallat", "personalitza", "matcha"}  # qui pot tenir una secció pròpia a `ext`


# --- L'estil neutre ------------------------------------------------------------------------------
_neutre: dict = {}


def sense_notes(d: dict) -> dict:
    """Treu les claus que comencen per «_» (són explicacions per a les persones)."""
    return {k: (sense_notes(v) if isinstance(v, dict) else v) for k, v in d.items() if not k.startswith("_")}


def neutre(amb_notes: bool = False) -> dict:
    """L'estil neutre (una còpia: qui el fa servir el pot canviar). Es llegeix un sol cop mentre el fitxer no canvia."""
    if amb_notes:
        return json.loads(NEUTRE.read_text(encoding="utf-8"))
    temps = NEUTRE.stat().st_mtime_ns
    if _neutre.get("temps") != temps:
        _neutre.update(temps=temps, dades=sense_notes(json.loads(NEUTRE.read_text(encoding="utf-8"))))
    return copy.deepcopy(_neutre["dades"])


# --- Validar -------------------------------------------------------------------------------------
def valida(seccio: str, canvis: dict) -> dict:
    """Comprova uns valors d'una secció; llança ValueError amb un missatge clar si n'hi ha cap de dolent.
    Els números es porten dins del seu rang en lloc de fallar."""
    if seccio not in SECCIONS:
        raise ValueError(f"No es pot canviar la secció «{seccio}»")
    base = neutre()[seccio]
    net = {}
    for clau, valor in canvis.items():
        if clau not in base:
            raise ValueError(f"Opció desconeguda: {clau}")
        defecte = base[clau]
        rangs, opcions = RANGS.get(seccio, {}), OPCIONS.get(seccio, {})
        if defecte is None and clau in COLORS:  # un color que també pot ser «el de sempre» (null)
            if valor is not None and not (isinstance(valor, str) and COLOR.fullmatch(valor)):
                raise ValueError(f"{clau} ha de ser un color com #FFD60A")
        elif defecte is None and (clau in ("font", "clau_font") or clau.startswith("lletra_")):
            if valor is not None and not (isinstance(valor, str) and NOM_DE_FONT.match(valor)):
                raise ValueError("Aquest nom de font no és vàlid")
        elif defecte is None:  # camins de fitxers (font pròpia, LUT): no es posen per aquí
            if valor is not None:
                raise ValueError(f"{clau} no es pot canviar així")
        elif isinstance(defecte, list):
            permesos = LLISTES.get(seccio, {}).get(clau, set())
            if not isinstance(valor, list) or not valor or any(v not in permesos for v in valor):
                raise ValueError(f"{clau} ha de ser una llista amb alguna d'aquestes: {', '.join(sorted(permesos))}")
            valor = list(dict.fromkeys(valor))
        elif isinstance(defecte, bool):
            if not isinstance(valor, bool):
                raise ValueError(f"{clau} ha de ser sí o no")
        elif isinstance(defecte, (int, float)):
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                raise ValueError(f"{clau} ha de ser un número")
            if clau in rangs:
                a, b = rangs[clau]
                valor = min(b, max(a, valor))
            valor = int(round(valor)) if isinstance(defecte, int) else round(float(valor), 4)
        elif isinstance(defecte, str):
            if not isinstance(valor, str):
                raise ValueError(f"{clau} ha de ser un text")
            if clau in COLORS and not COLOR.fullmatch(valor):
                raise ValueError(f"{clau} ha de ser un color com #FFD60A")
            if clau in opcions and valor not in opcions[clau]:
                raise ValueError(f"{clau} no pot ser «{valor}»")
            if clau == "font" and not NOM_DE_FONT.match(valor):
                raise ValueError("Aquest nom de font no és vàlid")
            valor = valor.strip()[:MIDA_TEXT] if not opcions.get(clau) and clau not in COLORS else valor
        net[clau] = valor
    return net


def neteja(dades: dict) -> dict:
    """Un estil d'on sigui (un zip, una altra eina) deixat només amb el que s'entén i és segur: les opcions
    vàlides de cada secció, el nom, el quadre i `ext`. Fora camins de fitxers (font pròpia fora de fonts/, LUT)."""
    net: dict = {"format": FORMAT}
    if isinstance(dades.get("nom"), str) and dades["nom"].strip():
        net["nom"] = " ".join(dades["nom"].split())[:60]
    quadre = dades.get("quadre")
    if isinstance(quadre, dict) and all(isinstance(quadre.get(k), (int, float)) for k in ("w", "h")):
        net["quadre"] = {k: quadre[k] for k in ("w", "h", "fps") if isinstance(quadre.get(k), (int, float))}
    for seccio in sorted(SECCIONS):
        valors = dades.get(seccio)
        if not isinstance(valors, dict):
            continue
        net[seccio] = {}
        for clau, valor in valors.items():
            if clau.startswith("_") or clau in ("font_fitxer", "lut"):
                continue
            try:
                net[seccio].update(valida(seccio, {clau: valor}))
            except ValueError:
                continue  # el que no s'entén es deixa: es farà servir el valor neutre
    font = dades.get("subtitols", {}).get("font_fitxer") if isinstance(dades.get("subtitols"), dict) else None
    if isinstance(font, str) and re.fullmatch(r"fonts/[^/\\:]+", font):
        net.setdefault("subtitols", {})["font_fitxer"] = font
    ext = dades.get("ext")
    if isinstance(ext, dict):
        net["ext"] = {eina: sense_camins(v) for eina, v in ext.items() if eina in EINES and isinstance(v, dict)}
    return net


def sense_camins(valor):
    """Treu els textos que semblen camins absoluts d'aquest ordinador (no han de viatjar amb l'estil)."""
    if isinstance(valor, dict):
        return {k: sense_camins(v) for k, v in valor.items() if not _es_cami(v)}
    if isinstance(valor, list):
        return [sense_camins(v) for v in valor if not _es_cami(v)]
    return valor


def _es_cami(v) -> bool:
    return isinstance(v, str) and bool(re.match(r"^(/|~|[A-Za-z]:[\\/])", v))


# --- Combinar --------------------------------------------------------------------------------------
def combina(dades: dict) -> dict:
    """L'estil sencer: el neutre amb els valors de `dades` al damunt (secció a secció). `nom`, `format` i
    `ext` no formen part de l'estil que es dibuixa i no hi van."""
    base = neutre()
    for seccio, valors in sense_notes(dades).items():
        if seccio in ("nom", "format", "ext"):
            continue
        if isinstance(valors, dict) and isinstance(base.get(seccio), dict):
            base[seccio].update(valors)
        else:
            base[seccio] = valors
    return base


def amb_la_marca(estil: dict) -> dict:
    """Els colors i les lletres de la marca, a sobre de les seccions: manen sempre. Sense color destacat, les
    destacades van del color del text."""
    m = estil.get("marca") or {}
    for clau, destins in ENLLACOS_MARCA.items():
        valor = m.get(clau)
        if clau == "color_destacat" and valor is None:
            valor = m.get("color_text")
        if valor is None:
            continue
        for seccio, desti in destins:
            estil.setdefault(seccio, {})[desti] = valor
            if (seccio, desti) == ("subtitols", "font"):
                estil["subtitols"]["font_fitxer"] = None
        if clau == "lletra_accent":  # la paraula emotiva, en cursiva
            for seccio in ("subtitols", "titol"):
                estil.setdefault(seccio, {})["clau_cursiva"] = True
    return estil


def claus_de_la_marca(m: dict) -> dict:
    """{seccio: claus} que hi posa la marca `m` (les que té): a sobre d'aquestes, l'estil no hi mana."""
    claus: dict = {}
    for clau, destins in ENLLACOS_MARCA.items():
        valor = m.get(clau) if not (clau == "color_destacat" and m.get(clau) is None) else m.get("color_text")
        if valor is None:
            continue
        for seccio, desti in destins:
            claus.setdefault(seccio, set()).add(desti)
            if (seccio, desti) == ("subtitols", "font"):
                claus[seccio].add("font_fitxer")
        if clau == "lletra_accent":
            for seccio in ("subtitols", "titol"):
                claus.setdefault(seccio, set()).add("clau_cursiva")
    return claus


def escampa_marca(dades: dict, canvis: dict) -> None:
    """Posa els colors i les lletres de la marca allà on fan la seva feina, dins de `dades` (si se'n treu un,
    hi torna el neutre). Després cada opció es pot retocar a part."""
    base = neutre()
    marca_ = dades.get("marca", {})
    claus = set(canvis)
    if "color_text" in claus and not marca_.get("color_destacat"):
        claus.add("color_destacat")
    for clau in claus:
        valor = marca_.get(clau)
        if clau == "color_destacat" and valor is None:
            valor = marca_.get("color_text")
        for seccio, desti in ENLLACOS_MARCA.get(clau, []):
            dades.setdefault(seccio, {})[desti] = valor if valor is not None else base[seccio][desti]
            if (seccio, desti) == ("subtitols", "font"):
                dades["subtitols"]["font_fitxer"] = None
        if clau == "lletra_accent":
            for seccio in ("subtitols", "titol"):
                dades.setdefault(seccio, {})["clau_cursiva"] = valor is not None


# --- Formats vells ---------------------------------------------------------------------------------
def que_es(dades: dict) -> str:
    """«estil» (el format comú), «tallat» (un kit sense `format`), «matcha» (un estil.json de matcha) o «res»."""
    if not isinstance(dades, dict):
        return "res"
    if dades.get("format") == FORMAT:
        return "estil"
    if "plans" in dades or "lletres" in dades or "fons_quadre" in dades or "referencies" in dades:
        return "matcha"
    if any(isinstance(dades.get(s), dict) for s in SECCIONS):
        return "tallat"
    return "res"


def migra(dades: dict) -> dict:
    """Qualsevol estil conegut, passat al format comú (sense netejar: això ho fa `neteja`)."""
    tipus = que_es(dades)
    if tipus == "estil":
        return copy.deepcopy(dades)
    if tipus == "tallat":
        return {"format": FORMAT, **{k: copy.deepcopy(v) for k, v in dades.items() if k != "_info"}}
    if tipus == "matcha":
        return de_matcha(dades)
    raise ValueError("Això no és cap estil que conegui (ni de tallat, ni de personalitza, ni de matcha).")


def de_matcha(e: dict) -> dict:
    """Un estil.json de matcha, al format comú. El que és només de matcha va a `ext.matcha`; el que diu com és
    el vídeo (colors i lletres) va també a `marca`, perquè tallat el pugui fer servir."""
    out: dict = {"format": FORMAT, "nom": e.get("nom") or e.get("id") or "Estil de matcha"}
    if isinstance(e.get("quadre"), dict):
        out["quadre"] = e["quadre"]
    marca_: dict = {}
    lletres = [l for l in e.get("lletres") or [] if isinstance(l, dict) and l.get("familia")]
    if lletres:  # la primera fa de lletra dels títols i del text; si n'hi ha una altra, d'accent
        marca_["lletra_titols"] = marca_["lletra_text"] = lletres[0]["familia"]
        altres = [l["familia"] for l in lletres if l["familia"] != lletres[0]["familia"]]
        if altres:
            marca_["lletra_accent"] = altres[0]
    if isinstance(e.get("fons_quadre"), str) and COLOR.fullmatch(e["fons_quadre"]):
        marca_["color_fosc"] = e["fons_quadre"]
    colors = e.get("colors") if isinstance(e.get("colors"), dict) else {}
    for clau in ("color_text", "color_principal", "color_destacat", "color_secundari", "color_clar", "color_fosc"):
        if isinstance(colors.get(clau), str) and COLOR.fullmatch(colors[clau]):
            marca_[clau] = colors[clau]
    if marca_:
        out["marca"] = marca_
    propi = {k: v for k, v in e.items() if k not in ("nom", "quadre", "projecte_mostra", "referencies", "creat")}
    out["ext"] = {"matcha": propi}
    return out


# --- Noms i zip ------------------------------------------------------------------------------------
def slug(text: str) -> str:
    t = unicodedata.normalize("NFD", str(text).lower())
    t = re.sub(r"[^a-z0-9]+", "-", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip("-")
    return t[:36].strip("-") or "estil"


def empaqueta(carpeta: Path, fitxer: str = FITXER, carpetes: tuple = ("fonts",), dades: dict | None = None,
              extres: dict | None = None, exclou: tuple = ()) -> tuple[str, bytes]:
    """Una carpeta d'estil en un `.estil.zip`: (nom del fitxer, contingut). `dades` (si es passa) és l'estil que hi
    va, ja en format comú; si no, es llegeix `fitxer` i es migra. Hi van les carpetes de `carpetes` (menys les
    subcarpetes que es diuen com algun nom d'`exclou`), NOTES.md i `extres` ({camí dins del zip: fitxer}), que
    han de caure dins d'una carpeta coneguda."""
    carpeta = Path(carpeta)
    if dades is None:
        dades = migra(json.loads((carpeta / fitxer).read_text(encoding="utf-8")))
    dades = neteja(dades)
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(FITXER, json.dumps(dades, ensure_ascii=False, indent=2) + "\n")
        for nom in carpetes:
            sub = carpeta / nom
            permesos = CARPETES.get(nom, set())
            for f in sorted(sub.rglob("*")) if sub.is_dir() else []:
                rel = f.relative_to(sub)
                if (f.is_file() and not f.name.startswith(".") and f.suffix.lower() in permesos
                        and not any(p in exclou for p in rel.parts[:-1])):
                    z.write(f, f"{nom}/{rel.as_posix()}")
        for dins, f in (extres or {}).items():
            parts = dins.split("/")
            if len(parts) < 2 or parts[0] not in CARPETES or Path(dins).suffix.lower() not in CARPETES[parts[0]]:
                raise ValueError(f"{dins} no pot anar dins d'un estil")
            z.write(f, dins)
        if (carpeta / NOTES).is_file():
            z.write(carpeta / NOTES, NOTES)
    return f"{slug(dades.get('nom') or carpeta.name)}.estil.zip", memoria.getvalue()


def llegeix_zip(contingut: bytes) -> tuple[dict, dict]:
    """Obre un `.estil.zip` (o un `.tallat-kit.zip` d'abans): (estil net en format comú, {camí: bytes} dels fitxers
    que l'acompanyen, només dins de les carpetes conegudes i NOTES.md). No escriu res."""
    try:
        z = zipfile.ZipFile(io.BytesIO(contingut))
    except zipfile.BadZipFile:
        raise ValueError("Aquest fitxer no és un estil (ha de ser el .zip que fa «Exporta»).") from None
    with z:
        infos = {i.filename: i for i in z.infolist() if not i.is_dir()}
        principal = next((n for n in (FITXER, *FITXERS_VELLS) if n in infos), None)
        if principal is None:
            raise ValueError("Aquest .zip no té cap estil.json: no és un estil.")
        if sum(i.file_size for i in infos.values()) > MIDA_MAXIMA:
            raise ValueError("Aquest estil és massa gran.")
        try:
            dades = json.loads(z.read(principal).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("L'estil.json d'aquest estil no es pot llegir.") from None
        if not isinstance(dades, dict):
            raise ValueError("L'estil.json d'aquest estil no es pot llegir.")
        fitxers = {}
        for nom, info in infos.items():
            parts = nom.split("/")
            if nom == NOTES or (len(parts) >= 2 and parts[0] in CARPETES and Path(nom).suffix.lower() in CARPETES[parts[0]]
                                and not any(p.startswith(".") or p in ("", "..") or ":" in p or "\\" in p for p in parts)):
                fitxers[nom] = z.read(info)
    return neteja(migra(dades)), fitxers


def importa(contingut: bytes, desti: Path, fitxer: str = FITXER) -> dict:
    """Desa un `.estil.zip` a la carpeta `desti` (que no ha d'existir): l'estil a `fitxer` i les carpetes que porta.
    Torna l'estil desat."""
    dades, fitxers = llegeix_zip(contingut)
    desti = Path(desti)
    desti.mkdir(parents=True)
    for nom, cos in fitxers.items():
        cami = desti / nom
        cami.parent.mkdir(parents=True, exist_ok=True)
        cami.write_bytes(cos)
    (desti / fitxer).write_text(json.dumps(dades, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dades
