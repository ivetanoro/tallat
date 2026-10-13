"""Servidor local de la pàgina de revisió. Només escolta a 127.0.0.1: res no surt de l'ordinador."""
from __future__ import annotations

import json
import mimetypes
import subprocess
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from motor import edicio, exporta
from motor.projecte import EXPORTS, PROXY, Projecte

PAGINA = Path(__file__).resolve().parent.parent / "pagina"


class Feina:
    """Un sol render alhora, en segon pla, amb el seu progrés."""

    def __init__(self):
        self.bloqueig = threading.Lock()
        self.estat = None

    def info(self) -> dict | None:
        with self.bloqueig:
            return dict(self.estat) if self.estat else None

    def comença(self, projecte: Projecte, qualitat: str) -> bool:
        with self.bloqueig:
            if self.estat and self.estat["estat"] == "treballant":
                return False
            self.estat = {"estat": "treballant", "qualitat": qualitat, "progres": 0, "fitxer": None, "error": None}
        threading.Thread(target=self._fes, args=(projecte, qualitat), daemon=True).start()
        return True

    def _actualitza(self, **canvis):
        with self.bloqueig:
            self.estat.update(canvis)

    def _fes(self, projecte: Projecte, qualitat: str) -> None:
        try:
            sortida = projecte.sortida(qualitat)
            trams = projecte.trams()
            exporta.exporta(projecte.video, trams, sortida, qualitat,
                            progres=lambda pct: self._actualitza(progres=pct))
            projecte.desa_talls(sortida, trams)
            self._actualitza(estat="fet", progres=100, fitxer=sortida.name)
        except Exception as e:  # el missatge arriba a la pàgina
            traceback.print_exc()
            self._actualitza(estat="error", error=str(e))


def crea_servidor(projecte: Projecte, port: int) -> ThreadingHTTPServer:
    feina = Feina()
    bloqueig = threading.Lock()

    def instantania() -> dict:
        trams = projecte.trams()
        return {"estat": _estat_json(projecte.estat), "trams": trams,
                "durada_final": round(sum(b - a for a, b in trams), 3)}

    class Gestor(BaseHTTPRequestHandler):
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
            mida = path.stat().st_size
            tipus = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            rang = self.headers.get("Range")
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
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(final - inici + 1))
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
                pass  # el navegador ha tallat la descàrrega (passa sovint en saltar pel vídeo)

        def _index(self):
            html = (PAGINA / "index.html").read_text(encoding="utf-8")
            for nom in ("app.js", "estil.css"):
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
            return json.loads(self.rfile.read(n) or b"{}")

        # --- rutes ---
        def do_GET(self):
            ruta = unquote(urlparse(self.path).path)
            if ruta == "/":
                return self._index()
            if ruta.startswith("/pagina/"):
                return self._segur(PAGINA, ruta[len("/pagina/"):])
            if ruta == "/proxy.mp4":
                return self._fitxer(projecte.carpeta / PROXY)
            if ruta.startswith("/exports/"):
                return self._segur(projecte.carpeta / EXPORTS, ruta[len("/exports/"):])
            if ruta == "/api/projecte":
                with bloqueig:
                    info = exporta.info_video(projecte.video) if projecte.video.exists() else {}
                    return self._json({
                        "nom": projecte.nom, "durada": projecte.dades["durada"], "fps": projecte.fps,
                        "font": projecte.dades.get("font"), "origen": info,
                        "paraules": projecte.dades["paraules"],
                        "paragrafs": [[p["id"] for p in g] for g in edicio.paragrafs(projecte.dades["paraules"])],
                        "notes": projecte.notes(), "exports": projecte.exports(), "feina": feina.info(),
                        **instantania()})
            if ruta == "/api/feina":
                return self._json({"feina": feina.info(), "exports": projecte.exports()})
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self):
            ruta = urlparse(self.path).path
            try:
                cos = self._cos()
            except json.JSONDecodeError:
                return self._json({"error": "JSON no vàlid"}, HTTPStatus.BAD_REQUEST)
            with bloqueig:
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
                if ruta == "/api/notes":
                    projecte.desa_notes(cos.get("notes", []))
                    return self._json({"notes": projecte.notes()})
                if ruta == "/api/registre":  # què fa el reproductor al navegador (per trobar errors)
                    with (projecte.carpeta / "registre-pagina.log").open("a", encoding="utf-8") as f:
                        for e in cos.get("events", [])[:500]:
                            f.write(json.dumps(e, ensure_ascii=False) + "\n")
                    return self._json({"ok": True})
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

        def _segur(self, arrel: Path, relatiu: str):
            path = (arrel / relatiu).resolve()
            if arrel.resolve() not in path.parents:
                return self.send_error(HTTPStatus.FORBIDDEN)
            return self._fitxer(path)

    return ThreadingHTTPServer(("127.0.0.1", port), Gestor)


def _estat_json(estat: dict) -> dict:
    sortida = dict(estat)
    for clau in ("esborrades", "propostes", "correccions"):
        sortida[clau] = {str(k): v for k, v in estat[clau].items()}
    return sortida


def _estat_de_json(cos: dict) -> dict:
    estat = edicio.estat_buit()
    estat.update({k: v for k, v in cos.items() if k in estat})
    for clau in ("esborrades", "propostes", "correccions"):
        estat[clau] = {int(k): v for k, v in (estat[clau] or {}).items()}
    for clau in ("mantingudes", "pauses_mantingudes"):
        estat[clau] = [int(i) for i in (estat[clau] or [])]
    return estat
