"""Exportar el muntatge per acabar-lo en un altre editor.

Escriu una carpeta a exports/ amb:
  NOM.fcpxml      Final Cut Pro (10.6 o més nou) i DaVinci Resolve (18 o més nou)
  NOM.xml         Premiere Pro (format XML de Final Cut 7, que Premiere importa)
  NOM.srt         els subtítols, en temps del muntatge
  subtitols.mov   (opcional) els subtítols, el títol i els gràfics de tallat, amb el fons transparent
  LLEGEIX-ME.txt  com obrir-ho a cada editor, i a CapCut (que no importa projectes)

Per a CapCut o iMovie, que no importen projectes d'altres editors, `exporta_trossos()` treu cada
tros del muntatge com un clip numerat (01.mp4, 02.mp4…): arrossegats tots alhora a la línia de
temps, queden en ordre i cada tall es pot retocar.

Els talls fan referència al vídeo original (no se'n fa cap còpia): no el moguis de lloc.
El b-roll i els stickers sí que s'hi copien (a recursos/, els stickers en PNG perquè tots els
editors els llegeixin).
Hi van els talls, els zooms, el b-roll i els stickers, cadascun a la seva pista. El tall i el
so són exactes al fotograma; les posicions dels stickers són aproximades (cada editor les
interpreta una mica diferent).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from motor import exporta, grafics, subtitols

AMPLADA, ALCADA = 1080, 1920
FPS_RECURSOS = 30  # el b-roll (motor/broll.py) i la capa de subtítols (motor/subtitols.py) es fan a 30 fps


def _mida_imatge(path: Path) -> tuple[int, int]:
    sortida = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height", "-of", "json", str(path)],
                             capture_output=True, text=True, check=True).stdout
    s = json.loads(sortida)["streams"][0]
    return int(s["width"]), int(s["height"])


def _hhmmss(segons: float) -> str:
    ms = max(0, round(segons * 1000))
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt(linies: list[dict]) -> str:
    """Els subtítols en format SRT (temps del muntatge)."""
    blocs = []
    for i, linia in enumerate(linies, 1):
        text = " ".join(w["text"] for w in linia["paraules"])
        blocs.append(f"{i}\n{_hhmmss(linia['inici'])} --> {_hhmmss(linia['final'])}\n{text}\n")
    return "\n".join(blocs)


class _Temps:
    """Temps en fotogrames, escrits com els volen els editors."""

    def __init__(self, fps: str | float):
        self.fr = Fraction(str(fps)).limit_denominator(1001)

    def fotogrames(self, segons: float) -> int:
        return round(segons * self.fr)

    def fcp(self, fotogrames: int) -> str:  # FCPXML: segons racionals, «45/30s»
        f = Fraction(fotogrames) / self.fr
        return "0s" if f == 0 else (f"{f.numerator}s" if f.denominator == 1 else f"{f.numerator}/{f.denominator}s")

    @property
    def durada_fotograma(self) -> str:
        f = 1 / self.fr
        return f"{f.numerator}/{f.denominator}s"

    @property
    def timebase(self) -> tuple[int, bool]:  # XML de Premiere: base entera i si és NTSC (29,97…)
        base = round(self.fr)
        return base, self.fr.denominator != 1


def _plan(projecte, trams) -> dict:
    """Tot el que cal per escriure els projectes: trossos en fotogrames i recursos situats."""
    t = _Temps(projecte.dades["fps"])
    info = exporta.info_video(projecte.video)
    zooms = projecte.zooms_per_tram(trams)
    trossos, offset = [], 0
    for k, (a, b) in enumerate(trams):
        fa, fb = t.fotogrames(a), t.fotogrames(b)
        if fb <= fa:
            continue
        trossos.append({"a": fa, "b": fb, "offset": offset, "zoom": bool(zooms[k]) if k < len(zooms) else False})
        offset += fb - fa
    est_st = projecte.estil().get("stickers", {})
    stickers = []
    for k, st in enumerate(projecte.stickers(trams)):
        x = est_st.get("x", 0.72) if k % 2 == 0 else 1 - est_st.get("x", 0.72)
        rot = est_st.get("rotacio", 8) * (1 if k % 2 == 0 else -1)
        stickers.append(dict(st, x=x, y=est_st.get("y", 0.3), rot=rot, mida=est_st.get("mida", 0.34),
                             px=_mida_imatge(st["fitxer"])))
    brolls = projecte.brolls(trams)
    return {"t": t, "info": info, "trossos": trossos, "total": offset,
            "brolls": brolls, "carrils": _carrils(brolls), "stickers": stickers}


def _carrils(brolls: list[dict]) -> int:
    """Posa cada b-roll en un carril (una pista) on no en trepitgi cap altre: al carrusel, les
    targetes es queden totes alhora. Torna quants carrils calen."""
    finals: list[float] = []
    for br in sorted(brolls, key=lambda b: b["inici"]):
        lliure = next((i for i, f in enumerate(finals) if f <= br["inici"] + 1e-6), None)
        if lliure is None:
            finals.append(0.0)
            lliure = len(finals) - 1
        finals[lliure] = br.get("fins", br["inici"] + br["durada"])
        br["carril"] = lliure
    return max(1, len(finals))


def _copia_clip(br: dict, desti: Path) -> None:
    """Copia el clip d'un b-roll. Si la targeta es queda més estona que el clip (al carrusel, o un
    vídeo més curt), l'allarga amb l'últim fotograma, com fan la vista prèvia i el vídeo final."""
    visible = br.get("fins", br["inici"] + br["durada"]) - br["inici"]
    if visible <= br["durada"] + 0.02:
        shutil.copy(br["fitxer"], desti)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(br["fitxer"]), "-an", "-vf",
                        f"tpad=stop_mode=clone:stop_duration={visible:.3f},trim=duration={visible:.3f}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(desti)],
                       check=True, capture_output=True)
        br["durada"] = round(visible, 3)
    br["fitxer"] = desti


def _copia_recursos(pla: dict, desti: Path) -> None:
    """Copia el b-roll i els stickers a desti/recursos (els stickers, en PNG) i hi apunta el pla."""
    carpeta = desti / "recursos"
    carpeta.mkdir(exist_ok=True)
    for br in pla["brolls"]:
        _copia_clip(br, carpeta / Path(br["fitxer"]).name)
    for st in pla["stickers"]:
        nou = carpeta / (Path(st["fitxer"]).stem + ".png")
        if Path(st["fitxer"]).suffix.lower() == ".png":
            shutil.copy(st["fitxer"], nou)
        else:  # WebP, GIF, SVG…: no tots els editors els obren
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(st["fitxer"]), "-frames:v", "1", str(nou)],
                           check=True, capture_output=True)
        st["fitxer"] = nou
        st["px"] = _mida_imatge(nou)


def _lloc_broll(br: dict) -> dict | None:
    """On va un b-roll en targeta (motor/targetes.py), dit com ho entenen els editors: escala,
    centre (de -0,5 a 0,5), inclinació i quant se'n retalla per cada banda (0 a 1). None si tapa
    tota la pantalla. Les cantonades arrodonides, la vora i l'ombra no hi van."""
    c = br.get("caixa")
    if not c or (c["w"] >= AMPLADA and c["h"] >= ALCADA):
        return None
    dins_w, dins_h = c["w"] - 2 * c["vora"], c["h"] - 2 * c["vora"]
    k = max(dins_w / AMPLADA, dins_h / ALCADA)  # el clip cobreix la targeta, com a l'export
    return {"escala": k, "centre": ((c["x"] + c["w"] / 2) / AMPLADA - 0.5, (c["y"] + c["h"] / 2) / ALCADA - 0.5),
            "rotacio": c["rotacio"], "retall": ((1 - dins_w / (k * AMPLADA)) / 2, (1 - dins_h / (k * ALCADA)) / 2)}


def _tros_de(trossos: list[dict], f: int) -> dict:
    """El tros del muntatge on cau el fotograma f."""
    return next((x for x in trossos if x["offset"] <= f < x["offset"] + x["b"] - x["a"]), trossos[-1])


# --- Final Cut Pro i DaVinci Resolve (FCPXML 1.10) -------------------------------------------

def fcpxml(nom: str, video: Path, pla: dict, capa: Path | None = None) -> str:
    t, info, trossos = pla["t"], pla["info"], pla["trossos"]
    recursos = [
        f'<format id="r1" frameDuration="{t.durada_fotograma}" width="{AMPLADA}" height="{ALCADA}"/>',
        f'<format id="r2" frameDuration="{t.durada_fotograma}" width="{info["amplada"]}" height="{info["alcada"]}"/>',
        f'<asset id="r3" name="{_attr(video.stem)}" start="0s" duration="{t.fcp(t.fotogrames(info["durada"]))}" '
        f'hasVideo="1" hasAudio="1" format="r2" audioSources="1" audioChannels="2" audioRate="48000">'
        f'<media-rep kind="original-media" src="{_url(video)}"/></asset>',
        '<format id="r4" frameDuration="1/30s" width="1080" height="1920"/>',
        '<format id="r5" name="FFVideoFormatRateUndefined" width="1080" height="1920"/>',
    ]
    connectats: dict[int, list[str]] = {i: [] for i in range(len(trossos))}

    def connecta(f_inici: int, xml_fn) -> None:
        tros = _tros_de(trossos, f_inici)
        i = trossos.index(tros)
        connectats[i].append(xml_fn(tros["a"] + f_inici - tros["offset"]))

    n = 6
    for br in pla["brolls"]:
        rid, nom_br = f"r{n}", _attr(Path(br["fitxer"]).stem)
        n += 1
        durada = t.fotogrames(br["durada"])
        recursos.append(f'<asset id="{rid}" name="{nom_br}" start="0s" duration="{t.fcp(durada)}" hasVideo="1" '
                        f'format="r4"><media-rep kind="original-media" src="{_url(br["fitxer"])}"/></asset>')
        lloc, ajust = _lloc_broll(br), ""
        # En targeta: retallat, més petit i al seu lloc. A FCPXML, tant les posicions com el retall
        # (trim-rect, també l'esquerra i la dreta) van en % de l'alçada del fotograma; y amunt.
        if lloc:
            rh, rv = lloc["retall"]
            ajust = (f'<adjust-crop mode="trim"><trim-rect left="{rh * AMPLADA / ALCADA * 100:.3f}" '
                     f'right="{rh * AMPLADA / ALCADA * 100:.3f}" top="{rv * 100:.3f}" bottom="{rv * 100:.3f}"/>'
                     f'</adjust-crop><adjust-transform position="{lloc["centre"][0] * AMPLADA / ALCADA * 100:.2f} '
                     f'{-lloc["centre"][1] * 100:.2f}" scale="{lloc["escala"]:.4f} {lloc["escala"]:.4f}" '
                     f'rotation="{-lloc["rotacio"]:g}"/>')
        carril = 1 + br.get("carril", 0)  # les targetes que coincideixen, cadascuna al seu
        connecta(t.fotogrames(br["inici"]), lambda off, rid=rid, nom_br=nom_br, durada=durada, ajust=ajust, carril=carril:
                 f'<asset-clip ref="{rid}" lane="{carril}" offset="{t.fcp(off)}" name="{nom_br}" start="0s" '
                 f'duration="{t.fcp(durada)}">{ajust}</asset-clip>' if ajust else
                 f'<asset-clip ref="{rid}" lane="{carril}" offset="{t.fcp(off)}" name="{nom_br}" start="0s" '
                 f'duration="{t.fcp(durada)}"/>')
    carril_stickers = pla.get("carrils", 1) + 1
    for st in pla["stickers"]:
        rid, nom_st = f"r{n}", _attr(Path(st["fitxer"]).stem)
        fid = f"r{n + 1}"
        n += 2
        w, h = st["px"]
        recursos.append(f'<format id="{fid}" name="FFVideoFormatRateUndefined" width="{w}" height="{h}"/>')
        recursos.append(f'<asset id="{rid}" name="{nom_st}" start="0s" duration="0s" hasVideo="1" format="{fid}">'
                        f'<media-rep kind="original-media" src="{_url(st["fitxer"])}"/></asset>')
        # Final Cut encabeix les imatges al fotograma: escalem fins a l'amplada que toca.
        encabida = min(AMPLADA, w * ALCADA / h)
        escala = st["mida"] * AMPLADA / encabida
        pos_x = (st["x"] - 0.5) * AMPLADA / ALCADA * 100  # en % de l'alçada, 0 0 al centre i y amunt
        pos_y = (0.5 - st["y"]) * 100
        durada = t.fotogrames(st["durada"])
        connecta(t.fotogrames(st["inici"]), lambda off, rid=rid, nom_st=nom_st, durada=durada, escala=escala,
                 pos_x=pos_x, pos_y=pos_y, rot=st["rot"]:
                 f'<video ref="{rid}" lane="{carril_stickers}" offset="{t.fcp(off)}" name="{nom_st}" start="0s" duration="{t.fcp(durada)}">'
                 f'<adjust-transform position="{pos_x:.2f} {pos_y:.2f}" scale="{escala:.4f} {escala:.4f}" '
                 f'rotation="{-rot:g}"/></video>')
    if capa is not None:
        recursos.append(f'<asset id="r{n}" name="subtitols" start="0s" duration="{t.fcp(pla["total"])}" hasVideo="1" '
                        f'format="r4"><media-rep kind="original-media" src="{_url(capa)}"/></asset>')
        connectats[0].append(f'<asset-clip ref="r{n}" lane="{carril_stickers + 1}" offset="{t.fcp(trossos[0]["a"])}" name="subtitols" '
                             f'start="0s" duration="{t.fcp(pla["total"])}"/>')

    espina = []
    for i, x in enumerate(trossos):
        ajustos = '<adjust-conform type="fill"/>'
        if x["zoom"]:
            ajustos += f'<adjust-transform scale="{exporta.ZOOM} {exporta.ZOOM}"/>'
        espina.append(f'<asset-clip ref="r3" offset="{t.fcp(x["offset"])}" name="{_attr(video.stem)}" '
                      f'start="{t.fcp(x["a"])}" duration="{t.fcp(x["b"] - x["a"])}" format="r2" tcFormat="NDF">'
                      f'{ajustos}{"".join(connectats[i])}</asset-clip>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.10">\n'
            f'  <resources>\n    {chr(10).join("    " + r if j else r for j, r in enumerate(recursos))}\n  </resources>\n'
            f'  <library>\n    <event name="tallat">\n      <project name="{_attr(nom)}">\n'
            f'        <sequence format="r1" duration="{t.fcp(pla["total"])}" tcStart="0s" tcFormat="NDF" '
            f'audioLayout="stereo" audioRate="48k">\n          <spine>\n'
            + "\n".join("            " + e for e in espina) +
            '\n          </spine>\n        </sequence>\n      </project>\n    </event>\n  </library>\n</fcpxml>\n')


def _attr(text) -> str:
    """Text a punt per anar dins d'un atribut entre cometes: un nom com «la "meva" gravació» no el trenca."""
    return escape(str(text), {'"': "&quot;"})


def _url(path: Path) -> str:
    return "file://" + quote(str(Path(path).resolve()))


# --- Premiere Pro (XML de Final Cut 7) ---------------------------------------------------------

def xmeml(nom: str, video: Path, pla: dict, capa: Path | None = None) -> str:
    t, info, trossos = pla["t"], pla["info"], pla["trossos"]
    # El b-roll i la capa de subtítols són a 30 fps encara que el vídeo sigui a 60 (o a 25): els
    # punts d'entrada i de sortida d'un fitxer es compten amb els seus fps; on comença i on acaba
    # a la seqüència, amb els de la seqüència.
    t30 = _Temps(FPS_RECURSOS)

    def rate_de(temps: _Temps) -> str:
        base, ntsc = temps.timebase
        return f"<rate><timebase>{base}</timebase><ntsc>{'TRUE' if ntsc else 'FALSE'}</ntsc></rate>"
    rate, rate30 = rate_de(t), rate_de(t30)
    total_font = t.fotogrames(info["durada"])
    omple = max(AMPLADA / info["amplada"], ALCADA / info["alcada"]) * 100  # que el vídeo ompli el 9:16
    comptador = iter(range(1, 10_000))

    def moviment(escala: float, centre=(0.0, 0.0), rotacio: float = 0.0) -> str:
        return ("<filter><effect><name>Basic Motion</name><effectid>basic</effectid>"
                "<effectcategory>motion</effectcategory><effecttype>motion</effecttype><mediatype>video</mediatype>"
                f"<parameter><parameterid>scale</parameterid><name>Scale</name><valuemin>0</valuemin>"
                f"<valuemax>1000</valuemax><value>{escala:.2f}</value></parameter>"
                f"<parameter><parameterid>rotation</parameterid><name>Rotation</name><valuemin>-8640</valuemin>"
                f"<valuemax>8640</valuemax><value>{rotacio:g}</value></parameter>"
                f"<parameter><parameterid>center</parameterid><name>Center</name>"
                f"<value><horiz>{centre[0]:.4f}</horiz><vert>{centre[1]:.4f}</vert></value></parameter>"
                "</effect></filter>")

    def fitxer(fid: str, path: Path, durada: int, w: int, h: int, so: bool, primer: bool,
               rate_font: str = rate) -> str:
        if not primer:
            return f'<file id="{fid}"/>'
        audio = ("<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate>"
                 "</samplecharacteristics><channelcount>2</channelcount></audio>") if so else ""
        return (f'<file id="{fid}"><name>{escape(Path(path).name)}</name>'
                f'<pathurl>{escape("file://localhost" + quote(str(Path(path).resolve())))}</pathurl>{rate_font}'
                f"<duration>{durada}</duration><media><video><samplecharacteristics><width>{w}</width>"
                f"<height>{h}</height></samplecharacteristics></video>{audio}</media></file>")

    def clip(nom_clip: str, inici: int, final: int, entrada: int, sortida: int, fitxer_xml: str,
             filtre: str = "", durada_font: int | None = None, tipus: str = "video", rate_font: str = rate) -> str:
        cid = f"clipitem-{next(comptador)}"
        pista = ("<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>"
                 if tipus == "audio" else "")
        return (f'<clipitem id="{cid}"><name>{escape(nom_clip)}</name><enabled>TRUE</enabled>'
                f"<duration>{durada_font if durada_font is not None else sortida - entrada}</duration>{rate_font}"
                f"<start>{inici}</start><end>{final}</end><in>{entrada}</in><out>{sortida}</out>"
                f"{fitxer_xml}{pista}{filtre}</clipitem>")

    v1, a1 = [], []
    for i, x in enumerate(trossos):
        ini, fi = x["offset"], x["offset"] + x["b"] - x["a"]
        escala = omple * (exporta.ZOOM if x["zoom"] else 1)
        f_xml = fitxer("file-1", video, total_font, info["amplada"], info["alcada"], True, i == 0)
        v1.append(clip(video.stem, ini, fi, x["a"], x["b"], f_xml, moviment(escala), total_font))
        a1.append(clip(video.stem, ini, fi, x["a"], x["b"], '<file id="file-1"/>', "", total_font, "audio"))

    v2 = [[] for _ in range(pla.get("carrils", 1))]  # una pista per carril (les targetes que coincideixen)
    for k, br in enumerate(pla["brolls"]):
        ini, d = t.fotogrames(br["inici"]), t.fotogrames(br["durada"])
        d30 = t30.fotogrames(br["durada"])
        f_xml = fitxer(f"file-b{k}", br["fitxer"], d30, AMPLADA, ALCADA, False, True, rate30)
        lloc = _lloc_broll(br)
        filtre = moviment(100)
        if lloc:  # en targeta: més petit, al seu lloc i retallat
            rh, rv = lloc["retall"]
            filtre = moviment(lloc["escala"] * 100, lloc["centre"], lloc["rotacio"]) + (
                "<filter><effect><name>Crop</name><effectid>crop</effectid><effectcategory>motion</effectcategory>"
                "<effecttype>motion</effecttype><mediatype>video</mediatype>" + "".join(
                    f"<parameter><parameterid>{costat}</parameterid><name>{costat}</name><valuemin>0</valuemin>"
                    f"<valuemax>100</valuemax><value>{valor * 100:.3f}</value></parameter>"
                    for costat, valor in (("left", rh), ("right", rh), ("top", rv), ("bottom", rv)))
                + "</effect></filter>")
        v2[br.get("carril", 0)].append(clip(Path(br["fitxer"]).stem, ini, ini + d, 0, d30, f_xml, filtre,
                                            rate_font=rate30))
    v3 = []
    for k, st in enumerate(pla["stickers"]):
        ini, d = t.fotogrames(st["inici"]), t.fotogrames(st["durada"])
        w, h = st["px"]
        f_xml = fitxer(f"file-s{k}", st["fitxer"], d, w, h, False, True)
        escala = st["mida"] * AMPLADA / w * 100  # Premiere posa les imatges a la seva mida real
        v3.append(clip(Path(st["fitxer"]).stem, ini, ini + d, 0, d, f_xml,
                       moviment(escala, (st["x"] - 0.5, st["y"] - 0.5), st["rot"])))
    v4 = []
    if capa is not None:
        d30 = t30.fotogrames(float(pla["total"] / t.fr))
        f_xml = fitxer("file-capa", capa, d30, AMPLADA, ALCADA, False, True, rate30)
        v4.append(clip("subtitols", 0, pla["total"], 0, d30, f_xml, moviment(100), rate_font=rate30))

    pistes = "".join(f"<track>{''.join(p)}</track>" for p in (v1, *v2, v3, v4) if p)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">'
            f'<sequence id="sequence-1"><name>{escape(nom)}</name><duration>{pla["total"]}</duration>{rate}'
            f"<media><video><format><samplecharacteristics>{rate}<width>{AMPLADA}</width><height>{ALCADA}</height>"
            "<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>"
            f"</samplecharacteristics></format>{pistes}</video>"
            "<audio><numOutputChannels>2</numOutputChannels><format><samplecharacteristics><depth>16</depth>"
            "<samplerate>48000</samplerate></samplecharacteristics></format>"
            f"<track>{''.join(a1)}</track></audio></media>"
            f"<timecode>{rate}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>"
            "</sequence></xmeml>\n")


LLEGEIX_ME = """Projecte de «{nom}» per acabar-lo en un altre editor
====================================================

Aquesta carpeta té el muntatge de tallat: els talls, els zooms, el b-roll i els stickers,
cadascun a la seva pista. El b-roll i els stickers són a «recursos». Els talls fan servir el
vídeo original:

    {video}

No el moguis ni li canviïs el nom. Si l'has de moure, l'editor et demanarà on és
(«tornar a enllaçar» o «relink»).

Premiere Pro
  1. Fitxer → Importa… → tria «{nom}.xml».
  2. Al panell Projecte surt la seqüència «{nom}». Fes-hi DOBLE CLIC per obrir-la: cada tall és un
     clip a part, i el pots allargar o escurçar (el vídeo original hi és sencer).
     No l'arrosseguis a una seqüència nova: el Premiere la convertiria en un sol clip.
  3. Subtítols: Fitxer → Importa… → «{nom}.srt», i arrossega'l a la seqüència.

Final Cut Pro
  1. Fitxer → Importa → XML… → tria «{nom}.fcpxml».
  2. Subtítols: Fitxer → Importa → Subtítols… → «{nom}.srt».

DaVinci Resolve
  1. File → Import → Timeline… → tria «{nom}.fcpxml».
  2. Subtítols: importa «{nom}.srt» a la Media Pool i arrossega'l a la línia de temps.

CapCut
  CapCut no deixa importar projectes d'altres editors. A la pàgina de revisió de tallat, fes
  Final… → «Trossos per a CapCut o iMovie»: tindràs cada tros com un clip a part, en ordre.
{capa}
Els subtítols animats de tallat (estil, colors, animacions) no passen a cap editor amb el
.srt: només el text i els temps. El títol del ganxo i els gràfics del pla només hi van amb
la capa animada (a la pàgina, «Inclou-hi els subtítols i els gràfics de tallat»).
"""

AMB_CAPA = """
Subtítols i gràfics animats («subtitols.mov»)
  Són els subtítols, el títol del ganxo i els gràfics de tallat tal com surten al vídeo
  final, amb el fons transparent. Ja són a la pista de dalt de tot del projecte. Si no els
  vols, esborra aquesta pista; si fas servir el .srt, no posis tots dos alhora.
"""


EFECTES = """
Efectes de so: «efectes-de-so.wav» dura tot el muntatge, amb cada efecte al seu moment. Posa'l en
una pista d'àudio, a l'inici (0:00). La neteja de la veu no hi va: aquí sona la veu original (el
vídeo que exporta tallat sí que la porta neta).
"""


def _efectes(projecte, trams, desti: Path) -> None:
    """Copia la pista d'efectes de so (si n'hi ha) i ho explica al LLEGEIX-ME."""
    pista = projecte.pista_efectes(trams)
    if pista is None:
        return
    shutil.copy(pista, desti / "efectes-de-so.wav")
    llegeix = desti / "LLEGEIX-ME.txt"
    llegeix.write_text(llegeix.read_text(encoding="utf-8") + EFECTES, encoding="utf-8")


def exporta_editors(projecte, amb_capa: bool = False, avis=None) -> Path:
    """Escriu la carpeta per a altres editors i en torna el camí."""
    trams = projecte.trams()
    if not trams:
        raise ValueError("No queda cap paraula: no hi ha res per exportar.")
    nom = projecte.video.stem
    desti = projecte.sortida("editors").with_suffix("")
    desti.mkdir(parents=True, exist_ok=True)
    pla = _plan(projecte, trams)
    _copia_recursos(pla, desti)
    linies = projecte.linies_subtitols(trams)
    (desti / f"{nom}.srt").write_text(srt(linies), encoding="utf-8")
    capa = None
    titol = projecte.titol(trams)
    situats = projecte.grafics(trams, linies, sense_bloc=True)  # aquí no hi ha el bloc de color
    if amb_capa and (linies or titol or situats):  # subtítols, títol del ganxo i gràfics (els stickers van a part)
        estil = projecte.estil()
        mov = subtitols.renderitza(linies, estil["subtitols"], sum(b - a for a, b in trams),
                                   projecte.carpeta, "1080", avis, fonts=projecte.fonts_subtitols(),
                                   titol=titol, estil_titol=estil.get("titol"),
                                   grafics=situats, paleta=grafics.paleta(estil), imatges=projecte.carpeta_imatges)
        capa = desti / "subtitols.mov"
        shutil.copy(mov, capa)
    (desti / f"{nom}.fcpxml").write_text(fcpxml(nom, projecte.video, pla, capa), encoding="utf-8")
    (desti / f"{nom}.xml").write_text(xmeml(nom, projecte.video, pla, capa), encoding="utf-8")
    (desti / "LLEGEIX-ME.txt").write_text(
        LLEGEIX_ME.format(nom=nom, video=projecte.video, capa=AMB_CAPA if capa else ""), encoding="utf-8")
    _efectes(projecte, trams, desti)
    return desti


# --- CapCut o iMovie: els trossos per separat --------------------------------------------------

def _moment(segons: float) -> str:
    """«1m18,1s»: es pot fer servir en un nom de fitxer (sense «:»)."""
    m, s = divmod(segons, 60)
    return f"{int(m)}m{s:04.1f}s".replace(".", ",")


def _on(st: dict) -> str:
    vertical = "a dalt" if st["y"] < 0.4 else ("a baix" if st["y"] > 0.6 else "al mig")
    costat = "a la dreta" if st["x"] > 0.5 else "a l'esquerra"
    return f"{vertical} {costat}"


LLEGEIX_ME_TROSSOS = """El muntatge de «{nom}» en trossos (per a CapCut o iMovie)
=========================================================

CapCut no importa projectes d'altres editors. Per això aquí tens el muntatge en trossos,
numerats en l'ordre en què sonen ({n} trossos, {durada} en total). Els zooms ja hi són aplicats.

CapCut
  1. Obre CapCut i crea un projecte nou.
  2. Importa (⌘I) i tria tots els trossos numerats: 01.mp4, 02.mp4…
  3. Selecciona'ls tots al panell de mitjans i arrossega'ls alhora a la línia de temps: queden
     un darrere l'altre. Si l'ordre no és bo, ordena el panell per nom i torna-hi.
  4. Per escurçar un tall, arrossega la vora del tros. Per allargar-lo (recuperar paraules),
     fes-ho a tallat i torna a exportar els trossos: aquí no hi ha imatge de més.
  5. Subtítols: Text → Subtítols locals → Importa «{nom}.srt» (o fes servir els subtítols
     automàtics de CapCut).
{recursos}
iMovie
  Importa els trossos (Fitxer → Importa contingut), selecciona'ls tots i arrossega'ls a la línia
  de temps. iMovie fa vídeos horitzontals: per a un reel vertical, millor CapCut.
"""


def _llista_recursos(brolls: list[dict], stickers: list[dict]) -> str:
    linies = []
    if brolls:
        linies.append("\nB-roll (carpeta «broll»): arrossega cada fitxer a la pista de sobre del vídeo, al moment")
        linies.append("que diu el nom. Tapa la imatge i el so continua.")
        if any(_lloc_broll(b) for b in brolls):
            linies.append("Al teu kit, el b-roll va en targeta: posa'l més petit i al seu lloc (al projecte de")
            linies.append("Premiere i Final Cut ja hi és; les cantonades arrodonides i la vora, no).")
        linies += [f"  B{i} al {_moment(b['inici'])}, durant {b['durada']:.1f} s".replace(".", ",")
                   for i, b in enumerate(brolls, 1)]
    if stickers:
        linies.append("\nStickers (carpeta «stickers»): igual que el b-roll, i fes-los més petits.")
        linies += [f"  S{i} al {_moment(s['inici'])}, durant {s['durada']:.1f} s, {_on(s)}".replace(".", ",", 1)
                   for i, s in enumerate(stickers, 1)]
    return "\n".join(linies) + ("\n" if linies else "")


def exporta_trossos(projecte, progres=None) -> Path:
    """Escriu cada tros del muntatge com un clip numerat, amb el b-roll, els stickers i el .srt."""
    trams = projecte.trams()
    if not trams:
        raise ValueError("No queda cap paraula: no hi ha res per exportar.")
    nom = projecte.video.stem
    desti = projecte.sortida("trossos").with_suffix("")
    desti.mkdir(parents=True, exist_ok=True)
    zooms = projecte.zooms_per_tram(trams)
    xifres = max(2, len(str(len(trams))))
    for i, tram in enumerate(trams, 1):
        exporta.exporta(projecte.video, [tram], desti / f"{i:0{xifres}d}.mp4", "1080",
                        zooms=[bool(zooms[i - 1])] if i - 1 < len(zooms) else None)
        if progres:
            progres(round(i / len(trams) * 100))
    pla = _plan(projecte, trams)
    for carpeta, llista, lletra in (("broll", pla["brolls"], "B"), ("stickers", pla["stickers"], "S")):
        for i, r in enumerate(llista, 1):
            (desti / carpeta).mkdir(exist_ok=True)
            origen = Path(r["fitxer"])
            final = ".png" if lletra == "S" else origen.suffix.lower()
            nou = desti / carpeta / f"{lletra}{i} al {_moment(r['inici'])}{final}"
            if lletra == "B":
                _copia_clip(r, nou)
            elif final == origen.suffix.lower():
                shutil.copy(origen, nou)
            else:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(origen), "-frames:v", "1", str(nou)],
                               check=True, capture_output=True)
    (desti / f"{nom}.srt").write_text(srt(projecte.linies_subtitols(trams)), encoding="utf-8")
    durada = sum(b - a for a, b in trams)
    (desti / "LLEGEIX-ME.txt").write_text(LLEGEIX_ME_TROSSOS.format(
        nom=nom, n=len(trams), durada=_moment(durada),
        recursos=_llista_recursos(pla["brolls"], pla["stickers"])), encoding="utf-8")
    _efectes(projecte, trams, desti)
    return desti
