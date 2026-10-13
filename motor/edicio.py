"""Edició per paraules: quines paraules es queden, quines es treuen i per què.

L'estat de l'edició es desa a `edicio.json`:
  esborrades   {id: motiu}   motiu = «usuari», «farciment» o «tall»
  propostes    {id: motiu}   suggeriments que encara no s'han aplicat
  mantingudes  [id]          paraules que la persona ha recuperat (la neteja no les torna a treure)
  correccions  {id: text}    text corregit per als subtítols (no talla res)
  pausa_maxima segons        els silencis més llargs s'escurcen fins aquí (null = no es toquen)
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

MARGE = 0.04          # segons d'aire abans i després de cada tros conservat
PAUSA_MAXIMA = 0.35   # segons: els silencis entre paraules no duraran més que això
FI_DE_FRASE = re.compile(r"[.?!…»\"]$")
PAUSA_PARAGRAF = 0.7  # segons de silenci que també obren un paràgraf nou


def estat_buit() -> dict:
    return {"versio": 1, "esborrades": {}, "propostes": {}, "mantingudes": [],
            "correccions": {}, "pausa_maxima": PAUSA_MAXIMA}


def llegeix_estat(path: Path) -> dict:
    estat = estat_buit()
    if path.exists():
        estat.update(json.loads(path.read_text(encoding="utf-8")))
    # Les claus JSON són text; internament fem servir enters.
    for clau in ("esborrades", "propostes", "correccions"):
        estat[clau] = {int(k): v for k, v in estat[clau].items()}
    estat["mantingudes"] = [int(i) for i in estat["mantingudes"]]
    return estat


def desa_estat(estat: dict, path: Path) -> None:
    sortida = dict(estat)
    for clau in ("esborrades", "propostes", "correccions"):
        sortida[clau] = {str(k): v for k, v in sorted(estat[clau].items())}
    sortida["mantingudes"] = sorted(set(estat["mantingudes"]))
    path.write_text(json.dumps(sortida, ensure_ascii=False, indent=1), encoding="utf-8")


def aplica_neteja(estat: dict, treure: dict[int, str], proposar: dict[int, str]) -> dict:
    """Afegeix el que ha trobat la neteja sense trepitjar decisions de la persona."""
    respectar = set(estat["mantingudes"]) | {i for i, m in estat["esborrades"].items() if m == "usuari"}
    estat["esborrades"] = {i: m for i, m in estat["esborrades"].items() if m == "usuari"}
    for i, motiu in treure.items():
        if i not in respectar:
            estat["esborrades"][i] = motiu
    estat["propostes"] = {i: m for i, m in proposar.items()
                          if i not in respectar and i not in estat["esborrades"]}
    return estat


def aplica(paraules: list[dict], estat: dict) -> list[dict]:
    resultat = []
    for p in paraules:
        q = dict(p, conservada=p["id"] not in estat["esborrades"])
        if p["id"] in estat["esborrades"]:
            q["motiu"] = estat["esborrades"][p["id"]]
        if p["id"] in estat["propostes"]:
            q["proposta"] = estat["propostes"][p["id"]]
        if p["id"] in estat["correccions"]:
            q["correccio"] = estat["correccions"][p["id"]]
        resultat.append(q)
    return resultat


# --- Text --------------------------------------------------------------------

def paragrafs(paraules: list[dict]) -> list[list[dict]]:
    """Agrupa les paraules en paràgrafs: on acaba la frase o on hi ha una pausa llarga."""
    grups, actual, anterior = [], [], None
    for p in paraules:
        if anterior is not None and p["frase"] != anterior["frase"] and (
                FI_DE_FRASE.search(anterior["text"]) or p["inici"] - anterior["final"] >= PAUSA_PARAGRAF):
            grups.append(actual)
            actual = []
        actual.append(p)
        anterior = p
    if actual:
        grups.append(actual)
    return grups


def text_editable(paraules: list[dict]) -> str:
    return "\n\n".join(" ".join(p["text"] for p in g) for g in paragrafs(paraules)) + "\n"


def text_revisio(paraules: list[dict]) -> str:
    """Text llegible amb el que es treu entre [claudàtors] i el que es proposa entre {claus}."""
    def marca(p):
        if not p["conservada"]:
            return f"[{p['text']}]"
        if p.get("proposta"):
            return "{" + p["text"] + "}"
        return p.get("correccio", p["text"])
    return "\n\n".join(" ".join(marca(p) for p in g) for g in paragrafs(paraules)) + "\n"


def _normalitza(paraula: str) -> str:
    p = unicodedata.normalize("NFC", paraula.lower()).replace("’", "'")
    return re.sub(r"[^\w'·-]", "", p)


def compara(paraules: list[dict], text_editat: str) -> tuple[list[dict], list[str]]:
    """Compara un text editat amb les paraules originals (per importar edicio.txt).

    Retorna (paraules amb «conservada» i, si cal, «correccio»; avisos)."""
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


def importa_text(paraules: list[dict], text_editat: str) -> tuple[dict, list[str]]:
    """Converteix un edicio.txt antic en un estat d'edició."""
    resultat, avisos = compara(paraules, text_editat)
    estat = estat_buit()
    estat["pausa_maxima"] = None  # el text antic no escurçava silencis
    for p in resultat:
        if not p["conservada"]:
            estat["esborrades"][p["id"]] = "usuari"
        if "correccio" in p:
            estat["correccions"][p["id"]] = p["correccio"]
    return estat, avisos


# --- Talls -------------------------------------------------------------------

def trams(paraules: list[dict], fps: float, durada: float, marge: float = MARGE,
          pausa_maxima: float | None = None) -> list[tuple[float, float]]:
    """Trossos del vídeo original que es conserven, ajustats a fotogrames sencers."""
    corregudes, actual = [], []
    for p in paraules:
        if p["conservada"]:
            if actual and pausa_maxima is not None and p["inici"] - actual[-1]["final"] > pausa_maxima:
                corregudes.append(actual)  # silenci massa llarg: el partim
                actual = []
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
        if anterior is not None:
            if anterior["conservada"]:  # tall per silenci: deixem mitja pausa a cada costat
                inici = max(inici - pausa_maxima / 2 + marge, anterior["final"])
            else:                       # no deixem entrar el final d'una paraula esborrada
                inici = max(inici, anterior["final"])
        if seguent is not None:
            if seguent["conservada"]:
                final = min(final + pausa_maxima / 2 - marge, seguent["inici"])
            else:
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
