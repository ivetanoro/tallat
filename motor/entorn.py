"""On són les eines de tallat (les que posa prepara.sh o, a Windows, prepara.ps1) i com trobar-les, i el
poc que es fa diferent al Mac i a Windows (obrir una carpeta, triar-ne una, trobar un programa).

L'instal·lador posa ffmpeg, ffprobe i Node.js a ~/.tallat/eines, sense tocar el sistema. Perquè tallat
(i HyperFrames) les facin servir, aquesta carpeta va al davant del PATH.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

TALLAT = Path.home() / ".tallat"
WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"
EINES = TALLAT / "eines" / "bin"
INSTAL_LADORS = TALLAT / "bin"
VERSIO_HYPERFRAMES = "0.8.154"


def carpetes_eines() -> list[Path]:
    """On deixa els programes l'instal·lador. Al Mac, eines/bin. A Windows (els paquets de conda-forge),
    ffmpeg va a eines/Library/bin i Node.js a la mateixa carpeta eines."""
    if WINDOWS:
        eines = TALLAT / "eines"
        return [eines / "Library" / "bin", eines]
    return [EINES]


def prepara() -> None:
    """Posa les eines de tallat al davant del PATH (si l'instal·lador les ha posat)."""
    camins = os.environ.get("PATH", "").split(os.pathsep)
    for carpeta in (INSTAL_LADORS, *reversed(carpetes_eines())):  # les eines queden primer
        if carpeta.is_dir() and str(carpeta) not in camins:
            camins.insert(0, str(carpeta))
    os.environ["PATH"] = os.pathsep.join(camins)
    if WINDOWS:
        # A Windows, torch i ctranslate2 (WhisperX) porten cadascun la seva còpia d'OpenMP; sense això, en
        # carregar la segona el programa s'atura («OMP: Error #15»). Al Mac Intel ho arregla prepara.sh.
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        # Quan la sortida no va a una finestra (Claude la llegeix per un canal), Windows fa servir una
        # codificació antiga i «✓» o «·» farien petar el programa. Els programes fills, en UTF-8.
        for corrent in (sys.stdout, sys.stderr):
            if hasattr(corrent, "reconfigure"):
                corrent.reconfigure(encoding="utf-8", errors="replace")
        os.environ.setdefault("PYTHONUTF8", "1")


def programa(nom: str) -> str:
    """El camí sencer d'un programa del PATH. A Windows, npx és «npx.cmd» i subprocess no el troba pel nom
    sol; si no hi és, el nom tal qual (i l'error que doni ja dirà que no hi és)."""
    return shutil.which(nom) or nom


def mostra_al_gestor(path: Path) -> None:
    """Obre el Finder (o l'Explorador de fitxers de Windows) amb el fitxer seleccionat."""
    if MAC:
        subprocess.run(["open", "-R", str(path)], check=False)
    elif WINDOWS:
        subprocess.run(["explorer", f"/select,{Path(path)}"], check=False)
    else:
        subprocess.run(["xdg-open", str(Path(path).parent)], check=False)


def tria_carpeta(pregunta: str) -> Path | None:
    """Obre la finestra del sistema per triar una carpeta. None si es cancel·la (o no es pot obrir)."""
    if MAC:
        r = subprocess.run(["osascript", "-e", f'POSIX path of (choose folder with prompt "{pregunta}")'],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    elif WINDOWS:
        # La sortida en UTF-8: si no, una carpeta com «Descàrregues» arribaria amb les lletres canviades.
        ordre = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms; "
                 "$d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = $env:TALLAT_PREGUNTA; "
                 "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }")
        r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ordre], capture_output=True,
                           text=True, encoding="utf-8", env={**os.environ, "TALLAT_PREGUNTA": pregunta})
    else:
        r = subprocess.run(["zenity", "--file-selection", "--directory", f"--title={pregunta}"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace") if shutil.which("zenity") else None
    if r is None or r.returncode != 0 or not r.stdout.strip():
        return None
    return Path(r.stdout.strip())


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
