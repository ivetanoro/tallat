"""Quin ritme de fotogrames diu ffprobe de vídeos de mòbil inventats, i amb quin exportaria tallat.

    python diag_ritmes.py CARPETA
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from motor import exporta  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# nom, unitats de temps per segon del fitxer, moment de cada fotograma N en aquestes unitats
CASOS = [
    ("regular a 30, com un iPhone (600)", 600, "N*20"),
    ("29,97 amb les unitats de l'iPhone (600)", 600, "floor(N*20.02)"),
    ("30 amb una unitat amunt o avall a l'atzar (600)", 600, "N*20+floor(random(0)*3)"),
    ("baixa de 30 a 24 i torna, poca llum (600)", 600, "N*20+5*(300*floor(N/900)+max(0\\,min(mod(N\\,900)-300\\,300)))"),
    ("60 amb algun fotograma perdut (600)", 600, "N*10+10*floor(N/50)"),
    ("30 amb tremolor d'1,5 ms, com un Android (90000)", 90000, "N*3000+floor(random(0)*270)"),
    ("baixa de 30 a 24 i torna, com un Android (90000)", 90000, "N*3000+750*(300*floor(N/900)+max(0\\,min(mod(N\\,900)-300\\,300)))"),
    ("gravació de pantalla, irregular (60000)", 60000, "N*1000+floor(random(0)*4000)"),
    ("el vídeo suau de les mesures (600)", 600, "(N/30+0.006*sin(N/3.7)+0.006)*600"),
    ("el vídeo fort de les mesures (600)", 600, "(N/30+(1/24-1/30)*(300*floor(N/900)+max(0\\,min(mod(N\\,900)-300\\,300)))+0.008*sin(N/3.7)+0.008)*600"),
]

carpeta = Path(sys.argv[1])
carpeta.mkdir(parents=True, exist_ok=True)
print(subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.splitlines()[0])
for i, (nom, unitats, moment) in enumerate(CASOS):
    for codec in ("libx264", "libx265", "hevc_videotoolbox"):  # el darrer, amb la gràfica del Mac, com un iPhone; sense gràfica no surt
        f = carpeta / f"cas{i}-{codec}.MOV"
        extra = ["-preset", "ultrafast"] if codec.startswith("lib") else ["-b:v", "2M"]
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=70",
                            "-vf", f"settb=1/{unitats},setpts={moment}", "-fps_mode", "passthrough", "-video_track_timescale", str(unitats),
                            "-c:v", codec, *extra, "-pix_fmt", "yuv420p", str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            print(f"{nom} [{codec}]: no s'ha pogut fer: {r.stderr.strip()[-120:]}")
            continue
        s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,avg_frame_rate,nb_frames", "-of", "json", str(f)],
                                      capture_output=True, text=True, encoding="utf-8", errors="replace").stdout)["streams"][0]
        print(f"{nom} [{codec}]: r_frame_rate={s['r_frame_rate']} avg_frame_rate={s['avg_frame_rate']} fotogrames={s['nb_frames']} → tallat exportaria a {exporta.info_video(f)['fps']}", flush=True)
        f.unlink()
