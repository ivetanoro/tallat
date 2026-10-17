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
COMA = ","  # marca d'una expressió que només compta si va seguida de coma


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


def _clau(expressio: str) -> tuple[str, ...]:
    """Com es compara una expressió de la llista. Amb una coma al final («bé,») és una altra entrada que
    «bé»: només compta si la paraula va seguida de coma. La mateixa clau serveix per carregar, buscar,
    moure i desfer (revisió de Codex: abans, desfer un canvi de «bé» esborrava «bé,»)."""
    expressio = expressio.strip()
    amb_coma = expressio.endswith(",")
    return tuple(normalitza(t) for t in expressio.rstrip(",").split()) + ((COMA,) if amb_coma else ())


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
            seccions[actual].append(_clau(linia))  # amb coma: només si va seguida de coma (config/farciment.txt)
    return seccions


FI_DE_FRASE = re.compile(r"[.?!…]$")
PAUSA_DINS_EXPRESSIO = 0.6  # segons: «o … sigui» amb més silenci entremig ja no és una expressió


def detecta(paraules: list[dict], llista: dict) -> tuple[dict[int, str], dict[int, str]]:
    """Retorna (treure, proposar) com a {id de paraula: motiu}."""
    norm = [normalitza(p["text"]) for p in paraules]
    treure: dict[int, str] = {}
    proposar: dict[int, str] = {}

    def seguides(i: int, j: int) -> bool:
        """Les paraules i..j es diuen de seguida: dins de la mateixa frase i sense una pausa llarga.
        (Revisió de Codex: «o» al final d'una frase i «sigui» deu segons després es proposaven com «o sigui».)"""
        for k in range(i, j):
            a, b = paraules[k], paraules[k + 1]
            if FI_DE_FRASE.search(a["text"].rstrip("»\"'")):
                return False
            if a.get("final") is not None and b.get("inici") is not None and b["inici"] - a["final"] > PAUSA_DINS_EXPRESSIO:
                return False
        return True

    def coincidencies(expressions):
        for expr in sorted(expressions, key=len, reverse=True):
            amb_coma = bool(expr) and expr[-1] == COMA
            expr = expr[:-1] if amb_coma else expr
            n = len(expr)
            for i in range(len(norm) - n + 1):
                if tuple(norm[i:i + n]) != expr or (n > 1 and not seguides(i, i + n - 1)):
                    continue
                if amb_coma and not paraules[i + n - 1]["text"].rstrip().endswith(","):
                    continue
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
