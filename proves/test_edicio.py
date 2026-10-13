import unittest

from motor import edicio


def paraules(*specs):
    return [{"id": i, "text": t, "inici": a, "final": b, "frase": f}
            for i, (t, a, b, f) in enumerate(specs)]


P = paraules(("Hola,", 1.0, 1.4, 0), ("eh,", 1.6, 2.0, 0), ("com", 2.2, 2.4, 0),
             ("estàs?", 2.5, 3.0, 0), ("Bé.", 4.0, 4.3, 1))


class TestEdicio(unittest.TestCase):
    def test_text_editable_separa_frases(self):
        self.assertEqual(edicio.text_editable(P), "Hola, eh, com estàs?\n\nBé.\n")

    def test_sense_canvis_ho_conserva_tot(self):
        r, avisos = edicio.compara(P, edicio.text_editable(P))
        self.assertTrue(all(p["conservada"] for p in r))
        self.assertEqual(avisos, [])

    def test_esborrar_una_paraula_fa_dos_trossos(self):
        r, _ = edicio.compara(P, "Hola, com estàs?\n\nBé.")
        self.assertEqual([p["conservada"] for p in r], [True, False, True, True, True])
        t = edicio.trams(r, fps=30, durada=10)
        self.assertEqual(len(t), 2)
        self.assertLessEqual(t[0][1], 1.6 + 1 / 30)   # el tall no entra a «eh»
        self.assertGreaterEqual(t[1][0], 2.0 - 1 / 30)

    def test_res_de_la_paraula_esborrada_es_cola(self):
        r, _ = edicio.compara(P, "Hola, com estàs?\n\nBé.")
        t = edicio.trams(r, fps=29.97, durada=10)
        self.assertLessEqual(t[0][1], 1.6)   # «eh,» comença a 1,6
        self.assertGreaterEqual(t[1][0], 2.0)  # i acaba a 2,0

    def test_correccio_ortografica_no_talla(self):
        r, avisos = edicio.compara(P, "Hola, eh, com estas?\n\nBé.")
        self.assertTrue(all(p["conservada"] for p in r))
        self.assertEqual(r[3]["correccio"], "estas?")
        self.assertEqual(avisos, [])

    def test_paraula_nova_genera_avis(self):
        _, avisos = edicio.compara(P, "Hola, eh, com estàs? molt\n\nBé.")
        self.assertEqual(len(avisos), 1)

    def test_trams_ajustats_a_fotogrames(self):
        r, _ = edicio.compara(P, "Hola,")
        (a, b), = edicio.trams(r, fps=30, durada=10)
        self.assertAlmostEqual(a * 30, round(a * 30), places=2)
        self.assertAlmostEqual(b * 30, round(b * 30), places=2)


if __name__ == "__main__":
    unittest.main()


class TestOrdre(unittest.TestCase):
    """Reels muntats: els trossos sonen en l'ordre indicat, no en el de la gravació."""

    def paraules(self):
        # 0..5, una per segon; totes conservades excepte la 2
        return [{"id": i, "text": f"p{i}", "inici": float(i), "final": i + 0.5, "frase": 0,
                 "conservada": i != 2} for i in range(6)]

    def test_ordre_invertit(self):
        p = self.paraules()
        p[3]["conservada"] = False
        t = edicio.trams(p, fps=30, durada=10, ordre=[[4, 5], [0, 1]])
        self.assertEqual(len(t), 2)
        self.assertGreater(t[0][0], t[1][0])  # primer sona el tros de més tard

    def test_paraula_recuperada_fora_dels_trossos(self):
        p = self.paraules()
        t = edicio.trams(p, fps=30, durada=10, ordre=[[0, 1]])  # 3, 4 i 5 conservades però fora
        self.assertEqual(len(t), 2)  # el tros [0-1] i, després, el [3-5]
        self.assertLess(t[0][0], t[1][0])

    def test_sense_pausa_maxima_no_peta_entre_blocs(self):
        p = self.paraules()
        edicio.trams(p, fps=30, durada=10, pausa_maxima=None, ordre=[[3, 3], [4, 5]])
