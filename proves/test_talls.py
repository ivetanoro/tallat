import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np

from motor import edicio, exporta, transcripcio, veu


class TestTrams(unittest.TestCase):
    def test_una_paraula_d_un_fotograma_no_desapareix(self):
        # Revisió de Codex: entre dues paraules treta, «sí» (0,40-0,45 s a 30 fps) feia exactament un
        # fotograma, però la resta en decimals donava una mica menys i el tros es perdia.
        p = [{"id": 0, "text": "eh", "inici": 0.0, "final": 0.4, "frase": 0, "conservada": False},
             {"id": 1, "text": "sí", "inici": 0.4, "final": 0.45, "frase": 0, "conservada": True},
             {"id": 2, "text": "eh", "inici": 0.45, "final": 1.0, "frase": 0, "conservada": False}]
        self.assertEqual(edicio.trams(p, fps=30, durada=1.0), [(0.4, 0.4333)])

    def test_una_paraula_mes_curta_que_un_fotograma_tampoc(self):
        # Segona revisió de Codex: de 0,41 a 0,46 s no hi cap cap fotograma sencer i es perdia.
        p = [{"id": 0, "text": "eh", "inici": 0.0, "final": 0.41, "frase": 0, "conservada": False},
             {"id": 1, "text": "sí", "inici": 0.41, "final": 0.46, "frase": 0, "conservada": True},
             {"id": 2, "text": "eh", "inici": 0.46, "final": 1.0, "frase": 0, "conservada": False}]
        (a, b), = edicio.trams(p, fps=30, durada=1.0)
        self.assertLessEqual(a, 0.41)
        self.assertGreaterEqual(b, 0.46)

    def test_l_ultima_paraula_acaba_on_acaba_la_veu(self):
        # L'alineador diu que acaba a 0,4 s, però la veu continua fins a 0,85 s.
        veu_ = np.zeros(200, dtype=bool)
        veu_[:85] = True
        p = [{"id": 0, "text": "adéu", "inici": 0.05, "final": 0.4, "frase": 0, "conservada": True}]
        (a, b), = edicio.trams(p, fps=30, durada=2.0, veu=veu_)
        self.assertGreaterEqual(b, 0.85)
        self.assertLess(b, 1.0)

    def test_l_ultima_paraula_no_s_allarga_sense_silenci_a_prop(self):
        veu_ = np.ones(1000, dtype=bool)  # soroll fins al final: no sabem de qui és, no s'allarga
        p = [{"id": 0, "text": "adéu", "inici": 0.05, "final": 0.4, "frase": 0, "conservada": True}]
        (a, b), = edicio.trams(p, fps=30, durada=10.0, veu=veu_)
        self.assertLess(b, 0.5)


class TestParaulesSenseTemps(unittest.TestCase):
    def test_es_reparteixen_el_forat(self):
        # Revisió de Codex: «25» es quedava tot el forat i «€» acabava sense durada.
        seg = {"start": 0.0, "end": 3.0, "words": [
            {"word": "Són", "start": 0.0, "end": 0.4}, {"word": "25"}, {"word": "€"},
            {"word": "avui", "start": 1.4, "end": 1.8}]}
        p = transcripcio.a_paraules([seg])
        self.assertEqual([x["text"] for x in p], ["Són", "25", "€", "avui"])
        self.assertAlmostEqual(p[1]["inici"], 0.4)
        self.assertAlmostEqual(p[2]["final"], 1.4)
        self.assertAlmostEqual(p[1]["final"], p[2]["inici"])
        self.assertGreater(p[2]["final"] - p[2]["inici"], 0.2)

    def test_al_principi_i_al_final_del_segment(self):
        seg = {"start": 1.0, "end": 2.0, "words": [{"word": "3"}, {"word": "gats", "start": 1.2, "end": 1.6},
                                                   {"word": "%"}]}
        p = transcripcio.a_paraules([seg])
        self.assertEqual([(x["inici"], x["final"]) for x in p], [(1.0, 1.2), (1.2, 1.6), (1.6, 2.0)])


class TestMapaDeVeu(unittest.TestCase):
    def test_parlant_sense_parar_no_tot_es_silenci(self):
        # Revisió de Codex: si la gravació gairebé no té silencis, el 10 % més fluix ja és veu i
        # el llindar quedava tan alt que gairebé tot semblava silenci (i s'escurçava on no tocava).
        t = np.arange(veu.SR * 4) / veu.SR
        so = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)  # veu de volum constant
        so[:int(0.1 * veu.SR)] = 0  # una mica de silenci, menys del 10 %
        m = veu.mapa(so)
        self.assertGreater(m.mean(), 0.8)
        self.assertFalse(m[:5].any())

    def test_un_mapa_desat_dolent_es_torna_a_fer(self):
        with tempfile.TemporaryDirectory() as d:
            np.save(Path(d) / "veu.npy", np.zeros(400, dtype=bool))
            original = veu.llegeix_audio
            veu.llegeix_audio = lambda video: np.full(veu.SR, 0.2, dtype=np.float32)
            try:
                m = veu.carrega(Path(d), Path(d) / "video.mov")
            finally:
                veu.llegeix_audio = original
            self.assertTrue(m.all())
            self.assertTrue(np.load(Path(d) / "veu.npy").all())


class TestExecutaFfmpeg(unittest.TestCase):
    def test_molts_errors_no_encallen_l_export(self):
        # Revisió de Codex: si el programa escrivia molts errors, el canal s'omplia i l'export no acabava mai.
        ordre = [sys.executable, "-c", "import sys; sys.stderr.write('x' * 2_000_000 + 'final'); sys.exit(1)"]
        resultat = {}

        def prova():
            try:
                exporta._executa(ordre, 1.0, None)
            except RuntimeError as e:
                resultat["error"] = str(e)
        fil = threading.Thread(target=prova, daemon=True)
        fil.start()
        fil.join(timeout=30)
        self.assertFalse(fil.is_alive(), "l'export s'ha quedat encallat")
        self.assertTrue(resultat["error"].endswith("final"))


class TestTempsExactes(unittest.TestCase):
    def test_29_97(self):
        # el fotograma 1 comença a 0,0333667 s: amb 4 decimals (0,0334) ffmpeg se'l saltava
        self.assertEqual(exporta.temps_exactes(1001 / 30000, 4004 / 30000, "30000/1001"), ("0.033366", "0.100100"))

    def test_30(self):
        self.assertEqual(exporta.temps_exactes(0.4, 0.4333, "30"), ("0.400000", "0.033333"))

    @unittest.skipUnless(shutil.which("ffmpeg"), "cal ffmpeg")
    def test_ffmpeg_en_treu_els_fotogrames_justos(self):
        # Amb els temps d'abans, 127 de 165 trossos sortien desplaçats un fotograma.
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "prova.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30000/1001",
                            "-t", "2", "-pix_fmt", "yuv420p", str(video)], check=True)

            def fotogrames(*opcions):
                sortida = subprocess.run(["ffmpeg", "-v", "error", *opcions, "-i", str(video), "-f", "framemd5", "-"],
                                         capture_output=True, text=True, check=True).stdout
                return [l.split(",")[-1] for l in sortida.splitlines() if l and not l.startswith("#")]
            tots = fotogrames()
            for fa, fb in ((1, 4), (7, 8), (13, 40), (29, 30), (44, 49)):
                a, b = round(fa * 1001 / 30000, 4), round(fb * 1001 / 30000, 4)
                inici, durada = exporta.temps_exactes(a, b, "30000/1001")
                self.assertEqual(fotogrames("-ss", inici, "-t", durada), tots[fa:fb], (fa, fb))

if __name__ == "__main__":
    unittest.main()
