"""Estil de marca de cada persona.

tallat porta un estil neutre (config/brand.example.json). La còpia personal és a
~/.tallat/brand.json, fora del repositori: es crea el primer cop i es pot editar a mà
o des de la pàgina de revisió. Els valors que hi faltin es prenen de l'estil neutre.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config"
PER_DEFECTE = CONFIG / "brand.example.json"
ESTILS = CONFIG / "estils_subtitols.json"
USUARI = Path.home() / ".tallat" / "brand.json"
FONTS = Path.home() / ".tallat" / "fonts"
FORMATS_FONT = {".ttf", ".otf", ".woff", ".woff2"}

# Què es pot canviar des de la pàgina, i entre quins límits.
EDITABLES = {"subtitols"}
RANGS = {"mida": (0.03, 0.16), "pes": (100, 900), "gruix_contorn": (0.0, 0.2), "posicio_y": (0.08, 0.92),
         "amplada_maxima": (0.4, 0.98), "paraules_per_linia": (1, 12), "lletres_per_linia": (4, 60)}
OPCIONS = {"animacio": {"pop", "fos", "cap"}, "apareixen": {"paraula", "linia"}}
COLORS = {"color", "color_actiu", "contorn"}
NOM_DE_FONT = re.compile(r"^[\w][\w .-]{0,60}$")


def _sense_notes(d: dict) -> dict:
    """Treu les claus que comencen per «_» (són explicacions per a les persones)."""
    return {k: (_sense_notes(v) if isinstance(v, dict) else v) for k, v in d.items() if not k.startswith("_")}


def ruta() -> Path:
    if not USUARI.exists():
        USUARI.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(PER_DEFECTE, USUARI)
    return USUARI


def carrega(path: Path | None = None) -> dict:
    base = _sense_notes(json.loads(PER_DEFECTE.read_text(encoding="utf-8")))
    try:
        propi = _sense_notes(json.loads((path or ruta()).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        propi = {}
    for seccio, valors in propi.items():
        if isinstance(valors, dict) and isinstance(base.get(seccio), dict):
            base[seccio].update(valors)
        else:
            base[seccio] = valors
    return base


def estils() -> list[dict]:
    """Els estils de subtítols predefinits: [{id, nom, descripcio, valors}]."""
    return json.loads(ESTILS.read_text(encoding="utf-8"))["estils"]


def valida(seccio: str, canvis: dict) -> dict:
    """Comprova els canvis que arriben de la pàgina; llança ValueError amb un missatge clar si n'hi ha cap de dolent."""
    if seccio not in EDITABLES:
        raise ValueError(f"No es pot canviar la secció «{seccio}»")
    base = _sense_notes(json.loads(PER_DEFECTE.read_text(encoding="utf-8")))[seccio]
    net = {}
    for clau, valor in canvis.items():
        if clau not in base:
            raise ValueError(f"Opció desconeguda: {clau}")
        defecte = base[clau]
        if clau == "font_fitxer":
            if valor is not None:  # la font pròpia només es posa pujant-la (desa_font)
                raise ValueError("La font pròpia s'ha de pujar com a fitxer")
        elif isinstance(defecte, bool):
            if not isinstance(valor, bool):
                raise ValueError(f"{clau} ha de ser sí o no")
        elif isinstance(defecte, (int, float)):
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                raise ValueError(f"{clau} ha de ser un número")
            if clau in RANGS:
                a, b = RANGS[clau]
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
            if clau in OPCIONS and valor not in OPCIONS[clau]:
                raise ValueError(f"{clau} no pot ser «{valor}»")
            if clau == "font" and not NOM_DE_FONT.match(valor):
                raise ValueError("Aquest nom de font no és vàlid")
        net[clau] = valor
    return net


def _escriu(dades: dict, path: Path) -> None:
    temporal = path.with_suffix(".tmp")
    temporal.write_text(json.dumps(dades, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporal.replace(path)


def desa(seccio: str, canvis: dict, path: Path | None = None) -> dict:
    """Desa els canvis al fitxer de la persona (conservant-ne les notes) i en torna la secció sencera."""
    net = valida(seccio, canvis)
    path = path or ruta()
    try:
        dades = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        dades = {}
    dades.setdefault(seccio, {}).update(net)
    _escriu(dades, path)
    return carrega(path)[seccio]


def restableix(seccio: str, path: Path | None = None) -> dict:
    """Torna una secció a l'estil neutre de tallat (amb les notes que expliquen cada opció)."""
    if seccio not in EDITABLES:
        raise ValueError(f"No es pot canviar la secció «{seccio}»")
    path = path or ruta()
    try:
        dades = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        dades = {}
    dades[seccio] = json.loads(PER_DEFECTE.read_text(encoding="utf-8"))[seccio]
    _escriu(dades, path)
    return carrega(path)[seccio]


def desa_font(nom: str, contingut: bytes, path: Path | None = None) -> dict:
    """Guarda una font pròpia a ~/.tallat/fonts i la fa servir per als subtítols."""
    origen = Path(nom).name
    if Path(origen).suffix.lower() not in FORMATS_FONT:
        raise ValueError("La font ha de ser un fitxer .ttf, .otf, .woff o .woff2")
    if not contingut:
        raise ValueError("El fitxer de la font és buit")
    FONTS.mkdir(parents=True, exist_ok=True)
    desti = FONTS / origen
    desti.write_bytes(contingut)
    familia = re.sub(r"[^\w .-]", "", Path(origen).stem)[:60] or "La meva font"
    path = path or ruta()
    try:
        dades = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        dades = {}
    dades.setdefault("subtitols", {}).update({"font": familia, "font_fitxer": str(desti)})
    _escriu(dades, path)
    return carrega(path)["subtitols"]


def fitxer_font(estil: dict) -> Path | None:
    """El fitxer de la font pròpia dels subtítols, si n'hi ha una i existeix."""
    font = estil.get("font_fitxer")
    if not font:
        return None
    path = Path(font).expanduser()
    return path if path.suffix.lower() in FORMATS_FONT and path.is_file() else None
