import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from motor import comprova, entorn


class TestEntorn(unittest.TestCase):
    def test_les_eines_de_tallat_van_al_davant(self):
        with tempfile.TemporaryDirectory() as d:
            eines, bin_ = Path(d) / "eines" / "bin", Path(d) / "bin"
            eines.mkdir(parents=True)
            bin_.mkdir()
            with mock.patch.object(entorn, "EINES", eines), mock.patch.object(entorn, "INSTAL_LADORS", bin_), \
                    mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
                entorn.prepara()
                entorn.prepara()  # dues vegades: no s'hi repeteixen
                self.assertEqual(os.environ["PATH"].split(os.pathsep), [str(eines), str(bin_), "/usr/bin", "/bin"])

    def test_si_no_hi_son_no_es_toca_res(self):
        with mock.patch.object(entorn, "EINES", Path("/no/existeix")), \
                mock.patch.object(entorn, "INSTAL_LADORS", Path("/tampoc")), \
                mock.patch.dict(os.environ, {"PATH": "/usr/bin"}):
            entorn.prepara()
            self.assertEqual(os.environ["PATH"], "/usr/bin")


class TestInforme(unittest.TestCase):
    def test_tot_be(self):
        text = comprova.informe([("ok", "Python", "3.11.1"), ("avis", "Model", "es baixarà")])
        self.assertIn("✓ Python  3.11.1", text)
        self.assertIn("! Model   es baixarà", text)
        self.assertIn("Tot a punt", text)

    def test_amb_errors(self):
        text = comprova.informe([("error", "ffmpeg", "no trobo ffmpeg"), ("error", "Node.js", "no el trobo")])
        self.assertIn("✗ ffmpeg", text)
        self.assertIn("Hi ha 2 coses per arreglar. Executa ./prepara.sh", text)

    def test_ffmpeg_que_no_hi_es(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(comprova._ffmpeg()[0][0], "error")


if __name__ == "__main__":
    unittest.main()
