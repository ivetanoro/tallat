import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

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
        self.assertEqual(net, {"mida": 0.16, "paraules_per_linia": 3, "posicio_y": 0.05})

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
        # La font va a la carpeta fonts/ del costat del fitxer d'estil (en un kit, dins del kit), amb el
        # nom de la família: així el kit es pot passar a algú amb la lletra.
        estil = marca.desa_font("La Meva Lletra.otf", b"OTTO-falsa", self.path)
        self.assertEqual(estil["font"], "La Meva Lletra")
        fonts = marca.fonts_de(estil, path=self.path)
        self.assertEqual([(f["familia"], f["pes"], f["fitxer"]) for f in fonts],
                         [("La Meva Lletra", "100 1000", Path(self.dir.name) / "fonts" / "La Meva Lletra.otf")])
        for dolent in ("virus.exe", ".amagada.otf"):
            with self.assertRaises(ValueError):
                marca.desa_font(dolent, b"x", self.path)
        # Tornar a una font del sistema deixa de fer servir el fitxer (però es queda al kit).
        estil = marca.desa("subtitols", {"font": "Avenir Next"}, self.path)
        self.assertEqual(marca.fonts_de(estil, path=self.path), [])
        self.assertEqual(len(marca.fonts_del_kit(path=self.path)), 1)

    def test_lletres_de_la_biblioteca(self):
        cridades = []

        class Resposta:
            def __init__(self, url):
                cridades.append(url)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, n):
                return b"wOF2" + b"0" * 10
        with mock.patch.object(marca.urllib.request, "urlopen", lambda url, timeout: Resposta(url)):
            estil = marca.baixa_lletra("poppins", path=self.path)
            marca.baixa_lletra("poppins", path=self.path)  # el segon cop ja hi és: no es baixa
            marca.baixa_lletra("inter", path=self.path)
        self.assertEqual(estil["font"], "Poppins")
        # 5 gruixos de Poppins + Inter (variable, un sol fitxer), cadascun amb la seva cursiva.
        self.assertEqual(len(cridades), 12)
        self.assertTrue(cridades[0].startswith("https://cdn.jsdelivr.net/npm/@fontsource/poppins@"))
        self.assertTrue(any(c.endswith("poppins-latin-700-italic.woff2") for c in cridades))
        self.assertIn("@fontsource-variable/inter@", cridades[-1])
        self.assertEqual(sorted((f["pes"], f["estil"]) for f in marca.fonts_de(estil, path=self.path)),
                         sorted((p, e) for p in ("400", "600", "700", "800", "900") for e in ("normal", "italic")))
        self.assertEqual(sorted(f["estil"] for f in marca.fonts_de({"font": "Inter"}, path=self.path)),
                         ["italic", "normal"])
        with self.assertRaises(KeyError):
            marca.baixa_lletra("no-existeix", path=self.path)

    def test_estils_predefinits_son_valids(self):
        for estil in marca.estils():
            with self.subTest(estil=estil["id"]):
                self.assertEqual(marca.valida("subtitols", estil["valors"]), estil["valors"])
                self.assertNotIn("font", estil["valors"])  # la lletra de cadascú no es toca


if __name__ == "__main__":
    unittest.main()
