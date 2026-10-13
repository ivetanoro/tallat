"""tallat: editor de reels en català, per paraules.

Ús:
  python tallat.py transcriu VIDEO --projecte CARPETA [--srt FITXER.srt] [--model large-v3]
  python tallat.py estat --projecte CARPETA
  python tallat.py exporta --projecte CARPETA [--qualitat esborrany|1080|4k]

La carpeta del projecte ha de ser fora del repositori (els vídeos i el que dius no es publiquen).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from fractions import Fraction
from pathlib import Path

from motor import edicio, exporta, transcripcio

TRANSCRIPCIO = "transcripcio.json"
EDICIO = "edicio.txt"
ORIGINAL = "original.txt"


def _minuts(segons: float) -> str:
    return f"{int(segons // 60)} min {int(segons % 60):02d} s"


def ordre_transcriu(args) -> None:
    video = Path(args.video).expanduser().resolve()
    projecte = Path(args.projecte).expanduser().resolve()
    if not video.exists():
        sys.exit(f"No trobo el vídeo: {video}")
    if (projecte / EDICIO).exists() and not args.forca:
        sys.exit(f"Aquest projecte ja té una transcripció ({projecte / EDICIO}).\n"
                 "Si la vols refer i perdre els canvis, afegeix --forca.")
    projecte.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("Carregant l'àudio…")
    audio = transcripcio.carrega_audio(video)
    if args.srt:
        frases = transcripcio.llegeix_srt(Path(args.srt).expanduser())
        font = "text de l'SRT + alineació WhisperX"
        print(f"Calculant el temps de cada paraula ({len(frases)} frases)…")
    else:
        print(f"Transcrivint amb WhisperX ({args.model}). En un Mac Intel pot trigar més que el vídeo…")
        frases = transcripcio.transcriu(audio, args.model)
        font = f"WhisperX {args.model}"
        print("Calculant el temps de cada paraula…")
    paraules = transcripcio.a_paraules(transcripcio.alinea(audio, frases))

    info = exporta.info_video(video)
    dades = {"versio": 1, "video": str(video), "font": font, **info, "paraules": paraules}
    (projecte / TRANSCRIPCIO).write_text(json.dumps(dades, ensure_ascii=False, indent=1), encoding="utf-8")
    text = edicio.text_editable(paraules)
    (projecte / ORIGINAL).write_text(text, encoding="utf-8")
    (projecte / EDICIO).write_text(text, encoding="utf-8")
    print(f"\nFet en {_minuts(time.time() - t0)}: {len(paraules)} paraules.")
    print(f"Ara esborra el que no vulguis a:\n  {projecte / EDICIO}")


def _carrega(projecte: Path):
    dades = json.loads((projecte / TRANSCRIPCIO).read_text(encoding="utf-8"))
    text = (projecte / EDICIO).read_text(encoding="utf-8")
    paraules, avisos = edicio.compara(dades["paraules"], text)
    fps = float(Fraction(dades["fps"]))
    trams = edicio.trams(paraules, fps, dades["durada"])
    return dades, paraules, avisos, trams


def ordre_estat(args) -> None:
    projecte = Path(args.projecte).expanduser().resolve()
    dades, paraules, avisos, trams = _carrega(projecte)
    fora = sum(not p["conservada"] for p in paraules)
    print(f"Paraules: {len(paraules) - fora} es queden, {fora} esborrades.")
    print(f"Durada: {_minuts(dades['durada'])} → {_minuts(sum(b - a for a, b in trams))} ({len(trams)} trossos).")
    for a in avisos:
        print("Avís:", a)


def ordre_exporta(args) -> None:
    projecte = Path(args.projecte).expanduser().resolve()
    dades, paraules, avisos, trams = _carrega(projecte)
    for a in avisos:
        print("Avís:", a)
    nom = Path(dades["video"]).stem.replace(" ", "-")
    sortida = projecte / "exports" / f"{nom}_{args.qualitat}_{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    (projecte / "exports").mkdir(exist_ok=True)
    (projecte / "exports" / "talls.json").write_text(json.dumps(trams), encoding="utf-8")
    print(f"Exportant {len(trams)} trossos ({_minuts(sum(b - a for a, b in trams))}) en qualitat «{args.qualitat}»…")
    t0 = time.time()
    exporta.exporta(Path(dades["video"]), trams, sortida, args.qualitat)
    print(f"\nFet en {_minuts(time.time() - t0)}:\n  {sortida}")


def main() -> None:
    p = argparse.ArgumentParser(prog="tallat", description="Editor de reels en català, per paraules.")
    sub = p.add_subparsers(dest="ordre", required=True)

    t = sub.add_parser("transcriu", help="Transcriu un vídeo amb temps per paraula")
    t.add_argument("video")
    t.add_argument("--projecte", required=True, help="Carpeta on es desa la feina (fora del repositori)")
    t.add_argument("--srt", help="Text ja transcrit (p. ex. exportat de Descript); només se n'alinea el temps")
    t.add_argument("--model", default="large-v3", help="Model de WhisperX si no hi ha --srt")
    t.add_argument("--forca", action="store_true", help="Refés la transcripció encara que ja n'hi hagi una")
    t.set_defaults(func=ordre_transcriu)

    e = sub.add_parser("estat", help="Mostra quantes paraules has esborrat i quant durarà")
    e.add_argument("--projecte", required=True)
    e.set_defaults(func=ordre_estat)

    x = sub.add_parser("exporta", help="Exporta el vídeo tallat a MP4 vertical")
    x.add_argument("--projecte", required=True)
    x.add_argument("--qualitat", choices=list(exporta.QUALITATS), default="esborrany")
    x.set_defaults(func=ordre_exporta)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
