"""Stickers: imatges (PNG amb fons transparent) que apareixen animades un moment.

Com el b-roll, tallat no depèn de cap IA: la persona té la seva biblioteca a
`~/.tallat/stickers/`, en puja des de la pàgina de revisió o, si té una IA d'imatges
connectada a Claude, Claude n'hi genera un i el registra amb `tallat.py sticker`.
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path

BIBLIOTECA = Path.home() / ".tallat" / "stickers"
CARPETA = "stickers"  # dins del projecte (al costat d'instruccions.json)
FORMATS = {".png", ".webp", ".gif", ".svg"}


def es_compatible(path: Path) -> bool:
    return path.suffix.lower() in FORMATS


def biblioteca() -> list[Path]:
    BIBLIOTECA.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in BIBLIOTECA.iterdir() if p.is_file() and es_compatible(p))


def _pla(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def suggereix(text: str) -> Path | None:
    """El sticker de la biblioteca el nom del qual surt a la instrucció («sticker d'un cor» → cor.png)."""
    paraules = set(_pla(text).split())
    for p in biblioteca():
        nom = _pla(p.stem)
        if nom and (nom in paraules or nom in _pla(text)):
            return p
    return None


def copia(origen: Path, carpeta: Path, nom: str) -> Path:
    desti = carpeta / CARPETA / f"{nom}{origen.suffix.lower()}"
    desti.parent.mkdir(parents=True, exist_ok=True)
    for vell in desti.parent.glob(f"{nom}.*"):  # si se'n canvia el format, no en deixem dos
        if vell != desti:
            vell.unlink()
    if origen.resolve() != desti.resolve():
        shutil.copy(origen, desti)
    return desti
