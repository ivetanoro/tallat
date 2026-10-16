"""El pla de gràfics: els que Claude proposa frase a frase i la persona revisa a la pàgina.

Cada gràfic es desa a l'estat de l'edició (`estat["grafics"]`), lligat a una paraula de la
transcripció: si es mouen els talls, el gràfic segueix la seva frase.

  {"id": "g3", "tipus": "frase", "paraula": 120, "fins": 131, "durada": null,
   "text": "no és mandra, és *cansament*", "punts": [], "estil": "mac", "posicio": "dalt",
   "amaga_subtitols": null, "motiu": "la idea central", "estat": "proposat", "nota": ""}

Tipus (tots de text: no cal cap fitxer):
  frase     una frase clau en gran (*entre asteriscs*, la part destacada); amaga els subtítols
  etiqueta  una paraula o dues en una etiqueta petita («mite», «pas 1»)
  llista    una targeta amb uns quants punts, que surten un a un (cadascun quan es diu); amaga els
            subtítols i va a baix, al seu lloc
  crida     la crida a l'acció del final (si no té text, la de la marca)

L'estil de cada gràfic (net, mac, scrapbook o editorial) és un dels de la marca. Estats:
proposat (el veus al vídeo), mantingut (t'agrada: Claude no el toca), canvia (amb una nota per
a Claude) i tret (no surt, però es guarda perquè Claude no el torni a proposar).
"""
from __future__ import annotations

import math
import re
import subprocess
import tempfile
from pathlib import Path

TIPUS = ("frase", "etiqueta", "llista", "crida")
NOMS = {"frase": "Frase", "etiqueta": "Etiqueta", "llista": "Llista", "crida": "Crida"}
ESTILS = ("net", "mac", "scrapbook", "editorial")
POSICIONS = ("dalt", "mig", "baix")  # o un número de 0 (dalt) a 1 (baix): on va el centre del gràfic
# La zona segura d'Instagram (i TikTok) en un vídeo de 1080 × 1920: el 14 % de dalt i el 35 % de baix
# queden tapats pel nom, el text i els botons. Els gràfics no en surten mai (ni tapen els subtítols).
ALCADA = 1920
ZONA_SEGURA = (0.14, 0.65)
MARGE_SUBTITOLS = 28  # px entre un gràfic i els subtítols
ESTATS = ("proposat", "mantingut", "canvia", "tret")
DURADES = {"frase": 2.8, "etiqueta": 2.2, "llista": 4.5, "crida": 3.5}
# On va cada tipus si no es diu: en un vídeo de cap parlant, la cara sol omplir el mig.
POSICIO = {"frase": "dalt", "etiqueta": "dalt", "llista": "baix", "crida": "baix"}
AMAGA = {"frase": True, "llista": True, "etiqueta": False, "crida": False}  # els subtítols, mentre surten
MIDA_TEXT = {"frase": 140, "etiqueta": 40, "llista": 80, "crida": 90}
DENSITAT = {"pocs": "un cada 8-12 s", "normal": "un cada 4-6 s", "molts": "un cada 2-4 s"}  # com la marca
MAX_PUNTS = 6
MIDA_PUNT = 80
MIDA_NOTA = 600
MINIM = 0.8         # segons: cap gràfic dura menys
ENTRADA_PUNT = 0.35  # quan surt el primer punt d'una llista sense paraules (després de la targeta)
FI_DE_FRASE = re.compile(r"[.?!…]['\"»”]*$")
PAUSA_FRASE = 0.7    # un silenci així també tanca una frase
CAMPS = ("id", "tipus", "paraula", "fins", "durada", "text", "punts", "estil", "posicio", "amaga_subtitols",
         "motiu", "estat", "nota")


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
    if tipus in ("frase", "etiqueta") and not sortida["text"]:
        raise ValueError(f"Una {NOMS[tipus].lower()} necessita «text»")
    punts = []
    if tipus == "llista":
        for p in g.get("punts") or []:
            p = p if isinstance(p, dict) else {"text": p}
            text = _text(p.get("text"), "punts", MIDA_PUNT)
            if text:
                paraula = _enter(p.get("paraula"), "punts.paraula")
                if paraules is not None and paraula is not None and paraula >= paraules:
                    raise ValueError(f"No hi ha cap paraula amb el número {paraula}")
                punts.append({"text": text, "paraula": paraula})
        if not punts:
            raise ValueError("Una llista necessita «punts»: [\"un\", \"dos\"…]")
    sortida["punts"] = punts[:MAX_PUNTS]
    sortida["estil"] = g.get("estil") if g.get("estil") in ESTILS else None
    posicio = g.get("posicio")
    if isinstance(posicio, (int, float)) and not isinstance(posicio, bool):
        sortida["posicio"] = round(min(1.0, max(0.0, float(posicio))), 3)
    else:
        sortida["posicio"] = posicio if posicio in POSICIONS else None
    amaga = g.get("amaga_subtitols")
    sortida["amaga_subtitols"] = amaga if isinstance(amaga, bool) else None
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
    actuals = [] if manera == "de-nou" else neteja_llista(actuals, paraules)
    per_id = {g["id"]: g for g in actuals}
    ids = set(per_id)
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

def temps_paraules(blocs: list[list[dict]], al_muntatge) -> tuple[dict, dict]:
    """Per a cada paraula: on comença al muntatge la primera que es queda a partir d'ella (dins del
    seu bloc), i on acaba al muntatge l'última que es queda fins a ella. {id: segons}."""
    inicis, finals = {}, {}
    for bloc in blocs:
        seguent = None
        for p in reversed(bloc):
            if p["conservada"]:
                m = al_muntatge(p["inici"])
                seguent = m if m is not None else seguent
            if seguent is not None:
                inicis[p["id"]] = seguent
        darrer = None
        for p in bloc:
            if p["conservada"]:
                m = al_muntatge(p["inici"])
                if m is not None:
                    darrer = m + max(0.0, p["final"] - p["inici"])
            if darrer is not None:
                finals[p["id"]] = darrer
    return inicis, finals


def limits(subtitols: dict | None, amaga: bool) -> list[int]:
    """Entre quines alçades (px) pot anar un gràfic: dins la zona segura i sense tapar els subtítols.
    Si el gràfic amaga els subtítols, pot ocupar el seu lloc (si s'hi veuen els subtítols, s'hi veu el
    gràfic): els de baix fan baixar el límit de baix fins on acaben. Si no, el gràfic s'hi queda a
    sobre (o a sota, si els subtítols són a dalt)."""
    dalt, baix = ZONA_SEGURA[0] * ALCADA, ZONA_SEGURA[1] * ALCADA
    if subtitols:
        y = float(subtitols.get("posicio_y", 0.7)) * ALCADA
        mitja = float(subtitols.get("mida", 0.075)) * 1080 * 0.75  # mitja línia, més o menys
        if y >= ALCADA / 2:
            baix = max(baix, min(y + mitja, 0.8 * ALCADA)) if amaga else min(baix, y - mitja - MARGE_SUBTITOLS)
        elif not amaga:
            dalt = max(dalt, y + mitja + MARGE_SUBTITOLS)
    return [round(dalt), round(max(baix, dalt + 200))]


def situa(grafics: list[dict], inicis: dict, finals: dict, total: float, estils: list[str],
          crida: str = "", subtitols: dict | None = None) -> list[dict]:
    """Els gràfics que surten al vídeo (no els trets), a punt per dibuixar, en temps del muntatge:
    [{id, tipus, inici, final, text, punts: [{text, t}], estil, posicio, amaga_subtitols, limits}].
    Els que són d'una frase que ja no surt al vídeo no hi són. Una crida sense text diu la de la marca.
    `subtitols`: l'estil dels subtítols, si el vídeo en porta (perquè els gràfics no els tapin)."""
    estil_marca = next((e for e in estils if e in ESTILS), "net")
    llista = []
    for g in grafics:
        text = g["text"] or (crida.strip()[:MIDA_TEXT["crida"]] if g["tipus"] == "crida" else "")
        if g.get("estat") == "tret" or not (text or g["punts"]):
            continue
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
        if g.get("fins") is not None and g["fins"] in finals and finals[g["fins"]] > inici:
            final = finals[g["fins"]] + 0.3
        final = round(min(total, max(inici + MINIM, final)), 3)
        punts = []
        if g["tipus"] == "llista":
            n = len(g["punts"])
            pas = min(0.7, max(0.2, (final - inici - 0.8) / max(1, n)))
            for k, p in enumerate(g["punts"]):
                t = inicis.get(p["paraula"]) if p.get("paraula") is not None else None
                t = inici + ENTRADA_PUNT + k * pas if t is None else t
                punts.append({"text": p["text"], "t": round(min(max(t, inici + 0.15), final - 0.3), 3)})
        amaga = AMAGA[g["tipus"]] if g.get("amaga_subtitols") is None else g["amaga_subtitols"]
        posicio = g.get("posicio")
        llista.append({"id": g["id"], "tipus": g["tipus"], "inici": round(inici, 3), "final": final,
                       "text": text, "punts": punts, "estil": g.get("estil") or estil_marca,
                       "posicio": POSICIO[g["tipus"]] if posicio is None else posicio,
                       "amaga_subtitols": amaga, "limits": limits(subtitols, amaga)})
    return _sense_trepitjar(sorted(llista, key=lambda g: g["inici"]))


def _sense_trepitjar(llista: list[dict]) -> list[dict]:
    """Si dos gràfics surten alhora al mateix lloc, el segon passa a un lloc lliure (si n'hi ha).
    Els que porten un lloc exacte (un número) es deixen on són."""
    ocupats: list[dict] = []
    for g in llista:
        ocupats = [o for o in ocupats if o["final"] > g["inici"]]
        if isinstance(g["posicio"], str) and any(o["posicio"] == g["posicio"] for o in ocupats):
            lliure = next((p for p in POSICIONS if all(o["posicio"] != p for o in ocupats)), None)
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
            "lletra_accent": m.get("lletra_accent") or sub.get("clau_font") or lletra_titols}


def families(p: dict) -> set[str]:
    return {p["lletra_titols"], p["lletra_text"], p["lletra_accent"]}


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
