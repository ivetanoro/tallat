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

from motor import edicio, instruccions, marca, neteja, subtitols

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
        return edicio.estat_buit()

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
        """Capa transparent amb els subtítols, o None si estan desactivats o no n'hi ha."""
        if not self.estat.get("subtitols", True):
            return None
        linies = self.linies_subtitols(trams)
        if not linies:
            return None
        return subtitols.renderitza(linies, self.estil_subtitols(), sum(b - a for a, b in trams),
                                    self.carpeta, qualitat, avis)

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
