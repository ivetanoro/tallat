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
