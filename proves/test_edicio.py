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

    def test_les_recuperades_de_fora_sonen_on_les_mostra_la_pagina(self):
        # Al final, com a la pàgina: abans s'afegien al tros d'abans (o al primer de la gravació) i el
        # vídeo saltava a un text que a la pàgina era molt més avall.
        p = self.paraules()
        p[2]["conservada"] = True
        t = edicio.trams(p, fps=30, durada=10, ordre=[[4, 5], [2, 3]])  # 0 i 1, recuperades
        self.assertEqual([round(a) for a, b in t], [4, 2, 0])

    def test_sense_pausa_maxima_no_peta_entre_blocs(self):
        p = self.paraules()
        edicio.trams(p, fps=30, durada=10, pausa_maxima=None, ordre=[[3, 3], [4, 5]])


class TestSilenciReal(unittest.TestCase):
    """Un silenci entre paraules només s'escurça si al so hi ha silenci de debò."""

    def paraules(self):
        return [{"id": 0, "text": "tu.", "inici": 0.0, "final": 0.5, "frase": 0, "conservada": True},
                {"id": 1, "text": "Vull", "inici": 1.5, "final": 2.0, "frase": 1, "conservada": True}]

    def veu(self, fins):
        import numpy as np
        v = np.zeros(300, dtype=bool)
        v[0:int(fins * 100)] = True       # veu des de 0 fins a «fins»
        v[150:200] = True                 # «Vull»
        return v

    def test_si_la_veu_continua_no_es_talla(self):
        t = edicio.trams(self.paraules(), fps=30, durada=3, pausa_maxima=0.35, veu=self.veu(1.25))
        self.assertEqual(len(t), 1)  # només hi ha 0,25 s de silenci real

    def test_es_talla_dins_del_silenci_real(self):
        t = edicio.trams(self.paraules(), fps=30, durada=3, pausa_maxima=0.35, veu=self.veu(0.8))
        self.assertEqual(len(t), 2)
        self.assertGreaterEqual(t[0][1], 0.8)  # el primer tros arriba fins on acaba la veu


class TestFiDeLaVeu(unittest.TestCase):
    def paraules(self):
        return [{"id": 0, "text": "gravat.", "inici": 0.0, "final": 0.4, "frase": 0, "conservada": True},
                {"id": 1, "text": "I", "inici": 1.3, "final": 1.5, "frase": 1, "conservada": False}]

    def test_allarga_fins_on_acaba_la_veu_si_hi_ha_silenci_abans_de_la_treta(self):
        import numpy as np
        v = np.zeros(200, dtype=bool)
        v[0:85] = True      # «gravat» sona fins a 0,85 (l'alineador deia 0,4)
        v[125:150] = True   # «I» (treta)
        t = edicio.trams(self.paraules(), fps=30, durada=2, veu=v)
        self.assertGreaterEqual(t[0][1], 0.85 - 1 / 30)
        self.assertLessEqual(t[0][1], 1.3)

    def test_sense_silenci_entremig_no_allarga(self):
        import numpy as np
        v = np.ones(200, dtype=bool)  # tot és veu: no sabem de qui és el so
        t = edicio.trams(self.paraules(), fps=30, durada=2, veu=v)
        self.assertLessEqual(t[0].so[1], 0.45)  # el so no s'allarga (el fotograma sencer sí, en silenci)
        self.assertLessEqual(t[0][1], 0.45 + 1 / 30)


class TestTramsPerALaPagina(unittest.TestCase):
    def test_un_canvi_nomes_de_so_es_veu(self):
        # Revisió de Codex: la pàgina només veia els fotogrames i no refeia la vista prèvia.
        abans = edicio.trams_json([edicio.Tram(0.4, 0.833333, so=(0.4, 0.811))])
        despres = edicio.trams_json([edicio.Tram(0.4, 0.833333, so=(0.4, 0.829))])
        self.assertNotEqual(abans, despres)
        self.assertEqual(abans, [[0.4, 0.833333, 0.4, 0.811]])
