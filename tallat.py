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
  python tallat.py afegeix TIPUS --paraula ID --projecte CARPETA [--text "…"]   (instrucció a mà)
  python tallat.py broll ID_INSTRUCCIO FITXER --projecte CARPETA [--durada 1.5]
  python tallat.py exporta --projecte CARPETA [--qualitat esborrany|1080|4k]
  python tallat.py editors --projecte CARPETA [--amb-subtitols] [--trossos]   (Premiere, Final Cut, DaVinci / CapCut)
  python tallat.py gust                                (les regles del teu gust)
  python tallat.py gust afegeix SECCIO "TEXT" [--ajust subtitols.mida=0.09]
  python tallat.py gust treu NUMERO

La carpeta del projecte ha de ser fora del repositori (els vídeos i el que dius no es publiquen).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from motor import comprova, edicio, editors, entorn, exporta, gust, instruccions, marca, muntatge, transcripcio
from motor.projecte import ORIGINAL, PROXY, TRANSCRIPCIO, Projecte, minuts


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
    for nom in (PROXY, "veu.npy"):  # el mateix vídeo: n'hi ha prou amb apuntar-hi
        if (carpeta / nom).exists():
            (desti / nom).symlink_to(Path("..") / nom)
    for nom in moure:
        (carpeta / nom).rename(desti / nom)
    return desti


def _enllaca(origen, desti) -> None:
    try:
        os.link(origen, desti)
    except OSError:
        shutil.copy2(origen, desti)


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
        font = "text de l'SRT + alineació WhisperX"
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
    proxy = projecte.carpeta / PROXY
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
    print(f"Pàgina de revisió de «{projecte.nom}»: {adreca}")
    print("Deixa aquesta finestra oberta mentre revises. Per tancar: Control + C.")
    if not args.sense_navegador:
        subprocess.run(["open", adreca], check=False)
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
    print(f"\nInstruccions de veu: {len(llista)} (tretes del vídeo; decideix-les a la pàgina de revisió)")
    for i in llista:
        print(f"  · {minuts(i['inici'])} · {NOMS_INSTRUCCIO.get(i['tipus'], i['tipus'])}: «{i['text']}»")


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
    ins = projecte.afegeix_instruccio(args.tipus, args.paraula, args.text or "")
    p = projecte.dades["paraules"][args.paraula]
    print(f"Instrucció {ins['id']} ({args.tipus}) a «{p['text']}» ({minuts(p['inici'])}).")


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
                    zooms=projecte.zooms_per_tram(trams), brolls=projecte.brolls(trams))
    projecte.desa_talls(sortida, trams)
    print(f"\nFet en {minuts(time.time() - t0)}:\n  {sortida}")


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
    ed.add_argument("--amb-subtitols", action="store_true", help="Inclou-hi els subtítols animats (capa transparent)")
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
    kl = ks.add_parser("lletra", help="Posa una lletra gratuïta als subtítols d'un kit (la baixa el primer cop)")
    kl.add_argument("id", help="L'id de la lletra (tallat.py kit lletres)")
    kl.add_argument("--kit", help="El kit (si no, el per defecte)")
    ki.set_defaults(func=ordre_kit)

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
