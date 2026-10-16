"""Instruccions de veu: frases que comencen per «Claude, …» o «tallat, …» dites durant la gravació.

- Es detecten a la transcripció (també quan el transcriptor ha entès «Clot», «Cloud», «Clau»…),
  però només si la paraula obre una frase: «si Claude detecta…» no és una instrucció.
- «tallat» (i «Codex») també serveixen, perquè no tothom fa servir Claude. Com que «tallat» és una
  paraula normal («un tallat, si us plau»), amb aquestes només compta si la frase és una ordre
  coneguda (torno a començar, zoom, b-roll, sticker). Igual amb «Clau», «Clot» i «Cloud».
- Les paraules de la instrucció es treuen soles del vídeo (motiu «instruccio»).
- Cada instrucció queda com a proposta en el moment exacte on s'ha dit, per acceptar-la o
  descartar-la a la pàgina de revisió. Es desen a `instruccions.json`.
- Si la persona s'oblida de dir «Claude» (o el transcriptor no l'entén: «Mira», «Llavors»), una
  segona passada busca frases curtes que comencen amb una ordre clara («sticker de…», «b-roll…»,
  «tallem…», «torno a començar»). Aquestes queden com a dubtoses (`sense_paraula`): no es treu res
  del vídeo fins que la persona les accepta.

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
# Passades per normalitza(), com les paraules de la transcripció (que, per exemple, fa «tallat» → «talat»).
DESPERTA = {normalitza(w) for w in ("claude", "claud", "clod", "glod", "klaud")}
# Aquestes també són paraules normals («Clau per entendre-ho…», «un tallat»): només amb una ordre coneguda.
DESPERTA_AMB_ORDRE = {normalitza(w) for w in ("tallat", "tayat", "codex", "còdex", "códex", "codecs",
                                               "clau", "clot", "cloud")}
FI_DE_FRASE = re.compile(r"[.?!…]['\"»”]*$")
PAUSA_INICI = 0.6      # un silenci així abans de «Claude» també compta com a inici de frase
PAUSA_SENSE_PUNT = 1.0  # sense puntuació, la instrucció acaba en un silenci així
MAX_PARAULES = 25       # les instruccions són curtes: si no se'n troba el final abans, és dubtosa
FINESTRA_REPRESA = 180  # segons enrere on es busca el primer intent d'una frase repetida

TIPUS = [
    ("talla", ("torno a començar", "tornem a començar", "torno a fer", "comenco de nou", "començo de nou",
               "talla des d'aqui", "talla d'aqui", "talla aqui", "des d'aqui", "repeteixo", "una altra vegada",
               "tallem", "talla abans")),
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


# Sense «Claude»: només les ordres que gairebé mai no surten parlant d'una altra cosa, i al començament
# de la frase (a les primeres paraules: «Mira, un sticker d'un mosquit»).
ORDRES_SENSE_PARAULA = ("sticker", "estiquer", "estiker", "b-roll", "broll", "be roll", "b roll",
                        "tallem", "talla aqui", "talla d'aqui", "talla des d'aqui", "torno a començar",
                        "tornem a començar", "començo de nou", "comenco de nou", "fes zoom", "fes un zoom",
                        "posa un zoom")
PRIMERES_PARAULES = 5


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


def _frases(paraules: list[dict]):
    """Les frases de la transcripció: (primera, última), pels finals de frase o els silencis llargs."""
    inici = 0
    for k in range(len(paraules)):
        final = k + 1 >= len(paraules) or FI_DE_FRASE.search(paraules[k]["text"]) \
            or paraules[k + 1]["inici"] - paraules[k]["final"] >= PAUSA_SENSE_PUNT
        if final:
            yield inici, k
            inici = k + 1


def _sense_paraula(paraules: list[dict], ocupades: set[int]) -> list[dict]:
    """Les frases curtes que comencen amb una ordre però sense «Claude»: dubtoses, per decidir."""
    trobades = []
    for a, b in _frases(paraules):
        if b - a + 1 > MAX_PARAULES or any(k in ocupades for k in range(a, b + 1)):
            continue
        obertura = _pla(" ".join(p["text"] for p in paraules[a:min(b + 1, a + PRIMERES_PARAULES)]))
        if not any(re.search(rf"(^| ){re.escape(_pla(o))}( |$)", obertura) for o in ORDRES_SENSE_PARAULA):
            continue
        text = " ".join(p["text"] for p in paraules[a:b + 1]).strip(" ,")
        ancora = b + 1 if b + 1 < len(paraules) else None
        ins = {"id": f"s{paraules[a]['id']}", "tipus": tipus_de(text), "text": text,
               "paraules": [paraules[a]["id"], paraules[b]["id"]],
               "inici": paraules[a]["inici"], "final": paraules[b]["final"],
               "ancora": paraules[ancora]["id"] if ancora is not None else None,
               "estat": "pendent", "dubtosa": True, "sense_paraula": True}
        if ins["tipus"] == "talla":
            tros = _represa(paraules, b)
            if tros and a > tros[0]:
                ins["treure"] = [paraules[tros[0]]["id"], paraules[a - 1]["id"]]
        trobades.append(ins)
    return trobades


def detecta(paraules: list[dict]) -> list[dict]:
    """Les instruccions de veu: les que comencen per «Claude» (o «tallat»…) i, a part, les dubtoses
    que semblen una ordre però no en porten (vegeu _sense_paraula)."""
    instruccions = []
    i = 0
    while i < len(paraules):
        paraula = normalitza(paraules[i]["text"])
        if (paraula in DESPERTA or paraula in DESPERTA_AMB_ORDRE) and _obre_frase(paraules, i):
            # La instrucció acaba al primer final de frase («Claude, zoom aquí.») o, si el transcriptor
            # no hi ha posat puntuació, en un silenci llarg. Una pausa just després de «Claude» no compta.
            fi, clara = i, False
            while fi + 1 < len(paraules) and fi - i < MAX_PARAULES:
                actual, seguent = paraules[fi], paraules[fi + 1]
                if fi > i and (FI_DE_FRASE.search(actual["text"])
                               or seguent["inici"] - actual["final"] >= PAUSA_SENSE_PUNT):
                    clara = True
                    break
                fi += 1
            else:
                clara = fi + 1 >= len(paraules)  # s'ha acabat la gravació: també és un final clar
            text = " ".join(p["text"] for p in paraules[i + 1:fi + 1]).strip(" ,")
            tipus = tipus_de(text)
            if paraula in DESPERTA_AMB_ORDRE and tipus == "altre":  # «Tallat amb llet, si us plau»
                i += 1
                continue
            ancora = fi + 1 if fi + 1 < len(paraules) else None
            ins = {"id": f"i{paraules[i]['id']}", "tipus": tipus, "text": text,
                   "paraules": [paraules[i]["id"], paraules[fi]["id"]],
                   "inici": paraules[i]["inici"], "final": paraules[fi]["final"],
                   "ancora": paraules[ancora]["id"] if ancora is not None else None,
                   "estat": "pendent"}
            if not clara:  # no se sap on acaba: no se'n treu res del vídeo sense que la persona ho vegi
                ins["dubtosa"] = True
            if tipus == "talla":
                tros = _represa(paraules, fi)
                if tros:  # treiem des del primer intent fins just abans de «Claude» (o «tallat»)
                    ins["treure"] = [paraules[tros[0]]["id"], paraules[i - 1]["id"]] if i > tros[0] else None
            instruccions.append(ins)
            i = fi + 1
        else:
            i += 1
    ocupades = {k for k, p in enumerate(paraules)
                for ins in instruccions if ins["paraules"][0] <= p["id"] <= ins["paraules"][1]}
    return sorted(instruccions + _sense_paraula(paraules, ocupades), key=lambda x: x["inici"])


def llegeix(carpeta: Path) -> list[dict]:
    path = carpeta / FITXER
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def desa(carpeta: Path, instruccions: list[dict]) -> None:
    (carpeta / FITXER).write_text(json.dumps(instruccions, ensure_ascii=False, indent=1), encoding="utf-8")


def aplica_a_estat(estat: dict, instruccions: list[dict]) -> dict:
    """Treu del vídeo les paraules de cada instrucció (es poden recuperar)."""
    for ins in instruccions:
        if not ins.get("paraules") or ins.get("dubtosa"):  # afegida a mà, o sense un final clar
            continue
        a, b = ins["paraules"]
        for pid in range(a, b + 1):
            if pid not in estat["mantingudes"] and pid not in estat["esborrades"]:
                estat["esborrades"][pid] = "instruccio"
    return estat


def aplica_decisio(estat: dict, ins: dict) -> dict:
    """L'efecte d'acceptar (o descartar) una instrucció: «talla» treu el primer intent i «zoom» fa el zoom.
    Les dites sense «Claude» no es treuen del vídeo fins que s'accepten (i hi tornen si es desaccepten)."""
    acceptada = ins.get("estat") == "acceptada"
    if ins.get("sense_paraula") and ins.get("paraules"):
        a, b = ins["paraules"]
        for pid in range(a, b + 1):
            if acceptada and pid not in estat["esborrades"] and pid not in estat["mantingudes"]:
                estat["esborrades"][pid] = "instruccio"
            elif not acceptada and estat["esborrades"].get(pid) == "instruccio":
                del estat["esborrades"][pid]
    if ins.get("tipus") == "talla" and ins.get("treure"):
        a, b = ins["treure"]
        for pid in range(a, b + 1):
            if acceptada and pid not in estat["esborrades"]:
                estat["esborrades"][pid] = "instruccio"
            elif not acceptada and estat["esborrades"].get(pid) == "instruccio":
                del estat["esborrades"][pid]
    if ins.get("tipus") == "zoom" and ins.get("ancora") is not None:
        zooms = set(estat.get("zooms", []))
        (zooms.add if acceptada else zooms.discard)(ins["ancora"])
        estat["zooms"] = sorted(zooms)
    return estat


CAMPS_DETECCIO = {"id", "tipus", "text", "paraules", "inici", "final", "ancora", "treure", "dubtosa", "sense_paraula"}


def fusiona(noves: list[dict], velles: list[dict]) -> list[dict]:
    """En tornar a detectar, no es perd res del que ja s'havia fet.

    - De les que es tornen a trobar, es conserva tot el que no surt de la detecció: la decisió
      (acceptada/descartada) i el recurs assignat (fitxer, original, durada…).
    - Les afegides a mà es queden tal qual.
    - Les que ja no es troben però tenien un fitxer assignat, també (no es llença feina)."""
    per_id = {v["id"]: v for v in velles}
    for n in noves:
        for clau, valor in per_id.get(n["id"], {}).items():
            if clau not in CAMPS_DETECCIO:
                n[clau] = valor
    trobades = {n["id"] for n in noves}
    conservades = [v for v in velles if v["id"] not in trobades and (v.get("manual") or v.get("fitxer"))]
    return sorted(noves + conservades, key=lambda x: x.get("inici", 0))
