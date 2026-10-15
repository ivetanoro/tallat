"""El so: la neteja de la veu i els efectes de so.

Neteja de la veu (a l'esborrany i al vídeo final): treu el brunzit greu i el soroll de fons,
treu una mica de «caixa» als greus i dona claredat a la veu, suavitza les «s», comprimeix una mica
i iguala el volum al que fan servir Instagram i TikTok (-14 LUFS), en dues passades perquè no
bombegi. Tot amb filtres d'ffmpeg.

Efectes de so: els fabrica tallat amb codi (cap fitxer de fora, cap llicència). Cada persona els
pot canviar pels seus posant un fitxer amb el mateix nom a ~/.tallat/sons/ (whoosh.wav, pop.mp3…).
Tots els efectes d'un vídeo es barregen en una sola pista (WAV) del llarg del muntatge: la mateixa
pista sona a la vista prèvia de la pàgina i es barreja al vídeo final.
"""
from __future__ import annotations

import array
import hashlib
import json
import math
import random
import subprocess
import wave
from pathlib import Path

MOSTREIG = 48000
SONS_PROPIS = Path.home() / ".tallat" / "sons"
NIVELLS_SOROLL = {"suau": 6, "mitja": 12, "fort": 20}  # quants dB de soroll es treuen
VOLUM_OBJECTIU = -14  # LUFS, el de les xarxes
VERSIO_SONS = "1"     # canvia-la si canvia com es fabriquen els sons (la pista es torna a fer)

# Què sona a cada cosa. «pocs»: b-roll, stickers i títol; «molts»: també les paraules destacades.
NOMS = {"whoosh": "Whoosh", "pop": "Pop", "tecla": "Teclat", "brill": "Brillantor", "tic": "Tic"}


# --- La neteja de la veu -------------------------------------------------------------------------

def cadena(nivell: str = "suau") -> str:
    """Els filtres de la neteja (sense igualar el volum)."""
    nr = NIVELLS_SOROLL.get(nivell, NIVELLS_SOROLL["suau"])
    return ("highpass=f=80,"                                   # el brunzit i els cops greus
            f"afftdn=nr={nr}:nf=-40:tn=1,"                     # el soroll de fons (seguint com canvia)
            "equalizer=f=250:t=q:w=1:g=-2,"                    # menys «caixa»
            "equalizer=f=3500:t=q:w=1.2:g=2,"                  # més claredat
            "deesser=i=0.35:m=0.5:f=0.5,"                      # les «s» més suaus
            "acompressor=threshold=-20dB:ratio=2.5:attack=10:release=150:makeup=1.5")


def _volum(mesura: dict | None) -> str:
    base = f"loudnorm=I={VOLUM_OBJECTIU}:TP=-1.5:LRA=11"
    if not mesura:
        return base + ":print_format=json"
    return (base + f":measured_I={mesura['input_i']}:measured_TP={mesura['input_tp']}"
            f":measured_LRA={mesura['input_lra']}:measured_thresh={mesura['input_thresh']}"
            f":offset={mesura['target_offset']}:linear=true,aresample={MOSTREIG}")


def filtre_veu(nivell: str, mesura: dict | None) -> str:
    """La neteja sencera; amb `mesura` (la primera passada), la definitiva."""
    return f"{cadena(nivell)},{_volum(mesura)}"


def llegeix_mesura(sortida_ffmpeg: str) -> dict:
    """El JSON que escriu loudnorm a la primera passada."""
    inici = sortida_ffmpeg.rfind("{")
    final = sortida_ffmpeg.rfind("}")
    if inici < 0 or final < inici:
        raise RuntimeError("No he pogut mesurar el volum de la veu")
    dades = json.loads(sortida_ffmpeg[inici:final + 1])
    if any(not math.isfinite(float(dades[k])) for k in ("input_i", "input_tp", "input_lra", "input_thresh")):
        raise RuntimeError("La veu és massa fluixa per mesurar-ne el volum")
    return dades


def mostra(video: Path, inici: float, desti: Path, nivell: str | None, durada: float = 10.0) -> Path:
    """Uns segons de la veu (per escoltar-la abans i després de netejar-la a la pàgina)."""
    desti.parent.mkdir(parents=True, exist_ok=True)
    entrada = ["ffmpeg", "-v", "error", "-y", "-ss", f"{inici:.3f}", "-t", f"{durada:.3f}", "-i", str(video), "-vn"]
    temporal = desti.with_suffix(".tmp" + desti.suffix)
    if nivell:
        mesura_ordre = ["ffmpeg", "-v", "info", *entrada[3:]]  # loudnorm diu la mesura amb -v info
        primera = subprocess.run([*mesura_ordre, "-af", filtre_veu(nivell, None), "-f", "null", "-"],
                                 capture_output=True, text=True)
        mesura = llegeix_mesura(primera.stderr)
        filtre = ["-af", filtre_veu(nivell, mesura)]
    else:
        filtre = []
    subprocess.run([*entrada, *filtre, "-ac", "1", "-c:a", "aac", "-b:a", "128k", str(temporal)],
                   check=True, capture_output=True)
    temporal.replace(desti)
    return desti


# --- Els efectes de so ------------------------------------------------------------------------------
# Cada so és una llista de mostres entre -1 i 1, a 48 kHz. Sempre surten iguals (llavor fixa).

def _soroll(n: int, llavor: int) -> list[float]:
    r = random.Random(llavor)
    return [r.uniform(-1, 1) for _ in range(n)]


def _whoosh() -> list[float]:
    """Aire que passa: soroll filtrat que s'obre i es tanca."""
    n = int(0.42 * MOSTREIG)
    soroll, sortida = _soroll(n, 7), []
    baix = baix2 = alt = 0.0
    for i, x in enumerate(soroll):
        p = i / n
        tall = 250 + 1800 * math.sin(math.pi * min(1.0, p * 1.15)) ** 2  # el filtre s'obre i es tanca
        a = 1 - math.exp(-2 * math.pi * tall / MOSTREIG)
        baix += a * (x - baix)       # dos filtres seguits: els aguts cauen de pressa
        baix2 += a * (baix - baix2)
        alt += 0.02 * (baix2 - alt)
        envolupant = (p / 0.6) ** 2 if p < 0.6 else ((1 - p) / 0.4) ** 1.5
        sortida.append((baix2 - alt) * envolupant)
    return sortida


def _pop() -> list[float]:
    """Una bombolla que esclata: un to que cau de pressa."""
    n = int(0.12 * MOSTREIG)
    fase, sortida = 0.0, []
    for i in range(n):
        t = i / MOSTREIG
        fase += 2 * math.pi * (950 * math.exp(-t * 28) + 260) / MOSTREIG
        sortida.append(math.sin(fase) * math.exp(-t * 32) * min(1.0, t / 0.002) * 0.75)
    return sortida


def _tecla(variant: int = 0) -> list[float]:
    """Una tecla de màquina d'escriure: un cop sec i curt."""
    n = int(0.04 * MOSTREIG)
    soroll, sortida, abans = _soroll(n, 100 + variant % 5), [], 0.0
    to = 1900 + 220 * (variant % 3)
    for i, x in enumerate(soroll):
        t = i / MOSTREIG
        aguda = x - abans  # només la part aguda del soroll
        abans = x
        sortida.append((aguda * 0.5 + math.sin(2 * math.pi * to * t) * 0.35) * math.exp(-t * 160))
    return sortida


def _brill() -> list[float]:
    """Una campaneta suau per quan surt el títol."""
    n = int(0.8 * MOSTREIG)
    sortida = []
    for i in range(n):
        t = i / MOSTREIG
        to = (math.sin(2 * math.pi * 1568 * t) + 0.6 * math.sin(2 * math.pi * 2093 * t)
              + 0.25 * math.sin(2 * math.pi * 3136 * t))
        sortida.append(to * math.exp(-t * 5.5) * min(1.0, t / 0.004) * 0.22)
    return sortida


def _tic() -> list[float]:
    n = int(0.06 * MOSTREIG)
    return [math.sin(2 * math.pi * 1750 * i / MOSTREIG) * math.exp(-i / MOSTREIG * 70) * 0.3 for i in range(n)]


FABRICATS = {"whoosh": _whoosh, "pop": _pop, "tecla": _tecla, "brill": _brill, "tic": _tic}
# El volum de cada so fabricat (el pic), perquè cap no destaqui més del compte sota la veu.
PICS = {"whoosh": 0.5, "pop": 0.5, "tecla": 0.3, "brill": 0.35, "tic": 0.3}


def _a_pic(mostres: list[float], pic: float) -> list[float]:
    maxim = max((abs(m) for m in mostres), default=0.0)
    return [m * pic / maxim for m in mostres] if maxim else mostres


def _propi(nom: str) -> Path | None:
    """El so que la persona ha posat a ~/.tallat/sons/ amb aquest nom, si n'hi ha."""
    if not SONS_PROPIS.is_dir():
        return None
    return next((p for p in sorted(SONS_PROPIS.iterdir())
                 if p.stem.lower() == nom and p.suffix.lower() in {".wav", ".mp3", ".m4a", ".aif", ".aiff", ".caf"}), None)


def _llegeix(path: Path) -> list[float]:
    cru = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-t", "3", "-ac", "1", "-ar", str(MOSTREIG),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    mostres = array.array("h")
    mostres.frombytes(cru[: len(cru) // 2 * 2])
    return [m / 32768 for m in mostres]


def so(nom: str, variant: int = 0) -> list[float]:
    propi = _propi(nom)
    if propi:
        return _llegeix(propi)
    return _a_pic(_tecla(variant) if nom == "tecla" else FABRICATS[nom](), PICS[nom])


def empremta_sons() -> str:
    """Canvia si la persona posa, treu o canvia algun so propi."""
    propis = [f"{p.name}:{p.stat().st_mtime_ns}" for p in sorted(SONS_PROPIS.iterdir())] if SONS_PROPIS.is_dir() else []
    return VERSIO_SONS + "|" + "|".join(propis)


# --- On sona cada efecte ---------------------------------------------------------------------------

def _lletres_titol(titol: dict, animacio: str) -> list[float]:
    """Els moments de cada lletra del títol a màquina d'escriure (la mateixa fórmula que
    pagina/subtitols.js: si en canvies una, canvia l'altra)."""
    linies = []
    for linia in titol["text"].split("\n"):
        linia = linia.strip()
        if linia:
            linies.append("".join(tros for tros in linia.split("*")))
    total = sum(len(l) for l in linies) or 1
    inici = float(titol["inici"])
    final = max(inici + 0.2, float(titol["final"]))
    pas = min(0.06, max(0.015, ((final - inici) * 0.55) / total))
    ara, moments = inici + 0.2, []
    for k, linia in enumerate(linies):
        for _ in linia:
            moments.append(ara)
            ara += pas
        if k + 1 < len(linies):
            ara += pas * 3
    return moments


def esdeveniments(brolls: list[dict], stickers: list[dict], titol: dict | None, animacio_titol: str,
                  linies_sub: list[dict] | None, quants: str) -> list[dict]:
    """Tots els efectes possibles d'un vídeo: [{clau, nom, so, t, moments}] (sense mirar els apagats).
    `moments`: on sona (el títol a màquina en té un per lletra)."""
    if quants == "cap":
        return []
    llista = []
    if titol:
        if animacio_titol == "maquina":
            llista.append({"clau": "titol", "nom": "Títol (teclat)", "so": "tecla", "t": titol["inici"],
                           "moments": _lletres_titol(titol, animacio_titol)})
        else:
            llista.append({"clau": "titol", "nom": "Títol", "so": "brill", "t": titol["inici"],
                           "moments": [titol["inici"] + 0.05]})
    for b in brolls:
        # El whoosh arriba al màxim just quan entra el b-roll.
        llista.append({"clau": f"broll:{b['id']}", "nom": "B-roll", "so": "whoosh", "t": b["inici"],
                       "moments": [max(0.0, b["inici"] - 0.25)]})
    for st in stickers:
        llista.append({"clau": f"sticker:{st['id']}", "nom": "Sticker", "so": "pop", "t": st["inici"],
                       "moments": [st["inici"]]})
    if quants == "molts":
        for linia in linies_sub or []:
            for w in linia["paraules"]:
                if w.get("clau"):
                    llista.append({"clau": f"clau:{w['id']}", "nom": f"«{w['text']}»", "so": "tic", "t": w["inici"],
                                   "moments": [w["inici"]]})
    return sorted(llista, key=lambda e: e["t"])


def pista(efectes: list[dict], durada: float, volum: float, desti: Path) -> Path:
    """Escriu la pista amb tots els efectes al seu moment (WAV mono de 48 kHz, del llarg del muntatge)."""
    n = max(1, int(durada * MOSTREIG))
    barreja = [0.0] * n
    sons: dict[tuple, list[float]] = {}
    for e in efectes:
        for k, t in enumerate(e["moments"]):
            clau = (e["so"], k % 5 if e["so"] == "tecla" else 0)
            if clau not in sons:
                sons[clau] = so(*clau)
            mostres, inici = sons[clau], int(t * MOSTREIG)
            for i, m in enumerate(mostres[: max(0, n - inici)]):
                if inici + i >= 0:
                    barreja[inici + i] += m * volum
    sortida = array.array("h", (int(max(-1.0, min(1.0, m)) * 32767) for m in barreja))
    desti.parent.mkdir(parents=True, exist_ok=True)
    temporal = desti.with_suffix(".tmp.wav")
    with wave.open(str(temporal), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(MOSTREIG)
        w.writeframes(sortida.tobytes())
    temporal.replace(desti)
    return desti


def empremta(efectes: list[dict], durada: float, volum: float) -> str:
    dades = json.dumps([[e["so"], [round(t, 3) for t in e["moments"]]] for e in efectes]) + f"|{durada:.3f}|{volum}"
    return hashlib.sha1((dades + empremta_sons()).encode()).hexdigest()[:12]


def mostra_efecte(nom: str, carpeta: Path) -> Path:
    """Un efecte sol (per escoltar-lo a la pàgina), tal com sonarà: el de tallat o el propi."""
    empremta_nom = hashlib.sha1((nom + empremta_sons()).encode()).hexdigest()[:8]
    desti = carpeta / f"so-{nom}-{empremta_nom}.wav"
    if not desti.exists():
        for vell in carpeta.glob(f"so-{nom}-*.wav") if carpeta.is_dir() else []:
            vell.unlink(missing_ok=True)
        moments = [0.05 + k * 0.07 for k in range(8)] if nom == "tecla" else [0.05]
        pista([{"so": nom, "moments": moments}], 1.2, 1.0, desti)
    return desti
