"""On hi ha veu i on hi ha silenci de debò, segons el volum del so. Ho fan servir tallat i matcha.

L'alineador de vegades comprimeix les últimes paraules d'una frase (diu que «tu» acaba a 36,35 s quan la veu
continua fins a 37,3 s). Si s'escurcés el silenci «entre paraules» refiant-se'n, es menjarien paraules. Abans
d'escurçar un silenci, doncs, es mira on és el silenci real dins d'aquell forat.

Cada eina desa el mapa on vol (i amb la seva versió): aquí només es calcula i es consulta.
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

PAS = 0.01              # segons per mesura
SOBRE_EL_SOROLL = 12    # dB per sobre del soroll de fons que comptem com a veu
SR = 16000
MINIM_VEU = 0.3         # en una gravació parlant, com a mínim aquesta part és veu
# Si la veu destaca tant del soroll de fons, el mapa és clar encara que hi hagi poca veu (un vídeo amb silencis
# llargs): n'hi ha prou que n'hi hagi aquesta part.
CONTRAST_CLAR, MINIM_VEU_CLAR = 25, 0.03
SOROLL = 0.1            # segons: dins d'una pausa, un so més curt (un clic, una tecla, un cop) no és veu
MINIM_SILENCI = 0.06    # segons de silenci que separen dues paraules


def llegeix_audio(p: Path, ffmpeg: str = "ffmpeg", executa=None) -> np.ndarray:
    """Àudio mono a 16 kHz de la primera pista (els iPhone en porten una d'espacial que no es llegeix). Un wav
    que ja ho és es llegeix tal qual; la resta, amb ffmpeg. `executa(ordre)` (opcional) torna un resultat amb
    `.stdout`: així cada eina hi posa els seus missatges d'error."""
    try:
        with wave.open(str(p), "rb") as w:
            if w.getframerate() == SR and w.getsampwidth() == 2:
                n = w.getnchannels()
                x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
                return x.reshape(-1, n).mean(axis=1) if n > 1 else x
    except (wave.Error, EOFError, OSError):
        pass
    ordre = [ffmpeg, "-hide_banner", "-v", "error", "-i", str(p), "-map", "0:a:0", "-vn",
             "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    r = executa(ordre) if executa else subprocess.run(ordre, capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def mapa(audio: np.ndarray) -> np.ndarray:
    """Un booleà cada 10 ms: True si hi ha veu.

    El soroll de fons s'estima amb els trossos més fluixos. Si la gravació gairebé no té silencis, el 10 % més
    fluix ja és veu i tot semblaria silenci: llavors es prova amb el 2 % més fluix. Si no es distingeix la veu del
    soroll, es dona tot per veu: així no es retalla ni s'escurça res que no s'hagi de tocar."""
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


def silenci_mes_llarg(veu: np.ndarray, t0: float, t1: float, soroll: float = SOROLL) -> tuple[float, float] | None:
    """El tros de silenci real més llarg entre t0 i t1 (segons), o None si no n'hi ha. Un so de menys de `soroll`
    segons hi compta com a silenci (una tecla enmig d'una pausa de 10 s no la parteix en dues). Els bocins de so
    separats per menys de MINIM_SILENCI són d'un mateix so (una paraula curta es pot partir en dos): es mesuren
    junts, perquè la veu de debò no es prengui per un clic."""
    a, b = max(0, int(np.ceil(t0 / PAS))), min(len(veu), int(t1 / PAS))
    tros = np.array(veu[a:b], dtype=bool) if b > a else np.zeros(0, dtype=bool)
    curt, junts = int(round(soroll / PAS)), int(round(MINIM_SILENCI / PAS))
    sons, k = [], 0  # (inici, final) de cada so, amb els bocins propers junts
    while k < len(tros):
        if not tros[k]:
            k += 1
            continue
        j = k
        while j < len(tros) and tros[j]:
            j += 1
        if sons and k - sons[-1][1] < junts:
            sons[-1] = (sons[-1][0], j)
        else:
            sons.append((k, j))
        k = j
    for x, y in sons:
        if y - x < curt:
            tros[x:y] = False
    millor, inici = None, None
    for k in range(a, b + 1):
        silenci = k < b and not tros[k - a]
        if silenci and inici is None:
            inici = k
        elif not silenci and inici is not None:
            if millor is None or k - inici > millor[1] - millor[0]:
                millor = (inici, k)
            inici = None
    return (millor[0] * PAS, millor[1] * PAS) if millor else None


def trossos_de_silenci(veu: np.ndarray, t0: float, t1: float) -> list[tuple[float, float]]:
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
    """On acaba de debò la veu que comença a «des_de»: l'inici del primer silenci abans de «abans_de». Serveix
    quan la paraula següent es treu. Si no hi ha cap silenci entremig, no se sap de qui és el so: None."""
    trossos = trossos_de_silenci(veu, des_de, abans_de)
    return trossos[0][0] if trossos else None


def inici_de_la_veu(veu: np.ndarray, despres_de: float, fins_a: float) -> float | None:
    """Simètric: on comença de debò la veu que acaba a «fins_a» (el final de l'últim silenci)."""
    trossos = trossos_de_silenci(veu, despres_de, fins_a)
    return trossos[-1][1] if trossos else None
