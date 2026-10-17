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


def llista_de_lletres() -> None:
    """WhisperX porta matplotlib, que el primer cop fa la llista de lletres del Mac amb system_profiler.
    En un Mac ocupat o amb moltes lletres, system_profiler s'atura a mitges sense la llista, matplotlib
    peta i WhisperX no arrenca. La fem sense system_profiler: n'hi ha prou amb les carpetes de lletres
    (tallat no dibuixa res amb matplotlib). Queda desada i els altres cops ja no es fa.
    S'ha de cridar abans d'importar WhisperX."""
    import subprocess
    import sys
    if sys.platform != "darwin" or "matplotlib.font_manager" in sys.modules:
        return
    original = subprocess.check_output

    def sense_system_profiler(args, *a, **k):
        if args and Path(str(args[0])).name == "system_profiler":
            raise subprocess.CalledProcessError(1, args)  # matplotlib ho entén com «no hi ha llista»
        return original(args, *a, **k)

    subprocess.check_output = sense_system_profiler
    try:
        import matplotlib.font_manager  # noqa: F401
    except ImportError:
        pass
    finally:
        subprocess.check_output = original
