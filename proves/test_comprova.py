import os
import subprocess
import sys
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

    @unittest.skipUnless(sys.platform == "darwin", "només al Mac")
    def test_la_llista_de_lletres_no_depen_de_system_profiler(self):
        # Un system_profiler que s'atura a mitges (Mac ocupat): torna una llista sense «_items».
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "bin").mkdir()
            fals = d / "bin" / "system_profiler"
            fals.write_text(f'#!/bin/sh\ntouch "{d}/cridat"\necho \'<plist version="1.0"><array><dict/></array></plist>\'\n')
            fals.chmod(0o755)
            arrel = Path(__file__).resolve().parent.parent
            codi = f"import sys; sys.path.insert(0, {str(arrel)!r}); from motor import entorn; " \
                   "entorn.llista_de_lletres(); import matplotlib.font_manager"
            entorn_proves = {**os.environ, "PATH": f"{d / 'bin'}:/usr/bin:/bin", "MPLCONFIGDIR": str(d / "mpl")}
            prova = subprocess.run([sys.executable, "-c", codi], env=entorn_proves, capture_output=True, text=True)
            self.assertEqual(prova.returncode, 0, prova.stderr[-500:])
            self.assertFalse((d / "cridat").exists())
            self.assertTrue(list((d / "mpl").glob("fontlist-*.json")))  # desada: els altres cops ja no es fa


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
