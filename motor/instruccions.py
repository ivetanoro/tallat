"""Instruccions de veu: frases que comencen per «Claude, …» dites durant la gravació.

- Es detecten a la transcripció (també quan el transcriptor ha entès «Clot», «Cloud», «Clau»…),
  però només si «Claude» obre una frase: «si Claude detecta…» no és una instrucció.
- Les paraules de la instrucció es treuen soles del vídeo (motiu «instruccio»).
- Cada instrucció queda com a proposta en el moment exacte on s'ha dit, per acceptar-la o
  descartar-la a la pàgina de revisió. Es desen a `instruccions.json`.

Tipus:
  talla    «torno a començar», «talla des d'aquí»: la presa bona comença aquí. Es proposa
           treure el primer intent (si es troba la mateixa frase abans) fins a la instrucció.
  zoom     un zoom (apropament) al tros que comença just després.
  broll    b-roll o imatges sobre el tros que ve (fase 4).
  sticker  un adhesiu (fase 4).
  altre    qualsevol altra cosa: queda apuntada.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from motor.neteja import normalitza

FITXER = "instruccions.json"
DESPERTA = {"claude", "claud", "clod", "clot", "cloud", "clau", "glod", "klaud"}
FI_DE_FRASE = re.compile(r"[.?!…]['\"»”]*$")
PAUSA_INICI = 0.6      # un silenci així abans de «Claude» també compta com a inici de frase
PAUSA_FINAL = 0.45     # la instrucció acaba en un final de frase seguit d'una pausa així
MAX_PARAULES = 45
FINESTRA_REPRESA = 180  # segons enrere on es busca el primer intent d'una frase repetida

TIPUS = [
    ("talla", ("torno a començar", "tornem a començar", "torno a fer", "comenco de nou", "començo de nou",
               "talla des d'aqui", "talla d'aqui", "talla aqui", "des d'aqui", "repeteixo", "una altra vegada")),
    ("zoom", ("zoom", "apropa", "acosta", "mes a prop", "pla curt")),
    ("sticker", ("sticker", "estiquer", "adhesiu", "estiker")),
    ("broll", ("b-roll", "broll", "be roll", "b roll", "imatge", "imatges", "video de", "clip de", "posa un pla")),
]


def _pla(text: str) -> str:
    """Text en minúscules i sense accents, per buscar-hi paraules clau."""
    t = text.lower().replace("’", "'")
    for a, b in (("à", "a"), ("è", "e"), ("é", "e"), ("í", "i"), ("ò", "o"), ("ó", "o"), ("ú", "u"),
                 ("ï", "i"), ("ü", "u"), ("ç", "c")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", re.sub(r"[^\w' -]", " ", t)).strip()


def tipus_de(text: str) -> str:
    pla = _pla(text)
    for tipus, claus in TIPUS:
        if any(_pla(c) in pla for c in claus):
            return tipus
    return "altre"


def _obre_frase(paraules: list[dict], i: int) -> bool:
    if i == 0:
        return True
    anterior = paraules[i - 1]
    return bool(FI_DE_FRASE.search(anterior["text"])) or paraules[i]["inici"] - anterior["final"] >= PAUSA_INICI


def _represa(paraules: list[dict], fi: int) -> tuple[int, int] | None:
    """Per a «torno a començar»: busca enrere el primer intent de la frase que ve després.

    Retorna el tros [primera, última] que caldria treure (des del primer intent fins just abans
    de la instrucció), o None si no es troba."""
    seguents = [normalitza(p["text"]) for p in paraules[fi + 1:fi + 8] if normalitza(p["text"])]
    if len(seguents) < 3:
        return None
    limit = paraules[fi]["inici"] - FINESTRA_REPRESA
    for llarg in (4, 3):
        objectiu = seguents[:llarg]
        for j in range(fi - llarg, -1, -1):
            if paraules[j]["inici"] < limit:
                break
            if [normalitza(p["text"]) for p in paraules[j:j + llarg]] == objectiu:
                return j, fi
    return None


def detecta(paraules: list[dict]) -> list[dict]:
    instruccions = []
    i = 0
    while i < len(paraules):
        if normalitza(paraules[i]["text"]) in DESPERTA and _obre_frase(paraules, i):
            fi = i
            while fi + 1 < len(paraules) and fi - i < MAX_PARAULES:
                actual, seguent = paraules[fi], paraules[fi + 1]
                if FI_DE_FRASE.search(actual["text"]) and seguent["inici"] - actual["final"] >= PAUSA_FINAL:
                    break
                fi += 1
            text = " ".join(p["text"] for p in paraules[i + 1:fi + 1]).strip(" ,")
            tipus = tipus_de(text)
            ancora = fi + 1 if fi + 1 < len(paraules) else None
            ins = {"id": f"i{paraules[i]['id']}", "tipus": tipus, "text": text,
                   "paraules": [paraules[i]["id"], paraules[fi]["id"]],
                   "inici": paraules[i]["inici"], "final": paraules[fi]["final"],
                   "ancora": paraules[ancora]["id"] if ancora is not None else None,
                   "estat": "pendent"}
            if tipus == "talla":
                tros = _represa(paraules, fi)
                if tros:  # treiem des del primer intent fins just abans de «Claude»
                    ins["treure"] = [paraules[tros[0]]["id"], paraules[i - 1]["id"]] if i > tros[0] else None
            instruccions.append(ins)
            i = fi + 1
        else:
            i += 1
    return instruccions


def llegeix(carpeta: Path) -> list[dict]:
    path = carpeta / FITXER
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def desa(carpeta: Path, instruccions: list[dict]) -> None:
    (carpeta / FITXER).write_text(json.dumps(instruccions, ensure_ascii=False, indent=1), encoding="utf-8")


def aplica_a_estat(estat: dict, instruccions: list[dict]) -> dict:
    """Treu del vídeo les paraules de cada instrucció (es poden recuperar)."""
    for ins in instruccions:
        a, b = ins["paraules"]
        for pid in range(a, b + 1):
            if pid not in estat["mantingudes"] and pid not in estat["esborrades"]:
                estat["esborrades"][pid] = "instruccio"
    return estat


def fusiona(noves: list[dict], velles: list[dict]) -> list[dict]:
    """En tornar a detectar, conserva les decisions ja preses (acceptada/descartada)."""
    per_id = {v["id"]: v for v in velles}
    for n in noves:
        if n["id"] in per_id:
            n["estat"] = per_id[n["id"]].get("estat", "pendent")
    return noves
