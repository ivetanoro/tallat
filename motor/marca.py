"""Estil de marca de cada persona.

tallat porta un estil neutre (config/brand.example.json). La còpia personal és a
~/.tallat/brand.json, fora del repositori: es crea el primer cop i es pot editar.
Els valors que hi faltin es prenen de l'estil neutre.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

PER_DEFECTE = Path(__file__).resolve().parent.parent / "config" / "brand.example.json"
USUARI = Path.home() / ".tallat" / "brand.json"


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
