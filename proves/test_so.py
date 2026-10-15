import array
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from motor import exporta, marca, so


class TestEfectes(unittest.TestCase):
    def test_on_sona_cada_efecte(self):
        brolls = [{"id": "b1", "inici": 2.0, "durada": 1.5}]
        stickers = [{"id": "s1", "inici": 4.0, "durada": 2.0}]
        titol = {"text": "Hola\n*món*", "inici": 0.0, "final": 3.0}
        linies = [{"paraules": [{"id": 7, "text": "gran", "inici": 5.0, "clau": True},
                                {"id": 8, "text": "petita", "inici": 5.4, "clau": False}]}]
        pocs = so.esdeveniments(brolls, stickers, titol, "puja", linies, "pocs")
        self.assertEqual([(e["clau"], e["so"]) for e in pocs],
                         [("titol", "brill"), ("broll:b1", "whoosh"), ("sticker:s1", "pop")])
        self.assertEqual(pocs[1]["moments"], [1.75])  # el whoosh arriba al màxim quan entra el b-roll
        molts = so.esdeveniments(brolls, stickers, titol, "puja", linies, "molts")
        self.assertEqual(molts[-1]["clau"], "clau:7")
        self.assertEqual(so.esdeveniments(brolls, stickers, titol, "puja", linies, "cap"), [])

    def test_el_titol_a_maquina_fa_una_tecla_per_lletra(self):
        titol = {"text": "ab\n*cd*", "inici": 0.0, "final": 3.0}
        moments = so.esdeveniments([], [], titol, "maquina", [], "pocs")[0]["moments"]
        pas = min(0.06, max(0.015, 3.0 * 0.55 / 4))
        self.assertEqual(len(moments), 4)
        self.assertAlmostEqual(moments[0], 0.2)
        self.assertAlmostEqual(moments[2] - moments[1], pas * 4)  # entre línies, una pausa (com subtitols.js)

    def test_la_pista_te_els_efectes_al_seu_lloc(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(so, "SONS_PROPIS", Path(d) / "sons"):
            desti = so.pista([{"so": "pop", "moments": [1.0]}], 2.0, 1.0, Path(d) / "p.wav")
            with wave.open(str(desti)) as w:
                self.assertEqual((w.getframerate(), w.getnchannels(), w.getnframes()), (48000, 1, 96000))
                mostres = array.array("h")
                mostres.frombytes(w.readframes(w.getnframes()))
            self.assertEqual(max(abs(m) for m in mostres[:47000]), 0)  # abans del segon 1, silenci
            self.assertGreater(max(abs(m) for m in mostres[48000:50000]), 10000)

    @unittest.skipUnless(shutil.which("ffmpeg"), "cal ffmpeg")
    def test_un_so_propi_substitueix_el_de_tallat(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(so, "SONS_PROPIS", Path(d)):
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=0.5", str(Path(d) / "Pop.wav")],
                           check=True)
            propi = so.so("pop")
            self.assertAlmostEqual(len(propi) / so.MOSTREIG, 0.5, places=1)
            self.assertNotEqual(propi[:100], so._a_pic(so._pop(), so.PICS["pop"])[:100])

    def test_l_estil_del_so_es_valida(self):
        self.assertEqual(marca.valida("so", {"efectes": "molts", "volum_efectes": 3, "soroll": "fort", "neteja": False}),
                         {"efectes": "molts", "volum_efectes": 1.0, "soroll": "fort", "neteja": False})
        for dolent in ({"efectes": "tots"}, {"soroll": "extrem"}, {"neteja": "sí"}):
            with self.assertRaises(ValueError):
                marca.valida("so", dolent)


@unittest.skipUnless(shutil.which("ffmpeg"), "cal ffmpeg")
class TestExportAmbSo(unittest.TestCase):
    def test_la_veu_neta_arriba_al_volum_de_les_xarxes(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            # Una «veu» fluixa (to que puja i baixa) amb soroll de fons.
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=360x640:r=30:d=6",
                            "-f", "lavfi", "-i", "aevalsrc='0.05*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*3*t))+0.004*(random(0)-0.5)':s=48000:d=6",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / "v.mp4")],
                           check=True)
            efectes = so.pista([{"so": "whoosh", "moments": [2.0]}], 6.0, 0.5, d / "e.wav")
            exporta.exporta(d / "v.mp4", [(0.0, 6.0)], d / "s.mp4", "esborrany", neteja="suau", efectes=efectes)
            mesura = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(d / "s.mp4"), "-af", "ebur128",
                                     "-f", "null", "-"], capture_output=True, text=True).stderr
            volum = float(mesura.rsplit("I:", 1)[1].split("LUFS")[0])
            self.assertAlmostEqual(volum, -14, delta=1.5)


if __name__ == "__main__":
    unittest.main()
