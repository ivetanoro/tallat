"""El pla de gràfics: els que Claude proposa frase a frase i la persona revisa a la pàgina.

Cada gràfic es desa a l'estat de l'edició (`estat["grafics"]`), lligat a una paraula de la
transcripció: si es mouen els talls, el gràfic segueix la seva frase.

  {"id": "g3", "tipus": "frase", "paraula": 120, "fins": 131, "durada": null,
   "text": "no és mandra, és *cansament*", "punts": [], "estil": "mac", "posicio": "dalt",
   "amaga_subtitols": null, "motiu": "la idea central", "estat": "proposat", "nota": ""}

Tipus:
  frase        una frase clau en gran (*entre asteriscs*, la part destacada); amaga els subtítols
  etiqueta     una paraula o dues en una etiqueta petita («mite», «pas 1»)
  llista       una targeta amb uns quants punts, que surten un a un (cadascun quan es diu); amaga els
               subtítols i va a baix, al seu lloc
  crida        la crida a l'acció del final (si no té text, la de la marca)
  notificacio  una notificació del mòbil: qui l'envia («de») i el missatge («text»)
  xat          una conversa: els «punts» són els missatges (rebuts o enviats, «costat»), que surten
               un a un; amaga els subtítols
  numero       una xifra que compta des de zero («xifra»: «73 %», «10.000 €»), amb un text a sota
  anotacio     una nota escrita a mà amb un cercle, un subratllat o una fletxa («forma») que es dibuixa
  web          una captura de pantalla dins d'una finestra de navegador («imatge»; «text»: l'adreça que
               surt a la barra), que baixa a poc a poc si la captura és llarga; amaga els subtítols
  ventall      unes quantes fotos obertes en ventall (els «punts», cadascun amb la seva «imatge» i, si
               es vol, un peu de foto a «text»), que surten una a una; «text»: un títol; amaga els subtítols

Les imatges (de la web i del ventall) es desen al projecte, a CARPETA_IMATGES, amb un nom fet del seu
contingut. Al pla, «imatge» és aquest nom (o, quan Claude envia el pla, el camí d'un fitxer, que tallat
copia al projecte). Mentre no tenen imatge, la web i el ventall no surten al vídeo.

Amb `bloc: true` (per defecte, a la web i al ventall), mentre surt el gràfic el fons es fa d'un color de la marca, el vídeo es fa petit (amb
una animació suau) dins d'una targeta a baix, on s'hi continua veient la cara, i el gràfic té tot l'espai
de dalt.

L'estil de cada gràfic (net, mac, scrapbook o editorial) és un dels de la marca. Estats:
proposat (el veus al vídeo), mantingut (t'agrada: Claude no el toca), canvia (amb una nota per
a Claude) i tret (no surt, però es guarda perquè Claude no el torni a proposar).
"""
from __future__ import annotations

import glob
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

TIPUS = ("frase", "etiqueta", "llista", "crida", "notificacio", "xat", "numero", "anotacio", "web", "ventall")
NOMS = {"frase": "Frase", "etiqueta": "Etiqueta", "llista": "Llista", "crida": "Crida",
        "notificacio": "Notificació", "xat": "Xat", "numero": "Número", "anotacio": "Anotació",
        "web": "Web", "ventall": "Fotos"}
AMB_PUNTS = ("llista", "xat", "ventall")  # els que tenen punts que surten un a un
AMB_IMATGE = ("web", "ventall")
BLOC_PER_DEFECTE = ("web", "ventall")  # els grans: amb el bloc de color si no es diu el contrari
CARPETA_IMATGES = "imatges-grafics"  # dins del projecte
FORMATS_IMATGE = (".png", ".jpg", ".jpeg", ".webp", ".gif")
NOM_IMATGE = re.compile(r"[A-Za-z0-9_-]{1,80}\.(?:png|jpe?g|webp|gif)")  # el nom d'una imatge ja copiada
FORMES = ("cercle", "subratllat", "fletxa")  # de l'anotació
COSTATS = ("esquerra", "dreta")
ESTILS = ("net", "mac", "scrapbook", "editorial")
POSICIONS = ("dalt", "mig", "baix")  # o un número de 0 (dalt) a 1 (baix): on va el centre del gràfic
# La zona segura d'Instagram (i TikTok) en un vídeo de 1080 × 1920: el 14 % de dalt i el 35 % de baix
# queden tapats pel nom, el text i els botons. Els gràfics no en surten mai (ni tapen els subtítols).
ALCADA = 1920
ZONA_SEGURA = (0.14, 0.65)
MARGE_SUBTITOLS = 28  # px entre un gràfic i els subtítols
ESTATS = ("proposat", "mantingut", "canvia", "tret")
DURADES = {"frase": 2.8, "etiqueta": 2.2, "llista": 4.5, "crida": 3.5, "notificacio": 3.0, "xat": 5.0,
           "numero": 2.8, "anotacio": 2.5, "web": 4.0, "ventall": 4.5}
# On va cada tipus si no es diu: en un vídeo de cap parlant, la cara sol omplir el mig.
POSICIO = {"frase": "dalt", "etiqueta": "dalt", "llista": "baix", "crida": "baix", "notificacio": "dalt",
           "xat": "baix", "numero": "dalt", "anotacio": "mig", "web": "mig", "ventall": "mig"}
# Els que amaguen els subtítols mentre surten (el que hi diu és el que se sent).
AMAGA = {"frase": True, "llista": True, "etiqueta": False, "crida": False, "notificacio": False, "xat": True,
         "numero": False, "anotacio": False, "web": True, "ventall": True}
MIDA_TEXT = {"frase": 140, "etiqueta": 40, "llista": 80, "crida": 90, "notificacio": 120, "xat": 30,
             "numero": 60, "anotacio": 40, "web": 60, "ventall": 60}
MIDA_PEU = 30  # el peu de cada foto del ventall
CAL_TEXT = ("frase", "etiqueta", "notificacio", "anotacio")
XIFRA = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?")  # «10.000», «2,5», «73»
DENSITAT = {"pocs": "un cada 8-12 s", "normal": "un cada 4-6 s", "molts": "un cada 2-4 s"}  # com la marca
MAX_PUNTS = 6
MIDA_PUNT = 80
MIDA_NOTA = 600
MINIM = 0.8         # segons: cap gràfic dura menys
ENTRADA_PUNT = 0.35  # quan surt el primer punt d'una llista sense paraules (després de la targeta)
FI_DE_FRASE = re.compile(r"[.?!…]['\"»”]*$")
PAUSA_FRASE = 0.7    # un silenci així també tanca una frase
CAMPS = ("id", "tipus", "paraula", "fins", "durada", "text", "punts", "de", "xifra", "forma", "costat", "imatge",
         "estil", "posicio", "amaga_subtitols", "bloc", "motiu", "estat", "nota")
# El bloc de color, en px de 1080 × 1920: la targeta on va el vídeo (4:5, a baix i centrada) i el tros del
# vídeo que s'hi veu (de dalt, on sol haver-hi la cara). El vídeo s'hi encongeix i en torna a sortir en
# ANIMACIO_BLOC segons. La mateixa geometria a l'export (motor/exporta.py) i a la pàgina (app.js).
BLOC = {"x": 151, "y": 838, "w": 778, "h": 972, "retall_y": 160}
ANIMACIO_BLOC = 0.45


def _enter(valor, nom: str) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or int(valor) != valor or valor < 0:
        raise ValueError(f"«{nom}» ha de ser el número d'una paraula")
    return int(valor)


def _text(valor, nom: str, mida: int, retalla: bool = False) -> str:
    """Un text en una línia. Si és massa llarg: es retalla (les notes) o no s'accepta (el que es veu al vídeo)."""
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise ValueError(f"«{nom}» ha de ser un text")
    text = " ".join(valor.replace("\r", "").split())
    if len(text) > mida and not retalla:
        raise ValueError(f"«{nom}» és massa llarg: com a molt {mida} lletres («{text[:30]}…»)")
    return text[:mida]


def _imatge(valor) -> str:
    """El nom d'una imatge del projecte o, al pla que envia Claude, el camí d'un fitxer."""
    if valor is None:
        return ""
    if not isinstance(valor, str) or len(valor) > 500:
        raise ValueError("«imatge» ha de ser el camí d'una imatge")
    return valor.strip()


def imatge_valida(nom, imatges=None) -> bool:
    """Si `nom` és una imatge ja copiada al projecte (i, si es diu quines hi ha, que hi sigui)."""
    return isinstance(nom, str) and bool(NOM_IMATGE.fullmatch(nom)) and (imatges is None or nom in imatges)


def net(g: dict, paraules: int | None = None) -> dict:
    """Un gràfic comprovat (llança ValueError, en català, si no s'entén). `paraules`: quantes en té
    la transcripció, per comprovar que les paraules hi són."""
    if not isinstance(g, dict):
        raise ValueError("Cada gràfic ha de ser un objecte JSON")
    tipus = g.get("tipus")
    if tipus not in TIPUS:
        raise ValueError(f"Tipus de gràfic desconegut: «{tipus}» (n'hi ha de {', '.join(TIPUS)})")
    sortida = {"id": str(g["id"])[:20] if g.get("id") not in (None, "") else None, "tipus": tipus}
    sortida["paraula"] = _enter(g.get("paraula"), "paraula")
    sortida["fins"] = _enter(g.get("fins"), "fins")
    for clau in ("paraula", "fins"):
        if paraules is not None and sortida[clau] is not None and sortida[clau] >= paraules:
            raise ValueError(f"No hi ha cap paraula amb el número {sortida[clau]} (n'hi ha de 0 a {paraules - 1})")
    if sortida["paraula"] is None and tipus != "crida":
        raise ValueError(f"Al gràfic «{g.get('text') or tipus}» li falta «paraula»: on comença")
    if sortida["fins"] is not None and sortida["paraula"] is not None and sortida["fins"] < sortida["paraula"]:
        sortida["fins"] = None
    durada = g.get("durada")
    if durada is not None and (isinstance(durada, bool) or not isinstance(durada, (int, float))):
        raise ValueError("«durada» ha de ser un número de segons")
    sortida["durada"] = round(min(15.0, max(MINIM, float(durada))), 2) if durada is not None else None
    sortida["text"] = _text(g.get("text"), "text", MIDA_TEXT[tipus])
    if tipus in CAL_TEXT and not sortida["text"]:
        raise ValueError(f"Al gràfic {NOMS[tipus].lower()} li falta «text»")
    punts = []
    if tipus == "ventall":  # les fotos: cadascuna amb la seva imatge (un text sol és el camí de la imatge)
        for p in g.get("punts") or []:
            p = p if isinstance(p, dict) else {"imatge": p}
            imatge = _imatge(p.get("imatge"))
            if imatge:
                paraula = _enter(p.get("paraula"), "punts.paraula")
                if paraules is not None and paraula is not None and paraula >= paraules:
                    raise ValueError(f"No hi ha cap paraula amb el número {paraula}")
                punts.append({"imatge": imatge, "text": _text(p.get("text"), "punts.text", MIDA_PEU), "paraula": paraula})
    elif tipus in AMB_PUNTS:
        for k, p in enumerate(g.get("punts") or []):
            p = p if isinstance(p, dict) else {"text": p}
            text = _text(p.get("text"), "punts", MIDA_PUNT)
            if text:
                paraula = _enter(p.get("paraula"), "punts.paraula")
                if paraules is not None and paraula is not None and paraula >= paraules:
                    raise ValueError(f"No hi ha cap paraula amb el número {paraula}")
                punt = {"text": text, "paraula": paraula}
                if tipus == "xat":  # els missatges: rebuts (a l'esquerra) o enviats (a la dreta), per torns si no es diu
                    punt["costat"] = p.get("costat") if p.get("costat") in ("rebut", "enviat") else \
                        ("rebut" if k % 2 == 0 else "enviat")
                punts.append(punt)
        if not punts:
            raise ValueError(f"{'Una llista' if tipus == 'llista' else 'Un xat'} necessita «punts»: [\"un\", \"dos\"…]")
    sortida["punts"] = punts[:MAX_PUNTS]
    sortida["de"] = _text(g.get("de"), "de", 30) if tipus == "notificacio" else ""
    sortida["xifra"] = _text(g.get("xifra"), "xifra", 24) if tipus == "numero" else ""
    if tipus == "numero" and not XIFRA.search(sortida["xifra"]):
        raise ValueError("Un número necessita «xifra», amb un número a dins («73 %», «10.000 €», «3 de cada 4»)")
    sortida["forma"] = (g.get("forma") if g.get("forma") in FORMES else "fletxa") if tipus == "anotacio" else None
    sortida["costat"] = (g.get("costat") if g.get("costat") in COSTATS else "esquerra") if tipus == "anotacio" else None
    sortida["imatge"] = _imatge(g.get("imatge")) if tipus == "web" else ""
    sortida["estil"] = g.get("estil") if g.get("estil") in ESTILS else None
    posicio = g.get("posicio")
    if isinstance(posicio, (int, float)) and not isinstance(posicio, bool):
        sortida["posicio"] = round(min(1.0, max(0.0, float(posicio))), 3)
    else:
        sortida["posicio"] = posicio if posicio in POSICIONS else None
    amaga = g.get("amaga_subtitols")
    sortida["amaga_subtitols"] = amaga if isinstance(amaga, bool) else None
    bloc = g.get("bloc")
    sortida["bloc"] = bloc if isinstance(bloc, bool) else None  # None: el de cada tipus (BLOC_PER_DEFECTE)
    sortida["motiu"] = _text(g.get("motiu"), "motiu", 200, retalla=True)
    sortida["estat"] = g.get("estat") if g.get("estat") in ESTATS else "proposat"
    sortida["nota"] = _text(g.get("nota"), "nota", MIDA_NOTA, retalla=True)
    return sortida


def neteja_llista(llista, paraules: int | None = None) -> list[dict]:
    """La llista desada (o la que envia la pàgina), sense els gràfics que no s'entenen."""
    sortida, ids = [], set()
    for g in llista if isinstance(llista, list) else []:
        try:
            g = net(g, paraules)
        except ValueError:
            continue
        if not g["id"] or g["id"] in ids:
            g["id"] = _id_nou(ids)
        ids.add(g["id"])
        sortida.append(g)
    return sortida[:300]


def _id_nou(ids) -> str:
    n = max([int(i[1:]) for i in ids if re.fullmatch(r"g\d+", i)] + [0])
    return f"g{n + 1}"


def _contingut(g: dict) -> dict:
    return {k: g[k] for k in CAMPS if k not in ("id", "estat", "nota")}


MANERES = ("proposa", "canvia", "de-nou")


def fusiona(actuals: list[dict], pla: list, paraules: int | None = None, manera: str = "proposa") -> list[dict]:
    """Posa al dia el pla amb el que envia Claude.

    - Un gràfic amb l'«id» d'un que ja hi era el substitueix: torna a «proposat» i se'n treu la nota
      (Claude ja l'ha atès). Si no ha canviat res, es queda com estava.
    - Un gràfic sense «id» és nou.
    - Els que ja hi eren i no s'esmenten: amb «proposa» (un pla nou), els proposats se'n van i els
      mantinguts, els que tenen una nota pendent i els trets es queden; amb «canvia» (atendre les
      notes), es queden tots; amb «de-nou», no se'n queda cap."""
    if manera not in MANERES:
        raise ValueError(f"Manera desconeguda: {manera}")
    if not isinstance(pla, list):
        raise ValueError("El pla ha de ser una llista de gràfics: [{…}, {…}]")
    # Els que ja hi eren no es comproven amb les paraules d'ara: un gràfic que la persona ha mantingut
    # no s'ha de perdre perquè la transcripció hagi canviat (si la seva paraula ja no hi és, no surt).
    tots = neteja_llista(actuals)
    actuals = [] if manera == "de-nou" else tots
    per_id = {g["id"]: g for g in actuals}
    # Un id no es torna a fer servir (tampoc el dels que se'n van): els sons apagats van per id.
    ids = {g["id"] for g in tots}
    nous, tocats = [], set()
    for k, g in enumerate(pla):
        try:
            g = net(g, paraules)
        except ValueError as e:
            raise ValueError(f"Gràfic {k + 1} del pla: {e}") from None
        vell = per_id.get(g["id"])
        if vell is not None and g["id"] not in tocats:
            if _contingut(g) == _contingut(vell):
                g.update(estat=vell["estat"], nota=vell["nota"])
            else:
                g.update(estat="proposat", nota="")
            tocats.add(g["id"])
        else:
            g["id"] = _id_nou(ids)
            g.update(estat="proposat", nota="")
        ids.add(g["id"])
        nous.append(g)
    queden = [g for g in actuals if g["id"] not in tocats and (manera == "canvia" or g["estat"] != "proposat")]
    return sorted(queden + nous, key=lambda g: (g["paraula"] if g["paraula"] is not None else 10 ** 9, g["id"]))


# --- On van, al muntatge -------------------------------------------------------------------------

def temps_paraules(blocs: list[list[dict]], al_muntatge) -> tuple[dict, dict, dict]:
    """Per a cada paraula: on comença al muntatge la primera que es queda a partir d'ella (dins del
    seu bloc), on acaba al muntatge l'última que es queda fins a ella ({id: segons}) i el seu bloc
    ({id: número}: en un reel, els trossos de la gravació que sonen en un altre ordre)."""
    inicis, finals, bloc_de = {}, {}, {}
    for n, bloc in enumerate(blocs):
        temps = {p["id"]: al_muntatge(p["inici"]) for p in bloc if p["conservada"]}  # un sol cop per paraula
        seguent = None
        for p in reversed(bloc):
            bloc_de[p["id"]] = n
            if temps.get(p["id"]) is not None:
                seguent = temps[p["id"]]
            if seguent is not None:
                inicis[p["id"]] = seguent
        darrer = None
        for p in bloc:
            if temps.get(p["id"]) is not None:
                darrer = temps[p["id"]] + max(0.0, p["final"] - p["inici"])
            if darrer is not None:
                finals[p["id"]] = darrer
    return inicis, finals, bloc_de


def alcada_subtitols(estil: dict, linies: list[dict] | None) -> float:
    """Quant d'alt (px) pot fer, com a molt, un bloc de subtítols: una línia, o les que s'apilen (apilat)
    o les files curtes del collage (escampat) de la frase més llarga d'aquest vídeo."""
    linia = float(estil.get("mida", 0.075)) * 1080 * float(estil.get("interlineat", 1.12))
    if estil.get("clau_grans"):
        linia *= 1 + (float(estil.get("clau_mida", 1.4)) - 1) / 2  # les destacades, més altes
    disposicio = estil.get("disposicio")
    if disposicio not in ("apilat", "escampat") or not linies:
        return linia
    per_bloc: dict = {}
    for l in linies:
        per_bloc.setdefault(l.get("bloc"), []).append(l)
    if disposicio == "apilat":
        files = max(len(b) for b in per_bloc.values())
        files = min(files, int(estil.get("linies_max", 4)))
    else:  # files de dues paraules, més o menys (pagina/subtitols.js, filesEscampades)
        files = max(math.ceil(sum(len(l["paraules"]) for l in b) / 2) for b in per_bloc.values())
    return linia * max(1, files)


def limits(subtitols: dict | None, amaga: bool, alcada: float | None = None) -> list[int]:
    """Entre quines alçades (px) pot anar un gràfic: dins la zona segura i sense tapar els subtítols.
    Si el gràfic amaga els subtítols, pot ocupar el seu lloc (si s'hi veuen els subtítols, s'hi veu el
    gràfic): els de baix fan baixar el límit de baix fins on acaben. Si no, el gràfic s'hi queda a
    sobre (o a sota, si els subtítols són a dalt). `alcada`: la del bloc de subtítols més alt
    (alcada_subtitols); si no se sap, una línia."""
    dalt, baix = ZONA_SEGURA[0] * ALCADA, ZONA_SEGURA[1] * ALCADA
    if subtitols:
        f = float(subtitols.get("posicio_y", 0.7))
        y = f * ALCADA
        h = alcada or alcada_subtitols(subtitols, None)
        # Com a pagina/subtitols.js: una línia va centrada a `posicio_y`; un bloc apilat o escampat hi
        # queda penjat per la mateixa proporció (a baix creix cap amunt, a dalt cap avall).
        sobre, sota = (f * h, (1 - f) * h) if subtitols.get("disposicio") in ("apilat", "escampat") else (h / 2, h / 2)
        if y >= ALCADA / 2:
            baix = max(baix, min(y + sota, 0.8 * ALCADA)) if amaga else min(baix, y - sobre - MARGE_SUBTITOLS)
        elif not amaga:
            dalt = max(dalt, y + sota + MARGE_SUBTITOLS)
    return [round(dalt), round(max(baix, dalt + 200))]


def _punts_visibles(g: dict, imatges) -> list[dict]:
    """Els punts que es veuen: al ventall, només les fotos que ja són al projecte."""
    if g["tipus"] != "ventall":
        return g["punts"]
    return [p for p in g["punts"] if imatge_valida(p.get("imatge"), imatges)]


def dibuix(g: dict, estils, crida: str = "", subtitols: dict | None = None, alcada: float | None = None,
           imatges=None, sense_bloc: bool = False) -> dict | None:
    """El que cal per dibuixar un gràfic, sense els temps: {id, tipus, nom, text, punts, estil, posicio,
    amaga_subtitols, limits, i de, xifra, forma i costat o imatge}. None si no té res a dir (una crida
    sense text ni crida a la marca). La web i el ventall sense imatges porten `falta`: a la pàgina es
    veuen (per pujar-les-hi), però no surten al vídeo. `imatges`: els noms de les que hi ha al projecte
    (si no es diu, no es comprova). `sense_bloc`: com si cap no en portés (per als altres editors, que no
    tenen el bloc de color). També el fa servir la pàgina per a les miniatures (dels trets, per exemple)."""
    estils = [estils] if isinstance(estils, str) else (estils or [])  # els kits d'abans: un sol estil
    text = g["text"] or (crida.strip()[:MIDA_TEXT["crida"]] if g["tipus"] == "crida" else "")
    if g["tipus"] not in AMB_IMATGE and not (text or g["punts"] or g.get("xifra")):
        return None
    # Amb el bloc de color, el gràfic fa de diapositiva: per defecte, sense subtítols.
    bloc = False if sense_bloc else g["tipus"] in BLOC_PER_DEFECTE if g.get("bloc") is None else g["bloc"]
    amaga = (AMAGA[g["tipus"]] or bloc) if g.get("amaga_subtitols") is None else g["amaga_subtitols"]
    d = {"id": g["id"], "tipus": g["tipus"], "nom": NOMS[g["tipus"]], "text": text,
         "punts": [{c: v for c, v in p.items() if c != "paraula"} for p in _punts_visibles(g, imatges)],
         "estil": g.get("estil") or next((e for e in estils if e in ESTILS), "net"),
         "posicio": POSICIO[g["tipus"]] if g.get("posicio") is None else g["posicio"],
         "amaga_subtitols": amaga, "limits": limits(subtitols, amaga, alcada)}
    if bloc:
        # El fons: el principal sota les targetes clares (mac, scrapbook); el fosc sota el text clar.
        d["bloc"] = "principal" if d["estil"] in ("mac", "scrapbook") else "fosc"
        d["limits"] = [round(ZONA_SEGURA[0] * ALCADA), BLOC["y"] - 40]  # tot l'espai de sobre la targeta
        if g.get("posicio") is None:
            d["posicio"] = "mig"
    if g["tipus"] == "notificacio":
        d["de"] = g.get("de") or ""
    elif g["tipus"] == "numero":
        d["xifra"] = llegeix_xifra(g["xifra"])
    elif g["tipus"] == "anotacio":
        d.update(forma=g.get("forma") or "fletxa", costat=g.get("costat") or "esquerra")
    elif g["tipus"] == "web":
        d["imatge"] = g["imatge"] if imatge_valida(g.get("imatge"), imatges) else ""
    if g["tipus"] in AMB_IMATGE and not (d.get("imatge") or d["punts"]):
        d["falta"] = True
    return d


def situa(grafics: list[dict], inicis: dict, finals: dict, total: float, estils: list[str],
          crida: str = "", subtitols: dict | None = None, bloc_de: dict | None = None,
          alcada: float | None = None, imatges=None, sense_bloc: bool = False) -> list[dict]:
    """Els gràfics que surten al vídeo (no els trets), a punt per dibuixar, en temps del muntatge:
    el `dibuix` de cadascun amb `inici`, `final` i, als punts, `t`. Els que són d'una frase que ja no
    surt al vídeo no hi són. `subtitols`: l'estil dels subtítols, si el vídeo en porta (perquè els
    gràfics no els tapin), i `alcada`, la del seu bloc més alt. `bloc_de`: el bloc de cada paraula
    (temps_paraules): el final i els punts d'un gràfic han de ser del mateix bloc que el començament.
    `imatges`: les que hi ha al projecte (la web i el ventall sense imatge no surten)."""
    llista = []
    for g in grafics:
        situat = dibuix(g, estils, crida, subtitols, alcada, imatges, sense_bloc) if g.get("estat") != "tret" else None
        if situat is None or situat.get("falta"):
            continue
        mateix_bloc = (lambda p: bloc_de is None or g["paraula"] is None or
                       bloc_de.get(p) == bloc_de.get(g["paraula"]))
        durada = g.get("durada") or DURADES[g["tipus"]]
        if g["paraula"] is None:  # una crida sense lloc: al final del vídeo
            inici = max(0.0, total - durada)
        elif g["paraula"] in inicis:
            inici = inicis[g["paraula"]]
        else:
            continue
        if inici >= total - 0.3:
            continue
        final = inici + durada
        if g.get("fins") is not None and g["fins"] in finals and finals[g["fins"]] > inici and mateix_bloc(g["fins"]):
            final = finals[g["fins"]] + 0.3
        final = round(min(total, max(inici + MINIM, final)), 3)
        if g["tipus"] in AMB_PUNTS:
            n = len(situat["punts"])
            pas = min(0.9 if g["tipus"] == "xat" else 0.7, max(0.2, (final - inici - 0.8) / max(1, n)))
            for k, (p, punt) in enumerate(zip(_punts_visibles(g, imatges), situat["punts"])):
                paraula = p.get("paraula")
                t = inicis.get(paraula) if paraula is not None and mateix_bloc(paraula) else None
                t = inici + ENTRADA_PUNT + k * pas if t is None else t
                punt["t"] = round(min(max(t, inici + 0.15), final - 0.3), 3)
        situat.update(inici=round(inici, 3), final=final)
        llista.append(situat)
    return _dins_dels_blocs(_sense_trepitjar(sorted(llista, key=lambda g: g["inici"])))


def _dins_dels_blocs(llista: list[dict]) -> list[dict]:
    """Un gràfic sense bloc que surt mentre n'hi ha un amb bloc no ha de tapar el gràfic de dalt: va sobre
    la targeta del vídeo, a la part que no tapa Instagram."""
    blocs = [g for g in llista if g.get("bloc")]
    for g in llista:
        if not g.get("bloc") and any(b["inici"] < g["final"] and g["inici"] < b["final"] for b in blocs):
            g["limits"] = [BLOC["y"] + 30, round(ZONA_SEGURA[1] * ALCADA) - 20]
    return llista


def blocs(situats: list[dict], paleta: dict) -> list[dict]:
    """Els blocs de color del vídeo: [{inici, final, color}], en temps del muntatge. Si dos gràfics amb
    bloc surten seguits (o alhora), és un sol bloc: el vídeo no torna a créixer per encongir-se de nou."""
    sortida = []
    for g in sorted((g for g in situats if g.get("bloc")), key=lambda g: g["inici"]):
        if sortida and g["inici"] - sortida[-1]["final"] < 2 * ANIMACIO_BLOC:
            sortida[-1]["final"] = max(sortida[-1]["final"], g["final"])
        else:
            sortida.append({"inici": g["inici"], "final": g["final"], "color": paleta[g["bloc"]]})
    return sortida


def pas_bloc(t: float, inici: float, final: float) -> float:
    """Quant s'ha encongit el vídeo en el moment t (en temps del muntatge): 0 fora del bloc, 1 del tot.
    Entra i surt suau (smoothstep). La pàgina fa el mateix (app.js, pasBloc)."""
    d = min(ANIMACIO_BLOC, (final - inici) / 2)
    if d <= 0:
        return 0.0
    p = min(1.0, max(0.0, min((t - inici) / d, (final - t) / d)))
    return p * p * (3 - 2 * p)


def llegeix_xifra(xifra: str) -> dict:
    """«10.000 €» → {abans: "", valor: 10000, decimals: 0, despres: " €", milers: True}: el que compta
    el número i el que l'envolta (el primer número del text)."""
    m = XIFRA.search(xifra)
    enter, decimals = m.group(1), m.group(2) or ""
    return {"abans": xifra[:m.start()], "despres": xifra[m.end():], "milers": "." in enter,
            "valor": float(f"{enter.replace('.', '')}.{decimals or 0}"), "decimals": len(decimals)}


def _zona(posicio) -> str:
    """La zona (dalt, mig o baix) d'un lloc, també si és un número."""
    if isinstance(posicio, str):
        return posicio
    return "dalt" if posicio < 0.36 else "mig" if posicio < 0.56 else "baix"


def _sense_trepitjar(llista: list[dict]) -> list[dict]:
    """Si dos gràfics surten alhora al mateix lloc, el segon passa a un lloc lliure (si n'hi ha).
    Els que porten un lloc exacte (un número) es deixen on són, però els altres no s'hi posen."""
    ocupats: list[dict] = []
    for g in llista:
        ocupats = [o for o in ocupats if o["final"] > g["inici"]]
        if isinstance(g["posicio"], str) and any(_zona(o["posicio"]) == g["posicio"] for o in ocupats):
            lliure = next((p for p in POSICIONS if all(_zona(o["posicio"]) != p for o in ocupats)), None)
            if lliure:
                g["posicio"] = lliure
        ocupats.append(g)
    return llista


def frases(blocs: list[list[dict]], al_muntatge) -> list[dict]:
    """Les frases del vídeo tal com sonen, per fer el pla: [{paraula, fins, inici, final, text}]."""
    sortida = []
    for bloc in blocs:
        actual: list[tuple[dict, float]] = []

        def tanca():
            if actual:
                p0, m0 = actual[0]
                p1, m1 = actual[-1]
                sortida.append({"paraula": p0["id"], "fins": p1["id"], "inici": round(m0, 2),
                                "final": round(m1 + p1["final"] - p1["inici"], 2),
                                "text": " ".join(p.get("correccio", p["text"]) for p, _ in actual)})
            actual.clear()

        anterior = None
        for p in bloc:
            if not p["conservada"]:
                continue
            m = al_muntatge(p["inici"])
            if m is None:
                continue
            if anterior is not None and p["inici"] - anterior["final"] >= PAUSA_FRASE:
                tanca()
            actual.append((p, m))
            if FI_DE_FRASE.search(p["text"]):
                tanca()
            anterior = p
        tanca()
    return sorted(sortida, key=lambda f: f["inici"])


# --- Colors i lletres -----------------------------------------------------------------------------

def paleta(estil: dict) -> dict:
    """Els colors i les lletres dels gràfics, de la marca del kit (i, si no n'hi ha, dels subtítols)."""
    m = estil.get("marca") or {}
    sub = estil.get("subtitols") or {}
    titol = estil.get("titol") or {}
    destacat = m.get("color_destacat") or sub.get("clau_color") or sub.get("color_actiu") or "#FFD60A"
    principal = m.get("color_principal") or destacat
    lletra_text = m.get("lletra_text") or sub.get("font") or "system-ui"
    lletra_titols = m.get("lletra_titols") or titol.get("font") or lletra_text
    return {"text": m.get("color_text") or sub.get("color") or "#FFFFFF",
            "principal": principal, "destacat": destacat,
            "secundari": m.get("color_secundari") or principal,
            "clar": m.get("color_clar") or "#FFFFFF",
            "fosc": m.get("color_fosc") or sub.get("contorn") or "#111111",
            "lletra_titols": lletra_titols, "lletra_text": lletra_text,
            "lletra_accent": m.get("lletra_accent") or sub.get("clau_font") or lletra_titols,
            "lletra_ma": m.get("lletra_ma") or m.get("lletra_accent") or sub.get("clau_font") or lletra_titols,
            "majuscules_ma": bool(m.get("majuscules_ma")) and bool(m.get("lletra_ma"))}


def families(p: dict) -> set[str]:
    return {p["lletra_titols"], p["lletra_text"], p["lletra_accent"], p["lletra_ma"]}


# --- Perquè l'assistent vegi on van --------------------------------------------------------------

MINIATURA = (270, 480)  # una quarta part de 1080 × 1920
COLUMNES = 5


def full_de_fotogrames(video: Path, quadres: list[dict], desti: Path) -> Path:
    """Un sol PNG amb el fotograma de cada gràfic, en ordre (d'esquerra a dreta i de dalt a baix), amb
    la part que no poden fer servir enfosquida (la zona d'Instagram i els subtítols).
    `quadres`: [{t: segon del vídeo original, limits: [dalt, baix] en px}]. Perquè l'assistent hi
    miri on hi ha la cara i el que no s'ha de tapar."""
    w, h = MINIATURA
    escala = h / ALCADA
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        files = math.ceil(len(quadres) / COLUMNES)
        for k in range(files * COLUMNES):
            sortida = tmp / f"q{k:03d}.png"
            if k >= len(quadres):  # per omplir l'última fila
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c=white:s={w}x{h}",
                                "-frames:v", "1", str(sortida)], check=True)
                continue
            dalt, baix = (round(x * escala) for x in quadres[k]["limits"])
            filtre = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                      f"drawbox=x=0:y=0:w={w}:h={dalt}:color=black@0.6:t=fill,"
                      f"drawbox=x=0:y={baix}:w={w}:h={h - baix}:color=black@0.6:t=fill,"
                      f"drawbox=x={round(120 * escala)}:y={dalt}:w={round(840 * escala)}:h={baix - dalt}:color=yellow@0.8:t=2")
            subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{quadres[k]['t']:.3f}", "-i", str(video),
                            "-frames:v", "1", "-vf", filtre, str(sortida)], check=True)
        desti.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", str(tmp / "q%03d.png"),
                        "-vf", f"tile={COLUMNES}x{files}:padding=8:margin=8:color=white", "-frames:v", "1",
                        str(desti)], check=True)
    return desti


# --- La captura d'una web (per al gràfic «web») ----------------------------------------------------

# El Chrome sense finestra que ja fa servir HyperFrames per dibuixar (o el Chrome o l'Edge de l'ordinador).
CHROMES = ("~/.cache/hyperframes/chrome/chrome-headless-shell/*/*/chrome-headless-shell",
           "~/.cache/hyperframes/chrome/chrome-headless-shell/*/*/chrome-headless-shell.exe",
           "~/.cache/puppeteer/chrome-headless-shell/*/*/chrome-headless-shell",
           "~/.cache/puppeteer/chrome-headless-shell/*/*/chrome-headless-shell.exe",
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "C:/Program Files/Google/Chrome/Application/chrome.exe",
           "~/AppData/Local/Google/Chrome/Application/chrome.exe",
           "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
MIDA_CAPTURA = (1280, 1950)  # com una pantalla d'ordinador, i una mica més de llarg perquè baixi


def troba_chrome() -> Path | None:
    for patro in CHROMES:
        patro = os.path.expanduser(patro)  # glob accepta camins absoluts a tots els sistemes (Path.glob no)
        trobats = [Path(p) for p in sorted(glob.glob(patro)) if Path(p).is_file()]
        if trobats:
            return trobats[-1]
    return None


def adreca_curta(url: str) -> str:
    """«https://www.elmeuweb.cat/curs/?ref=x» → «elmeuweb.cat/curs»: el que surt a la barra."""
    text = re.sub(r"^[a-z]+://", "", url.strip(), flags=re.I)
    text = re.sub(r"^www\.", "", text).split("?")[0].split("#")[0].rstrip("/")
    return text[:MIDA_TEXT["web"]]


def captura_web(url: str, desti: Path) -> Path:
    """Fa una captura de la web (la part de dalt, com es veu a l'ordinador) amb Chrome sense finestra."""
    if not re.match(r"^https?://", url.strip(), flags=re.I):
        url = "https://" + url.strip()
    chrome = troba_chrome()
    if chrome is None:
        raise RuntimeError("No trobo cap Chrome per fer la captura. Fes-la tu i puja-la a la pàgina.")
    desti.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as perfil:
        # Sense el clauer del Mac: així no demana cap contrasenya.
        r = subprocess.run([str(chrome), "--headless", "--use-mock-keychain", "--password-store=basic",
                            "--hide-scrollbars", "--no-first-run", "--disable-gpu", f"--user-data-dir={perfil}",
                            f"--window-size={MIDA_CAPTURA[0]},{MIDA_CAPTURA[1]}", "--virtual-time-budget=8000",
                            f"--screenshot={desti}", url], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    if not desti.is_file() or desti.stat().st_size == 0:
        raise RuntimeError(f"No he pogut fer la captura de {url}:\n{(r.stderr or r.stdout)[-500:]}")
    return desti
