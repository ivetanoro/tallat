import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from motor import exporta, marca, targetes

ARREL = Path(__file__).resolve().parent.parent


def brolls(*inicis, durada=1.5):
    return [{"id": f"b{i}", "inici": t, "durada": durada} for i, t in enumerate(inicis)]


class TestDisposicio(unittest.TestCase):
    def test_pantalla_sencera_per_defecte(self):
        b = targetes.disposa(brolls(1.0), {})[0]
        self.assertEqual((b["caixa"]["w"], b["caixa"]["h"], b["fins"], b["partida"]), (1080, 1920, 2.5, False))

    def test_la_targeta_no_surt_de_la_pantalla(self):
        b = targetes.disposa(brolls(0), {"disposicio": "targeta", "mida": 0.6, "posicio_x": 1.0, "posicio_y": 0.0,
                                         "proporcio": "1:1", "radi": 0.1})[0]["caixa"]
        self.assertEqual((b["x"] + b["w"], b["y"], b["w"], b["h"], b["radi"]), (1080, 0, 648, 648, 64.8))
        alta = targetes.disposa(brolls(0), {"disposicio": "targeta", "mida": 1.0, "proporcio": "9:16"})[0]["caixa"]
        self.assertLessEqual(alta["h"], 0.92 * 1920 + 0.01)  # massa alta: s'encongeix

    def test_la_vora_sense_color_fa_servir_el_destacat_del_kit(self):
        estil = {"disposicio": "targeta", "vora": 0.01}
        self.assertEqual(targetes.disposa(brolls(0), estil, "#FFD60A")[0]["caixa"]["vora_color"], "#FFD60A")
        self.assertEqual(targetes.disposa(brolls(0), {**estil, "vora_color": "#112233"}, "#FFD60A")[0]["caixa"]
                         ["vora_color"], "#112233")

    def test_carrusel_agrupa_els_seguits_fins_a_tres(self):
        llista = targetes.disposa(brolls(0, 1.8, 3.6, 5.4, 12), {"disposicio": "carrusel"})
        fins = [b["fins"] for b in llista]
        self.assertEqual(fins, [5.1, 5.1, 5.1, 6.9, 13.5])  # el 4t comença un grup nou (màxim tres)
        self.assertEqual([b["caixa"]["rotacio"] for b in llista], [-6, 0, 6, 0, 0])

    def test_pantalla_partida(self):
        b = targetes.disposa(brolls(0), {"disposicio": "partida"})[0]
        self.assertTrue(b["partida"])
        self.assertEqual((b["caixa"]["h"], b["caixa"]["y"]), (960, 0))

    def test_els_estils_predefinits_son_valids(self):
        for e in marca.estils_broll():
            self.assertEqual(marca.valida("broll", e["valors"]), e["valors"])
            self.assertTrue(targetes.mostra(e["valors"]))
        with self.assertRaises(ValueError):
            marca.valida("broll", {"disposicio": "espiral"})
        self.assertEqual(marca.valida("broll", {"vora": 0.5}), {"vora": 0.04})


def _avalua(expr: str, t: float) -> float:
    return eval(expr.replace("\\,", ",").replace("t-0.0000", "t").replace("t", str(t)),
                {"pow": pow, "min": min, "max": max})


@unittest.skipUnless(shutil.which("node"), "cal node")
class TestMateixaAnimacio(unittest.TestCase):
    """La vista prèvia (pagina/app.js) i l'export (motor/targetes.py) fan la mateixa entrada."""

    def test_formules_iguals(self):
        codi = (ARREL / "pagina" / "app.js").read_text(encoding="utf-8")
        funcio = re.search(r"function animacioBroll\(b, m\) \{.*?\n\}\n", codi, re.S).group(0)
        temps = [0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.6]
        casos = [{"animacio": a, "inici": 0, "entrada": targetes.ENTRADA, "direccio": 1, "caixa": {"rotacio": 0}}
                 for a in ("pop", "puja", "llisca", "fos")]
        script = funcio + f"console.log(JSON.stringify({json.dumps(casos)}.map((b) => {json.dumps(temps)}" \
                          ".map((m) => animacioBroll(b, m)))))"
        js = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
        for cas, valors in zip(casos, js):
            for t, v in zip(temps, valors):
                nums = [float(x) for x in re.findall(r"-?[\d.]+(?:e-?\d+)?", v["transform"])]
                dx, dy, escala = nums[0], nums[1], nums[3]
                p = min(1, t / targetes.ENTRADA)
                if cas["animacio"] == "pop":
                    self.assertAlmostEqual(escala, 0.8 + 0.2 * _avalua(targetes._salt("t"), t), places=4)
                    self.assertAlmostEqual(float(v["opacity"]), min(1, p / 0.4), places=4)
                elif cas["animacio"] == "puja":
                    self.assertAlmostEqual(dy, 96 * (1 - _avalua(targetes._cubica("t"), t)), places=3)
                    self.assertAlmostEqual(float(v["opacity"]), p, places=4)
                elif cas["animacio"] == "llisca":
                    self.assertAlmostEqual(dx, 380 * (1 - _avalua(targetes._cubica("t"), t)), places=3)


@unittest.skipUnless(shutil.which("ffmpeg"), "cal ffmpeg")
class TestExport(unittest.TestCase):
    def test_exporta_targetes_amb_vora_i_ombra(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:r=30:d=3",
                            "-f", "lavfi", "-i", "sine=d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                            str(d / "v.mp4")], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=1080x1920:r=30:d=1",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(d / "b.mp4")], check=True)
            for estil, punt in (({"disposicio": "targeta", "vora": 0.02, "vora_color": "#00FF00", "ombra": True,
                                  "animacio": "pop", "rotacio": 5, "posicio_y": 0.5, "mida": 0.6}, "360:640"),
                                ({"disposicio": "partida", "animacio": "fos"}, "360:320")):
                llista = targetes.disposa([{"id": "b", "fitxer": d / "b.mp4", "inici": 1.0, "durada": 1.0}], estil)
                exporta.exporta(d / "v.mp4", [(0.0, 3.0)], d / "s.mp4", "esborrany", brolls=llista)
                pixel = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1.8", "-i", str(d / "s.mp4"), "-frames:v", "1",
                                        "-vf", f"crop=2:2:{punt}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                       capture_output=True, check=True).stdout
                self.assertGreater(pixel[0], 200)  # al mig de la targeta (o a dalt, en partida): el b-roll vermell
                self.assertLess(pixel[2], 60)


if __name__ == "__main__":
    unittest.main()
