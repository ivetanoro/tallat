"""Neteja automàtica: farciment, frases tallades i repeticions.

Res no s'esborra del tot: cada paraula treta porta el seu motiu i es pot recuperar.
- «farciment»: sons de dubte de la secció [treu] → es treuen sols.
- «tall»: paraules a mig dir («experè--») → es treuen soles.
- «farciment?» i «repeticio?»: només es proposen.
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path

LLISTA_PER_DEFECTE = Path(__file__).resolve().parent.parent / "config" / "farciment.txt"
LLISTA_USUARI = Path.home() / ".tallat" / "farciment.txt"


def normalitza(paraula: str) -> str:
    p = unicodedata.normalize("NFC", paraula.lower()).replace("’", "'")
    p = re.sub(r"[^\w'·-]", "", p).strip("-")
    return re.sub(r"(.)\1+", r"\1", p)  # «mmmm» → «m», «síí» → «sí»


def ruta_llista() -> Path:
    """La còpia de l'usuari (es crea el primer cop a partir de la llista per defecte)."""
    if not LLISTA_USUARI.exists():
        LLISTA_USUARI.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(LLISTA_PER_DEFECTE, LLISTA_USUARI)
    return LLISTA_USUARI


def carrega_llista(path: Path | None = None) -> dict[str, list[tuple[str, ...]]]:
    seccions: dict[str, list[tuple[str, ...]]] = {"treu": [], "proposa": []}
    actual = None
    for linia in (path or ruta_llista()).read_text(encoding="utf-8").splitlines():
        linia = linia.strip()
        if not linia or linia.startswith("#"):
            continue
        m = re.fullmatch(r"\[(\w+)\]", linia)
        if m:
            actual = m.group(1)
            continue
        if actual in seccions:
            seccions[actual].append(tuple(normalitza(t) for t in linia.split()))
    return seccions


def detecta(paraules: list[dict], llista: dict) -> tuple[dict[int, str], dict[int, str]]:
    """Retorna (treure, proposar) com a {id de paraula: motiu}."""
    norm = [normalitza(p["text"]) for p in paraules]
    treure: dict[int, str] = {}
    proposar: dict[int, str] = {}

    def coincidencies(expressions):
        for expr in sorted(expressions, key=len, reverse=True):
            n = len(expr)
            for i in range(len(norm) - n + 1):
                if tuple(norm[i:i + n]) == expr:
                    yield range(i, i + n)

    def dins_de_ratxa(i: int) -> bool:
        """Tres o més sons iguals seguits («uh, uh, uh») solen ser expressius, no dubtes."""
        j, k = i, i
        while j > 0 and norm[j - 1] == norm[i]:
            j -= 1
        while k + 1 < len(norm) and norm[k + 1] == norm[i]:
            k += 1
        return k - j + 1 >= 3

    for rang in coincidencies(llista["treu"]):
        for i in rang:
            if dins_de_ratxa(i):
                proposar.setdefault(paraules[i]["id"], "expressiu?")
            else:
                treure.setdefault(paraules[i]["id"], "farciment")
    for rang in coincidencies(llista["proposa"]):
        for i in rang:
            if paraules[i]["id"] not in treure:
                proposar.setdefault(paraules[i]["id"], "farciment?")

    for i, p in enumerate(paraules):
        if p["text"].rstrip(",.…").endswith("--"):
            treure[p["id"]] = "tall"

    # Una paraula dita dues vegades seguides («la, la teta»): proposem treure la primera.
    # Tres o més repeticions solen ser expressives («tu, tu, tu…») i es deixen.
    for i in range(len(norm) - 1):
        if not norm[i] or norm[i] != norm[i + 1]:
            continue
        if (i > 0 and norm[i - 1] == norm[i]) or (i + 2 < len(norm) and norm[i + 2] == norm[i]):
            continue
        pid = paraules[i]["id"]
        if pid not in treure:
            proposar.setdefault(pid, "repeticio?")
    return treure, proposar
