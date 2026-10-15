import tempfile
import unittest
from pathlib import Path
from unittest import mock

from motor import edicio, marca, subtitols

ESTIL = marca.carrega(marca.PER_DEFECTE)["subtitols"]


def paraules(*specs):
    """specs: (text, inici, final[, conservada])"""
    return [{"id": i, "text": s[0], "inici": s[1], "final": s[2], "frase": 0,
             "conservada": s[3] if len(s) > 3 else True} for i, s in enumerate(specs)]


class TestGrups(unittest.TestCase):
    def test_temps_al_muntatge_salta_el_que_es_treu(self):
        p = paraules(("Hola,", 1.0, 1.4), ("eh,", 1.6, 2.0, False), ("com", 2.2, 2.4), ("estàs?", 2.5, 3.0))
        linies = subtitols.grups(p, [(0.96, 1.6), (2.0, 3.04)], ESTIL)
        textos = [w["text"] for l in linies for w in l["paraules"]]
        self.assertEqual(textos, ["Hola", "com", "estàs?"])  # sense coma, amb interrogant
        com = linies[0]["paraules"][1]
        self.assertAlmostEqual(com["inici"], 0.64 + (2.2 - 2.0), places=3)

    def test_maxim_de_paraules_per_linia(self):
        p = paraules(*[(f"p{i}", i * 0.3, i * 0.3 + 0.25) for i in range(7)])
        linies = subtitols.grups(p, [(0, 3)], dict(ESTIL, paraules_per_linia=3))
        self.assertEqual([len(l["paraules"]) for l in linies], [3, 3, 1])

    def test_final_de_frase_i_pausa_obren_linia(self):
        p = paraules(("Sí.", 0.0, 0.3), ("Molt", 0.4, 0.6), ("bé", 0.7, 0.9), ("ara", 2.0, 2.2))
        linies = subtitols.grups(p, [(0, 3)], ESTIL)
        self.assertEqual([[w["text"] for w in l["paraules"]] for l in linies], [["Sí"], ["Molt", "bé"], ["ara"]])

    def test_correccio_es_fa_servir(self):
        p = paraules(("satura", 0.0, 0.4))
        p[0]["correccio"] = "s'atura"
        self.assertEqual(subtitols.grups(p, [(0, 1)], ESTIL)[0]["paraules"][0]["text"], "s'atura")

    def test_paraula_que_comenca_abans_del_tros_arrodonit(self):
        # Segona revisió de Codex: el tall s'arrodoneix a 0,4333 s i «Hola» (0,401 s) desapareixia dels subtítols.
        for fps in (30, 30000 / 1001):
            p = paraules(("eh", 0.0, 0.401, False), ("Hola", 0.401, 0.8))
            trams = edicio.trams(p, fps=fps, durada=1.0)
            linies = subtitols.grups(p, trams, ESTIL)
            self.assertEqual([m["text"] for l in linies for m in l["paraules"]], ["Hola"])
            self.assertEqual(linies[0]["inici"], 0.0)

    def test_cap_linia_passa_del_final(self):
        p = paraules(("final", 0.0, 0.9))
        self.assertLessEqual(subtitols.grups(p, [(0, 1)], ESTIL)[-1]["final"], 1.0)

    def test_composicio_registra_el_timeline(self):
        p = paraules(("Hola", 0.0, 0.4))
        html = subtitols.composicio(subtitols.grups(p, [(0, 1)], ESTIL), ESTIL, 1.0)
        self.assertIn('data-composition-id="subtitols"', html)
        self.assertIn('window.__timelines["subtitols"] = tl', html)

    def test_composicio_fa_servir_el_codi_compartit(self):
        p = paraules(("Hola", 0.0, 0.4), ("món", 0.5, 0.9))
        linies = subtitols.grups(p, [(0, 1)], ESTIL)
        estil = dict(ESTIL, apareixen="linia", animacio="impacte")
        html = subtitols.composicio(linies, estil, 1.0, escala=0.5)
        self.assertIn('<script src="subtitols.js"></script>', html)
        self.assertIn("TallatSubtitols.construeix(", html)
        self.assertIn('"animacio": "impacte"', html)
        self.assertIn('"text": "món"', html)
        self.assertIn("transform: scale(0.5)", html)
        self.assertTrue(subtitols.CODI_ANIMACIO.exists())

    def test_res_del_text_trenca_el_script(self):
        p = paraules(("</script><b>", 0.0, 0.4))
        html = subtitols.composicio(subtitols.grups(p, [(0, 1)], ESTIL), ESTIL, 1.0)
        self.assertNotIn("</script><b>", html)

    def test_nom_de_font_amb_espais(self):
        self.assertEqual(subtitols.familia_css(dict(ESTIL, font="Avenir Next")), '"Avenir Next", system-ui, sans-serif')
        self.assertEqual(subtitols.familia_css(dict(ESTIL, font="system-ui")), "system-ui, sans-serif")
        self.assertNotIn("}", subtitols.familia_css(dict(ESTIL, font='x"; } body {')))
        # Les lletres del kit es declaren amb @font-face, amb el seu nom i el seu gruix.
        html = subtitols.composicio([], dict(ESTIL, font="Poppins"), 1.0,
                                    fonts=[{"familia": "Poppins", "pes": "700", "src": "font0.woff2"},
                                           {"familia": "Inter", "pes": "100 1000", "src": "font1.woff2"}])
        self.assertIn("""@font-face { font-family: "Poppins"; src: url('font0.woff2'); font-weight: 700;""", html)
        self.assertIn("""font-family: "Inter"; src: url('font1.woff2'); font-weight: 100 1000;""", html)


class TestParaulesClau(unittest.TestCase):
    def test_numeros_i_paraula_important(self):
        p = paraules(("en", 0.0, 0.1), ("tinc", 0.2, 0.3), ("25", 0.4, 0.5), ("de", 0.6, 0.7), ("música", 0.8, 0.9))
        linia = subtitols.grups(p, [(0, 1)], dict(ESTIL, paraules_per_linia=7, lletres_per_linia=40))[0]
        claus = [w["text"] for w in linia["paraules"] if w["clau"]]
        self.assertEqual(claus, ["25", "música"])
        self.assertEqual([w["emoji"] for w in linia["paraules"]], [None, None, None, None, "🎵"])

    def test_emojis(self):
        self.assertEqual(subtitols.emoji_de("d'idees,"), "💡")
        self.assertEqual(subtitols.emoji_de("Minuts"), "⏰")  # «minut*» vol dir qualsevol paraula que comenci així
        self.assertIsNone(subtitols.emoji_de("que"))


class TestMemoriaDelRender(unittest.TestCase):
    def test_canviar_la_font_amb_el_mateix_nom_torna_a_dibuixar(self):
        # Revisió de Codex: la vista prèvia ja feia servir la font nova, però el vídeo reaprofitava el dibuix vell.
        dibuixos = []

        def hyperframes(ordre, **_):
            sortida = Path(ordre[ordre.index("--output") + 1])
            sortida.write_bytes(b"mov")
            dibuixos.append(sortida)
            return mock.Mock(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(subtitols.subprocess, "run", hyperframes):
            font = Path(d) / "La Meva.ttf"
            font.write_bytes(b"lletra antiga")
            estil = {**ESTIL, "font": "La Meva"}
            fonts = [{"familia": "La Meva", "pes": "100 1000", "fitxer": font}]
            linies = [{"inici": 0.0, "final": 1.0, "paraules": [{"text": "hola", "inici": 0.0, "final": 1.0}]}]
            primer = subtitols.renderitza(linies, estil, 1.0, Path(d), "esborrany", fonts=fonts)
            self.assertEqual(subtitols.renderitza(linies, estil, 1.0, Path(d), "esborrany", fonts=fonts), primer)
            self.assertEqual(len(dibuixos), 1)
            font.write_bytes(b"lletra nova")
            self.assertNotEqual(subtitols.renderitza(linies, estil, 1.0, Path(d), "esborrany", fonts=fonts), primer)
            self.assertEqual(len(dibuixos), 2)


def frase(text: str, pas: float = 0.3):
    return paraules(*[(w, i * pas, i * pas + pas - 0.05) for i, w in enumerate(text.split())])


class TestDisseny(unittest.TestCase):
    """Les peces dels estils dissenyats: paraules destacades soles, línies apilades i triades a mà."""

    def test_les_destacades_van_soles_a_la_seva_linia(self):
        estil = dict(ESTIL, clau_grans=True, clau_sola=True, paraules_per_linia=3)
        linies = subtitols.grups(frase("is as ambitious or entrepreneurial"), [(0, 5)], estil)
        self.assertEqual([[w["text"] for w in l["paraules"]] for l in linies],
                         [["is", "as"], ["ambitious"], ["or"], ["entrepreneurial"]])
        self.assertEqual([l["paraules"][0]["clau"] for l in linies], [False, True, False, True])

    def test_apilades_es_queden_fins_al_final_de_la_frase(self):
        estil = dict(ESTIL, disposicio="apilat", paraules_per_linia=2, linies_max=4)
        p = frase("una dues tres quatre cinc.") + [
            {"id": 5, "text": "sis", "inici": 3.0, "final": 3.2, "frase": 1, "conservada": True}]
        linies = subtitols.grups(p, [(0, 4)], estil)
        self.assertEqual([[w["text"] for w in l["paraules"]] for l in linies],
                         [["una", "dues"], ["tres", "quatre"], ["cinc"], ["sis"]])
        self.assertEqual([l["bloc"] for l in linies], [0, 0, 0, 1])  # la frase nova, en un bloc nou
        self.assertEqual(len({l["final"] for l in linies[:3]}), 1)  # les tres es queden fins al final del bloc
        self.assertLess(linies[0]["inici"], linies[1]["inici"])

    def test_un_bloc_no_passa_del_maxim_de_linies(self):
        estil = dict(ESTIL, disposicio="apilat", paraules_per_linia=1, linies_max=3)
        linies = subtitols.grups(frase("a1 b2 c3 d4 e5"), [(0, 5)], estil)
        self.assertEqual([l["bloc"] for l in linies], [0, 0, 0, 1, 1])

    def test_escampades_tambe_van_per_frases(self):
        estil = dict(ESTIL, disposicio="escampat", paraules_per_linia=2, linies_max=4)
        linies = subtitols.grups(frase("una dues tres quatre cinc."), [(0, 4)], estil)
        self.assertEqual([l["bloc"] for l in linies], [0, 0, 0])
        self.assertEqual(len({l["final"] for l in linies}), 1)
        self.assertEqual(marca.valida("subtitols", {"disposicio": "escampat"}), {"disposicio": "escampat"})

    def test_sense_apilar_cada_linia_acaba_quan_comenca_la_seguent(self):
        linies = subtitols.grups(frase("una dues tres quatre"), [(0, 5)], dict(ESTIL, paraules_per_linia=2))
        self.assertEqual(linies[0]["final"], linies[1]["inici"])

    def test_les_triades_a_ma_manen(self):
        p = frase("tinc una idea genial")
        p[3]["destacada"] = True   # «genial», sí
        p[2]["destacada"] = False  # «idea», no (tallat l'hauria triat)
        linies = subtitols.grups(p, [(0, 5)], dict(ESTIL, clau_grans=True, paraules_per_linia=4, lletres_per_linia=30))
        self.assertEqual([(w["text"], w["clau"]) for w in linies[0]["paraules"]],
                         [("tinc", False), ("una", False), ("idea", False), ("genial", True)])
        self.assertEqual([w["id"] for w in linies[0]["paraules"]], [0, 1, 2, 3])

    def test_l_estat_guarda_les_destacades(self):
        estat = edicio.estat_buit()
        estat["destacades"] = {3: True, 1: False}
        with tempfile.TemporaryDirectory() as d:
            edicio.desa_estat(estat, Path(d) / "edicio.json")
            llegit = edicio.llegeix_estat(Path(d) / "edicio.json")
        self.assertEqual(llegit["destacades"], {3: True, 1: False})
        aplicades = edicio.aplica(frase("a b c d"), llegit)
        self.assertEqual([x.get("destacada") for x in aplicades], [None, False, None, True])

    def test_estils_nous_valids(self):
        ids = {e["id"] for e in marca.estils()}
        self.assertTrue({"apilat", "esglao", "titular", "retol", "escampat"} <= ids)
        for e in marca.estils():  # tots porten la base comuna
            self.assertIn("disposicio", e["valors"])


class TestTitol(unittest.TestCase):
    """El títol del ganxo: text del vídeo, estil del kit, dibuixat amb el mateix codi."""

    def test_el_titol_es_neteja(self):
        self.assertEqual(edicio.titol_net({"text": "  #3 canvis \r\n *ser creadora*\n", "durada": 99}),
                         {"text": "#3 canvis\n*ser creadora*", "durada": 10.0})
        for dolent in (None, {}, {"text": "   "}, {"text": 3}, "text"):
            self.assertIsNone(edicio.titol_net(dolent))
        self.assertIsNone(edicio.titol_net({"text": "hola", "durada": True})["durada"])

    def test_la_composicio_porta_el_titol(self):
        titol = {"text": "#3 canvis\n*ser creadora*", "inici": 0.0, "final": 3.0}
        estil_titol = dict(marca.carrega(marca.PER_DEFECTE)["titol"], amaga_subtitols=True, font="Fraunces")
        html = subtitols.composicio([], ESTIL, 5.0, titol=titol, estil_titol=estil_titol)
        self.assertIn('TallatSubtitols.titol(document.getElementById("titol")', html)
        self.assertIn('amaga: [0.0, 3.0]', html)  # sense subtítols mentre surt el títol
        self.assertIn('familia: "\\"Fraunces\\", system-ui', html)  # la lletra del títol, en JSON
        self.assertNotIn("TallatSubtitols.titol(", subtitols.composicio([], ESTIL, 5.0))

    def test_estils_de_titol_valids(self):
        for e in marca.estils_titol():
            with self.subTest(estil=e["id"]):
                self.assertEqual(marca.valida("titol", e["valors"]), e["valors"])
        self.assertEqual(marca.valida("titol", {"font": None, "animacio": "maquina"}), {"font": None, "animacio": "maquina"})
        self.assertEqual(marca.valida("titol", {"corba": 3, "corba_linies": "totes"}), {"corba": 1.0, "corba_linies": "totes"})
        for dolent in ({"animacio": "explota"}, {"fons": "neó"}, {"font": "x; }"}, {"corba_linies": "la tercera"}):
            with self.assertRaises(ValueError):
                marca.valida("titol", dolent)


if __name__ == "__main__":
    unittest.main()
