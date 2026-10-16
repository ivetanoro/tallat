"""Export del muntatge a MP4 vertical 9:16 amb ffmpeg."""
from __future__ import annotations

import collections
import json
import os
import shutil
import subprocess
import tempfile
import threading
from fractions import Fraction
from pathlib import Path

from motor import so, targetes

QUALITATS = {
    # nom: (amplada, alçada, bitrate de vídeo)
    "esborrany": (720, 1280, "4M"),
    "1080": (1080, 1920, "16M"),
    "4k": (2160, 3840, "45M"),
}
PREFERENCIES = Path.home() / ".tallat" / "preferencies.json"  # la carpeta on la persona vol els vídeos
FOS_AUDIO = 0.01  # segons de fos a cada tall, perquè no se sentin clics
ZOOM = 1.15       # apropament dels trossos amb zoom (instrucció de veu «Claude, zoom aquí»)


def info_video(video: Path) -> dict:
    """Mida tal com es veu (tenint en compte la rotació dels mòbils), fps i durada."""
    sortida = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_format",
         "-of", "json", str(video)],
        capture_output=True, text=True, check=True).stdout
    d = json.loads(sortida)
    s = d["streams"][0]
    amplada, alcada = s["width"], s["height"]
    if abs(_rotacio(s)) % 180 == 90:  # l'iPhone desa el vertical com a horitzontal + «gira'l 90°»
        amplada, alcada = alcada, amplada
    return {"amplada": amplada, "alcada": alcada,
            "fps": str(Fraction(s["r_frame_rate"])), "durada": float(d["format"]["duration"])}


def _rotacio(stream: dict) -> int:
    """L'etiqueta «gira'l» d'un vídeo, en graus. Les versions noves de ffprobe la donen a
    side_data_list; les antigues, a tags.rotate."""
    return next((int(float(x["rotation"])) for x in stream.get("side_data_list", []) if "rotation" in x),
                int(float(stream.get("tags", {}).get("rotate", 0) or 0)))


def treu_rotacio(fitxer: Path) -> None:
    """Els fotogrames que fa tallat ja surten drets, però l'ffmpeg 7.1 hi copia l'etiqueta «gira'l 90°»
    del vídeo de l'iPhone, i els reproductors el tornaven a girar (el vídeo sortia de costat). Si hi
    és, es treu, sense tornar a codificar res."""
    fitxer = Path(fitxer)
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json",
                                   str(fitxer)], capture_output=True, text=True, check=True).stdout)["streams"]
    if not s or _rotacio(s[0]) == 0:
        return
    temporal = fitxer.with_name(f".{fitxer.stem}.dret{fitxer.suffix}")
    try:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-display_rotation:v:0", "0", "-i", str(fitxer),
                        "-map", "0", "-c", "copy", "-movflags", "+faststart", str(temporal)],
                       check=True, capture_output=True)
        temporal.replace(fitxer)
    finally:
        temporal.unlink(missing_ok=True)


# --- On es desen els vídeos -----------------------------------------------------------------------
# Cada export es fa a la carpeta del projecte (exports/), on el troba la pestanya Vídeos. Si la
# persona ha triat una carpeta seva, també hi va: com un enllaç al mateix fitxer (no ocupa més lloc
# si és al mateix disc) o, si és en un altre disc, com una còpia.

def _preferencies() -> dict:
    try:
        dades = json.loads(PREFERENCIES.read_text(encoding="utf-8"))
        return dades if isinstance(dades, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def carpeta_exports() -> Path | None:
    """La carpeta que ha triat la persona per als vídeos exportats (None: només la del projecte)."""
    carpeta = _preferencies().get("carpeta_exports")
    return Path(carpeta) if isinstance(carpeta, str) and Path(carpeta).is_dir() else None


def tria_carpeta_exports(carpeta: Path | None) -> None:
    dades = _preferencies()
    dades["carpeta_exports"] = str(Path(carpeta).expanduser().resolve()) if carpeta else None
    PREFERENCIES.parent.mkdir(parents=True, exist_ok=True)
    PREFERENCIES.write_text(json.dumps(dades, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _enllaca(origen, desti) -> None:
    try:
        os.link(origen, desti)
    except OSError:  # un altre disc (o un sistema que no en fa): una còpia
        shutil.copy2(origen, desti)


def copia_a_carpeta(fitxer: Path) -> Path | None:
    """Posa un export (un vídeo o una carpeta) a la carpeta de la persona, si n'ha triat una."""
    carpeta = carpeta_exports()
    if carpeta is None:
        return None
    desti = carpeta / fitxer.name
    n = 2
    while desti.exists():  # no en trepitgem cap
        desti = carpeta / f"{fitxer.stem}-{n}{fitxer.suffix}"
        n += 1
    if fitxer.is_dir():
        shutil.copytree(fitxer, desti, copy_function=_enllaca)
    else:
        _enllaca(fitxer, desti)
    return desti


def temps_exactes(a: float, b: float, fps: str) -> tuple[str, str]:
    """-ss i -t d'un tros perquè ffmpeg en tregui exactament els fotogrames que toquen.

    Els trossos ja comencen i acaben en fotogrames sencers. Amb 4 decimals, a 29,97 fps l'inici
    del fotograma 1 (0,0333667 s) arribava com a 0,0334 i ffmpeg se'l saltava. Ara es parteix del
    número de fotograma i s'arrodoneix cap avall al microsegon (que és com ho compta ffmpeg)."""
    f = Fraction(fps)
    fa, fb = round(Fraction(a) * f), round(Fraction(b) * f)
    inici = (fa * 1_000_000 * f.denominator) // f.numerator
    durada = ((fb - fa) * 1_000_000 * f.denominator) // f.numerator
    return tuple(f"{us // 1_000_000}.{us % 1_000_000:06d}" for us in (inici, durada))


def _enquadrament(amplada: int, alcada: int, ow: int, oh: int) -> str:
    """Retalla el centre fins a 9:16 (si cal) i escala a la mida final."""
    if amplada * 16 > alcada * 9:      # més ample que 9:16 (p. ex. horitzontal)
        retall = "crop=trunc(ih*9/16/2)*2:ih"
    elif amplada * 16 < alcada * 9:    # més estret que 9:16
        retall = "crop=iw:trunc(iw*16/9/2)*2"
    else:
        retall = None
    escala = f"scale={ow}:{oh}:flags=lanczos,setsar=1,format=yuv420p"
    return f"{retall},{escala}" if retall else escala


def _filtre(trams: list[tuple[float, float]], enquadrament: str, capa: bool = False,
            zooms: list[bool] | None = None, mida: tuple[int, int] | None = None,
            brolls: list[dict] | None = None, peces: list[dict] | None = None,
            veu: str | None = None, efectes: bool = False) -> str:
    """Cada tros és una entrada pròpia (ja retallada amb -ss/-t); aquí només s'uneixen.

    Ordre de les entrades: els trossos, els b-rolls (un per entrada, ja preparats), les imatges
    fixes de les targetes (forma i marc, vegeu `_entrades_peces`) i, al final, la capa de
    subtítols i, si n'hi ha, la pista d'efectes de so. Les capes s'apilen així: vídeo, b-roll i
    subtítols a dalt. `veu`: els filtres de la neteja de la veu (motor/so.py), o None."""
    brolls = brolls or []
    parts, entrades = [], []
    for i, (a, b) in enumerate(trams):
        d = b - a
        if zooms and zooms[i] and mida:
            # Apropament: retallem el centre i el tornem a la mida original perquè tots els trossos casin.
            parts.append(f"[{i}:v]setpts=PTS-STARTPTS,crop=trunc(iw/{ZOOM}/2)*2:trunc(ih/{ZOOM}/2)*2,"
                         f"scale={mida[0]}:{mida[1]},setsar=1[v{i}];")
        else:
            parts.append(f"[{i}:v]setpts=PTS-STARTPTS,setsar=1[v{i}];")  # píxels quadrats: concat els vol iguals
        parts.append(f"[{i}:a]asetpts=PTS-STARTPTS,"
                     f"afade=t=in:st=0:d={FOS_AUDIO},afade=t=out:st={max(0, d - FOS_AUDIO):.4f}:d={FOS_AUDIO}[a{i}];")
        entrades.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(entrades)}concat=n={len(trams)}:v=1:a=1[vc][ac];")
    mida_sortida = enquadrament.split("scale=")[1].split(":flags")[0]
    ow, oh = (int(x) for x in mida_sortida.split(":"))
    parts.append(f"[vc]{enquadrament}[vb0];")
    actual = "vb0"
    if brolls:
        # El b-roll comença a «inici» del muntatge: a pantalla sencera, en targeta, en pantalla
        # partida o en carrusel (motor/targetes.py, la mateixa disposició que la vista prèvia).
        peces = peces or [{"mascara": None, "marc": None} for _ in brolls]
        linies, actual = targetes.filtre(brolls, peces, len(trams), _entrades_peces(peces, len(trams) + len(brolls)),
                                         actual, (ow, oh))
        parts += linies
    n_peces = sum(1 for p in peces or [] for v in p.values() if v)
    if not capa:
        parts.append(f"[{actual}]null[vout];")
    else:
        # La capa de subtítols (ProRes amb transparència) va després del b-roll i les peces.
        # Cal passar tots dos a un format amb canal alfa perquè l'overlay la respecti.
        parts.append(f"[{actual}]format=yuva444p[vba];")
        parts.append(f"[{len(trams) + len(brolls) + n_peces}:v]scale={mida_sortida}:flags=lanczos,format=yuva444p[capa];")
        parts.append("[vba][capa]overlay=0:0:format=yuv444:eof_action=pass,format=yuv420p[vout];")
    # El so: la veu (neta, si toca) i, a sobre, els efectes; un limitador perquè res no saturi.
    parts.append(f"[ac]{veu or 'anull'}[aveu];")
    if efectes:
        entrada = len(trams) + len(brolls) + n_peces + (1 if capa else 0)
        parts.append(f"[{entrada}:a]aresample=48000[aef];")
        parts.append("[aveu][aef]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]")
    else:
        parts.append("[aveu]anull[aout]")
    return "\n".join(parts)


def _entrades_peces(peces: list[dict], primera: int) -> dict:
    """{(k, "mascara"|"marc"): índex de l'entrada}: les imatges fixes de les targetes, en ordre."""
    index, n = {}, primera
    for k, p in enumerate(peces):
        for tipus in ("mascara", "marc"):
            if p.get(tipus):
                index[(k, tipus)] = n
                n += 1
    return index


def _executa(ordre: list[str], durada: float, progres) -> None:
    """Executa ffmpeg i va cridant progres(percentatge) de 0 a 100."""
    # Els errors es llegeixen alhora, en un altre fil: si ffmpeg n'escriu molts (un vídeo malmès)
    # i ningú no els llegeix, el canal s'omple, ffmpeg s'espera i l'export no acaba mai.
    errors = collections.deque(maxlen=200)
    with subprocess.Popen(ordre, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          errors="replace") as proces:
        fil = threading.Thread(target=lambda: errors.extend(proces.stderr), daemon=True)
        fil.start()
        for linia in proces.stdout:
            if progres and linia.startswith("out_time_us="):
                try:
                    progres(min(100, int(int(linia.split("=")[1]) / 1e6 / durada * 100)))
                except ValueError:
                    continue
        proces.wait()
        fil.join()
    if proces.returncode != 0:
        raise RuntimeError("ffmpeg ha fallat:\n" + "".join(errors)[-2000:])


def exporta(video: Path, trams: list[tuple[float, float]], sortida: Path, qualitat: str,
            progres=None, capa: Path | None = None, zooms: list[bool] | None = None,
            brolls: list[dict] | None = None, neteja: str | None = None, efectes: Path | None = None) -> Path:
    """`brolls`: [{"fitxer": Path, "inici": segons del muntatge, "durada": segons}], ja disposats
    amb `targetes.disposa` (si no ho estan, van a pantalla sencera). `neteja`: el nivell de la
    neteja de la veu (motor/so.py) o None; `efectes`: la pista d'efectes de so (WAV) o None."""
    if not trams:
        raise ValueError("No queda cap paraula: no hi ha res per exportar.")
    ow, oh, bitrate = QUALITATS[qualitat]
    info = info_video(video)
    enquadrament = _enquadrament(info["amplada"], info["alcada"], ow, oh)

    brolls = [b if "caixa" in b else targetes.disposa([b], {})[0] for b in brolls or []]
    sortida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporal:
        if efectes is not None:  # una còpia pròpia: la pàgina pot refer la pista mentre s'exporta
            efectes = Path(shutil.copy(efectes, Path(temporal) / "efectes.wav"))
        # Les targetes arrodonides, amb vora o amb ombra necessiten unes imatges fixes (forma i marc).
        peces = targetes.prepara_peces(brolls, ow / targetes.AMPLADA, Path(temporal))
        veu = so.filtre_veu(neteja, _mesura_veu(video, trams, info, neteja)) if neteja else None
        filtre = Path(temporal) / "filtre.txt"
        filtre.write_text(_filtre(trams, enquadrament, capa=capa is not None, zooms=zooms,
                                  mida=(info["amplada"], info["alcada"]), brolls=brolls, peces=peces,
                                  veu=veu, efectes=efectes is not None),
                          encoding="utf-8")
        _exporta(video, trams, sortida, qualitat, info, filtre, brolls, peces, capa, progres, efectes)
    return sortida


def _entrades_trams(video: Path, trams, info) -> list[str]:
    entrades = []
    for a, b in trams:
        inici, durada = temps_exactes(a, b, info["fps"])
        entrades += ["-ss", inici, "-t", durada, "-i", str(video)]
    return entrades


def _mesura_veu(video: Path, trams, info, nivell: str) -> dict:
    """Primera passada de la neteja: mesura el volum de la veu ja muntada (només l'àudio: va de pressa)."""
    parts = [f"[{i}:a]asetpts=PTS-STARTPTS,afade=t=in:st=0:d={FOS_AUDIO},"
             f"afade=t=out:st={max(0, b - a - FOS_AUDIO):.4f}:d={FOS_AUDIO}[a{i}];" for i, (a, b) in enumerate(trams)]
    parts.append(f"{''.join(f'[a{i}]' for i in range(len(trams)))}concat=n={len(trams)}:v=0:a=1,"
                 f"{so.filtre_veu(nivell, None)}[m]")
    resultat = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *_entrades_trams(video, trams, info),
                               "-filter_complex", "".join(parts), "-map", "[m]", "-f", "null", "-"],
                              capture_output=True, text=True)
    return so.llegeix_mesura(resultat.stderr)


def _exporta(video, trams, sortida, qualitat, info, filtre, brolls, peces, capa, progres, efectes=None) -> None:
    _, _, bitrate = QUALITATS[qualitat]

    # Cada tros s'obre com una entrada pròpia: ffmpeg salta directament al seu inici
    # i només descodifica el que fem servir (molt més ràpid amb gravacions llargues).
    # Descodifiquem amb el processador: en Macs Intel, fer-ho amb la gràfica i baixar
    # els fotogrames 4K a memòria és unes 4 vegades més lent.
    entrades = _entrades_trams(video, trams, info)
    for b in brolls:
        entrades += ["-i", str(b["fitxer"])]
    for b, p in zip(brolls, peces):
        for tipus in ("mascara", "marc"):
            if p.get(tipus):  # una imatge quieta que dura el que es veu la targeta
                entrades += ["-loop", "1", "-framerate", "30", "-t", f"{b['fins'] - b['inici'] + 0.1:.3f}",
                             "-i", str(p[tipus])]
    if capa is not None:
        entrades += ["-i", str(capa)]
    if efectes is not None:
        entrades += ["-i", str(efectes)]

    ordre = [
        "ffmpeg", "-y", "-v", "error", "-progress", "pipe:1", "-nostats", *entrades,
        "-filter_complex_script", filtre, "-map", "[vout]", "-map", "[aout]",
        "-r", info["fps"],
        "-c:v", "h264_videotoolbox", "-b:v", bitrate, "-maxrate", bitrate, "-profile:v", "high",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-map_metadata", "-1", "-write_tmcd", "0", "-movflags", "+faststart", str(sortida),
    ]
    _executa(ordre, sum(b - a for a, b in trams), progres)
    treu_rotacio(sortida)


def fes_proxy(video: Path, sortida: Path, progres=None) -> Path:
    """Còpia lleugera i vertical de tota la gravació, per al reproductor de la pàgina de revisió.

    Un fotograma clau cada mig segon perquè els salts entre trossos siguin instantanis."""
    info = info_video(video)
    enquadrament = _enquadrament(info["amplada"], info["alcada"], 720, 1280).replace("lanczos", "fast_bilinear")
    temporal = sortida.with_suffix(".tmp.mp4")
    ordre = [
        "ffmpeg", "-y", "-v", "error", "-progress", "pipe:1", "-nostats", "-i", str(video),
        "-map", "0:v:0", "-map", "0:a:0", "-vf", enquadrament,
        "-c:v", "h264_videotoolbox", "-b:v", "3M", "-g", "15",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-map_metadata", "-1", "-write_tmcd", "0", "-movflags", "+faststart", str(temporal),
    ]
    _executa(ordre, info["durada"], progres)
    treu_rotacio(temporal)
    temporal.replace(sortida)
    return sortida
