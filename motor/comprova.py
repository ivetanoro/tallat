"""Comprova que l'ordinador té tot el que necessita tallat (`tallat.py comprova`).

Cada comprovació diu «ok», «avís» (funcionarà, però hi ha alguna cosa a saber) o «error» (cal
arreglar-ho), amb una explicació curta i què fer. Gairebé sempre, el que cal fer és tornar a
executar ./prepara.sh.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from motor import entorn

ARREGLA = "executa ./prepara.sh (des de la carpeta de tallat)"
MARQUES = {"ok": "✓", "avis": "!", "error": "✗"}


def _versio(paquet: str) -> str | None:
    try:
        return importlib.metadata.version(paquet)
    except importlib.metadata.PackageNotFoundError:
        return None


def _executa(ordre: list[str], temps: int = 60) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(ordre, capture_output=True, text=True, timeout=temps)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _python() -> list[tuple]:
    v = sys.version_info
    estat = "ok" if v[:2] == (3, 11) else "avis"
    detall = f"{platform.python_version()}" + ("" if estat == "ok" else " · tallat està provat amb la 3.11")
    resultat = [(estat, "Python", detall)]
    falten = [p for p in ("whisperx", "torch", "torchaudio", "transformers", "numpy") if not _versio(p)]
    if falten:
        return resultat + [("error", "WhisperX", f"falten paquets ({', '.join(falten)}) → {ARREGLA}")]
    if int(_versio("numpy").split(".")[0]) >= 2:
        resultat.append(("error", "numpy", f"cal la versió 1 (n'hi ha la {_versio('numpy')}) → {ARREGLA}"))
    # S'importa a part: a Mac Intel, si dues còpies d'OpenMP xoquen, el programa peta.
    prova = _executa([sys.executable, "-c", "import ctranslate2, torch, whisperx"], temps=300)
    if prova is None or prova.returncode != 0:
        omp = prova is not None and (prova.returncode < 0 or "OMP" in prova.stderr)
        motiu = "dues còpies d'OpenMP xoquen (Mac Intel)" if omp else "no arrenca"
        return resultat + [("error", "WhisperX", f"{motiu} → {ARREGLA}")]
    return resultat + [("ok", "WhisperX", f"{_versio('whisperx')} · torch {_versio('torch')}")]


def _ffmpeg() -> list[tuple]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        falta = " i ".join(n for n, p in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)) if not p)
        return [("error", "ffmpeg", f"no trobo {falta} → {ARREGLA}")]
    versio = (_executa([ffmpeg, "-hide_banner", "-version"]) or subprocess.CompletedProcess([], 1, "", "")).stdout
    versio = (versio.splitlines() or ["?"])[0].replace("ffmpeg version ", "")
    codificadors = (_executa([ffmpeg, "-hide_banner", "-encoders"]) or subprocess.CompletedProcess([], 1, "", "")).stdout
    filtres = (_executa([ffmpeg, "-hide_banner", "-filters"]) or subprocess.CompletedProcess([], 1, "", "")).stdout
    falten = [c for c in ("h264_videotoolbox", "libx264", "aac") if not re.search(rf"\s{c}\s", codificadors)]
    falten += [f for f in ("lut3d", "zoompan", "overlay", "concat") if not re.search(rf"\s{f}\s", filtres)]
    if falten:
        return [("error", "ffmpeg", f"{versio} no porta {', '.join(falten)} → {ARREGLA}")]
    propi = Path(ffmpeg).parent == entorn.EINES
    return [("ok", "ffmpeg", f"{versio.split(' ')[0]}" + (" (de tallat)" if propi else f" ({ffmpeg})"))]


def _node() -> list[tuple]:
    node, npx = shutil.which("node"), shutil.which("npx")
    if not node or not npx:
        return [("error", "Node.js", f"no el trobo (cal per a HyperFrames) → {ARREGLA}")]
    versio = ((_executa([node, "--version"]) or subprocess.CompletedProcess([], 1, "", "")).stdout or "").strip()
    major = int(re.sub(r"\D", "", versio.split(".")[0]) or 0)
    if major < 18:
        return [("error", "Node.js", f"{versio} és massa antic (cal el 18 o més nou) → {ARREGLA}")]
    resultat = [("ok", "Node.js", versio)]
    paquets = list((Path.home() / ".npm" / "_npx").glob("*/node_modules/hyperframes/package.json"))
    versions = set()
    for p in paquets:
        try:
            versions.add(json.loads(p.read_text(encoding="utf-8")).get("version"))
        except (OSError, json.JSONDecodeError):
            continue
    if entorn.VERSIO_HYPERFRAMES not in versions:
        return resultat + [("avis", "HyperFrames", "es baixarà el primer cop que facis un esborrany (uns segons)")]
    cami = _executa([npx, "--yes", f"hyperframes@{entorn.VERSIO_HYPERFRAMES}", "browser", "path"], temps=90)
    navegador = cami.stdout.strip().splitlines()[-1] if cami and cami.returncode == 0 and cami.stdout.strip() else ""
    if not navegador or not Path(navegador).exists():
        return resultat + [("avis", "HyperFrames", f"{entorn.VERSIO_HYPERFRAMES}; el navegador es baixarà el primer cop (uns 100 MB)")]
    return resultat + [("ok", "HyperFrames", f"{entorn.VERSIO_HYPERFRAMES} amb el seu navegador")]


def _models() -> list[tuple]:
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    tenim = lambda nom: any((hub / f"models--{nom}" / "snapshots").glob("*/*"))  # noqa: E731
    resultat = []
    if tenim("softcatala--wav2vec2-large-xlsr-catala"):
        resultat.append(("ok", "Model de veu català", "Softcatalà"))
    else:
        resultat.append(("avis", "Model de veu català", f"es baixarà el primer cop que transcriguis (1,2 GB); o {ARREGLA}"))
    if tenim("Systran--faster-whisper-large-v3"):
        resultat.append(("ok", "Model de transcripció", "large-v3"))
    else:
        resultat.append(("avis", "Model de transcripció", "només cal si no fas servir Descript; es baixarà el primer cop (3 GB)"))
    return resultat


def _disc_i_carpeta() -> list[tuple]:
    resultat = []
    lliure = shutil.disk_usage(Path.home()).free / 1e9
    estat = "error" if lliure < 5 else ("avis" if lliure < 15 else "ok")
    resultat.append((estat, "Espai al disc", f"{lliure:.0f} GB lliures" + ("" if estat == "ok" else " · els vídeos en 4K n'ocupen molt")))
    try:
        entorn.TALLAT.mkdir(parents=True, exist_ok=True)
        prova = entorn.TALLAT / ".prova-escriptura"
        prova.write_text("ok", encoding="utf-8")
        prova.unlink()
        resultat.append(("ok", "Carpeta ~/.tallat", "s'hi pot escriure"))
    except OSError as e:
        resultat.append(("error", "Carpeta ~/.tallat", f"no s'hi pot escriure ({e.strerror})"))
    return resultat


def comprovacions() -> list[tuple[str, str, str]]:
    """[(estat, nom, detall)] amb estat «ok», «avis» o «error»."""
    entorn.prepara()
    return _python() + _ffmpeg() + _node() + _models() + _disc_i_carpeta()


def informe(resultats: list[tuple[str, str, str]]) -> str:
    amplada = max(len(nom) for _, nom, _ in resultats)
    linies = [f"  {MARQUES[estat]} {nom.ljust(amplada)}  {detall}" for estat, nom, detall in resultats]
    errors = sum(1 for estat, _, _ in resultats if estat == "error")
    if errors:
        linies.append(f"\nHi ha {errors} {'cosa' if errors == 1 else 'coses'} per arreglar. {ARREGLA[0].upper() + ARREGLA[1:]}.")
    else:
        linies.append("\nTot a punt per fer servir tallat.")
    return "\n".join(linies)
