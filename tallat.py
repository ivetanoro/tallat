"""tallat: editor de reels en català, per paraules.

Ús (la primera vegada: ./prepara.sh, que instal·la tot el que cal):
  python tallat.py comprova                           (revisa que l'ordinador tingui tot el que cal)
  python tallat.py transcriu VIDEO --projecte CARPETA [--srt FITXER.srt] [--model large-v3]
  python tallat.py revisa --projecte CARPETA          (obre la pàgina de revisió)
  python tallat.py neteja --projecte CARPETA [--pausa 0.35]
  python tallat.py estat --projecte CARPETA
  python tallat.py guio --projecte CARPETA            (text per paràgrafs perquè l'assistent proposi reels)
  python tallat.py reels --projecte CARPETA           (valida reels.json i en mostra la durada)
  python tallat.py reel ID --projecte CARPETA         (crea el projecte d'un reel proposat)
  python tallat.py realinea --projecte CARPETA         (torna a calcular el temps de cada paraula)
  python tallat.py afegeix TIPUS --paraula ID --projecte CARPETA [--text "…"] [--treu A-B]   (instrucció a mà)
  python tallat.py broll ID_INSTRUCCIO FITXER --projecte CARPETA [--durada 1.5]
  python tallat.py exporta --projecte CARPETA [--qualitat esborrany|1080|4k]
  python tallat.py editors --projecte CARPETA [--amb-subtitols] [--trossos]   (Premiere, Final Cut, DaVinci / CapCut)
  python tallat.py gust                                (les regles del teu gust)
  python tallat.py gust afegeix SECCIO "TEXT" [--ajust subtitols.mida=0.09]
  python tallat.py gust treu NUMERO
  python tallat.py marca [--projecte CARPETA] [CLAU=VALOR …]   (la teva marca: colors, lletres, crida a l'acció)
  python tallat.py grafics --projecte CARPETA [--json]          (les frases, la marca i el pla de gràfics, amb notes)
  python tallat.py grafics proposa PLA.json --projecte CARPETA  (desa el pla de gràfics que proposa l'assistent)
  python tallat.py grafics canvia PLA.json --projecte CARPETA   (només els gràfics del fitxer: les notes ateses)
  python tallat.py grafics fotogrames --projecte CARPETA        (el fotograma de cada gràfic, per triar-ne el lloc)
  python tallat.py grafics captura URL [--grafic g3] --projecte CARPETA  (la captura d'una web, per al gràfic «web»)

La carpeta del projecte ha de ser fora del repositori (els vídeos i el que dius no es publiquen).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
from pathlib import Path

from motor import comprova, edicio, editors, entorn, exporta, grafics, gust, instruccions, marca, muntatge, transcripcio
from motor.projecte import EXPORTS, ORIGINAL, PROXY, TRANSCRIPCIO, Projecte, minuts


def _carrega(args) -> Projecte:
    carpeta = Path(args.projecte).expanduser().resolve()
    if not (carpeta / TRANSCRIPCIO).exists():
        sys.exit(f"Aquesta carpeta encara no té cap transcripció: {carpeta}\n"
                 "Primer fes: python tallat.py transcriu VIDEO --projecte CARPETA")
    projecte = Projecte(carpeta)
    for a in projecte.avisos:
        print("Avís:", a)
    return projecte


def _barra(text: str):
    ultim = [-10]

    def progres(pct: int):
        if pct >= ultim[0] + 10:
            print(f"  {text}… {pct} %", flush=True)
            ultim[0] = pct
    return progres


def guarda_anteriors(carpeta: Path) -> Path | None:
    """Abans de canviar la transcripció, guarda l'edició d'abans en una carpeta a part.

    L'edició, les instruccions i els reels apunten a paraules que amb la transcripció nova poden
    ser unes altres. No s'esborren: van a «anteriors-…», amb una còpia de la transcripció vella i
    dels recursos, i amb la mateixa estructura, de manera que els reels hi continuen funcionant."""
    moure = [nom for nom in ("edicio.json", "edicio.txt", instruccions.FITXER, muntatge.CARPETA_REELS)
             if (carpeta / nom).exists() or (carpeta / nom).is_symlink()]
    if not moure or not (carpeta / TRANSCRIPCIO).exists():
        return None
    desti = carpeta / f"anteriors-{time.strftime('%Y%m%d-%H%M%S')}"
    desti.mkdir()
    shutil.copy2(carpeta / TRANSCRIPCIO, desti / TRANSCRIPCIO)
    if (carpeta / ORIGINAL).exists():
        shutil.copy2(carpeta / ORIGINAL, desti / ORIGINAL)
    for nom in ("broll", "stickers"):  # els recursos, enllaçats (no ocupen el doble)
        if (carpeta / nom).is_dir():
            shutil.copytree(carpeta / nom, desti / nom, copy_function=_enllaca)
    for nom in (PROXY, "veu.npy", "veu.json"):  # el mateix vídeo: n'hi ha prou amb apuntar-hi
        if (carpeta / nom).exists():
            try:
                (desti / nom).symlink_to(Path("..") / nom)
            except OSError:  # Windows sense permís per fer enllaços: el mateix fitxer amb un altre nom (o una còpia)
                _enllaca(carpeta / nom, desti / nom)
    for nom in moure:
        (carpeta / nom).rename(desti / nom)
    return desti


def _enllaca(origen, desti) -> None:
    try:
        os.link(origen, desti)
    except OSError:
        shutil.copy2(origen, desti)


def ordre_realinea(args) -> None:
    """Torna a calcular quan comença i acaba cada paraula (amb l'alineador d'ara), sense canviar el text
    ni res de l'edició: els talls, els subtítols i els gràfics hi tornen a caure al lloc."""
    projecte = _carrega(args)
    path = projecte.fitxer(TRANSCRIPCIO).resolve()  # en un reel, la de la gravació sencera
    dades = json.loads(path.read_text(encoding="utf-8"))
    paraules = dades["paraules"]
    frases: dict[int, list[dict]] = {}
    for p in paraules:
        frases.setdefault(p["frase"], []).append(p)
    segments = [{"start": ps[0]["inici"], "end": ps[-1]["final"], "text": " ".join(p["text"] for p in ps)}
                for _, ps in sorted(frases.items())]
    print(f"Calculant de nou el temps de {len(paraules)} paraules (pot trigar uns minuts; el primer cop baixa el model)…",
          flush=True)
    t0 = time.time()
    video = Path(dades["video"])
    if not video.exists():  # s'ha mogut l'original: la còpia lleugera té el mateix so i el mateix temps
        video = path.parent / PROXY
        print(f"No trobo el vídeo original: faig servir la còpia lleugera ({video.name}).")
    if not paraules or not video.exists():
        sys.exit("No hi ha res per alinear (cap paraula, o ni el vídeo ni la còpia lleugera).")
    noves = transcripcio.a_paraules(transcripcio.alinea(transcripcio.carrega_audio(video), segments))
    if [p["text"] for p in noves] != [p["text"] for p in paraules]:
        sys.exit("Les paraules no coincideixen amb les de la transcripció: no he canviat res.")
    canvis = [abs(n["inici"] - p["inici"]) for n, p in zip(noves, paraules)]
    copia = path.with_name(f"transcripcio-abans-{time.strftime('%Y%m%d-%H%M%S')}.json")
    shutil.copy2(path, copia)
    for p, n in zip(paraules, noves):
        p["inici"], p["final"], p["confianca"] = n["inici"], n["final"], n.get("confianca")
    font = re.sub(r"\s*\+ alineació.*$", "", str(dades.get("font", "")))
    dades["font"] = f"{font} + alineació de tot el text" if font else "alineació de tot el text"
    path.write_text(json.dumps(dades, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Fet en {minuts(time.time() - t0)}. {sum(c > 0.25 for c in canvis)} paraules s'han mogut més d'un quart de "
          f"segon (la que més, {max(canvis):.1f} s). La d'abans és a {copia.name}.")
    print("Si tens la pàgina de revisió oberta, tanca-la i torna-la a obrir.")


def ordre_compara_temps(args) -> None:
    """Quant s'assemblen els temps de les paraules del projecte i els d'un SRT fet per una altra eina
    (Descript). Amb un SRT d'una paraula per subtítol es comparen totes; amb subtítols de frases, només
    l'inici de la primera paraula i el final de l'última de cada subtítol. On no coincideixen, val la pena
    escoltar-ho: és la manera de saber quin dels dos encerta (vegeu transcripcio.compara_temps)."""
    path = Path(args.projecte).expanduser().resolve() / TRANSCRIPCIO
    if not path.exists():
        sys.exit(f"No trobo la transcripció: {path}")
    paraules = json.loads(path.read_text(encoding="utf-8"))["paraules"]
    r = transcripcio.compara_temps(paraules, transcripcio.llegeix_srt(Path(args.srt).expanduser()))
    if not r["n"]:
        sys.exit("No he trobat paraules comunes entre la transcripció i l'SRT.")
    print(f"{r['n']} vores comparades. Diferència mediana: {r['mediana'] * 1000:.0f} ms.")
    print(f"  més d'una dècima: {r['mes_01']} ({r['mes_01'] / r['n']:.0%}) · més d'un quart de segon: {r['mes_025']}"
          f" · més de mig segon: {r['mes_05']}")
    if r["grans"]:
        print("On més difereixen (escolta-ho per saber quin encerta):")
        for g in r["grans"]:
            print(f"  {minuts_i_segons(g['nostre'])}  «{g['text']}»: tallat {g['nostre']:.2f} s, SRT {g['srt']:.2f} s")


def minuts_i_segons(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:05.2f}"


def ordre_transcriu(args) -> None:
    video = Path(args.video).expanduser().resolve()
    carpeta = Path(args.projecte).expanduser().resolve()
    if not video.exists():
        sys.exit(f"No trobo el vídeo: {video}")
    if (carpeta / TRANSCRIPCIO).is_symlink() or (carpeta / muntatge.REEL).exists():
        # Un reel comparteix la transcripció amb la gravació sencera: refer-la aquí la canviaria per a tots.
        sys.exit("Aquest projecte és un reel: comparteix la transcripció amb la gravació sencera.\n"
                 "Si l'has de refer, fes-ho a la carpeta de la gravació (i torna a crear els reels).")
    if (carpeta / TRANSCRIPCIO).exists() and not args.forca:
        sys.exit(f"Aquest projecte ja té una transcripció ({carpeta / TRANSCRIPCIO}).\n"
                 "Si la vols refer i perdre els canvis, afegeix --forca.")
    carpeta.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("Carregant l'àudio…")
    audio = transcripcio.carrega_audio(video)
    if args.srt:
        frases = transcripcio.llegeix_srt(Path(args.srt).expanduser())
        font = "text de l'SRT + alineació de tot el text"
        print(f"Calculant el temps de cada paraula ({len(frases)} frases)…")
    else:
        print(f"Transcrivint amb WhisperX ({args.model}). En un Mac Intel pot trigar més que el vídeo…")
        frases = transcripcio.transcriu(audio, args.model)
        font = f"WhisperX {args.model}"
        print("Calculant el temps de cada paraula…")
    paraules = transcripcio.a_paraules(transcripcio.alinea(audio, frases))

    dades = {"versio": 1, "video": str(video), "font": font, **exporta.info_video(video), "paraules": paraules}
    anteriors = guarda_anteriors(carpeta)
    if anteriors:
        print(f"He guardat l'edició d'abans (amb les instruccions i els reels) a {anteriors.name}.")
    (carpeta / TRANSCRIPCIO).write_text(json.dumps(dades, ensure_ascii=False, indent=1), encoding="utf-8")
    (carpeta / ORIGINAL).write_text(edicio.text_editable(paraules), encoding="utf-8")

    projecte = Projecte(carpeta)
    if not args.sense_neteja:
        projecte.neteja()
    trobades = projecte.detecta_instruccions()
    projecte.desa()
    print(f"\nTranscripció feta en {minuts(time.time() - t0)}: {len(paraules)} paraules.")
    print("\n".join(projecte.resum()))
    _mostra_instruccions(trobades)

    print("\nPreparant la còpia lleugera per a la pàgina de revisió…")
    exporta.fes_proxy(video, carpeta / PROXY, progres=_barra("còpia"))
    print(f"\nTot a punt. Obre la pàgina de revisió amb:\n  python tallat.py revisa --projecte \"{carpeta}\"")


def ordre_revisa(args) -> None:
    from motor.servidor import crea_servidor

    projecte = _carrega(args)
    proxy = projecte.fitxer(PROXY)
    if not proxy.exists() or proxy.stat().st_mtime < projecte.video.stat().st_mtime:
        print("Preparant la còpia lleugera del vídeo (només el primer cop)…")
        exporta.fes_proxy(projecte.video, proxy, progres=_barra("còpia"))

    for port in range(args.port, args.port + 20):
        try:
            servidor = crea_servidor(projecte, port)
            break
        except OSError:
            continue
    else:
        sys.exit("No trobo cap port lliure per obrir la pàgina.")

    adreca = f"http://127.0.0.1:{servidor.server_port}/"
    print(f"Pàgina de revisió de «{projecte.nom}»: {adreca}", flush=True)  # també si no és un terminal
    print("Deixa aquesta finestra oberta mentre revises. Per tancar: Control + C.")
    if not args.sense_navegador:
        webbrowser.open(adreca)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nPàgina tancada. Els canvis ja estan desats.")


def ordre_neteja(args) -> None:
    projecte = _carrega(args)
    projecte.neteja()
    if args.pausa is not None:
        projecte.estat["pausa_maxima"] = args.pausa if args.pausa > 0 else None
    projecte.desa()
    print("\n".join(projecte.resum()))


def ordre_estat(args) -> None:
    projecte = _carrega(args)
    projecte.desa()  # actualitza revisio.txt
    print("\n".join(projecte.resum()))


NOMS_INSTRUCCIO = {"talla": "torna a començar", "zoom": "zoom", "broll": "b-roll / imatges",
                   "sticker": "sticker", "altre": "altres"}


def _mostra_instruccions(llista: list[dict]) -> None:
    if not llista:
        return
    print(f"\nInstruccions de veu: {len(llista)} (decideix-les a la pàgina de revisió)")
    for i in llista:
        dubte = " · sense «Claude»: no s'ha tret res, sembla una ordre" if i.get("sense_paraula") else \
            " · no se sap on acaba: no s'ha tret res" if i.get("dubtosa") else ""
        print(f"  · {minuts(i['inici'])} · {NOMS_INSTRUCCIO.get(i['tipus'], i['tipus'])}: «{i['text']}»{dubte}")


def ordre_instruccions(args) -> None:
    projecte = _carrega(args)
    trobades = projecte.detecta_instruccions()
    projecte.desa()
    _mostra_instruccions(trobades) if trobades else print("No he trobat cap instrucció «Claude, …» ni «tallat, …».")


def ordre_afegeix(args) -> None:
    projecte = _carrega(args)
    n = len(projecte.dades["paraules"])
    if not 0 <= args.paraula < n:
        sys.exit(f"La paraula ha de ser un número entre 0 i {n - 1} (mira'ls al guió: tallat.py guio).")
    treu = None
    if args.treu:
        try:
            a, b = (int(x) for x in args.treu.replace("–", "-").split("-"))
        except ValueError:
            sys.exit("--treu vol dues paraules: la primera i l'última de la instrucció (p. ex. --treu 40-51).")
        if not (0 <= a <= b < n):
            sys.exit(f"--treu: les paraules han de ser entre 0 i {n - 1}, i la primera abans que l'última.")
        treu = (a, b)
    ins = projecte.afegeix_instruccio(args.tipus, args.paraula, args.text or "", treu)
    p = projecte.dades["paraules"][args.paraula]
    print(f"Instrucció {ins['id']} ({args.tipus}) a «{p['text']}» ({minuts(p['inici'])})."
          + (f" He tret del vídeo les paraules {treu[0]}–{treu[1]} (on la deies)." if treu else ""))


def ordre_broll(args) -> None:
    projecte = _carrega(args)
    fitxer = Path(args.fitxer).expanduser()
    try:
        ins = projecte.assigna_recurs(args.instruccio, fitxer, args.durada)
    except KeyError:
        ids = ", ".join(i["id"] for i in projecte.instruccions()) or "cap"
        sys.exit(f"No trobo la instrucció «{args.instruccio}». Instruccions: {ids}")
    nom = "Sticker" if ins["tipus"] == "sticker" else "B-roll"
    print(f"{nom} preparat per a {ins['id']} ({ins['durada']} s): {projecte.carpeta_instruccions() / ins['fitxer']}")


def ordre_guio(args) -> None:
    projecte = _carrega(args)
    path = projecte.carpeta / muntatge.GUIO
    path.write_text(muntatge.guio(projecte.dades["paraules"]), encoding="utf-8")
    print(f"Guió escrit: {path}")


def ordre_reels(args) -> None:
    projecte = _carrega(args)
    reels, errors = muntatge.llegeix_reels(projecte.carpeta, projecte.dades["paraules"])
    for e in errors:
        print("Error:", e)
    if not reels:
        print(f"No hi ha cap reel proposat a {projecte.carpeta / muntatge.REELS}")
        return
    for r in reels:
        print(f"· {r['id']}: «{r['titol']}» · {minuts(muntatge.durada_estimada(projecte, r))}")
        print(f"    ganxo: {r['ganxo']}")


def ordre_reel(args) -> None:
    projecte = _carrega(args)
    reels, errors = muntatge.llegeix_reels(projecte.carpeta, projecte.dades["paraules"])
    reel = next((r for r in reels if r["id"] == args.id), None)
    if reel is None:
        sys.exit(f"No trobo el reel «{args.id}». Reels: {', '.join(r['id'] for r in reels) or 'cap'}")
    carpeta = muntatge.crea_reel(projecte, reel)
    print("\n".join(Projecte(carpeta).resum()))
    print(f"\nProjecte del reel: {carpeta}")


def ordre_exporta(args) -> None:
    projecte = _carrega(args)
    trams = projecte.trams()
    sortida = projecte.sortida(args.qualitat)
    print(f"Exportant {len(trams)} trossos ({minuts(sum(b - a for a, b in trams))}) en qualitat «{args.qualitat}»…")
    t0 = time.time()
    if args.sense_subtitols:
        projecte.estat["subtitols"] = False
    capa = projecte.capa_subtitols(trams, args.qualitat, avis=print)
    exporta.exporta(projecte.font(args.qualitat), trams, sortida, args.qualitat, progres=_barra("exportant"), capa=capa,
                    zooms=projecte.zooms_per_tram(trams), brolls=projecte.brolls(trams),
                    blocs=projecte.blocs(trams), **projecte.opcions_so(trams))
    projecte.desa_talls(sortida, trams)
    avis = exporta.comprova_durades(sortida, sum(b - a for a, b in trams), projecte.dades["fps"])
    if avis:
        print(f"\nAvís: {avis}")
    copia = None
    try:
        copia = exporta.copia_a_carpeta(sortida)
    except OSError as e:
        print(f"\nNo l'he pogut copiar a la teva carpeta ({e.strerror or e}): és a la del projecte.")
    print(f"\nFet en {minuts(time.time() - t0)}:\n  {copia or sortida}")


def ordre_comprova(args) -> None:
    print("Comprovant tallat…")
    resultats = comprova.comprovacions()
    print(comprova.informe(resultats))
    if any(estat == "error" for estat, _, _ in resultats):
        sys.exit(1)


def ordre_editors(args) -> None:
    projecte = _carrega(args)
    try:
        if args.trossos:
            carpeta = editors.exporta_trossos(projecte, progres=_barra("exportant els trossos"))
        else:
            carpeta = editors.exporta_editors(projecte, amb_capa=args.amb_subtitols, avis=print)
    except ValueError as e:
        sys.exit(str(e))
    print(f"A punt: {carpeta}")
    print("Hi ha un LLEGEIX-ME.txt amb els passos per obrir-ho a l'editor.")


def ordre_gust(args) -> None:
    try:
        if args.accio == "afegeix":
            regla = gust.afegeix(args.seccio, args.text, args.ajust)
            ajust = regla.get("ajust")
            print(f"Regla {regla['id']} desada." + (f" Ajust aplicat: {ajust['clau']} = {ajust['valor']}" if ajust else ""))
        elif args.accio == "treu":
            regla, desfet = gust.treu(args.numero)
            print(f"Regla {regla['id']} treta." + (" L'opció ha tornat a com estava abans." if desfet else ""))
        else:
            print(gust.text(gust.llegeix()))
    except KeyError:
        sys.exit(f"No hi ha cap regla amb el número {args.numero}.")
    except ValueError as e:
        sys.exit(str(e))


def ordre_moment(args) -> None:
    """Què hi ha en un segon del vídeo: per arreglar el que la persona diu al xat («al segon 12…»)."""
    projecte = _carrega(args)
    trams, on, d_on = projecte.trams(), "el muntatge d'ara", "del muntatge d'ara (En directe)"
    if args.esborrany:  # el temps de l'últim esborrany, que pot ser d'abans dels darrers canvis
        talls = sorted((projecte.carpeta / EXPORTS).glob("*_esborrany_*.talls.json"), key=lambda f: f.stat().st_mtime)
        if not talls:
            sys.exit("Aquest projecte encara no té cap esborrany.")
        trams = [tuple(t) for t in json.loads(talls[-1].read_text(encoding="utf-8"))]
        on = f"l'esborrany {talls[-1].name.removesuffix('.talls.json')}"
        d_on = f"de {on}"
    original = projecte.al_original(args.segons, trams)
    if original is None:
        sys.exit(f"{on[0].upper()}{on[1:]} dura {sum(b - a for a, b in trams):.1f} s: el segon {args.segons:g} no hi és.")
    print(f"Segon {args.segons:g} {d_on} = segon {original:.2f} de la gravació.")
    a_prop = [p for p in projecte.paraules() if p["final"] >= original - 2.5 and p["inici"] <= original + 2.5]
    marca_p = lambda p: (("»" if p["inici"] <= original <= p["final"] + 0.15 else "")
                         + (f"{p['id']}:{p.get('correccio', p['text'])}" if p["conservada"] else f"[{p['id']}:{p['text']}]"))
    print("Paraules del voltant (» la que sona; [entre claudàtors] les tretes):")
    print("  " + " ".join(marca_p(p) for p in a_prop))
    ara = projecte.trams()  # i què hi ha ara en aquell moment
    m = projecte.al_muntatge(original, ara)
    if m is None:
        print("Ara aquest moment ja no surt al vídeo (s'ha tret).")
        return
    titol = projecte.titol(ara)
    if titol and titol["inici"] <= m < titol["final"]:
        print(f"Hi surt el títol del ganxo: «{titol['text'].replace(chr(10), ' / ')}».")
    for g in projecte.grafics(ara):
        if g["inici"] <= m < g["final"]:
            print(f"Hi surt el gràfic {g['id']} ({g['tipus']}, {g['estil']}): "
                  f"«{g['text'] or ' / '.join(p['text'] for p in g['punts'])}».")
    for nom, recursos in (("B-roll", projecte.brolls(ara)), ("Sticker", projecte.stickers(ara))):
        for r in recursos:
            if r["inici"] <= m < r["inici"] + r["durada"]:
                print(f"Hi surt el {nom.lower()} {r['id']} ({Path(r['fitxer']).name}, {r['durada']:g} s).")


def ordre_titol(args) -> None:
    projecte = _carrega(args)
    if args.treu or args.text is not None:
        if args.treu:
            projecte.estat["titol"] = None
        else:  # les línies, separades amb «|» (o amb salts de línia de debò)
            text = "\n".join(l.strip() for l in args.text.replace("|", "\n").split("\n"))
            projecte.estat["titol"] = edicio.titol_net({"text": text, "durada": args.durada})
            if projecte.estat["titol"] is None:
                sys.exit("El títol no pot ser buit.")
        projecte.estat["revisio"] = projecte.estat.get("revisio", 0) + 1  # la pàgina oberta s'hi posa al dia
        projecte.desa()
    titol = edicio.titol_net(projecte.estat.get("titol"))
    if not titol:
        print("Aquest vídeo no té títol del ganxo.")
        return
    estil = projecte.estil()["titol"]
    print("Títol del ganxo (les parts *entre asteriscs* surten destacades):")
    print("\n".join(f"  {l}" for l in titol["text"].split("\n")))
    print(f"Durada: {titol['durada'] or estil['durada']} s · estil del kit: {estil['animacio']}, {estil['alineacio']}"
          + (" · amaga els subtítols mentre surt" if estil.get("amaga_subtitols") else ""))


def _segons(t: float) -> str:
    return f"{t:.1f}".replace(".", ",") + " s"


def ordre_grafics(args) -> None:
    """El pla de gràfics: el que necessita l'assistent per fer-lo (les frases i la marca) i el que hi ha
    (amb les notes de la persona). `proposa` hi desa un pla nou i `canvia` només toca els gràfics que
    esmenta (per atendre les notes); motor/grafics.py diu com es fusionen."""
    projecte = _carrega(args)
    if args.accio == "captura":
        if not args.fitxer:
            sys.exit("Falta l'adreça: tallat.py grafics captura https://… --projecte …")
        print(f"Fent la captura de {args.fitxer}…", flush=True)
        try:
            with tempfile.TemporaryDirectory() as temporal:
                nom = projecte.importa_imatge(grafics.captura_web(args.fitxer, Path(temporal) / "captura.png"))
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as e:
            sys.exit(f"No he pogut fer la captura: {e}")
        if args.grafic:
            g = next((x for x in projecte.estat.get("grafics") or [] if x["id"] == args.grafic), None)
            if g is None or g["tipus"] != "web":
                sys.exit(f"No hi ha cap gràfic web «{args.grafic}» al pla (la captura és a {projecte.carpeta_imatges / nom}).")
            g["imatge"] = nom
            g["text"] = g["text"] or grafics.adreca_curta(args.fitxer)
            projecte.estat["revisio"] = projecte.estat.get("revisio", 0) + 1
            projecte.desa()
            print(f"Fet: la captura ja és al gràfic {args.grafic}.")
        else:
            print(f"Fet. Al pla, posa-hi \"imatge\": \"{nom}\" (i \"text\": \"{grafics.adreca_curta(args.fitxer)}\").")
        print(f"Per veure-la: {projecte.carpeta_imatges / nom}")
        return
    if args.accio == "fotogrames":
        trams = projecte.trams()
        situats = projecte.grafics(trams)
        if not situats:
            sys.exit("Aquest vídeo encara no té cap gràfic que surti al vídeo.")
        proxy = projecte.fitxer(PROXY)
        quadres = [{"t": projecte.al_original(g["inici"] + min(1.0, (g["final"] - g["inici"]) / 2), trams),
                    "limits": g["limits"]} for g in situats]
        desti = grafics.full_de_fotogrames(proxy if proxy.exists() else projecte.video, quadres,
                                           projecte.carpeta / "grafics-fotogrames.png")
        print(f"Fotogrames: {desti}")
        print(f"Un per gràfic, en files de {grafics.COLUMNES}, d'esquerra a dreta i de dalt a baix:")
        print("  " + "  ".join(f"{g['id']} ({_segons(g['inici'])}, {g['posicio']})" for g in situats))
        print("Enfosquit: on no pot anar cap gràfic (el que tapa Instagram i els subtítols). "
              "El requadre groc: on pot anar (dalt, mig o baix, o un número de 0 a 1).")
        return
    if args.accio:
        if not args.fitxer:
            sys.exit(f"Falta el fitxer amb el pla: tallat.py grafics {args.accio} PLA.json --projecte …")
        try:
            text = sys.stdin.read() if args.fitxer == "-" else Path(args.fitxer).expanduser().read_text(encoding="utf-8")
            pla = json.loads(text)
        except (OSError, json.JSONDecodeError) as e:
            sys.exit(f"No puc llegir el pla: {e}")
        pla = pla.get("grafics") if isinstance(pla, dict) else pla
        try:
            pla = projecte.importa_imatges(pla)  # les imatges que són camins de fitxers, al projecte
            manera = "de-nou" if args.de_nou else args.accio
            projecte.estat["grafics"] = grafics.fusiona(projecte.estat.get("grafics") or [], pla,
                                                        len(projecte.dades["paraules"]), manera)
        except ValueError as e:
            sys.exit(str(e))
        projecte.estat["revisio"] = projecte.estat.get("revisio", 0) + 1  # la pàgina oberta s'hi posa al dia
        projecte.desa()
    trams = projecte.trams()
    marca_kit = projecte.estil().get("marca") or {}
    pla = projecte.estat.get("grafics") or []
    situats = {g["id"]: g for g in projecte.grafics(trams)}
    frases = projecte.frases(trams)
    if args.json:
        print(json.dumps({"marca": {k: marca_kit.get(k) for k in ("compte", "public", "energia", "grafics", "crida",
                                                                  "colors_prohibits")},
                          "durada": round(sum(b - a for a, b in trams), 2), "frases": frases,
                          "grafics": [{**g, **({"inici": situats[g["id"]]["inici"], "final": situats[g["id"]]["final"]}
                                               if g["id"] in situats else {})} for g in pla]},
                         ensure_ascii=False, indent=1))
        return
    energia = marca_kit.get("energia") or ["net"]
    energia = ", ".join(energia if isinstance(energia, list) else [energia])
    quants = marca_kit.get("grafics") or "normal"
    print(f"Marca: estil dels gràfics «{energia}» · quants: «{quants}» ({grafics.DENSITAT.get(quants, '')})"
          + (f" · crida: «{marca_kit['crida']}»" if marca_kit.get("crida") else " · sense crida a la marca"))
    print(f"Vídeo de {_segons(sum(b - a for a, b in trams))}. Frases (on comença · paraules · text):")
    for f in frases:
        print(f"  {_segons(f['inici']):>8}  {f['paraula']}–{f['fins']}  {f['text']}")
    if not pla:
        print("Encara no hi ha cap pla de gràfics. Per desar-ne un: tallat.py grafics proposa PLA.json --projecte …")
        return
    notes = sum(1 for g in pla if g["estat"] == "canvia")
    print(f"Pla de gràfics ({len(pla)}" + (f"; {notes} amb nota" if notes else "") + "):")
    for g in pla:
        s = situats.get(g["id"])
        on = (_segons(s["inici"]) if s else "—" if g["estat"] == "tret"
              else "sense text" if g["tipus"] == "crida" and not g["text"] else "fora del vídeo")
        text = g["text"] or ("(la crida de la marca)" if g["tipus"] == "crida" else "")
        text = " · ".join(x for x in (g.get("de"), g.get("xifra"), text) if x)
        punts = " / ".join(("→ " if p.get("costat") == "enviat" else "") + p["text"] for p in g["punts"])
        punts = f"{g['forma']}, {g['costat']}" if g["tipus"] == "anotacio" else punts
        estat = {"canvia": "CANVIA", "mantingut": "mantingut", "tret": "tret"}.get(g["estat"], "proposat")
        print(f"  {g['id']:>4}  {g['tipus']:<11} {on:>14}  paraula {g['paraula'] if g['paraula'] is not None else 'final'}"
              f"  {g.get('estil') or '(marca)'}  {estat}  «{text}»" + (f" [{punts}]" if punts else ""))
        if g["nota"]:
            print(f"        nota: «{g['nota']}»")


NOMS_MARCA = {"compte": "El compte", "public": "Qui el mira", "referencia": "Reel de referència",
              "color_text": "Color del text", "color_principal": "Color principal", "color_destacat": "Color destacat",
              "color_secundari": "Color secundari", "color_clar": "Color clar", "color_fosc": "Color fosc",
              "colors_prohibits": "Mai", "lletra_titols": "Lletra dels títols", "lletra_text": "Lletra del text",
              "lletra_accent": "Lletra d'accent", "lletra_ma": "Lletra de mà",
              "majuscules_ma": "Lletra de mà en majúscules", "energia": "Estil dels gràfics", "grafics": "Quants gràfics",
              "crida": "Crida a l'acció"}


def ordre_marca(args) -> None:
    """La marca d'un kit: la mostra i, amb CLAU=VALOR, la desa (i l'escampa pel kit)."""
    kit = Projecte(Path(args.projecte).expanduser().resolve()).kit() if args.projecte else marca.resol(args.kit)
    canvis, biblioteca = {}, marca.biblioteca_lletres()["lletres"]
    for parell in args.valors:
        clau, igual, valor = parell.partition("=")
        if not igual or clau not in NOMS_MARCA:
            sys.exit(f"No entenc «{parell}». Fes servir CLAU=VALOR amb una d'aquestes claus: {', '.join(NOMS_MARCA)}")
        valor = valor.strip()
        if clau.startswith("lletra_") and valor:
            # Una lletra gratuïta (pel nom o per l'id): es baixa al kit, amb la cursiva si en té.
            lletra = next((l for l in biblioteca if valor.lower() in (l["id"], l["nom"].lower())), None)
            if lletra:
                try:
                    marca.baixa_lletra(lletra["id"], kit=kit, seccio="marca", clau=clau)
                except ConnectionError as e:
                    sys.exit(str(e))
                continue
        if clau == "energia":  # un o uns quants, separats amb comes
            canvis[clau] = [v.strip() for v in valor.split(",") if v.strip()]
            continue
        if clau == "majuscules_ma":  # sí o no
            if valor.lower() not in ("sí", "si", "no", "true", "false", "1", "0"):
                sys.exit("majuscules_ma ha de ser sí o no")
            canvis[clau] = valor.lower() in ("sí", "si", "true", "1")
            continue
        canvis[clau] = None if valor.lower() in ("", "null", "cap") and (clau.startswith(("color_", "lletra_"))) else valor
    if canvis:
        try:
            marca.desa("marca", canvis, kit=kit)
        except ValueError as e:
            sys.exit(str(e))
    m = marca.carrega(kit=kit)["marca"]
    nom = next((k["nom"] for k in marca.kits() if k["id"] == kit), kit)
    if not any(m.get(c) for c in NOMS_MARCA if c.startswith(("compte", "color_", "lletra_"))):
        print(f"El kit «{nom}» encara no té marca. Fes l'entrevista de marca (vegeu SKILL.md).")
        return
    print(f"La marca del kit «{nom}» (els colors i les lletres ja s'han posat als subtítols, al títol i al b-roll):")
    for clau, etiqueta in NOMS_MARCA.items():
        if m.get(clau) not in (None, "", [], False):
            valor = m[clau]
            print(f"  {etiqueta}: {', '.join(valor) if isinstance(valor, list) else 'sí' if valor is True else valor}")


def ordre_destaca(args) -> None:
    projecte = _carrega(args)
    destacades = projecte.estat.setdefault("destacades", {})
    if args.automatic:
        destacades.clear()
    total = len(projecte.dades["paraules"])
    for ids, valor in ((args.si or [], True), (args.no or [], False)):
        for id_ in ids:
            if not 0 <= id_ < total:
                sys.exit(f"No hi ha cap paraula amb el número {id_} (n'hi ha de 0 a {total - 1}).")
            destacades[id_] = valor
    if args.si or args.no or args.automatic:
        projecte.estat["revisio"] = projecte.estat.get("revisio", 0) + 1  # la pàgina oberta s'hi posa al dia
        projecte.desa()
    claus = [(w["id"], w["text"]) for l in projecte.linies_subtitols() for w in l["paraules"] if w["clau"]]
    print(f"Paraules destacades als subtítols ({len(claus)}):")
    print("  " + "  ".join(f"{i}:{text}" for i, text in claus))
    triades = sorted(destacades.items())
    if triades:
        print("Triades a mà (la resta les tria tallat): "
              + ", ".join(f"{i} {'sí' if v else 'no'}" for i, v in triades))
    if not projecte.estil_subtitols().get("clau_grans"):
        print("Avís: el kit d'aquest vídeo no fa més grans les paraules destacades. "
              "S'activa a la pàgina: Subtítols → Estil → Paraules destacades.")


PESOS = {"thin": "100", "extralight": "200", "light": "300", "regular": "400", "book": "400", "normal": "400",
         "medium": "500", "semibold": "600", "bold": "700", "extrabold": "800", "black": "900", "heavy": "900"}


def _pes_de(nom: str) -> tuple[str, bool]:
    """El gruix i si és cursiva, pel nom del fitxer («LaMeva-Italic» → 400 cursiva; «…Var…» → variable)."""
    baix = nom.lower().replace(" ", "").replace("-", "").replace("_", "")
    cursiva = "italic" in baix or "oblique" in baix
    if "var" in baix:
        return "var", cursiva
    pes = next((v for k, v in sorted(PESOS.items(), key=lambda x: -len(x[0])) if k in baix), "400")
    return pes, cursiva


def ordre_kit(args) -> None:
    try:
        if args.accio == "nou":
            kit = marca.crea_kit(args.nom, args.copia_de)
            print(f"Kit «{args.nom}» creat (id: {kit}).")
        elif args.accio == "nom":
            marca.canvia_nom(args.kit, args.nom)
            print(f"El kit {args.kit} ara es diu «{args.nom}».")
        elif args.accio == "per-defecte":
            marca.fes_per_defecte(args.kit)
            print(f"Els vídeos nous faran servir el kit {args.kit}.")
        elif args.accio == "tria":
            projecte = _carrega(args)
            projecte.tria_kit(args.kit)
            print(f"«{projecte.nom}» fa servir el kit {args.kit}.")
        elif args.accio == "exporta":
            nom, contingut = marca.empaqueta_kit(args.kit)
            desti = Path(args.a).expanduser() / nom
            desti.write_bytes(contingut)
            print(f"Kit desat a {desti}. Si porta una font teva, comprova que la pots compartir.")
        elif args.accio == "importa":
            kit = marca.importa_kit(Path(args.fitxer).expanduser().read_bytes())
            print(f"Kit importat (id: {kit}). Tria'l per a un vídeo a la pàgina o amb «tallat.py kit tria».")
        elif args.accio == "esborra":
            desti = marca.esborra_kit(args.kit)
            print(f"Kit tret de la llista. Si el vols recuperar, és a {desti}.")
        elif args.accio == "lletres":
            biblioteca = marca.biblioteca_lletres()
            for grup, nom in biblioteca["grups"].items():
                print(f"{nom}: " + ", ".join(f"{l['nom']} ({l['id']})" for l in biblioteca["lletres"] if l["grup"] == grup))
            print("\nPer posar-ne una a un kit: tallat.py kit lletra ID [--kit KIT]. Es baixa el primer cop.")
        elif args.accio == "font":
            origen = Path(args.fitxer).expanduser()
            familia = args.familia or re.split(r"[-_ ]", origen.stem)[0]
            pes, cursiva = _pes_de(origen.stem) if args.pes is None else (args.pes, False)
            desti = marca.afegeix_font(origen.read_bytes(), origen.name, familia, pes, args.cursiva or cursiva, kit=args.kit)
            print(f"Lletra «{familia}» afegida al kit {marca.resol(args.kit)} ({desti.name}). "
                  "Fes-la servir amb tallat.py marca (lletra_text=…, lletra_titols=…) o des de la pàgina.")
        elif args.accio == "lletra":
            if not any(l["id"] == args.id for l in marca.biblioteca_lletres()["lletres"]):
                sys.exit(f"No conec la lletra «{args.id}». Mira quines hi ha amb: tallat.py kit lletres")
            estil = marca.baixa_lletra(args.id, kit=args.kit)
            print(f"Els subtítols del kit {marca.resol(args.kit)} fan servir «{estil['font']}».")
        else:
            for k in marca.kits():
                print(f"{'★' if k['per_defecte'] else ' '} {k['id']}: {k['nom']}")
            print(f"\n★ = el kit per defecte (el dels vídeos nous). Els kits són a {marca.KITS}.")
    except KeyError as e:
        sys.exit(f"No trobo el kit «{e.args[0]}». Mira quins n'hi ha amb: tallat.py kit")
    except (ValueError, OSError) as e:  # ConnectionError (no s'ha pogut baixar una lletra) és un OSError
        sys.exit(str(e))


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)  # que els missatges surtin al moment
    entorn.prepara()  # les eines que ha instal·lat prepara.sh (ffmpeg, Node), al davant del PATH
    p = argparse.ArgumentParser(prog="tallat", description="Editor de reels en català, per paraules.")
    sub = p.add_subparsers(dest="ordre", required=True)

    t = sub.add_parser("transcriu", help="Transcriu un vídeo amb temps per paraula")
    t.add_argument("video")
    t.add_argument("--projecte", required=True, help="Carpeta on es desa la feina (fora del repositori)")
    t.add_argument("--srt", help="Text ja transcrit (p. ex. exportat de Descript); només se n'alinea el temps")
    t.add_argument("--model", default="large-v3", help="Model de WhisperX si no hi ha --srt")
    t.add_argument("--forca", action="store_true", help="Refés la transcripció encara que ja n'hi hagi una")
    t.add_argument("--sense-neteja", action="store_true", help="No treguis el farciment automàticament")
    t.set_defaults(func=ordre_transcriu)

    ra = sub.add_parser("realinea", help="Torna a calcular quan comença i acaba cada paraula (sense tocar l'edició)")
    ra.add_argument("--projecte", required=True)
    ra.set_defaults(func=ordre_realinea)

    ct = sub.add_parser("compara-temps", help="Compara el temps de cada paraula amb el d'un SRT (p. ex. de Descript)")
    ct.add_argument("--projecte", required=True)
    ct.add_argument("--srt", required=True)
    ct.set_defaults(func=ordre_compara_temps)

    r = sub.add_parser("revisa", help="Obre la pàgina de revisió al navegador")
    r.add_argument("--projecte", required=True)
    r.add_argument("--port", type=int, default=8765)
    r.add_argument("--sense-navegador", action="store_true", help="No obris el navegador automàticament")
    r.set_defaults(func=ordre_revisa)

    n = sub.add_parser("neteja", help="Treu farciment i paraules a mig dir, i escurça silencis")
    n.add_argument("--projecte", required=True)
    n.add_argument("--pausa", type=float, help="Silenci màxim en segons (0 = no escurçar)")
    n.set_defaults(func=ordre_neteja)

    e = sub.add_parser("estat", help="Mostra què s'ha tret i quant durarà")
    e.add_argument("--projecte", required=True)
    e.set_defaults(func=ordre_estat)

    ins = sub.add_parser("instruccions", help="Detecta les instruccions de veu «Claude, …» o «tallat, …»")
    ins.add_argument("--projecte", required=True)
    ins.set_defaults(func=ordre_instruccions)

    af = sub.add_parser("afegeix", help="Afegeix a mà una instrucció (b-roll, sticker, zoom) en una paraula")
    af.add_argument("tipus", choices=["broll", "sticker", "zoom"])
    af.add_argument("--paraula", type=int, required=True, help="Número de paraula (el del guió)")
    af.add_argument("--text", help="Descripció (p. ex. «una rentadora»)")
    af.add_argument("--treu", metavar="A-B", help="Les paraules on es deia la instrucció, per treure-les del vídeo (p. ex. 40-51)")
    af.add_argument("--projecte", required=True)
    af.set_defaults(func=ordre_afegeix)

    br = sub.add_parser("broll", aliases=["sticker"],
                        help="Assigna un fitxer a una instrucció de b-roll (vídeo o imatge) o de sticker (PNG)")
    br.add_argument("instruccio", help="Id de la instrucció (p. ex. i133 o m290-1)")
    br.add_argument("fitxer")
    br.add_argument("--durada", type=float, help="Segons (per defecte, els de l'estil)")
    br.add_argument("--projecte", required=True)
    br.set_defaults(func=ordre_broll)

    g = sub.add_parser("guio", help="Escriu el guió per paràgrafs per al primer muntatge")
    g.add_argument("--projecte", required=True)
    g.set_defaults(func=ordre_guio)

    rl = sub.add_parser("reels", help="Valida els reels proposats i en mostra la durada")
    rl.add_argument("--projecte", required=True)
    rl.set_defaults(func=ordre_reels)

    r1 = sub.add_parser("reel", help="Crea el projecte d'un dels reels proposats")
    r1.add_argument("id")
    r1.add_argument("--projecte", required=True)
    r1.set_defaults(func=ordre_reel)

    x = sub.add_parser("exporta", help="Exporta el vídeo tallat a MP4 vertical")
    x.add_argument("--projecte", required=True)
    x.add_argument("--qualitat", choices=list(exporta.QUALITATS), default="esborrany")
    x.add_argument("--sense-subtitols", action="store_true", help="Exporta sense subtítols")
    x.set_defaults(func=ordre_exporta)

    co = sub.add_parser("comprova", help="Revisa que l'ordinador tingui tot el que necessita tallat")
    co.set_defaults(func=ordre_comprova)

    ed = sub.add_parser("editors", help="Prepara el muntatge per acabar-lo a Premiere, Final Cut, DaVinci o CapCut")
    ed.add_argument("--projecte", required=True)
    ed.add_argument("--amb-subtitols", action="store_true", help="Inclou-hi els subtítols, el títol i els gràfics animats (capa transparent)")
    ed.add_argument("--trossos", action="store_true", help="Cada tros com un clip a part (per a CapCut o iMovie)")
    ed.set_defaults(func=ordre_editors)

    gu = sub.add_parser("gust", help="Les regles del teu gust (correccions que serveixen per als vídeos següents)")
    gs = gu.add_subparsers(dest="accio")
    ga = gs.add_parser("afegeix", help="Afegeix una regla")
    ga.add_argument("seccio", choices=list(gust.SECCIONS))
    ga.add_argument("text", help="La regla, en paraules de la persona")
    ga.add_argument("--ajust", help="Opció que canvia, p. ex. subtitols.mida=0.09 o farciment.deixa=vale")
    gt = gs.add_parser("treu", help="Treu una regla (i desfà el seu ajust)")
    gt.add_argument("numero", type=int)
    gu.set_defaults(func=ordre_gust)

    ki = sub.add_parser("kit", help="Els kits d'estil: llista'ls, crea'n, tria'n un per a un vídeo, exporta'ls o importa'ls")
    ks = ki.add_subparsers(dest="accio")
    kn = ks.add_parser("nou", help="Crea un kit (còpia d'un altre amb --copia-de; si no, l'estil neutre)")
    kn.add_argument("nom")
    kn.add_argument("--copia-de", help="L'id del kit que es copia")
    km = ks.add_parser("nom", help="Canvia el nom d'un kit")
    km.add_argument("kit")
    km.add_argument("nom")
    kd = ks.add_parser("per-defecte", help="El kit dels vídeos nous (i el que canvien les regles del gust)")
    kd.add_argument("kit")
    kt = ks.add_parser("tria", help="Tria el kit d'un vídeo (o d'un reel)")
    kt.add_argument("kit")
    kt.add_argument("--projecte", required=True)
    ke = ks.add_parser("exporta", help="Desa el kit en un .zip per passar-lo a algú")
    ke.add_argument("kit")
    ke.add_argument("--a", default=".", help="Carpeta on es desa (per defecte, l'actual)")
    kim = ks.add_parser("importa", help="Afegeix un kit d'un .zip")
    kim.add_argument("fitxer")
    kb = ks.add_parser("esborra", help="Treu un kit de la llista (es guarda a ~/.tallat/kits-esborrats)")
    kb.add_argument("kit")
    ks.add_parser("lletres", help="Les lletres gratuïtes que es poden posar a un kit")
    kf = ks.add_parser("font", help="Afegeix al kit una lletra teva (un fitxer .ttf, .otf, .woff o .woff2)")
    kf.add_argument("fitxer")
    kf.add_argument("--familia", help="El nom de la lletra (si no, el principi del nom del fitxer)")
    kf.add_argument("--pes", help="El gruix (400, 700…) o «var» si és variable (si no, pel nom del fitxer)")
    kf.add_argument("--cursiva", action="store_true", help="És la versió cursiva")
    kf.add_argument("--kit", help="El kit (si no, el per defecte)")
    kl = ks.add_parser("lletra", help="Posa una lletra gratuïta als subtítols d'un kit (la baixa el primer cop)")
    kl.add_argument("id", help="L'id de la lletra (tallat.py kit lletres)")
    kl.add_argument("--kit", help="El kit (si no, el per defecte)")
    ki.set_defaults(func=ordre_kit)

    mo = sub.add_parser("moment", help="Què hi ha en un segon del vídeo (paraules, títol, b-roll, stickers)")
    mo.add_argument("segons", type=float)
    mo.add_argument("--projecte", required=True)
    mo.add_argument("--esborrany", action="store_true", help="El segon és de l'últim esborrany, no del muntatge d'ara")
    mo.set_defaults(func=ordre_moment)

    ti = sub.add_parser("titol", help="El títol del ganxo: un text dissenyat als primers segons")
    ti.add_argument("--projecte", required=True)
    ti.add_argument("text", nargs="?", help="Les línies separades amb «|»; el que va *entre asteriscs* surt destacat")
    ti.add_argument("--durada", type=float, help="Segons (si no, els del kit)")
    ti.add_argument("--treu", action="store_true", help="Treu el títol")
    ti.set_defaults(func=ordre_titol)

    ma = sub.add_parser("marca", help="La marca d'un kit: colors, lletres i com són els teus vídeos (CLAU=VALOR la desa)")
    on = ma.add_mutually_exclusive_group()
    on.add_argument("--projecte", help="El kit d'aquest vídeo")
    on.add_argument("--kit", help="Un kit pel seu id (si no, el per defecte)")
    ma.add_argument("valors", nargs="*", metavar="CLAU=VALOR",
                    help="p. ex. color_destacat=#FF7DB8 lletra_accent=Fraunces crida=\"comenta GUIA\"")
    ma.set_defaults(func=ordre_marca)

    gr = sub.add_parser("grafics", help="El pla de gràfics: frases, marca, gràfics i notes (proposa o canvia: el desa)")
    gr.add_argument("accio", nargs="?", choices=["proposa", "canvia", "fotogrames", "captura"],
                    help="proposa: un pla nou (substitueix els proposats); canvia: només els gràfics que hi ha a FITXER; "
                         "fotogrames: una imatge amb el moment de cada gràfic, per veure on queden; "
                         "captura: fa la captura de la web URL (per al gràfic «web»)")
    gr.add_argument("fitxer", nargs="?", help="El pla en JSON (una llista de gràfics), o «-» per llegir-lo de l'entrada; "
                                              "amb «captura», l'adreça de la web")
    gr.add_argument("--grafic", help="Amb «captura»: el gràfic web on va la captura")
    gr.add_argument("--projecte", required=True)
    gr.add_argument("--de-nou", action="store_true", help="El pla nou substitueix tots els d'abans (també els mantinguts)")
    gr.add_argument("--json", action="store_true", help="Ho mostra en JSON")
    gr.set_defaults(func=ordre_grafics)

    de = sub.add_parser("destaca", help="Les paraules destacades dels subtítols (més grans i d'un altre color)")
    de.add_argument("--projecte", required=True)
    de.add_argument("--si", type=int, nargs="+", metavar="ID", help="Paraules que han de sortir destacades")
    de.add_argument("--no", type=int, nargs="+", metavar="ID", help="Paraules que no han de sortir destacades")
    de.add_argument("--automatic", action="store_true", help="Oblida les triades a mà: les tria totes tallat")
    de.set_defaults(func=ordre_destaca)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
