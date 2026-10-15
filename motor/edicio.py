"""Edició per paraules: quines paraules es queden, quines es treuen i per què.

L'estat de l'edició es desa a `edicio.json`:
  esborrades   {id: motiu}   motiu = «usuari», «farciment», «tall», «muntatge» (fora del reel)
                             o «instruccio» (instrucció de veu)
  propostes    {id: motiu}   suggeriments que encara no s'han aplicat
  mantingudes  [id]          paraules que la persona ha recuperat (la neteja no les torna a treure)
  correccions  {id: text}    text corregit per als subtítols (no talla res)
  pausa_maxima segons        els silencis més llargs s'escurcen fins aquí (null = no es toquen)
  pauses_mantingudes [id]    silencis que es deixen sencers (id de la paraula que ve després)
  revisio      n             puja a cada canvi desat (evita que dues pestanyes es trepitgin)
  subtitols    bool          si els renders porten subtítols
  ordre        [[a, b]]      (reels muntats) trossos d'ids en l'ordre en què han de sonar
  zooms        [id]          paraules on comença un zoom (instruccions de veu acceptades)
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

MARGE = 0.04          # segons d'aire abans i després de cada tros conservat
MAXIM_ALLARGA = 1.5   # com a molt, l'última paraula s'allarga això si la veu continua
PAUSA_MAXIMA = 0.35   # segons: els silencis entre paraules no duraran més que això
FI_DE_FRASE = re.compile(r"[.?!…»\"]$")
PAUSA_PARAGRAF = 0.7  # segons de silenci que també obren un paràgraf nou


def estat_buit(pausa_maxima: float | None = PAUSA_MAXIMA) -> dict:
    return {"versio": 1, "revisio": 0, "esborrades": {}, "propostes": {}, "mantingudes": [],
            "correccions": {}, "pausa_maxima": pausa_maxima, "pauses_mantingudes": [],
            "subtitols": True, "ordre": None, "zooms": [], "destacades": {}, "titol": None}


def titol_net(titol) -> dict | None:
    """El títol del ganxo d'un vídeo, comprovat: {text, durada (o None: la del kit)}; None si no n'hi ha."""
    if not isinstance(titol, dict) or not isinstance(titol.get("text"), str) or not titol["text"].strip():
        return None
    text = "\n".join(l.strip() for l in titol["text"].replace("\r", "").split("\n"))[:400].strip()
    durada = titol.get("durada")
    durada = min(10.0, max(0.5, float(durada))) if isinstance(durada, (int, float)) and not isinstance(durada, bool) else None
    return {"text": text, "durada": durada}


def llegeix_estat(path: Path) -> dict:
    estat = estat_buit()
    if path.exists():
        estat.update(json.loads(path.read_text(encoding="utf-8")))
    # Les claus JSON són text; internament fem servir enters.
    for clau in ("esborrades", "propostes", "correccions", "destacades"):
        estat[clau] = {int(k): v for k, v in estat[clau].items()}
    estat["mantingudes"] = [int(i) for i in estat["mantingudes"]]
    estat["pauses_mantingudes"] = [int(i) for i in estat["pauses_mantingudes"]]
    return estat


def desa_estat(estat: dict, path: Path) -> None:
    sortida = dict(estat)
    for clau in ("esborrades", "propostes", "correccions", "destacades"):
        sortida[clau] = {str(k): v for k, v in sorted(estat[clau].items())}
    sortida["mantingudes"] = sorted(set(estat["mantingudes"]))
    sortida["pauses_mantingudes"] = sorted(set(estat["pauses_mantingudes"]))
    path.write_text(json.dumps(sortida, ensure_ascii=False, indent=1), encoding="utf-8")


MOTIUS_NETEJA = {"farciment", "tall"}  # els únics que la neteja pot treure i tornar a posar


def aplica_neteja(estat: dict, treure: dict[int, str], proposar: dict[int, str]) -> dict:
    """Afegeix el que ha trobat la neteja sense trepitjar cap altra decisió.

    Es mantenen les paraules tretes per la persona, pel primer muntatge o per una
    instrucció de veu; només es refà el que havia tret la neteja mateixa."""
    respectar = set(estat["mantingudes"]) | {i for i, m in estat["esborrades"].items() if m not in MOTIUS_NETEJA}
    estat["esborrades"] = {i: m for i, m in estat["esborrades"].items() if m not in MOTIUS_NETEJA}
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
        if p["id"] in estat.get("destacades", {}):  # destacada als subtítols (true) o no (false), triat a mà
            q["destacada"] = bool(estat["destacades"][p["id"]])
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

def _blocs(paraules: list[dict], ordre) -> list[list[dict]]:
    """Agrupa les paraules en blocs que sonen en l'ordre indicat (per a reels muntats).

    Sense `ordre`, tot és un sol bloc en l'ordre de la gravació. Amb `ordre` (llista de
    trossos [primera, última] d'ids), cada tros és un bloc. Si s'ha recuperat una paraula
    de fora de tots els trossos, s'afegeix al bloc que la precedeix a la gravació."""
    if not ordre:
        return [paraules]
    rangs = [(int(a), int(b)) for a, b in ordre]
    blocs: list[list[dict]] = [[] for _ in rangs]
    for p in paraules:
        i = p["id"]
        k = next((n for n, (a, b) in enumerate(rangs) if a <= i <= b), None)
        if k is None:
            if not p["conservada"]:
                continue
            anteriors = [n for n, (a, b) in enumerate(rangs) if b < i]
            k = (max(anteriors, key=lambda n: rangs[n][1]) if anteriors
                 else min(range(len(rangs)), key=lambda n: rangs[n][0]))
        blocs[k].append(p)
    for b in blocs:
        b.sort(key=lambda p: p["id"])
    return blocs


def trams(paraules: list[dict], fps: float, durada: float, marge: float = MARGE,
          pausa_maxima: float | None = None, pauses_mantingudes=(), ordre=None,
          veu=None) -> list[tuple[float, float]]:
    """Trossos del vídeo original que es conserven, en l'ordre en què sonen, ajustats a fotogrames.

    `veu` (opcional) és el mapa de veu del so (motor/veu.py): si hi és, un silenci entre dues
    paraules només s'escurça si al so hi ha prou silenci de debò, i es talla dins d'aquest silenci."""
    from motor.veu import fi_de_la_veu, inici_de_la_veu, silenci_mes_llarg
    pauses_mantingudes = set(pauses_mantingudes)

    def silenci_real(anterior: dict, p: dict):
        """(inici, final) del silenci on es pot tallar entre dues paraules, o None si no se'n pot treure."""
        if veu is None:
            return anterior["final"], p["inici"]
        tros = silenci_mes_llarg(veu, anterior["final"], p["inici"])
        return tros if tros and tros[1] - tros[0] > pausa_maxima else None
    corregudes = []
    for bloc in _blocs(paraules, ordre):
        actual = []
        for p in bloc:
            if p["conservada"]:
                salt = actual and p["id"] != actual[-1]["id"] + 1  # hi ha paraules entremig que no hi són
                silenci = (actual and pausa_maxima is not None and p["id"] not in pauses_mantingudes
                           and p["inici"] - actual[-1]["final"] > pausa_maxima
                           and silenci_real(actual[-1], p) is not None)
                if salt or silenci:  # silenci massa llarg: el partim
                    corregudes.append(actual)
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
        tanca_inici = tanca_final = False  # el costat toca una paraula esborrada
        if anterior is not None:
            if anterior["conservada"] and pausa_maxima is not None:
                # tall per silenci: deixem mitja pausa a cada costat, dins del silenci de debò
                tros = silenci_real(anterior, c[0]) or (anterior["final"], c[0]["inici"])
                inici = max(min(inici, tros[1] - pausa_maxima / 2), anterior["final"])
            elif anterior["conservada"]:
                inici = max(inici, anterior["final"])
            else:                       # no deixem entrar el final d'una paraula esborrada
                if veu is not None:     # però sí el principi real de la nostra (l'alineador s'equivoca)
                    real = inici_de_la_veu(veu, anterior["final"], c[0]["inici"])
                    if real is not None and real < inici:
                        inici = real - marge / 2
                inici = max(inici, anterior["final"])
                tanca_inici = True
        if seguent is not None:
            if seguent["conservada"] and pausa_maxima is not None:
                tros = silenci_real(c[-1], seguent) or (c[-1]["final"], seguent["inici"])
                final = min(max(final, tros[0] + pausa_maxima / 2), seguent["inici"])
            elif seguent["conservada"]:
                final = min(final, seguent["inici"])
            else:
                if veu is not None:     # allarguem fins on acaba la veu de debò, si hi ha silenci abans de la treta
                    real = fi_de_la_veu(veu, c[-1]["final"], seguent["inici"])
                    if real is not None and real > final:
                        final = real + marge / 2
                final = min(final, seguent["inici"])
                tanca_final = True
        elif veu is not None:  # l'última paraula de la gravació: també pot acabar més tard del que diu l'alineador
            real = fi_de_la_veu(veu, c[-1]["final"], min(durada, c[-1]["final"] + MAXIM_ALLARGA))
            if real is not None and real > final:
                final = real + marge / 2
        brut.append((max(0.0, inici), min(durada, final), tanca_inici, tanca_final))

    # Ajustem a fotogrames sencers. Al costat d'una paraula esborrada arrodonim cap endins,
    # perquè no se'n coli ni un fotograma (una «s» de 30 ms ja se sent).
    # Es compta en fotogrames enters: en decimals, «13/30 − 12/30» dona una mica menys d'un
    # fotograma i una paraula d'un sol fotograma desapareixia.
    ajustats = []
    for a, b, tanca_a, tanca_b in brut:
        fa = math.ceil(a * fps - 1e-6) if tanca_a else math.floor(a * fps + 1e-6)
        fb = math.floor(b * fps + 1e-6) if tanca_b else math.ceil(b * fps - 1e-6)
        if fb - fa < 1:  # una paraula més curta que un fotograma: millor un bocí de més que perdre-la
            fa, fb = math.floor(a * fps + 1e-6), math.ceil(b * fps - 1e-6)
        if fb - fa < 1:
            continue
        if ajustats and ajustats[-1][0] <= fa <= ajustats[-1][1]:  # continuació directa: un sol tros
            ajustats[-1] = (ajustats[-1][0], max(ajustats[-1][1], fb))
        else:
            ajustats.append((fa, fb))
    return [(round(fa / fps, 4), round(fb / fps, 4)) for fa, fb in ajustats]
