import unittest

from motor import marca, subtitols

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

    def test_cap_linia_passa_del_final(self):
        p = paraules(("final", 0.0, 0.9))
        self.assertLessEqual(subtitols.grups(p, [(0, 1)], ESTIL)[-1]["final"], 1.0)

    def test_composicio_registra_el_timeline(self):
        p = paraules(("Hola", 0.0, 0.4))
        html = subtitols.composicio(subtitols.grups(p, [(0, 1)], ESTIL), ESTIL, 1.0)
        self.assertIn('data-composition-id="subtitols"', html)
        self.assertIn('window.__timelines["subtitols"] = tl', html)

    def test_composicio_segons_l_estil(self):
        p = paraules(("Hola", 0.0, 0.4), ("món", 0.5, 0.9))
        linies = subtitols.grups(p, [(0, 1)], ESTIL)
        # Per defecte: cada paraula entra amb un salt quan sona, i la que sona canvia de color.
        html = subtitols.composicio(linies, ESTIL, 1.0)
        self.assertIn('tl.fromTo("#p0-1"', html)
        self.assertIn("back.out", html)
        self.assertIn("color: ACTIU", html)
        # Tota la línia de cop, amb fos i sense destacar.
        estil = dict(ESTIL, apareixen="linia", animacio="fos", destaca=False)
        html = subtitols.composicio(linies, estil, 1.0)
        self.assertIn('tl.fromTo("#l0 .p"', html)
        self.assertNotIn('tl.fromTo("#p0-1"', html)
        self.assertIn("power1.out", html)
        self.assertNotIn("color: ACTIU", html)

    def test_nom_de_font_amb_espais(self):
        html = subtitols.composicio([], dict(ESTIL, font="Avenir Next"), 1.0)
        self.assertIn('font-family: "Avenir Next", sans-serif', html)
        html = subtitols.composicio([], dict(ESTIL, font='x"; } body {'), 1.0)
        self.assertNotIn("} body {", html.split("<style>")[1].split("</style>")[0].replace("html, body {", ""))


if __name__ == "__main__":
    unittest.main()
