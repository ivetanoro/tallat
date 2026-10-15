import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from motor import marca
from motor.projecte import Projecte


class AmbKits(unittest.TestCase):
    """Cada prova té la seva carpeta ~/.tallat de mentida."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.casa = Path(self.dir.name)
        self.pegats = [mock.patch.object(marca, "KITS", self.casa / "kits"),
                       mock.patch.object(marca, "USUARI", self.casa / "brand.json")]
        for p in self.pegats:
            p.start()

    def tearDown(self):
        for p in self.pegats:
            p.stop()
        self.dir.cleanup()


class TestKits(AmbKits):
    def test_l_estil_d_abans_es_converteix_en_el_primer_kit(self):
        (self.casa / "fonts").mkdir()
        (self.casa / "fonts" / "Lletra.otf").write_bytes(b"OTTO")
        marca.USUARI.write_text(json.dumps({"subtitols": {"color": "#00FF00", "font": "Lletra",
                                                          "font_fitxer": str(self.casa / "fonts" / "Lletra.otf")}}),
                                encoding="utf-8")
        self.assertEqual(marca.kits(), [{"id": "el-meu-estil", "nom": "El meu estil", "per_defecte": True}])
        estil = marca.carrega()["subtitols"]
        self.assertEqual(estil["color"], "#00FF00")
        self.assertEqual(marca.fitxer_font(estil), marca.KITS / "el-meu-estil" / "fonts" / "Lletra.otf")
        self.assertTrue(marca.USUARI.exists())  # el fitxer d'abans no es toca

    def test_sense_estil_d_abans_el_primer_kit_es_neutre(self):
        self.assertEqual(marca.carrega(), marca.carrega(marca.PER_DEFECTE))

    def test_crear_duplicar_canviar_el_nom_i_per_defecte(self):
        marca.desa("subtitols", {"color": "#112233"})
        neutre = marca.crea_kit("Neutre")
        copia = marca.crea_kit("Còpia de l'Estil!", copia_de="el-meu-estil")
        self.assertEqual(copia, "copia-de-l-estil")
        self.assertEqual(marca.carrega(kit=copia)["subtitols"]["color"], "#112233")
        self.assertEqual(marca.carrega(kit=neutre)["subtitols"]["color"], "#FFFFFF")
        self.assertEqual(marca.crea_kit("Neutre"), "neutre-2")  # el nom es pot repetir; l'id, no
        marca.canvia_nom(neutre, "  Net   i   clar ")
        marca.fes_per_defecte(neutre)
        self.assertEqual(marca.kits()[0], {"id": neutre, "nom": "Net i clar", "per_defecte": True})
        self.assertEqual(marca.carrega()["subtitols"]["color"], "#FFFFFF")  # sense dir-ne cap: el per defecte
        with self.assertRaises(ValueError):
            marca.crea_kit("   ")
        with self.assertRaises(KeyError):
            marca.crea_kit("X", copia_de="no-existeix")
        for dolent in ("../../etc", "El Meu", ""):
            with self.assertRaises(KeyError):
                marca.fes_per_defecte(dolent)

    def test_esborrar_un_kit_el_guarda_a_part(self):
        altre = marca.crea_kit("Altre")
        with self.assertRaises(ValueError):
            marca.esborra_kit("el-meu-estil")  # el per defecte no
        desti = marca.esborra_kit(altre)
        self.assertTrue((desti / "kit.json").exists())
        self.assertEqual([k["id"] for k in marca.kits()], ["el-meu-estil"])

    def test_exportar_i_importar(self):
        marca.desa("subtitols", {"color": "#ABCDEF", "animacio": "fos"})
        marca.desa_font("La Meva.otf", b"OTTO-font")
        nom, contingut = marca.empaqueta_kit("el-meu-estil")
        self.assertEqual(nom, "el-meu-estil.tallat-kit.zip")
        nou = marca.importa_kit(contingut)
        self.assertNotEqual(nou, "el-meu-estil")
        self.assertEqual(next(k["nom"] for k in marca.kits() if k["id"] == nou), "El meu estil (importat)")
        estil = marca.carrega(kit=nou)["subtitols"]
        self.assertEqual((estil["color"], estil["animacio"], estil["font"]), ("#ABCDEF", "fos", "La Meva"))
        self.assertEqual(marca.fonts_de(estil, kit=nou)[0]["fitxer"].read_bytes(), b"OTTO-font")

    def test_un_kit_importat_no_pot_fer_mal(self):
        memoria = io.BytesIO()
        with zipfile.ZipFile(memoria, "w") as z:
            z.writestr("kit.json", json.dumps({
                "nom": "Kit estrany",
                "subtitols": {"color": "#FF0000", "mida": 99, "animacio": "explota", "font": "x; } body {",
                              "font_fitxer": "/etc/passwd"},
                "broll": {"lut": "/etc/passwd", "durada": 1.0},
                "secreta": {"x": 1}}))
            z.writestr("../fora.otf", b"x")
            z.writestr("fonts/../../fora.otf", b"x")
            z.writestr("fonts/script.sh", b"x")
            z.writestr("fonts/bona.ttf", b"TTF")
        kit = marca.importa_kit(memoria.getvalue())
        dades = json.loads((marca.KITS / kit / "kit.json").read_text(encoding="utf-8"))
        self.assertEqual(dades["subtitols"], {"color": "#FF0000", "mida": 0.16})  # el que no s'entén, fora
        self.assertEqual(dades["broll"], {"durada": 1.0})
        self.assertNotIn("secreta", dades)
        self.assertEqual(sorted(f.name for f in (marca.KITS / kit / "fonts").iterdir()), ["bona.ttf"])
        self.assertFalse((self.casa / "fora.otf").exists() or (marca.KITS / "fora.otf").exists())
        for dolent in (b"no soc cap zip", self._zip({"altres.txt": b"x"})):
            with self.assertRaises(ValueError):
                marca.importa_kit(dolent)

    @staticmethod
    def _zip(fitxers: dict) -> bytes:
        memoria = io.BytesIO()
        with zipfile.ZipFile(memoria, "w") as z:
            for nom, contingut in fitxers.items():
                z.writestr(nom, contingut)
        return memoria.getvalue()


def paraules(n: int) -> list[dict]:
    return [{"id": i, "text": f"p{i}", "inici": i * 0.5, "final": i * 0.5 + 0.4, "frase": 0} for i in range(n)]


class TestKitDelProjecte(AmbKits):
    def projecte(self, carpeta: Path) -> Projecte:
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "transcripcio.json").write_text(json.dumps(
            {"video": str(carpeta / "no-hi-es.mov"), "fps": "30", "durada": 5.0, "paraules": paraules(10)}),
            encoding="utf-8")
        return Projecte(carpeta)

    def test_cada_video_amb_el_seu_kit(self):
        gran = marca.crea_kit("Gran")
        marca.desa("subtitols", {"mida": 0.12}, kit=gran)
        p = self.projecte(self.casa / "video")
        self.assertEqual((p.kit(), p.estil_subtitols()["mida"]), ("el-meu-estil", 0.075))
        p.tria_kit(gran)
        self.assertEqual((p.kit(), Projecte(p.carpeta).estil_subtitols()["mida"]), (gran, 0.12))
        with self.assertRaises(KeyError):
            p.tria_kit("no-existeix")

    def test_un_reel_fa_servir_el_kit_de_la_gravacio(self):
        from motor import muntatge
        gran = marca.crea_kit("Gran")
        arrel = self.projecte(self.casa / "gravacio")
        arrel.tria_kit(gran)
        reel = Projecte(muntatge.crea_reel(arrel, {"id": "r", "paraules": [(2, 6)]}))
        self.assertEqual(reel.kit(), gran)
        reel.tria_kit("el-meu-estil")  # i el reel en pot triar un altre
        self.assertEqual((Projecte(reel.carpeta).kit(), Projecte(arrel.carpeta).kit()), ("el-meu-estil", gran))

    def test_si_el_kit_triat_ja_no_hi_es_fa_servir_el_per_defecte(self):
        altre = marca.crea_kit("Altre")
        p = self.projecte(self.casa / "video")
        p.tria_kit(altre)
        marca.esborra_kit(altre)
        self.assertEqual(p.kit(), "el-meu-estil")


if __name__ == "__main__":
    unittest.main()
