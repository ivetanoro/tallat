"""Les paraules d'una transcripció: el farciment («eh», «o sigui»), les paraules a mitges i les repetides.

Ho fan servir tallat i matcha. Res no s'esborra: es torna quines paraules es treuen soles i quines es
proposen, amb el motiu, i cada eina decideix què en fa.
- «farciment»: sons de dubte de la secció [treu] → es treuen sols.
- «tall»: paraules a mig dir («experè--») → es treuen soles.
- «farciment?», «repeticio?» i «expressiu?»: només es proposen.

Una paraula és un dict amb `id` i `text`, i el temps a `inici`/`final` (tallat) o a `t`/`fi` (matcha).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

FARCIMENT = Path(__file__).resolve().parent / "farciment"  # ca.txt, es.txt, en.txt
COMA = ","  # marca d'una expressió que només compta si va seguida de coma
FI_DE_FRASE = re.compile(r"[.?!…]$")
PAUSA_DINS_EXPRESSIO = 0.6  # segons: «o … sigui» amb més silenci entremig ja no és una expressió


def llista_per_defecte(idioma: str = "ca") -> Path | None:
    """La llista de farciment de fàbrica d'un idioma, si n'hi ha."""
    p = FARCIMENT / f"{idioma}.txt"
    return p if p.is_file() else None


def normalitza(paraula: str) -> str:
    p = unicodedata.normalize("NFC", paraula.lower()).replace("’", "'")
    p = re.sub(r"[^\w'·-]", "", p).strip("-")
    return re.sub(r"(.)\1+", r"\1", p)  # «mmmm» → «m», «síí» → «sí»


def clau(expressio: str) -> tuple[str, ...]:
    """Com es compara una expressió de la llista. Amb una coma al final («bé,») és una altra entrada que
    «bé»: només compta si la paraula va seguida de coma."""
    expressio = expressio.strip()
    amb_coma = expressio.endswith(",")
    return tuple(normalitza(t) for t in expressio.rstrip(",").split()) + ((COMA,) if amb_coma else ())


def carrega_llista(path: Path) -> dict[str, list[tuple[str, ...]]]:
    """{treu: [...], proposa: [...]} d'un fitxer de farciment (seccions [treu] i [proposa], # per als comentaris)."""
    seccions: dict[str, list[tuple[str, ...]]] = {"treu": [], "proposa": []}
    actual = None
    for linia in Path(path).read_text(encoding="utf-8").splitlines():
        linia = linia.strip()
        if not linia or linia.startswith("#"):
            continue
        m = re.fullmatch(r"\[(\w+)\]", linia)
        if m:
            actual = m.group(1)
            continue
        if actual in seccions:
            seccions[actual].append(clau(linia))
    return seccions


def _temps(p: dict, inici: bool) -> float | None:
    v = p.get("inici", p.get("t")) if inici else p.get("final", p.get("fi"))
    return v if isinstance(v, (int, float)) else None


def detecta(paraules: list[dict], llista: dict | None) -> tuple[dict[int, str], dict[int, str]]:
    """(treure, proposar) com a {id de paraula: motiu}. Sense llista (un idioma sense llista), només els talls
    i les repeticions."""
    norm = [normalitza(p["text"]) for p in paraules]
    treure: dict[int, str] = {}
    proposar: dict[int, str] = {}

    def seguides(i: int, j: int) -> bool:
        """Les paraules i..j es diuen de seguida: dins de la mateixa frase i sense una pausa llarga."""
        for k in range(i, j):
            a, b = paraules[k], paraules[k + 1]
            if FI_DE_FRASE.search(a["text"].rstrip("»\"'")):
                return False
            fi, ini = _temps(a, False), _temps(b, True)
            if fi is not None and ini is not None and ini - fi > PAUSA_DINS_EXPRESSIO:
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

    if llista:
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
    for p in paraules:
        if p["text"].rstrip(",.…").endswith("--"):
            treure[p["id"]] = "tall"
    # Una paraula dita dues vegades seguides («la, la teta»): es proposa treure la primera.
    # Tres o més repeticions solen ser expressives («tu, tu, tu…») i es deixen.
    for i in range(len(norm) - 1):
        if not norm[i] or norm[i] != norm[i + 1]:
            continue
        if (i > 0 and norm[i - 1] == norm[i]) or (i + 2 < len(norm) and norm[i + 2] == norm[i]):
            continue
        if paraules[i]["id"] not in treure:
            proposar.setdefault(paraules[i]["id"], "repeticio?")
    return treure, proposar
