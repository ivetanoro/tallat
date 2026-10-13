"""tallat: editor de reels en català, per paraules.

Ús:
  python tallat.py transcriu VIDEO --projecte CARPETA [--srt FITXER.srt] [--model large-v3]
  python tallat.py neteja --projecte CARPETA
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

from motor import edicio, exporta, neteja, transcripcio

TRANSCRIPCIO = "transcripcio.json"
EDICIO = "edicio.json"
EDICIO_TEXT = "edicio.txt"  # format antic (fase 1): s'importa un cop
ORIGINAL = "original.txt"
REVISIO = "revisio.txt"


def _minuts(segons: float) -> str:
    return f"{int(segons // 60)} min {int(segons % 60):02d} s"


def ordre_transcriu(args) -> None:
    video = Path(args.video).expanduser().resolve()
    projecte = Path(args.projecte).expanduser().resolve()
    if not video.exists():
        sys.exit(f"No trobo el vídeo: {video}")
    if (projecte / TRANSCRIPCIO).exists() and not args.forca:
        sys.exit(f"Aquest projecte ja té una transcripció ({projecte / TRANSCRIPCIO}).\n"
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
    (projecte / ORIGINAL).write_text(edicio.text_editable(paraules), encoding="utf-8")
    estat = edicio.estat_buit()
    if not args.sense_neteja:
        estat = edicio.aplica_neteja(estat, *neteja.detecta(paraules, neteja.carrega_llista()))
    edicio.desa_estat(estat, projecte / EDICIO)
    print(f"\nFet en {_minuts(time.time() - t0)}: {len(paraules)} paraules.")
    _resum(dades, edicio.aplica(paraules, estat), estat, projecte)


def _carrega(projecte: Path):
    dades = json.loads((projecte / TRANSCRIPCIO).read_text(encoding="utf-8"))
    if (projecte / EDICIO).exists():
        estat = edicio.llegeix_estat(projecte / EDICIO)
    elif (projecte / EDICIO_TEXT).exists():
        estat, avisos = edicio.importa_text(dades["paraules"], (projecte / EDICIO_TEXT).read_text(encoding="utf-8"))
        for a in avisos:
            print("Avís:", a)
        edicio.desa_estat(estat, projecte / EDICIO)
        print(f"He passat la teva edició d'{EDICIO_TEXT} a {EDICIO} (a partir d'ara es fa servir aquest).")
    else:
        estat = edicio.estat_buit()
    return dades, estat


def _trams(dades: dict, paraules: list[dict], estat: dict):
    return edicio.trams(paraules, float(Fraction(dades["fps"])), dades["durada"],
                        pausa_maxima=estat.get("pausa_maxima"))


MOTIUS = {"usuari": "tretes per tu", "farciment": "farciment", "tall": "paraules a mig dir"}
PROPOSTES = {"farciment?": "possible farciment", "expressiu?": "sons repetits (potser expressius)",
             "repeticio?": "paraules repetides"}


def _resum(dades: dict, paraules: list[dict], estat: dict, projecte: Path) -> None:
    from collections import Counter
    trams = _trams(dades, paraules, estat)
    fora = Counter(p["motiu"] for p in paraules if not p["conservada"])
    print(f"Paraules: {sum(p['conservada'] for p in paraules)} es queden.")
    for motiu, n in fora.items():
        print(f"  − {n} {MOTIUS.get(motiu, motiu)}")
    for motiu, n in Counter(estat["propostes"].values()).items():
        print(f"  ? {n} {PROPOSTES.get(motiu, motiu)} (només proposat)")
    pausa = estat.get("pausa_maxima")
    print(f"Silencis: {'escurçats a ' + str(pausa) + ' s com a màxim' if pausa else 'sense tocar'}.")
    print(f"Durada: {_minuts(dades['durada'])} → {_minuts(sum(b - a for a, b in trams))} ({len(trams)} trossos).")
    (projecte / REVISIO).write_text(edicio.text_revisio(paraules), encoding="utf-8")
    print(f"Text per revisar ([tret], {{proposat}}): {projecte / REVISIO}")


def ordre_neteja(args) -> None:
    projecte = Path(args.projecte).expanduser().resolve()
    dades, estat = _carrega(projecte)
    llista = neteja.ruta_llista()
    estat = edicio.aplica_neteja(estat, *neteja.detecta(dades["paraules"], neteja.carrega_llista(llista)))
    if args.pausa is not None:
        estat["pausa_maxima"] = args.pausa if args.pausa > 0 else None
    edicio.desa_estat(estat, projecte / EDICIO)
    print(f"Neteja feta amb la llista {llista}")
    _resum(dades, edicio.aplica(dades["paraules"], estat), estat, projecte)


def ordre_estat(args) -> None:
    projecte = Path(args.projecte).expanduser().resolve()
    dades, estat = _carrega(projecte)
    _resum(dades, edicio.aplica(dades["paraules"], estat), estat, projecte)


def ordre_exporta(args) -> None:
    projecte = Path(args.projecte).expanduser().resolve()
    dades, estat = _carrega(projecte)
    trams = _trams(dades, edicio.aplica(dades["paraules"], estat), estat)
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
    t.add_argument("--sense-neteja", action="store_true", help="No treguis el farciment automàticament")
    t.set_defaults(func=ordre_transcriu)

    n = sub.add_parser("neteja", help="Treu farciment i paraules a mig dir, i escurça silencis")
    n.add_argument("--projecte", required=True)
    n.add_argument("--pausa", type=float, help="Silenci màxim en segons (0 = no escurçar)")
    n.set_defaults(func=ordre_neteja)

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
