import argparse
import json
import tempfile
import unittest
from pathlib import Path

import tallat
from motor import muntatge


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


if __name__ == "__main__":
    unittest.main()
