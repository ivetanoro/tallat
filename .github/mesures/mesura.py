"""Mesura un vídeo que surt de tallat contra el vídeo inventat d'on ve (fabrica.py).

Imatge: el codi de barres de cada fotograma diu de quin fotograma de l'original ve.
So: el soroll no es repeteix, i amb una correlació es troba de quin punt de l'original ve cada tros.
Sincronisme: al mateix moment de l'original hi ha un flaix i un xiulet; es mira quant se separen.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

import fabrica

MOSTREIG = fabrica.MOSTREIG
BANDA = 100, 3000  # la banda que l'AAC guarda (a dalt, a poc bitrate, s'inventa el soroll)
PETIT = 54, 96


class Font:
    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)
        self.dades = json.loads((self.carpeta / "mesura.json").read_text(encoding="utf-8"))
        self.temps = np.array(self.dades["temps"])
        self.fps = eval_fps(self.dades["fps"])
        self.ref = banda(np.fromfile(self.carpeta / "so-original.f32", dtype=np.float32))
        self.paraules = self.dades["paraules"]
        self.flaixos = self.dades["flaixos"]
        self.video = self.carpeta / self.dades["video"]


def eval_fps(fps: str) -> float:
    a, _, b = str(fps).partition("/")
    return float(a) / float(b or 1)


def banda(x: np.ndarray) -> np.ndarray:
    n = len(x)
    if n == 0:
        return x
    espectre = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / MOSTREIG)
    espectre[(f < BANDA[0]) | (f > BANDA[1])] = 0
    return np.fft.irfft(espectre, n).astype(np.float32)


def info(fitxer: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,start_time,duration,nb_frames,avg_frame_rate,width,height",
                        "-show_entries", "format=duration", "-of", "json", str(fitxer)], capture_output=True, text=True, encoding="utf-8", check=True)
    d = json.loads(r.stdout)
    sortida = {"format": float(d.get("format", {}).get("duration", 0) or 0)}
    for s in d["streams"]:
        sortida[s["codec_type"]] = s
    return sortida


def so_de(fitxer: Path) -> tuple[np.ndarray, float]:
    """(mostres mono a 48 kHz, en quin moment del fitxer comencen)."""
    inf = info(fitxer)
    inici = float(inf.get("audio", {}).get("start_time") or 0)
    cru = subprocess.run(["ffmpeg", "-v", "error", "-i", str(fitxer), "-map", "0:a:0", "-ac", "1", "-ar", str(MOSTREIG), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(cru, dtype=np.float32), inici


def imatges_de(fitxer: Path, retalla: bool = False) -> dict:
    """Per a cada fotograma del fitxer: quan surt, de quin fotograma ve (-1 si no es llegeix) i si hi ha flaix."""
    w, h = PETIT
    filtre = (f"crop=trunc(ih*9/16/2)*2:ih," if retalla else "") + f"scale={w}:{h}:flags=area,format=gray"
    cru = subprocess.run(["ffmpeg", "-v", "error", "-i", str(fitxer), "-map", "0:v:0", "-vf", filtre, "-fps_mode", "passthrough", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    fotos = np.frombuffer(cru, dtype=np.uint8).reshape(-1, h, w)
    pts = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(fitxer)],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    temps = np.array(sorted(float(x.strip().rstrip(",")) for x in pts.split() if x.strip().rstrip(",") not in ("", "N/A")))
    n = min(len(fotos), len(temps))
    pesos = 1 << np.arange(16)
    numeros = np.full(n, -1, dtype=np.int64)
    bits = np.zeros((n, fabrica.BITS), dtype=np.int64)
    for k in range(fabrica.BITS):
        c, r = k % fabrica.COLUMNES, k // fabrica.COLUMNES
        x = int(w * (0.20 + (c + 0.5) * fabrica.BLOC_X))
        y = int(h * (0.35 + (r + 0.5) * fabrica.BLOC_Y))
        bits[:, k] = fotos[:n, y - 1:y + 2, x - 1:x + 2].mean(axis=(1, 2)) > 128
    valors = (bits[:, :16] * pesos).sum(axis=1)
    comprova = (bits[:, 16:] * (1 << np.arange(4))).sum(axis=1)
    bones = sum((valors >> s) & 15 for s in (0, 4, 8, 12)) & 15 == comprova
    numeros[bones] = valors[bones]
    franja = fotos[:n, int(h * fabrica.FRANJA[0]) + 1:int(h * fabrica.FRANJA[1]) - 1, :].mean(axis=(1, 2))
    return {"temps": temps[:n], "numeros": numeros, "flaix": franja > 150}


def _troba(seg: np.ndarray, r: np.ndarray) -> tuple[int, float]:
    """On encaixa més `seg` dins de `r`: (posició, correlació normalitzada de 0 a 1)."""
    m = len(seg)
    if m == 0 or len(r) < m:
        return 0, 0.0
    mida = int(2 ** np.ceil(np.log2(len(r) + m)))
    corr = np.fft.irfft(np.fft.rfft(r, mida) * np.conj(np.fft.rfft(seg, mida)), mida)[:len(r) - m + 1]
    energia = np.cumsum(np.concatenate(([0.0], r.astype(np.float64) ** 2)))
    finestra = energia[m:] - energia[:-m]
    norma = np.sqrt(np.maximum(finestra, 1e-12) * max(float((seg.astype(np.float64) ** 2).sum()), 1e-12))
    ncc = corr / norma
    # Una finestra quasi muda no compta: en silenci, la correlació normalitzada no vol dir res.
    ncc[finestra < 0.02 * finestra.max()] = 0
    k = int(np.argmax(ncc))
    return k, float(ncc[k])


def error_so(so_: np.ndarray, ref: np.ndarray, t_sortida: float, t_ref: float, llarg: float, marge: float = 0.2) -> tuple[float, float]:
    """(error en ms, correlació): del tros del fitxer a `t_sortida`, de quin punt de l'original ve, comparat amb `t_ref`."""
    a = int(round(t_sortida * MOSTREIG))
    m = int(llarg * MOSTREIG)
    seg = so_[max(0, a):max(0, a) + m]
    c = int(round(t_ref * MOSTREIG))
    d = int(marge * MOSTREIG)
    r0 = max(0, c - d)
    k, ncc = _troba(seg, ref[r0:c + m + d])
    return (r0 + k - c) / MOSTREIG * 1000, ncc


def mesura_so(fitxer: Path, font: Font, trams: list, inici_so: float = 0.0) -> dict:
    """`trams`: [inici, final, inici del so, final del so] en segons de l'original, en l'ordre en què sonen."""
    so_, comenca = so_de(fitxer)
    so_ = banda(so_)
    errors, baixes, paraules_justes, retallades, fuites = [], [], 0, [], []
    sortida = 0.0
    talls = []
    # Quant va desplaçat tot el so (positiu: el so que surt ve de més endavant de l'original; negatiu: va tard).
    # Les comprovacions fines (paraules senceres, silencis) es fan amb aquest desplaçament descomptat.
    mostra = [x for x in trams if (x[3] - x[2] if len(x) == 4 else x[1] - x[0]) >= 0.5][:9]
    t_acum, desplacaments = 0.0, []
    for t in trams:
        a, b, sa, sb = t if len(t) == 4 else (*t, *t)
        if t in mostra:
            e0, n0 = error_so(so_, font.ref, t_acum + (sa - a) + 0.1 - comenca, sa + 0.1, 0.25)
            if n0 >= 0.3:
                desplacaments.append(e0)
        t_acum += b - a
    decalatge = float(np.median(desplacaments)) / 1000 if desplacaments else 0.0
    # Els xiulets de prova són forts i l'AAC els escampa uns mil·lisegons: això no és cap fuita del que s'ha tret.
    flaixos = font.dades["flaixos"]
    xiulets, t_acum = [], 0.0
    for t in trams:
        a, b, sa, sb = t if len(t) == 4 else (*t, *t)
        xiulets += [t_acum + f - a for f in flaixos if sa <= f < sb]
        t_acum += b - a
    for i, t in enumerate(trams):
        a, b, sa, sb = t if len(t) == 4 else (*t, *t)
        fi_sortida = sortida + (b - a)
        decalatge_tram = decalatge  # si el so s'ha anat desplaçant, cada tros es mira on és de debò
        finestra = min(0.25, (sb - sa) - 0.024)
        if finestra >= 0.05:
            # Just després de començar i just abans d'acabar (sense els 10 ms del fos).
            e1, n1 = error_so(so_, font.ref, sortida + (sa - a) + 0.012 - comenca, sa + 0.012, finestra)
            e2, n2 = error_so(so_, font.ref, sortida + (sb - a) - 0.012 - finestra - comenca, sb - 0.012 - finestra, finestra)
            talls.append({"tram": i, "error_inici_ms": round(e1, 2), "error_final_ms": round(e2, 2), "corr_inici": round(n1, 3), "corr_final": round(n2, 3),
                          "original": [round(a, 4), round(b, 4)], "sortida": round(sortida, 4)})
            for e, n in ((e1, n1), (e2, n2)):
                (errors if n >= 0.3 else baixes).append(e)
            if n2 >= 0.5 or n1 >= 0.5:
                decalatge_tram = (e2 if n2 >= 0.5 else e1) / 1000
        # Silenci on hi ha un bocí de fotograma de més: aquí no hauria de sonar res del que s'ha tret.
        for x0, x1 in ((sortida, sortida + (sa - a)), (sortida + (sb - a), fi_sortida)):
            if x1 - x0 >= 0.003 and not any(x0 - 0.14 < w < x1 + 0.1 for w in xiulets):
                tros = so_[int((x0 - decalatge_tram - comenca) * MOSTREIG) + 2:int((x1 - decalatge_tram - comenca) * MOSTREIG) - 2]
                if len(tros):
                    fuites.append(20 * np.log10(max(float(np.abs(tros).max()), 1e-6)))
        # Les paraules de les vores han de ser senceres.
        for p in font.paraules:
            if p["inici"] >= sb or p["final"] <= sa:
                continue
            for x, nom in ((p["inici"] + 0.004, "inici"), (p["final"] - 0.029, "final")):
                if not (sa + 0.012 <= x and x + 0.025 <= sb - 0.012):
                    continue
                if not (x - sa < 0.15 or sb - x < 0.15):  # només les de la vora del tros
                    continue
                paraules_justes += 1
                e, n = error_so(so_, font.ref, sortida + (x - a) - decalatge_tram - comenca, x, 0.025, 0.003)
                if n < 0.5:
                    retallades.append({"paraula": p["id"], "on": nom, "corr": round(n, 2)})
        sortida = fi_sortida

    # El que s'ha tret: es busca a tot el fitxer. I, com a control de l'eina, el que s'ha quedat.
    fora_de = []
    conservades = []
    for p in font.paraules:
        centre = (p["inici"] + p["final"]) / 2
        dins = any(t[2 if len(t) == 4 else 0] <= p["inici"] and p["final"] <= t[3 if len(t) == 4 else 1] for t in trams)
        toca = any(t[2 if len(t) == 4 else 0] < p["final"] and p["inici"] < t[3 if len(t) == 4 else 1] for t in trams)
        del centre
        if not toca:
            fora_de.append(p)
        elif dins:
            conservades.append(p)
    sonen, pics = [], []
    # La cerca a tot el fitxer, a 8 kHz (la banda arriba a 3 kHz): deu minuts no costen deu vegades més per paraula.
    petit, ref_petit = so_[::6], font.ref[::6]
    mida = int(2 ** np.ceil(np.log2(len(petit) + 8000)))
    espectre = np.fft.rfft(petit, mida)
    energia = np.cumsum(np.concatenate(([0.0], petit.astype(np.float64) ** 2)))

    def pic(p: dict) -> float:
        # Sense el xiulet de prova: és igual a tot arreu, i trobaria el de qualsevol altre flaix.
        trossos, x0 = [], p["inici"] + 0.02
        for f in flaixos:
            if x0 < f + 0.1 and f - 0.04 < p["final"] - 0.02:
                trossos.append((x0, f - 0.04))
                x0 = f + 0.1
        trossos.append((x0, p["final"] - 0.02))
        x0, x1 = max(trossos, key=lambda x: x[1] - x[0])
        if x1 - x0 < 0.08:
            return 0.0
        seg = ref_petit[int(x0 * 8000):int(x1 * 8000)]
        m = len(seg)
        corr = np.fft.irfft(espectre * np.conj(np.fft.rfft(seg, mida)), mida)[:max(1, len(petit) - m + 1)]
        finestra = energia[m:] - energia[:-m]
        n = min(len(corr), len(finestra))
        valid = finestra[:n] > 0.02 * finestra[:n].max()
        norma = np.sqrt(np.maximum(finestra[:n], 1e-12) * float((seg.astype(np.float64) ** 2).sum()))
        return float((corr[:n] / norma * valid).max())
    for p in fora_de:
        v = pic(p)
        pics.append(v)
        if v > 0.5:  # el soroll de fons de la cerca arriba a 0,30, i una paraula que hi és no baixa de 0,80
            sonen.append({"paraula": p["id"], "corr": round(v, 2)})
    control = [pic(p) for p in conservades[:: max(1, len(conservades) // 12)]]

    abs_err = np.abs(errors) if errors else np.array([0.0])
    return {"decalatge_ms": round(-decalatge * 1000, 2), "talls_mesurats": len(errors), "sense_coincidencia": len(baixes), "error_mediana_ms": round(float(np.median(abs_err)), 2),
            "error_p95_ms": round(float(np.percentile(abs_err, 95)), 2), "error_max_ms": round(float(abs_err.max()), 2),
            "error_mitjana_amb_signe_ms": round(float(np.mean(errors)) if errors else 0, 2),
            "corr_mediana": round(float(np.median([x["corr_inici"] for x in talls] or [0])), 3), "paraules_de_vora_mirades": paraules_justes,
            "paraules_retallades": retallades[:30], "n_retallades": len(retallades),
            "fuita_max_db": round(max(fuites), 1) if fuites else None,
            "trets_buscats": len(fora_de), "trets_que_sonen": sonen, "pic_max_trets": round(max(pics), 3) if pics else None,
            "control_conservats_min": round(min(control), 3) if control else None,
            "detall": talls}


def mesura_imatge(fitxer: Path, font: Font, trams: list, retalla: bool = False) -> dict:
    img = imatges_de(fitxer, retalla)
    temps, numeros = img["temps"], img["numeros"]
    origen = temps[0] if len(temps) else 0
    errors_primer, errors_darrer, errors = [], [], []
    fora, salts, sense_codi = 0, 0, int((numeros < 0).sum())
    sortida = 0.0
    valids = numeros >= 0
    per_tram = []
    n_tots = len(font.temps)
    for i, t in enumerate(trams):
        a, b = t[0], t[1]
        d = b - a
        dins = np.where((temps - origen >= sortida - 1e-4) & (temps - origen < sortida + d - 1e-4))[0]
        sortida += d
        if not len(dins):
            per_tram.append({"tram": i, "cap_fotograma": True})
            continue
        ks = dins[valids[dins]]
        if not len(ks):
            continue
        esperat = a + (temps[ks] - origen - (sortida - d))
        real = font.temps[np.clip(numeros[ks], 0, n_tots - 1)]
        e = (real - esperat) * 1000
        errors.extend(e.tolist())
        errors_primer.append(float(e[0]))
        errors_darrer.append(float(e[-1]))
        per_tram.append({"tram": i, "error_primer_ms": round(float(e[0]), 1), "error_darrer_ms": round(float(e[-1]), 1), "fotogrames": len(ks)})
        fora += int(((real < a - 0.75 / font.fps) | (real > b + 0.25 / font.fps)).sum())
        salts += int((np.diff(numeros[ks]) != 1).sum())
    tot = np.abs(errors) if errors else np.array([0.0])
    vora = np.abs(errors_primer + errors_darrer) if errors_primer else np.array([0.0])
    return {"fotogrames": len(temps), "sense_codi": sense_codi, "trams": len(trams), "error_vora_max_ms": round(float(vora.max()), 1),
            "error_vora_mediana_ms": round(float(np.median(vora)), 1), "error_tots_max_ms": round(float(tot.max()), 1), "fora_del_muntatge": fora,
            "salts_dins_d_un_tram": salts, "trams_amb_error_de_mes_d_un_fotograma": sum(1 for x in errors_primer + errors_darrer if abs(x) > 1000 / font.fps + 1),
            "detall": per_tram, "_img": img}


def sincronisme(fitxer: Path, font: Font, trams: list, img: dict) -> dict:
    """Flaix (imatge) contra xiulet (so): quant se separen, al principi i al final."""
    so_, comenca = so_de(fitxer)
    flaixos = np.where(img["flaix"])[0]
    origen = img["temps"][0] if len(img["temps"]) else 0
    punts = []
    for k in flaixos:
        t_v = img["temps"][k] - origen
        a = int((t_v - 0.25 - comenca) * MOSTREIG)
        b = int((t_v + 0.35 - comenca) * MOSTREIG)
        tros = so_[max(0, a):max(0, b)]
        if len(tros) < MOSTREIG // 10:
            continue
        esp = np.fft.rfft(tros)
        f = np.fft.rfftfreq(len(tros), 1 / MOSTREIG)
        esp[np.abs(f - fabrica.XIULET_HZ) > 300] = 0
        fil = np.fft.irfft(esp, len(tros))
        m = int(0.002 * MOSTREIG)
        env = np.sqrt(np.convolve(fil ** 2, np.ones(m) / m, mode="same"))
        if env.max() < 3 * np.median(env) or env.max() < 1e-4:
            continue
        i = int(np.argmax(env >= 0.5 * env.max()))
        t_a = (max(0, a) + i) / MOSTREIG + comenca - m / 2 / MOSTREIG
        punts.append({"t": round(float(t_v), 3), "diferencia_ms": round((t_a - t_v) * 1000, 1)})
    valors = [p["diferencia_ms"] for p in punts]
    if not valors:
        return {"flaixos": 0}
    primers, darrers = valors[:3], valors[-3:]
    return {"flaixos": len(valors), "al_principi_ms": round(float(np.mean(primers)), 1), "al_final_ms": round(float(np.mean(darrers)), 1),
            "max_abs_ms": round(float(np.abs(valors).max()), 1), "punts": punts}


def mesura_fitxer(fitxer: Path, font: Font, trams: list) -> dict:
    inf = info(fitxer)
    v = float(inf.get("video", {}).get("duration") or 0)
    a = float(inf.get("audio", {}).get("duration") or 0)
    img = mesura_imatge(fitxer, font, trams)
    dades_img = img.pop("_img")
    return {"fitxer": fitxer.name, "mb": round(fitxer.stat().st_size / 1e6, 1), "durada_video": v, "durada_so": a,
            "durada_muntatge": round(sum(t[1] - t[0] for t in trams), 3), "fps": inf.get("video", {}).get("avg_frame_rate"),
            "mida": f"{inf.get('video', {}).get('width')}x{inf.get('video', {}).get('height')}",
            "imatge": img, "so": mesura_so(fitxer, font, trams), "sincronisme": sincronisme(fitxer, font, trams, dades_img)}
