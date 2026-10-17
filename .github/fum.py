"""Prova de fum de tot el camí, per a les proves automàtiques (el Windows de GitHub): un vídeo inventat,
una transcripció inventada, l'export amb subtítols (HyperFrames de debò), el projecte per a altres editors
i la pàgina de revisió. Sense vídeos ni veus de ningú.

    python .github/fum.py CARPETA_DE_PROVES
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ARREL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ARREL))

from motor import entorn, exporta  # noqa: E402

entorn.prepara()
carpeta = Path(sys.argv[1]).resolve()
carpeta.mkdir(parents=True, exist_ok=True)
# Unes preferències pròpies: els vídeos no han d'anar a la carpeta que la persona hagi triat (Descàrregues…).
os.environ["TALLAT_PREFERENCIES"] = str(carpeta / "preferencies.json")
video = carpeta / "vídeo de prova.mp4"  # amb accent i espais: com els noms de debò
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=8", "-f", "lavfi",
                "-i", "sine=f=220:d=8", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video)],
               check=True)
projecte = carpeta / "projecte"
projecte.mkdir(exist_ok=True)
textos = "Hola, això és una prova de tallat a Windows. Funciona amb accents: què, cançó, l·l.".split()
paraules = [{"id": i, "text": t, "inici": round(0.4 + i * 0.5, 3), "final": round(0.4 + i * 0.5 + 0.4, 3), "frase": 0,
             "confianca": 0.9} for i, t in enumerate(textos)]
dades = {"versio": 1, "video": str(video), "font": "prova de fum", **exporta.info_video(video), "paraules": paraules}
(projecte / "transcripcio.json").write_text(json.dumps(dades, ensure_ascii=False, indent=1), encoding="utf-8")


def tallat(*args: str, temps: int = 900) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, str(ARREL / "tallat.py"), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=temps)
    print(f"$ tallat.py {' '.join(args)}\n{r.stdout[-1500:]}{r.stderr[-3000:]}", flush=True)
    if r.returncode != 0:
        sys.exit(f"Ha fallat: tallat.py {' '.join(args)}")
    return r


tallat("exporta", "--projecte", str(projecte))  # esborrany amb subtítols (HyperFrames)
exports = list((projecte / "exports").glob("*.mp4"))
assert exports, "no hi ha cap vídeo exportat"
fluxos = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json",
                                   str(exports[0])], capture_output=True, text=True, encoding="utf-8", check=True).stdout)["streams"]
assert {f["codec_type"] for f in fluxos} == {"video", "audio"}, fluxos
print("export:", exports[0].name, exports[0].stat().st_size, "bytes", [(f["codec_type"], f["duration"]) for f in fluxos])

tallat("editors", "--projecte", str(projecte))
editors = [c for c in (projecte / "exports").iterdir() if c.is_dir() and "editors" in c.name]
assert editors, "no hi ha el projecte per a altres editors"
# Els XML han d'apuntar al vídeo de debò (a Windows, «file:///C:/…»; abans hi quedaven les «\\»).
for xml, patro in (("*.xml", r"<pathurl>file://localhost([^<]+)</pathurl>"), ("*.fcpxml", r'src="file://([^"]+)"')):
    text = next(editors[0].glob(xml)).read_text(encoding="utf-8")
    adreca = re.search(patro, text).group(1)
    cami = Path(urllib.request.url2pathname(html.unescape(adreca)))
    assert cami.resolve() == video.resolve(), (xml, adreca, cami)
print("projecte per a editors: els XML apunten al vídeo")

# La pàgina de revisió: al port que digui (si el 8799 és ocupat, en pren un altre), i que sigui tallat.
servidor = subprocess.Popen([sys.executable, str(ARREL / "tallat.py"), "revisa", "--projecte", str(projecte),
                             "--port", "8799", "--sense-navegador"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
try:
    port, dites = None, []
    while port is None:  # abans pot dir altres coses (la primera vegada fa la còpia lleugera)
        linia = servidor.stdout.readline()
        assert linia, f"la pàgina no ha dit on és: {''.join(dites)!r}"
        dites.append(linia)
        port = re.search(r"http://127\.0\.0\.1:(\d+)/", linia)
    for _ in range(60):
        assert servidor.poll() is None, "el servidor s'ha aturat"
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port.group(1)}/", timeout=2) as resposta:
                assert resposta.status == 200 and "tallat" in resposta.read().decode("utf-8", "replace")
                print("pàgina de revisió: respon")
                break
        except OSError:
            time.sleep(1)
    else:
        sys.exit("La pàgina de revisió no respon")
finally:
    servidor.terminate()
    try:
        servidor.wait(timeout=15)
    except subprocess.TimeoutExpired:
        servidor.kill()
print("Prova de fum: tot bé")
