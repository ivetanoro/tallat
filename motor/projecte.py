"""Un projecte de tallat: una carpeta (fora del repositori) amb tota la feina d'un vídeo.

  transcripcio.json   paraules amb els seus temps (no es toca després de transcriure)
  edicio.json         què es treu, què es proposa, correccions i pauses
  original.txt        el text sencer, per consultar
  revisio.txt         el text amb [tret] i {proposat}
  proxy.mp4           còpia lleugera per a la pàgina de revisió
  kit-triat.json      el kit d'estil d'aquest vídeo, si no és el per defecte
  exports/            vídeos exportats
"""
from __future__ import annotations

import bisect
import json
import time
from collections import Counter
from fractions import Fraction
from pathlib import Path

from motor import broll, edicio, grafics, instruccions, marca, neteja, so, stickers, subtitols, targetes

TRANSCRIPCIO = "transcripcio.json"
EDICIO = "edicio.json"
EDICIO_TEXT = "edicio.txt"  # format de la fase 1: s'importa un cop
ORIGINAL = "original.txt"
REVISIO = "revisio.txt"
PROXY = "proxy.mp4"
EXPORTS = "exports"
KIT_TRIAT = "kit-triat.json"

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
        self._versio_al_disc = self._versio_estat()

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
            estat = edicio.llegeix_estat(self.carpeta / EDICIO)
            # El pla de gràfics també el pot escriure algú a mà: el que no s'entén no ha de trencar res.
            estat["grafics"] = grafics.neteja_llista(estat.get("grafics"))
            return estat
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
        self._versio_al_disc = self._versio_estat()

    def _versio_estat(self):
        try:
            return (self.carpeta / EDICIO).stat().st_mtime_ns
        except OSError:
            return None

    def al_dia(self) -> bool:
        """Si algú altre ha canviat edicio.json (Claude, amb una ordre, mentre la pàgina és oberta),
        el torna a llegir. La revisió puja: la pàgina, en desar, veurà que hi ha canvis més nous."""
        versio = self._versio_estat()
        if versio is None or versio == self._versio_al_disc:
            return False
        revisio = self.estat.get("revisio", 0)
        self.estat = self._carrega_estat()
        self.estat["revisio"] = max(self.estat.get("revisio", 0), revisio) + 1
        self._versio_al_disc = versio
        return True

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

    # --- Kit d'estil --------------------------------------------------------------

    def kit(self) -> str:
        """El kit d'estil d'aquest vídeo: el triat aquí; en un reel que no en té cap de triat, el de la
        gravació sencera; i si no, el kit per defecte (també si el triat ja no existeix)."""
        arrel = (self.carpeta / TRANSCRIPCIO).resolve().parent  # en un reel, la gravació sencera
        for carpeta in (self.carpeta, arrel):
            try:
                triat = json.loads((carpeta / KIT_TRIAT).read_text(encoding="utf-8")).get("kit")
            except (OSError, json.JSONDecodeError, AttributeError):
                continue
            if triat:
                return marca.resol(triat)
        return marca.kit_per_defecte()

    def tria_kit(self, kit: str) -> None:
        if marca.resol(kit) != kit:
            raise KeyError(kit)
        (self.carpeta / KIT_TRIAT).write_text(json.dumps({"kit": kit}) + "\n", encoding="utf-8")

    def estil(self) -> dict:
        """L'estil sencer del kit d'aquest vídeo (subtítols, b-roll, stickers i talls)."""
        return marca.carrega(kit=self.kit())

    def estil_subtitols(self) -> dict:
        return self.estil()["subtitols"]

    def fonts_subtitols(self) -> list[dict]:
        """Les lletres del kit que fan servir els subtítols, el títol i els gràfics d'aquest vídeo."""
        estil = self.estil()
        fonts = marca.fonts_de(estil["subtitols"], kit=self.kit(), titol=estil.get("titol"))
        if self.estat.get("grafics"):
            families = grafics.families(grafics.paleta(estil))
            fonts += [f for f in marca.fonts_del_kit(self.kit()) if f["familia"] in families and f not in fonts]
        return fonts

    def titol(self, trams=None) -> dict | None:
        """El títol del ganxo, a punt per dibuixar: {text, inici, final} en temps del muntatge (o None)."""
        titol = edicio.titol_net(self.estat.get("titol"))
        if not titol:
            return None
        trams = trams if trams is not None else self.trams()
        total = sum(b - a for a, b in trams)
        if total <= 0:
            return None
        durada = titol["durada"] or float(self.estil().get("titol", {}).get("durada", 3.0))
        return {"text": titol["text"], "inici": 0.0, "final": round(min(total, durada), 3)}

    def _per_dibuixar(self, linies=None) -> tuple[dict, dict | None, float | None]:
        """La marca del kit, l'estil dels subtítols (si el vídeo en porta) i l'alçada del seu bloc més alt."""
        estil = self.estil()
        sub = estil["subtitols"] if self.estat.get("subtitols", True) else None
        if sub and linies is None and sub.get("disposicio") in ("apilat", "escampat"):
            linies = self.linies_subtitols()
        return estil.get("marca") or {}, sub, grafics.alcada_subtitols(sub, linies) if sub else None

    def grafics(self, trams=None, linies=None) -> list[dict]:
        """Els gràfics del pla que surten al vídeo, en temps del muntatge (motor/grafics.py). Qui ja té
        les línies dels subtítols les pot passar (si són apilades, se n'ha de saber l'alçada)."""
        pla = self.estat.get("grafics")
        if not pla:
            return []
        trams = trams if trams is not None else self.trams()
        inicis, finals, bloc_de = grafics.temps_paraules(self._blocs(), mapa_muntatge(trams))
        marca_kit, sub, alcada = self._per_dibuixar(linies)
        return grafics.situa(pla, inicis, finals, sum(b - a for a, b in trams), marca_kit.get("energia"),
                             marca_kit.get("crida") or "", sub, bloc_de, alcada)

    def dibuixos_grafics(self, linies=None) -> dict:
        """Com es dibuixa cada gràfic del pla, també els trets i els que ara no surten (per a les
        miniatures de la pàgina): {id: dibuix}."""
        if not self.estat.get("grafics"):
            return {}
        marca_kit, sub, alcada = self._per_dibuixar(linies)
        dibuixos = {g["id"]: grafics.dibuix(g, marca_kit.get("energia"), marca_kit.get("crida") or "", sub, alcada)
                    for g in self.estat["grafics"]}
        return {k: v for k, v in dibuixos.items() if v}

    def frases(self, trams=None) -> list[dict]:
        """Les frases del vídeo tal com sonen ara (per fer el pla de gràfics)."""
        trams = trams if trams is not None else self.trams()
        return grafics.frases(self._blocs(), mapa_muntatge(trams))

    def _blocs(self) -> list[list[dict]]:
        return edicio._blocs(self.paraules(), self.estat.get("ordre"))

    def linies_subtitols(self, trams=None) -> list[dict]:
        return subtitols.grups(self.paraules(), trams if trams is not None else self.trams(),
                               self.estil_subtitols())

    def capa_subtitols(self, trams, qualitat: str, avis=None) -> Path | None:
        """Capa transparent amb els subtítols (si estan activats), el títol, els gràfics i els stickers;
        None si no n'hi ha cap."""
        linies = self.linies_subtitols(trams) if self.estat.get("subtitols", True) else []
        enganxines = self.stickers(trams)
        titol = self.titol(trams)
        situats = self.grafics(trams, linies)
        if not linies and not enganxines and not titol and not situats:
            return None
        estil = self.estil()
        return subtitols.renderitza(linies, estil["subtitols"], sum(b - a for a, b in trams),
                                    self.carpeta, qualitat, avis, stickers=enganxines,
                                    estil_stickers=estil.get("stickers", {}), fonts=self.fonts_subtitols(),
                                    titol=titol, estil_titol=estil.get("titol"),
                                    grafics=situats, paleta=grafics.paleta(estil))

    # --- So --------------------------------------------------------------------

    def estil_so(self) -> dict:
        return self.estil().get("so", {})

    def neteja_veu(self) -> str | None:
        """El nivell de la neteja de la veu (suau, mitja o fort), o None si està apagada."""
        e = self.estil_so()
        return (e.get("soroll") or "suau") if e.get("neteja", True) else None

    def efectes(self, trams, brolls=None, stickers=None, titol=False, linies=None, situats=None) -> list[dict]:
        """Els efectes de so d'aquest vídeo (motor/so.py), amb «actiu» false els que s'han apagat.
        Qui ja té calculats els b-rolls, els stickers, el títol, les línies o els gràfics els pot passar."""
        estil = self.estil()
        quants = estil.get("so", {}).get("efectes", "pocs")
        if quants == "cap":
            return []
        if titol is False:
            titol = self.titol(trams)
        if not self.estat.get("subtitols", True) or quants != "molts":
            linies = []  # les línies només compten per als «molts»
        elif linies is None:
            linies = self.linies_subtitols(trams)
        llista = so.esdeveniments(self.brolls(trams) if brolls is None else brolls,
                                  self.stickers(trams) if stickers is None else stickers, titol,
                                  estil.get("titol", {}).get("animacio", "puja"), linies, quants,
                                  self.grafics(trams) if situats is None else situats)
        apagats = set(self.estat.get("sons_apagats") or [])
        return [dict(x, actiu=x["clau"] not in apagats) for x in llista]

    def pista_efectes(self, trams, efectes=None) -> Path | None:
        """La pista amb els efectes actius (es refà només si canvia), o None si no n'hi ha cap."""
        actius = [x for x in (self.efectes(trams) if efectes is None else efectes) if x["actiu"]]
        if not actius:
            return None
        durada = sum(b - a for a, b in trams)
        volum = float(self.estil_so().get("volum_efectes", 0.5))
        carpeta = self.carpeta / "so"
        desti = carpeta / f"efectes-{so.empremta(actius, durada, volum)}.wav"
        if not desti.exists():
            so.pista(actius, durada, volum, desti)
            # Es guarden les tres més noves: un export que ja ha començat pot estar fent servir l'anterior.
            _poda(carpeta, "efectes-*.wav", guarda=3)
        return desti

    def mostres_veu(self) -> dict:
        """Deu segons de la veu, abans i després de la neteja (per escoltar-los a la pàgina)."""
        trams = self.trams()
        inici = trams[0][0] if trams else 0.0
        nivell = self.estil_so().get("soroll") or "suau"
        carpeta = self.carpeta / "so"
        abans = carpeta / f"veu-abans-{inici:.1f}.m4a"
        despres = carpeta / f"veu-neta-{nivell}-{inici:.1f}.m4a"
        if not abans.exists():
            _poda(carpeta, "veu-abans-*.m4a")
            so.mostra(self.video, inici, abans, None)
        if not despres.exists():
            _poda(carpeta, "veu-neta-*.m4a")
            so.mostra(self.video, inici, despres, nivell)
        return {"abans": abans, "despres": despres}

    def opcions_so(self, trams) -> dict:
        """El que necessita l'export: la neteja de la veu i la pista d'efectes."""
        return {"neteja": self.neteja_veu(), "efectes": self.pista_efectes(trams)}

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
        self.estat = instruccions.aplica_decisio(self.estat, ins)
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
        estil = self.estil().get("broll", {})
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
        d = float(durada or ins.get("durada") or self.estil().get("stickers", {}).get("durada", 2.0))
        copia = stickers.copia(origen, base, iid)
        ins.update(fitxer=str(copia.relative_to(base)), durada=d, estat="acceptada", tipus="sticker")
        instruccions.desa(base, llista)
        stickers.retira_anteriors(copia)
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

    def al_original(self, m: float, trams) -> float | None:
        """Temps del muntatge → temps del vídeo original (None si el muntatge no dura tant)."""
        acum = 0.0
        for a, b in trams:
            if m < acum + (b - a):
                return a + max(0.0, m - acum)
            acum += b - a
        return None

    def al_muntatge(self, t: float, trams) -> float | None:
        """Temps del vídeo original → temps del muntatge (si cau en un tall, l'inici del tros següent)."""
        return mapa_muntatge(trams)(t)

    def stickers(self, trams) -> list[dict]:
        return self._recursos(trams, "sticker")

    def brolls(self, trams) -> list[dict]:
        """Els b-rolls al muntatge, amb on van a la pantalla i com entren (motor/targetes.py)."""
        estil = self.estil()
        sub = estil.get("subtitols", {})
        accent = sub.get("clau_color") or sub.get("color_actiu") or "#FFFFFF"
        return targetes.disposa(self._recursos(trams, "broll"), estil.get("broll", {}), accent)

    def _recursos(self, trams, tipus: str) -> list[dict]:
        """B-rolls o stickers acceptats amb fitxer, situats al muntatge: [{id, fitxer, inici, durada}]."""
        base = self.carpeta_instruccions()
        total = sum(b - a for a, b in trams)
        # Cada paraula, amb el bloc on sona (en un reel, cada tros triat de la gravació és un bloc).
        bloc_de = {p["id"]: bloc for bloc in self._blocs() for p in bloc}
        resultat = []
        for ins in self.instruccions():
            if ins.get("tipus") != tipus or ins.get("estat") != "acceptada" or not ins.get("fitxer"):
                continue
            if ins.get("ancora") is None or not (base / ins["fitxer"]).exists():
                continue
            # Comença a la primera paraula que es queda a partir de l'àncora, dins del mateix bloc:
            # si l'àncora és d'un tros que aquest reel no fa servir, el recurs no hi va.
            bloc = bloc_de.get(ins["ancora"])
            if bloc is None:
                continue
            seguent = next((p for p in bloc if p["id"] >= ins["ancora"] and p["conservada"]), None)
            m = self.al_muntatge(seguent["inici"], trams) if seguent else None
            if m is None or m >= total - 0.1:
                continue
            resultat.append({"id": ins["id"], "fitxer": base / ins["fitxer"], "inici": round(m, 3),
                             "durada": round(min(float(ins.get("durada", 1.5)), total - m), 3)})
        return resultat

    def zooms_per_tram(self, trams) -> list[bool]:
        """Quins trossos porten zoom: el que comença amb la paraula que ve després de la instrucció."""
        # Els de l'estat i els de les instruccions de zoom acceptades: les instruccions són compartides
        # entre la gravació i els seus reels, i acceptar-ne una en un lloc també val per als altres.
        ids = set(self.estat.get("zooms", [])) | {
            i["ancora"] for i in self.instruccions()
            if i.get("tipus") == "zoom" and i.get("estat") == "acceptada" and i.get("ancora") is not None}
        ancores = [self.dades["paraules"][i] for i in sorted(ids) if 0 <= i < len(self.dades["paraules"])]
        return [any(a - 0.05 <= p["inici"] < b for p in ancores) for a, b in trams]

    def neteja(self) -> None:
        treure, proposar = neteja.detecta(self.dades["paraules"], neteja.carrega_llista())
        self.estat = edicio.aplica_neteja(self.estat, treure, proposar)

    # --- Exports ---------------------------------------------------------

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
        """Desa els talls de cada versió exportada (per marcar-los al reproductor i per situar-hi un moment)."""
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


def mapa_muntatge(trams):
    """Una funció temps del vídeo original → temps del muntatge per a moltes crides seguides (cada
    paraula d'una gravació llarga): es busca el tros amb una cerca binària. Si el temps cau en un tall,
    l'inici del tros següent; si va més enllà de tot, None."""
    acum, ordenats = 0.0, []
    for k, (a, b) in enumerate(trams):
        ordenats.append((a, b, acum, k))
        acum += b - a
    ordenats.sort()
    inicis = [a for a, _, _, _ in ordenats]

    def mapa(t: float) -> float | None:
        j = bisect.bisect_right(inicis, t + 0.01)  # els trossos que comencen fins a t (+10 ms)
        # Al voltant d'un tall, dos trossos poden tocar t: mana el que sona abans (com sempre).
        candidats = [o for o in ordenats[max(0, j - 2):j] if o[0] - 0.01 <= t < o[1]]
        if candidats:
            a, _, posicio, _ = min(candidats, key=lambda o: o[3])
            return posicio + max(0.0, t - a)
        seguent = next((o for o in ordenats[j - 1 if j else 0:] if o[0] > t), None)
        return seguent[2] if seguent else None
    return mapa


def _poda(carpeta: Path, patro: str, guarda: int = 0) -> None:
    """Esborra els fitxers fets per tallat que ja no calen (en guarda els `guarda` més nous)."""
    if not carpeta.is_dir():
        return
    for vell in sorted(carpeta.glob(patro), key=lambda f: f.stat().st_mtime, reverse=True)[guarda:]:
        vell.unlink(missing_ok=True)
