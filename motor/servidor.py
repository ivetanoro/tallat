"""Servidor local de la pàgina de revisió. Només escolta a 127.0.0.1: res no surt de l'ordinador."""
from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import secrets
import subprocess
import sys
import threading
import traceback
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from motor import broll, edicio, editors, exporta, gust, marca, muntatge, stickers
from motor.projecte import EXPORTS, PROXY, Projecte

PAGINA = Path(__file__).resolve().parent.parent / "pagina"
MIDA_MAXIMA_FONT = 20 * 1024 * 1024  # una font no passa mai d'uns quants MB
MIDA_MAXIMA_JSON = 10 * 1024 * 1024  # l'estat d'un projecte llarg no arriba ni a 1 MB
MIDA_MAXIMA_PUJADA = 2 * 1024 ** 3   # un b-roll o un sticker
# Les peticions que canvien el projecte obert: han de dir a quin projecte van (dues pestanyes).
RUTES_DEL_PROJECTE = {"/api/estat", "/api/neteja", "/api/notes", "/api/instruccio", "/api/broll/biblioteca",
                      "/api/broll/treu", "/api/broll/puja", "/api/mostra", "/api/exporta", "/api/editors",
                      "/api/marca", "/api/marca/restableix", "/api/marca/font", "/api/marca/lletra",
                      "/api/kit/tria", "/api/kit/nou",
                      "/api/kit/nom", "/api/kit/per-defecte", "/api/kit/esborra", "/api/kit/importa"}
RUTES_DE_FITXER = {"/api/broll/puja", "/api/marca/font", "/api/kit/importa"}  # el cos és el fitxer mateix


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
                          "fitxer": None, "error": None}
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
                self._actualitza(estat="fet", progres=100, fitxer=carpeta.name)
                return
            sortida = projecte.sortida(qualitat)
            trams = projecte.trams()
            self._actualitza(fase="subtitols")
            capa = projecte.capa_subtitols(trams, qualitat)
            self._actualitza(fase="video", progres=0)
            exporta.exporta(projecte.font(qualitat), trams, sortida, qualitat,
                            progres=lambda pct: self._actualitza(progres=pct), capa=capa,
                            zooms=projecte.zooms_per_tram(trams), brolls=projecte.brolls(trams))
            projecte.desa_talls(sortida, trams)
            self._actualitza(estat="fet", progres=100, fitxer=sortida.name)
        except Exception as e:  # el missatge arriba a la pàgina
            traceback.print_exc()
            self._actualitza(estat="error", error=str(e))


def _arrel_de(projecte: Projecte) -> Projecte:
    """Si el projecte és un reel (reels/<id>/ dins d'una gravació), la gravació sencera."""
    if (projecte.carpeta / muntatge.REEL).exists() and projecte.carpeta.parent.name == muntatge.CARPETA_REELS:
        return Projecte(projecte.carpeta.parent.parent)
    return projecte


def crea_servidor(inicial: Projecte, port: int) -> ThreadingHTTPServer:
    feina = Feina()
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
        return {"estat": _estat_json(projecte.estat), "trams": trams,
                "durada_final": round(sum(b - a for a, b in trams), 3),
                "zooms": projecte.zooms_per_tram(trams), "zoom": exporta.ZOOM,
                "instruccions": projecte.instruccions(),
                "brolls": [{"id": b["id"], "inici": b["inici"], "durada": b["durada"],
                            "url": "/broll/" + b["fitxer"].name + f"?v={int(b['fitxer'].stat().st_mtime)}"}
                           for b in projecte.brolls(trams)],
                "stickers": [{"id": st["id"], "inici": st["inici"], "durada": st["durada"],
                              "url": "/stickers/" + st["fitxer"].name + f"?v={int(st['fitxer'].stat().st_mtime)}"}
                             for st in projecte.stickers(trams)],
                "subtitols": projecte.linies_subtitols(trams),
                "paragrafs": projecte.paragrafs()}

    def versio_estil(projecte) -> str:
        """Canvia quan canvia el kit del vídeo o el seu fitxer (o les seves lletres)."""
        kit = projecte.kit()
        carpeta = marca.ruta(kit).parent
        fitxers = [carpeta / marca.FITXER_KIT, carpeta / "fonts"]
        return f"{kit}:" + ":".join(str(f.stat().st_mtime_ns) if f.exists() else "-" for f in fitxers)

    def info_marca() -> dict:
        kit = obert["p"].kit()
        estil = obert["p"].estil_subtitols()
        fonts = [{"familia": f["familia"], "pes": f["pes"],
                  "url": f"/marca/fonts/{quote(f['fitxer'].name)}?v={int(f['fitxer'].stat().st_mtime)}"}
                 for f in marca.fonts_del_kit(kit) if f["fitxer"].parent == marca.ruta(kit).parent / "fonts"]
        return {"estil_subtitols": estil, "fitxer_estil": str(marca.ruta(kit)),
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
                return self._fitxer(projecte.carpeta / PROXY)
            if ruta.startswith("/broll/"):
                return self._segur(projecte.carpeta_instruccions() / broll.CARPETA, ruta[len("/broll/"):])
            if ruta.startswith("/stickers/"):
                return self._segur(projecte.carpeta_instruccions() / stickers.CARPETA, ruta[len("/stickers/"):])
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
                        "notes": projecte.notes(), "exports": projecte.exports(), "feina": feina.info(),
                        "estil_stickers": projecte.estil().get("stickers", {}),
                        "gust": gust.llegeix(), "seccions_gust": gust.SECCIONS,
                        **info_marca(),
                        **info_reels(),
                        **instantania()})
            if ruta == "/api/feina":
                return self._json({"feina": feina.info(), "exports": projecte.exports()})
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
                if ruta == "/api/neteja":
                    projecte.neteja()
                    projecte.estat["revisio"] = projecte.estat.get("revisio", 0) + 1
                    projecte.desa()
                    return self._json(instantania())
                if ruta == "/api/notes":  # d'una en una: dues pestanyes no es trepitgen les notes
                    if isinstance(cos.get("afegeix"), dict):
                        projecte.afegeix_nota(cos["afegeix"])
                    elif cos.get("esborra") is not None:
                        projecte.esborra_nota(cos["esborra"])
                    return self._json({"notes": projecte.notes()})
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
                if ruta in ("/api/marca", "/api/marca/restableix"):  # l'estil dels subtítols, al kit d'aquest vídeo
                    try:
                        if ruta.endswith("restableix"):
                            marca.restableix("subtitols", kit=projecte.kit())
                        else:
                            marca.desa("subtitols", cos.get("subtitols") or {}, kit=projecte.kit())
                    except ValueError as e:
                        return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                    return self._json({**info_marca(), **instantania()})
                if ruta == "/api/marca/lletra":  # una lletra de la biblioteca (es baixa al kit el primer cop)
                    try:
                        marca.baixa_lletra(str(cos.get("id", "")), kit=projecte.kit())
                    except KeyError:
                        return self._json({"error": "No conec aquesta lletra"}, HTTPStatus.NOT_FOUND)
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
                        return self._json({"error": "No trobo aquest kit"}, HTTPStatus.NOT_FOUND)
                    except ValueError as e:
                        return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                    return self._json({**info_marca(), **instantania()})
                if ruta == "/api/gust":  # una regla nova escrita a la pàgina (o una nota que es vol recordar)
                    try:
                        gust.afegeix(cos.get("seccio") or "altres", cos.get("text", ""))
                    except ValueError as e:
                        return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                    return self._json({"gust": gust.llegeix()})
                if ruta == "/api/gust/treu":
                    try:
                        _, desfet = gust.treu(int(cos.get("id")))
                    except (KeyError, TypeError, ValueError):
                        return self._json({"error": "No trobo aquesta regla"}, HTTPStatus.NOT_FOUND)
                    # Si la regla tenia un ajust (p. ex. la mida dels subtítols), ha tornat a com estava.
                    return self._json({"gust": gust.llegeix(), "desfet": desfet, **info_marca(), **instantania()})
                if ruta == "/api/editors":  # projecte per acabar-lo en un altre editor
                    if not feina.comença(projecte, "editors", capa=bool(cos.get("capa")),
                                         trossos=bool(cos.get("trossos"))):
                        return self._json({"error": "Ja hi ha un render en marxa"}, HTTPStatus.CONFLICT)
                    return self._json({"feina": feina.info()})
                if ruta == "/api/mostra":  # obre el Finder amb el fitxer seleccionat
                    path = (projecte.carpeta / EXPORTS / cos.get("nom", "")).resolve()
                    if path.parent != (projecte.carpeta / EXPORTS).resolve() or not path.exists():
                        return self._json({"error": "No trobo aquest fitxer"}, HTTPStatus.NOT_FOUND)
                    subprocess.run(["open", "-R", str(path)], check=False)
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
                return self._no_permesa(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "El kit és buit o massa gran")
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
    for clau in ("mantingudes", "pauses_mantingudes"):
        estat[clau] = [int(i) for i in (estat[clau] or [])]
    return estat
