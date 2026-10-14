"""On són les eines de tallat (les que posa prepara.sh) i com trobar-les.

prepara.sh instal·la ffmpeg, ffprobe i Node.js a ~/.tallat/eines/bin, sense tocar el sistema.
Perquè tallat (i HyperFrames) les facin servir, aquesta carpeta va al davant del PATH.
"""
from __future__ import annotations

import os
from pathlib import Path

TALLAT = Path.home() / ".tallat"
EINES = TALLAT / "eines" / "bin"
INSTAL_LADORS = TALLAT / "bin"
VERSIO_HYPERFRAMES = "0.8.154"


def prepara() -> None:
    """Posa les eines de tallat al davant del PATH (si prepara.sh les ha instal·lat)."""
    camins = os.environ.get("PATH", "").split(os.pathsep)
    for carpeta in (INSTAL_LADORS, EINES):  # EINES queda primer
        if carpeta.is_dir() and str(carpeta) not in camins:
            camins.insert(0, str(carpeta))
    os.environ["PATH"] = os.pathsep.join(camins)
