"""On hi ha veu i on hi ha silenci de debò, segons el volum del so.

L'alineador de vegades comprimeix les últimes paraules d'una frase (diu que «tu» acaba a
36,35 s quan la veu continua fins a 37,3 s). Si escurcéssim el silenci «entre paraules»
refiant-nos-en, ens menjaríem paraules. Abans d'escurçar un silenci, doncs, mirem on és
el silenci real dins d'aquell forat.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

PAS = 0.01              # segons per mesura
SOBRE_EL_SOROLL = 12    # dB per sobre del soroll de fons que comptem com a veu
SR = 16000


def llegeix_audio(video: Path) -> np.ndarray:
    """Àudio mono a 16 kHz de la primera pista (els iPhone en porten una d'espacial que no es llegeix)."""
    brut = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-map", "0:a:0", "-vn",
                           "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                          capture_output=True, check=True).stdout
    return np.frombuffer(brut, dtype=np.int16).astype(np.float32) / 32768.0


def mapa(audio: np.ndarray) -> np.ndarray:
    """Un booleà cada 10 ms: True si hi ha veu."""
    mida = int(SR * PAS)
    n = len(audio) // mida
    trossos = audio[:n * mida].reshape(n, mida)
    db = 20 * np.log10(np.sqrt((trossos ** 2).mean(axis=1)) + 1e-9)
    return db >= float(np.percentile(db, 10)) + SOBRE_EL_SOROLL


def carrega(carpeta: Path, video: Path) -> np.ndarray:
    """El mapa de veu del projecte (es calcula un cop i es desa a veu.npy)."""
    path = carpeta / "veu.npy"
    if path.exists():
        return np.load(path)
    m = mapa(llegeix_audio(video))
    np.save(path, m)
    return m


def silenci_mes_llarg(veu: np.ndarray, t0: float, t1: float) -> tuple[float, float] | None:
    """El tros de silenci real més llarg entre t0 i t1 (segons), o None si no n'hi ha."""
    a, b = max(0, int(np.ceil(t0 / PAS))), min(len(veu), int(t1 / PAS))
    millor, inici = None, None
    for k in range(a, b + 1):
        silenci = k < b and not veu[k]
        if silenci and inici is None:
            inici = k
        elif not silenci and inici is not None:
            if millor is None or k - inici > millor[1] - millor[0]:
                millor = (inici, k)
            inici = None
    return (millor[0] * PAS, millor[1] * PAS) if millor else None


MINIM_SILENCI = 0.06  # segons de silenci que separen dues paraules


def _trossos_de_silenci(veu: np.ndarray, t0: float, t1: float):
    """Trossos de silenci (inici, final) d'almenys MINIM_SILENCI entre t0 i t1, en ordre."""
    a, b = max(0, int(np.ceil(t0 / PAS))), min(len(veu), int(t1 / PAS))
    minim = max(1, int(round(MINIM_SILENCI / PAS)))
    trossos, inici = [], None
    for k in range(a, b + 1):
        silenci = k < b and not veu[k]
        if silenci and inici is None:
            inici = k
        elif not silenci and inici is not None:
            if k - inici >= minim:
                trossos.append((inici * PAS, k * PAS))
            inici = None
    return trossos


def fi_de_la_veu(veu: np.ndarray, des_de: float, abans_de: float) -> float | None:
    """On acaba de debò la veu que comença a «des_de»: l'inici del primer silenci abans de «abans_de».

    Serveix quan la paraula següent es treu: l'alineador sovint fa acabar massa d'hora l'última
    paraula d'una frase. Si no hi ha cap silenci entremig, no sabem de qui és el so: None."""
    trossos = _trossos_de_silenci(veu, des_de, abans_de)
    return trossos[0][0] if trossos else None


def inici_de_la_veu(veu: np.ndarray, despres_de: float, fins_a: float) -> float | None:
    """Simètric: on comença de debò la veu que acaba a «fins_a» (el final de l'últim silenci)."""
    trossos = _trossos_de_silenci(veu, despres_de, fins_a)
    return trossos[-1][1] if trossos else None
