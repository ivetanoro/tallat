import json
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


    def test_no_s_empassen_el_silenci_fins_a_la_frase_seguent(self):
        # Segona revisió de Codex: «25» al final d'una frase rebia de 0,3 a 30 s.
        p = transcripcio.a_paraules([
            {"start": 0.0, "end": 1.0, "words": [{"word": "Hola", "start": 0.0, "end": 0.3}, {"word": "25"}]},
            {"start": 30.0, "end": 31.0, "words": [{"word": "adéu", "start": 30.0, "end": 30.5}]}])
        self.assertEqual((p[1]["inici"], p[1]["final"]), (0.3, 1.0))


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


@unittest.skipUnless(shutil.which("ffmpeg"), "cal ffmpeg")
class TestVideosDeLiPhone(unittest.TestCase):
    """L'iPhone desa el vertical com a horitzontal amb l'etiqueta «gira'l 90°». Amb l'ffmpeg 7.1, el
    vídeo exportat sortia dret però amb l'etiqueta, i els reproductors el tornaven a girar."""

    def rotacio(self, video):
        s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams",
                                       "-of", "json", str(video)], capture_output=True, text=True).stdout)
        return exporta._rotacio(s["streams"][0])

    def test_l_export_no_porta_l_etiqueta_de_girar(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=3",
                            "-f", "lavfi", "-i", "sine=d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                            "-shortest", str(d / "pla.mp4")], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-display_rotation:v:0", "-90", "-i", str(d / "pla.mp4"),
                            "-c", "copy", str(d / "iphone.mov")], check=True)
            self.assertEqual(self.rotacio(d / "iphone.mov"), -90)
            self.assertEqual(exporta.info_video(d / "iphone.mov")["alcada"], 320)  # es veu vertical
            sortida = exporta.exporta(d / "iphone.mov", [(0.2, 1.0), (1.5, 2.5)], d / "s.mp4", "esborrany")
            self.assertEqual(self.rotacio(sortida), 0)
            # i el que la treu, sense tornar a codificar res
            exporta.treu_rotacio(d / "iphone.mov")
            self.assertEqual(self.rotacio(d / "iphone.mov"), 0)


class TestCarpetaDelsVideos(unittest.TestCase):
    """La persona pot triar on van els vídeos exportats (a més de la carpeta del projecte)."""

    def test_sense_carpeta_triada_no_es_copia_res(self):
        exporta.tria_carpeta_exports(None)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "v.mp4").write_bytes(b"video")
            self.assertIsNone(exporta.copia_a_carpeta(Path(d) / "v.mp4"))

    def test_hi_va_un_enllac_i_no_trepitja_res(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as meva:
            exporta.tria_carpeta_exports(Path(meva))
            try:
                self.assertEqual(exporta.carpeta_exports(), Path(meva).resolve())
                video = Path(d) / "v.mp4"
                video.write_bytes(b"video")
                (Path(meva) / "v.mp4").write_bytes(b"un altre")  # ja n'hi ha un amb aquest nom
                copia = exporta.copia_a_carpeta(video)
                self.assertEqual((copia.name, copia.read_bytes()), ("v-2.mp4", b"video"))
                self.assertEqual(copia.stat().st_ino, video.stat().st_ino)  # el mateix fitxer: no ocupa més
                carpeta = Path(d) / "projecte_editors"
                carpeta.mkdir()
                (carpeta / "LLEGEIX-ME.txt").write_text("hola")
                self.assertEqual((exporta.copia_a_carpeta(carpeta) / "LLEGEIX-ME.txt").read_text(), "hola")
            finally:
                exporta.tria_carpeta_exports(None)
        self.assertIsNone(exporta.carpeta_exports())  # si la carpeta ja no hi és, la del projecte


class TestPreviaContinua(unittest.TestCase):
    """El muntatge en un sol vídeo, perquè la pàgina el reprodueixi sense saltar."""

    def test_dura_el_que_dura_el_muntatge(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=30:d=4",
                            "-f", "lavfi", "-i", "sine=d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                            "-shortest", str(d / "proxy.mp4")], check=True)
            trams = [(0.2, 1.0), (2.0, 3.5)]
            sortida = exporta.fes_previa(d / "proxy.mp4", trams, d / "previa" / "p.mp4")
            self.assertAlmostEqual(exporta.info_video(sortida)["durada"], 2.3, delta=0.08)
            self.assertFalse(list((d / "previa").glob(".*")))  # cap fitxer a mitges


class TestAlineadorMMS(unittest.TestCase):
    """El temps de cada paraula (motor/transcripcio.py): el que entén el model i les vores als silencis."""

    def test_el_text_que_entén_el_model(self):
        self.assertEqual(transcripcio.romanitza("L'àvia,"), "l'avia")
        self.assertEqual(transcripcio.romanitza("Col·legi!"), "collegi")
        self.assertEqual(transcripcio.romanitza("25"), "")  # aquestes van amb el comodí

    def test_les_vores_als_silencis(self):
        veu = np.zeros(300, dtype=bool)
        veu[100:150] = True  # veu d'1,00 a 1,50 s
        self.assertEqual(transcripcio.retalla_als_silencis([(0.6, 1.8)], veu), [(1.0, 1.5)])
        self.assertEqual(transcripcio.retalla_als_silencis([(2.0, 2.5)], veu), [(2.0, 2.5)])  # sense veu: com era
