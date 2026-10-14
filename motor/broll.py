"""B-roll: plans de recurs que tapen la imatge un moment mentre la veu continua.

tallat no depèn de cap IA: només necessita un fitxer. Pot venir de:
- un fitxer propi pujat des de la pàgina de revisió (vídeo o imatge);
- la biblioteca de la persona, `~/.tallat/broll/`;
- una IA d'imatge o vídeo que la persona tingui connectada a Claude (Krea, Higgsfield…):
  Claude el genera i el registra amb `tallat.py broll`.

`prepara()` en fa sempre el mateix: un clip vertical 1080 × 1920, curt (1-1,5 s), sense so i,
si l'estil en porta, amb el LUT de color aplicat. Les imatges es converteixen en un clip
amb un zoom lent perquè no quedin estàtiques.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from motor.exporta import info_video

AMPLADA, ALCADA, FPS = 1080, 1920, 30
BIBLIOTECA = Path.home() / ".tallat" / "broll"
CARPETA = "broll"  # dins del projecte (al costat d'instruccions.json)
IMATGES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff", ".bmp"}
VIDEOS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def es_compatible(path: Path) -> bool:
    return path.suffix.lower() in IMATGES | VIDEOS


def biblioteca() -> list[Path]:
    BIBLIOTECA.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in BIBLIOTECA.iterdir() if p.is_file() and es_compatible(p))


def _cobreix() -> str:
    """Escala perquè ompli el 9:16 i en retalla el centre (com fa l'export amb el vídeo)."""
    return (f"scale={AMPLADA}:{ALCADA}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={AMPLADA}:{ALCADA},setsar=1")


def _lut(lut: str | None) -> str:
    if not lut:
        return ""
    path = Path(lut).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"No trobo el LUT de l'estil: {path}")
    return f",lut3d=file='{str(path).replace(chr(39), '')}'"


def prepara(origen: Path, desti: Path, durada: float = 1.5, lut: str | None = None) -> Path:
    """Converteix un vídeo o una imatge en el clip de b-roll que fa servir l'export."""
    origen = Path(origen).expanduser()
    if not origen.exists():
        raise FileNotFoundError(f"No trobo el fitxer de b-roll: {origen}")
    desti.parent.mkdir(parents=True, exist_ok=True)
    temporal = desti.with_suffix(".tmp.mp4")
    comu = ["-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporal)]
    if origen.suffix.lower() in IMATGES:
        fotogrames = max(1, round(durada * FPS))
        # Zoom lent del 100 % al 108 %, centrat: la imatge «respira» en lloc de quedar quieta.
        filtre = (f"{_cobreix()},scale={AMPLADA * 2}:{ALCADA * 2},"
                  f"zoompan=z='1+0.08*on/{fotogrames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                  f":d={fotogrames}:s={AMPLADA}x{ALCADA}:fps={FPS}{_lut(lut)}")
        ordre = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(origen),
                 "-vf", filtre, "-frames:v", str(fotogrames), *comu]
    else:
        info = info_video(origen)
        # Si el clip és prou llarg, n'agafem un tros del principi (deixant passar el primer instant).
        inici = 0.3 if info["durada"] > durada + 0.6 else 0.0
        ordre = ["ffmpeg", "-v", "error", "-y", "-ss", f"{inici:.2f}", "-i", str(origen),
                 "-t", f"{durada:.3f}", "-map", "0:v:0", "-vf", _cobreix() + _lut(lut), *comu]
    subprocess.run(ordre, check=True, capture_output=True)
    temporal.replace(desti)
    return desti


def copia_original(origen: Path, carpeta: Path, nom: str) -> Path:
    """Desa una còpia del fitxer original al projecte (per poder-lo tornar a preparar)."""
    desti = carpeta / CARPETA / "originals" / f"{nom}{origen.suffix.lower()}"
    desti.parent.mkdir(parents=True, exist_ok=True)
    if origen.resolve() != desti.resolve():
        shutil.copy(origen, desti)
    return desti
