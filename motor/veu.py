"""On hi ha veu i on hi ha silenci de debò, segons el volum del so.

L'alineador de vegades comprimeix les últimes paraules d'una frase (diu que «tu» acaba a
36,35 s quan la veu continua fins a 37,3 s). Si escurcéssim el silenci «entre paraules»
refiant-nos-en, ens menjaríem paraules. Abans d'escurçar un silenci, doncs, mirem on és
el silenci real dins d'aquell forat.
"""
from __future__ import annotations

import json
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


MINIM_VEU = 0.3  # en una gravació parlant, com a mínim aquesta part és veu
# Si la veu destaca tant del soroll de fons, el mapa és clar encara que hi hagi poca veu (p. ex. un
# vídeo amb silencis llargs): n'hi ha prou que n'hi hagi aquesta part.
CONTRAST_CLAR, MINIM_VEU_CLAR = 25, 0.03
VERSIO_MAPA = 2  # puja si canvia com es calcula: els mapes desats d'abans es tornen a fer


def mapa(audio: np.ndarray) -> np.ndarray:
    """Un booleà cada 10 ms: True si hi ha veu.

    El soroll de fons s'estima amb els trossos més fluixos. Si la gravació gairebé no té silencis,
    el 10 % més fluix ja és veu i tot semblaria silenci: llavors es prova amb el 2 % més fluix.
    Si no es distingeix la veu del soroll (no ho sabem), es dona tot per veu: així no es retalla ni
    s'escurça res que no s'hagi de tocar."""
    mida = int(SR * PAS)
    n = len(audio) // mida
    if not n:
        return np.ones(0, dtype=bool)
    trossos = audio[:n * mida].reshape(n, mida)
    db = 20 * np.log10(np.sqrt((trossos ** 2).mean(axis=1)) + 1e-9)
    alt = float(np.percentile(db, 99))  # el nivell de la veu, encara que n'hi hagi poca (fins al 3 %)
    for percentil in (10, 2):
        terra = float(np.percentile(db, percentil))
        veu = db >= terra + SOBRE_EL_SOROLL
        part = veu.mean()
        if part >= MINIM_VEU or (part >= MINIM_VEU_CLAR and alt - terra >= CONTRAST_CLAR):
            return veu
    return np.ones(n, dtype=bool)


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
