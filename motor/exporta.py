"""Export del muntatge a MP4 vertical 9:16 amb ffmpeg."""
from __future__ import annotations

import json
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

QUALITATS = {
    # nom: (amplada, alçada, bitrate de vídeo)
    "esborrany": (720, 1280, "4M"),
    "1080": (1080, 1920, "16M"),
    "4k": (2160, 3840, "45M"),
}
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
    # Les versions noves de ffprobe la donen a side_data_list; les antigues, a tags.rotate.
    rotacio = next((int(float(x["rotation"])) for x in s.get("side_data_list", []) if "rotation" in x),
                   int(float(s.get("tags", {}).get("rotate", 0) or 0)))
    if abs(rotacio) % 180 == 90:  # l'iPhone desa el vertical com a horitzontal + «gira'l 90°»
        amplada, alcada = alcada, amplada
    return {"amplada": amplada, "alcada": alcada,
            "fps": str(Fraction(s["r_frame_rate"])), "durada": float(d["format"]["duration"])}


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
            zooms: list[bool] | None = None, mida: tuple[int, int] | None = None) -> str:
    """Cada tros és una entrada pròpia (ja retallada amb -ss/-t); aquí només s'uneixen."""
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
    if not capa:
        parts.append(f"[vc]{enquadrament}[vout]")
    else:
        # La capa de subtítols (ProRes amb transparència) és l'última entrada.
        # Cal passar tots dos a un format amb canal alfa perquè l'overlay la respecti.
        mida = enquadrament.split("scale=")[1].split(":flags")[0]
        parts.append(f"[vc]{enquadrament},format=yuva444p[vb];")
        parts.append(f"[{len(trams)}:v]scale={mida}:flags=lanczos,format=yuva444p[capa];")
        parts.append("[vb][capa]overlay=0:0:format=yuv444:eof_action=pass,format=yuv420p[vout]")
    return "\n".join(parts)


def _executa(ordre: list[str], durada: float, progres) -> None:
    """Executa ffmpeg i va cridant progres(percentatge) de 0 a 100."""
    proces = subprocess.Popen(ordre, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for linia in proces.stdout:
        if progres and linia.startswith("out_time_us="):
            try:
                progres(min(100, int(int(linia.split("=")[1]) / 1e6 / durada * 100)))
            except ValueError:
                continue
    proces.wait()
    if proces.returncode != 0:
        raise RuntimeError("ffmpeg ha fallat:\n" + proces.stderr.read()[-2000:])


def exporta(video: Path, trams: list[tuple[float, float]], sortida: Path, qualitat: str,
            progres=None, capa: Path | None = None, zooms: list[bool] | None = None) -> Path:
    if not trams:
        raise ValueError("No queda cap paraula: no hi ha res per exportar.")
    ow, oh, bitrate = QUALITATS[qualitat]
    info = info_video(video)
    enquadrament = _enquadrament(info["amplada"], info["alcada"], ow, oh)

    sortida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(_filtre(trams, enquadrament, capa=capa is not None, zooms=zooms,
                        mida=(info["amplada"], info["alcada"])))
        filtre = f.name

    # Cada tros s'obre com una entrada pròpia: ffmpeg salta directament al seu inici
    # i només descodifica el que fem servir (molt més ràpid amb gravacions llargues).
    # Descodifiquem amb el processador: en Macs Intel, fer-ho amb la gràfica i baixar
    # els fotogrames 4K a memòria és unes 4 vegades més lent.
    entrades = []
    for a, b in trams:
        entrades += ["-ss", f"{a:.4f}", "-t", f"{b - a:.4f}", "-i", str(video)]
    if capa is not None:
        entrades += ["-i", str(capa)]

    ordre = [
        "ffmpeg", "-y", "-v", "error", "-progress", "pipe:1", "-nostats", *entrades,
        "-filter_complex_script", filtre, "-map", "[vout]", "-map", "[ac]",
        "-r", info["fps"],
        "-c:v", "h264_videotoolbox", "-b:v", bitrate, "-maxrate", bitrate, "-profile:v", "high",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-map_metadata", "-1", "-write_tmcd", "0", "-movflags", "+faststart", str(sortida),
    ]
    try:
        _executa(ordre, sum(b - a for a, b in trams), progres)
    finally:
        Path(filtre).unlink(missing_ok=True)
    return sortida


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
    temporal.replace(sortida)
    return sortida
