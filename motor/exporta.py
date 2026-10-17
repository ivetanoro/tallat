"""Export del muntatge a MP4 vertical 9:16 amb ffmpeg."""
from __future__ import annotations

import collections
import functools
import json
import os
import shutil
import subprocess
import tempfile
import threading
from fractions import Fraction
from pathlib import Path

from motor import grafics, so, targetes
from motor.edicio import so_del_tram

QUALITATS = {
    # nom: (amplada, alçada, bitrate de vídeo)
    "esborrany": (720, 1280, "4M"),
    "1080": (1080, 1920, "16M"),
    "4k": (2160, 3840, "45M"),
}
PREFERENCIES = Path.home() / ".tallat" / "preferencies.json"  # la carpeta on la persona vol els vídeos
FOS_AUDIO = 0.01  # segons de fos a cada tall, perquè no se sentin clics
ZOOM = 1.15       # apropament dels trossos amb zoom (instrucció de veu «Claude, zoom aquí»)
# Cada tros és una entrada d'ffmpeg, i cada entrada guarda uns quants fotogrames a la memòria: amb el
# vídeo 4K d'una càmera, uns 230 MB (mesurat; 20 trossos de cop, més de 4 GB). Amb més trossos dels que
# hi caben, el muntatge es fa a lots (vegeu _munta_lots). I cada entrada descodifica amb pocs fils: amb
# tots els del processador per a cadascuna, s'estorben i va tres vegades més lent.
MEMORIA_LOT = 2_000_000_000
FILS_PER_ENTRADA = "4"


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


def _so_del_tros(i: int, tram) -> str:
    """El so del tros i (l'entrada i ja comença a l'inici del tros): un fos curt a cada costat perquè no
    se sentin clics. Si el so de debò (Tram.so) comença després o acaba abans que els fotogrames, fora
    d'aquí queda en silenci: és el bocí de fotograma d'una paraula treta. En un tros molt curt, el fos
    també ho és (com a molt una quarta part del que sona)."""
    a, b = tram[0], tram[1]
    sa, sb = so_del_tram(tram)
    inici, final = max(0.0, sa - a), max(0.0, min(b - a, sb - a))
    # El fos mai no passa de la finestra (abans tenia un mínim d'1 ms, i en una finestra més curta se'n
    # sortia, revisió de Codex). Temps al microsegon: amb quatre decimals podia quedar alguna mostra fora.
    fos = max(1e-6, min(FOS_AUDIO, (final - inici) / 4))
    return (f"[{i}:a]asetpts=PTS-STARTPTS,afade=t=in:st={inici:.6f}:d={fos:.6f},"
            f"afade=t=out:st={max(inici, final - fos):.6f}:d={fos:.6f}[a{i}];")


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


def _uneix_trossos(trams, zooms: list[bool] | None, mida: tuple[int, int] | None) -> list[str]:
    """Les línies del filtre que uneixen els trossos (entrades 0…n-1, ja retallades amb -ss/-t) en [vc][ac]."""
    parts, entrades = [], []
    for i, tram in enumerate(trams):
        if zooms and zooms[i] and mida:
            # Apropament: retallem el centre i el tornem a la mida original perquè tots els trossos casin.
            parts.append(f"[{i}:v]setpts=PTS-STARTPTS,crop=trunc(iw/{ZOOM}/2)*2:trunc(ih/{ZOOM}/2)*2,"
                         f"scale={mida[0]}:{mida[1]},setsar=1[v{i}];")
        else:
            parts.append(f"[{i}:v]setpts=PTS-STARTPTS,setsar=1[v{i}];")  # píxels quadrats: concat els vol iguals
        parts.append(_so_del_tros(i, tram))
        entrades.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(entrades)}concat=n={len(trams)}:v=1:a=1[vc][ac];")
    return parts


def _filtre(trams: list[tuple[float, float]], enquadrament: str, capa: bool = False,
            zooms: list[bool] | None = None, mida: tuple[int, int] | None = None,
            brolls: list[dict] | None = None, peces: list[dict] | None = None,
            veu: str | None = None, efectes: bool = False, blocs: list[dict] | None = None,
            fps: str = "30", base: bool = False) -> str:
    """Cada tros és una entrada pròpia (ja retallada amb -ss/-t); aquí només s'uneixen. Amb `base`, la
    primera entrada ja és el muntatge sencer, enquadrat (fet a lots, _munta_lots) i no hi ha la resta.

    Ordre de les entrades: els trossos (o el muntatge), els b-rolls (un per entrada, ja preparats), les
    imatges fixes de les targetes (forma i marc, vegeu `_entrades_peces`) i, al final, la capa de
    subtítols i, si n'hi ha, la pista d'efectes de so. Les capes s'apilen així: vídeo (encongit dins
    del bloc de color, si n'hi ha), b-roll i subtítols a dalt. `veu`: els filtres de la neteja de la veu
    (motor/so.py), o None. `blocs`: els blocs de color (grafics.blocs); `fps`, els del vídeo."""
    brolls = brolls or []
    mida_sortida = enquadrament.split("scale=")[1].split(":flags")[0]
    ow, oh = (int(x) for x in mida_sortida.split(":"))
    if base:
        n_base = 1
        parts = ["[0:v]setpts=PTS-STARTPTS[vb0];", "[0:a]asetpts=PTS-STARTPTS[ac];"]
    else:
        n_base = len(trams)
        parts = _uneix_trossos(trams, zooms, mida)
        parts.append(f"[vc]{enquadrament}[vb0];")
    actual = "vb0"
    total = sum(b - a for a, b in trams)
    for i, bloc in enumerate(blocs or []):
        linies, actual = _filtre_bloc(bloc, i, actual, (ow, oh), fps, total)
        parts += linies
    if brolls:
        # El b-roll comença a «inici» del muntatge: a pantalla sencera, en targeta, en pantalla
        # partida o en carrusel (motor/targetes.py, la mateixa disposició que la vista prèvia).
        peces = peces or [{"mascara": None, "marc": None} for _ in brolls]
        linies, actual = targetes.filtre(brolls, peces, n_base, _entrades_peces(peces, n_base + len(brolls)),
                                         actual, (ow, oh))
        parts += linies
    n_peces = sum(1 for p in peces or [] for v in p.values() if v)
    if not capa:
        parts.append(f"[{actual}]null[vout];")
    else:
        # La capa de subtítols (ProRes amb transparència) va després del b-roll i les peces.
        # Cal passar tots dos a un format amb canal alfa perquè l'overlay la respecti.
        parts.append(f"[{actual}]format=yuva444p[vba];")
        parts.append(f"[{n_base + len(brolls) + n_peces}:v]scale={mida_sortida}:flags=lanczos,format=yuva444p[capa];")
        parts.append("[vba][capa]overlay=0:0:format=yuv444:eof_action=pass,format=yuv420p[vout];")
    # El so: la veu (neta, si toca) i, a sobre, els efectes; un limitador perquè res no saturi.
    parts.append(f"[ac]{veu or 'anull'}[aveu];")
    if efectes:
        entrada = n_base + len(brolls) + n_peces + (1 if capa else 0)
        parts.append(f"[{entrada}:a]aresample=48000[aef];")
        parts.append("[aveu][aef]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]")
    else:
        parts.append("[aveu]anull[aout]")
    return "\n".join(parts)


def _color_ffmpeg(color: str) -> str:
    """«#5E8B6B» o «#5e8» → «0x5E8B6B» (el que entén ffmpeg); si no és un color així, gairebé negre."""
    c = str(color).strip().lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    return "0x" + c.upper() if len(c) == 6 and all(x in "0123456789abcdefABCDEF" for x in c) else "0x111111"


def _filtre_bloc(bloc: dict, i: int, actual: str, mida: tuple[int, int], fps: str,
                 total: float) -> tuple[list[str], str]:
    """Un bloc de color (motor/grafics.py, BLOC): entre `inici` i `final`, el vídeo s'encongeix fins a la
    targeta de baix sobre el color de la marca i, al final, torna a créixer. El vídeo sencer passa per un
    scale que, fotograma a fotograma, el deixa igual fora del bloc i l'encongeix a dins; es posa sobre un
    fons del color (tan llarg com el vídeo) i dues franges del mateix color en retallen el que sobresurt
    per dalt i per baix. Sense còpies del vídeo: si n'hi hagués una que comencés al bloc, ffmpeg hauria de
    guardar a la memòria tots els fotogrames d'abans. La pàgina fa el mateix (app.js, pintaBloc)."""
    ow, oh = mida
    k = ow / 1080
    a, b = bloc["inici"], bloc["final"]
    llarg = b - a
    d = max(0.001, min(grafics.ANIMACIO_BLOC, llarg / 2))
    g = grafics.BLOC
    s_fi = g["w"] / 1080  # l'escala de la targeta
    ty_fi = g["y"] - g["retall_y"] * s_fi  # on queda la part de dalt del vídeo encongit
    franja_dalt = 2 * round(k * g["y"] / 2)
    franja_baix = 2 * round(k * (1920 - g["y"] - g["h"]) / 2)
    # Com pas_bloc, amb el temps del vídeo: 0 fora del bloc, 0 → 1 en entrar, 1 → 0 en sortir, suau.
    # Cada expressió el calcula de nou (no comparteixen variables).
    e = f"(st(1,clip(min((t-{a:.4f})/{d:.4f},({b:.4f}-t)/{d:.4f}),0,1));ld(1)*ld(1)*(3-2*ld(1)))"
    s = f"(1-{1 - s_fi:.5f}*{e})"
    dins = f"between(t,{a:.4f},{b:.4f})"
    color = _color_ffmpeg(bloc["color"])
    # Els fons, una mica més llargs que el vídeo: cada overlay s'acaba amb el més curt (shortest), el vídeo.
    font = f"color=c={color}:r={fps}:d={total + 1:.4f}"
    return [
        f"[{actual}]scale=w='2*trunc({ow}*{s}/2)':h='2*trunc({oh}*{s}/2)':eval=frame[bv{i}];",
        f"{font}:s={ow}x{oh}[bf{i}];",
        f"{font}:s={ow}x{franja_dalt}[bd{i}];",
        f"{font}:s={ow}x{franja_baix}[bb{i}];",
        f"[bf{i}][bv{i}]overlay=x='{k * g['x']:.3f}*{e}':y='{k * ty_fi:.3f}*{e}':eval=frame:shortest=1[bo{i}];",
        f"[bo{i}][bd{i}]overlay=x=0:y='{franja_dalt}*{e}-{franja_dalt}':eval=frame:enable='{dins}':shortest=1[bp{i}];",
        f"[bp{i}][bb{i}]overlay=x=0:y='{oh}-{franja_baix}*{e}':eval=frame:enable='{dins}':shortest=1[vbl{i}];",
    ], f"vbl{i}"


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
            brolls: list[dict] | None = None, neteja: str | None = None, efectes: Path | None = None,
            blocs: list[dict] | None = None) -> Path:
    """`brolls`: [{"fitxer": Path, "inici": segons del muntatge, "durada": segons}], ja disposats
    amb `targetes.disposa` (si no ho estan, van a pantalla sencera). `neteja`: el nivell de la
    neteja de la veu (motor/so.py) o None; `efectes`: la pista d'efectes de so (WAV) o None;
    `blocs`: els blocs de color dels gràfics (Projecte.blocs) o None."""
    if not trams:
        raise ValueError("No queda cap paraula: no hi ha res per exportar.")
    ow, oh, bitrate = QUALITATS[qualitat]
    info = info_video(video)
    enquadrament = _enquadrament(info["amplada"], info["alcada"], ow, oh)

    brolls = [b if "caixa" in b else targetes.disposa([b], {})[0] for b in brolls or []]
    sortida.parent.mkdir(parents=True, exist_ok=True)
    total = sum(b - a for a, b in trams)
    with tempfile.TemporaryDirectory() as temporal:
        if efectes is not None:  # una còpia pròpia: la pàgina pot refer la pista mentre s'exporta
            efectes = Path(shutil.copy(efectes, Path(temporal) / "efectes.wav"))
        # Les targetes arrodonides, amb vora o amb ombra necessiten unes imatges fixes (forma i marc).
        peces = targetes.prepara_peces(brolls, ow / targetes.AMPLADA, Path(temporal))
        base = len(trams) > trossos_per_lot(info)
        if base:  # molts trossos: primer el muntatge a lots (60 % de la feina), després la resta
            llista = _munta_lots(video, trams, info, Path(temporal), ["-c:v", "h264_videotoolbox", "-b:v",
                                 _bitrate_intermedi(bitrate), "-profile:v", "high"], enquadrament=enquadrament,
                                 zooms=zooms, progres=_part_del_progres(progres, 0, 60))
            entrades = _entrada_lots(llista)
            progres = _part_del_progres(progres, 60, 100)
        else:
            entrades = _entrades_trams(video, trams, info)
        veu = so.filtre_veu(neteja, _mesura_veu(entrades, None if base else trams, neteja)) if neteja else None
        filtre = Path(temporal) / "filtre.txt"
        filtre.write_text(_filtre(trams, enquadrament, capa=capa is not None, zooms=zooms,
                                  mida=(info["amplada"], info["alcada"]), brolls=brolls, peces=peces,
                                  veu=veu, efectes=efectes is not None, blocs=blocs, fps=info["fps"], base=base),
                          encoding="utf-8")
        _exporta(entrades, total, sortida, qualitat, info, filtre, brolls, peces, capa, progres, efectes)
    return sortida


def comprova_durades(fitxer: Path, esperada: float, fps: str) -> str | None:
    """Després d'exportar: el vídeo i el so han de durar el mateix, i el que dura el muntatge. Si no (un
    vídeo amb fotogrames de durada variable, un tros que no s'ha pogut llegir sencer…), torna un avís."""
    try:
        streams = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration",
                                             "-of", "json", str(fitxer)], capture_output=True, text=True,
                                            check=True).stdout)["streams"]
        durades = {s_["codec_type"]: float(s_["duration"]) for s_ in streams if "duration" in s_}
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
        return None
    v, a = durades.get("video"), durades.get("audio")
    if v is None or a is None:
        return None
    marge = 2 / float(Fraction(fps))  # dos fotogrames
    if abs(v - a) > marge:
        return (f"Al vídeo exportat, la imatge dura {v:.2f} s i el so {a:.2f} s: pot ser que el so vagi "
                "una mica desplaçat. Mira-ho abans de publicar-lo.")
    if abs(v - esperada) > max(marge, 0.1):
        return f"El vídeo exportat dura {v:.2f} s i el muntatge {esperada:.2f} s: mira'l abans de publicar-lo."
    return None


def _entrades_trams(video: Path, trams, info) -> list[str]:
    """Cada tros, una entrada pròpia: ffmpeg salta directament al seu inici i només descodifica el que
    fem servir (molt més ràpid amb gravacions llargues). Descodifiquem amb el processador: en Macs Intel,
    fer-ho amb la gràfica i baixar els fotogrames 4K a memòria és unes 4 vegades més lent."""
    entrades = []
    for a, b in trams:
        inici, durada = temps_exactes(a, b, info["fps"])
        entrades += ["-threads", FILS_PER_ENTRADA, "-ss", inici, "-t", durada, "-i", str(video)]
    return entrades


def trossos_per_lot(info: dict) -> int:
    """Quants trossos es munten de cop sense passar de MEMORIA_LOT (mesurat: uns 20 MB per entrada més
    25 bytes per píxel; 4K → 8 trossos, 1080 → 27, la còpia lleugera → 40)."""
    per_entrada = 20_000_000 + 25 * info["amplada"] * info["alcada"]
    return max(4, min(40, MEMORIA_LOT // per_entrada))


def _bitrate_intermedi(bitrate: str) -> str:
    """El muntatge a lots es torna a codificar al final: el fem amb prou qualitat perquè no es noti."""
    return f"{int(bitrate.rstrip('M')) * 3}M"


def _part_del_progres(progres, de: float, fins: float):
    """Un progrés de 0 a 100 que l'altre veu entre `de` i `fins`."""
    if progres is None:
        return None
    return lambda pc: progres(int(de + (fins - de) * pc / 100))


def _munta_lots(video: Path, trams, info, carpeta: Path, codec_video: list[str], enquadrament: str | None = None,
                zooms: list[bool] | None = None, progres=None) -> Path:
    """El muntatge dels trossos a lots de trossos_per_lot(): cada lot és un fitxer amb la imatge (enquadrada,
    si cal) i el so ja units (el so sense comprimir, perquè en encadenar-los no hi hagi petits salts). Torna
    la llista per al «concat» d'ffmpeg, que els encadena com si fossin un sol vídeo."""
    mida_lot = trossos_per_lot(info)
    total = sum(b - a for a, b in trams) or 1
    fets, noms = 0.0, []
    for k in range(0, len(trams), mida_lot):
        lot = trams[k:k + mida_lot]
        parts = _uneix_trossos(lot, zooms[k:k + mida_lot] if zooms else None, (info["amplada"], info["alcada"]))
        parts.append(f"[vc]{enquadrament or 'null'}[v];[ac]anull[a]")
        filtre = carpeta / f"lot_{k:05d}.txt"
        filtre.write_text("\n".join(parts), encoding="utf-8")
        nom = carpeta / f"lot_{k:05d}.mov"
        durada = sum(b - a for a, b in lot)
        avanc = (lambda pc, d=durada, f=fets: progres(min(100, int((f + d * pc / 100) / total * 100)))) if progres else None
        _executa(["ffmpeg", "-y", "-v", "error", "-progress", "pipe:1", "-nostats", *_entrades_trams(video, lot, info),
                  "-filter_complex_script", str(filtre), "-map", "[v]", "-map", "[a]", "-r", info["fps"],
                  *codec_video, "-allow_sw", "1", "-c:a", "pcm_s16le", "-ar", "48000", str(nom)], durada, avanc)
        fets += durada
        noms.append(nom)
    llista = carpeta / "lots.txt"
    llista.write_text("".join(f"file '{n.name}'\n" for n in noms), encoding="utf-8")
    return llista


def _entrada_lots(llista: Path) -> list[str]:
    """Els lots com una sola entrada. Els seus fotogrames ja són drets, però l'ffmpeg 7.1 hi copia
    l'etiqueta «gira'l 90°» del vídeo de l'iPhone: sense -noautorotate, es tornaven a girar (revisió de Codex)."""
    return ["-noautorotate", "-f", "concat", "-safe", "0", "-i", str(llista)]


def _mesura_veu(entrades: list[str], trams, nivell: str) -> dict:
    """Primera passada de la neteja: mesura el volum de la veu ja muntada (només l'àudio: va de pressa).
    `entrades`: els trossos (i llavors `trams`, per unir-los) o el muntatge ja fet a lots (trams None)."""
    if trams is None:
        parts = [f"[0:a]{so.filtre_veu(nivell, None)}[m]"]
    else:
        parts = [_so_del_tros(i, tram) for i, tram in enumerate(trams)]
        parts.append(f"{''.join(f'[a{i}]' for i in range(len(trams)))}concat=n={len(trams)}:v=0:a=1,"
                     f"{so.filtre_veu(nivell, None)}[m]")
    resultat = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *entrades,
                               "-filter_complex", "".join(parts), "-map", "[m]", "-f", "null", "-"],
                              capture_output=True, text=True)
    return so.llegeix_mesura(resultat.stderr)


def _exporta(entrades_base, durada, sortida, qualitat, info, filtre, brolls, peces, capa, progres, efectes=None) -> None:
    _, _, bitrate = QUALITATS[qualitat]
    entrades = list(entrades_base)
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
    _executa(ordre, durada, progres)
    treu_rotacio(sortida)


@functools.lru_cache(maxsize=1)
def _te_x264() -> bool:
    try:
        return "libx264" in subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True,
                                           text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def fes_previa(proxy: Path, trams: list[tuple[float, float]], sortida: Path, curt: bool = False) -> Path:
    """El muntatge en un sol vídeo continu (de la còpia lleugera, sense subtítols ni res), perquè la pàgina
    el pugui reproduir sense saltar: als salts, el Safari s'encalla uns quants dècims de segon. Els talls
    i els fosos del so, com a l'export (el temps del muntatge és el mateix)."""
    if not trams:
        raise ValueError("No queda cap paraula")
    info = info_video(proxy)
    # Si la gràfica és ocupada (un export alhora), amb el processador (-allow_sw). Un vídeo `curt` (uns
    # segons per escoltar un tall) es fa amb x264: la gràfica tarda mig segon a arrencar i x264 no.
    codec_video = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-g", "15", "-pix_fmt", "yuv420p"]
                   if curt and _te_x264() else ["-c:v", "h264_videotoolbox", "-allow_sw", "1", "-b:v", "3M", "-g", "15"])
    sortida.parent.mkdir(parents=True, exist_ok=True)
    # Un nom propi per a cada feina: dues peticions iguals alhora no s'han de trepitjar el fitxer a mitges.
    temporal = sortida.with_name(f".{sortida.stem}.{os.getpid()}-{threading.get_ident()}.fent{sortida.suffix}")
    with tempfile.TemporaryDirectory() as carpeta:
        if len(trams) > trossos_per_lot(info):  # molts trossos: a lots, i la imatge dels lots es copia tal qual
            llista = _munta_lots(proxy, trams, info, Path(carpeta), codec_video)
            ordre = ["ffmpeg", "-y", "-v", "error", "-nostats", *_entrada_lots(llista),
                     "-map", "0:v", "-map", "0:a", "-c:v", "copy"]
        else:
            parts = _uneix_trossos(trams, None, None)
            parts.append("[vc]null[v];[ac]anull[a]")
            filtre = Path(carpeta) / "previa.txt"
            filtre.write_text("\n".join(parts), encoding="utf-8")
            ordre = ["ffmpeg", "-y", "-v", "error", "-nostats", *_entrades_trams(proxy, trams, info),
                     "-filter_complex_script", str(filtre), "-map", "[v]", "-map", "[a]", "-r", info["fps"],
                     *codec_video]
        ordre += ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(temporal)]
        try:
            # Un vídeo curt (l'escolta d'un tall) que no surt en mig minut, ja no cal: la pàgina se'n surt sense.
            r = subprocess.run(ordre, capture_output=True, text=True, timeout=30 if curt else None)
            if r.returncode != 0:
                raise RuntimeError("ffmpeg no ha pogut fer la previsualització:\n" + r.stderr[-1500:])
            temporal.replace(sortida)
        finally:
            temporal.unlink(missing_ok=True)
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
    treu_rotacio(temporal)
    temporal.replace(sortida)
    return sortida
