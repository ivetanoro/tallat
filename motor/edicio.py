"""Edició per paraules: el text que la persona esborra es converteix en talls.

La persona edita `edicio.txt` (una frase per paràgraf). Comparem les paraules que hi queden
amb les originals: les que falten s'eliminen del vídeo. Per recuperar-ne una, n'hi ha prou
de tornar-la a escriure al seu lloc (o copiar-la d'`original.txt`).
"""
from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher

MARGE = 0.04  # segons d'aire abans i després de cada tros conservat


FI_DE_FRASE = re.compile(r"[.?!…»\"]$")
PAUSA_PARAGRAF = 0.7  # segons de silenci que també obren un paràgraf nou


def text_editable(paraules: list[dict]) -> str:
    """Un paràgraf per frase: on acaba la puntuació o on hi ha una pausa llarga."""
    linies, actual, anterior = [], [], None
    for p in paraules:
        if anterior is not None and p["frase"] != anterior["frase"] and (
                FI_DE_FRASE.search(anterior["text"]) or p["inici"] - anterior["final"] >= PAUSA_PARAGRAF):
            linies.append(" ".join(actual))
            actual = []
        actual.append(p["text"])
        anterior = p
    if actual:
        linies.append(" ".join(actual))
    return "\n\n".join(linies) + "\n"


def _normalitza(paraula: str) -> str:
    p = unicodedata.normalize("NFC", paraula.lower()).replace("’", "'")
    return re.sub(r"[^\w'·-]", "", p)


def compara(paraules: list[dict], text_editat: str) -> tuple[list[dict], list[str]]:
    """Retorna (paraules amb el camp «conservada» i, si cal, «correccio»; avisos)."""
    originals = [_normalitza(p["text"]) for p in paraules]
    editades_brutes = text_editat.split()
    editades = [_normalitza(t) for t in editades_brutes]
    avisos = []
    resultat = [dict(p, conservada=False) for p in paraules]

    sm = SequenceMatcher(a=originals, b=editades, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for i in range(i1, i2):
                resultat[i]["conservada"] = True
        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            # Mateix nombre de paraules però escrites diferent: és una correcció del text.
            for k, i in enumerate(range(i1, i2)):
                resultat[i]["conservada"] = True
                resultat[i]["correccio"] = editades_brutes[j1 + k]
        elif tag in ("replace", "insert"):
            noves = " ".join(editades_brutes[j1:j2])
            avisos.append(f"No puc afegir paraules que no són a la gravació: «{noves}»")
    return resultat, avisos


def trams(paraules: list[dict], fps: float, durada: float, marge: float = MARGE) -> list[tuple[float, float]]:
    """Trossos del vídeo original que es conserven, ajustats a fotogrames sencers."""
    corregudes, actual = [], []
    for p in paraules:
        if p["conservada"]:
            actual.append(p)
        elif actual:
            corregudes.append(actual)
            actual = []
    if actual:
        corregudes.append(actual)

    per_id = {p["id"]: p for p in paraules}
    brut = []
    for c in corregudes:
        inici = c[0]["inici"] - marge
        final = c[-1]["final"] + marge
        anterior = per_id.get(c[0]["id"] - 1)
        seguent = per_id.get(c[-1]["id"] + 1)
        if anterior is not None:  # no deixem entrar el final d'una paraula esborrada
            inici = max(inici, anterior["final"])
        if seguent is not None:
            final = min(final, seguent["inici"])
        brut.append((max(0.0, inici), min(durada, final)))

    ajustats = []
    for a, b in brut:
        a = math.floor(a * fps) / fps
        b = math.ceil(b * fps) / fps
        if b - a < 1 / fps:
            continue
        if ajustats and a <= ajustats[-1][1]:
            ajustats[-1] = (ajustats[-1][0], max(ajustats[-1][1], b))
        else:
            ajustats.append((a, b))
    return [(round(a, 4), round(b, 4)) for a, b in ajustats]
