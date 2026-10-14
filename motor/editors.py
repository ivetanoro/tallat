"""Exportar el muntatge per acabar-lo en un altre editor.

Escriu una carpeta a exports/ amb:
  NOM.fcpxml      Final Cut Pro (10.6 o més nou) i DaVinci Resolve (18 o més nou)
  NOM.xml         Premiere Pro (format XML de Final Cut 7, que Premiere importa)
  NOM.srt         els subtítols, en temps del muntatge
  subtitols.mov   (opcional) els subtítols animats de tallat, amb el fons transparent
  LLEGEIX-ME.txt  com obrir-ho a cada editor, i a CapCut (que no importa projectes)

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

from motor import exporta, marca, subtitols

AMPLADA, ALCADA = 1080, 1920


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
    est_st = marca.carrega().get("stickers", {})
    stickers = []
    for k, st in enumerate(projecte.stickers(trams)):
        x = est_st.get("x", 0.72) if k % 2 == 0 else 1 - est_st.get("x", 0.72)
        rot = est_st.get("rotacio", 8) * (1 if k % 2 == 0 else -1)
        stickers.append(dict(st, x=x, y=est_st.get("y", 0.3), rot=rot, mida=est_st.get("mida", 0.34),
                             px=_mida_imatge(st["fitxer"])))
    return {"t": t, "info": info, "trossos": trossos, "total": offset,
            "brolls": projecte.brolls(trams), "stickers": stickers}


def _copia_recursos(pla: dict, desti: Path) -> None:
    """Copia el b-roll i els stickers a desti/recursos (els stickers, en PNG) i hi apunta el pla."""
    carpeta = desti / "recursos"
    carpeta.mkdir(exist_ok=True)
    for br in pla["brolls"]:
        nou = carpeta / Path(br["fitxer"]).name
        shutil.copy(br["fitxer"], nou)
        br["fitxer"] = nou
    for st in pla["stickers"]:
        nou = carpeta / (Path(st["fitxer"]).stem + ".png")
        if Path(st["fitxer"]).suffix.lower() == ".png":
            shutil.copy(st["fitxer"], nou)
        else:  # WebP, GIF, SVG…: no tots els editors els obren
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(st["fitxer"]), "-frames:v", "1", str(nou)],
                           check=True, capture_output=True)
        st["fitxer"] = nou
        st["px"] = _mida_imatge(nou)


def _tros_de(trossos: list[dict], f: int) -> dict:
    """El tros del muntatge on cau el fotograma f."""
    return next((x for x in trossos if x["offset"] <= f < x["offset"] + x["b"] - x["a"]), trossos[-1])


# --- Final Cut Pro i DaVinci Resolve (FCPXML 1.10) -------------------------------------------

def fcpxml(nom: str, video: Path, pla: dict, capa: Path | None = None) -> str:
    t, info, trossos = pla["t"], pla["info"], pla["trossos"]
    recursos = [
        f'<format id="r1" frameDuration="{t.durada_fotograma}" width="{AMPLADA}" height="{ALCADA}"/>',
        f'<format id="r2" frameDuration="{t.durada_fotograma}" width="{info["amplada"]}" height="{info["alcada"]}"/>',
        f'<asset id="r3" name="{escape(video.stem)}" start="0s" duration="{t.fcp(t.fotogrames(info["durada"]))}" '
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
        rid, nom_br = f"r{n}", escape(Path(br["fitxer"]).stem)
        n += 1
        durada = t.fotogrames(br["durada"])
        recursos.append(f'<asset id="{rid}" name="{nom_br}" start="0s" duration="{t.fcp(durada)}" hasVideo="1" '
                        f'format="r4"><media-rep kind="original-media" src="{_url(br["fitxer"])}"/></asset>')
        connecta(t.fotogrames(br["inici"]), lambda off, rid=rid, nom_br=nom_br, durada=durada:
                 f'<asset-clip ref="{rid}" lane="1" offset="{t.fcp(off)}" name="{nom_br}" start="0s" '
                 f'duration="{t.fcp(durada)}"/>')
    for st in pla["stickers"]:
        rid, nom_st = f"r{n}", escape(Path(st["fitxer"]).stem)
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
                 f'<video ref="{rid}" lane="2" offset="{t.fcp(off)}" name="{nom_st}" start="0s" duration="{t.fcp(durada)}">'
                 f'<adjust-transform position="{pos_x:.2f} {pos_y:.2f}" scale="{escala:.4f} {escala:.4f}" '
                 f'rotation="{-rot:g}"/></video>')
    if capa is not None:
        recursos.append(f'<asset id="r{n}" name="subtitols" start="0s" duration="{t.fcp(pla["total"])}" hasVideo="1" '
                        f'format="r1"><media-rep kind="original-media" src="{_url(capa)}"/></asset>')
        connectats[0].append(f'<asset-clip ref="r{n}" lane="3" offset="{t.fcp(trossos[0]["a"])}" name="subtitols" '
                             f'start="0s" duration="{t.fcp(pla["total"])}"/>')

    espina = []
    for i, x in enumerate(trossos):
        ajustos = '<adjust-conform type="fill"/>'
        if x["zoom"]:
            ajustos += f'<adjust-transform scale="{exporta.ZOOM} {exporta.ZOOM}"/>'
        espina.append(f'<asset-clip ref="r3" offset="{t.fcp(x["offset"])}" name="{escape(video.stem)}" '
                      f'start="{t.fcp(x["a"])}" duration="{t.fcp(x["b"] - x["a"])}" format="r2" tcFormat="NDF">'
                      f'{ajustos}{"".join(connectats[i])}</asset-clip>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.10">\n'
            f'  <resources>\n    {chr(10).join("    " + r if j else r for j, r in enumerate(recursos))}\n  </resources>\n'
            f'  <library>\n    <event name="tallat">\n      <project name="{escape(nom)}">\n'
            f'        <sequence format="r1" duration="{t.fcp(pla["total"])}" tcStart="0s" tcFormat="NDF" '
            f'audioLayout="stereo" audioRate="48k">\n          <spine>\n'
            + "\n".join("            " + e for e in espina) +
            '\n          </spine>\n        </sequence>\n      </project>\n    </event>\n  </library>\n</fcpxml>\n')


def _url(path: Path) -> str:
    return "file://" + quote(str(Path(path).resolve()))


# --- Premiere Pro (XML de Final Cut 7) ---------------------------------------------------------

def xmeml(nom: str, video: Path, pla: dict, capa: Path | None = None) -> str:
    t, info, trossos = pla["t"], pla["info"], pla["trossos"]
    base, ntsc = t.timebase
    rate = f"<rate><timebase>{base}</timebase><ntsc>{'TRUE' if ntsc else 'FALSE'}</ntsc></rate>"
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

    def fitxer(fid: str, path: Path, durada: int, w: int, h: int, so: bool, primer: bool) -> str:
        if not primer:
            return f'<file id="{fid}"/>'
        audio = ("<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate>"
                 "</samplecharacteristics><channelcount>2</channelcount></audio>") if so else ""
        return (f'<file id="{fid}"><name>{escape(Path(path).name)}</name>'
                f'<pathurl>{escape("file://localhost" + quote(str(Path(path).resolve())))}</pathurl>{rate}'
                f"<duration>{durada}</duration><media><video><samplecharacteristics><width>{w}</width>"
                f"<height>{h}</height></samplecharacteristics></video>{audio}</media></file>")

    def clip(nom_clip: str, inici: int, final: int, entrada: int, sortida: int, fitxer_xml: str,
             filtre: str = "", durada_font: int | None = None, tipus: str = "video") -> str:
        cid = f"clipitem-{next(comptador)}"
        pista = ("<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>"
                 if tipus == "audio" else "")
        return (f'<clipitem id="{cid}"><name>{escape(nom_clip)}</name><enabled>TRUE</enabled>'
                f"<duration>{durada_font if durada_font is not None else sortida - entrada}</duration>{rate}"
                f"<start>{inici}</start><end>{final}</end><in>{entrada}</in><out>{sortida}</out>"
                f"{fitxer_xml}{pista}{filtre}</clipitem>")

    v1, a1 = [], []
    for i, x in enumerate(trossos):
        ini, fi = x["offset"], x["offset"] + x["b"] - x["a"]
        escala = omple * (exporta.ZOOM if x["zoom"] else 1)
        f_xml = fitxer("file-1", video, total_font, info["amplada"], info["alcada"], True, i == 0)
        v1.append(clip(video.stem, ini, fi, x["a"], x["b"], f_xml, moviment(escala), total_font))
        a1.append(clip(video.stem, ini, fi, x["a"], x["b"], '<file id="file-1"/>', "", total_font, "audio"))

    v2 = []
    for k, br in enumerate(pla["brolls"]):
        ini, d = t.fotogrames(br["inici"]), t.fotogrames(br["durada"])
        f_xml = fitxer(f"file-b{k}", br["fitxer"], d, AMPLADA, ALCADA, False, True)
        v2.append(clip(Path(br["fitxer"]).stem, ini, ini + d, 0, d, f_xml, moviment(100)))
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
        f_xml = fitxer("file-capa", capa, pla["total"], AMPLADA, ALCADA, False, True)
        v4.append(clip("subtitols", 0, pla["total"], 0, pla["total"], f_xml, moviment(100)))

    pistes = "".join(f"<track>{''.join(p)}</track>" for p in (v1, v2, v3, v4) if p)
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
  1. Fitxer → Importa… → tria «{nom}.xml». Surt una seqüència vertical amb el muntatge.
  2. Subtítols: Fitxer → Importa… → «{nom}.srt», i arrossega'l a la seqüència.

Final Cut Pro
  1. Fitxer → Importa → XML… → tria «{nom}.fcpxml».
  2. Subtítols: Fitxer → Importa → Subtítols… → «{nom}.srt».

DaVinci Resolve
  1. File → Import → Timeline… → tria «{nom}.fcpxml».
  2. Subtítols: importa «{nom}.srt» a la Media Pool i arrossega'l a la línia de temps.

CapCut
  CapCut no deixa importar projectes d'altres editors. Fes-ho així:
  1. A la pàgina de revisió de tallat, desactiva «Posa subtítols al vídeo» i exporta la
     versió final (Final… → 1080 o 4K).
  2. A CapCut, importa aquell vídeo i, per als subtítols: Text → Subtítols → Importa
     («{nom}.srt»). Si no t'hi surt aquesta opció, fes servir els subtítols automàtics de CapCut.
{capa}
Els subtítols animats de tallat (estil, colors, animacions) no passen a cap editor amb el
.srt: només el text i els temps.
"""

AMB_CAPA = """
Subtítols animats («subtitols.mov»)
  Són els subtítols de tallat tal com surten al vídeo final, amb el fons transparent. Ja
  són a la pista de dalt de tot del projecte. Si no els vols, esborra aquesta pista; si
  fas servir el .srt, no posis tots dos alhora.
"""


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
    if amb_capa and linies:
        mov = subtitols.renderitza(linies, projecte.estil_subtitols(), sum(b - a for a, b in trams),
                                   projecte.carpeta, "1080", avis)  # només els subtítols: els stickers van a part
        capa = desti / "subtitols.mov"
        shutil.copy(mov, capa)
    (desti / f"{nom}.fcpxml").write_text(fcpxml(nom, projecte.video, pla, capa), encoding="utf-8")
    (desti / f"{nom}.xml").write_text(xmeml(nom, projecte.video, pla, capa), encoding="utf-8")
    (desti / "LLEGEIX-ME.txt").write_text(
        LLEGEIX_ME.format(nom=nom, video=projecte.video, capa=AMB_CAPA if capa else ""), encoding="utf-8")
    return desti
