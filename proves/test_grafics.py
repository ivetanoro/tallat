import argparse
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from motor import grafics, marca, servidor, so, subtitols
from motor.projecte import Projecte

ARREL = Path(__file__).resolve().parent.parent


def g(**camps):
    return {"tipus": "frase", "paraula": 0, "text": "una idea", **camps}


class TestUnGrafic(unittest.TestCase):
    def test_es_comprova(self):
        net = grafics.net(g(text="  no és  *mandra* ", estil="mac", posicio="lateral", durada=40, punts=["x"]))
        self.assertEqual((net["text"], net["estil"], net["posicio"], net["durada"], net["punts"], net["estat"]),
                         ("no és *mandra*", "mac", None, 15.0, [], "proposat"))
        llista = grafics.net({"tipus": "llista", "paraula": 2, "punts": ["un", {"text": "dos", "paraula": 4}, ""]})
        self.assertEqual(llista["punts"], [{"text": "un", "paraula": None}, {"text": "dos", "paraula": 4}])
        self.assertIsNone(grafics.net({"tipus": "crida"})["paraula"])  # la crida pot anar al final, sense paraula

    def test_el_que_no_s_enten_es_diu_en_catala(self):
        for dolent, paraula in (({"tipus": "pantalla", "paraula": 0}, "Tipus"), ({"tipus": "frase", "text": "x"}, "paraula"),
                                (g(text=""), "text"), ({"tipus": "llista", "paraula": 0}, "punts"),
                                (g(paraula=12), "12"), (g(paraula=True), "paraula"), (g(durada="llarg"), "durada"),
                                ({"tipus": "etiqueta", "paraula": 0, "text": "x" * 41}, "massa llarg")):
            with self.assertRaises(ValueError) as e:
                grafics.net(dolent, paraules=10)
            self.assertIn(paraula, str(e.exception))

    def test_la_llista_desada_perd_el_que_no_val(self):
        llista = grafics.neteja_llista([g(id="g1"), {"tipus": "res"}, g(id="g1"), "brossa"])
        self.assertEqual([x["id"] for x in llista], ["g1", "g2"])  # l'id repetit en rep un de nou
        self.assertEqual(grafics.neteja_llista(None), [])


class TestTipusNous(unittest.TestCase):
    def test_notificacio_xat_numero_i_anotacio(self):
        notif = grafics.net({"tipus": "notificacio", "paraula": 0, "de": "mama", "text": "on ets?"})
        self.assertEqual((notif["de"], notif["forma"]), ("mama", None))
        xat = grafics.net({"tipus": "xat", "paraula": 0, "punts": ["hola", "què tal", {"text": "bé", "costat": "enviat"}]})
        self.assertEqual([p["costat"] for p in xat["punts"]], ["rebut", "enviat", "enviat"])  # per torns, si no es diu
        nota = grafics.net({"tipus": "anotacio", "paraula": 0, "text": "jo, fa 3 anys", "forma": "estrella"})
        self.assertEqual((nota["forma"], nota["costat"]), ("fletxa", "esquerra"))
        for dolent, paraula in (({"tipus": "numero", "paraula": 0, "xifra": "molts"}, "xifra"),
                                ({"tipus": "xat", "paraula": 0}, "punts"), ({"tipus": "notificacio", "paraula": 0}, "text")):
            with self.assertRaises(ValueError) as e:
                grafics.net(dolent)
            self.assertIn(paraula, str(e.exception))

    def test_la_lletra_de_ma_pot_anar_sempre_en_majuscules(self):
        self.assertFalse(grafics.paleta({"marca": {"majuscules_ma": True}})["majuscules_ma"])  # sense lletra de mà, res
        paleta = grafics.paleta({"marca": {"lletra_ma": "La Meva Mà", "majuscules_ma": True}})
        self.assertEqual((paleta["lletra_ma"], paleta["majuscules_ma"]), ("La Meva Mà", True))
        self.assertEqual(marca.valida("marca", {"majuscules_ma": True}), {"majuscules_ma": True})
        with self.assertRaises(ValueError):
            marca.valida("marca", {"majuscules_ma": "sí"})

    def test_la_xifra_es_llegeix_com_s_escriu(self):
        self.assertEqual(grafics.llegeix_xifra("10.000 €"),
                         {"abans": "", "despres": " €", "milers": True, "valor": 10000.0, "decimals": 0})
        self.assertEqual(grafics.llegeix_xifra("+2,5 h")["abans"], "+")
        self.assertEqual(grafics.llegeix_xifra("2,5 h")[("valor")], 2.5)
        self.assertEqual(grafics.llegeix_xifra("3 de cada 4")["despres"], " de cada 4")

    def test_situats_porten_el_que_cal_per_dibuixar(self):
        pla = grafics.neteja_llista([{"tipus": "numero", "paraula": 0, "xifra": "73 %", "text": "de mares"},
                                     {"tipus": "xat", "paraula": 1, "punts": [{"text": "hola", "paraula": 2}, "adeu"]},
                                     {"tipus": "anotacio", "paraula": 3, "text": "jo", "forma": "cercle", "costat": "dreta"}])
        numero, xat, nota = grafics.situa(pla, {0: 0.0, 1: 1.0, 2: 1.5, 3: 2.0}, {}, 10.0, [])
        self.assertEqual(numero["xifra"]["valor"], 73.0)
        self.assertEqual([(p["costat"], p["t"]) for p in xat["punts"]], [("rebut", 1.5), ("enviat", 2.25)])
        self.assertTrue(xat["amaga_subtitols"])
        self.assertEqual((nota["forma"], nota["costat"], nota["posicio"]), ("cercle", "dreta", "mig"))


class TestFusio(unittest.TestCase):
    def setUp(self):
        self.actuals = grafics.fusiona([], [g(paraula=1, text="a"), g(paraula=2, text="b"), g(paraula=3, text="c"),
                                            g(paraula=4, text="d")])
        estats = {"g2": ("mantingut", ""), "g3": ("canvia", "més curta"), "g4": ("tret", "")}
        for x in self.actuals:
            x["estat"], x["nota"] = estats.get(x["id"], ("proposat", ""))

    def test_un_pla_nou_substitueix_els_proposats(self):
        nou = grafics.fusiona(self.actuals, [g(paraula=5, text="e")])
        self.assertEqual([(x["id"], x["text"], x["estat"]) for x in nou],
                         [("g2", "b", "mantingut"), ("g3", "c", "canvia"), ("g4", "d", "tret"), ("g5", "e", "proposat")])

    def test_canviar_un_gràfic_n_atén_la_nota(self):
        nou = grafics.fusiona(self.actuals, [g(id="g3", paraula=3, text="c!")], manera="canvia")
        self.assertEqual([(x["id"], x["text"], x["estat"], x["nota"]) for x in nou],
                         [("g1", "a", "proposat", ""), ("g2", "b", "mantingut", ""), ("g3", "c!", "proposat", ""),
                          ("g4", "d", "tret", "")])
        igual = grafics.fusiona(self.actuals, [g(id="g3", paraula=3, text="c")], manera="canvia")
        self.assertEqual((igual[2]["estat"], igual[2]["nota"]), ("canvia", "més curta"))  # sense canvis, la nota hi és

    def test_de_nou(self):
        nou = grafics.fusiona(self.actuals, [g(paraula=9, text="z")], manera="de-nou")
        # Un id no es torna a fer servir: els sons apagats d'un gràfic d'abans no passen a un de nou.
        self.assertEqual([(x["id"], x["text"]) for x in nou], [("g5", "z")])
        with self.assertRaises(ValueError):
            grafics.fusiona(self.actuals, {"no": "és una llista"})


class TestSituar(unittest.TestCase):
    def test_cada_grafic_al_seu_moment(self):
        inicis = {0: 0.0, 1: 0.5, 2: 1.0, 3: 2.0, 4: 3.0}
        finals = {0: 0.4, 1: 0.9, 2: 1.4, 3: 2.4, 4: 3.4}
        pla = grafics.neteja_llista([
            g(paraula=1, fins=2),
            {"tipus": "llista", "paraula": 1, "punts": [{"text": "x", "paraula": 3}, "y"], "fins": 4},
            {"tipus": "etiqueta", "paraula": 1, "text": "pas 1"},
            {"tipus": "crida"},
            {"tipus": "etiqueta", "paraula": 7, "text": "fora"},  # la seva paraula ja no hi és
            g(paraula=2, estat="tret"),
        ])
        situats = grafics.situa(pla, inicis, finals, 10.0, ["scrapbook", "mac"], crida="comenta GUIA")
        frase, llista, etiqueta, crida = situats
        self.assertEqual((frase["inici"], frase["final"], frase["estil"], frase["amaga_subtitols"]), (0.5, 1.7, "scrapbook", True))
        self.assertEqual((llista["final"], llista["punts"][0]["t"], llista["amaga_subtitols"], llista["posicio"]),
                         (3.7, 2.0, True, "baix"))
        self.assertEqual(etiqueta["posicio"], "mig")  # dalt i baix ja hi ha la frase i la llista: va a un lloc lliure
        self.assertEqual((crida["inici"], crida["final"], crida["text"]), (6.5, 10.0, "comenta GUIA"))
        self.assertEqual(len(grafics.situa(pla, inicis, finals, 10.0, [], crida="")), 3)  # sense crida a la marca, no hi és

    def test_les_frases_del_video(self):
        paraules = [{"id": i, "text": t, "inici": i * 0.5, "final": i * 0.5 + 0.4, "conservada": i != 1}
                    for i, t in enumerate("Hola, eh, món. Una altra cosa".split())]
        paraules[4]["inici"], paraules[4]["final"] = 5.0, 5.4  # un silenci llarg també tanca la frase
        frases = grafics.frases([paraules], lambda t: t)
        self.assertEqual([(f["paraula"], f["fins"], f["text"]) for f in frases],
                         [(0, 2, "Hola, món."), (3, 3, "Una"), (4, 5, "altra cosa")])


class TestBlocDeColor(unittest.TestCase):
    """Amb `bloc`, el vídeo s'encongeix a baix sobre el color de la marca i el gràfic té l'espai de dalt."""

    def test_es_desa_nomes_si_es_vol(self):
        self.assertTrue(grafics.net(g(bloc=True))["bloc"])
        self.assertIsNone(grafics.net(g(bloc="sí"))["bloc"])  # el de cada tipus
        self.assertIsNone(grafics.net(g())["bloc"])

    def test_el_dibuix_va_a_dalt_i_sense_subtitols(self):
        d = grafics.dibuix(grafics.net({"tipus": "etiqueta", "paraula": 0, "text": "x", "bloc": True}), ["net"])
        self.assertEqual((d["bloc"], d["posicio"], d["amaga_subtitols"]), ("fosc", "mig", True))
        self.assertEqual(d["limits"], [269, grafics.BLOC["y"] - 40])  # tot sobre la targeta
        mac = grafics.dibuix(grafics.net(g(bloc=True, estil="mac", posicio="dalt", amaga_subtitols=False)), [])
        self.assertEqual((mac["bloc"], mac["posicio"], mac["amaga_subtitols"]), ("principal", "dalt", False))
        self.assertNotIn("bloc", grafics.dibuix(grafics.net(g()), []))

    def test_els_blocs_seguits_son_un_de_sol(self):
        paleta = {"fosc": "#111111", "principal": "#5E8B6B"}
        situats = [{"inici": 5.0, "final": 7.0, "bloc": "principal"}, {"inici": 1.0, "final": 3.0, "bloc": "fosc"},
                   {"inici": 3.5, "final": 4.0, "bloc": "principal"}, {"inici": 2.0, "final": 9.0}]
        self.assertEqual(grafics.blocs(situats, paleta),
                         [{"inici": 1.0, "final": 4.0, "color": "#111111"}, {"inici": 5.0, "final": 7.0, "color": "#5E8B6B"}])

    def test_l_animacio_entra_i_surt_suau(self):
        a = grafics.ANIMACIO_BLOC
        self.assertEqual([grafics.pas_bloc(t, 1, 5) for t in (0.5, 1, 3, 5, 6)], [0, 0, 1, 0, 0])
        self.assertAlmostEqual(grafics.pas_bloc(1 + a / 2, 1, 5), 0.5)
        self.assertAlmostEqual(grafics.pas_bloc(5 - a / 2, 1, 5), 0.5)
        self.assertLess(grafics.pas_bloc(1 + a / 4, 1, 5), 0.25)  # comença a poc a poc
        self.assertAlmostEqual(grafics.pas_bloc(1.25, 1, 1.5), 1)  # un de curt: arriba a baix just al mig

    def test_la_pagina_fa_la_mateixa_animacio(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("cal node")
        codi = (ARREL / "pagina" / "app.js").read_text(encoding="utf-8")
        inici = codi.index("const BLOC = ")
        tros = codi[inici:codi.index("function pintaBloc")]
        temps = [0.9, 1.1, 1.2, 2.0, 4.8, 4.9, 5.0]
        sortida = subprocess.run([node, "-e", tros + f"console.log(JSON.stringify([BLOC, ANIMACIO_BLOC, "
                                  f"{temps}.map((t) => pasBloc(t, 1, 5))]))"],
                                 capture_output=True, text=True, encoding="utf-8", check=True).stdout
        bloc, animacio, passos = json.loads(sortida)
        self.assertEqual(bloc, grafics.BLOC)
        self.assertEqual(animacio, grafics.ANIMACIO_BLOC)
        for t, p in zip(temps, passos):
            self.assertAlmostEqual(p, grafics.pas_bloc(t, 1, 5))

    def test_l_export_hi_posa_el_color_i_encongeix_el_video(self):
        from motor import exporta
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            video = d / "vermell.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=360x640:r=30:d=4",
                            "-f", "lavfi", "-i", "sine=d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                            "-shortest", str(video)], check=True)
            sortida = exporta.exporta(video, [(0.0, 4.0)], d / "s.mp4", "esborrany",
                                      blocs=[{"inici": 1.0, "final": 3.0, "color": "#0000FF"}])

            def pixel(t, x, y):  # en px de 1080 × 1920
                k = 720 / 1080
                rgb = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(sortida), "-frames:v", "1",
                                      "-vf", f"format=rgb24,crop=1:1:{round(x * k)}:{round(y * k)}", "-f", "rawvideo",
                                      "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
                return "blau" if rgb[2] > 180 and rgb[0] < 80 else "vermell" if rgb[0] > 180 and rgb[2] < 80 else rgb

            b = grafics.BLOC
            self.assertEqual(pixel(0.5, 540, 300), "vermell")  # abans del bloc, el vídeo sencer
            self.assertEqual(pixel(2.0, 540, 300), "blau")  # a dalt, el color
            self.assertEqual(pixel(2.0, 60, b["y"] + 400), "blau")  # al costat de la targeta, també
            self.assertEqual(pixel(2.0, 540, 1880), "blau")  # i a sota
            self.assertEqual(pixel(2.0, 540, b["y"] + b["h"] / 2), "vermell")  # i a la targeta, el vídeo
            self.assertEqual(pixel(3.5, 540, 300), "vermell")  # en acabar, torna a ser sencer
            self.assertEqual((exporta._color_ffmpeg("#abc"), exporta._color_ffmpeg("vermell")), ("0xAABBCC", "0x111111"))

    def test_un_bloc_tard_no_guarda_tot_el_video_a_la_memoria(self):
        # Una còpia del vídeo que comencés al bloc obligaria ffmpeg a guardar tots els fotogrames d'abans
        # (2 GB per a un bloc al segon 20 en 1080): el bloc es fa sobre el mateix vídeo, sense split ni trim.
        from motor import exporta
        filtre = exporta._filtre([(0.0, 60.0)], exporta._enquadrament(1080, 1920, 1080, 1920),
                                 blocs=[{"inici": 50.0, "final": 55.0, "color": "#000000"}], fps="30")
        bloc = filtre.split("[vb0];", 1)[1]
        self.assertNotIn("split", bloc)
        self.assertNotIn("trim", bloc)
        self.assertIn("shortest=1", bloc)  # el fons de color no allarga el vídeo


class TestWebIVentall(unittest.TestCase):
    """La captura d'una web en una finestra i les fotos en ventall: gràfics amb imatges del projecte."""

    def test_es_comproven(self):
        web = grafics.net({"tipus": "web", "paraula": 1, "imatge": "~/Desktop/captura.png", "text": "elmeuweb.cat"})
        self.assertEqual((web["imatge"], web["text"], web["bloc"]), ("~/Desktop/captura.png", "elmeuweb.cat", None))
        ventall = grafics.net({"tipus": "ventall", "paraula": 1, "punts": ["a.png", {"imatge": "b.jpg", "text": "abans", "paraula": 3}, {"text": "sense foto"}]})
        self.assertEqual(ventall["punts"], [{"imatge": "a.png", "text": "", "paraula": None},
                                            {"imatge": "b.jpg", "text": "abans", "paraula": 3}])
        self.assertEqual(grafics.net({"tipus": "ventall", "paraula": 1})["punts"], [])  # les fotos es poden pujar després
        with self.assertRaises(ValueError):
            grafics.net({"tipus": "web", "paraula": 1, "imatge": 3})

    def test_sense_imatge_no_surten_al_video(self):
        pla = grafics.neteja_llista([{"tipus": "web", "paraula": 0, "imatge": "abc.png"},
                                     {"tipus": "ventall", "paraula": 1, "punts": ["f1.jpg", "../fora.png", "f2.webp"]}])
        dibuix = grafics.dibuix(pla[0], [], imatges=set())
        self.assertEqual((dibuix["imatge"], dibuix["falta"], dibuix["bloc"], dibuix["amaga_subtitols"]), ("", True, "fosc", True))
        self.assertNotIn("falta", grafics.dibuix(pla[0], [], imatges={"abc.png"}))
        inicis, finals = {0: 0.0, 1: 2.0, 2: 3.0}, {0: 0.5, 1: 2.5, 2: 3.5}
        situats = grafics.situa(pla, inicis, finals, 10.0, [], imatges={"f2.webp", "fora.png"})
        self.assertEqual([g["tipus"] for g in situats], ["ventall"])  # la web no té la captura
        self.assertEqual([p["imatge"] for p in situats[0]["punts"]], ["f2.webp"])  # ni camins ni les que no hi són
        self.assertEqual(situats[0]["posicio"], "mig")

    def test_sense_bloc_si_es_diu(self):
        g = grafics.net({"tipus": "ventall", "paraula": 0, "punts": ["a.png"], "bloc": False})
        self.assertNotIn("bloc", grafics.dibuix(g, []))

    def test_el_que_surt_durant_un_bloc_va_sobre_la_targeta(self):
        pla = grafics.neteja_llista([{"tipus": "ventall", "paraula": 0, "punts": ["f1.jpg"]},
                                     {"tipus": "etiqueta", "paraula": 1, "text": "pas 1"},
                                     {"tipus": "etiqueta", "paraula": 2, "text": "després"}])
        inicis, finals = {0: 0.0, 1: 1.0, 2: 9.0}, {0: 0.5, 1: 1.5, 2: 9.5}
        ventall, durant, despres = grafics.situa(pla, inicis, finals, 12.0, [], imatges={"f1.jpg"})
        self.assertEqual(ventall["limits"], [269, grafics.BLOC["y"] - 40])
        self.assertEqual(durant["limits"], [grafics.BLOC["y"] + 30, 1228])  # no tapa el ventall de dalt
        self.assertNotEqual(despres["limits"], durant["limits"])  # quan el bloc ja ha acabat, com sempre
        # Per als altres editors, sense bloc: la web i el ventall, com un gràfic qualsevol.
        sense = grafics.situa(pla, inicis, finals, 12.0, [], imatges={"f1.jpg"}, sense_bloc=True)
        self.assertFalse(any(g.get("bloc") for g in sense))
        self.assertNotEqual(sense[1]["limits"], durant["limits"])

    def test_la_web_curta(self):
        self.assertEqual(grafics.adreca_curta("https://www.elmeuweb.cat/curs/?ref=ig#a"), "elmeuweb.cat/curs")


class TestZonaSegura(unittest.TestCase):
    def test_els_grafics_no_tapen_instagram_ni_els_subtitols(self):
        sub = {"posicio_y": 0.7, "mida": 0.075}
        self.assertEqual(grafics.limits(None, False), [269, 1248])  # el 14 % de dalt i el 35 % de baix, lliures
        dalt, baix = grafics.limits(sub, False)
        self.assertLess(baix, 0.7 * 1920 - 0.075 * 1080 / 2)  # per sobre dels subtítols
        self.assertGreater(grafics.limits(sub, True)[1], 0.7 * 1920)  # si els amaga, pot anar al seu lloc
        self.assertGreater(grafics.limits({"posicio_y": 0.2, "mida": 0.075}, False)[0], 0.2 * 1920)  # subtítols a dalt
        net = grafics.net(g(posicio=1.7))
        self.assertEqual(net["posicio"], 1.0)  # un número, de 0 a 1


class TestArranjaments(unittest.TestCase):
    """El que va trobar la revisió del codi."""

    def test_els_subtitols_apilats_ocupen_mes_d_una_linia(self):
        sub = {"posicio_y": 0.7, "mida": 0.075, "interlineat": 1.12, "disposicio": "apilat", "linies_max": 4}
        linies = [{"bloc": 1, "paraules": [{"text": "a"}]} for _ in range(5)]
        alcada = grafics.alcada_subtitols(sub, linies)
        self.assertAlmostEqual(alcada, 4 * 0.075 * 1080 * 1.12)  # com a molt linies_max
        self.assertLess(grafics.limits(sub, False, alcada)[1], 0.7 * 1920 - 0.7 * alcada)  # per sobre de tot el bloc
        escampat = grafics.alcada_subtitols({**sub, "disposicio": "escampat"}, [{"bloc": 1, "paraules": [{}] * 9}])
        self.assertAlmostEqual(escampat, 5 * 0.075 * 1080 * 1.12)  # files de dues paraules

    def test_un_lloc_exacte_tambe_ocupa_el_seu_lloc(self):
        pla = grafics.neteja_llista([{"tipus": "anotacio", "paraula": 0, "text": "jo", "posicio": 0.2},
                                     {"tipus": "etiqueta", "paraula": 0, "text": "pas 1"}])
        nota, etiqueta = grafics.situa(pla, {0: 0.0}, {}, 10.0, [])
        self.assertEqual((nota["posicio"], etiqueta["posicio"]), (0.2, "mig"))

    def test_el_final_ha_de_ser_del_mateix_bloc(self):
        pla = grafics.neteja_llista([g(paraula=1, fins=5)])
        inicis, finals = {1: 2.0, 5: 9.0}, {1: 2.4, 5: 9.4}
        self.assertEqual(grafics.situa(pla, inicis, finals, 20.0, [])[0]["final"], 9.7)
        separats = grafics.situa(pla, inicis, finals, 20.0, [], bloc_de={1: 0, 5: 1})  # en un reel, un altre tros
        self.assertEqual(separats[0]["final"], 2.0 + grafics.DURADES["frase"])

    def test_els_mantinguts_no_es_perden_si_la_transcripcio_es_mes_curta(self):
        actuals = [dict(grafics.net(g(paraula=50)), id="g1", estat="mantingut")]
        nou = grafics.fusiona(actuals, [g(paraula=2, text="nova")], paraules=10, manera="canvia")
        self.assertEqual([(x["id"], x["estat"]) for x in nou], [("g2", "proposat"), ("g1", "mantingut")])

    def test_un_estil_de_marca_d_abans_en_text(self):
        self.assertEqual(grafics.dibuix(grafics.net(g()), "mac")["estil"], "mac")

    @unittest.skipUnless(shutil.which("node"), "cal node")
    def test_el_numero_s_escriu_com_es_llegeix(self):
        casos = ["73 %", "10.000 €", "2,5 h", "+3 de cada 4", "1.250.000 persones"]
        xifres = [grafics.llegeix_xifra(c) for c in casos]
        codi = "".join((ARREL / "pagina" / f).read_text(encoding="utf-8") for f in ("subtitols.js", "grafics.js"))
        codi += f"\nconsole.log(JSON.stringify({json.dumps(xifres)}.map((x) => TallatGrafics.formata(x, x.valor))));"
        # Per l'entrada: a Windows, una ordre tan llarga (node -e …) passa del límit de la línia d'ordres.
        sortida = subprocess.run(["node"], input=codi, capture_output=True, text=True, encoding="utf-8",
                                 check=True).stdout
        self.assertEqual(json.loads(sortida), casos)  # el que compta la pàgina acaba igual que s'ha escrit


class TestMapaMuntatge(unittest.TestCase):
    def test_fa_el_mateix_que_abans_pero_rapid(self):
        import random
        from motor.projecte import mapa_muntatge

        def com_abans(t, trams):  # l'al_muntatge d'abans, tros a tros
            acum, posicions = 0.0, []
            for a, b in trams:
                posicions.append(acum)
                acum += b - a
            for k, (a, b) in enumerate(trams):
                if a - 0.01 <= t < b:
                    return posicions[k] + max(0.0, t - a)
            seguents = [k for k, (a, _) in enumerate(trams) if a > t]
            return posicions[min(seguents, key=lambda k: trams[k][0])] if seguents else None

        atzar = random.Random(7)
        for _ in range(200):
            trams, t = [], 0.0
            for _ in range(atzar.randint(1, 12)):
                t += atzar.choice([0.0, 0.005, 0.3, 1.0])
                d = atzar.uniform(0.2, 3)
                trams.append((round(t, 3), round(t + d, 3)))
                t += d
            if atzar.random() < 0.4:
                atzar.shuffle(trams)  # un reel: els trossos sonen en un altre ordre
            mapa = mapa_muntatge(trams)
            for _ in range(30):
                x = atzar.uniform(-1, t + 1)
                antic, nou = com_abans(x, trams), mapa(x)
                self.assertTrue(antic == nou or abs(antic - nou) < 1e-9, (trams, x, antic, nou))


class TestAlProjecte(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        casa = Path(self.dir.name)
        self.pegats = [mock.patch.object(marca, "KITS", casa / "kits"), mock.patch.object(marca, "USUARI", casa / "brand.json")]
        for p in self.pegats:
            p.start()
        self.carpeta = casa / "video"
        self.carpeta.mkdir()
        paraules = [{"id": i, "text": f"p{i}.", "inici": i * 1.0, "final": i * 1.0 + 0.5, "frase": i} for i in range(8)]
        (self.carpeta / "transcripcio.json").write_text(json.dumps(
            {"video": str(self.carpeta / "no-hi-es.mov"), "fps": "30", "durada": 8.0, "paraules": paraules}), encoding="utf-8")
        marca.desa("marca", {"color_principal": "#8A1C2B", "energia": ["editorial"], "crida": "segueix-me"})

    def tearDown(self):
        for p in self.pegats:
            p.stop()
        self.dir.cleanup()

    def test_el_grafic_segueix_la_seva_frase_quan_es_talla(self):
        p = Projecte(self.carpeta)
        p.estat["grafics"] = grafics.fusiona([], [g(paraula=4, text="aquí")])
        abans = p.grafics()[0]["inici"]
        p.estat["esborrades"] = {0: "usuari", 1: "usuari"}  # es treuen dues paraules d'abans
        despres = p.grafics()[0]
        self.assertLess(despres["inici"], abans - 1)
        self.assertAlmostEqual(despres["inici"], p.al_muntatge(4.0, p.trams()), places=3)  # quan es diu la paraula 4
        self.assertEqual(despres["estil"], "editorial")
        p.estat["esborrades"][4] = "usuari"  # la paraula mateixa: comença a la següent que es queda
        self.assertAlmostEqual(p.grafics()[0]["inici"], p.al_muntatge(5.0, p.trams()), places=3)

    def test_els_efectes_de_so_dels_grafics(self):
        p = Projecte(self.carpeta)
        p.estat["grafics"] = grafics.fusiona([], [g(paraula=2), {"tipus": "etiqueta", "paraula": 3, "text": "pas 1"},
                                                  {"tipus": "llista", "paraula": 4, "punts": ["a", "b"]}, {"tipus": "crida"}])
        pocs = {e["clau"]: e for e in so.esdeveniments([], [], None, "puja", [], "pocs", p.grafics())}
        self.assertEqual(sorted(pocs), ["grafic:g1", "grafic:g3", "grafic:g4"])  # sense l'etiqueta
        self.assertEqual((pocs["grafic:g1"]["so"], pocs["grafic:g4"]["so"]), ("whoosh", "brill"))
        molts = {e["clau"]: e for e in so.esdeveniments([], [], None, "puja", [], "molts", p.grafics())}
        self.assertIn("grafic:g2", molts)
        self.assertEqual(len(molts["grafic:g3"]["moments"]), 3)  # la targeta i cada punt

    def test_la_composicio_els_dibuixa_i_amaga_els_subtitols(self):
        p = Projecte(self.carpeta)
        p.estat["grafics"] = grafics.fusiona([], [g(paraula=2, fins=3)])
        situats = p.grafics()
        html = subtitols.composicio([], p.estil_subtitols(), 8.0, grafics=situats, paleta=grafics.paleta(p.estil()))
        self.assertIn('<script src="grafics.js"></script>', html)
        self.assertIn("TallatGrafics.construeix", html)
        self.assertIn('"principal": "#8A1C2B"', html)
        self.assertIn(f"amaga: [[{situats[0]['inici']}, {situats[0]['final']}]]", html)

    def test_les_imatges_del_pla_es_copien_al_projecte(self):
        p = Projecte(self.carpeta)
        foto = Path(self.dir.name) / "La meva foto.JPEG"
        foto.write_bytes(b"\xff\xd8 una foto")
        pla = p.importa_imatges([{"tipus": "ventall", "paraula": 1, "punts": [str(foto), {"imatge": str(foto), "text": "x"}]},
                                 {"tipus": "web", "paraula": 2, "imatge": "ja-hi-es.png"}, g(paraula=3)])
        nom = pla[0]["punts"][0]
        self.assertRegex(nom, r"^[0-9a-f]{16}\.jpg$")
        self.assertEqual(pla[0]["punts"][1], {"imatge": nom, "text": "x"})  # la mateixa foto, el mateix nom
        self.assertEqual(pla[1]["imatge"], "ja-hi-es.png")
        self.assertTrue((p.carpeta_imatges / nom).is_file())
        with self.assertRaises(ValueError):
            p.importa_imatges([{"tipus": "web", "paraula": 1, "imatge": "/no/hi/es.png"}])
        p.estat["grafics"] = grafics.fusiona([], pla)
        self.assertEqual([x["tipus"] for x in p.grafics()], ["ventall", "frase"])  # la web: no hi ha la captura
        dibuixos = p.dibuixos_grafics()
        self.assertTrue(dibuixos["g2"]["falta"])

    def test_la_composicio_porta_les_imatges(self):
        p = Projecte(self.carpeta)
        foto = Path(self.dir.name) / "foto.png"
        foto.write_bytes(b"png")
        p.estat["grafics"] = grafics.fusiona([], p.importa_imatges([{"tipus": "web", "paraula": 1, "imatge": str(foto)}]))
        situats = p.grafics()
        with mock.patch.object(subtitols.subprocess, "run", side_effect=RuntimeError("prou")):
            with self.assertRaises(RuntimeError):
                subtitols.renderitza([], p.estil_subtitols(), 8.0, p.carpeta, "esborrany", grafics=situats,
                                     paleta=grafics.paleta(p.estil()), imatges=p.carpeta_imatges)
        copiades = list((p.carpeta / "subtitols").glob("*/imatges/*.png"))
        self.assertEqual([c.name for c in copiades], [situats[0]["imatge"]])

    def test_l_ordre_del_xat(self):
        import tallat
        pla = self.carpeta / "pla.json"
        pla.write_text(json.dumps([g(paraula=2, text="la *clau*", motiu="la idea central"), {"tipus": "crida"}]),
                       encoding="utf-8")
        args = dict(projecte=str(self.carpeta), fitxer=str(pla), de_nou=False, json=False)
        sortida = io.StringIO()
        with contextlib.redirect_stdout(sortida):
            tallat.ordre_grafics(argparse.Namespace(accio="proposa", **args))
        text = sortida.getvalue()
        self.assertIn("estil dels gràfics «editorial»", text)
        self.assertIn("p2.", text)  # les frases, per fer el pla
        self.assertIn("g1  frase", text)
        estat = Projecte(self.carpeta).estat
        self.assertEqual(([x["id"] for x in estat["grafics"]], estat["revisio"]), (["g1", "g2"], 1))
        pla.write_text(json.dumps([{"tipus": "frase", "text": "x"}]), encoding="utf-8")
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stdout(io.StringIO()):
            tallat.ordre_grafics(argparse.Namespace(accio="canvia", **args))
        self.assertIn("paraula", str(e.exception))

    def test_un_sticker_amb_imatge_surt_encara_que_estigui_pendent(self):
        # Del feedback: s'havien pujat les imatges, s'havia tocat el ✓ (que desmarca) i no van sortir al vídeo.
        (self.carpeta / "stickers").mkdir()
        for k in range(3):
            (self.carpeta / "stickers" / f"s{k}.png").write_bytes(b"png")
        (self.carpeta / "instruccions.json").write_text(json.dumps([
            {"id": f"s{k}", "tipus": "sticker", "text": "sticker", "paraules": None, "inici": k, "final": k,
             "ancora": k + 1, "estat": estat, "manual": True, "fitxer": f"stickers/s{k}.png"}
            for k, estat in enumerate(("acceptada", "pendent", "descartada"))]), encoding="utf-8")
        p = Projecte(self.carpeta)
        self.assertEqual([x["id"] for x in p.stickers(p.trams())], ["s0", "s1"])  # el descartat, no

    def test_un_pla_mal_escrit_no_trenca_res(self):
        (self.carpeta / "edicio.json").write_text(json.dumps({"grafics": [{"tipus": "frase", "paraula": 1},
                                                                          {"tipus": "llista"}, g(paraula=3)]}),
                                                  encoding="utf-8")
        p = Projecte(self.carpeta)
        self.assertEqual([x["text"] for x in p.grafics()], ["una idea"])  # els que no s'entenen, fora

    def test_el_projecte_per_a_editors_porta_els_grafics(self):
        from motor import editors
        p = Projecte(self.carpeta)
        p.estat["grafics"] = grafics.fusiona([], [g(paraula=2)])
        with tempfile.TemporaryDirectory() as d:
            capa = Path(d) / "capa.mov"
            capa.write_bytes(b"mov")
            with mock.patch.object(editors, "_plan", return_value={}), mock.patch.object(editors, "_copia_recursos"), \
                    mock.patch.object(editors, "fcpxml", return_value=""), mock.patch.object(editors, "xmeml", return_value=""), \
                    mock.patch.object(editors, "_efectes"), \
                    mock.patch.object(p, "sortida", return_value=Path(d) / "editors.mp4"), \
                    mock.patch.object(editors.subtitols, "renderitza", return_value=capa) as dibuixa:
                editors.exporta_editors(p, amb_capa=True)
        self.assertEqual([x["id"] for x in dibuixa.call_args.kwargs["grafics"]], ["g1"])
        self.assertIn("principal", dibuixa.call_args.kwargs["paleta"])

    def test_la_pagina_no_hi_pot_ficar_brossa(self):
        estat = servidor._estat_de_json({"grafics": [g(estat="canvia", nota="x" * 900), {"tipus": "<script>"}, 5]})
        self.assertEqual(len(estat["grafics"]), 1)
        self.assertEqual((estat["grafics"][0]["estat"], len(estat["grafics"][0]["nota"])), ("canvia", grafics.MIDA_NOTA))


if __name__ == "__main__":
    unittest.main()
