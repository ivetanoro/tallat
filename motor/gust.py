"""El gust de cada persona: les correccions que fa queden com a regles per als vídeos següents.

Les regles són a ~/.tallat/gust.json, fora del repositori. N'hi ha de dues menes:
- amb un **ajust**: una opció concreta que es canvia al moment i serveix per a tots els vídeos
  («subtítols més grans» → subtitols.mida=0.09; «no em treguis els vale» → farciment.deixa=vale);
- només amb **text**: una preferència que Claude llegeix abans de decidir res («prefereixo reels
  curts», «el b-roll, sense persones»).

Ajustos possibles:
  subtitols.<opció>, broll.durada, stickers.<opció>, talls.pausa_maxima (secció del fitxer d'estil)
  farciment.treu=EXPRESSIO, farciment.proposa=EXPRESSIO, farciment.deixa=EXPRESSIO

Quan es treu una regla amb ajust, l'opció torna a com estava abans (si ningú no l'ha tornada a canviar).
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from motor import marca, neteja

FITXER = Path.home() / ".tallat" / "gust.json"
SECCIONS = {"talls": "Talls", "subtitols": "Subtítols", "broll": "B-roll", "stickers": "Stickers",
            "reels": "Reels i muntatge", "altres": "Altres"}
FARCIMENT = {"treu": "treu", "proposa": "proposa", "deixa": None}


def llegeix(path: Path | None = None) -> list[dict]:
    try:
        return json.loads((path or FITXER).read_text(encoding="utf-8")).get("regles", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return []


def _desa(regles: list[dict], path: Path | None = None) -> None:
    path = path or FITXER
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(".tmp")
    temporal.write_text(json.dumps({"regles": regles}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporal.replace(path)


def llegeix_ajust(text: str) -> tuple[str, object]:
    """«subtitols.mida=0.09» → ("subtitols.mida", 0.09). Els valors poden ser números, true/false o text."""
    clau, igual, valor = text.partition("=")
    clau = clau.strip()
    if not igual or not re.fullmatch(r"[a-z_]+\.[a-z_]+", clau):
        raise ValueError(f"L'ajust ha de ser com «subtitols.mida=0.09», no «{text}»")
    valor = valor.strip()
    try:
        return clau, json.loads(valor)
    except json.JSONDecodeError:
        return clau, valor


def valor_actual(clau: str):
    seccio, nom = clau.split(".", 1)
    if seccio == "farciment":
        return None  # depèn de l'expressió: es mira a aplica()
    return marca.carrega().get(seccio, {}).get(nom)


def aplica(clau: str, valor) -> object:
    """Aplica un ajust i en torna el valor d'abans (per poder-lo desfer)."""
    seccio, nom = clau.split(".", 1)
    if seccio == "farciment":
        if nom not in FARCIMENT or not isinstance(valor, str):
            raise ValueError("El farciment s'ajusta amb farciment.treu, farciment.proposa o farciment.deixa i una paraula")
        abans = neteja.seccio_de(valor)
        neteja.mou_expressio(valor, FARCIMENT[nom])
        return abans
    if seccio not in marca.EDITABLES:
        raise ValueError(f"No conec l'ajust «{clau}»")
    abans = valor_actual(clau)
    marca.desa(seccio, {nom: valor})
    return abans


def _mateix_ajust(a: dict | None, b: dict | None) -> bool:
    if not a or not b:
        return False
    if a["clau"].startswith("farciment.") and b["clau"].startswith("farciment."):
        return neteja._clau(str(a["valor"])) == neteja._clau(str(b["valor"]))  # la mateixa paraula
    return a["clau"] == b["clau"]


def afegeix(seccio: str, text: str, ajust: str | None = None, path: Path | None = None) -> dict:
    """Afegeix una regla (o actualitza la que deia el mateix) i n'aplica l'ajust, si en porta."""
    if seccio not in SECCIONS:
        raise ValueError(f"La secció ha de ser una d'aquestes: {', '.join(SECCIONS)}")
    text = " ".join(str(text).split())
    if not text:
        raise ValueError("La regla no pot ser buida")
    regles = llegeix(path)
    nou_ajust = None
    if ajust:
        clau, valor = llegeix_ajust(ajust)
        anterior = next((r for r in regles if _mateix_ajust(r.get("ajust"), {"clau": clau, "valor": valor})), None)
        abans = aplica(clau, valor)
        if anterior:  # la mateixa opció ja tenia una regla: la substituïm, recordant el valor original
            abans = anterior["ajust"]["abans"]
            regles.remove(anterior)
        nou_ajust = {"clau": clau, "valor": valor, "abans": abans}
    else:
        igual = next((r for r in regles if r["seccio"] == seccio and r["text"].lower() == text.lower()), None)
        if igual:
            return igual
    regla = {"id": max((r["id"] for r in regles), default=0) + 1, "seccio": seccio, "text": text,
             "data": date.today().isoformat(), "ajust": nou_ajust}
    regles.append(regla)
    _desa(regles, path)
    return regla


def treu(rid: int, path: Path | None = None) -> tuple[dict, bool]:
    """Treu una regla. Si tenia un ajust i ningú no l'ha tornat a canviar, l'opció torna a com estava.

    Torna (regla, desfet)."""
    regles = llegeix(path)
    regla = next((r for r in regles if r["id"] == rid), None)
    if regla is None:
        raise KeyError(rid)
    regles.remove(regla)
    desfet = False
    ajust = regla.get("ajust")
    if ajust:
        seccio, nom = ajust["clau"].split(".", 1)
        if seccio == "farciment":
            if neteja.seccio_de(ajust["valor"]) == FARCIMENT.get(nom):
                neteja.mou_expressio(ajust["valor"], ajust["abans"])
                desfet = True
        elif valor_actual(ajust["clau"]) == ajust["valor"] and ajust["abans"] is not None:
            marca.desa(seccio, {nom: ajust["abans"]})
            desfet = True
    _desa(regles, path)
    return regla, desfet


def text(regles: list[dict]) -> str:
    """Les regles agrupades per seccions, per llegir-les (Claude i la persona)."""
    if not regles:
        return "Encara no hi ha cap regla. Quan la persona corregeixi alguna cosa «per sempre», afegeix-la."
    linies = []
    for seccio, nom in SECCIONS.items():
        del_grup = [r for r in regles if r["seccio"] == seccio]
        if not del_grup:
            continue
        linies.append(f"{nom}:")
        for r in del_grup:
            ajust = r.get("ajust")
            detall = f"  [{ajust['clau']}={json.dumps(ajust['valor'], ensure_ascii=False)}]" if ajust else ""
            linies.append(f"  {r['id']}. {r['text']}{detall}")
    return "\n".join(linies)
