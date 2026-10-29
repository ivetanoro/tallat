"""Les notes per a Claude: el que la persona demana des de la pàgina, i el que Claude hi respon.

Es desen a notes.json, a la carpeta de la gravació sencera (també les dels seus reels: així Claude les espera
totes d'un sol lloc): {"versio": n, "darrera": id, "notes": [...]}. `darrera` és el número més alt que s'ha donat
mai: si s'esborra l'última nota, la següent no torna a tenir el seu número (la pàgina recorda coses de cada nota
pel número, com la resposta a mig escriure). Hi escriuen dos processos
(el servidor de la pàgina i `tallat.py notes`, que fa servir Claude), i per això tot es llegeix i s'escriu
amb el fitxer bloquejat: el bloqueig del sistema (flock al Mac, msvcrt a Windows) sobre notes.json.bloqueig,
que s'allibera sol si el procés s'acaba (revisió de Codex: esborrar bloquejos «vells» deixava entrar dos processos).

Cada nota és una conversa: {id, estat, projecte, reel, paraula, inici, cita, fil: [{de: "persona" | "claude",
text, quan}]}. `projecte` és la carpeta que s'editava (la gravació o un reel; `reel`, el títol del reel).
Les que fa el botó «Demana la ronda següent» del tauler de Vesteix porten `tipus: "ronda"` i la ronda que hi havia (`ronda`).
Les de l'estació Revisa diuen també de quina versió són (`versio`: el nom de l'esborrany exportat), el segon
d'aquella versió (`t_versio`) i la miniatura del fotograma (`miniatura`, a la carpeta MINIATURES).
`paraula` i `inici` diuen on va (la paraula marcada i el segon de la gravació), o None si és per a tot el vídeo;
`cita` és el que es diu en aquell moment, perquè Claude ho entengui sense obrir res.
Estats: «esborrany» (a la pàgina, encara no enviada), «enviada» (Claude encara no l'ha agafada), «treballant»
(Claude l'ha agafada), «feta» (Claude hi ha respost) i «pregunta» (Claude pregunta alguna cosa: la resposta de
la persona hi torna a anar de seguida). En agafar-la, s'hi apunta quan (`agafada`), quants cops (`cops`) i quants
missatges ha vist Claude (`vistos`): si la persona n'hi afegeix mentre Claude hi treballa, la resposta de Claude
no la tanca, i li torna a arribar.

Quan Claude espera notes, ho diu a connexio.json cada pocs segons: així la pàgina pot dir «Connectat amb Claude».
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

FITXER = "notes.json"
MINIATURES = "notes-miniatures"
TOTES = object()    # a `envia`: les notes de qualsevol versió (i les que no en són de cap)
CONNEXIO = "connexio.json"
VIU = 15            # segons: si Claude no ha dit res en aquest temps, ja no hi és connectat
ESPERA_BLOQUEIG = 20  # segons: més, i és que alguna cosa ha anat malament
REAGAFA = 20 * 60   # segons: una nota agafada fa més temps i sense resposta es torna a donar (Claude es va aturar)
AGRUPA = 10         # segons: si la persona n'acaba d'enviar una, s'espera aquesta estona per si n'envia més (i van juntes)
ESTATS = ("esborrany", "enviada", "treballant", "feta", "pregunta")


def _intenta_bloquejar(f) -> bool:
    try:
        if os.name == "nt":
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _desbloqueja(f) -> None:
    if os.name == "nt":
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@contextmanager
def _bloquejat(carpeta: Path):
    # El fitxer del bloqueig es queda a la carpeta: el que bloqueja és tenir-lo obert i bloquejat, no que hi sigui.
    with open(Path(carpeta) / (FITXER + ".bloqueig"), "a+b") as f:
        t0 = time.time()
        while not _intenta_bloquejar(f):
            if time.time() - t0 > ESPERA_BLOQUEIG:
                raise TimeoutError("Les notes fa massa que estan bloquejades.")
            time.sleep(0.02)
        try:
            yield
        finally:
            _desbloqueja(f)


def _llegeix(carpeta: Path) -> dict:
    try:
        dades = json.loads((Path(carpeta) / FITXER).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"versio": 0, "darrera": 0, "notes": []}
    llista = list(dades.get("notes", []))
    darrera = max([int(dades.get("darrera", 0)), *(n["id"] for n in llista)])
    return {"versio": int(dades.get("versio", 0)), "darrera": darrera, "notes": llista}


def _substitueix(tmp: Path, path: Path) -> None:
    """os.replace, però a Windows pot fallar un moment si un altre procés (o l'antivirus) té el fitxer obert:
    s'hi torna uns quants cops abans de rendir-se."""
    for intent in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if intent == 19:
                raise
            time.sleep(0.05)


def _escriu(carpeta: Path, dades: dict) -> None:
    path = Path(carpeta) / FITXER
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dades, ensure_ascii=False, indent=1), encoding="utf-8")
    _substitueix(tmp, path)


def llegeix(carpeta: Path) -> dict:
    """{"versio": n, "notes": [...]}: la versió puja a cada canvi (la pàgina sap quan les ha de tornar a pintar)."""
    with _bloquejat(carpeta):
        return _llegeix(carpeta)


def _canvia(carpeta: Path, fn, tot: bool = False):
    """Aplica fn(notes) amb el fitxer bloquejat i desa; torna el que torni fn. Amb `tot`, fn(dades): també hi
    veu la darrera."""
    with _bloquejat(carpeta):
        dades = _llegeix(carpeta)
        resultat = fn(dades if tot else dades["notes"])
        dades["versio"] += 1
        dades["darrera"] = max([dades["darrera"], *(n["id"] for n in dades["notes"])])
        _escriu(carpeta, dades)
        return resultat


def _troba(notes: list[dict], id_: int) -> dict:
    for n in notes:
        if n["id"] == id_:
            return n
    raise KeyError(f"No hi ha cap nota {id_}.")


def _missatge(de: str, text: str) -> dict:
    text = str(text).strip()
    if not text:
        raise ValueError("La nota és buida.")
    return {"de": de, "text": text[:4000], "quan": round(time.time())}


def afegeix(carpeta: Path, text: str, paraula: int | None = None, inici: float | None = None,
            cita: str | None = None, projecte: str | None = None, reel: str | None = None,
            versio: str | None = None, t_versio: float | None = None, miniatura: str | None = None,
            tipus: str | None = None, ronda: int | None = None) -> dict:
    """Una nota nova, encara per enviar. Les de la ronda porten la ronda que hi havia en demanar-la (`ronda`): la
    pàgina espera la següent."""
    def fes(dades):
        nota = {"id": dades["darrera"] + 1, "estat": "esborrany",
                "projecte": projecte, "reel": reel,
                "paraula": paraula, "inici": inici, "cita": (cita or "").strip()[:200] or None,
                "fil": [_missatge("persona", text)]}
        if versio:
            nota.update(versio=versio, t_versio=t_versio, miniatura=miniatura)
        if tipus:
            nota["tipus"] = tipus
        if ronda is not None:
            nota["ronda"] = ronda
        dades["notes"].append(nota)
        return nota
    return _canvia(carpeta, fes, tot=True)


def esborra(carpeta: Path, id_: int) -> None:
    """Treu una nota que encara no s'ha enviat (les altres ja les ha vist Claude), amb la seva miniatura."""
    def fes(notes):
        nota = _troba(notes, id_)
        if nota["estat"] != "esborrany":
            raise ValueError("Aquesta nota ja és a Claude.")
        notes.remove(nota)
        return nota.get("miniatura")
    esborra_miniatura(carpeta, _canvia(carpeta, fes))


def esborra_miniatura(carpeta: Path, nom: str | None) -> None:
    """Esborra una miniatura de la carpeta MINIATURES (només un nom de fitxer d'allà dins, mai un altre camí)."""
    if not nom or Path(nom).name != nom or nom.startswith("."):
        return
    try:
        (Path(carpeta) / MINIATURES / nom).unlink(missing_ok=True)
    except OSError:  # a Windows, si el navegador la té oberta: es queda, i prou
        pass


def respon_persona(carpeta: Path, id_: int, text: str) -> dict:
    """La persona contesta la pregunta de Claude (o hi afegeix alguna cosa a una nota ja feta): torna a Claude
    de seguida, sense haver de prémer «Envia». Si encara no l'havia enviada, s'afegeix a la nota i prou; si Claude
    hi treballa, li arribarà quan respongui (vegeu `respon`)."""
    def fes(notes):
        nota = _troba(notes, id_)
        nota["fil"].append(_missatge("persona", text))
        if nota["estat"] in ("feta", "pregunta"):
            nota.update(estat="enviada", enviada_quan=time.time(), al_xat=False)
        return nota
    return _canvia(carpeta, fes)


def envia(carpeta: Path, projecte: str | None = None, versio=TOTES, nomes: int | None = None) -> int:
    """Les notes per enviar (totes, o només les d'un projecte: el que es veu a la pàgina), cap a Claude.
    Amb `versio`, només les d'aquella versió (None: les que s'han fet editant, sense versió); amb `nomes`, només
    aquella nota. Torna quantes."""
    def fes(notes):
        n = 0
        for nota in notes:
            if (nota["estat"] == "esborrany" and (projecte is None or nota.get("projecte") == projecte)
                    and (versio is TOTES or nota.get("versio") == versio) and nomes in (None, nota["id"])):
                nota.update(estat="enviada", enviada_quan=time.time())
                n += 1
        return n
    return _canvia(carpeta, fes)


def _per_agafar(nota: dict, ara: float) -> bool:
    """Les enviades, i les agafades fa estona que no s'han respost (Claude es va aturar a mitges). Les que s'acaben
    d'agafar no: si hi ha dues esperes alhora, o Claude torna a esperar abans d'acabar, no les rep dos cops."""
    if nota["estat"] == "enviada":
        return True
    return nota["estat"] == "treballant" and ara - nota.get("agafada", 0) > REAGAFA


def pren(carpeta: Path) -> list[dict]:
    """Claude agafa les notes que li toquen (passen a «treballant»). Torna còpies."""
    ara = time.time()

    def fes(notes):
        preses = []
        for nota in notes:
            if _per_agafar(nota, ara):
                # «reagafada»: Claude ja la tenia i no l'ha resposta (no és que la persona hi hagi tornat a escriure).
                nota.update(estat="treballant", agafada=ara, cops=nota.get("cops", 0) + 1, vistos=len(nota["fil"]),
                            reagafada=nota["estat"] == "treballant")
                preses.append(nota)
        return [json.loads(json.dumps(n)) for n in preses]
    with _bloquejat(carpeta):  # si no n'hi ha cap, no cal reescriure el fitxer
        if not any(_per_agafar(n, ara) for n in _llegeix(carpeta)["notes"]):
            return []
    return _canvia(carpeta, fes)


def respon(carpeta: Path, id_: int, text: str, pregunta: bool = False, cop: int | None = None,
           al_xat: bool = False) -> dict:
    """La resposta de Claude a una nota: «feta» o, si pregunta alguna cosa, «pregunta». Però si mentrestant la
    persona hi ha escrit alguna cosa que Claude no ha vist, la nota li torna a arribar (amb tota la conversa).
    `cop` diu de quina vegada que se li va donar és la resposta: si és d'una d'abans (la nota s'ha tornat a donar,
    potser a un altre Claude), la resposta es desa però no la tanca (revisió de Codex). `al_xat`: és una pregunta
    que s'ha de respondre al xat (un permís, com baixar un fitxer d'internet), i la pàgina ho diu."""
    def fes(notes):
        nota = _troba(notes, id_)
        if cop is not None and cop > nota.get("cops", 0):  # una vegada que no ha passat: no es pot deixar encallada
            raise ValueError(f"La nota {id_} només se t'ha donat {nota.get('cops', 0)} cops: "
                             f"respon amb {id_per_respondre(nota)}.")
        vella = cop is not None and cop != nota.get("cops", 0)
        vistos = nota.get("vistos", len(nota["fil"]))
        noves = any(m["de"] == "persona" for m in nota["fil"][vistos:])
        nota["fil"].append(_missatge("claude", text))
        if not vella:
            if noves:
                nota.update(estat="enviada", enviada_quan=time.time(), al_xat=False)
            else:
                nota.update(estat="pregunta" if pregunta or al_xat else "feta", al_xat=bool(al_xat))
        return nota
    return _canvia(carpeta, fes)


def marca_connexio(carpeta: Path) -> None:
    """Claude espera notes: ho diu a la pàgina (cal repetir-ho cada pocs segons). Cada procés amb el seu fitxer
    temporal: si hi ha dues esperes alhora, no es trepitgen (revisió de Codex)."""
    path = Path(carpeta) / CONNEXIO
    tmp = path.with_name(f"{CONNEXIO}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"vist": time.time(), "pid": os.getpid()}), encoding="utf-8")
    try:
        _substitueix(tmp, path)
    except PermissionError:
        tmp.unlink(missing_ok=True)  # la pàgina ho llegia just ara: ja es dirà d'aquí a un segon


def deixa_connexio(carpeta: Path) -> None:
    """Treu el senyal, si és d'aquest procés (si n'hi ha una altra espera, que continuï dient-ho)."""
    path = Path(carpeta) / CONNEXIO
    try:
        if json.loads(path.read_text(encoding="utf-8")).get("pid") == os.getpid():
            path.unlink()
    except (OSError, ValueError):
        pass


def connectat(carpeta: Path) -> bool:
    """Si Claude espera notes ara mateix."""
    try:
        vist = float(json.loads((Path(carpeta) / CONNEXIO).read_text(encoding="utf-8")).get("vist", 0))
    except (FileNotFoundError, ValueError, OSError):
        return False
    return time.time() - vist < VIU


def espera(carpeta: Path, segons: float, cada: float = 1.0, avis=None) -> list[dict]:
    """Espera fins que hi hagi notes enviades (i les agafa) o fins que passin `segons`; mentrestant, la pàgina
    sap que Claude hi és connectat. Torna les notes agafades (pot ser una llista buida)."""
    fi = time.time() + segons
    try:
        while True:
            marca_connexio(carpeta)
            # Si n'acaba d'enviar una, s'espera una mica: qui les envia d'una en una les té juntes en una sola tongada.
            if time.time() >= fi or not _acabades_d_enviar(carpeta):
                preses = pren(carpeta)
                if preses or time.time() >= fi:
                    return preses
            time.sleep(min(cada, max(0.0, fi - time.time())))
    finally:
        deixa_connexio(carpeta)


def _acabades_d_enviar(carpeta: Path) -> bool:
    ara = time.time()
    with _bloquejat(carpeta):
        return any(n["estat"] == "enviada" and ara - n.get("enviada_quan", 0) < AGRUPA for n in _llegeix(carpeta)["notes"])


def id_per_respondre(nota: dict) -> str:
    """El que Claude escriu a `--respon`: el número de la nota i de quina vegada se li ha donat («3.2»)."""
    return f"{nota['id']}.{nota['cops']}" if nota.get("cops") else str(nota["id"])


def numeros_pagina(totes: list[dict], al_video) -> dict[int, int]:
    """El número amb què la pàgina ensenya cada nota ({id: número}): per l'ordre del vídeo (les de tot el vídeo,
    primer) dins del seu projecte (la gravació o un reel) i, a Revisa, de la seva versió. Com pagina/app.js
    (numNota). `al_video(nota)`: el segon del vídeo editat on cau (o None)."""
    grups: dict = {}
    for n in totes:
        grups.setdefault((n.get("projecte"), n.get("versio")), []).append(n)
    numeros = {}
    for (_, versio), llista in grups.items():
        if versio:
            ordre = sorted(llista, key=lambda n: (n.get("t_versio") or 0, n["id"]))
        else:
            def clau(n):
                if n.get("inici") is None:
                    return (0, 0.0, n["id"])
                t = al_video(n)
                return (1, t if t is not None else float("inf"), n["id"])
            ordre = sorted(llista, key=clau)
        numeros.update({n["id"]: k for k, n in enumerate(ordre, 1)})
    return numeros


def text_per_a_claude(nota: dict, durada_mmss, al_video: float | None = None, carpeta: Path | None = None,
                      numero: int | None = None) -> str:
    """Una nota explicada perquè Claude la pugui fer: on va, què hi diu la persona i què s'han dit abans.
    `al_video` és el segon del vídeo editat (el que la persona veu sota el vídeo), si se sap. Si la nota és d'una
    versió (Revisa), es diu quina i on és la miniatura (`carpeta`: la de la gravació), perquè Claude la pugui mirar.
    `numero`: el que la persona veu a la pàgina (per l'ordre del vídeo; numeros_pagina), si no és l'id."""
    on = f"per a tot el reel «{nota['reel']}»" if nota.get("reel") else "per a tot el vídeo"
    if nota.get("inici") is not None:
        gravacio = durada_mmss(nota["inici"])
        on = (f"al {durada_mmss(al_video)} del vídeo, el {gravacio} de la gravació" if al_video is not None
              else f"al {gravacio} de la gravació, un tros que ara no surt al vídeo")
        if nota.get("cita"):
            on += f", a «{nota['cita']}»"
        if nota.get("paraula") is not None:
            on += f" (paraula {nota['paraula']})"
        if nota.get("reel"):
            on += f", al reel «{nota['reel']}»"
    if nota.get("versio"):
        on += f"; feta mirant l'esborrany {nota['versio']}, al {durada_mmss(nota.get('t_versio') or 0)} d'aquell vídeo"
    nom = f"Nota {nota['id']}" if numero in (None, nota["id"]) else f"Nota {nota['id']} (a la pàgina, la {numero})"
    linies = [f"{nom} ({on}):"]
    for m in nota["fil"]:
        linies.append(f"  {'Tu' if m['de'] == 'claude' else 'La persona'}: {m['text']}")
    if nota.get("reagafada"):
        linies.append("  (Ja te l'havia donat i no l'has resposta: mira si ja l'havies feta abans de tornar-la a fer.)")
    if nota.get("tipus") == "ronda":
        linies.append("  (És el botó «Demana la ronda següent» del tauler de Vesteix: els vots i les notes de cada peça són a "
                      "`tallat.py grafics`. Vegeu «El tauler» a les instruccions de tallat.)")
    if nota.get("miniatura") and carpeta is not None:
        linies.append(f"  El fotograma que mirava: {Path(carpeta) / MINIATURES / nota['miniatura']}")
    if nota["estat"] == "treballant":
        linies.append(f"  Per respondre-la: --respon {id_per_respondre(nota)}")
    if nota.get("projecte"):
        linies.append(f"  (es fa a --projecte \"{nota['projecte']}\")")
    return "\n".join(linies)
