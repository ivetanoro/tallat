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
        # El vídeo, en fotogrames sencers cap enfora; el so, just el de la paraula.
        (tram,) = edicio.trams(p, fps=30, durada=1.0)
        self.assertEqual(tram, (0.4, 0.466667))
        self.assertEqual(tram.so, (0.4, 0.45))

    def test_una_paraula_mes_curta_que_un_fotograma_tampoc(self):
        # Segona revisió de Codex: de 0,41 a 0,46 s no hi cap cap fotograma sencer i es perdia.
        p = [{"id": 0, "text": "eh", "inici": 0.0, "final": 0.41, "frase": 0, "conservada": False},
             {"id": 1, "text": "sí", "inici": 0.41, "final": 0.46, "frase": 0, "conservada": True},
             {"id": 2, "text": "eh", "inici": 0.46, "final": 1.0, "frase": 0, "conservada": False}]
        (tram,) = edicio.trams(p, fps=30, durada=1.0)
        self.assertLessEqual(tram[0], 0.41)
        self.assertGreaterEqual(tram[1], 0.46)
        self.assertEqual(tram.so, (0.41, 0.46))  # i no se sent res de les tretes

    def test_dues_paraules_que_comparteixen_fotograma_sonen_senceres(self):
        # Revisió de Codex: entre «A» i «B» hi havia una paraula treta més curta que un fotograma; el so de
        # «B» es retallava (o desapareixia sencer). Ara el fotograma es repeteix i cada tros sona sencer.
        for fps, (a, x, b) in ((30, (0.41, 0.42, 0.46)), (24, (0.501, 0.521, 0.541))):
            p = [{"id": 0, "text": "A", "inici": 0.2, "final": a, "frase": 0, "conservada": True},
                 {"id": 1, "text": "eh", "inici": a, "final": x, "frase": 0, "conservada": False},
                 {"id": 2, "text": "B", "inici": x, "final": b, "frase": 0, "conservada": True},
                 {"id": 3, "text": "eh", "inici": b, "final": 1.0, "frase": 0, "conservada": False}]
            primer, segon = edicio.trams(p, fps=fps, durada=1.0, marge=0)
            self.assertEqual((primer.so[1], segon.so), (a, (x, b)))

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

    def test_poca_veu_pero_clara(self):
        # Revisió de Codex: amb només un 10 % de veu, tot sortia com a veu i no es podia escurçar res.
        t = np.arange(veu.SR * 10) / veu.SR
        so = (0.001 * np.sin(2 * np.pi * 50 * t)).astype(np.float32)  # soroll de fons fluix
        so[:veu.SR] += (0.3 * np.sin(2 * np.pi * 220 * t[:veu.SR])).astype(np.float32)  # 1 s de veu
        m = veu.mapa(so)
        self.assertTrue(m[5:95].all())
        self.assertFalse(m[105:].any())

    def test_el_mapa_desat_d_un_altre_video_es_torna_a_fer(self):
        # Revisió de Codex: veu.npy no deia de quin vídeo era; en tornar a transcriure amb un altre, es reaprofitava.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            original = veu.llegeix_audio
            try:
                veu.llegeix_audio = lambda video: np.full(veu.SR * 2, 0.2, dtype=np.float32)
                self.assertEqual(len(veu.carrega(d, d / "a.mov", durada=2.0)), 200)
                veu.llegeix_audio = lambda video: self.fail("no l'havia de tornar a calcular")
                self.assertEqual(len(veu.carrega(d, d / "a.mov", durada=2.0)), 200)
                veu.llegeix_audio = lambda video: np.full(veu.SR * 5, 0.2, dtype=np.float32)
                self.assertEqual(len(veu.carrega(d, d / "b.mov", durada=5.0)), 500)  # un altre vídeo
            finally:
                veu.llegeix_audio = original

    def test_un_altre_video_que_dura_el_mateix_tambe_es_torna_a_fer(self):
        # Revisió de Codex: amb la mateixa durada, el mapa d'un altre vídeo es reaprofitava.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            video = d / "v.mov"
            video.write_bytes(b"primer")
            crides = []
            original = veu.llegeix_audio
            veu.llegeix_audio = lambda v: crides.append(v) or np.full(veu.SR * 2, 0.2, dtype=np.float32)
            try:
                veu.carrega(d, video, durada=2.0)
                veu.carrega(d, video, durada=2.0)
                self.assertEqual(len(crides), 1)
                video.write_bytes(b"un altre video")  # el mateix nom i la mateixa durada, un altre fitxer
                veu.carrega(d, video, durada=2.0)
                self.assertEqual(len(crides), 2)
            finally:
                veu.llegeix_audio = original

    def test_un_3_per_cent_de_veu_clara(self):
        t = np.arange(veu.SR * 10) / veu.SR
        so = (0.001 * np.sin(2 * np.pi * 50 * t)).astype(np.float32)
        so[:int(veu.SR * 0.3)] += (0.3 * np.sin(2 * np.pi * 220 * t[:int(veu.SR * 0.3)])).astype(np.float32)
        self.assertAlmostEqual(veu.mapa(so).mean(), 0.03, delta=0.005)

    def test_no_trepitja_el_mapa_on_apunta_un_enllac(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "anteriors").mkdir()
            np.save(d / "veu.npy", np.zeros(300, dtype=bool))
            (d / "anteriors" / "veu.npy").symlink_to(Path("..") / "veu.npy")
            original = veu.llegeix_audio
            veu.llegeix_audio = lambda video: np.full(veu.SR, 0.2, dtype=np.float32)
            try:
                veu.carrega(d / "anteriors", d / "x.mov", durada=1.0)
            finally:
                veu.llegeix_audio = original
            self.assertEqual(len(np.load(d / "veu.npy")), 300)
            self.assertFalse((d / "anteriors" / "veu.npy").is_symlink())

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


class TestSoExacte(unittest.TestCase):
    """Revisió de Codex: el so anava lligat als fotogrames sencers i en un tros curt hi entrava un bocí
    de les paraules tretes. Ara el vídeo agafa el fotograma sencer i el so es talla al punt exacte."""

    @unittest.skipUnless(shutil.which("ffmpeg"), "cal ffmpeg")
    def test_no_se_sent_res_de_les_paraules_tretes(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            # So fort a les paraules tretes (fins a 0,41 s i des de 0,46 s) i silenci a la que es queda.
            so_ = "0.5*sin(2*PI*1000*t)*(lt(t,0.41)+gte(t,0.46))"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=30:d=1",
                            "-f", "lavfi", "-i", f"aevalsrc='{so_}':s=48000:d=1", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(d / "proxy.mov")], check=True)
            p = [{"id": 0, "text": "eh", "inici": 0.0, "final": 0.41, "frase": 0, "conservada": False},
                 {"id": 1, "text": "sí", "inici": 0.41, "final": 0.46, "frase": 0, "conservada": True},
                 {"id": 2, "text": "eh", "inici": 0.46, "final": 1.0, "frase": 0, "conservada": False}]
            trams = edicio.trams(p, fps=30, durada=1.0)
            sortida = exporta.fes_previa(d / "proxy.mov", trams, d / "p.mp4")
            brut = subprocess.run(["ffmpeg", "-v", "error", "-i", str(sortida), "-ac", "1", "-f", "s16le", "-"],
                                  capture_output=True, check=True).stdout
            mostres = np.frombuffer(brut, dtype=np.int16).astype(np.float32) / 32768
            self.assertGreater(len(mostres), 1000)
            self.assertLess(float(np.abs(mostres).max()), 0.02)


class TestMuntatgeALots(unittest.TestCase):
    """Revisió de Codex: cada tros és una entrada d'ffmpeg i cadascuna guarda fotogrames a la memòria (amb
    un vídeo 4K, 20 trossos ja passaven de 8 GB). Amb molts trossos, el muntatge es fa a lots."""

    def test_quants_per_lot(self):
        self.assertEqual(exporta.trossos_per_lot({"amplada": 3840, "alcada": 2160}), 8)
        self.assertEqual(exporta.trossos_per_lot({"amplada": 720, "alcada": 1280}), 40)

    @unittest.skipUnless(shutil.which("ffmpeg"), "cal ffmpeg")
    def test_a_lots_un_video_d_iphone_no_es_torna_a_girar(self):
        # Revisió de Codex: l'ffmpeg 7.1 copia l'etiqueta «gira'l 90°» als lots, que ja són drets, i el
        # vídeo sortia de costat (1280×720).
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=6",
                            "-f", "lavfi", "-i", "sine=d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                            "-shortest", str(d / "pla.mp4")], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-display_rotation:v:0", "90", "-i", str(d / "pla.mp4"),
                            "-c", "copy", str(d / "girat.mov")], check=True)
            trams = [edicio.Tram(i * 0.5, i * 0.5 + 0.3) for i in range(9)]
            with mock.patch.object(exporta, "MEMORIA_LOT", 1):  # lots de 4 trossos
                sortida = exporta.exporta(d / "girat.mov", trams, d / "final.mp4", "esborrany")
            s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams",
                                           "-of", "json", str(sortida)], capture_output=True, text=True).stdout)["streams"][0]
            self.assertEqual((s["width"], s["height"], exporta._rotacio(s)), (720, 1280, 0))

    @unittest.skipUnless(shutil.which("ffmpeg"), "cal ffmpeg")
    def test_a_lots_dura_el_mateix_i_no_perd_res(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=30:d=8",
                            "-f", "lavfi", "-i", "sine=f=440:d=8", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-shortest", str(d / "v.mp4")], check=True)
            trams = [edicio.Tram(i * 0.6, i * 0.6 + 0.4) for i in range(11)]
            esperat = sum(b - a for a, b in trams)
            with mock.patch.object(exporta, "MEMORIA_LOT", 1):  # lots de 4 trossos
                previa = exporta.fes_previa(d / "v.mp4", trams, d / "previa.mp4")
                final = exporta.exporta(d / "v.mp4", trams, d / "final.mp4", "esborrany")
            for fitxer in (previa, final):
                info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration",
                                                  "-of", "json", str(fitxer)], capture_output=True, text=True).stdout)
                durades = {s["codec_type"]: float(s["duration"]) for s in info["streams"]}
                self.assertAlmostEqual(durades["video"], esperat, delta=0.05, msg=fitxer.name)
                self.assertAlmostEqual(durades["audio"], esperat, delta=0.05, msg=fitxer.name)


class TestCodificadorPerSistema(unittest.TestCase):
    """Al Mac, la gràfica (VideoToolbox); a Windows no n'hi ha i es fa amb el processador (x264)."""

    def test_al_mac_com_sempre(self):
        from unittest import mock
        with mock.patch.object(exporta.sys, "platform", "darwin"):
            self.assertEqual(exporta.codec_video("final", "16M"),
                             ["-c:v", "h264_videotoolbox", "-b:v", "16M", "-maxrate", "16M", "-profile:v", "high"])
            self.assertEqual(exporta.codec_video("copia", "3M"), ["-c:v", "h264_videotoolbox", "-b:v", "3M", "-g", "15"])

    @unittest.skipUnless(shutil.which("ffmpeg"), "cal ffmpeg")
    def test_a_windows_amb_x264_tambe_a_lots(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=6",
                            "-f", "lavfi", "-i", "sine=d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                            "-shortest", str(d / "v.mp4")], check=True)
            trams = [edicio.Tram(i * 0.5, i * 0.5 + 0.3) for i in range(9)]
            with mock.patch.object(exporta.sys, "platform", "win32"), mock.patch.object(exporta, "MEMORIA_LOT", 1):
                self.assertEqual(exporta.codec_video("final", "4M")[:2], ["-c:v", "libx264"])
                sortida = exporta.exporta(d / "v.mp4", trams, d / "final.mp4", "esborrany")
                previa = exporta.fes_previa(d / "v.mp4", trams, d / "previa.mp4")
            for f in (sortida, previa):
                s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams",
                                               "-of", "json", str(f)], capture_output=True, text=True).stdout)["streams"][0]
                self.assertEqual(s["codec_name"], "h264")


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


class TestAlineador(unittest.TestCase):
    """El temps de cada paraula (motor/transcripcio.py): el que entén el model, l'alineació i les vores als silencis."""

    DICCIONARI = {"[pad]": 3, "|": 2, "a": 0, "b": 1, "à": 4, "'": 5, "·": 6, "l": 7}

    def test_el_text_que_entén_el_model(self):
        d = self.DICCIONARI
        self.assertEqual(transcripcio.normalitza("L’à,", d), "l'à")
        self.assertEqual(transcripcio.normalitza("Bâ·l!", d), "ba·l")  # «â» no hi és: va sense accent
        self.assertEqual(transcripcio.normalitza("25", d), "")  # aquestes van amb el comodí

    def test_alinea_amb_el_buit_i_el_separador_del_model(self):
        import types
        import torch

        class Model:  # «a» a les trames 10-14, el separador a la 20, «b» a les 30-34 (trames de 20 ms)
            def __call__(self, x):
                logits = torch.full((1, x.shape[1] // 320, 8), -10.0)
                logits[0, :, 3] = 10.0
                for trames, lletra in ((range(10, 15), 0), (range(20, 21), 2), (range(30, 35), 1)):
                    for t in trames:
                        logits[0, t, 3], logits[0, t, lletra] = -10.0, 10.0
                return types.SimpleNamespace(logits=logits)

        temps, confiances = transcripcio.temps_paraules(np.zeros(16000, dtype=np.float32), ["A,", "b"],
                                                        Model(), self.DICCIONARI)
        self.assertEqual([tuple(round(x, 2) for x in t) for t in temps], [(0.2, 0.3), (0.6, 0.7)])
        self.assertGreater(min(confiances), 0.9)

    def test_les_vores_als_silencis(self):
        veu = np.zeros(300, dtype=bool)
        veu[100:150] = True  # veu d'1,00 a 1,50 s
        # Amb una mica d'aire a cada costat, perquè no es retallin les consonants fluixes.
        self.assertEqual(transcripcio.retalla_als_silencis([(0.6, 1.8)], veu), [(0.97, 1.55)])
        self.assertEqual(transcripcio.retalla_als_silencis([(2.0, 2.5)], veu), [(2.0, 2.5)])  # sense veu: com era


class TestAjustaTemps(unittest.TestCase):
    """Revisió de Codex: si fallava l'alineació de tot el text, l'alineador d'abans no retallava les vores, i
    a les gravacions llargues (a trossos) una paraula podia començar abans que l'anterior."""

    def test_retalla_i_no_va_enrere(self):
        veu_ = np.zeros(400, dtype=bool)
        veu_[100:150] = True
        veu_[200:260] = True
        segments = [{"start": 0.5, "end": 2.6, "words": [
            {"word": "u", "start": 0.5, "end": 1.9, "score": 0.9},      # s'estira pel silenci
            {"word": "dos", "start": 1.5, "end": 2.6, "score": 0.9},    # comença una mica abans que acabi «u»
            {"word": "25", "start": None, "end": None}]}]
        self.assertEqual(transcripcio.ajusta_temps(segments, veu_), 0)
        u, dos, _ = segments[0]["words"]
        self.assertEqual((u["start"], u["end"]), (0.97, 1.55))
        self.assertGreaterEqual(dos["start"], u["end"])
        self.assertEqual(segments[0]["start"], 0.5)  # hi ha «25» sense temps: el segment conserva els límits

    def test_compta_les_que_anaven_enrere(self):
        segments = [{"words": [{"word": "a", "start": 5.0, "end": 5.5, "score": 0.9},
                               {"word": "b", "start": 2.0, "end": 2.4, "score": 0.9}]}]
        self.assertEqual(transcripcio.ajusta_temps(segments, np.ones(1000, dtype=bool)), 1)
        self.assertEqual(segments[0]["words"][1]["start"], 5.5)
        self.assertIsNone(segments[0]["words"][1]["score"])  # ja no és el temps de l'alineador: aproximat

    def test_els_numbers_conserven_el_forat(self):
        # Revisió de Codex: el segment s'encongia fins a «gats» i «25» i «%» es quedaven sense durada.
        segments = [{"start": 0.0, "end": 3.0, "words": [{"word": "25"}, {"word": "gats", "start": 1.0, "end": 2.0},
                                                          {"word": "%"}]}]
        transcripcio.ajusta_temps(segments, np.ones(400, dtype=bool))
        p = transcripcio.a_paraules(segments)
        self.assertEqual([(x["inici"], x["final"]) for x in p], [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)])

    def test_la_confianca_es_desa_i_el_comodi_no_se_sap(self):
        p = transcripcio.a_paraules([{"start": 0, "end": 2, "words": [
            {"word": "Hola", "start": 0.0, "end": 0.4, "score": 0.876}, {"word": "25", "start": 0.5, "end": 0.9, "score": None}]}])
        self.assertEqual([x["confianca"] for x in p], [0.88, None])


class TestComparaTemps(unittest.TestCase):
    def test_compara_les_vores_amb_un_srt(self):
        paraules = [{"text": t, "inici": a, "final": b} for t, a, b in
                    [("Hola,", 0.0, 0.4), ("què", 0.5, 0.7), ("tal?", 0.8, 1.2), ("Bé.", 3.0, 3.3)]]
        srt = [{"start": 0.02, "end": 1.21, "text": "Hola, què tal?"}, {"start": 3.3, "end": 3.6, "text": "Bé."}]
        r = transcripcio.compara_temps(paraules, srt)
        self.assertEqual(r["n"], 4)  # inici de «Hola», final de «tal?», i les dues vores de «Bé.»
        self.assertEqual((r["mes_025"], r["mes_05"]), (2, 0))
        self.assertEqual(r["grans"][0]["text"], "Bé.")

    def test_la_mediana_i_els_llindars(self):
        # Revisió de Codex: amb [0, 1] la mediana sortia 1, i 0,4 − 0,3 comptava com a més d'una dècima.
        paraules = [{"text": "a", "inici": 0.4, "final": 1.0}, {"text": "b", "inici": 2.0, "final": 3.0}]
        srt = [{"start": 0.3, "end": 1.0, "text": "a"}, {"start": 2.0, "end": 3.0, "text": "b"}]
        r = transcripcio.compara_temps(paraules, srt)
        self.assertEqual((r["mediana"], r["mes_01"]), (0.0, 0))


class TestAlineadorSegur(unittest.TestCase):
    """L'alineador no es refia d'un text que no correspon al so, i les gravacions llargues van a trossos."""

    def test_trossos_de_frases(self):
        frases = [{"start": i * 60.0, "end": i * 60.0 + 50, "text": "x"} for i in range(12)]  # 12 minuts
        trossos = list(transcripcio._trossos_de_frases(frases, 720.0))
        self.assertEqual([(i, j) for i, j, _, _ in trossos], [(0, 6), (6, 12)])
        self.assertEqual(trossos[1][2:], (360.0 - 20, 720.0))  # amb marge (fins on s'acaba el so)
        self.assertEqual(trossos[0][2], 0.0)

    def test_un_text_que_no_correspon_al_so_no_s_accepta(self):
        from unittest import mock
        frases = [{"start": 0.0, "end": 2.0, "text": "u dos tres quatre"}]
        audio = np.zeros(16000 * 2, dtype=np.float32)
        temps = [(0.1, 0.2), (0.3, 0.4), (0.5, 0.6), (0.7, 0.8)]
        with mock.patch.object(transcripcio, "model_alineador", return_value=(None, None)):
            with mock.patch.object(transcripcio, "temps_paraules", return_value=(temps, [0.9, 0.1, 0.1, 0.9])):
                with self.assertRaises(ValueError):
                    transcripcio.alinea_global(audio, frases)
            with mock.patch.object(transcripcio, "temps_paraules", return_value=(temps, [0.9, 0.9, 0.1, 0.9])):
                segments = transcripcio.alinea_global(audio, frases)
        self.assertEqual([w["word"] for w in segments[0]["words"]], ["u", "dos", "tres", "quatre"])


class TestRealinea(unittest.TestCase):
    def test_canvia_els_temps_i_res_mes(self):
        import argparse
        from unittest import mock
        import tallat
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "proxy.mp4").write_bytes(b"x")
            paraules = [{"id": i, "text": t, "inici": i * 1.0, "final": i * 1.0 + 0.5, "frase": 0}
                        for i, t in enumerate(["Hola,", "què", "tal?"])]
            (d / "transcripcio.json").write_text(json.dumps({"video": str(d / "ja-no-hi-es.mov"), "fps": "30",
                                                             "durada": 4.0, "font": "WhisperX", "paraules": paraules}))
            segments = [{"start": 0.2, "end": 2.9, "text": "Hola, què tal?",
                         "words": [{"word": "Hola,", "start": 0.2, "end": 0.6}, {"word": "què", "start": 1.3, "end": 1.6},
                                   {"word": "tal?", "start": 2.2, "end": 2.9}]}]
            with mock.patch.object(tallat.transcripcio, "carrega_audio", return_value=None) as audio, \
                    mock.patch.object(tallat.transcripcio, "alinea", return_value=segments):
                tallat.ordre_realinea(argparse.Namespace(projecte=str(d)))
            self.assertEqual(audio.call_args[0][0].name, "proxy.mp4")  # l'original no hi és: la còpia lleugera
            dades = json.loads((d / "transcripcio.json").read_text())
            self.assertEqual([(p["text"], p["inici"], p["frase"]) for p in dades["paraules"]],
                             [("Hola,", 0.2, 0), ("què", 1.3, 0), ("tal?", 2.2, 0)])
            self.assertEqual(len(list(d.glob("transcripcio-abans-*.json"))), 1)
