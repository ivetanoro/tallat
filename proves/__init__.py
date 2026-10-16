"""Proves de tallat. Cap prova no toca la configuració de la persona: els kits d'estil d'aquí
dins van a una carpeta temporal, que s'esborra en acabar."""
import atexit
import shutil
import tempfile
from pathlib import Path

from motor import exporta, marca

_CASA = Path(tempfile.mkdtemp(prefix="tallat-proves-"))
marca.KITS = _CASA / "kits"
marca.USUARI = _CASA / "brand.json"
exporta.PREFERENCIES = _CASA / "preferencies.json"
atexit.register(shutil.rmtree, _CASA, True)
