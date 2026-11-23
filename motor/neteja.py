"""Neteja automàtica: farciment, frases tallades i repeticions.

Res no s'esborra del tot: cada paraula treta porta el seu motiu i es pot recuperar.
- «farciment»: sons de dubte de la secció [treu] → es treuen sols.
- «tall»: paraules a mig dir («experè--») → es treuen soles.
- «farciment?» i «repeticio?»: només es proposen.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from motor.nucli import paraules as nucli_paraules  # la detecció la comparteixen tallat i matcha

LLISTA_PER_DEFECTE = nucli_paraules.llista_per_defecte("ca")
LLISTA_USUARI = Path.home() / ".tallat" / "farciment.txt"
COMA = nucli_paraules.COMA  # marca d'una expressió que només compta si va seguida de coma
normalitza = nucli_paraules.normalitza
_clau = nucli_paraules.clau
FI_DE_FRASE = nucli_paraules.FI_DE_FRASE
PAUSA_DINS_EXPRESSIO = nucli_paraules.PAUSA_DINS_EXPRESSIO


def ruta_llista() -> Path:
    """La còpia de l'usuari (es crea el primer cop a partir de la llista per defecte)."""
    if not LLISTA_USUARI.exists():
        LLISTA_USUARI.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(LLISTA_PER_DEFECTE, LLISTA_USUARI)
    return LLISTA_USUARI


def seccio_de(expressio: str, path: Path | None = None) -> str | None:
    """«treu», «proposa» o None (si l'expressió no és a la llista)."""
    llista = carrega_llista(path)
    return next((s for s, expressions in llista.items() if _clau(expressio) in expressions), None)


def mou_expressio(expressio: str, desti: str | None, path: Path | None = None) -> None:
    """Posa una expressió a [treu] o a [proposa], o la treu de la llista (desti None).

    Es fa sobre la còpia de l'usuari i en conserva els comentaris."""
    if desti not in (None, "treu", "proposa"):
        raise ValueError(f"Secció de farciment desconeguda: {desti}")
    expressio = " ".join(expressio.lower().split())
    if not _clau(expressio) or not all(_clau(expressio)):
        raise ValueError("Cal una paraula o expressió")
    path = path or ruta_llista()
    sortida, seccio, final_de = [], None, {}
    for linia in path.read_text(encoding="utf-8").splitlines():
        net = linia.strip()
        capcalera = re.fullmatch(r"\[(\w+)\]", net)
        if capcalera:
            seccio = capcalera.group(1)
        elif net and not net.startswith("#") and _clau(net) == _clau(expressio):
            continue  # la traiem d'on sigui
        sortida.append(linia)
        if seccio and (capcalera or (net and not net.startswith("#"))):
            final_de[seccio] = len(sortida)  # on acaba el contingut de cada secció
    if desti:
        if desti not in final_de:
            sortida += ["", f"[{desti}]"]
            final_de[desti] = len(sortida)
        sortida.insert(final_de[desti], expressio)
    path.write_text("\n".join(sortida) + "\n", encoding="utf-8")


def carrega_llista(path: Path | None = None) -> dict[str, list[tuple[str, ...]]]:
    return nucli_paraules.carrega_llista(path or ruta_llista())


def detecta(paraules: list[dict], llista: dict) -> tuple[dict[int, str], dict[int, str]]:
    """Retorna (treure, proposar) com a {id de paraula: motiu} (vegeu motor/nucli/paraules.py)."""
    return nucli_paraules.detecta(paraules, llista)
