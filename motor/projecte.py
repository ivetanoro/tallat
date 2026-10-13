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

from motor import edicio, neteja

TRANSCRIPCIO = "transcripcio.json"
EDICIO = "edicio.json"
EDICIO_TEXT = "edicio.txt"  # format de la fase 1: s'importa un cop
ORIGINAL = "original.txt"
REVISIO = "revisio.txt"
NOTES = "notes.json"
PROXY = "proxy.mp4"
EXPORTS = "exports"

MOTIUS = {"usuari": "tretes per tu", "farciment": "farciment", "tall": "paraules a mig dir"}
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

    def trams(self) -> list[tuple[float, float]]:
        return edicio.trams(self.paraules(), self.fps, self.dades["durada"],
                            pausa_maxima=self.estat.get("pausa_maxima"),
                            pauses_mantingudes=self.estat.get("pauses_mantingudes", []))

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
