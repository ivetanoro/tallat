"""Servidor local de la pàgina de revisió. Només escolta a 127.0.0.1: res no surt de l'ordinador."""
from __future__ import annotations

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
import traceback
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from motor import broll, edicio, editors, entorn, exporta, grafics, marca, muntatge, so, stickers, targetes
from motor.projecte import EXPORTS, PREVIES, PROXY, Projecte

PAGINA = Path(__file__).resolve().parent.parent / "pagina"
MIDA_MAXIMA_FONT = 20 * 1024 * 1024  # una font no passa mai d'uns quants MB
MIDA_MAXIMA_JSON = 10 * 1024 * 1024  # l'estat d'un projecte llarg no arriba ni a 1 MB
MIDA_MAXIMA_PUJADA = 2 * 1024 ** 3   # un b-roll o un sticker
MIDA_MAXIMA_IMATGE = 60 * 1024 ** 2  # una captura o una foto d'un gràfic
# Les peticions que canvien el projecte obert: han de dir a quin projecte van (dues pestanyes).
RUTES_DEL_PROJECTE = {"/api/estat", "/api/instruccio", "/api/broll/biblioteca",
                      "/api/broll/treu", "/api/broll/puja", "/api/mostra", "/api/exporta", "/api/editors",
                      "/api/marca", "/api/marca/restableix", "/api/marca/font", "/api/marca/lletra",
                      "/api/kit/tria", "/api/kit/nou",
                      "/api/kit/nom", "/api/kit/per-defecte", "/api/kit/esborra", "/api/kit/importa",
                      "/api/so/mostres", "/api/grafics/imatge", "/api/previa", "/api/escolta"}
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
                    carpeta = editors.exporta_editors(projecte, amb_capa=capa)
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
                            blocs=projecte.blocs(trams), **projecte.opcions_so(trams))
            projecte.desa_talls(sortida, trams)
            copia, avis = _copia(sortida)  # també l'esborrany: la carpeta que es tria és per a tot
            durades = exporta.comprova_durades(sortida, sum(b - a for a, b in trams), projecte.dades["fps"])
            avis = " ".join(x for x in (durades, avis) if x) or None
            self._actualitza(estat="fet", progres=100, fitxer=sortida.name, copia=copia, avis=avis)
        except Exception as e:  # el missatge arriba a la pàgina
            traceback.print_exc()
            self._actualitza(estat="error", error=str(e))


def _esborra(path: Path) -> None:
    """Esborra una vista prèvia vella. A Windows no es pot esborrar un fitxer obert (el navegador encara la
    pot estar llegint): llavors es deixa, i ja s'esborrarà una altra vegada."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


class Previa:
    """El muntatge en un vídeo continu per a la pàgina (exporta.fes_previa), un alhora i en segon pla.
    La pàgina el demana després de cada canvi; mentre es fa, reprodueix saltant com sempre."""

    def __init__(self):
        self.bloqueig = threading.Lock()
        self.fent = None  # el fitxer que s'està fent

    def demana(self, projecte: Projecte, trams) -> dict:
        if not trams or not (projecte.fitxer(PROXY)).exists():
            return {"estat": "no", "trams": edicio.trams_json(trams)}
        desti = projecte.previa(trams)
        if desti.exists():
            try:
                os.utime(desti)  # la darrera que s'ha demanat: la neteja no se l'emporta
            except OSError:
                pass
            return {"estat": "fet", "url": f"/previa/{desti.name}", "trams": edicio.trams_json(trams)}
        with self.bloqueig:
            if self.fent is None:  # si se'n fa una altra, la pàgina ho tornarà a demanar
                self.fent = desti
                threading.Thread(target=self._fes, args=(projecte.fitxer(PROXY), list(trams), desti),
                                 daemon=True).start()
        return {"estat": "fent", "trams": edicio.trams_json(trams)}

    def _fes(self, proxy: Path, trams, desti: Path) -> None:
        try:
            exporta.fes_previa(proxy, trams, desti)
            # Se'n guarden les quatre que s'han fet servir darrerament (desfer i refer hi tornen); la que
            # sona a la pàgina sempre n'és una, perquè cada petició la toca (os.utime).
            for vell in sorted(desti.parent.glob("previa_*.mp4"), key=lambda p: p.stat().st_mtime)[:-4]:
                _esborra(vell)
        except Exception:
            traceback.print_exc()
        finally:
            with self.bloqueig:
                self.fent = None


ESCOLTA = 1.5  # segons abans i després del tall que se senten en treure o recuperar paraules


def prepara_escolta(projecte: Projecte, m: float) -> dict | None:
    """El que cal per fer el vídeo curt d'escolta (es llegeix amb el projecte bloquejat; el vídeo es fa
    després, sense bloquejar: mentrestant la pàgina ha de poder desar i fer la resta, revisió de Codex)."""
    proxy = projecte.fitxer(PROXY)
    trams, inici = edicio.finestra(projecte.trams(), max(0.0, m - ESCOLTA), m + ESCOLTA, projecte.fps)
    if not trams or not proxy.exists():
        return None
    return {"proxy": proxy, "trams": trams, "desti": projecte.previa(trams, nom="escolta"), "inici": inici}


def fes_escolta(feina: dict | None) -> dict:
    """El muntatge d'uns segons al voltant d'un tall (un vídeo curt fet ara mateix: en mig segon ja és a
    punt) i se sent com a l'export: el so tallat al punt exacte i amb els fosos. Mentrestant el muntatge
    sencer encara no hi és, i la còpia que salta no fa fosos. Si no es pot fer a temps, la pàgina ho fa
    com abans."""
    if feina is None:
        return {"estat": "no"}
    desti = feina["desti"]
    if not desti.exists():
        try:
            exporta.fes_previa(feina["proxy"], feina["trams"], desti, curt=True)
        except Exception:  # noqa: BLE001 — la pàgina se'n surt sense
            traceback.print_exc()
            return {"estat": "no"}
        for vell in sorted(desti.parent.glob("escolta_*.mp4"), key=lambda p: p.stat().st_mtime)[:-5]:
            _esborra(vell)
    return {"estat": "fet", "url": f"/previa/{desti.name}", "inici": feina["inici"],
            "durada": round(sum(b - a for a, b in feina["trams"]), 6)}


def escolta(projecte: Projecte, m: float) -> dict:
    return fes_escolta(prepara_escolta(projecte, m))


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

    def info_reels() -> dict:
        arrel = obert["arrel"]
        reels, errors = muntatge.llegeix_reels(arrel.carpeta, arrel.dades["paraules"])
        actual = None
        if obert["p"] is not arrel:
            actual = obert["p"].carpeta.name
        return {"arrel": arrel.nom, "reel_actual": actual, "errors_reels": errors,
                "reels": [dict(r, durada=muntatge.durada_estimada(arrel, r)) for r in reels]}

    def instantania() -> dict:
        projecte = obert["p"]
        trams = projecte.trams()
        brolls, enganxines = projecte.brolls(trams), projecte.stickers(trams)
        linies, titol = projecte.linies_subtitols(trams), projecte.titol(trams)
        situats = projecte.grafics(trams, linies)
        return {"estat": _estat_json(projecte.estat), "trams": edicio.trams_json(trams),
                "durada_final": round(sum(b - a for a, b in trams), 3),
                "zooms": projecte.zooms_per_tram(trams), "zoom": exporta.ZOOM,
                "instruccions": projecte.instruccions(),
                "brolls": [{**{k: v for k, v in b.items() if k != "fitxer"},
                            "url": "/broll/" + b["fitxer"].name + f"?v={int(b['fitxer'].stat().st_mtime)}"}
                           for b in brolls],
                "stickers": [{"id": st["id"], "inici": st["inici"], "durada": st["durada"],
                              "url": "/stickers/" + st["fitxer"].name + f"?v={int(st['fitxer'].stat().st_mtime)}"}
                             for st in enganxines],
                "subtitols": linies,
                "titol": titol, "grafics": situats, "grafics_dibuix": projecte.dibuixos_grafics(linies),
                "blocs": projecte.blocs(trams, situats),
                **info_efectes(projecte, trams, brolls, enganxines, titol, linies, situats),
                "paragrafs": projecte.paragrafs()}

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
        kit = obert["p"].kit()
        estil = obert["p"].estil_subtitols()
        broll_estil = obert["p"].estil().get("broll", {})
        accent = estil.get("clau_color") or estil.get("color_actiu") or "#FFFFFF"
        fonts = [{"familia": f["familia"], "pes": f["pes"], "estil": f.get("estil", "normal"),
                  "url": f"/marca/fonts/{quote(f['fitxer'].name)}?v={int(f['fitxer'].stat().st_mtime)}"}
                 for f in marca.fonts_del_kit(kit) if f["fitxer"].parent == marca.ruta(kit).parent / "fonts"]
        return {"estil_subtitols": estil, "estil_titol": obert["p"].estil().get("titol", {}),
                "estil_so": obert["p"].estil_so(), "sons_propis": str(so.SONS_PROPIS),
                "estil_marca": obert["p"].estil().get("marca", {}),
                "paleta_grafics": grafics.paleta(obert["p"].estil()),
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
                return self._fitxer(projecte.fitxer(PROXY))
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
            if ruta == "/api/projecte":
                with bloqueig:
                    projecte.al_dia()
                    info = exporta.info_video(projecte.video) if projecte.video.exists() else {}
                    return self._json({
                        "nom": projecte.nom, "clau_projecte": clau_de(projecte),
                        "durada": projecte.dades["durada"], "fps": projecte.fps,
                        "font": projecte.dades.get("font"), "origen": info,
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
                    return self._json({"clau_projecte": clau_de(projecte), "revisio": projecte.estat.get("revisio", 0),
                                       "estil": versio_estil(projecte)})
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
            feina_escolta = None
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
                        return self._json({"ok": True})
                    reels, _ = muntatge.llegeix_reels(arrel.carpeta, arrel.dades["paraules"])
                    reel = next((r for r in reels if r["id"] == rid), None)
                    if reel is None:
                        return self._json({"error": "No trobo aquest reel"}, HTTPStatus.NOT_FOUND)
                    obert["p"] = Projecte(muntatge.crea_reel(arrel, reel))
                    return self._json({"ok": True})
                if ruta == "/api/estat":
                    if cos.get("revisio") != projecte.estat.get("revisio", 0):
                        # Una altra pestanya ha desat abans: no la trepitgem.
                        return self._json({"error": "conflicte", **instantania()}, HTTPStatus.CONFLICT)
                    projecte.estat = _estat_de_json(cos)
                    projecte.estat["revisio"] = cos["revisio"] + 1
                    projecte.desa()
                    return self._json(instantania())
                if ruta == "/api/previa":  # el muntatge d'ara en un vídeo continu (si no hi és, es fa)
                    return self._json(previa.demana(projecte, projecte.trams()))
                if ruta == "/api/escolta":  # uns segons al voltant d'un tall: el vídeo es fa fora del bloqueig
                    feina_escolta = prepara_escolta(projecte, float(cos.get("m", 0)))
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
                if ruta in ("/api/broll/biblioteca", "/api/broll/treu"):
                    iid = str(cos.get("instruccio", ""))
                    try:
                        if ruta.endswith("treu"):
                            projecte.treu_broll(iid)
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
                if ruta == "/api/marca/lletra":  # una lletra de la biblioteca (es baixa al kit el primer cop)
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
            if ruta == "/api/escolta":
                return self._json(fes_escolta(feina_escolta))
            self.send_error(HTTPStatus.NOT_FOUND)

        def _puja_broll(self, projecte):
            """Rep un fitxer (vídeo o imatge) i el fa servir de b-roll o sticker d'una instrucció.

            Abans de llegir res, comprova el tipus, la mida i que la instrucció existeixi."""
            consulta = parse_qs(urlparse(self.path).query)
            iid = (consulta.get("instruccio") or [""])[0]
            nom = Path((consulta.get("nom") or ["fitxer"])[0]).name
            mida = int(self.headers.get("Content-Length") or 0)
            if not (broll.es_compatible(Path(nom)) or stickers.es_compatible(Path(nom))):
                return self._no_permesa(HTTPStatus.BAD_REQUEST, "Aquest tipus de fitxer no serveix")
            if not 0 < mida <= MIDA_MAXIMA_PUJADA:
                return self._no_permesa(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "El fitxer és buit o massa gran (2 GB com a màxim)")
            if not any(i["id"] == iid and i.get("tipus") in ("broll", "sticker") for i in projecte.instruccions()):
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
                        obert["p"].assigna_recurs(iid, temporal)  # en fa una còpia al projecte
                    except KeyError:
                        return self._json({"error": "No trobo aquesta instrucció"}, HTTPStatus.NOT_FOUND)
                    except Exception as e:
                        return self._json({"error": f"No he pogut preparar el b-roll: {e}"}, HTTPStatus.BAD_REQUEST)
                    return self._json(instantania())
            finally:
                temporal.unlink(missing_ok=True)

        def _puja_imatge_grafic(self, projecte):
            """Rep una imatge per a un gràfic: la captura de la web (la canvia) o una foto més del ventall."""
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
                if g["tipus"] == "ventall" and len(g["punts"]) >= grafics.MAX_PUNTS:
                    return self._json({"error": f"Hi caben {grafics.MAX_PUNTS} fotos com a molt"}, HTTPStatus.BAD_REQUEST)
                with tempfile.TemporaryDirectory() as temporal:
                    fitxer = Path(temporal) / f"imatge{Path(nom).suffix.lower()}"
                    fitxer.write_bytes(contingut)
                    nom_imatge = projecte.importa_imatge(fitxer)
                if g["tipus"] == "web":
                    g["imatge"] = nom_imatge
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
    apagats = estat.get("sons_apagats") if isinstance(estat.get("sons_apagats"), list) else []
    estat["sons_apagats"] = sorted({c for c in apagats if isinstance(c, str) and 0 < len(c) <= 60})[:500]
    for clau in ("mantingudes", "pauses_mantingudes"):
        estat[clau] = [int(i) for i in (estat[clau] or [])]
    return estat
