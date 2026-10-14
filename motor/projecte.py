"""Un projecte de tallat: una carpeta (fora del repositori) amb tota la feina d'un vídeo.

  transcripcio.json   paraules amb els seus temps (no es toca després de transcriure)
  edicio.json         què es treu, què es proposa, correccions i pauses
  notes.json          notes en moments exactes de l'esborrany
  original.txt        el text sencer, per consultar
  revisio.txt         el text amb [tret] i {proposat}
  proxy.mp4           còpia lleugera per a la pàgina de revisió
  exports/            vídeos exportats
"""
from __future__ import annotations

import json
import time
from collections import Counter
from fractions import Fraction
from pathlib import Path

from motor import broll, edicio, instruccions, marca, neteja, stickers, subtitols

TRANSCRIPCIO = "transcripcio.json"
EDICIO = "edicio.json"
EDICIO_TEXT = "edicio.txt"  # format de la fase 1: s'importa un cop
ORIGINAL = "original.txt"
REVISIO = "revisio.txt"
NOTES = "notes.json"
PROXY = "proxy.mp4"
EXPORTS = "exports"

MOTIUS = {"usuari": "tretes per tu", "farciment": "farciment", "tall": "paraules a mig dir",
          "muntatge": "fora del reel", "instruccio": "instruccions de veu"}
PROPOSTES = {"farciment?": "possible farciment", "expressiu?": "sons repetits (potser expressius)",
             "repeticio?": "paraules repetides"}


def minuts(segons: float) -> str:
    return f"{int(segons // 60)} min {int(segons % 60):02d} s"


class Projecte:
    def __init__(self, carpeta: Path | str):
        self.carpeta = Path(carpeta).expanduser().resolve()
        self.avisos: list[str] = []
        self.dades = json.loads((self.carpeta / TRANSCRIPCIO).read_text(encoding="utf-8"))
        self.estat = self._carrega_estat()

    @property
    def nom(self) -> str:
        return self.carpeta.name

    @property
    def video(self) -> Path:
        return Path(self.dades["video"])

    @property
    def fps(self) -> float:
        return float(Fraction(self.dades["fps"]))

    def _carrega_estat(self) -> dict:
        if (self.carpeta / EDICIO).exists():
            return edicio.llegeix_estat(self.carpeta / EDICIO)
        if (self.carpeta / EDICIO_TEXT).exists():
            text = (self.carpeta / EDICIO_TEXT).read_text(encoding="utf-8")
            estat, self.avisos = edicio.importa_text(self.dades["paraules"], text)
            edicio.desa_estat(estat, self.carpeta / EDICIO)
            self.avisos.append(f"He passat la teva edició d'{EDICIO_TEXT} a {EDICIO} "
                               "(a partir d'ara es fa servir aquest).")
            return estat
        return edicio.estat_buit(marca.pausa_per_defecte())

    def desa(self) -> None:
        edicio.desa_estat(self.estat, self.carpeta / EDICIO)
        (self.carpeta / REVISIO).write_text(edicio.text_revisio(self.paraules()), encoding="utf-8")

    def paraules(self) -> list[dict]:
        return edicio.aplica(self.dades["paraules"], self.estat)

    def veu(self):
        """Mapa de veu del so (on hi ha silenci de debò). Es calcula un cop i el comparteixen
        la gravació sencera i els seus reels (es desa al costat de transcripcio.json)."""
        if not hasattr(self, "_veu"):
            from motor import veu
            try:
                self._veu = veu.carrega((self.carpeta / TRANSCRIPCIO).resolve().parent, self.video)
            except Exception:  # sense el vídeo o sense so: escurcem els silencis com abans
                self._veu = None
        return self._veu

    def trams(self) -> list[tuple[float, float]]:
        return edicio.trams(self.paraules(), self.fps, self.dades["durada"],
                            pausa_maxima=self.estat.get("pausa_maxima"),
                            pauses_mantingudes=self.estat.get("pauses_mantingudes", []),
                            ordre=self.estat.get("ordre"), veu=self.veu())

    def paragrafs(self) -> list[list[int]]:
        """Paràgrafs (ids) en l'ordre en què sonen; en un reel muntat, el que queda fora va al final."""
        paraules = self.dades["paraules"]
        ordre = self.estat.get("ordre")
        if not ordre:
            return [[p["id"] for p in g] for g in edicio.paragrafs(paraules)]
        resultat, dins = [], set()
        for a, b in ordre:
            bloc = paraules[int(a):int(b) + 1]
            dins.update(p["id"] for p in bloc)
            resultat += [[p["id"] for p in g] for g in edicio.paragrafs(bloc)]
        fora = [p for p in paraules if p["id"] not in dins]
        tros = []
        for p in fora:  # els trossos de fora, seguits, en ordre de gravació
            if tros and p["id"] != tros[-1]["id"] + 1:
                resultat += [[q["id"] for q in g] for g in edicio.paragrafs(tros)]
                tros = []
            tros.append(p)
        if tros:
            resultat += [[q["id"] for q in g] for g in edicio.paragrafs(tros)]
        return resultat

    def estil_subtitols(self) -> dict:
        return marca.carrega()["subtitols"]

    def linies_subtitols(self, trams=None) -> list[dict]:
        return subtitols.grups(self.paraules(), trams if trams is not None else self.trams(),
                               self.estil_subtitols())

    def capa_subtitols(self, trams, qualitat: str, avis=None) -> Path | None:
        """Capa transparent amb els subtítols (si estan activats) i els stickers; None si no n'hi ha cap."""
        linies = self.linies_subtitols(trams) if self.estat.get("subtitols", True) else []
        enganxines = self.stickers(trams)
        if not linies and not enganxines:
            return None
        return subtitols.renderitza(linies, self.estil_subtitols(), sum(b - a for a, b in trams),
                                    self.carpeta, qualitat, avis, stickers=enganxines,
                                    estil_stickers=marca.carrega().get("stickers", {}))

    # --- Instruccions de veu ------------------------------------------------------

    def instruccions(self) -> list[dict]:
        return instruccions.llegeix(self.carpeta)

    def detecta_instruccions(self) -> list[dict]:
        """Detecta les instruccions «Claude, …», les treu del vídeo i en desa les propostes."""
        noves = instruccions.fusiona(instruccions.detecta(self.dades["paraules"]), self.instruccions())
        instruccions.desa(self.carpeta, noves)
        self.estat = instruccions.aplica_a_estat(self.estat, noves)
        return noves

    def decideix_instruccio(self, iid: str, nou_estat: str) -> list[dict]:
        """Accepta o descarta una instrucció i n'aplica l'efecte («talla» i «zoom»)."""
        llista = self.instruccions()
        ins = next((i for i in llista if i["id"] == iid), None)
        if ins is None:
            raise KeyError(iid)
        ins["estat"] = nou_estat
        if ins["tipus"] == "talla" and ins.get("treure"):
            a, b = ins["treure"]
            for pid in range(a, b + 1):
                if nou_estat == "acceptada" and pid not in self.estat["esborrades"]:
                    self.estat["esborrades"][pid] = "instruccio"
                elif nou_estat != "acceptada" and self.estat["esborrades"].get(pid) == "instruccio":
                    del self.estat["esborrades"][pid]
        if ins["tipus"] == "zoom" and ins.get("ancora") is not None:
            zooms = set(self.estat.get("zooms", []))
            (zooms.add if nou_estat == "acceptada" else zooms.discard)(ins["ancora"])
            self.estat["zooms"] = sorted(zooms)
        instruccions.desa(self.carpeta, llista)
        return llista

    def carpeta_instruccions(self) -> Path:
        """On viuen instruccions.json i el b-roll: a la gravació sencera (els reels hi apunten)."""
        path = self.carpeta / instruccions.FITXER
        return path.resolve().parent if path.exists() else self.carpeta

    def afegeix_instruccio(self, tipus: str, paraula: int, text: str = "") -> dict:
        """Una instrucció afegida a mà en una paraula (no treu cap paraula del vídeo)."""
        llista = self.instruccions()
        p = self.dades["paraules"][paraula]
        n = sum(1 for i in llista if i["id"].startswith("m"))
        ins = {"id": f"m{paraula}-{n + 1}", "tipus": tipus, "text": text or tipus, "paraules": None,
               "inici": p["inici"], "final": p["inici"], "ancora": paraula, "estat": "acceptada", "manual": True}
        llista.append(ins)
        llista.sort(key=lambda i: i["inici"])
        instruccions.desa(self.carpeta_instruccions(), llista)
        return ins

    def assigna_broll(self, iid: str, origen: Path, durada: float | None = None) -> dict:
        """Prepara un fitxer (vídeo o imatge) com a b-roll d'una instrucció i l'hi assigna."""
        llista = self.instruccions()
        ins = next((i for i in llista if i["id"] == iid), None)
        if ins is None:
            raise KeyError(iid)
        base = self.carpeta_instruccions()
        estil = marca.carrega().get("broll", {})
        d = float(durada or ins.get("durada") or estil.get("durada", 1.5))
        original = broll.copia_original(Path(origen), base, iid)
        clip = broll.prepara(original, base / broll.CARPETA / f"{iid}.mp4", d, estil.get("lut"))
        ins.update(fitxer=str(clip.relative_to(base)), original=str(original.relative_to(base)),
                   durada=d, estat="acceptada", tipus="broll")
        instruccions.desa(base, llista)
        return ins

    def treu_broll(self, iid: str) -> None:
        """Treu el fitxer (b-roll o sticker) assignat a una instrucció."""
        llista = self.instruccions()
        for ins in llista:
            if ins["id"] == iid:
                ins.pop("fitxer", None)
        instruccions.desa(self.carpeta_instruccions(), llista)

    def assigna_sticker(self, iid: str, origen: Path, durada: float | None = None) -> dict:
        llista = self.instruccions()
        ins = next((i for i in llista if i["id"] == iid), None)
        if ins is None:
            raise KeyError(iid)
        origen = Path(origen).expanduser()
        if not stickers.es_compatible(origen):
            raise ValueError("Els stickers han de ser PNG, WebP, GIF o SVG (millor amb el fons transparent).")
        base = self.carpeta_instruccions()
        d = float(durada or ins.get("durada") or marca.carrega().get("stickers", {}).get("durada", 2.0))
        copia = stickers.copia(origen, base, iid)
        ins.update(fitxer=str(copia.relative_to(base)), durada=d, estat="acceptada", tipus="sticker")
        instruccions.desa(base, llista)
        return ins

    def assigna_recurs(self, iid: str, origen: Path, durada: float | None = None) -> dict:
        """B-roll o sticker, segons el tipus de la instrucció."""
        ins = next((i for i in self.instruccions() if i["id"] == iid), None)
        if ins is None:
            raise KeyError(iid)
        if ins["tipus"] == "sticker":
            return self.assigna_sticker(iid, origen, durada)
        return self.assigna_broll(iid, origen, durada)

    def suggereix_stickers(self) -> int:
        """Assigna sol el sticker de la biblioteca que surt al text de cada instrucció acceptada."""
        n = 0
        for ins in self.instruccions():
            if ins.get("tipus") == "sticker" and ins.get("estat") == "acceptada" and not ins.get("fitxer"):
                trobat = stickers.suggereix(ins.get("text", ""))
                if trobat:
                    self.assigna_sticker(ins["id"], trobat)
                    n += 1
        return n

    def al_muntatge(self, t: float, trams) -> float | None:
        """Temps del vídeo original → temps del muntatge (si cau en un tall, l'inici del tros següent)."""
        acum, posicions = 0.0, []
        for a, b in trams:
            posicions.append(acum)
            acum += b - a
        for k, (a, b) in enumerate(trams):
            if a - 0.01 <= t < b:
                return posicions[k] + max(0.0, t - a)
        seguents = [k for k, (a, _) in enumerate(trams) if a > t]
        return posicions[min(seguents, key=lambda k: trams[k][0])] if seguents else None

    def stickers(self, trams) -> list[dict]:
        return self._recursos(trams, "sticker")

    def brolls(self, trams) -> list[dict]:
        return self._recursos(trams, "broll")

    def _recursos(self, trams, tipus: str) -> list[dict]:
        """B-rolls o stickers acceptats amb fitxer, situats al muntatge: [{id, fitxer, inici, durada}]."""
        base = self.carpeta_instruccions()
        total = sum(b - a for a, b in trams)
        paraules = self.paraules()
        resultat = []
        for ins in self.instruccions():
            if ins.get("tipus") != tipus or ins.get("estat") != "acceptada" or not ins.get("fitxer"):
                continue
            if ins.get("ancora") is None or not (base / ins["fitxer"]).exists():
                continue
            # Comença a la primera paraula que es queda a partir de l'àncora.
            seguent = next((p for p in paraules[ins["ancora"]:] if p["conservada"]), None)
            m = self.al_muntatge(seguent["inici"], trams) if seguent else None
            if m is None or m >= total - 0.1:
                continue
            resultat.append({"id": ins["id"], "fitxer": base / ins["fitxer"], "inici": round(m, 3),
                             "durada": round(min(float(ins.get("durada", 1.5)), total - m), 3)})
        return resultat

    def zooms_per_tram(self, trams) -> list[bool]:
        """Quins trossos porten zoom: el que comença amb la paraula que ve després de la instrucció."""
        ancores = [self.dades["paraules"][i] for i in self.estat.get("zooms", [])
                   if 0 <= i < len(self.dades["paraules"])]
        return [any(a - 0.05 <= p["inici"] < b for p in ancores) for a, b in trams]

    def neteja(self) -> None:
        treure, proposar = neteja.detecta(self.dades["paraules"], neteja.carrega_llista())
        self.estat = edicio.aplica_neteja(self.estat, treure, proposar)

    # --- Notes i exports ---------------------------------------------------------

    def notes(self) -> list[dict]:
        path = self.carpeta / NOTES
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def desa_notes(self, notes: list[dict]) -> None:
        (self.carpeta / NOTES).write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")

    def exports(self) -> list[dict]:
        carpeta = self.carpeta / EXPORTS
        if not carpeta.exists():
            return []
        llista = []
        for f in sorted(carpeta.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True):
            qualitat = next((q for q in ("esborrany", "1080", "4k") if f"_{q}_" in f.name), "")
            llista.append({"nom": f.name, "qualitat": qualitat, "mida_mb": round(f.stat().st_size / 1e6, 1),
                           "data": time.strftime("%d/%m %H:%M", time.localtime(f.stat().st_mtime))})
        return llista

    def font(self, qualitat: str) -> Path:
        """Vídeo d'on es fa l'export. L'esborrany surt de la còpia lleugera (ja és vertical i
        petita): és molt més ràpid, sobretot amb vídeos d'iPhone (HEVC 4K)."""
        proxy = self.carpeta / PROXY
        if qualitat == "esborrany" and proxy.exists():
            return proxy
        return self.video

    def desa_talls(self, sortida: Path, trams: list) -> None:
        """Desa els talls de cada versió exportada, per poder situar-hi les notes."""
        sortida.with_suffix(".talls.json").write_text(json.dumps(trams), encoding="utf-8")

    def sortida(self, qualitat: str) -> Path:
        nom = self.video.stem.replace(" ", "-")
        return self.carpeta / EXPORTS / f"{nom}_{qualitat}_{time.strftime('%Y%m%d-%H%M%S')}.mp4"

    # --- Resum -------------------------------------------------------------------

    def resum(self) -> list[str]:
        paraules = self.paraules()
        trams = self.trams()
        linies = [f"Paraules: {sum(p['conservada'] for p in paraules)} es queden."]
        for motiu, n in Counter(p["motiu"] for p in paraules if not p["conservada"]).items():
            linies.append(f"  − {n} {MOTIUS.get(motiu, motiu)}")
        for motiu, n in Counter(self.estat["propostes"].values()).items():
            linies.append(f"  ? {n} {PROPOSTES.get(motiu, motiu)} (només proposat)")
        pausa = self.estat.get("pausa_maxima")
        linies.append(f"Silencis: {'escurçats a ' + str(pausa) + ' s com a màxim' if pausa else 'sense tocar'}.")
        linies.append(f"Durada: {minuts(self.dades['durada'])} → {minuts(sum(b - a for a, b in trams))} "
                      f"({len(trams)} trossos).")
        return linies
