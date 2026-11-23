"""On hi ha veu i on hi ha silenci de debò, segons el volum del so.

L'alineador de vegades comprimeix les últimes paraules d'una frase (diu que «tu» acaba a
36,35 s quan la veu continua fins a 37,3 s). Si escurcéssim el silenci «entre paraules»
refiant-nos-en, ens menjaríem paraules. Abans d'escurçar un silenci, doncs, mirem on és
el silenci real dins d'aquell forat.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from motor.nucli import veu as nucli_veu  # el càlcul el comparteixen tallat i matcha
from motor.nucli.veu import (CONTRAST_CLAR, MINIM_SILENCI, MINIM_VEU, MINIM_VEU_CLAR, PAS,  # noqa: F401
                             SOBRE_EL_SOROLL, SOROLL, SR, fi_de_la_veu, inici_de_la_veu, mapa, silenci_mes_llarg)

_trossos_de_silenci = nucli_veu.trossos_de_silenci
VERSIO_MAPA = 2  # puja si canvia com es calcula: els mapes desats d'abans es tornen a fer


def llegeix_audio(video: Path) -> np.ndarray:
    """Àudio mono a 16 kHz de la primera pista (vegeu motor/nucli/veu.py)."""
    return nucli_veu.llegeix_audio(video)


def _identitat(font: Path) -> dict:
    """De quin fitxer és el mapa: camí, mida i data de modificació."""
    st = Path(font).stat()
    return {"cami": str(Path(font).resolve()), "mida": st.st_size, "modificat": st.st_mtime_ns}


def carrega(carpeta: Path, video: Path, durada: float | None = None, alternativa: Path | None = None) -> np.ndarray:
    """El mapa de veu del projecte. Es calcula un cop i es desa a veu.npy, amb veu.json al costat (de quin
    fitxer és, la durada del so i la versió del càlcul). Si el projecte ara és d'un altre vídeo (s'ha tornat
    a transcriure), el fitxer ha canviat o el càlcul és un altre, es torna a fer. `alternativa`: d'on llegir
    el so si el vídeo ja no hi és (la còpia lleugera, que té el mateix so)."""
    path, path_meta = carpeta / "veu.npy", carpeta / "veu.json"
    font = video if Path(video).exists() or alternativa is None else alternativa
    try:
        meta = json.loads(path_meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    try:
        identitat = _identitat(font)
    except OSError:
        identitat = None
    if path.exists() and meta.get("versio") == VERSIO_MAPA and (
            durada is None or abs(float(meta.get("durada", -10)) - durada) < 1.0) and (
            identitat is None or meta.get("font") == identitat):
        desat = np.load(path)
        if desat.size:
            return desat
    m = mapa(llegeix_audio(font))
    for p in (path, path_meta):  # un enllaç (els «anteriors-…» apunten al del projecte): no el trepitgem
        if p.is_symlink():
            p.unlink()
    np.save(path, m)
    path_meta.write_text(json.dumps({"versio": VERSIO_MAPA, "durada": round(len(m) * PAS, 2), "font": identitat},
                                    ensure_ascii=False), encoding="utf-8")
    return m
