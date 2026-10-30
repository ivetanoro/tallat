"""Servidor local de la pàgina de revisió. Només escolta a 127.0.0.1: res no surt de l'ordinador."""
from __future__ import annotations

import base64
import binascii
import bisect
import errno
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from motor import broll, edicio, editors, entorn, exporta, grafics, marca, muntatge, notes, so, stickers, targetes
from motor.projecte import EXPORTS, PREVIES, Projecte

PAGINA = Path(__file__).resolve().parent.parent / "pagina"
MIDA_MAXIMA_FONT = 20 * 1024 * 1024  # una font no passa mai d'uns quants MB
MIDA_MAXIMA_JSON = 10 * 1024 * 1024  # l'estat d'un projecte llarg no arriba ni a 1 MB
MIDA_MAXIMA_PUJADA = 2 * 1024 ** 3   # un b-roll o un sticker
MIDA_MAXIMA_IMATGE = 60 * 1024 ** 2  # una captura o una foto d'un gràfic
# Les peticions que canvien el projecte obert: han de dir a quin projecte van (dues pestanyes).
RUTES_DEL_PROJECTE = {"/api/estat", "/api/instruccio", "/api/broll/biblioteca",
                      "/api/broll/treu", "/api/broll/esborra", "/api/broll/puja", "/api/mostra", "/api/exporta", "/api/editors",
                      "/api/marca", "/api/marca/restableix", "/api/marca/font", "/api/marca/lletra",
                      "/api/kit/tria", "/api/kit/nou",
                      "/api/kit/nom", "/api/kit/per-defecte", "/api/kit/esborra", "/api/kit/importa",
                      "/api/so/mostres", "/api/grafics/imatge", "/api/previa", "/api/notes", "/api/estil/a-tots"}
mimetypes.add_type("audio/mp4", ".m4a")  # Python diu «audio/mp4a-latm», que els navegadors no reprodueixen
mimetypes.add_type("audio/wav", ".wav")
RUTES_DE_FITXER = {"/api/broll/puja", "/api/marca/font", "/api/kit/importa", "/api/grafics/imatge"}  # el cos és el fitxer mateix


def clau_de(projecte: Projecte) -> str:
    """Un nom curt i estable per a cada projecte (la pàgina el diu a cada petició)."""
    return hashlib.sha1(str(projecte.carpeta).encode()).hexdigest()[:16]


class Feina:
    """Un sol render alhora, en segon pla, amb el seu progrés."""

    def __init__(self):
        self.bloqueig = threading.Lock()
        self.estat = None

    def info(self) -> dict | None:
        with self.bloqueig:
            return dict(self.estat) if self.estat else None

    def comença(self, projecte: Projecte, qualitat: str, capa: bool = False, trossos: bool = False) -> bool:
        """`qualitat`: esborrany, 1080, 4k, o «editors» (projecte per a Premiere, Final Cut…)."""
        with self.bloqueig:
            if self.estat and self.estat["estat"] == "treballant":
                return False
            self.estat = {"estat": "treballant", "qualitat": qualitat, "fase": "video", "progres": 0,
                          "fitxer": None, "copia": None, "avis": None, "error": None}
        threading.Thread(target=self._fes, args=(projecte, qualitat, capa, trossos), daemon=True).start()
        return True

    def _actualitza(self, **canvis):
        with self.bloqueig:
            self.estat.update(canvis)

    def _fes(self, projecte: Projecte, qualitat: str, capa: bool = False, trossos: bool = False) -> None:
        try:
            if qualitat == "editors":
                if trossos:  # CapCut o iMovie: cada tros com un clip a part
                    self._actualitza(fase="video", progres=0)
                    carpeta = editors.exporta_trossos(projecte, progres=lambda pct: self._actualitza(progres=pct))
                else:
                    self._actualitza(fase="subtitols" if capa else "editors")
                    carpeta = editors.exporta_editors(projecte, amb_capa=capa,
                                                      progres=lambda pct: self._actualitza(fase="fons", progres=pct))
                copia, avis = _copia(carpeta)
                self._actualitza(estat="fet", progres=100, fitxer=carpeta.name, copia=copia, avis=avis)
                return
            sortida = projecte.sortida(qualitat)
            trams = projecte.trams()
            self._actualitza(fase="subtitols")
            capa = projecte.capa_subtitols(trams, qualitat)
            self._actualitza(fase="video", progres=0)
            exporta.exporta(projecte.font(qualitat), trams, sortida, qualitat,
                            progres=lambda pct: self._actualitza(progres=pct), capa=capa,
                            zooms=projecte.zooms_per_tram(trams), brolls=projecte.brolls(trams),
                            blocs=projecte.blocs(trams), encaix=projecte.encaix, **projecte.opcions_so(trams))
            projecte.desa_talls(sortida, trams)
            copia, avis = _copia(sortida)  # també l'esborrany: la carpeta que es tria és per a tot
            durades = exporta.comprova_durades(sortida, sum(b - a for a, b in trams), projecte.dades["fps"])
            avis = " ".join(x for x in (durades, avis) if x) or None
            self._actualitza(estat="fet", progres=100, fitxer=sortida.name, copia=copia, avis=avis)
        except Exception as e:  # el missatge arriba a la pàgina
            traceback.print_exc()
            self._actualitza(estat="error", error=str(e))


REPROVA_PREVIA = 30  # segons: si fer el continu ha fallat, fins aleshores no es torna a provar (amb els mateixos talls)


class Previa:
    """El muntatge en un vídeo continu per a la pàgina (exporta.fes_previa), un alhora i en segon pla.
    La pàgina el demana després de cada canvi i, mentrestant, espera per fer sonar el vídeo. Si no es pot fer,
    diu «error» (i la pàgina fa sonar la còpia que salta): abans es tornava a provar a cada pregunta, sense
    dir-ho mai, i la pàgina esperava per sempre (revisió de Codex)."""

    def __init__(self):
        self.bloqueig = threading.Lock()
        self.fent = None  # el fitxer que s'està fent
        self.fallades = {}  # fitxer → (quan, error) dels que no s'han pogut fer

    def demana(self, projecte: Projecte, trams) -> dict:
        if not trams or not projecte.proxy.exists():
            return {"estat": "no", "trams": edicio.trams_json(trams)}
        desti = projecte.previa(trams)
        if desti.exists():
            try:
                os.utime(desti)  # la darrera que s'ha demanat: la neteja no se l'emporta
            except OSError:
                pass
            return {"estat": "fet", "url": f"/previa/{desti.name}", "trams": edicio.trams_json(trams)}
        with self.bloqueig:
            fallada = self.fallades.get(desti)
            if fallada and time.time() - fallada[0] < REPROVA_PREVIA and self.fent != desti:
                return {"estat": "error", "error": fallada[1], "trams": edicio.trams_json(trams)}
            if self.fent is None:  # si se'n fa una altra, la pàgina ho tornarà a demanar
                self.fent = desti
                threading.Thread(target=self._fes, args=(projecte.proxy, list(trams), desti),
                                 daemon=True).start()
        return {"estat": "fent", "trams": edicio.trams_json(trams)}

    def _fes(self, proxy: Path, trams, desti: Path) -> None:
        try:
            exporta.fes_previa(proxy, trams, desti)
            # Se'n guarden les quatre que s'han fet servir darrerament (desfer i refer hi tornen); la que
            # sona a la pàgina sempre n'és una, perquè cada petició la toca (os.utime). Els vídeos curts de
            # l'antic «Escolta cada tall» (fins a la 0.7) ja no els fa servir res.
            vells = sorted(desti.parent.glob("previa_*.mp4"), key=lambda p: p.stat().st_mtime)[:-4]
            for vell in [*vells, *desti.parent.glob("escolta_*.mp4")]:
                entorn.esborra_si_pots(vell)
            with self.bloqueig:
                self.fallades.pop(desti, None)
        except Exception as e:
            traceback.print_exc()
            with self.bloqueig:
                self.fallades[desti] = (time.time(), str(e)[:300])
        finally:
            with self.bloqueig:
                self.fent = None


def _copia(fitxer: Path) -> tuple[str | None, str | None]:
    """La còpia a la carpeta de la persona: (nom, None) o, si no es pot (un disc que ja no hi és, sense
    permís…), (None, avís). L'export ja és a la carpeta del projecte: no es dona per fallat."""
    try:
        copia = exporta.copia_a_carpeta(fitxer)
        return (copia.name if copia else None), None
    except OSError as e:
        return None, f"El vídeo és a la carpeta del projecte, però no l'he pogut copiar a la teva carpeta ({e.strerror or e})."


def _arrel_de(projecte: Projecte) -> Projecte:
    """Si el projecte és un reel (reels/<id>/ dins d'una gravació), la gravació sencera."""
    if (projecte.carpeta / muntatge.REEL).exists() and projecte.carpeta.parent.name == muntatge.CARPETA_REELS:
        return Projecte(projecte.carpeta.parent.parent)
    return projecte


def crea_servidor(inicial: Projecte, port: int) -> ThreadingHTTPServer:
    feina = Feina()
    previa = Previa()
    bloqueig = threading.Lock()
    # Seguretat: el servidor només escolta aquest Mac, però una web oberta al navegador podria
    # intentar enviar-li peticions. Per això: només s'accepten els noms 127.0.0.1 i localhost
    # (contra el «DNS rebinding»), i les peticions que canvien coses han de portar un codi que
    # només coneix la pàgina de tallat (es crea cada cop que s'engega el servidor).
    token = secrets.token_urlsafe(24)
    amfitrions = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origens = {f"http://{a}" for a in amfitrions}
    # La pàgina pot passar de la gravació sencera a qualsevol dels reels proposats.
    obert = {"p": inicial, "arrel": _arrel_de(inicial)}
    # Les còpies lleugeres de cada enquadrament d'un vídeo horitzontal (encaix) es fan en segon pla, la primera
    # vegada que cal cadascuna (una per fitxer, encara que se'n demanin unes quantes alhora). La pàgina canvia de
    # vídeo quan la seva és a punt (/api/novetats, «copia»).
    copia = {"fent": set(), "error": None}

    def fes_copia(projecte: Projecte) -> None:
        """Es crida amb `bloqueig` agafat (des de les peticions que desen l'estat o obren un projecte)."""
        encaix, desti = projecte.encaix, projecte.proxy_de()
        if desti in copia["fent"] or not projecte.video.exists() or projecte.proxy_al_dia(encaix):
            return
        copia["fent"].add(desti)
        copia["error"] = None

        def fes():
            try:
                projecte.prepara_proxy(encaix=encaix)
            except Exception as e:
                copia["error"] = f"No he pogut preparar el vídeo: {e}"
            finally:
                with bloqueig:
                    copia["fent"].discard(desti)
        threading.Thread(target=fes, daemon=True).start()

    def versio_copia(projecte: Projecte) -> str:
        """Quina còpia serveix /proxy.mp4 ara (la pàgina hi posa ?v=… i, si canvia, la torna a carregar)."""
        proxy = projecte.proxy
        return f"{proxy.name}:{proxy.stat().st_mtime_ns}" if proxy.exists() else ""

    def info_reels() -> dict:
        arrel = obert["arrel"]
        reels, errors = muntatge.llegeix_reels(arrel.carpeta, arrel.dades["paraules"])
        actual = None
        if obert["p"] is not arrel:
            actual = obert["p"].carpeta.name
        return {"arrel": arrel.nom, "reel_actual": actual, "errors_reels": errors,
                "reels": [dict(r, durada=muntatge.durada_estimada(arrel, r)) for r in reels]}

    def darrer_export(p: Projecte) -> str | None:
        """El vídeo exportat més nou: si en surt un de nou (Claude n'ha fet un des del xat), la pàgina ho sap."""
        return next((x["nom"] for x in p.exports() if x["complet"]), None)

    def moment_de_versio(p: Projecte, versio: str, t) -> tuple[str, float, int, float]:
        """La versió (el nom d'un esborrany d'aquest projecte), el seu segon, la paraula que s'hi sentia i el segon
        exacte de la gravació (amb els talls d'aquella versió)."""
        fitxer = p.carpeta / EXPORTS / Path(versio).name
        talls = fitxer.with_suffix(".talls.json")
        if fitxer.suffix != ".mp4" or not fitxer.exists() or not talls.exists():
            raise ValueError("No trobo aquesta versió.")
        trams = [tuple(x) for x in json.loads(talls.read_text(encoding="utf-8"))]
        total = sum(b - a for a, b in trams)
        t_versio = max(0.0, float(t))
        if t_versio > total + 0.25:
            raise ValueError("Aquest moment no és a la versió.")
        # Al final de tot, el reproductor pot dir un pèl més del que dura: és l'últim fotograma (Codex).
        original = p.al_original(min(t_versio, max(0.0, total - 0.001)), trams)
        if original is None:
            raise ValueError("Aquest moment no és a la versió.")
        paraules = p.dades["paraules"]
        i = max(0, bisect.bisect_right([w["inici"] for w in paraules], original) - 1)
        # Al començament d'un tros, la paraula d'abans pot ser una de les tretes: llavors, la primera del tros (Codex).
        tram = next(((a, b) for a, b in trams if a - 0.001 <= original < b), None)
        if tram and paraules[i]["final"] < tram[0] and i + 1 < len(paraules) and paraules[i + 1]["inici"] < tram[1]:
            i += 1
        return fitxer.name, round(min(t_versio, total), 2), i, round(original, 3)

    def desa_miniatura(carpeta: Path, dades) -> str | None:
        """La miniatura que envia la pàgina (una imatge JPEG petita, en base64) → notes-miniatures/xxx.jpg."""
        if not isinstance(dades, str) or not dades.startswith("data:image/jpeg;base64,"):
            return None
        try:
            imatge = base64.b64decode(dades.split(",", 1)[1], validate=True)
        except (ValueError, binascii.Error):
            return None
        if not imatge.startswith(b"\xff\xd8") or len(imatge) > 600_000:
            return None
        desti = Path(carpeta) / notes.MINIATURES
        nom = f"{uuid.uuid4().hex[:12]}.jpg"
        try:
            desti.mkdir(exist_ok=True)
            (desti / nom).write_bytes(imatge)
        except OSError:  # sense miniatura, la nota es desa igualment
            notes.esborra_miniatura(carpeta, nom)
            return None
        return nom

    def info_notes() -> dict:
        """Les notes per a Claude (de la gravació sencera i dels seus reels: la pàgina ensenya les del que
        s'edita, `projecte`) i si Claude les espera ara."""
        carpeta = obert["arrel"].carpeta
        dades = notes.llegeix(carpeta)
        return {"notes": dades["notes"], "versio_notes": dades["versio"], "connectat": notes.connectat(carpeta),
                "projecte": str(obert["p"].carpeta)}

    def instantania() -> dict:
        projecte = obert["p"]
        trams = projecte.trams()
        brolls, enganxines = projecte.brolls(trams), projecte.stickers(trams)
        linies, titol = projecte.linies_subtitols(trams), projecte.titol(trams)
        tots = projecte.grafics(trams, linies, amb_alternatives=True)
        situats = [g for g in tots if not g.get("alternativa")]
        return {"estat": _estat_json(projecte.estat), "trams": edicio.trams_json(trams),
                "durada_final": round(sum(b - a for a, b in trams), 3),
                "zooms": projecte.zooms_per_tram(trams), "zoom": exporta.ZOOM,
                "instruccions": projecte.instruccions(),
                "brolls": [{**{k: v for k, v in b.items() if k != "fitxer"},
                            "url": "/broll/" + b["fitxer"].name + f"?v={int(b['fitxer'].stat().st_mtime)}"}
                           for b in brolls],
                "stickers": [{"id": st["id"], "inici": st["inici"], "durada": st["durada"],
                              **{k: st[k] for k in ("x", "y", "mida", "rotacio")},
                              "url": "/stickers/" + st["fitxer"].name + f"?v={int(st['fitxer'].stat().st_mtime)}"}
                             for st in enganxines],
                "subtitols": linies,
                "titol": titol, "grafics": situats, "grafics_dibuix": projecte.dibuixos_grafics(linies),
                "grafics_alternatives": [g for g in tots if g.get("alternativa")],
                "blocs": projecte.blocs(trams, situats),
                **info_efectes(projecte, trams, brolls, enganxines, titol, linies, situats),
                **mostres_del_video(projecte),
                "paragrafs": projecte.paragrafs()}

    def mostres_del_video(projecte) -> dict:
        """Les miniatures que depenen de l'estil d'aquest vídeo (el b-roll i les mostres dels gràfics)."""
        estil = projecte.estil()
        sub, marca_ = estil.get("subtitols", {}), estil.get("marca", {})
        accent = sub.get("clau_color") or sub.get("color_actiu") or "#FFFFFF"
        return {"mostra_broll": targetes.mostra(estil.get("broll", {}), accent),
                "mostres_grafics": grafics.mostres(marca_.get("energia"), marca_.get("crida") or "")}

    def info_efectes(projecte, trams, brolls, enganxines, titol, linies, situats) -> dict:
        """Els efectes de so (per a la llista de la pestanya So) i la pista que sona a la vista prèvia."""
        try:
            efectes = projecte.efectes(trams, brolls, enganxines, titol, linies, situats)
            pista = projecte.pista_efectes(trams, efectes)
        except Exception:  # un so propi que no es pot llegir, per exemple: la pàgina ha de funcionar igual
            traceback.print_exc()
            return {"efectes": [], "pista_efectes": None}
        return {"efectes": [{k: e[k] for k in ("clau", "nom", "so", "t", "actiu")} for e in efectes],
                "pista_efectes": f"/so/{pista.name}" if pista else None}

    def info_carpeta(projecte) -> dict:
        """On es desen els vídeos exportats: la carpeta de la persona, si n'ha triat una (també hi
        van, a més de la del projecte)."""
        propia = exporta.carpeta_exports()
        carpeta = propia or projecte.carpeta / EXPORTS
        return {"carpeta_exports": str(carpeta).replace(str(Path.home()), "~", 1), "carpeta_propia": bool(propia)}

    def versio_estil(projecte) -> str:
        """Canvia quan canvia el kit del vídeo o el seu fitxer (o les seves lletres)."""
        kit = projecte.kit()
        carpeta = marca.ruta(kit).parent
        fitxers = [carpeta / marca.FITXER_KIT, carpeta / "fonts"]
        return f"{kit}:" + ":".join(str(f.stat().st_mtime_ns) if f.exists() else "-" for f in fitxers)

    def info_marca() -> dict:
        # Les seccions, tal com són al kit (el de tots els vídeos): la pàgina hi posa al damunt el que aquest vídeo
        # hi ha canviat (l'estat, «estil»), que es desfà com la resta.
        kit = obert["p"].kit()
        del_kit = obert["p"].estil_kit()
        estil = del_kit["subtitols"]
        broll_estil = del_kit.get("broll", {})
        accent = estil.get("clau_color") or estil.get("color_actiu") or "#FFFFFF"
        fonts = [{"familia": f["familia"], "pes": f["pes"], "estil": f.get("estil", "normal"),
                  "url": f"/marca/fonts/{quote(f['fitxer'].name)}?v={int(f['fitxer'].stat().st_mtime)}"}
                 for f in marca.fonts_del_kit(kit) if f["fitxer"].parent == marca.ruta(kit).parent / "fonts"]
        return {"estil_subtitols": estil, "estil_titol": del_kit.get("titol", {}),
                "estil_so": del_kit.get("so", {}), "sons_propis": str(so.SONS_PROPIS),
                "estil_marca": del_kit.get("marca", {}), "estils_video": marca.estils_video(),
                "paleta_grafics": grafics.paleta(obert["p"].estil()),
                "mostres_grafics": grafics.mostres(obert["p"].estil().get("marca", {}).get("energia"),
                                                   obert["p"].estil().get("marca", {}).get("crida") or ""),
                "estils_titol": marca.estils_titol(), "estil_broll": broll_estil,
                "mostra_broll": targetes.mostra(broll_estil, accent),
                "estils_broll": [{**e, "mostra": targetes.mostra({**broll_estil, **e["valors"]}, accent)}
                                 for e in marca.estils_broll()], "fitxer_estil": str(marca.ruta(kit)),
                "kit": kit, "kits": marca.kits(), "fonts_kit": fonts, "versio_estil": versio_estil(obert["p"]),
                "biblioteca_lletres": marca.biblioteca_lletres(),
                "estils_subtitols": marca.estils()}

    class Gestor(BaseHTTPRequestHandler):
        # HTTP/1.1: connexions que es mantenen obertes, com esperen els reproductors de vídeo
        # (el Safari, amb HTTP/1.0, de vegades es quedava esperant dades en saltar pel vídeo).
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # silenciós: la terminal és per als missatges importants
            pass

        # --- respostes ---
        def _json(self, dades, codi=HTTPStatus.OK):
            cos = json.dumps(dades, ensure_ascii=False).encode()
            self.send_response(codi)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cos)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cos)

        def _fitxer(self, path: Path):
            if not path.is_file():
                return self.send_error(HTTPStatus.NOT_FOUND)
            info = path.stat()
            mida = info.st_size
            tipus = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            etiqueta = f'"{int(info.st_mtime)}-{mida}"'
            rang = self.headers.get("Range")
            if rang and self.headers.get("If-Range") not in (None, etiqueta):
                rang = None  # el fitxer ha canviat: enviem-lo sencer
            inici, final = 0, mida - 1
            if rang and rang.startswith("bytes="):
                a, _, b = rang[6:].partition("-")
                inici = int(a) if a else max(0, mida - int(b))
                final = int(b) if a and b else mida - 1
                final = min(final, mida - 1)
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Range", f"bytes {inici}-{final}/{mida}")
            else:
                self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", tipus)
            # Els fitxers (stickers SVG pujats, exports…) no poden executar res encara que s'obrin
            # directament al navegador: un SVG amb un script podria llegir el codi de la pàgina.
            if not tipus.startswith(("video/", "audio/")):  # els vídeos s'han de poder mirar tal qual
                self.send_header("Content-Security-Policy", "sandbox; default-src 'none'; img-src 'self' data:; "
                                                            "style-src 'unsafe-inline'; font-src 'self'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(final - inici + 1))
            self.send_header("ETag", etiqueta)
            self.send_header("Last-Modified", self.date_time_string(int(info.st_mtime)))
            if path.suffix in (".html", ".js", ".css", ".json"):
                self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                with path.open("rb") as f:
                    f.seek(inici)
                    pendent = final - inici + 1
                    while pendent > 0:
                        tros = f.read(min(1 << 20, pendent))
                        if not tros:
                            break
                        self.wfile.write(tros)
                        pendent -= len(tros)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True  # el navegador ha tallat la descàrrega (passa en saltar)

        def _amfitrio_valid(self) -> bool:
            if self.headers.get("Host", "") in amfitrions:
                return True
            self.close_connection = True
            self.send_error(HTTPStatus.FORBIDDEN)
            return False

        def _no_permesa(self, codi: HTTPStatus, missatge: str) -> bool:
            self.close_connection = True  # no llegim el cos: la connexió no es pot reaprofitar
            self._json({"error": missatge}, codi)
            return False

        def _peticio_valida(self, json_esperat: bool) -> bool:
            origen = self.headers.get("Origin")
            if origen is not None and origen not in origens:
                return self._no_permesa(HTTPStatus.FORBIDDEN, "Petició d'una altra web: no permesa")
            if not hmac.compare_digest(self.headers.get("X-Tallat-Token", ""), token):
                return self._no_permesa(HTTPStatus.FORBIDDEN, "Petició no autoritzada. Torna a carregar la pàgina.")
            if json_esperat and not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._no_permesa(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "S'esperava JSON")
            return True

        def _index(self):
            html = (PAGINA / "index.html").read_text(encoding="utf-8")
            html = html.replace("</head>", f'  <meta name="tallat-token" content="{token}">\n</head>', 1)
            for nom in ("app.js", "estil.css", "subtitols.js"):
                versio = int((PAGINA / nom).stat().st_mtime)
                html = html.replace(f"/pagina/{nom}", f"/pagina/{nom}?v={versio}")
            cos = html.encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cos)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cos)

        def _cos(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MIDA_MAXIMA_JSON:
                raise ValueError("massa gran")
            return json.loads(self.rfile.read(n) or b"{}")

        # --- rutes ---
        def do_GET(self):
            if not self._amfitrio_valid():
                return
            projecte = obert["p"]
            ruta = unquote(urlparse(self.path).path)
            if ruta == "/":
                return self._index()
            if ruta.startswith("/pagina/"):
                return self._segur(PAGINA, ruta[len("/pagina/"):])
            if ruta == "/proxy.mp4":
                return self._fitxer(projecte.proxy)
            if ruta.startswith("/broll/"):
                return self._segur(projecte.carpeta_instruccions() / broll.CARPETA, ruta[len("/broll/"):])
            if ruta.startswith("/stickers/"):
                return self._segur(projecte.carpeta_instruccions() / stickers.CARPETA, ruta[len("/stickers/"):])
            if ruta.startswith("/previa/"):  # el muntatge en un vídeo continu
                return self._segur(projecte.carpeta / PREVIES, ruta[len("/previa/"):])
            if ruta.startswith("/imatges-grafics/"):  # les captures i les fotos dels gràfics
                return self._segur(projecte.carpeta_imatges, ruta[len("/imatges-grafics/"):])
            if ruta.startswith("/so/"):  # la pista d'efectes, les mostres de la veu i cada so
                return self._segur(projecte.carpeta / "so", ruta[len("/so/"):])
            if ruta.startswith("/marca/fonts/"):  # les lletres del kit, per a la vista prèvia
                return self._segur(marca.ruta(projecte.kit()).parent / "fonts", ruta[len("/marca/fonts/"):])
            if ruta == "/api/biblioteca":
                return self._json({"broll": [p.name for p in broll.biblioteca()],
                                   "sticker": [p.name for p in stickers.biblioteca()]})
            if ruta.startswith("/exports/"):
                return self._segur(projecte.carpeta / EXPORTS, ruta[len("/exports/"):])
            if ruta.startswith("/notes-miniatures/"):  # els fotogrames de les notes de Revisa
                return self._segur(obert["arrel"].carpeta / notes.MINIATURES, ruta[len("/notes-miniatures/"):])
            if ruta == "/api/projecte":
                with bloqueig:
                    projecte.al_dia()
                    info = exporta.info_video(projecte.video) if projecte.video.exists() else {}
                    return self._json({
                        "nom": projecte.nom, "clau_projecte": clau_de(projecte),
                        "durada": projecte.dades["durada"], "fps": projecte.fps,
                        "font": projecte.dades.get("font"), "origen": info, "copia": versio_copia(projecte),
                        "paraules": projecte.dades["paraules"],
                        "paragrafs": projecte.paragrafs(),
                        "exports": projecte.exports(), "feina": feina.info(), **info_carpeta(projecte),
                        "estil_stickers": projecte.estil().get("stickers", {}),
                        **info_marca(),
                        **info_reels(),
                        **instantania()})
            if ruta == "/api/feina":
                return self._json({"feina": feina.info(), "exports": projecte.exports(), **info_carpeta(projecte)})
            if ruta == "/api/novetats":  # la pàgina hi pregunta sovint: hi ha canvis fets des del xat?
                with bloqueig:
                    projecte.al_dia()
                    info = info_notes()
                    return self._json({"clau_projecte": clau_de(projecte), "revisio": projecte.estat.get("revisio", 0),
                                       "estil": versio_estil(projecte), "versio_notes": info["versio_notes"],
                                       "connectat": info["connectat"], "darrer_export": darrer_export(projecte),
                                       "copia": versio_copia(projecte), "copia_fent": projecte.proxy_de() in copia["fent"],
                                       "copia_error": copia["error"]})
            if ruta == "/api/notes":
                return self._json(info_notes())
            if ruta == "/api/instantania":
                with bloqueig:
                    projecte.al_dia()
                    return self._json(instantania())
            if ruta == "/api/marca/info":
                with bloqueig:
                    return self._json({**info_marca(), **instantania()})
            if ruta == "/api/kit/exporta":  # el kit en un .zip, per passar-lo a algú (es baixa)
                kit = (parse_qs(urlparse(self.path).query).get("kit") or [""])[0]
                try:
                    nom, cos = marca.empaqueta_kit(kit)
                except KeyError:
                    return self.send_error(HTTPStatus.NOT_FOUND)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="{nom}"')
                self.send_header("Content-Length", str(len(cos)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(cos)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def _notes(self, cos):
            """Afegir una nota (a una paraula o a tot el vídeo), treure-la, contestar Claude o enviar-les."""
            arrel, p = obert["arrel"], obert["p"]
            accio = cos.get("accio")
            try:
                if accio == "afegeix":
                    # La nota va a una paraula (la que sonava en aquell moment) o a tot el vídeo. Perquè Claude
                    # l'entengui sense obrir res, s'hi desa el segon de la gravació i el que es diu al voltant.
                    # A Revisa, la nota és d'una versió (un esborrany exportat) i d'un segon d'aquell vídeo: la
                    # paraula es troba amb els talls d'aquella versió, i es desa la miniatura del fotograma.
                    paraula, inici, cita = cos.get("paraula"), None, None
                    versio, t_versio, miniatura = cos.get("versio"), None, None
                    if versio:
                        versio, t_versio, paraula, original = moment_de_versio(p, str(versio), cos.get("t"))
                        miniatura = desa_miniatura(arrel.carpeta, cos.get("miniatura"))
                    if paraula is not None:
                        paraula = int(paraula)
                        paraules = p.dades["paraules"]
                        if not 0 <= paraula < len(paraules):
                            raise ValueError("Aquesta paraula no hi és.")
                        # A Revisa, el segon exacte del moment (no el de l'inici de la paraula).
                        inici = original if versio else round(float(paraules[paraula]["inici"]), 3)
                        cita = " ".join(w["text"].strip() for w in paraules[max(0, paraula - 3):paraula + 4])
                    reel = None
                    if p is not arrel:
                        reel = next((r["titol"] for r in info_reels()["reels"] if r["id"] == p.carpeta.name), p.carpeta.name)
                    try:
                        notes.afegeix(arrel.carpeta, str(cos.get("text", "")), paraula=paraula, inici=inici,
                                      cita=cita, projecte=str(p.carpeta), reel=reel,
                                      versio=versio, t_versio=t_versio, miniatura=miniatura)
                    except Exception:  # la nota no s'ha desat: la seva miniatura no la farà servir ningú
                        notes.esborra_miniatura(arrel.carpeta, miniatura)
                        raise
                elif accio == "ronda":
                    # «Demana la ronda següent» (o, si encara no n'hi ha cap, les primeres propostes): una nota per a
                    # tot el vídeo que surt de seguida. Els vots i les notes de cada peça, Claude els llegeix amb
                    # `tallat.py grafics`.
                    primera = not any(g.get("estat") != "tret" for g in p.estat.get("grafics") or [])
                    text = "Proposa'm gràfics per a aquest vídeo." if primera else "Ronda següent de propostes."
                    general = " ".join(str(cos.get("text") or "").split())[:600]
                    if general:
                        text += f" Per a tota la ronda: «{general}»."
                    reel = None
                    if p is not arrel:
                        reel = next((r["titol"] for r in info_reels()["reels"] if r["id"] == p.carpeta.name), p.carpeta.name)
                    nota = notes.afegeix(arrel.carpeta, text, projecte=str(p.carpeta), reel=reel, tipus="ronda",
                                         ronda=p.estat.get("ronda", 0))
                    notes.envia(arrel.carpeta, nomes=nota["id"])  # només aquesta: les altres, quan la persona les enviï
                elif accio == "esborra":
                    notes.esborra(arrel.carpeta, int(cos.get("id")))
                elif accio == "respon":
                    notes.respon_persona(arrel.carpeta, int(cos.get("id")), str(cos.get("text", "")))
                elif accio == "envia":  # les de la versió que es revisa, o (sense) les que s'han fet editant
                    notes.envia(arrel.carpeta, projecte=str(p.carpeta), versio=cos.get("versio") or None)
                else:
                    return self._json({"error": "No sé què vols fer amb les notes."}, HTTPStatus.BAD_REQUEST)
            except (KeyError, ValueError, TypeError) as e:
                return self._json({"error": str(e).strip("'\"")}, HTTPStatus.BAD_REQUEST)
            except TimeoutError as e:
                return self._json({"error": str(e)}, HTTPStatus.SERVICE_UNAVAILABLE)
            except OSError as e:  # el disc ple, la carpeta sense permís…: abans, la pàgina només deia «Load failed»
                motiu = {errno.ENOSPC: " (el disc és ple)", errno.EACCES: " (no hi ha permís per escriure-hi)",
                         errno.EPERM: " (no hi ha permís per escriure-hi)",
                         errno.EROFS: " (el disc és només de lectura)"}.get(e.errno, "")
                return self._json({"error": f"No he pogut desar la nota a la carpeta del projecte{motiu}."},
                                  HTTPStatus.INTERNAL_SERVER_ERROR)
            return self._json(info_notes())

        def _carpeta_exports(self, projecte):
            """Tria la carpeta dels vídeos amb el diàleg del Mac, o torna a la del projecte."""
            try:
                cos = self._cos()
            except (ValueError, json.JSONDecodeError):
                return self._json({"error": "Petició no vàlida"}, HTTPStatus.BAD_REQUEST)
            if cos.get("accio") == "projecte":
                exporta.tria_carpeta_exports(None)
            else:
                triada = entorn.tria_carpeta("On vols desar els vídeos que exportis amb tallat?")
                if triada is None:  # ha cancel·lat
                    return self._json({"cancel·lat": True, **info_carpeta(projecte)})
                exporta.tria_carpeta_exports(triada)
            return self._json(info_carpeta(projecte))

        def do_POST(self):
            ruta = urlparse(self.path).path
            fitxer = ruta in RUTES_DE_FITXER
            if not self._amfitrio_valid() or not self._peticio_valida(json_esperat=not fitxer):
                return
            projecte = obert["p"]
            if ruta in RUTES_DEL_PROJECTE and self.headers.get("X-Tallat-Projecte") != clau_de(projecte):
                # Una altra pestanya ha obert un altre projecte (un reel, o la gravació sencera).
                self._no_permesa(HTTPStatus.CONFLICT, "projecte-canviat")
                return
            if ruta == "/api/broll/puja":
                return self._puja_broll(projecte)
            if ruta == "/api/grafics/imatge":
                return self._puja_imatge_grafic(projecte)
            if ruta == "/api/exports/carpeta":
                return self._carpeta_exports(projecte)
            if ruta == "/api/marca/font":
                return self._puja_font()
            if ruta == "/api/kit/importa":
                return self._importa_kit()
            try:
                cos = self._cos()
            except ValueError:
                self._no_permesa(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Petició massa gran")
                return
            except json.JSONDecodeError:
                return self._json({"error": "JSON no vàlid"}, HTTPStatus.BAD_REQUEST)
            with bloqueig:
                # Mentre llegíem el cos, una altra pestanya pot haver canviat de projecte o haver tornat
                # a obrir el mateix reel (amb canvis desats): es comprova amb el que hi ha obert ara.
                projecte = obert["p"]
                if ruta in RUTES_DEL_PROJECTE and self.headers.get("X-Tallat-Projecte") != clau_de(projecte):
                    return self._json({"error": "projecte-canviat"}, HTTPStatus.CONFLICT)
                projecte.al_dia()  # si Claude hi ha fet canvis des del xat, es tenen en compte
                if ruta == "/api/obre":  # canvia a un reel proposat o torna a la gravació sencera
                    arrel = obert["arrel"]
                    rid = cos.get("reel")
                    if not rid:
                        obert["p"] = arrel
                        fes_copia(arrel)
                        return self._json({"ok": True})
                    reels, _ = muntatge.llegeix_reels(arrel.carpeta, arrel.dades["paraules"])
                    reel = next((r for r in reels if r["id"] == rid), None)
                    if reel is None:
                        return self._json({"error": "No trobo aquest reel"}, HTTPStatus.NOT_FOUND)
                    obert["p"] = Projecte(muntatge.crea_reel(arrel, reel))
                    fes_copia(obert["p"])  # el reel pot estar enquadrat d'una altra manera que la gravació
                    return self._json({"ok": True})
                if ruta == "/api/notes":  # les notes per a Claude
                    return self._notes(cos)
                if ruta == "/api/estat":
                    if cos.get("revisio") != projecte.estat.get("revisio", 0):
                        # Una altra pestanya ha desat abans: no la trepitgem.
                        return self._json({"error": "conflicte", **instantania()}, HTTPStatus.CONFLICT)
                    projecte.estat = _estat_de_json(cos)
                    projecte.estat["revisio"] = cos["revisio"] + 1
                    projecte.desa()
                    fes_copia(projecte)  # si ara se n'enquadra un d'horitzontal d'una altra manera
                    return self._json(instantania())
                if ruta == "/api/previa":  # el muntatge d'ara en un vídeo continu (si no hi és, es fa)
                    return self._json(previa.demana(projecte, projecte.trams()))
                if ruta == "/api/registre":  # què fa el reproductor al navegador (per trobar errors)
                    with (projecte.carpeta / "registre-pagina.log").open("a", encoding="utf-8") as f:
                        for e in cos.get("events", [])[:500]:
                            f.write(json.dumps(e, ensure_ascii=False) + "\n")
                    return self._json({"ok": True})
                if ruta == "/api/instruccio":  # accepta o descarta una instrucció de veu
                    nou = cos.get("estat")
                    if nou not in ("acceptada", "descartada", "pendent"):
                        return self._json({"error": "Estat no vàlid"}, HTTPStatus.BAD_REQUEST)
                    try:
                        projecte.decideix_instruccio(str(cos.get("id")), nou)
                        projecte.suggereix_stickers()  # «sticker d'un cor» → cor.png de la biblioteca
                    except KeyError:
                        return self._json({"error": "No trobo aquesta instrucció"}, HTTPStatus.NOT_FOUND)
                    projecte.estat["revisio"] = projecte.estat.get("revisio", 0) + 1
                    projecte.desa()
                    return self._json(instantania())
                if ruta in ("/api/broll/biblioteca", "/api/broll/treu", "/api/broll/esborra"):
                    iid = str(cos.get("instruccio", ""))
                    paraula = cos.get("paraula")  # Vesteix: un b-roll nou en aquesta paraula
                    try:
                        if ruta.endswith("treu"):
                            projecte.treu_broll(iid)
                        elif ruta.endswith("esborra"):
                            projecte.esborra_broll(iid)
                        elif isinstance(paraula, int) and not isinstance(paraula, bool) and not iid:
                            fitxer = next((p for p in broll.biblioteca() if p.name == cos.get("nom", "")), None)
                            if fitxer is None:
                                return self._json({"error": "No trobo aquest fitxer a la biblioteca"}, HTTPStatus.NOT_FOUND)
                            projecte.afegeix_broll(paraula, fitxer)
                        else:
                            nom = cos.get("nom", "")
                            ins = next((i for i in projecte.instruccions() if i["id"] == iid), {})
                            llista = stickers.biblioteca() if ins.get("tipus") == "sticker" else broll.biblioteca()
                            fitxer = next((p for p in llista if p.name == nom), None)
                            if fitxer is None:
                                return self._json({"error": "No trobo aquest fitxer a la biblioteca"}, HTTPStatus.NOT_FOUND)
                            projecte.assigna_recurs(iid, fitxer)
                    except KeyError:
                        return self._json({"error": "No trobo aquesta instrucció"}, HTTPStatus.NOT_FOUND)
                    except ValueError as e:
                        return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                    except Exception as e:  # ffmpeg no ha pogut llegir el fitxer
                        return self._json({"error": f"No he pogut preparar el b-roll: {e}"}, HTTPStatus.BAD_REQUEST)
                    return self._json(instantania())
                if ruta in ("/api/marca", "/api/marca/restableix", "/api/marca/lletra") and cos.get("kit") not in (None, projecte.kit()):
                    # La pàgina ho demanava per a un altre kit (el vídeo n'ha canviat mentrestant): no en toquem cap.
                    return self._json({"error": "Aquest vídeo ha canviat d'estil i aquest canvi no s'ha desat. "
                                                "Torna'l a fer si el vols a l'estil nou.", **info_marca(), **instantania()},
                                      HTTPStatus.CONFLICT)
                if ruta in ("/api/marca", "/api/marca/restableix"):  # l'estil (subtítols, títol, b-roll o so), al kit del vídeo
                    try:
                        if ruta.endswith("restableix"):
                            seccio = cos.get("seccio") or "subtitols"
                            if seccio not in ("subtitols", "titol", "broll", "so"):
                                raise ValueError("Secció desconeguda")
                            marca.restableix(seccio, kit=projecte.kit())
                        else:
                            for seccio in ("subtitols", "titol", "broll", "so", "marca"):
                                if isinstance(cos.get(seccio), dict):
                                    marca.desa(seccio, cos[seccio], kit=projecte.kit())
                    except ValueError as e:
                        return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                    return self._json({**info_marca(), **instantania()})
                if ruta == "/api/so/mostres":  # la veu abans i després de netejar-la, i cada efecte
                    try:
                        veu = projecte.mostres_veu()
                        sons = {}
                        for nom in so.NOMS:
                            sons[nom] = f"/so/{so.mostra_efecte(nom, projecte.carpeta / 'so').name}"
                    except (OSError, RuntimeError, subprocess.CalledProcessError) as e:
                        return self._json({"error": f"No he pogut preparar les mostres: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
                    return self._json({"abans": f"/so/{veu['abans'].name}", "despres": f"/so/{veu['despres'].name}",
                                       "sons": sons})
                if ruta == "/api/estil/a-tots":  # «Fes-lo servir en tots els vídeos»: l'estil d'aquest vídeo, al kit
                    try:
                        queda = marca.passa_al_kit(projecte.estat.get("estil") or {}, kit=projecte.kit())
                    except ValueError as e:
                        return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                    projecte.estat["estil"] = queda  # els colors i les lletres canviats només aquí, aquí es queden
                    projecte.estat["revisio"] = projecte.estat.get("revisio", 0) + 1
                    projecte.desa()
                    return self._json({**info_marca(), **instantania()})
                if ruta == "/api/marca/lletra":  # una lletra de la biblioteca (es baixa al kit el primer cop)
                    if cos.get("nomes_baixa"):  # la fa servir un sol vídeo: la pàgina la posa al seu estil
                        try:
                            nom = marca.baixa_lletra(str(cos.get("id", "")), kit=projecte.kit(), nomes_baixa=True)
                        except KeyError:
                            return self._json({"error": "No conec aquesta lletra"}, HTTPStatus.NOT_FOUND)
                        except ConnectionError as e:
                            return self._json({"error": str(e)}, HTTPStatus.BAD_GATEWAY)
                        return self._json({"familia": nom, **info_marca()})
                    try:
                        marca.baixa_lletra(str(cos.get("id", "")), kit=projecte.kit(),
                                           seccio=str(cos.get("seccio") or "subtitols"), clau=str(cos.get("clau") or "font"))
                    except KeyError:
                        return self._json({"error": "No conec aquesta lletra"}, HTTPStatus.NOT_FOUND)
                    except ValueError as e:
                        return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                    except ConnectionError as e:
                        return self._json({"error": str(e)}, HTTPStatus.BAD_GATEWAY)
                    return self._json({**info_marca(), **instantania()})
                if ruta.startswith("/api/kit/"):  # triar, crear, canviar el nom, per defecte o treure un kit
                    kit = str(cos.get("kit") or "")
                    try:
                        if ruta == "/api/kit/tria":
                            projecte.tria_kit(kit)
                        elif ruta == "/api/kit/nou":  # un kit nou (còpia d'un altre o neutre) per a aquest vídeo
                            copia = cos.get("copia_de")
                            projecte.tria_kit(marca.crea_kit(cos.get("nom", ""), str(copia) if copia else None))
                        elif ruta == "/api/kit/nom":
                            marca.canvia_nom(kit, cos.get("nom", ""))
                        elif ruta == "/api/kit/per-defecte":
                            marca.fes_per_defecte(kit)
                        elif ruta == "/api/kit/esborra":
                            marca.esborra_kit(kit)
                        else:
                            return self.send_error(HTTPStatus.NOT_FOUND)
                    except KeyError:
                        return self._json({"error": "No trobo aquest estil"}, HTTPStatus.NOT_FOUND)
                    except ValueError as e:
                        return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                    return self._json({**info_marca(), **instantania()})
                if ruta == "/api/editors":  # projecte per acabar-lo en un altre editor
                    if not feina.comença(projecte, "editors", capa=bool(cos.get("capa")),
                                         trossos=bool(cos.get("trossos"))):
                        return self._json({"error": "Ja hi ha un render en marxa"}, HTTPStatus.CONFLICT)
                    return self._json({"feina": feina.info()})
                if ruta == "/api/mostra":  # obre el Finder amb el fitxer seleccionat
                    # el de la carpeta de la persona (copia) o el del projecte
                    carpeta = exporta.carpeta_exports() if cos.get("copia") else None
                    carpeta = (carpeta or projecte.carpeta / EXPORTS).resolve()
                    path = (carpeta / str(cos.get("copia") or cos.get("nom", ""))).resolve()
                    if path.parent != carpeta or not path.exists():
                        return self._json({"error": "No trobo aquest fitxer"}, HTTPStatus.NOT_FOUND)
                    entorn.mostra_al_gestor(path)
                    return self._json({"ok": True})
                if ruta == "/api/exporta":
                    qualitat = cos.get("qualitat", "esborrany")
                    if qualitat not in exporta.QUALITATS:
                        return self._json({"error": "Qualitat desconeguda"}, HTTPStatus.BAD_REQUEST)
                    if not feina.comença(projecte, qualitat):
                        return self._json({"error": "Ja hi ha un render en marxa"}, HTTPStatus.CONFLICT)
                    return self._json({"feina": feina.info()})
            self.send_error(HTTPStatus.NOT_FOUND)

        def _puja_broll(self, projecte):
            """Rep un fitxer (vídeo o imatge) i el fa servir de b-roll o sticker d'una instrucció.

            Abans de llegir res, comprova el tipus, la mida i que la instrucció existeixi."""
            consulta = parse_qs(urlparse(self.path).query)
            iid = (consulta.get("instruccio") or [""])[0]
            nom = Path((consulta.get("nom") or ["fitxer"])[0]).name
            mida = int(self.headers.get("Content-Length") or 0)
            # El tauler: un b-roll o un sticker nou en una paraula (en lloc d'una instrucció que ja hi era).
            paraula = (consulta.get("paraula") or [""])[0]
            paraula = int(paraula) if paraula.isdigit() and not iid else None
            sticker = paraula is not None and (consulta.get("tipus") or [""])[0] == "sticker"
            if sticker and not stickers.es_compatible(Path(nom)):
                return self._no_permesa(HTTPStatus.BAD_REQUEST, "Un sticker ha de ser una imatge PNG, WebP, GIF o SVG")
            if not sticker and not (broll.es_compatible(Path(nom)) or (paraula is None and stickers.es_compatible(Path(nom)))):
                return self._no_permesa(HTTPStatus.BAD_REQUEST, "Aquest tipus de fitxer no serveix: ha de ser un vídeo o una imatge")
            if not 0 < mida <= MIDA_MAXIMA_PUJADA:
                return self._no_permesa(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "El fitxer és buit o massa gran (2 GB com a màxim)")
            if paraula is not None:
                if paraula >= len(projecte.dades["paraules"]):
                    return self._no_permesa(HTTPStatus.BAD_REQUEST, "No trobo aquest moment del vídeo")
            elif not any(i["id"] == iid and i.get("tipus") in ("broll", "sticker") for i in projecte.instruccions()):
                return self._no_permesa(HTTPStatus.NOT_FOUND, "No trobo aquesta instrucció")
            carpeta = projecte.carpeta_instruccions() / broll.CARPETA / "pujats"
            carpeta.mkdir(parents=True, exist_ok=True)
            # Un fitxer temporal per pujada: dues pestanyes que pugin «image.png» alhora no es barregen.
            # Conserva l'extensió (és la que diu si és vídeo, imatge o sticker).
            temporal = carpeta / f".pujant-{uuid.uuid4().hex}{Path(nom).suffix.lower()}"
            try:
                with temporal.open("wb") as f:
                    pendent = mida
                    while pendent > 0:
                        tros = self.rfile.read(min(1 << 20, pendent))
                        if not tros:
                            raise ConnectionError("pujada interrompuda")
                        f.write(tros)
                        pendent -= len(tros)
            except (OSError, ConnectionError):
                temporal.unlink(missing_ok=True)
                self.close_connection = True
                return
            try:
                with bloqueig:
                    if self.headers.get("X-Tallat-Projecte") != clau_de(obert["p"]):
                        return self._json({"error": "projecte-canviat"}, HTTPStatus.CONFLICT)
                    try:
                        if paraula is not None:
                            obert["p"].afegeix_broll(paraula, temporal, "sticker" if sticker else "broll")
                        else:
                            obert["p"].assigna_recurs(iid, temporal)  # en fa una còpia al projecte
                    except KeyError:
                        return self._json({"error": "No trobo aquesta instrucció"}, HTTPStatus.NOT_FOUND)
                    except Exception as e:
                        return self._json({"error": f"No he pogut preparar el b-roll: {e}"}, HTTPStatus.BAD_REQUEST)
                    return self._json(instantania())
            finally:
                temporal.unlink(missing_ok=True)

        def _puja_imatge_grafic(self, projecte):
            """Rep una imatge per a un gràfic: la captura de la web (la canvia) o una foto més (el ventall, l'abans i
            després o el carrusel)."""
            consulta = parse_qs(urlparse(self.path).query)
            gid = (consulta.get("grafic") or [""])[0]
            nom = Path((consulta.get("nom") or ["imatge"])[0]).name
            mida = int(self.headers.get("Content-Length") or 0)
            if Path(nom).suffix.lower() not in grafics.FORMATS_IMATGE:
                return self._no_permesa(HTTPStatus.BAD_REQUEST, "Ha de ser una imatge PNG, JPG, WebP o GIF")
            if not 0 < mida <= MIDA_MAXIMA_IMATGE:
                return self._no_permesa(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "La imatge és buida o massa gran (60 MB com a màxim)")
            contingut = self.rfile.read(mida)
            if len(contingut) != mida:
                self.close_connection = True
                return
            with bloqueig:
                projecte = obert["p"]
                if self.headers.get("X-Tallat-Projecte") != clau_de(projecte):
                    return self._json({"error": "projecte-canviat"}, HTTPStatus.CONFLICT)
                projecte.al_dia()
                g = next((x for x in projecte.estat.get("grafics") or [] if x["id"] == gid), None)
                if g is None or g["tipus"] not in grafics.AMB_IMATGE:
                    return self._json({"error": "No trobo aquest gràfic"}, HTTPStatus.NOT_FOUND)
                # Les fotos que ja no hi són (esborrades, d'un pla amb un camí dolent) deixen el seu lloc lliure.
                imatges = projecte.imatges_grafics()
                buit = next((p for p in g["punts"] if not grafics.imatge_valida(p.get("imatge"), imatges)), None)
                maxim = grafics.MAX_FOTOS.get(g["tipus"], grafics.MAX_PUNTS)
                if g["tipus"] in grafics.AMB_FOTOS and buit is None and len(g["punts"]) >= maxim:
                    return self._json({"error": f"Hi caben {maxim} fotos com a molt"}, HTTPStatus.BAD_REQUEST)
                with tempfile.TemporaryDirectory() as temporal:
                    fitxer = Path(temporal) / f"imatge{Path(nom).suffix.lower()}"
                    fitxer.write_bytes(contingut)
                    nom_imatge = projecte.importa_imatge(fitxer)
                if g["tipus"] == "web":
                    g["imatge"] = nom_imatge
                elif buit is not None:
                    buit["imatge"] = nom_imatge
                else:
                    g["punts"].append({"imatge": nom_imatge, "text": "", "paraula": None})
                if g["estat"] == "proposat":  # si hi poses la imatge, és que t'agrada
                    g["estat"] = "mantingut"
                projecte.estat["revisio"] = projecte.estat.get("revisio", 0) + 1
                projecte.desa()
                return self._json(instantania())

        def _puja_font(self):
            """Rep una font (.ttf, .otf, .woff o .woff2) i la fa servir per als subtítols."""
            nom = Path((parse_qs(urlparse(self.path).query).get("nom") or [""])[0]).name
            mida = int(self.headers.get("Content-Length") or 0)
            if Path(nom).suffix.lower() not in marca.FORMATS_FONT:
                return self._no_permesa(HTTPStatus.BAD_REQUEST, "La font ha de ser un fitxer .ttf, .otf, .woff o .woff2")
            if not 0 < mida <= MIDA_MAXIMA_FONT:
                return self._no_permesa(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "La font és buida o massa gran")
            contingut = self.rfile.read(mida)
            with bloqueig:
                if self.headers.get("X-Tallat-Projecte") != clau_de(obert["p"]):
                    return self._json({"error": "projecte-canviat"}, HTTPStatus.CONFLICT)
                try:
                    marca.desa_font(nom, contingut, kit=obert["p"].kit())
                except ValueError as e:
                    return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                return self._json({**info_marca(), **instantania()})

        def _importa_kit(self):
            """Rep un kit (el .zip que fa «Exporta»), l'afegeix i el fa servir per a aquest vídeo."""
            mida = int(self.headers.get("Content-Length") or 0)
            if not 0 < mida <= marca.MIDA_MAXIMA_KIT:
                return self._no_permesa(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "El fitxer de l'estil és buit o massa gran")
            contingut = self.rfile.read(mida)
            with bloqueig:
                if self.headers.get("X-Tallat-Projecte") != clau_de(obert["p"]):
                    return self._json({"error": "projecte-canviat"}, HTTPStatus.CONFLICT)
                try:
                    obert["p"].tria_kit(marca.importa_kit(contingut))
                except ValueError as e:
                    return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                return self._json({**info_marca(), **instantania()})

        def _segur(self, arrel: Path, relatiu: str):
            path = (arrel / relatiu).resolve()
            if arrel.resolve() not in path.parents:
                return self.send_error(HTTPStatus.FORBIDDEN)
            return self._fitxer(path)

    return _Servidor(("127.0.0.1", port), Gestor)


class _Servidor(ThreadingHTTPServer):
    daemon_threads = True  # en tancar la pàgina (Control + C), no esperem les connexions obertes

    def handle_error(self, request, client_address):
        # El navegador talla connexions sovint (en saltar pel vídeo): no és cap error de debò.
        error = sys.exc_info()[1]
        if isinstance(error, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def _estat_json(estat: dict) -> dict:
    sortida = dict(estat)
    for clau in ("esborrades", "propostes", "correccions", "destacades"):
        sortida[clau] = {str(k): v for k, v in estat[clau].items()}
    return sortida


def _estat_de_json(cos: dict) -> dict:
    estat = edicio.estat_buit()
    estat.update({k: v for k, v in cos.items() if k in estat})
    for clau in ("esborrades", "propostes", "correccions", "destacades"):
        estat[clau] = {int(k): v for k, v in (estat[clau] or {}).items()}
    estat["destacades"] = {k: bool(v) for k, v in estat["destacades"].items()}
    estat["titol"] = edicio.titol_net(estat.get("titol"))
    estat["grafics"] = grafics.neteja_llista(estat.get("grafics"))
    estat["sons"] = so.neteja_sons(estat.get("sons"))
    estat["estil"] = marca.neteja_estil_video(estat.get("estil"))
    estat["vots"] = edicio.vots_nets(estat.get("vots"))
    estat["llocs_stickers"] = edicio.llocs_stickers_nets(estat.get("llocs_stickers"))
    estat["encaix"] = estat.get("encaix") if estat.get("encaix") in exporta.ENCAIXOS else "retalla"
    estat["ronda"] = edicio.ronda_neta(estat.get("ronda"))
    apagats = estat.get("sons_apagats") if isinstance(estat.get("sons_apagats"), list) else []
    estat["sons_apagats"] = sorted({c for c in apagats if isinstance(c, str) and 0 < len(c) <= 60})[:500]
    for clau in ("mantingudes", "pauses_mantingudes"):
        estat[clau] = [int(i) for i in (estat[clau] or [])]
    return estat
