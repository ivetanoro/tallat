"""Fabrica un vídeo de mesura inventat: cap persona, cap veu.

Cada fotograma porta el seu número en un codi de barres (blocs blancs i negres al mig) i, de tant en tant, un flaix
a la franja de dalt. El so és soroll amb llavor, que no es repeteix mai, modelat com si fossin paraules, amb un
xiulet just a cada flaix. Així, a qualsevol lloc d'un export es pot saber de quin punt de l'original ve la imatge
i de quin ve el so.

    python fabrica.py CARPETA --nom "vídeo.mp4" --durada 120 --mida 1080x1920 --fps 30 --codec h264
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

MOSTREIG = 48000
# Tot es defineix en fraccions del retall central 9:16: així un vídeo horitzontal, un cop retallat, es llegeix igual.
LLENC = 108, 192  # mida del dibuix (9:16), es fa gran amb píxels nets
COLUMNES, FILES = 5, 4
BITS = COLUMNES * FILES  # 16 per al número i 4 de comprovació
BLOC_X = 0.60 / COLUMNES  # el codi va de 0,20 a 0,80 de l'amplada
BLOC_Y = 0.30 / FILES     # i de 0,35 a 0,65 de l'alçada
FRANJA = 0.05, 0.20       # el flaix, en alçada
CADA_FLAIX = 7.0
XIULET_HZ = 3000
XIULET_S = 0.04


def bits_de(n: int) -> list[int]:
    comprova = sum((n >> k) & 15 for k in (0, 4, 8, 12)) & 15
    valor = (n & 0xFFFF) | (comprova << 16)
    return [(valor >> k) & 1 for k in range(BITS)]


def dibuix(n: int, flaix: bool) -> np.ndarray:
    w, h = LLENC
    f = np.full((h, w), 40, dtype=np.uint8)
    f[int(h * 0.30):int(h * 0.70), int(w * 0.15):int(w * 0.85)] = 128  # el fons del codi
    if flaix:
        f[int(h * FRANJA[0]):int(h * FRANJA[1]), :] = 255
    for k, b in enumerate(bits_de(n)):
        c, r = k % COLUMNES, k // COLUMNES
        x0, y0 = 0.20 + c * BLOC_X, 0.35 + r * BLOC_Y
        f[int(h * (y0 + 0.1 * BLOC_Y)):int(h * (y0 + 0.9 * BLOC_Y)),
          int(w * (x0 + 0.1 * BLOC_X)):int(w * (x0 + 0.9 * BLOC_X))] = 235 if b else 16
    return f


def paraules(durada: float, llavor: int) -> list[dict]:
    """Paraules de durada variable, amb silencis curts i alguna pausa llarga, com quan es parla."""
    atzar = np.random.default_rng(llavor)
    llista, t, n = [], 0.35, 0
    frase = 0
    while True:
        d = float(atzar.uniform(0.18, 0.62))
        if t + d > durada - 0.4:
            return llista
        llista.append({"id": n, "text": f"mot{n}", "inici": round(t, 3), "final": round(t + d, 3), "frase": frase, "confianca": 0.95})
        n += 1
        t += d + float(atzar.uniform(0.04, 0.30))
        if n % 11 == 0:  # final de frase
            llista[-1]["text"] += "."
            frase += 1
            t += float(atzar.uniform(0.25, 0.8))
        if n % 53 == 0:  # una pausa llarga
            t += float(atzar.uniform(1.6, 3.2))


def so(durada: float, llavor: int, mots: list[dict], flaixos: list[float]) -> np.ndarray:
    n = int(durada * MOSTREIG)
    cru = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"anoisesrc=r={MOSTREIG}:color=pink:seed={llavor}:amplitude=1.0",
                          "-t", f"{durada:.6f}", "-ac", "1", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    soroll = np.frombuffer(cru, dtype=np.float32).copy()[:n]
    soroll = np.pad(soroll, (0, max(0, n - len(soroll))))
    soroll /= max(1e-6, float(np.abs(soroll).max()))
    env = np.full(n, 0.012, dtype=np.float32)  # el fons de l'habitació
    rampa = int(0.008 * MOSTREIG)
    for m in mots:
        a, b = int(m["inici"] * MOSTREIG), int(m["final"] * MOSTREIG)
        tros = np.full(b - a, 0.55, dtype=np.float32)
        tros[:rampa] *= np.linspace(0.02, 1, rampa)
        tros[-rampa:] *= np.linspace(1, 0.02, rampa)
        env[a:b] = tros
    senyal = soroll * env
    for t in flaixos:
        a = int(round(t * MOSTREIG))
        m = int(XIULET_S * MOSTREIG)
        if a + m < n:
            senyal[a:a + m] += 0.5 * np.sin(2 * np.pi * XIULET_HZ * np.arange(m) / MOSTREIG)
    return np.clip(senyal, -1, 1)


def temps_fotogrames(n: int, fps: Fraction, vfr: bool, suau: bool = False) -> list[float]:
    if not vfr:
        return [float(k / fps) for k in range(n)]
    f = float(1 / fps)
    if suau:  # amb bona llum: els fotogrames no cauen mai regulars, però la mitjana no es mou
        return [k * f + 0.006 * math.sin(k / 3.7) for k in range(n)]
    # Com un mòbil: a estones baixa a 24 fps, i els fotogrames no cauen mai regulars (la mateixa fórmula que EXPR_VFR).
    return [k * f + (1 / 24 - f) * (300 * (k // 900) + max(0, min(k % 900 - 300, 300))) + 0.008 * math.sin(k / 3.7) for k in range(n)]


def expr_vfr(fps: Fraction, suau: bool = False) -> str:
    f = float(1 / fps)
    if suau:
        return f"settb=1/600,setpts=(N*{f}+0.006*sin(N/3.7)+0.006)/TB"
    return f"settb=1/600,setpts=(N*{f}+({1 / 24 - f})*(300*floor(N/900)+max(0\\,min(mod(N\\,900)-300\\,300)))+0.008*sin(N/3.7)+0.008)/TB"


def te_grafica(codec: str) -> bool:
    """En un Mac virtual no hi ha gràfica: es fa amb el processador."""
    if sys.platform != "darwin":
        return False
    return subprocess.run(["ffmpeg", "-v", "quiet", "-f", "lavfi", "-i", "color=c=gray:s=320x240:d=0.2", "-c:v", f"{codec}_videotoolbox", "-b:v", "1M", "-f", "null", "-"],
                          capture_output=True).returncode == 0


def codificador(codec: str, bitrate: str) -> list[str]:
    if codec == "hevc":
        if te_grafica("hevc"):
            return ["-c:v", "hevc_videotoolbox", "-b:v", bitrate, "-tag:v", "hvc1", "-allow_sw", "1"]
        return ["-c:v", "libx265", "-preset", "ultrafast", "-b:v", bitrate, "-tag:v", "hvc1", "-x265-params", "log-level=error"]
    if te_grafica("h264"):
        return ["-c:v", "h264_videotoolbox", "-b:v", bitrate, "-allow_sw", "1"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-b:v", bitrate]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--nom", default="video.mp4")
    ap.add_argument("--durada", type=float, default=120)
    ap.add_argument("--mida", default="1080x1920", help="la mida visible (amb la rotació ja aplicada)")
    ap.add_argument("--fps", default="30")
    ap.add_argument("--codec", default="h264", choices=["h264", "hevc"])
    ap.add_argument("--bitrate", default="8M")
    ap.add_argument("--rotacio", action="store_true", help="vertical com l'iPhone: desat horitzontal, amb l'etiqueta de girar-lo")
    ap.add_argument("--vfr", action="store_true")
    ap.add_argument("--suau", action="store_true", help="amb --vfr: sense baixar a 24 fps, només fotogrames irregulars")
    ap.add_argument("--deu-bits", action="store_true", help="10 bits i HLG, com el vídeo HDR de l'iPhone")
    ap.add_argument("--llavor", type=int, default=7)
    a = ap.parse_args()

    a.carpeta.mkdir(parents=True, exist_ok=True)
    w, h = (int(x) for x in a.mida.split("x"))
    fps = Fraction(a.fps)
    temps = temps_fotogrames(int(a.durada * float(fps)) + 1, fps, a.vfr, a.suau)
    temps = [t for t in temps if t < a.durada]
    durada = temps[-1] + float(1 / fps)
    # Els flaixos, cada CADA_FLAIX segons, al fotograma que toqui: el xiulet comença just quan el fotograma.
    flaixos_k = sorted({min(range(len(temps)), key=lambda k: abs(temps[k] - t)) for t in np.arange(CADA_FLAIX, durada - 1, CADA_FLAIX)})
    flaixos_t = [temps[k] for k in flaixos_k]
    mots = paraules(durada, a.llavor)
    senyal = so(durada, a.llavor, mots, flaixos_t)

    desti = a.carpeta / a.nom
    wav = a.carpeta / "so-original.f32"
    senyal.tofile(wav)

    # Dibuix → mida real. Si el vídeo és horitzontal, el dibuix va al mig del retall central 9:16.
    fons = []
    if w * 16 > h * 9:
        visible = (h * 9 // 16) // 2 * 2
        fons = [f"scale={visible}:{h}:flags=neighbor,pad={w}:{h}:(ow-iw)/2:0:color=0x282828"]
    else:
        fons = [f"scale={w}:{h}:flags=neighbor"]
    filtres = [*fons, "noise=alls=10:allf=t", "setsar=1"]
    if a.rotacio:
        filtres.append("transpose=2")  # es desa ajagut: l'etiqueta el torna a posar dret
    filtres.append("format=yuv420p10le" if a.deu_bits else "format=yuv420p")
    if a.vfr:
        filtres.append(expr_vfr(fps, a.suau))
    w0, h0 = LLENC
    imatge = a.carpeta / "_imatge.mov"
    ordre = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w0}x{h0}", "-r", str(fps), "-i", "-",
             "-vf", ",".join(filtres), *codificador(a.codec, a.bitrate), "-g", "30"]
    if a.vfr:
        ordre += ["-fps_mode", "passthrough", "-video_track_timescale", "600"]
    if a.deu_bits:
        ordre += ["-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc"]
        if a.codec == "hevc" and te_grafica("hevc"):
            ordre += ["-profile:v", "main10"]
    ordre.append(str(imatge))
    p = subprocess.Popen(ordre, stdin=subprocess.PIPE)
    per_flaix = set(flaixos_k)
    for k in range(len(temps)):
        p.stdin.write(dibuix(k, k in per_flaix).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        sys.exit("ffmpeg no ha pogut fer la imatge")

    entrada = ["-i", str(imatge)]
    if a.rotacio:
        entrada = ["-display_rotation:v:0", "-90", *entrada]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entrada, "-f", "f32le", "-ar", str(MOSTREIG), "-ac", "1", "-i", str(wav),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-ac", "2", "-b:a", "192k", "-shortest", str(desti)], check=True)
    imatge.unlink()

    # Els temps de debò de cada fotograma, tal com han quedat al fitxer.
    sortida = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(desti)],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
    reals = sorted(float(x.strip().rstrip(",")) for x in sortida.split() if x.strip().rstrip(",") not in ("", "N/A"))
    (a.carpeta / "mesura.json").write_text(json.dumps({
        "video": desti.name, "durada": durada, "fps": a.fps, "mida": a.mida, "vfr": a.vfr, "rotacio": a.rotacio, "llavor": a.llavor,
        "flaixos": [reals[k] for k in flaixos_k], "paraules": mots, "temps": reals}, ensure_ascii=False), encoding="utf-8")
    print(f"{desti.name}: {len(reals)} fotogrames, {durada:.1f} s, {desti.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
