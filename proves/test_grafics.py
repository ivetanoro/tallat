import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from motor import grafics, marca, servidor, so, subtitols
from motor.projecte import Projecte


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
        for dolent, paraula in (({"tipus": "notificacio", "paraula": 0}, "Tipus"), ({"tipus": "frase", "text": "x"}, "paraula"),
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
        self.assertEqual([(x["id"], x["text"]) for x in nou], [("g1", "z")])
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

    def test_la_pagina_no_hi_pot_ficar_brossa(self):
        estat = servidor._estat_de_json({"grafics": [g(estat="canvia", nota="x" * 900), {"tipus": "<script>"}, 5]})
        self.assertEqual(len(estat["grafics"]), 1)
        self.assertEqual((estat["grafics"][0]["estat"], len(estat["grafics"][0]["nota"])), ("canvia", grafics.MIDA_NOTA))


if __name__ == "__main__":
    unittest.main()
