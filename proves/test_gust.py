import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from motor import gust, marca, neteja


class TestGust(unittest.TestCase):
    """Cada prova fa servir fitxers temporals: no toca mai la configuració de la persona."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = Path(self.dir.name)
        shutil.copy(marca.PER_DEFECTE, d / "brand.json")
        shutil.copy(neteja.LLISTA_PER_DEFECTE, d / "farciment.txt")
        self.pegats = [mock.patch.object(marca, "USUARI", d / "brand.json"),
                       mock.patch.object(neteja, "LLISTA_USUARI", d / "farciment.txt"),
                       mock.patch.object(gust, "FITXER", d / "gust.json")]
        for p in self.pegats:
            p.start()

    def tearDown(self):
        for p in self.pegats:
            p.stop()
        self.dir.cleanup()

    def test_regla_amb_ajust_s_aplica_i_es_desfa(self):
        regla = gust.afegeix("subtitols", "Subtítols més grans", "subtitols.mida=0.09")
        self.assertEqual(marca.carrega()["subtitols"]["mida"], 0.09)
        self.assertEqual(regla["ajust"]["abans"], 0.075)
        _, desfet = gust.treu(regla["id"])
        self.assertTrue(desfet)
        self.assertEqual(marca.carrega()["subtitols"]["mida"], 0.075)
        self.assertEqual(gust.llegeix(), [])

    def test_si_algu_ho_ha_tornat_a_canviar_no_es_desfa(self):
        regla = gust.afegeix("subtitols", "Subtítols més grans", "subtitols.mida=0.09")
        marca.desa("subtitols", {"mida": 0.1})  # després la persona l'ha canviat a la pàgina
        _, desfet = gust.treu(regla["id"])
        self.assertFalse(desfet)
        self.assertEqual(marca.carrega()["subtitols"]["mida"], 0.1)

    def test_la_mateixa_opcio_no_es_repeteix(self):
        gust.afegeix("subtitols", "Més grans", "subtitols.mida=0.09")
        gust.afegeix("subtitols", "Encara més grans", "subtitols.mida=0.11")
        regles = gust.llegeix()
        self.assertEqual(len(regles), 1)
        self.assertEqual(regles[0]["ajust"]["abans"], 0.075)  # el valor original, per poder-lo recuperar
        gust.afegeix("reels", "Prefereixo reels curts")
        gust.afegeix("reels", "prefereixo reels curts")
        self.assertEqual(len(gust.llegeix()), 2)

    def test_farciment(self):
        self.assertEqual(neteja.seccio_de("vale"), "proposa")
        regla = gust.afegeix("talls", "No em treguis mai els «vale»", "farciment.deixa=vale")
        self.assertIsNone(neteja.seccio_de("vale"))
        gust.afegeix("talls", "Treu sempre «o sigui»", "farciment.treu=o sigui")
        self.assertEqual(neteja.seccio_de("O sigui"), "treu")
        self.assertIn(("eh",), neteja.carrega_llista()["treu"])  # la resta de la llista hi continua
        gust.treu(regla["id"])
        self.assertEqual(neteja.seccio_de("vale"), "proposa")
        self.assertIn("# Sons de dubte", (Path(self.dir.name) / "farciment.txt").read_text(encoding="utf-8"))

    def test_ajustos_dolents(self):
        for ajust in ("subtitols.mida", "subtitols.color=vermell", "secreta.x=1", "farciment.esborra=vale",
                      "broll.lut=/etc/passwd"):
            with self.subTest(ajust=ajust), self.assertRaises(ValueError):
                gust.afegeix("altres", "Prova", ajust)
        with self.assertRaises(ValueError):
            gust.afegeix("inventada", "Prova")
        self.assertEqual(gust.llegeix(), [])

    def test_silenci_dels_projectes_nous(self):
        gust.afegeix("talls", "Talls més ràpids", "talls.pausa_maxima=0.25")
        self.assertEqual(marca.pausa_per_defecte(), 0.25)

    def test_text_per_llegir(self):
        gust.afegeix("subtitols", "Més grans", "subtitols.mida=0.09")
        gust.afegeix("reels", "Prefereixo reels curts")
        text = gust.text(gust.llegeix())
        self.assertIn("Subtítols:", text)
        self.assertIn("1. Més grans  [subtitols.mida=0.09]", text)
        self.assertIn("2. Prefereixo reels curts", text)


if __name__ == "__main__":
    unittest.main()
