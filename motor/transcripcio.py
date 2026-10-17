"""Transcripció en català amb marques de temps per paraula.

Dues fonts del text:
- un SRT (p. ex. exportat de Descript): és la més ràpida i la més fidel (conserva el farciment).
- WhisperX escriu el text. Gratuïta i sense internet, però més lenta i tendeix a esborrar el
  farciment («eh», «mmm»).

El temps de cada paraula el calcula l'alineador MMS de Meta (torchaudio.pipelines.MMS_FA): tot el
text contra tot el so, sense refiar-se dels temps de les frases (els de Descript poden anar uns
segons desplaçats, i l'alineador d'abans, el de WhisperX, estirava les paraules pels silencis i
s'equivocava fins a un segon i mig). Després, les vores de cada paraula es retallen als silencis
reals (motor/veu.py). El primer cop baixa el model (uns 1,2 GB). Si no pot, fa servir el de WhisperX.
"""
from __future__ import annotations

import re
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
    """Calcula el temps de cada paraula: [{start, end, text, words: [{word, start, end}]}].
    Amb MMS; si no es pot (no s'ha pogut baixar el model…), amb el model català de WhisperX."""
    try:
        return alinea_mms(audio, frases)
    except Exception as e:  # noqa: BLE001 — qualsevol problema amb MMS: l'alineador d'abans
        if avis:
            avis(f"No he pogut fer servir l'alineador MMS ({e}); faig servir el de WhisperX.")
        wx = _whisperx()
        model, meta = wx.load_align_model(language_code=IDIOMA, device=DISPOSITIU)
        return wx.align(frases, model, meta, audio, DISPOSITIU, return_char_alignments=False)["segments"]


# --- L'alineador MMS -----------------------------------------------------------------------------

SR = 16000
TROS_EMISSIO = 30  # segons: el so es passa pel model a trossos (amb un segon de marge a cada costat)
MINIM_PARAULA = 0.04


def romanitza(text: str) -> str:
    """El que entén MMS: minúscules sense accents ni signes («L'àvia,» → «l'avia», «col·la» → «colla»)."""
    t = unicodedata.normalize("NFKD", text.lower().replace("·", ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z']", "", t)


def _emissions(model, audio):
    """Què sona a cada trama (20 ms), a trossos per no omplir la memòria amb gravacions llargues."""
    import torch
    x = torch.from_numpy(audio).unsqueeze(0)
    tros, marge = TROS_EMISSIO * SR, SR
    parts = []
    with torch.inference_mode():
        for a in range(0, x.shape[1], tros):
            i0, i1 = max(0, a - marge), min(x.shape[1], a + tros + marge)
            em, _ = model(x[:, i0:i1])
            per_mostra = em.shape[1] / (i1 - i0)
            s0 = round((a - i0) * per_mostra)
            parts.append(em[:, s0:s0 + round((min(a + tros, x.shape[1]) - a) * per_mostra)])
    return torch.cat(parts, dim=1)


def temps_mms(audio, textos: list[str]) -> list[tuple[float, float]]:
    """(inici, final) de cada paraula, en ordre, alineant-les totes contra tot el so. Les que no tenen
    lletres (números, «--») van amb el comodí: ocupen el que soni allà."""
    import torch
    import torchaudio
    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model(with_star=True)
    model.eval()
    diccionari = bundle.get_dict(star="*")
    emissio = _emissions(model, audio)
    fites, n_per_paraula = [], []
    for text in textos:
        ids = [diccionari[c] for c in romanitza(text) if c in diccionari] or [diccionari["*"]]
        n_per_paraula.append(len(ids))
        fites += ids
    alineacio, punts = torchaudio.functional.forced_align(emissio, torch.tensor([fites], dtype=torch.int32), blank=0)
    trams = torchaudio.functional.merge_tokens(alineacio[0], punts[0].exp())
    per_trama = len(audio) / SR / emissio.shape[1]
    sortida, k = [], 0
    for n in n_per_paraula:
        tros = trams[k:k + n]
        k += n
        sortida.append((tros[0].start * per_trama, tros[-1].end * per_trama))
    return sortida


def retalla_als_silencis(temps: list[tuple[float, float]], veu, pas: float = 0.01) -> list[tuple[float, float]]:
    """Les vores de cada paraula, sense el silenci que hi hagi a dins (l'alineador sovint allarga una
    paraula fins a la següent, per sobre del silenci): l'inici, al primer moment amb veu; el final,
    a l'últim. Si dins la paraula no hi ha veu (o és molt curta), es queda com era."""
    sortida = []
    for a, b in temps:
        i0, i1 = int(a / pas), min(len(veu), int(round(b / pas)))
        amb_veu = [i for i in range(i0, i1) if veu[i]]
        if amb_veu:
            na, nb = amb_veu[0] * pas, (amb_veu[-1] + 1) * pas
            if nb - na >= MINIM_PARAULA:
                a, b = max(a, na), min(b, nb)
        sortida.append((round(a, 3), round(b, 3)))
    return sortida


def alinea_mms(audio, frases: list[dict]) -> list[dict]:
    """Com alinea(), amb MMS: cada frase porta les seves paraules (separades pels espais) amb el temps."""
    from motor import veu
    textos = [[w for w in f["text"].split() if w.strip()] for f in frases]
    temps = retalla_als_silencis(temps_mms(audio, [w for t in textos for w in t]), veu.mapa(audio))
    sortida, k = [], 0
    for f, paraules in zip(frases, textos):
        words = [{"word": w, "start": temps[k + j][0], "end": temps[k + j][1]} for j, w in enumerate(paraules)]
        k += len(paraules)
        sortida.append({"start": words[0]["start"] if words else f["start"],
                        "end": words[-1]["end"] if words else f["end"], "text": f["text"], "words": words})
    return sortida


def transcriu(audio, model: str = "large-v3") -> list[dict]:
    """WhisperX escriu el text (sense temps per paraula encara)."""
    wx = _whisperx()
    m = wx.load_model(model, DISPOSITIU, compute_type="int8", language=IDIOMA)
    return m.transcribe(audio, batch_size=8, language=IDIOMA)["segments"]


def _primer(*valors):
    """El primer valor que no és None."""
    return next(v for v in valors if v is not None)


def a_paraules(segments: list[dict]) -> list[dict]:
    """Aplana els segments en una llista de paraules amb id, text, inici, final i frase.

    Les poques paraules a les quals l'alineador no troba temps (números, símbols)
    reben el forat que queda entre les paraules del costat.
    """
    paraules = []
    for f, seg in enumerate(segments):
        for w in seg.get("words", []):
            text = w.get("word", "").strip()
            if text:
                paraules.append({"text": text, "inici": w.get("start"), "final": w.get("end"),
                                 "frase": f, "_seg": (seg.get("start"), seg.get("end"))})

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
