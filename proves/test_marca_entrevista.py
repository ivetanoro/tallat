import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from motor import marca


class TestMarca(unittest.TestCase):
    """La marca d'un kit: es valida i els colors i les lletres s'escampen pel kit."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        casa = Path(self.dir.name)
        self.pegats = [mock.patch.object(marca, "KITS", casa / "kits"), mock.patch.object(marca, "USUARI", casa / "b.json")]
        for p in self.pegats:
            p.start()

    def tearDown(self):
        for p in self.pegats:
            p.stop()
        self.dir.cleanup()

    def test_els_colors_i_les_lletres_fan_la_seva_feina(self):
        marca.desa("marca", {"color_destacat": "#FF7DB8", "color_principal": "#ED84B0",
                             "lletra_text": "DM Sans", "lletra_titols": "Fraunces", "lletra_accent": "Instrument Serif"})
        kit = marca.carrega()
        self.assertEqual((kit["subtitols"]["color_actiu"], kit["subtitols"]["clau_color"], kit["titol"]["clau_color"]),
                         ("#FF7DB8",) * 3)
        self.assertEqual(kit["broll"]["vora_color"], "#ED84B0")
        self.assertEqual((kit["subtitols"]["font"], kit["titol"]["font"]), ("DM Sans", "Fraunces"))
        self.assertEqual((kit["subtitols"]["clau_font"], kit["subtitols"]["clau_cursiva"], kit["titol"]["clau_cursiva"]),
                         ("Instrument Serif", True, True))
        # Treure'n un torna a l'estil neutre (i la cursiva se'n va amb la lletra d'accent).
        marca.desa("marca", {"color_destacat": None, "lletra_accent": None})
        kit = marca.carrega()
        self.assertEqual(kit["subtitols"]["color_actiu"], "#FFD60A")
        self.assertEqual((kit["subtitols"]["clau_font"], kit["subtitols"]["clau_cursiva"]), (None, False))

    def test_textos_i_opcions(self):
        net = marca.valida("marca", {"crida": "  comenta GUIA  ", "compte": "x" * 900, "energia": "editorial"})
        self.assertEqual((net["crida"], len(net["compte"]), net["energia"]), ("comenta GUIA", marca.MIDA_TEXT, "editorial"))
        for dolent in ({"energia": "barroc"}, {"grafics": "tots"}, {"color_clar": "rosa"}, {"lletra_text": "x; }"}):
            with self.assertRaises(ValueError):
                marca.valida("marca", dolent)

    def test_les_cursives_del_kit_es_declaren_com_a_cursives(self):
        carpeta = marca.ruta().parent / "fonts"
        carpeta.mkdir(parents=True, exist_ok=True)
        for nom in ("Fraunces__var.woff2", "Fraunces__var-cursiva.woff2", "Poppins__700-cursiva.woff2"):
            (carpeta / nom).write_bytes(b"wOF2")
        fonts = {(f["familia"], f["pes"], f["estil"]) for f in marca.fonts_del_kit()}
        self.assertEqual(fonts, {("Fraunces", "100 1000", "normal"), ("Fraunces", "100 1000", "italic"),
                                 ("Poppins", "700", "italic")})
        marca.desa("subtitols", {"font": "Poppins", "clau_font": "Fraunces"})
        self.assertEqual({f["familia"] for f in marca.fonts_de(marca.carrega()["subtitols"])}, {"Poppins", "Fraunces"})

    def test_un_kit_importat_porta_la_seva_marca(self):
        marca.desa("marca", {"color_destacat": "#123456", "crida": "segueix-me"})
        nom, contingut = marca.empaqueta_kit("el-meu-estil")
        nou = marca.importa_kit(contingut)
        self.assertEqual(marca.carrega(kit=nou)["marca"]["crida"], "segueix-me")
        self.assertEqual(json.loads((marca.KITS / nou / "kit.json").read_text())["subtitols"]["color_actiu"], "#123456")


if __name__ == "__main__":
    unittest.main()
