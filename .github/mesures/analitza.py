"""Què s'ha sentit de debò a la pàgina: compara el so enregistrat amb l'original i treu les xifres.

    python analitza.py CARPETA_DEL_VIDEO CARPETA_DE_LA_PROVA
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mesura  # noqa: E402

MOSTREIG = mesura.MOSTREIG


def localitza(rec: np.ndarray, ref: np.ndarray) -> list[tuple[float, float, float]]:
    """Per a cada finestra de 100 ms amb so: de quin punt de l'original ve. A 8 kHz (la banda arriba a 3 kHz)."""
    p = rec[::6]
    r = ref[::6]
    sr = 8000
    win, hop = int(0.1 * sr), int(0.05 * sr)
    mida = int(2 ** np.ceil(np.log2(len(r) + win)))
    espectre = np.fft.rfft(r, mida)
    energia = np.cumsum(np.concatenate(([0.0], r.astype(np.float64) ** 2)))
    fin = energia[win:] - energia[:-win]
    rms = np.array([np.sqrt(np.mean(p[i:i + win] ** 2)) for i in range(0, max(1, len(p) - win), hop)])
    if not len(rms) or rms.max() <= 0:
        return []
    llindar = 0.12 * float(np.percentile(rms[rms > 1e-5], 90)) if (rms > 1e-5).any() else 1
    punts, darrer = [], None
    for n, i in enumerate(range(0, max(1, len(p) - win), hop)):
        if rms[n] < llindar:
            darrer = None
            continue
        seg = p[i:i + win]
        norma_seg = float((seg.astype(np.float64) ** 2).sum())
        trobat = None
        if darrer is not None:  # el més probable: continua on era
            c = darrer + hop
            a, b = max(0, c - 40), min(len(r), c + win + 40)
            local = r[a:b]
            if len(local) >= win:
                corr = np.correlate(local, seg, "valid")
                e = np.cumsum(np.concatenate(([0.0], local.astype(np.float64) ** 2)))
                f = e[win:] - e[:-win]
                ncc = corr / np.sqrt(np.maximum(f, 1e-12) * max(norma_seg, 1e-12))
                k = int(np.argmax(ncc))
                if ncc[k] >= 0.45:
                    trobat = (a + k, float(ncc[k]))
        if trobat is None:
            corr = np.fft.irfft(espectre * np.conj(np.fft.rfft(seg, mida)), mida)[:len(fin)]
            ncc = corr / np.sqrt(np.maximum(fin, 1e-12) * max(norma_seg, 1e-12))
            ncc[fin < 0.02 * fin.max()] = 0
            k = int(np.argmax(ncc))
            trobat = (k, float(ncc[k]))
        if trobat[1] >= 0.35:
            punts.append((i / sr, trobat[0] / sr, trobat[1]))
            darrer = trobat[0]
        else:
            darrer = None
    return punts


def sense_casualitats(punts: list) -> list:
    """Una finestra que troba per casualitat un altre lloc de l'original dura un instant; el que sona de debò, no."""
    tandes: list[list] = []
    for x in punts:
        if tandes and abs((x[0] - x[1]) - (tandes[-1][-1][0] - tandes[-1][-1][1])) < 0.03:
            tandes[-1].append(x)
        else:
            tandes.append([x])
    return [x for t in tandes if len(t) >= 3 for x in t]


def trams_muntatge(trams: list) -> list[tuple[float, float, float, float, float]]:
    """(inici, final, so inici, so final, moment al muntatge)"""
    t, sortida = 0.0, []
    for x in trams:
        a, b = x[0], x[1]
        sa, sb = (x[2], x[3]) if len(x) >= 4 else (a, b)
        sortida.append((a, b, sa, sb, t))
        t += b - a
    return sortida


def analitza(font: mesura.Font, carpeta: Path) -> dict:
    d = json.loads((carpeta / "dades.json").read_text(encoding="utf-8"))
    res = {k: d.get(k) for k in ("motor", "versio", "cpu", "escenari", "error", "goto_ms", "pot", "estat_captura", "espera_continu_ms", "continu_no_arriba", "ha_arribat_al_final", "paraules", "total_ms", "memoriaJS", "paraula_treta", "qualitat", "error_clic", "error_tria", "recursos")}
    res["fcp_ms"], res["dom_ms"], res["load_ms"] = d.get("fcp"), d.get("dom"), d.get("load")
    marques = d.get("marques", {})
    res["text_ms"], res["video_llest_ms"], res["continu_llest_ms"] = (round(marques[k]) if marques.get(k) else None for k in ("text", "video", "continu"))
    ev = d.get("ev", [])
    clic = next((e for e in ev if e["tipus"] == "clic" and e.get("id") in ("play", "gran-play") or e["tipus"] == "clic" and "play" in str(e.get("id"))), None)
    res["clic_ms"] = clic["t"] if clic else None
    despres = [e for e in ev if clic and e["t"] >= clic["t"]]
    fi = next((e["t"] for e in ev if e["tipus"] == "fi"), None)
    primer_sona = next((e for e in despres if e["tipus"] == "v:playing"), None)
    res["del_clic_a_playing_ms"] = round(primer_sona["t"] - clic["t"]) if primer_sona and clic else None
    # Quan es deixa de carregar: els «waiting» després de començar a sonar, a tots dos vídeos
    if primer_sona:
        res["waiting"] = sum(1 for e in despres if e["tipus"] == "v:waiting" and e["t"] > primer_sona["t"] + 100)
    res["stalled"] = sum(1 for e in despres if e["tipus"] == "v:stalled")
    res["seeks"] = sum(1 for e in despres if e["tipus"] == "v:seeking")
    res["fil_ocupat_max_ms"] = max((e["ms"] for e in despres if e["tipus"] == "fil-ocupat"), default=0)
    res["fil_ocupat_n"] = sum(1 for e in despres if e["tipus"] == "fil-ocupat")
    res["errors_js"] = [e for e in ev if e["tipus"] in ("error-js", "promesa-rebutjada")][:5]
    res["consola"] = [c for c in d.get("consola", []) if c["tipus"] != "warning"][:5]
    ticks = [t for t in d.get("ticks", []) if clic and t[0] >= clic["t"]]
    res["ticks"] = len(ticks)
    if ticks:
        # Temps mirant el rètol «Preparant…» i la rodeta «Carregant…», mentre sona o espera
        pas = np.diff([t[0] for t in ticks], append=ticks[-1][0])
        res["preparant_s"] = round(float(sum(p for p, t in zip(pas, ticks) if t[5])) / 1000, 2)
        res["carregant_s"] = round(float(sum(p for p, t in zip(pas, ticks) if t[6])) / 1000, 2)
        # Quin vídeo sonava: si ha passat al continu i quan
        amb_m = [t for t in ticks if t[4] and not t[4][1] and not t[4][5]]
        res["continu_sonant_des_de_ms"] = round(amb_m[0][0] - clic["t"]) if amb_m else None
    trams = d.get("trams") or []
    res["trams"] = len(trams)
    res["durada_final"] = d.get("duradaFinal")
    so_fitxer = carpeta / "so.f32"
    if not so_fitxer.exists() or so_fitxer.stat().st_size == 0 or not trams:
        return res
    rec = np.fromfile(so_fitxer, dtype=np.float32)
    if d.get("mostreig") and d["mostreig"] != MOSTREIG:
        res["avis_mostreig"] = d["mostreig"]
    rec = mesura.banda(rec)
    res["so_enregistrat_s"] = round(len(rec) / MOSTREIG, 1)
    primer = (d.get("primerFrame") or 0) / MOSTREIG
    # Temps de l'àudio → temps de l'enregistrament
    t_clic = (clic.get("audio") - primer) if clic and clic.get("audio") is not None else None
    if t_clic is not None:
        finestra = int(0.01 * MOSTREIG)
        desde = max(0, int(t_clic * MOSTREIG))
        rms = np.array([np.sqrt(np.mean(rec[i:i + finestra] ** 2)) for i in range(desde, max(desde + 1, len(rec) - finestra), finestra)])
        so_i = np.where(rms > max(1e-3, 0.02 * (rms.max() if len(rms) else 0)))[0]
        res["del_clic_a_so_ms"] = round(float(so_i[0] * 10)) if len(so_i) else None
    flaixos = np.array(font.dades["flaixos"])
    # Els xiulets de prova són tots iguals: una finestra que en toqui un pot trobar el de qualsevol altre flaix.
    punts = sense_casualitats([x for x in localitza(rec, font.ref) if not np.any((flaixos > x[1] - 0.04) & (flaixos < x[1] + 0.14))])
    res["finestres_reconegudes"] = len(punts)
    if not punts:
        return res

    muntatge = trams_muntatge(trams)
    paraules = font.paraules
    fora = []  # paraules que no són a cap tros
    treta = d.get("paraula_treta")
    t_treta = None
    if treta is not None:
        e_tr = next((e for e in ev if e["tipus"] == "treta"), None)
        if e_tr and e_tr.get("audio") is not None:
            t_treta = e_tr["audio"] - primer
    for p in paraules:
        if not any(sa < p["final"] and p["inici"] < sb for _, _, sa, sb, _ in muntatge):
            fora.append(p)

    def on(t_src):
        for a, b, sa, sb, m in muntatge:
            if sa - 0.02 <= t_src < sb + 0.02:
                return m + (t_src - a)
        return None

    sonades, desfases, fora_munt = [], [], []
    per_paraula: dict[int, int] = {}
    pos_paraula = np.array([p["inici"] for p in paraules])
    for t_rec, t_src, ncc in punts:
        centre = t_src + 0.05
        k = int(np.searchsorted(pos_paraula, centre)) - 1
        if 0 <= k < len(paraules) and paraules[k]["inici"] + 0.03 <= centre <= paraules[k]["final"] - 0.03:
            pid = paraules[k]["id"]
            per_paraula[pid] = per_paraula.get(pid, 0) + 1
            esta_fora = any(q["id"] == pid for q in fora)
            if esta_fora:
                sonades.append({"t": round(t_rec, 2), "paraula": pid, "src": round(t_src, 2), "corr": round(ncc, 2), "despres_de_treure": t_treta is None or t_rec > t_treta})
        m = on(centre)
        if m is not None:
            desfases.append((t_rec, t_rec + 0.05 - m))
        else:
            fora_munt.append((round(t_rec, 2), round(centre, 2)))
    res["paraules_tretes_buscades"] = len(fora)
    tretes_sonades = {x["paraula"] for x in sonades if x["despres_de_treure"]}
    res["paraules_tretes_que_sonen"] = len(tretes_sonades)
    res["exemples_sonen"] = [x for x in sonades if x["despres_de_treure"]][:8]
    res["finestres_fora_del_muntatge"] = len(fora_munt)
    if treta is not None:
        res["treta_sona_despres"] = any(x["paraula"] == treta and x["despres_de_treure"] for x in sonades)
        res["treta_sona_mai"] = any(x["paraula"] == treta for x in sonades)
    # Encallades que s'oien: el desfasament entre el so i el muntatge fa un salt. Salt positiu = s'ha aturat.
    encallades, enrere, perdut = [], [], 0.0
    for (t0, d0), (t1, d1) in zip(desfases, desfases[1:]):
        salt = d1 - d0
        if salt > 0.08:
            encallades.append({"t": round(t1, 2), "ms": round(salt * 1000)})
            perdut += salt
        elif salt < -0.08:
            enrere.append({"t": round(t1, 2), "ms": round(salt * 1000)})
    res["encallades_audibles"] = len(encallades)
    res["encallades_ms_total"] = round(perdut * 1000)
    res["encallada_max_ms"] = max((x["ms"] for x in encallades), default=0)
    res["exemples_encallades"] = encallades[:10]
    res["salts_endavant_audibles"] = len(enrere)
    res["exemples_salts_endavant"] = enrere[:8]
    # Paraules que tocava sentir i no s'han sentit (fins on ha arribat el so)
    if desfases:
        fins_munt = desfases[-1][0] + 0.05 - desfases[-1][1]
        falten = []
        for p in paraules:
            m = on((p["inici"] + p["final"]) / 2)
            if m is None or m > fins_munt - 0.5 or p["final"] - p["inici"] < 0.24 or np.any((flaixos > p["inici"] - 0.05) & (flaixos < p["final"] + 0.05)):
                continue
            if not any(q["id"] == p["id"] for q in fora) and per_paraula.get(p["id"], 0) == 0 and p["id"] != treta:
                falten.append(p["id"])
        res["paraules_que_tocava_i_no_sonen"] = len(falten)
        res["exemples_falten"] = falten[:12]
        res["muntatge_sentit_s"] = round(float(fins_munt), 1)
    # Fuita al final de cada tros: el so segueix més enllà del tall?
    fuites = []
    fi_src = [(sb, m + (b - a)) for a, b, sa, sb, m in muntatge]
    # Per a cada segment continu: on acaba a l'original
    seg_fi = []
    for (t0, s0, _), (t1, s1, _) in zip(punts, punts[1:]):
        if abs((s1 - t1) - (s0 - t0)) > 0.01:
            seg_fi.append((t0, s0))
    for t_rec, s_rec in seg_fi:
        final_src = s_rec + 0.1
        sb_prop = min(fi_src, key=lambda x: abs(x[0] - final_src))[0]
        offset = t_rec - s_rec
        # Mira de 20 en 20 ms, més enllà del tall, si l'enregistrament encara coincideix amb l'original
        k, durada = 0, 0.0
        while k < 20:
            ts = sb_prop + 0.005 + k * 0.02
            tr = ts + offset
            a, c = int(tr * MOSTREIG), int(ts * MOSTREIG)
            n = int(0.02 * MOSTREIG)
            if a < 0 or a + n > len(rec) or c + n > len(font.ref):
                break
            x, y = rec[a:a + n], font.ref[c:c + n]
            nx, ny = np.linalg.norm(x), np.linalg.norm(y)
            if nx < 1e-5 or ny < 1e-5 or float(np.dot(x, y) / (nx * ny)) < 0.6:
                break
            durada += 0.02
            k += 1
        fuites.append(round(durada * 1000))
    res["talls_passats"] = len(fuites)
    res["fuita_max_ms"] = max(fuites, default=0)
    res["fuites_de_mes_de_40ms"] = sum(1 for x in fuites if x > 40)
    return res


if __name__ == "__main__":
    sortida = analitza(mesura.Font(Path(sys.argv[1])), Path(sys.argv[2]))
    print(json.dumps(sortida, ensure_ascii=False, indent=1, default=str))
