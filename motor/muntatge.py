"""Primer muntatge automàtic: d'una gravació llarga en surten diversos reels.

El «cervell» és Claude, dins de Claude Code (vegeu skill/SKILL.md):
1. `guio()` escriu la transcripció per paràgrafs, amb números i temps, perquè Claude la llegeixi.
2. Claude escriu `reels.json` al projecte: per a cada reel, quins trossos de paraules es queden.
3. `llegeix_reels()` ho valida i en calcula la durada.
4. `crea_reel()` en fa un projecte propi a `<projecte>/reels/<id>/`, que comparteix la
   transcripció i la còpia lleugera amb la gravació sencera.

Format de reels.json:
{
  "reels": [
    {"id": "dj-teta", "titol": "…", "ganxo": "…", "per_que": "…",
     "paraules": [[140, 148], [600, 655]]}      # trossos d'ids de paraula, inclosos els extrems
  ]
}
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from motor import edicio

REELS = "reels.json"
GUIO = "guio.txt"
CARPETA_REELS = "reels"


def _temps(s: float) -> str:
    return f"{int(s // 60)}:{s % 60:04.1f}".replace(".", ",")


def guio(paraules: list[dict]) -> str:
    """Transcripció per paràgrafs: [número · inici–final · paraules a–b] text."""
    linies = ["# Guió per al primer muntatge (tallat)",
              "# [P número · inici–final · paraules primera–última] text", ""]
    for n, g in enumerate(edicio.paragrafs(paraules)):
        linies.append(f"[P{n} · {_temps(g[0]['inici'])}–{_temps(g[-1]['final'])} · "
                      f"paraules {g[0]['id']}–{g[-1]['id']}] " + " ".join(p["text"] for p in g))
    return "\n".join(linies) + "\n"


def _id_segur(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")[:40] or "reel"


def llegeix_reels(carpeta: Path, paraules: list[dict]) -> tuple[list[dict], list[str]]:
    """Llegeix i valida reels.json. Retorna (reels, errors)."""
    path = carpeta / REELS
    if not path.exists():
        return [], []
    try:
        dades = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [], [f"reels.json no és JSON vàlid: {e}"]
    n = len(paraules)
    reels, errors, vistos = [], [], set()
    for i, r in enumerate(dades.get("reels", [])):
        rid = _id_segur(str(r.get("id") or r.get("titol") or f"reel-{i + 1}"))
        if rid in vistos:
            rid = f"{rid}-{i + 1}"
        vistos.add(rid)
        rangs = []
        for rang in r.get("paraules", []):
            try:
                a, b = int(rang[0]), int(rang[1])
            except (TypeError, ValueError, IndexError):
                errors.append(f"{rid}: tros no vàlid {rang!r}")
                continue
            if not (0 <= a <= b < n):
                errors.append(f"{rid}: el tros {a}–{b} surt de la transcripció (0–{n - 1})")
                continue
            rangs.append((a, b))
        if not rangs:
            errors.append(f"{rid}: no té cap tros de paraules")
            continue
        reels.append({"id": rid, "titol": r.get("titol", rid), "ganxo": r.get("ganxo", ""),
                      "per_que": r.get("per_que", ""), "paraules": rangs})  # l'ordre és el del muntatge
    return reels, errors


def estat_inicial(paraules: list[dict], rangs: list[tuple[int, int]]) -> dict:
    """Estat d'edició d'un reel: tot el que queda fora dels trossos, tret amb motiu «muntatge»."""
    dins = {i for a, b in rangs for i in range(a, b + 1)}
    estat = edicio.estat_buit()
    estat["esborrades"] = {p["id"]: "muntatge" for p in paraules if p["id"] not in dins}
    estat["ordre"] = [list(r) for r in rangs]
    return estat


def crea_reel(arrel, reel: dict) -> Path:
    """Crea (o reaprofita) el projecte del reel i en retorna la carpeta."""
    from motor.projecte import EDICIO, PROXY, TRANSCRIPCIO, Projecte

    carpeta = arrel.carpeta / CARPETA_REELS / reel["id"]
    carpeta.mkdir(parents=True, exist_ok=True)
    for nom in (TRANSCRIPCIO, PROXY):
        enllac = carpeta / nom
        if not enllac.exists() and (arrel.carpeta / nom).exists():
            enllac.symlink_to(Path("..") / ".." / nom)
    (carpeta / "reel.json").write_text(json.dumps(reel, ensure_ascii=False, indent=1), encoding="utf-8")
    if not (carpeta / EDICIO).exists():
        projecte = Projecte(carpeta)
        projecte.estat = estat_inicial(projecte.dades["paraules"], reel["paraules"])
        projecte.neteja()
        projecte.desa()
    return carpeta


def durada_estimada(arrel, reel: dict) -> float:
    """Quant duraria el reel amb la neteja aplicada (sense crear-lo)."""
    estat = estat_inicial(arrel.dades["paraules"], reel["paraules"])
    from motor import neteja as net
    estat = edicio.aplica_neteja(estat, *net.detecta(arrel.dades["paraules"], net.carrega_llista()))
    trams = edicio.trams(edicio.aplica(arrel.dades["paraules"], estat), arrel.fps, arrel.dades["durada"],
                         pausa_maxima=estat["pausa_maxima"], ordre=estat["ordre"])
    return round(sum(b - a for a, b in trams), 2)
