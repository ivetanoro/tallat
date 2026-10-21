"""Transcripció en català amb marques de temps per paraula.

Dues fonts del text:
- un SRT (p. ex. exportat de Descript): és la més ràpida i la més fidel (conserva el farciment).
- WhisperX escriu el text. Gratuïta i sense internet, però més lenta i tendeix a esborrar el
  farciment («eh», «mmm»).

El temps de cada paraula el calcula el model de veu català de Softcatalà (el mateix que fa servir
WhisperX; llicència Apache 2.0, i ja el baixa prepara.sh) alineant tot el text contra tot el so, sense
refiar-se dels temps de les frases: els de Descript poden anar uns segons desplaçats, i l'alineació
de WhisperX, frase per frase, estirava les paraules pels silencis i s'equivocava fins a un segon i mig.
Després, les vores de cada paraula es retallen als silencis reals (motor/veu.py). Si no es pot, es fa
com abans, frase per frase amb WhisperX.
"""
from __future__ import annotations

import re
import statistics
import unicodedata
from pathlib import Path

IDIOMA = "ca"
DISPOSITIU = "cpu"


def llegeix_srt(path: Path) -> list[dict]:
    """Retorna les frases d'un SRT com a [{start, end, text}]."""

    def segons(t: str) -> float:
        h, m, rest = t.strip().split(":")
        s, ms = rest.replace(".", ",").split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    frases = []
    for bloc in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        linies = [l for l in bloc.strip().splitlines() if l.strip()]
        temps = next((i for i, l in enumerate(linies) if "-->" in l), None)
        if temps is None:
            continue
        inici, final = linies[temps].split("-->")
        text = " ".join(linies[temps + 1:]).strip()
        if text:
            frases.append({"start": segons(inici), "end": segons(final), "text": text})
    return frases


def _whisperx():
    from motor import entorn
    entorn.llista_de_lletres()
    import whisperx  # import tardà: tarda uns segons a carregar
    return whisperx


def carrega_audio(video: Path):
    """Àudio a 16 kHz per a WhisperX. Agafem sempre la primera pista d'àudio: els iPhone
    n'hi afegeixen una d'àudio espacial que ffmpeg no sap llegir."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-map", "0:a:0", "-vn",
                        "-ac", "1", "-ar", "16000", str(wav)], check=True)
        return _whisperx().load_audio(str(wav))


def alinea(audio, frases: list[dict], avis=print) -> list[dict]:
    """Calcula el temps de cada paraula: [{start, end, text, words: [{word, start, end, score}]}].
    Tot el text contra tot el so; si no es pot (el text no correspon al so…), frase per frase amb WhisperX.
    En tots dos casos, les vores de les paraules es retallen als silencis reals i el temps no va mai enrere."""
    from motor import veu
    try:
        segments = alinea_global(audio, frases)
    except Exception as e:  # noqa: BLE001 — qualsevol problema: l'alineador d'abans
        if avis:
            avis(f"No he pogut alinear tot el text de cop ({e}); ho faig frase per frase.")
        wx = _whisperx()
        model, meta = wx.load_align_model(language_code=IDIOMA, device=DISPOSITIU)
        segments = wx.align(frases, model, meta, audio, DISPOSITIU, return_char_alignments=False)["segments"]
    endarrere = ajusta_temps(segments, veu.mapa(audio))
    if endarrere and avis:
        avis(f"Avís: {endarrere} paraules sortien abans que l'anterior; les he posat just després.")
    return segments


def ajusta_temps(segments: list[dict], veu) -> int:
    """Retalla les vores de cada paraula als silencis reals (retalla_als_silencis) i fa que cap paraula no
    comenci abans que acabi l'anterior (a les gravacions llargues, que s'alineen a trossos, els trossos es
    poden trepitjar). Canvia `segments` i torna quantes paraules anaven enrere més d'una dècima."""
    paraules = [w for seg in segments for w in seg.get("words", [])
                if w.get("start") is not None and w.get("end") is not None]
    temps = retalla_als_silencis([(w["start"], w["end"]) for w in paraules], veu,
                                 textos=[w.get("word", "") for w in paraules])
    for w, (a, b) in zip(paraules, temps):
        w["start"], w["end"] = a, b
    endarrere, fi = 0, 0.0
    for w in paraules:
        if w["start"] < fi - 0.1:
            # Anava enrere: es posa just després de l'anterior, però aquest temps ja no és el de l'alineador.
            # Sense confiança (None) surt marcada com a aproximada (revisió de Codex).
            endarrere += 1
            w["score"] = None
        w["start"] = max(w["start"], fi)
        w["end"] = fi = max(w["end"], w["start"])
    for seg in segments:
        # Si hi ha paraules sense temps (números, símbols), el segment conserva els límits: a_paraules
        # els reparteix el forat que queda fins a les vores del segment (revisió de Codex).
        words = seg.get("words", [])
        amb_temps = [w for w in words if w.get("start") is not None]
        if amb_temps and len(amb_temps) == len(words):
            seg["start"], seg["end"] = amb_temps[0]["start"], max(w["end"] for w in amb_temps)
    return endarrere


# --- L'alineador de tot el text --------------------------------------------------------------------

SR = 16000
TROS_EMISSIO = 30  # segons: el so es passa pel model a trossos (amb un segon de marge a cada costat)
MINIM_PARAULA = 0.04
# Fins aquí, tot el text contra tot el so. Més llarg, a trossos de frases (la memòria de l'alineació
# creix amb la llargada del so per la del text), cadascun amb un bon marge al voltant dels seus temps.
LLARG = 10 * 60
TROS_FRASES = 5 * 60
MARGE_TROS = 20
# Si més d'aquesta part de les paraules surt amb poca confiança, el text no correspon al so (un SRT
# d'un altre muntatge, un tros que no hi és): llavors no ens en refiem i es fa com abans.
CONFIANCA_BAIXA, MAXIM_DUBTOSES = 0.3, 0.25
BUIT, ENTRE_PARAULES = "[pad]", "|"


def model_alineador():
    """El model de veu català (el mateix que fa servir WhisperX) i el seu diccionari {lletra: número}."""
    model, meta = _whisperx().load_align_model(language_code=IDIOMA, device=DISPOSITIU)
    model.eval()
    return model, meta["dictionary"]


def normalitza(text: str, diccionari: dict) -> str:
    """Les lletres de la paraula que coneix el model («L’àvia,» → «l'àvia»). Una lletra que no coneix
    va sense accent si així la coneix; els números i els signes no hi són (van amb el comodí)."""
    t = unicodedata.normalize("NFC", text.lower().replace("’", "'").replace("‘", "'").replace("ŀ", "l·"))
    sortida = []
    for c in t:
        if not (c.isalpha() or c in "'·"):
            continue
        if c not in diccionari:
            c = unicodedata.normalize("NFKD", c)[0]
        if c in diccionari:
            sortida.append(c)
    return "".join(sortida)


def _emissions(model, audio):
    """Què sona a cada trama (20 ms), com a logaritmes de probabilitat, a trossos per no omplir la memòria
    amb gravacions llargues. S'hi afegeix al final el comodí, que encaixa amb qualsevol so."""
    import torch
    x = torch.from_numpy(audio)
    tros, marge = TROS_EMISSIO * SR, SR
    parts = []
    with torch.inference_mode():
        for a in range(0, len(x), tros):
            i0, i1 = max(0, a - marge), min(len(x), a + tros + marge)
            s = x[i0:i1]
            s = (s - s.mean()) / torch.sqrt(s.var() + 1e-7)  # com ho espera el model
            em = torch.log_softmax(model(s.unsqueeze(0)).logits, dim=-1)
            per_mostra = em.shape[1] / (i1 - i0)
            s0 = round((a - i0) * per_mostra)
            parts.append(em[:, s0:s0 + round((min(a + tros, len(x)) - a) * per_mostra)])
    em = torch.cat(parts, dim=1)
    return torch.cat([em, torch.zeros(1, em.shape[1], 1)], dim=-1)


def temps_paraules(audio, textos: list[str], model=None, diccionari=None) -> tuple[list[tuple[float, float]], list[float]]:
    """(inici, final) de cada paraula, en ordre, alineant-les totes contra aquest so, i la confiança de
    cadascuna (de 0 a 1). Les que no tenen lletres (números, «--») van amb el comodí: ocupen el que soni allà,
    i la seva confiança és None (no se sap)."""
    import torch
    import torchaudio
    if model is None:
        model, diccionari = model_alineador()
    emissio = _emissions(model, audio)
    comodi, buit, entre = emissio.shape[-1] - 1, diccionari.get(BUIT, 0), diccionari.get(ENTRE_PARAULES)
    fites, posicions = [], []
    for text in textos:
        if fites and entre is not None:
            fites.append(entre)
        ids = [diccionari[c] for c in normalitza(text, diccionari)] or [comodi]
        posicions.append(range(len(fites), len(fites) + len(ids)))
        fites += ids
    alineacio, punts = torchaudio.functional.forced_align(emissio, torch.tensor([fites], dtype=torch.int32), blank=buit)
    trams = torchaudio.functional.merge_tokens(alineacio[0], punts[0].exp(), blank=buit)
    per_trama = len(audio) / SR / emissio.shape[1]
    sortida = [(trams[ps[0]].start * per_trama, trams[ps[-1]].end * per_trama) for ps in posicions]
    # El comodí encaixa amb qualsevol so: la seva «confiança» no diu res (None, no se sap).
    confiances = [None if fites[ps[0]] == comodi else sum(trams[k].score for k in ps) / len(ps) for ps in posicions]
    return sortida, confiances


# Aire que es deixa davant del primer moment amb veu i darrere de l'últim: les consonants fluixes
# (una «f», una «s» final) poden quedar per sota del llindar del mapa de veu i no les volem retallar.
PROTEGEIX_INICI, PROTEGEIX_FINAL = 0.03, 0.05


# Una paraula dita a poc a poc no dura més de durada_maxima(). Si en dura més i a dins hi ha un silenci
# d'almenys FORAT_DINS, l'alineador l'ha estirada per sobre d'una pausa (o d'un tros que la transcripció
# s'ha saltat) i aquella pausa no es podria escurçar: la paraula es queda amb la primera part amb veu.
FORAT_DINS = 0.5
SOROLL = 0.05  # segons de veu: un tros que en té menys és un cop o un clic, no la paraula


def durada_maxima(text: str) -> float:
    return 1.0 + 0.12 * len(text)


def _illes(veu, i0: int, i1: int) -> list[tuple[int, int]]:
    """Els trossos seguits amb veu entre les mesures i0 i i1: [(primera, última + 1)]."""
    illes, inici = [], None
    for i in range(i0, i1 + 1):
        if i < i1 and veu[i]:
            if inici is None:
                inici = i
        elif inici is not None:
            illes.append((inici, i))
            inici = None
    return illes


def _primera_part(illes: list[tuple[int, int]], pas: float) -> list[tuple[int, int]]:
    """De les illes de veu d'una paraula massa llarga, les de la primera part que no és un soroll (les
    parts se separen per silencis de FORAT_DINS o més). Si totes són sorolls, totes."""
    parts = []
    for x, y in illes:
        if parts and (x - parts[-1][-1][1]) * pas < FORAT_DINS:
            parts[-1].append((x, y))
        else:
            parts.append([(x, y)])
    return next((p for p in parts if sum(y - x for x, y in p) * pas >= SOROLL), illes)


def retalla_als_silencis(temps: list[tuple[float, float]], veu, pas: float = 0.01,
                         textos: list[str] | None = None) -> list[tuple[float, float]]:
    """Les vores de cada paraula, sense el silenci que hi hagi a dins (l'alineador sovint allarga una
    paraula fins a la següent, per sobre del silenci): l'inici, al primer moment amb veu; el final,
    a l'últim (amb una mica d'aire, PROTEGEIX_*). Amb `textos`, una paraula massa llarga es queda amb
    la primera part (vegeu FORAT_DINS). Si dins la paraula no hi ha veu (o és molt curta), es queda com era."""
    sortida = []
    for k, (a, b) in enumerate(temps):
        illes = _illes(veu, int(a / pas), min(len(veu), int(round(b / pas))))
        if illes and textos is not None and b - a > durada_maxima(textos[k]):
            illes = _primera_part(illes, pas)
        if illes:
            na, nb = illes[0][0] * pas, illes[-1][1] * pas
            if nb - na >= MINIM_PARAULA:
                a, b = max(a, na - PROTEGEIX_INICI), min(b, nb + PROTEGEIX_FINAL)
        sortida.append((round(a, 3), round(b, 3)))
    return sortida


def _trossos_de_frases(frases: list[dict], durada: float):
    """Les frases en trossos de TROS_FRASES segons: (primera, última+1, inici, final del so que s'hi mira)."""
    i = 0
    while i < len(frases):
        j = i + 1
        while j < len(frases) and frases[j - 1]["end"] - frases[i]["start"] < TROS_FRASES:
            j += 1
        yield i, j, max(0.0, frases[i]["start"] - MARGE_TROS), min(durada, frases[j - 1]["end"] + MARGE_TROS)
        i = j


def alinea_global(audio, frases: list[dict]) -> list[dict]:
    """Com alinea(), tot el text de cop: cada frase porta les seves paraules (separades pels espais) amb el temps
    i la confiança (score). Les vores encara no s'han retallat als silencis: ho fa alinea().
    Llança ValueError si el text no sembla correspondre al so (vegeu MAXIM_DUBTOSES)."""
    textos = [[w for w in f["text"].split() if w.strip()] for f in frases]
    model, diccionari = model_alineador()
    durada = len(audio) / SR
    if durada <= LLARG:
        crus, confiances = temps_paraules(audio, [w for t in textos for w in t], model, diccionari)
    else:
        crus, confiances = [], []
        for i, j, a, b in _trossos_de_frases(frases, durada):
            t, c = temps_paraules(audio[int(a * SR):int(b * SR)], [w for tt in textos[i:j] for w in tt], model, diccionari)
            crus += [(x + a, y + a) for x, y in t]
            confiances += c
    sabudes = [c for c in confiances if c is not None]
    dubtoses = sum(c < CONFIANCA_BAIXA for c in sabudes) / max(1, len(sabudes))
    if dubtoses > MAXIM_DUBTOSES:
        raise ValueError(f"el text no sembla correspondre al so ({dubtoses:.0%} de paraules dubtoses)")
    sortida, k = [], 0
    for f, paraules in zip(frases, textos):
        words = [{"word": w, "start": round(crus[k + j][0], 3), "end": round(crus[k + j][1], 3),
                  "score": None if confiances[k + j] is None else round(confiances[k + j], 3)}
                 for j, w in enumerate(paraules)]
        k += len(paraules)
        sortida.append({"start": words[0]["start"] if words else f["start"],
                        "end": words[-1]["end"] if words else f["end"], "text": f["text"], "words": words})
    return sortida


def compara_temps(paraules: list[dict], frases_srt: list[dict], grans: int = 10) -> dict:
    """Compara les vores de les paraules (inici i final) amb les d'un SRT d'una altra eina. Les paraules
    s'aparellen pel text (difflib), així una paraula de més o de menys no ho desquadra. D'un subtítol de
    diverses paraules només se'n saben l'inici de la primera i el final de l'última."""
    from difflib import SequenceMatcher
    from motor.neteja import normalitza
    vores = []  # (text, index de la paraula del SRT, "inici"/"final", temps)
    srt = []
    for f in frases_srt:
        mots = f["text"].split()
        for k, w in enumerate(mots):
            srt.append({"text": w, "inici": f["start"] if k == 0 else None,
                        "final": f["end"] if k == len(mots) - 1 else None})
    nostres = [normalitza(p["text"]) for p in paraules]
    seus = [normalitza(w["text"]) for w in srt]
    diferencies = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=nostres, b=seus, autojunk=False).get_opcodes():
        if tag != "equal":
            continue
        for i, j in zip(range(i1, i2), range(j1, j2)):
            for vora in ("inici", "final"):
                if srt[j][vora] is not None and paraules[i].get(vora) is not None:
                    # Al mil·lisegon: 0,4 − 0,3 dona 0,10000000000000003 i comptava com a més d'una dècima.
                    dif = round(abs(paraules[i][vora] - srt[j][vora]), 3)
                    diferencies.append((dif, paraules[i], srt[j], vora))
    if not diferencies:
        return {"n": 0, "mediana": 0.0, "mes_01": 0, "mes_025": 0, "mes_05": 0, "grans": []}
    d = sorted(x[0] for x in diferencies)
    pitjors = sorted(diferencies, key=lambda x: -x[0])[:grans]
    return {"n": len(d), "mediana": statistics.median(d),
            "mes_01": sum(x > 0.1 for x in d), "mes_025": sum(x > 0.25 for x in d), "mes_05": sum(x > 0.5 for x in d),
            "grans": [{"text": p["text"], "vora": v, "nostre": p[v], "srt": w[v]} for _, p, w, v in pitjors if _ > 0.1]}


def transcriu(audio, model: str = "large-v3") -> list[dict]:
    """WhisperX escriu el text (sense temps per paraula encara)."""
    wx = _whisperx()
    m = wx.load_model(model, DISPOSITIU, compute_type="int8", language=IDIOMA)
    return m.transcribe(audio, batch_size=8, language=IDIOMA)["segments"]


def _primer(*valors):
    """El primer valor que no és None."""
    return next(v for v in valors if v is not None)


def a_paraules(segments: list[dict]) -> list[dict]:
    """Aplana els segments en una llista de paraules amb id, text, inici, final, frase i confiança.

    Les poques paraules a les quals l'alineador no troba temps (números, símbols)
    reben el forat que queda entre les paraules del costat. La confiança (de 0 a 1) diu com de segur
    n'està l'alineador; None vol dir que no se sap (números, símbols: el temps és aproximat).
    """
    paraules = []
    for f, seg in enumerate(segments):
        for w in seg.get("words", []):
            text = w.get("word", "").strip()
            if text:
                sap = w.get("start") is not None and w.get("score") is not None
                paraules.append({"text": text, "inici": w.get("start"), "final": w.get("end"),
                                 "frase": f, "confianca": round(float(w["score"]), 2) if sap else None,
                                 "_seg": (seg.get("start"), seg.get("end"))})

    # Si n'hi ha diverses de seguides sense temps («Són 25 € avui»), es reparteixen el forat entre
    # totes (segons la llargada), en lloc de donar-lo tot a la primera i deixar les altres sense durada.
    i = 0
    while i < len(paraules):
        if paraules[i]["inici"] is not None and paraules[i]["final"] is not None:
            i += 1
            continue
        # Només dins de la mateixa frase (segment): les veïnes d'una altra frase poden ser a 30 s,
        # i la paraula s'empassaria el silenci que hi ha entremig.
        frase = paraules[i]["frase"]
        j = i
        while (j < len(paraules) and paraules[j]["frase"] == frase
               and (paraules[j]["inici"] is None or paraules[j]["final"] is None)):
            j += 1
        tanda = paraules[i:j]
        seg_inici, seg_final = tanda[0]["_seg"]
        anterior = paraules[i - 1] if i > 0 else None
        seguent = paraules[j] if j < len(paraules) else None
        ini = _primer(tanda[0]["inici"],
                      anterior["final"] if anterior and anterior["frase"] == frase else None,
                      seg_inici, anterior["final"] if anterior else None, 0.0)
        fi = _primer(tanda[-1]["final"],
                     seguent["inici"] if seguent and seguent["frase"] == frase else None,
                     seg_final, seguent["inici"] if seguent else None, ini)
        fi = max(fi, ini)
        pesos = [max(1, len(p["text"])) for p in tanda]
        t = ini
        for p, pes in zip(tanda, pesos):
            p["inici"] = t
            t += (fi - ini) * pes / sum(pesos)
            p["final"] = t
        i = j
    for p in paraules:
        p["final"] = max(p["final"], p["inici"])

    for i, p in enumerate(paraules):
        del p["_seg"]
        p["id"] = i
        p["inici"] = round(p["inici"], 3)
        p["final"] = round(p["final"], 3)
    return paraules
