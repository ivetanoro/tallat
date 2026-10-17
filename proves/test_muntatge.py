import argparse
import json
import tempfile
import unittest
from pathlib import Path

import tallat
from motor import muntatge
from motor.projecte import Projecte


def paraules(n: int) -> list[dict]:
    return [{"id": i, "text": f"p{i}", "inici": i * 0.5, "final": i * 0.5 + 0.4, "frase": 0} for i in range(n)]


class TestReels(unittest.TestCase):
    def test_trossos_repetits_o_solapats_son_errors(self):
        # Revisió de Codex: [[4,5],[0,1],[4,5]] es donava per bo, però el muntatge només en feia sonar un.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / muntatge.REELS).write_text(json.dumps({"reels": [
                {"id": "a", "paraules": [[4, 5], [0, 1], [4, 5]]},
                {"id": "b", "paraules": [[0, 3], [2, 6]]},
                {"id": "c", "paraules": [[7, 9], [0, 2]]},
            ]}), encoding="utf-8")
            reels, errors = muntatge.llegeix_reels(Path(d), paraules(10))
        self.assertEqual({r["id"]: r["paraules"] for r in reels},
                         {"a": [(4, 5), (0, 1)], "b": [(0, 3)], "c": [(7, 9), (0, 2)]})
        self.assertEqual(len(errors), 2)
        self.assertIn("repeteix", errors[0])


class TestRetranscriure(unittest.TestCase):
    def test_un_reel_no_es_pot_retranscriure(self):
        # Revisió de Codex: el reel comparteix transcripcio.json (enllaç) amb la gravació sencera.
        with tempfile.TemporaryDirectory() as d:
            arrel, reel = Path(d) / "gravacio", Path(d) / "gravacio" / "reels" / "un"
            reel.mkdir(parents=True)
            (arrel / "transcripcio.json").write_text("{}", encoding="utf-8")
            (reel / "transcripcio.json").symlink_to(arrel / "transcripcio.json")
            video = Path(d) / "video.mov"
            video.write_bytes(b"")
            args = argparse.Namespace(video=str(video), projecte=str(reel), forca=True, srt=None,
                                      model="large-v3", sense_neteja=False)
            with self.assertRaises(SystemExit) as e:
                tallat.ordre_transcriu(args)
            self.assertIn("reel", str(e.exception.code))
            self.assertEqual((arrel / "transcripcio.json").read_text(encoding="utf-8"), "{}")


class TestRecursosDelReel(unittest.TestCase):
    def test_un_b_roll_d_un_tros_que_no_hi_es_no_entra_al_reel(self):
        # Revisió de Codex: un b-roll amb l'àncora a la paraula 1 sortia al principi d'un reel
        # que només fa servir les paraules 4 i 5.
        with tempfile.TemporaryDirectory() as d:
            carpeta = Path(d)
            (carpeta / "transcripcio.json").write_text(json.dumps(
                {"video": str(carpeta / "no-hi-es.mov"), "fps": "30", "durada": 5.0, "paraules": paraules(10)}),
                encoding="utf-8")
            (carpeta / "broll").mkdir()
            for nom in ("i1.mp4", "i2.mp4"):
                (carpeta / "broll" / nom).write_bytes(b"")
            (carpeta / "instruccions.json").write_text(json.dumps([
                {"id": f"i{k}", "tipus": "broll", "text": "x", "paraules": None, "inici": 0, "final": 0,
                 "ancora": ancora, "estat": "acceptada", "manual": True, "fitxer": f"broll/i{k}.mp4"}
                for k, ancora in ((1, 1), (2, 4))]), encoding="utf-8")
            projecte = Projecte(carpeta)
            projecte.estat["esborrades"] = {i: "muntatge" for i in range(10) if i not in (4, 5)}
            projecte.estat["ordre"] = [[4, 5]]
            brolls = projecte.brolls(projecte.trams())
        self.assertEqual([b["id"] for b in brolls], ["i2"])
        self.assertLess(brolls[0]["inici"], 0.1)  # al principi del reel (amb el petit marge d'abans de la paraula)


def projecte_amb(carpeta: Path, instruccions_: list[dict]) -> Projecte:
    (carpeta / "transcripcio.json").write_text(json.dumps(
        {"video": str(carpeta / "no-hi-es.mov"), "fps": "30", "durada": 5.0, "paraules": paraules(10)}),
        encoding="utf-8")
    (carpeta / "instruccions.json").write_text(json.dumps(instruccions_), encoding="utf-8")
    return Projecte(carpeta)


ZOOM = {"id": "i2", "tipus": "zoom", "text": "zoom aquí", "paraules": [2, 3], "inici": 1.0, "final": 1.9,
        "ancora": 4, "estat": "acceptada"}
REPRESA = {"id": "i6", "tipus": "talla", "text": "torno a començar", "paraules": [6, 6], "inici": 3.0,
           "final": 3.4, "ancora": 7, "treure": [5, 5], "estat": "acceptada"}


class TestDecisionsAlsReels(unittest.TestCase):
    def test_un_reel_nou_aplica_les_instruccions_ja_acceptades(self):
        # Segona revisió de Codex: el reel les mostrava acceptades, però no feia el zoom ni treia la represa.
        with tempfile.TemporaryDirectory() as d:
            arrel = projecte_amb(Path(d), [ZOOM, REPRESA])
            reel = Projecte(muntatge.crea_reel(arrel, {"id": "r", "paraules": [(4, 9)]}))
            self.assertIn(4, reel.estat["zooms"])
            self.assertEqual(reel.estat["esborrades"].get(5), "instruccio")
            self.assertTrue(reel.zooms_per_tram(reel.trams())[0])

    def test_acceptar_un_zoom_a_la_gravacio_tambe_val_al_reel(self):
        with tempfile.TemporaryDirectory() as d:
            arrel = projecte_amb(Path(d), [{**ZOOM, "estat": "pendent"}])
            carpeta_reel = muntatge.crea_reel(arrel, {"id": "r", "paraules": [(4, 9)]})
            self.assertFalse(Projecte(carpeta_reel).zooms_per_tram(Projecte(carpeta_reel).trams())[0])
            arrel.decideix_instruccio("i2", "acceptada")
            reel = Projecte(carpeta_reel)
            self.assertTrue(reel.zooms_per_tram(reel.trams())[0])


class TestReelsSenseEnllacos(unittest.TestCase):
    """A Windows, fer enllaços demana permisos especials: el reel funciona igual sense, buscant la
    transcripció, la còpia lleugera i les instruccions a la gravació sencera."""

    def test_un_reel_sense_enllacos(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            arrel = projecte_amb(Path(d), [ZOOM])
            (Path(d) / "proxy.mp4").write_bytes(b"x")
            with mock.patch.object(Path, "symlink_to", side_effect=OSError(1314, "A required privilege is not held")):
                carpeta_reel = muntatge.crea_reel(arrel, {"id": "r", "paraules": [(4, 9)]})
            self.assertFalse(any(f.is_symlink() for f in carpeta_reel.iterdir()))
            reel = Projecte(carpeta_reel)
            self.assertEqual(reel.arrel, arrel.carpeta)
            self.assertEqual(reel.fitxer("proxy.mp4"), arrel.carpeta / "proxy.mp4")
            self.assertEqual(reel.carpeta_instruccions(), arrel.carpeta)
            self.assertTrue(reel.zooms_per_tram(reel.trams())[0])  # l'instrucció de la gravació sencera hi val
            # Les ordres del terminal també l'obren (abans demanaven transcripcio.json a la carpeta del reel).
            self.assertEqual(tallat._carrega(argparse.Namespace(projecte=str(carpeta_reel))).arrel, arrel.carpeta)

    def test_la_primera_instruccio_d_un_reel_va_a_la_gravacio(self):
        # Revisió de Codex: si la gravació encara no en tenia, la primera es quedava només al reel.
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            arrel = projecte_amb(Path(d), [])
            (Path(d) / "instruccions.json").unlink()
            with mock.patch.object(Path, "symlink_to", side_effect=OSError(1314, "A required privilege is not held")):
                reel = Projecte(muntatge.crea_reel(arrel, {"id": "r", "paraules": [(4, 9)]}))
            self.assertEqual(reel.carpeta_instruccions(), arrel.carpeta)

    def test_l_arxiu_d_un_mapa_de_veu_es_una_copia(self):
        # Revisió de Codex: sense enllaços, veu.npy s'arxivava amb un enllaç dur i refer-lo canviava tots dos.
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            carpeta = Path(d)
            (carpeta / "transcripcio.json").write_text("{}", encoding="utf-8")
            (carpeta / "edicio.json").write_text("{}", encoding="utf-8")
            (carpeta / "veu.npy").write_bytes(b"mapa vell")
            (carpeta / "proxy.mp4").write_bytes(b"video")
            with mock.patch.object(Path, "symlink_to", side_effect=OSError(1314, "A required privilege is not held")):
                anteriors = tallat.guarda_anteriors(carpeta)
            (carpeta / "veu.npy").write_bytes(b"mapa nou")  # es reescriu al mateix lloc
            self.assertEqual((anteriors / "veu.npy").read_bytes(), b"mapa vell")
            self.assertEqual((anteriors / "proxy.mp4").read_bytes(), b"video")


class TestGuardaAnteriors(unittest.TestCase):
    def test_els_reels_guardats_conserven_la_transcripcio_vella(self):
        # Segona revisió de Codex: els reels arxivats seguien apuntant a la transcripció nova.
        with tempfile.TemporaryDirectory() as d:
            carpeta = Path(d)
            (carpeta / "transcripcio.json").write_text('{"vella": true}', encoding="utf-8")
            (carpeta / "instruccions.json").write_text("[]", encoding="utf-8")
            (carpeta / "edicio.json").write_text("{}", encoding="utf-8")
            (carpeta / "broll").mkdir()
            (carpeta / "broll" / "i1.mp4").write_bytes(b"clip")
            reel = carpeta / "reels" / "r"
            reel.mkdir(parents=True)
            (reel / "transcripcio.json").symlink_to(Path("..") / ".." / "transcripcio.json")
            (reel / "instruccions.json").symlink_to(Path("..") / ".." / "instruccions.json")
            anteriors = tallat.guarda_anteriors(carpeta)
            (carpeta / "transcripcio.json").write_text('{"nova": true}', encoding="utf-8")
            guardat = anteriors / "reels" / "r"
            self.assertEqual(json.loads((guardat / "transcripcio.json").read_text(encoding="utf-8")), {"vella": True})
            self.assertEqual(json.loads((guardat / "instruccions.json").read_text(encoding="utf-8")), [])
            self.assertEqual((anteriors / "broll" / "i1.mp4").read_bytes(), b"clip")
            self.assertTrue((anteriors / "edicio.json").exists())
            self.assertFalse((carpeta / "reels").exists() or (carpeta / "instruccions.json").exists())


class TestCanviarSticker(unittest.TestCase):
    STICKER = {"id": "i3", "tipus": "sticker", "text": "un cor", "paraules": None, "inici": 1.5, "final": 1.5,
               "ancora": 3, "estat": "acceptada", "manual": True}

    def test_si_el_nou_falla_el_d_abans_es_queda(self):
        # Segona revisió de Codex: s'esborrava i3.png abans de copiar el nou, i si fallava es perdia.
        with tempfile.TemporaryDirectory() as d:
            projecte = projecte_amb(Path(d), [self.STICKER])
            vell = Path(d) / "cor.png"
            vell.write_bytes(b"png")
            projecte.assigna_sticker("i3", vell)
            with self.assertRaises(OSError):
                projecte.assigna_sticker("i3", Path(d) / "no-hi-es.webp")
            self.assertEqual((Path(d) / "stickers" / "i3.png").read_bytes(), b"png")
            self.assertEqual(projecte.instruccions()[0]["fitxer"], "stickers/i3.png")

    def test_canviar_de_format_no_en_deixa_dos(self):
        with tempfile.TemporaryDirectory() as d:
            projecte = projecte_amb(Path(d), [self.STICKER])
            for nom in ("cor.png", "cor.webp"):
                (Path(d) / nom).write_bytes(nom.encode())
                projecte.assigna_sticker("i3", Path(d) / nom)
            self.assertEqual(sorted(f.name for f in (Path(d) / "stickers").iterdir()), ["i3.webp"])


if __name__ == "__main__":
    unittest.main()
