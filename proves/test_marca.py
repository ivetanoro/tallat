import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from motor import marca


class TestMarca(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "brand.json"
        self.path.write_text(json.dumps({"subtitols": {"_nota": "per a la persona", "color": "#00FF00"},
                                         "broll": {"durada": 1.0}}), encoding="utf-8")

    def tearDown(self):
        self.dir.cleanup()

    def test_desa_conserva_notes_i_altres_seccions(self):
        estil = marca.desa("subtitols", {"mida": 0.09, "animacio": "fos"}, self.path)
        self.assertEqual((estil["mida"], estil["animacio"], estil["color"]), (0.09, "fos", "#00FF00"))
        dades = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(dades["subtitols"]["_nota"], "per a la persona")
        self.assertEqual(dades["broll"], {"durada": 1.0})

    def test_valors_fora_de_mida_es_limiten(self):
        net = marca.valida("subtitols", {"mida": 5, "paraules_per_linia": 2.6, "posicio_y": -1})
        self.assertEqual(net, {"mida": 0.16, "paraules_per_linia": 3, "posicio_y": 0.08})

    def test_valors_dolents_es_rebutgen(self):
        for canvi in ({"color": "vermell"}, {"animacio": "explota"}, {"destaca": "sí"}, {"opcio_inventada": 1},
                      {"font": "x; } body { display: none"}, {"font_fitxer": "/etc/passwd"}, {"mida": True}):
            with self.subTest(canvi=canvi), self.assertRaises(ValueError):
                marca.valida("subtitols", canvi)
        for seccio, canvi in (("secreta", {"x": 1}), ("broll", {"lut": "/etc/passwd"}), ("broll", {"durada": "llarg"}),
                              ("stickers", {"animacio": "explota"})):
            with self.subTest(seccio=seccio, canvi=canvi), self.assertRaises(ValueError):
                marca.valida(seccio, canvi)

    def test_altres_seccions(self):
        self.assertEqual(marca.valida("broll", {"durada": 9}), {"durada": 4.0})
        self.assertEqual(marca.valida("talls", {"pausa_maxima": 0.25}), {"pausa_maxima": 0.25})
        self.assertEqual(marca.valida("stickers", {"mida": 0.3, "animacio": "cap"}), {"mida": 0.3, "animacio": "cap"})

    def test_restableix_torna_a_l_estil_neutre(self):
        marca.desa("subtitols", {"mida": 0.1}, self.path)
        estil = marca.restableix("subtitols", self.path)
        neutre = marca.carrega(marca.PER_DEFECTE)["subtitols"]
        self.assertEqual(estil, neutre)

    def test_font_propia(self):
        with mock.patch.object(marca, "FONTS", Path(self.dir.name) / "fonts"):
            estil = marca.desa_font("La Meva Lletra.otf", b"OTTO-falsa", self.path)
            self.assertEqual(estil["font"], "La Meva Lletra")
            self.assertEqual(marca.fitxer_font(estil), Path(self.dir.name) / "fonts" / "La Meva Lletra.otf")
            with self.assertRaises(ValueError):
                marca.desa_font("virus.exe", b"x", self.path)
            # Tornar a una font del sistema deixa de fer servir el fitxer.
            estil = marca.desa("subtitols", {"font": "Avenir Next", "font_fitxer": None}, self.path)
            self.assertIsNone(marca.fitxer_font(estil))

    def test_estils_predefinits_son_valids(self):
        for estil in marca.estils():
            with self.subTest(estil=estil["id"]):
                self.assertEqual(marca.valida("subtitols", estil["valors"]), estil["valors"])
                self.assertNotIn("font", estil["valors"])  # la lletra de cadascú no es toca


if __name__ == "__main__":
    unittest.main()
