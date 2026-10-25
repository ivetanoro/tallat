"""Kits d'estil de cada persona.

Un kit és un estil amb nom: com són els subtítols, el b-roll, els stickers i els talls (i, amb
les fonts pròpies, la lletra). Cada persona en pot tenir uns quants a ~/.tallat/kits/, fora del
repositori, triar-ne un per a cada vídeo i passar-ne un a una altra persona (un .zip).

  ~/.tallat/kits/<kit>/kit.json   l'estil (els valors que hi falten es prenen de l'estil neutre,
                                  config/brand.example.json)
  ~/.tallat/kits/<kit>/fonts/     les fonts pròpies del kit
  ~/.tallat/kits/kits.json        quin és el kit per defecte (el dels vídeos nous)

El primer cop, l'estil que la persona ja tenia (~/.tallat/brand.json, d'abans dels kits) es
converteix en el kit «El meu estil». brand.json no es toca, però ja no es fa servir.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config"
PER_DEFECTE = CONFIG / "brand.example.json"
ESTILS = CONFIG / "estils_subtitols.json"
ESTILS_TITOL = CONFIG / "estils_titol.json"
ESTILS_BROLL = CONFIG / "estils_broll.json"
ESTILS_VIDEO = CONFIG / "estils_video.json"
LLETRES = CONFIG / "lletres.json"
USUARI = Path.home() / ".tallat" / "brand.json"  # l'estil d'abans dels kits: amb ell es fa el primer kit
KITS = Path.home() / ".tallat" / "kits"
FITXER_KIT = "kit.json"
INDEX = "kits.json"
PRIMER_KIT = ("el-meu-estil", "El meu estil")
INFO_KIT = ("Kit d'estil de tallat. Es canvia des de la pàgina de revisió (o a mà, aquí). "
            "Els valors que hi falten es prenen de l'estil neutre de tallat.")
ID_KIT = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
MIDA_MAXIMA_KIT = 60 * 1024 * 1024  # un kit importat (amb les seves fonts), com a màxim
FORMATS_FONT = {".ttf", ".otf", ".woff", ".woff2"}

# Què es pot canviar (des de la pàgina o amb les regles del teu gust), i entre quins límits.
EDITABLES = {"subtitols", "titol", "broll", "stickers", "talls", "so", "marca"}
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
# Opcions que són una llista (se'n pot triar més d'una).
LLISTES = {"marca": {"energia": {"net", "mac", "scrapbook", "editorial"}}}
MIDA_TEXT = 600  # els textos de la marca (el compte, la referència…), com a molt
# La marca s'escampa: cada color i cada lletra fa la seva feina a la resta del kit.
ENLLACOS_MARCA = {
    "color_text": [("subtitols", "color"), ("titol", "color")],
    "color_fosc": [("subtitols", "contorn"), ("titol", "contorn")],  # també el color de les ombres
    "color_destacat": [("subtitols", "color_actiu"), ("subtitols", "clau_color"), ("titol", "clau_color")],
    "color_principal": [("broll", "vora_color")],
    "lletra_text": [("subtitols", "font")],
    "lletra_titols": [("titol", "font")],
    "lletra_accent": [("subtitols", "clau_font"), ("titol", "clau_font")],
}
NOM_DE_FONT = re.compile(r"^[\w][\w .-]{0,60}$")


_neutre: dict = {}


def _estil_neutre() -> dict:
    """L'estil neutre sense notes (una còpia: qui el fa servir el pot canviar). Es llegeix un sol cop mentre el
    fitxer no canvia: valida i carrega el demanen a cada opció i a cada petició."""
    marca_temps = PER_DEFECTE.stat().st_mtime_ns
    if _neutre.get("temps") != marca_temps:
        _neutre.update(temps=marca_temps, dades=_sense_notes(json.loads(PER_DEFECTE.read_text(encoding="utf-8"))))
    return json.loads(json.dumps(_neutre["dades"]))


def _sense_notes(d: dict) -> dict:
    """Treu les claus que comencen per «_» (són explicacions per a les persones)."""
    return {k: (_sense_notes(v) if isinstance(v, dict) else v) for k, v in d.items() if not k.startswith("_")}


def _llegeix_json(path: Path) -> dict:
    try:
        dades = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dades if isinstance(dades, dict) else {}


# --- Kits --------------------------------------------------------------------------------------

def _existeix(kit) -> bool:
    return isinstance(kit, str) and bool(ID_KIT.match(kit)) and (KITS / kit / FITXER_KIT).is_file()


def _inicialitza() -> None:
    """El primer cop: l'estil que la persona ja tenia es converteix en el kit «El meu estil»."""
    if KITS.is_dir() and any(_existeix(c.name) for c in KITS.iterdir() if c.is_dir()):
        return
    id_, nom = PRIMER_KIT
    carpeta = KITS / id_
    carpeta.mkdir(parents=True, exist_ok=True)
    dades = _llegeix_json(USUARI) or json.loads(PER_DEFECTE.read_text(encoding="utf-8"))
    subtitols = dades.get("subtitols") if isinstance(dades.get("subtitols"), dict) else {}
    font = subtitols.get("font_fitxer")
    if font:  # la font pròpia passa a viure dins del kit (així el kit es pot passar a una altra persona)
        origen = Path(str(font)).expanduser()
        if origen.is_file() and origen.suffix.lower() in FORMATS_FONT:
            (carpeta / "fonts").mkdir(exist_ok=True)
            shutil.copy2(origen, carpeta / "fonts" / origen.name)
            subtitols["font_fitxer"] = f"fonts/{origen.name}"
        else:
            subtitols["font_fitxer"] = None
    dades.update(_info=INFO_KIT, nom=nom)
    _escriu(dades, carpeta / FITXER_KIT)
    _escriu({"per_defecte": id_}, KITS / INDEX)


def kit_per_defecte() -> str:
    _inicialitza()
    triat = _llegeix_json(KITS / INDEX).get("per_defecte")
    if _existeix(triat):
        return triat
    return next(c.name for c in sorted(KITS.iterdir()) if c.is_dir() and _existeix(c.name))


def resol(kit: str | None) -> str:
    """El kit demanat, si existeix; si no (o si no se'n demana cap), el kit per defecte."""
    return kit if _existeix(kit) else kit_per_defecte()


COLORS_MOSTRA = ("color_text", "color_principal", "color_destacat", "color_secundari")  # els de la mostra de cada kit


def kits() -> list[dict]:
    """[{id, nom, per_defecte, colors}], amb el kit per defecte primer i els altres per ordre alfabètic.
    `colors`: els de la mostra que en fa la pàgina (COLORS_MOSTRA), els que el kit tingui triats."""
    defecte = kit_per_defecte()
    llista = []
    for carpeta in KITS.iterdir():
        if carpeta.is_dir() and _existeix(carpeta.name):
            dades = _llegeix_json(carpeta / FITXER_KIT)
            nom = dades.get("nom")
            marca_ = dades.get("marca") if isinstance(dades.get("marca"), dict) else {}
            llista.append({"id": carpeta.name, "nom": nom.strip() if isinstance(nom, str) and nom.strip() else carpeta.name,
                           "per_defecte": carpeta.name == defecte,
                           "colors": [c for c in (marca_.get(k) for k in COLORS_MOSTRA) if isinstance(c, str) and c]})
    return sorted(llista, key=lambda k: (not k["per_defecte"], k["nom"].lower()))


def _slug(text: str) -> str:
    t = unicodedata.normalize("NFD", str(text).lower())
    t = re.sub(r"[^a-z0-9]+", "-", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip("-")
    return t[:36].strip("-") or "kit"


def _nom_valid(nom) -> str:
    nom = " ".join(str(nom or "").split())[:60]
    if not nom:
        raise ValueError("El kit necessita un nom")
    return nom


def _id_nou(nom: str) -> str:
    base = _slug(nom)
    id_, n = base, 2
    while (KITS / id_).exists():
        id_, n = f"{base}-{n}", n + 1
    return id_


def crea_kit(nom: str, copia_de: str | None = None) -> str:
    """Un kit nou: una còpia d'un altre (amb les seves fonts) o, si no se'n diu cap, l'estil neutre."""
    nom = _nom_valid(nom)
    _inicialitza()
    if copia_de is not None and not _existeix(copia_de):
        raise KeyError(copia_de)
    id_ = _id_nou(nom)
    if copia_de is not None:
        shutil.copytree(KITS / copia_de, KITS / id_)
        dades = _llegeix_json(KITS / id_ / FITXER_KIT)
    else:
        (KITS / id_).mkdir(parents=True)
        dades = {**json.loads(PER_DEFECTE.read_text(encoding="utf-8")), "_info": INFO_KIT}
    dades["nom"] = nom
    _escriu(dades, KITS / id_ / FITXER_KIT)
    return id_


def canvia_nom(kit: str, nom: str) -> None:
    if not _existeix(kit):
        raise KeyError(kit)
    path = KITS / kit / FITXER_KIT
    dades = _llegeix_json(path)
    dades["nom"] = _nom_valid(nom)
    _escriu(dades, path)


def fes_per_defecte(kit: str) -> None:
    if not _existeix(kit):
        raise KeyError(kit)
    _escriu({"per_defecte": kit}, KITS / INDEX)


def esborra_kit(kit: str) -> Path:
    """Treu un kit de la llista. No s'esborra de debò: va a ~/.tallat/kits-esborrats, per si de cas."""
    if not _existeix(kit):
        raise KeyError(kit)
    if kit == kit_per_defecte():
        raise ValueError("És el kit per defecte. Abans de treure'l, tria'n un altre per defecte.")
    desti = KITS.parent / "kits-esborrats" / f"{kit}-{time.strftime('%Y%m%d-%H%M%S')}"
    desti.parent.mkdir(parents=True, exist_ok=True)
    (KITS / kit).rename(desti)
    return desti


def empaqueta_kit(kit: str) -> tuple[str, bytes]:
    """El kit en un .zip, per passar-lo a una altra persona o a un altre Mac: (nom del fitxer, contingut)."""
    if not _existeix(kit):
        raise KeyError(kit)
    carpeta = KITS / kit
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(carpeta / FITXER_KIT, FITXER_KIT)
        fonts = carpeta / "fonts"
        for font in sorted(fonts.iterdir()) if fonts.is_dir() else []:
            if font.is_file() and font.suffix.lower() in FORMATS_FONT:
                z.write(font, f"fonts/{font.name}")
    nom = _llegeix_json(carpeta / FITXER_KIT).get("nom") or kit
    return f"{_slug(nom)}.tallat-kit.zip", memoria.getvalue()


def importa_kit(contingut: bytes) -> str:
    """Afegeix un kit d'un .zip (fet amb «Exporta»). Només se'n agafa el que tallat entén: les opcions
    vàlides de l'estil i les fonts. La resta (camins de fitxers, opcions estranyes) es deixa estar."""
    try:
        z = zipfile.ZipFile(io.BytesIO(contingut))
    except zipfile.BadZipFile:
        raise ValueError("Aquest fitxer no és un kit de tallat (ha de ser el .zip que fa «Exporta»).") from None
    with z:
        fitxers = {i.filename: i for i in z.infolist() if not i.is_dir()}
        if FITXER_KIT not in fitxers:
            raise ValueError("Aquest .zip no té cap kit.json: no és un kit de tallat.")
        if sum(i.file_size for i in fitxers.values()) > MIDA_MAXIMA_KIT:
            raise ValueError("Aquest kit és massa gran.")
        try:
            dades = json.loads(z.read(FITXER_KIT).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("El kit.json d'aquest kit no es pot llegir.") from None
        if not isinstance(dades, dict):
            raise ValueError("El kit.json d'aquest kit no es pot llegir.")
        fonts = {nom[len("fonts/"):]: info for nom, info in fitxers.items()
                 if re.fullmatch(r"fonts/[^/\\:]+", nom) and not nom[len("fonts/"):].startswith(".")
                 and Path(nom).suffix.lower() in FORMATS_FONT}
        net = {"_info": INFO_KIT, "nom": _nom_valid(dades.get("nom") or "Kit importat")}
        if any(k["nom"] == net["nom"] for k in kits()):
            net["nom"] = _nom_valid(f"{net['nom']} (importat)")
        for seccio in sorted(EDITABLES):
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
        font = (dades.get("subtitols") or {}).get("font_fitxer") if isinstance(dades.get("subtitols"), dict) else None
        if isinstance(font, str) and font.startswith("fonts/") and font[len("fonts/"):] in fonts:
            net.setdefault("subtitols", {})["font_fitxer"] = font
        id_ = _id_nou(net["nom"])
        carpeta = KITS / id_
        (carpeta / "fonts").mkdir(parents=True)
        for nom, info in fonts.items():
            (carpeta / "fonts" / nom).write_bytes(z.read(info))
        _escriu(net, carpeta / FITXER_KIT)
    return id_


def ruta(kit: str | None = None) -> Path:
    """El fitxer d'estil d'un kit (sense dir-ne cap, el del kit per defecte)."""
    return KITS / resol(kit) / FITXER_KIT


def carrega(path: Path | None = None, kit: str | None = None) -> dict:
    """L'estil sencer d'un kit (o d'un fitxer), amb els valors que hi falten presos de l'estil neutre."""
    path = path or ruta(kit)
    base = _estil_neutre()
    for seccio, valors in _sense_notes(_llegeix_json(path)).items():
        if seccio == "nom":  # el nom del kit no és part de l'estil
            continue
        if isinstance(valors, dict) and isinstance(base.get(seccio), dict):
            base[seccio].update(valors)
        else:
            base[seccio] = valors
    font = base.get("subtitols", {}).get("font_fitxer")
    if font and not Path(str(font)).expanduser().is_absolute():  # les fonts del kit: «fonts/…», dins del kit
        base["subtitols"]["font_fitxer"] = str(path.parent / font)
    return base


def pausa_per_defecte() -> float:
    """El silenci màxim dels projectes nous (secció «talls» del fitxer d'estil)."""
    return float(carrega().get("talls", {}).get("pausa_maxima", 0.35))


def _estils(path: Path) -> list[dict]:
    """Uns estils fets: [{id, nom, descripcio, valors}]. Cada un parteix de «comu», perquè triar-ne un
    no deixi a mitges el que havia posat un altre."""
    dades = json.loads(path.read_text(encoding="utf-8"))
    comu = dades.get("comu", {})
    return [{**e, "valors": {**comu, **e["valors"]}} for e in dades["estils"]]


def estils() -> list[dict]:
    """Els estils de subtítols fets."""
    return _estils(ESTILS)


def estils_titol() -> list[dict]:
    """Els estils de títol fets."""
    return _estils(ESTILS_TITOL)


def estils_broll() -> list[dict]:
    """Les maneres de posar el b-roll fetes."""
    return _estils(ESTILS_BROLL)


# --- L'estil de cada vídeo ----------------------------------------------------------------------
# El kit diu com són tots els vídeos d'aquell estil; cada vídeo en pot canviar el que vulgui sense tocar els altres
# (l'estat de l'edició, «estil»: es desfà com la resta). «Fes-lo servir en tots els vídeos» ho passa al kit.
# Els colors i les lletres (la secció «marca») són sempre del kit: valen per a tots els vídeos.

SECCIONS_VIDEO = ("subtitols", "titol", "broll", "so")
ESTILS_GRAFICS = ("net", "mac", "scrapbook", "editorial")
# El que posen els colors i les lletres de la persona (ENLLACOS_MARCA): un estil del vídeo no ho porta, i així
# sempre surt amb els seus colors i lletres (i, si els canvia, tots els vídeos ho veuen).
DE_LA_MARCA = {"subtitols": {"color", "contorn", "color_actiu", "clau_color", "font", "clau_font", "clau_cursiva",
                             "font_fitxer", "posicio_y"},
               "titol": {"color", "contorn", "clau_color", "font", "clau_font", "clau_cursiva"},
               "broll": {"vora_color"}}


def estils_video() -> list[dict]:
    """Els estils de tot el vídeo: [{id, nom, descripcio, subtitols, titol, broll (els valors), grafics}]. Dels
    subtítols, tampoc no hi va la posició (on els tens, s'hi queden)."""
    parts = {"subtitols": {e["id"]: e for e in estils()}, "titol": {e["id"]: e for e in estils_titol()},
             "broll": {e["id"]: e for e in estils_broll()}}
    sortida = []
    for e in json.loads(ESTILS_VIDEO.read_text(encoding="utf-8"))["estils"]:
        estil = {"id": e["id"], "nom": e["nom"], "descripcio": e.get("descripcio", ""), "grafics": e["grafics"]}
        for seccio, fets in parts.items():
            estil[seccio] = {k: v for k, v in fets[e[seccio]]["valors"].items() if k not in DE_LA_MARCA[seccio]}
        sortida.append(estil)
    return sortida


def neteja_estil_video(estil) -> dict:
    """L'estil propi d'un vídeo, comprovat opció a opció (el que no s'entén, fora: la resta es queda)."""
    if not isinstance(estil, dict):
        return {}
    net: dict = {}
    for seccio in SECCIONS_VIDEO:
        for clau, valor in (estil.get(seccio) or {}).items() if isinstance(estil.get(seccio), dict) else ():
            try:
                net.setdefault(seccio, {}).update(valida(seccio, {clau: valor}))
            except ValueError:
                continue
    if estil.get("grafics") in ESTILS_GRAFICS:
        net["grafics"] = estil["grafics"]
    return net


def amb_la_marca(estil: dict) -> dict:
    """Els colors i les lletres de la marca, a sobre de les seccions del kit: manen sempre (un estil fet que s'hi
    hagués triat abans no els trepitja). Els que la marca no té, es queden com són. Sense color destacat, les
    destacades van del color del text (com _escampa_marca). Després, un vídeo encara els pot canviar (amb_estil_video)."""
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


def amb_estil_video(base: dict, estil: dict | None) -> dict:
    """L'estil d'un kit (carrega) amb el que el vídeo hi ha canviat al damunt."""
    for seccio, valors in (estil or {}).items():
        if seccio == "grafics":
            base.setdefault("marca", {})["energia"] = [valors]
        elif isinstance(valors, dict):
            base.setdefault(seccio, {}).update(valors)
    return base


def claus_de_la_marca(m: dict) -> dict:
    """{seccio: claus} que hi posa la marca `m` (les que té): a sobre d'aquestes, el kit no hi mana (amb_la_marca)."""
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


def passa_al_kit(estil: dict, kit: str | None = None, path: Path | None = None) -> dict:
    """«Fes-lo servir en tots els vídeos»: el que un vídeo ha canviat, al seu kit. Els colors i les lletres que hi posa
    la marca no hi van (al kit, la marca hi passaria al damunt i es perdrien): torna el que s'ha de quedar al vídeo."""
    marca_ = carrega(path, kit).get("marca") or {}
    de_la_marca = claus_de_la_marca(marca_)
    queda: dict = {}
    for seccio in SECCIONS_VIDEO:
        valors = estil.get(seccio) or {}
        propis = {k: v for k, v in valors.items() if k in de_la_marca.get(seccio, set())}
        resta = {k: v for k, v in valors.items() if k not in propis}
        if resta:
            desa(seccio, resta, path, kit)
        if propis:
            queda[seccio] = propis
    if estil.get("grafics"):
        desa("marca", {"energia": [estil["grafics"]]}, path, kit)
    return queda


def valida(seccio: str, canvis: dict) -> dict:
    """Comprova els canvis que arriben de la pàgina; llança ValueError amb un missatge clar si n'hi ha cap de dolent."""
    if seccio not in EDITABLES:
        raise ValueError(f"No es pot canviar la secció «{seccio}»")
    base = _estil_neutre()[seccio]
    net = {}
    for clau, valor in canvis.items():
        if clau not in base:
            raise ValueError(f"Opció desconeguda: {clau}")
        defecte = base[clau]
        rangs, opcions = RANGS.get(seccio, {}), OPCIONS.get(seccio, {})
        if defecte is None and clau in COLORS:  # un color que també pot ser «el de sempre» (null)
            if valor is not None and not (isinstance(valor, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", valor)):
                raise ValueError(f"{clau} ha de ser un color com #FFD60A")
        elif defecte is None and (clau in ("font", "clau_font") or clau.startswith("lletra_")):  # null: la de sempre
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
            if isinstance(defecte, int):
                valor = int(round(valor))
            else:
                valor = round(float(valor), 4)
        elif isinstance(defecte, str):
            if not isinstance(valor, str):
                raise ValueError(f"{clau} ha de ser un text")
            if clau in COLORS and not re.fullmatch(r"#[0-9A-Fa-f]{6}", valor):
                raise ValueError(f"{clau} ha de ser un color com #FFD60A")
            if clau in opcions and valor not in opcions[clau]:
                raise ValueError(f"{clau} no pot ser «{valor}»")
            if clau == "font" and not NOM_DE_FONT.match(valor):
                raise ValueError("Aquest nom de font no és vàlid")
            valor = valor.strip()[:MIDA_TEXT] if not opcions.get(clau) and clau not in COLORS else valor
        net[clau] = valor
    return net


def _escriu(dades: dict, path: Path) -> None:
    temporal = path.with_suffix(".tmp")
    temporal.write_text(json.dumps(dades, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporal.replace(path)


def desa(seccio: str, canvis: dict, path: Path | None = None, kit: str | None = None) -> dict:
    """Desa els canvis al kit (conservant-ne les notes) i en torna la secció sencera."""
    net = valida(seccio, canvis)
    path = path or ruta(kit)
    dades = _llegeix_json(path)
    dades.setdefault(seccio, {}).update(net)
    if seccio == "marca":
        _escampa_marca(dades, net)
    _escriu(dades, path)
    return carrega(path)[seccio]


def _escampa_marca(dades: dict, canvis: dict) -> None:
    """Posa els colors i les lletres de la marca allà on fan la seva feina (si se'n treu un, hi torna
    el de l'estil neutre). Sense color destacat, les destacades van del color del text. Després cada
    opció es pot retocar a part."""
    base = _sense_notes(json.loads(PER_DEFECTE.read_text(encoding="utf-8")))
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
        if clau == "lletra_accent":  # la paraula emotiva, en cursiva
            for seccio in ("subtitols", "titol"):
                dades.setdefault(seccio, {})["clau_cursiva"] = valor is not None


def restableix(seccio: str, path: Path | None = None, kit: str | None = None) -> dict:
    """Torna una secció a l'estil neutre de tallat (amb les notes que expliquen cada opció)."""
    if seccio not in EDITABLES:
        raise ValueError(f"No es pot canviar la secció «{seccio}»")
    path = path or ruta(kit)
    dades = _llegeix_json(path)
    abans = dades.get(seccio) if isinstance(dades.get(seccio), dict) else {}
    dades[seccio] = json.loads(PER_DEFECTE.read_text(encoding="utf-8"))[seccio]
    if seccio == "broll" and abans.get("lut"):  # el LUT és un fitxer de la persona: es queda
        dades[seccio]["lut"] = abans["lut"]
    _escriu(dades, path)
    return carrega(path)[seccio]


# --- Lletres ------------------------------------------------------------------------------------
# Cada kit porta les seves lletres a fonts/. El nom del fitxer en diu la família i el gruix:
# «Inter__var.woff2» (una lletra variable: tots els gruixos), «Poppins__700.woff2» o, les que puja
# la persona, «La Meva Lletra.otf». Així el kit es pot passar a algú amb les lletres i tot.

def biblioteca_lletres() -> dict:
    """Les lletres gratuïtes que tallat pot baixar (config/lletres.json)."""
    return json.loads(LLETRES.read_text(encoding="utf-8"))


def _nom_familia(text: str) -> str:
    return re.sub(r"[^\w .-]", "", str(text)).replace("__", "_").strip()[:60]


def fonts_del_kit(kit: str | None = None, path: Path | None = None) -> list[dict]:
    """Les lletres que porta un kit: [{familia, pes, fitxer}] (pes: un número o «100 1000», tots)."""
    path = path or ruta(kit)
    carpeta = path.parent / "fonts"
    llista = []
    for f in sorted(carpeta.iterdir()) if carpeta.is_dir() else []:
        if not f.is_file() or f.suffix.lower() not in FORMATS_FONT or f.name.startswith("."):
            continue
        familia, _, pes = f.stem.partition("__")
        estil = "italic" if pes.endswith("-cursiva") else "normal"  # «Fraunces__var-cursiva»: la cursiva
        pes = pes.removesuffix("-cursiva")
        llista.append({"familia": familia, "pes": pes if pes.isdigit() else "100 1000", "estil": estil, "fitxer": f})
    # Els kits d'abans: la font pròpia era un fitxer qualsevol, i la família, la de «font».
    subtitols = _llegeix_json(path).get("subtitols")
    if isinstance(subtitols, dict) and subtitols.get("font_fitxer") and subtitols.get("font"):
        fitxer = Path(str(subtitols["font_fitxer"])).expanduser()
        fitxer = fitxer if fitxer.is_absolute() else path.parent / fitxer
        if fitxer.is_file() and fitxer.suffix.lower() in FORMATS_FONT and not any(
                f["fitxer"] == fitxer and f["familia"] == subtitols["font"] for f in llista):
            llista.append({"familia": str(subtitols["font"]), "pes": "100 1000", "estil": "normal", "fitxer": fitxer})
    return llista


def fonts_de(estil: dict, kit: str | None = None, path: Path | None = None, titol: dict | None = None) -> list[dict]:
    """Les lletres del kit que fa servir un estil de subtítols (i, si se'n passa, el del títol), també
    la de les paraules destacades."""
    titol = titol or {}
    families = {estil.get("font"), titol.get("font") or estil.get("font"), estil.get("clau_font"), titol.get("clau_font")}
    return [f for f in fonts_del_kit(kit, path) if f["familia"] in families]


# On es pot posar una lletra de la biblioteca: (secció del kit, clau).
LLOCS_LLETRA = {("subtitols", "font"), ("titol", "font"), ("subtitols", "clau_font"), ("titol", "clau_font"),
                ("marca", "lletra_titols"), ("marca", "lletra_text"), ("marca", "lletra_accent"), ("marca", "lletra_ma")}


def baixa_lletra(id_lletra: str, kit: str | None = None, path: Path | None = None, seccio: str = "subtitols",
                 clau: str = "font", nomes_baixa: bool = False) -> dict | str:
    """Posa una lletra de la biblioteca al kit (la baixa el primer cop, amb la cursiva si en té) i la fa
    servir on diu `seccio` i `clau`: els subtítols, el títol, les paraules destacades o la marca (que
    l'escampa on toca). Torna l'estil d'aquella secció."""
    if (seccio, clau) not in LLOCS_LLETRA:
        raise ValueError("Secció desconeguda")
    biblioteca = biblioteca_lletres()
    lletra = next((l for l in biblioteca["lletres"] if l["id"] == id_lletra), None)
    if lletra is None:
        raise KeyError(id_lletra)
    path = path or ruta(kit)
    carpeta = path.parent / "fonts"
    carpeta.mkdir(parents=True, exist_ok=True)
    nom, id_ = lletra["nom"], lletra["id"]
    estils = ["normal", "italic"] if lletra.get("cursiva") else ["normal"]
    if lletra.get("variable"):
        fitxers = [(f"@fontsource-variable/{id_}", f"{id_}-latin-wght-{e}", "var") for e in estils]
    else:
        fitxers = [(f"@fontsource/{id_}", f"{id_}-latin-{p}-{e}", str(p)) for p in lletra["pesos"] for e in estils]
    for paquet, fitxer, pes in fitxers:
        cursiva = "-cursiva" if fitxer.endswith("-italic") else ""
        desti = carpeta / f"{nom}__{pes}{cursiva}.woff2"
        if desti.is_file():
            continue
        url = f"{biblioteca['cdn']}/{paquet}@{biblioteca['versio']}/files/{fitxer}.woff2"
        try:
            with urllib.request.urlopen(url, timeout=30) as resposta:
                contingut = resposta.read(5_000_001)
        except (OSError, urllib.error.URLError) as e:
            raise ConnectionError(f"No he pogut baixar la lletra «{nom}». Comprova la connexió a internet.") from e
        if not contingut.startswith(b"wOF2") or len(contingut) > 5_000_000:
            raise ConnectionError(f"La lletra «{nom}» no s'ha baixat bé. Torna-ho a provar.")
        temporal = desti.with_name(f".{desti.name}.baixant")
        temporal.write_bytes(contingut)
        temporal.replace(desti)
    if nomes_baixa:  # a les lletres del kit, i prou: torna el nom (un vídeo la posa al seu estil)
        return nom
    if seccio == "marca":
        return desa("marca", {clau: nom}, path)
    dades = _llegeix_json(path)
    dades.setdefault(seccio, {})[clau] = nom
    if (seccio, clau) == ("subtitols", "font"):
        dades["subtitols"]["font_fitxer"] = None
    _escriu(dades, path)
    return carrega(path)[seccio]


def desa_font(nom: str, contingut: bytes, path: Path | None = None, kit: str | None = None) -> dict:
    """Guarda una font pròpia dins del kit (a la seva carpeta fonts/) i la fa servir per als subtítols."""
    origen = Path(nom).name
    if Path(origen).suffix.lower() not in FORMATS_FONT or origen.startswith("."):
        raise ValueError("La font ha de ser un fitxer .ttf, .otf, .woff o .woff2")
    if not contingut:
        raise ValueError("El fitxer de la font és buit")
    familia = _nom_familia(Path(origen).stem) or "La meva font"
    path = path or ruta(kit)
    (path.parent / "fonts").mkdir(parents=True, exist_ok=True)
    (path.parent / "fonts" / f"{familia}{Path(origen).suffix.lower()}").write_bytes(contingut)
    dades = _llegeix_json(path)
    dades.setdefault("subtitols", {}).update({"font": familia, "font_fitxer": None})
    _escriu(dades, path)
    return carrega(path)["subtitols"]


def afegeix_font(contingut: bytes, nom_fitxer: str, familia: str, pes: str = "400", cursiva: bool = False,
                 path: Path | None = None, kit: str | None = None) -> Path:
    """Desa una lletra pròpia al kit amb el nom que entén tallat («Família__pes.ttf», amb «-cursiva»),
    sense fer-la servir enlloc encara (això ho fa la marca o l'estil). Torna el fitxer."""
    extensio = Path(nom_fitxer).suffix.lower()
    if extensio not in FORMATS_FONT:
        raise ValueError("La font ha de ser un fitxer .ttf, .otf, .woff o .woff2")
    if not contingut:
        raise ValueError("El fitxer de la font és buit")
    familia = _nom_familia(familia)
    if not familia or not NOM_DE_FONT.match(familia):
        raise ValueError("Aquest nom de lletra no és vàlid")
    if not re.fullmatch(r"\d{3}|var", str(pes)):
        raise ValueError("El gruix ha de ser un número com 400 o «var» (una lletra variable)")
    path = path or ruta(kit)
    carpeta = path.parent / "fonts"
    carpeta.mkdir(parents=True, exist_ok=True)
    desti = carpeta / f"{familia}__{pes}{'-cursiva' if cursiva else ''}{extensio}"
    desti.write_bytes(contingut)
    return desti


def fitxer_font(estil: dict) -> Path | None:
    """El fitxer de la font pròpia dels subtítols, si n'hi ha una i existeix."""
    font = estil.get("font_fitxer")
    if not font:
        return None
    path = Path(font).expanduser()
    return path if path.suffix.lower() in FORMATS_FONT and path.is_file() else None
