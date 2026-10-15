"""Transcripció en català amb marques de temps per paraula.

Dues fonts possibles:
- «alinea»: el text ve d'un SRT (p. ex. exportat de Descript) i WhisperX només calcula
  quan comença i acaba cada paraula. És la més ràpida i la més fidel (conserva el farciment).
- «whisperx»: WhisperX escriu el text i calcula els temps. Gratuïta i sense internet,
  però més lenta i tendeix a esborrar el farciment («eh», «mmm»).
"""
from __future__ import annotations

import re
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


def alinea(audio, frases: list[dict]) -> list[dict]:
    """Calcula el temps de cada paraula amb el model català de Softcatalà."""
    wx = _whisperx()
    model, meta = wx.load_align_model(language_code=IDIOMA, device=DISPOSITIU)
    return wx.align(frases, model, meta, audio, DISPOSITIU, return_char_alignments=False)["segments"]


def transcriu(audio, model: str = "large-v3") -> list[dict]:
    """WhisperX escriu el text (sense temps per paraula encara)."""
    wx = _whisperx()
    m = wx.load_model(model, DISPOSITIU, compute_type="int8", language=IDIOMA)
    return m.transcribe(audio, batch_size=8, language=IDIOMA)["segments"]


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
        j = i
        while j < len(paraules) and (paraules[j]["inici"] is None or paraules[j]["final"] is None):
            j += 1
        tanda = paraules[i:j]
        ini = paraules[i - 1]["final"] if i > 0 else None
        ini = ini if ini is not None else (tanda[0]["inici"] if tanda[0]["inici"] is not None else tanda[0]["_seg"][0])
        fi = paraules[j]["inici"] if j < len(paraules) else None
        fi = fi if fi is not None else (tanda[-1]["final"] if tanda[-1]["final"] is not None else tanda[-1]["_seg"][1])
        ini, fi = (ini or 0.0), max(fi or 0.0, ini or 0.0)
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
