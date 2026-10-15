import unittest
import xml.dom.minidom
from pathlib import Path

from motor import editors


def pla(fps="30"):
    t = editors._Temps(fps)
    return {"t": t, "info": {"amplada": 2160, "alcada": 3840, "durada": 20.0},
            "trossos": [{"a": 30, "b": 90, "offset": 0, "zoom": False},
                        {"a": 300, "b": 330, "offset": 60, "zoom": True}],
            "total": 90,
            "brolls": [{"id": "b1", "fitxer": Path("/tmp/b1.mp4"), "inici": 1.5, "durada": 1.5}],
            "stickers": [{"id": "s1", "fitxer": Path("/tmp/cor & co.png"), "inici": 2.2, "durada": 0.6,
                          "x": 0.72, "y": 0.3, "rot": 8, "mida": 0.34, "px": (500, 500)}]}


class TestEditors(unittest.TestCase):
    def test_temps(self):
        t = editors._Temps("30")
        self.assertEqual(t.fcp(0), "0s")
        self.assertEqual(t.fcp(45), "3/2s")
        self.assertEqual(t.fcp(60), "2s")
        ntsc = editors._Temps("30000/1001")
        self.assertEqual(ntsc.fcp(30), "1001/1000s")
        self.assertEqual(ntsc.durada_fotograma, "1001/30000s")
        self.assertEqual(ntsc.timebase, (30, True))
        self.assertEqual(ntsc.fotogrames(1.001), 30)

    def test_srt(self):
        text = editors.srt([{"inici": 0.0, "final": 1.25, "paraules": [{"text": "Hola"}, {"text": "món"}]},
                            {"inici": 3661.5, "final": 3662.0, "paraules": [{"text": "adeu"}]}])
        self.assertEqual(text, "1\n00:00:00,000 --> 00:00:01,250\nHola món\n\n"
                               "2\n01:01:01,500 --> 01:01:02,000\nadeu\n")

    def test_fcpxml(self):
        doc = editors.fcpxml("Prova", Path("/tmp/la meva gravació.MOV"), pla())
        dom = xml.dom.minidom.parseString(doc)  # XML ben format, amb noms de fitxer amb espais i «&»
        clips = [c for c in dom.getElementsByTagName("asset-clip") if c.getAttribute("ref") == "r3"]
        self.assertEqual([(c.getAttribute("offset"), c.getAttribute("start"), c.getAttribute("duration"))
                          for c in clips], [("0s", "1s", "2s"), ("2s", "10s", "1s")])
        zoom = [n for n in clips[1].childNodes if n.nodeName == "adjust-transform"]
        self.assertEqual(zoom[0].getAttribute("scale"), "1.15 1.15")  # el segon tros porta zoom
        self.assertFalse([n for n in clips[0].childNodes if n.nodeName == "adjust-transform"])
        broll = [c for c in dom.getElementsByTagName("asset-clip") if c.getAttribute("lane") == "1"][0]
        self.assertEqual(broll.getAttribute("offset"), "5/2s")  # 1,5 s del muntatge = 1 s + 1,5 s de l'original
        sticker = dom.getElementsByTagName("video")[0]
        self.assertEqual(sticker.parentNode, clips[1])  # el sticker cau al segon tros
        self.assertIn("la%20meva%20gravaci%C3%B3.MOV", doc)

    def test_premiere(self):
        doc = editors.xmeml("Prova", Path("/tmp/la meva gravació.MOV"), pla())
        dom = xml.dom.minidom.parseString(doc)
        items = dom.getElementsByTagName("clipitem")
        primer = items[0]
        valors = {k: primer.getElementsByTagName(k)[0].firstChild.data for k in ("start", "end", "in", "out")}
        self.assertEqual(valors, {"start": "0", "end": "60", "in": "30", "out": "90"})
        escales = [p.getElementsByTagName("value")[0].firstChild.data for p in dom.getElementsByTagName("parameter")
                   if p.getElementsByTagName("parameterid")[0].firstChild.data == "scale"]
        self.assertEqual(escales[:2], ["50.00", "57.50"])  # 2160 → 1080 (50 %), i amb zoom ×1,15
        self.assertEqual(len(dom.getElementsByTagName("track")), 4)  # vídeo, b-roll, stickers i so

    def test_un_nom_amb_cometes_no_trenca_el_fcpxml(self):
        # Segona revisió de Codex: les cometes dins dels noms trencaven l'XML de Final Cut i DaVinci.
        doc = editors.fcpxml('El "meu" reel', Path('/tmp/la "meva" gravació.MOV'), pla())
        dom = xml.dom.minidom.parseString(doc)
        self.assertEqual(dom.getElementsByTagName("project")[0].getAttribute("name"), 'El "meu" reel')

    def test_premiere_a_60_fps_amb_b_roll_a_30(self):
        # Segona revisió de Codex: el b-roll (a 30 fps) s'hi declarava amb els fps del vídeo (60):
        # 1,5 s eren 90 fotogrames quan el fitxer només en té 45.
        dades = pla("60")
        doc = editors.xmeml("Prova", Path("/tmp/video.MOV"), dades, capa=Path("/tmp/subtitols.mov"))
        dom = xml.dom.minidom.parseString(doc)
        valor = lambda node, nom: node.getElementsByTagName(nom)[0].firstChild.data
        broll = next(c for c in dom.getElementsByTagName("clipitem") if valor(c, "name") == "b1")
        self.assertEqual({k: valor(broll, k) for k in ("start", "end", "in", "out", "duration", "timebase")},
                         {"start": "90", "end": "180", "in": "0", "out": "45", "duration": "45", "timebase": "30"})
        capa = next(c for c in dom.getElementsByTagName("clipitem") if valor(c, "name") == "subtitols")
        self.assertEqual({k: valor(capa, k) for k in ("start", "end", "out", "timebase")},
                         {"start": "0", "end": "90", "out": "45", "timebase": "30"})

    def test_els_fps_dels_recursos_coincideixen(self):
        from motor import broll, subtitols
        self.assertEqual({broll.FPS, subtitols.FPS}, {editors.FPS_RECURSOS})

    def test_trossos(self):
        self.assertEqual(editors._moment(78.12), "1m18,1s")
        self.assertEqual(editors._on({"x": 0.28, "y": 0.3}), "a dalt a l'esquerra")
        text = editors._llista_recursos([{"inici": 38.4, "durada": 1.5}], [{"inici": 57.0, "durada": 2.0, "x": 0.72, "y": 0.3}])
        self.assertIn("B1 al 0m38,4s, durant 1,5 s", text)
        self.assertIn("S1 al 0m57,0s, durant 2,0 s, a dalt a la dreta", text)


if __name__ == "__main__":
    unittest.main()


class TestBrollEnTargeta(unittest.TestCase):
    def test_la_targeta_va_al_seu_lloc(self):
        from motor import targetes
        p = pla()
        p["brolls"] = targetes.disposa(p["brolls"], {"disposicio": "targeta", "mida": 0.5, "proporcio": "9:16",
                                                     "posicio_x": 0.25, "posicio_y": 0.25, "radi": 0.1})
        lloc = editors._lloc_broll(p["brolls"][0])
        self.assertAlmostEqual(lloc["escala"], 0.5)
        self.assertEqual(lloc["retall"], (0.0, 0.0))  # 9:16 dins de 9:16: no cal retallar
        self.assertAlmostEqual(lloc["centre"][0], -0.25)
        fcp = xml.dom.minidom.parseString(editors.fcpxml("Prova", Path("/tmp/v.mov"), p))
        broll = [c for c in fcp.getElementsByTagName("asset-clip") if c.getAttribute("lane") == "1"][0]
        self.assertEqual(broll.getElementsByTagName("adjust-transform")[0].getAttribute("scale"), "0.5000 0.5000")
        premiere = editors.xmeml("Prova", Path("/tmp/v.mov"), p)
        self.assertIn("<effectid>crop</effectid>", premiere)
        xml.dom.minidom.parseString(premiere)

    def test_a_pantalla_sencera_res_de_nou(self):
        self.assertIsNone(editors._lloc_broll({"inici": 0, "durada": 1}))
        from motor import targetes
        self.assertIsNone(editors._lloc_broll(targetes.disposa([{"id": "b", "inici": 0, "durada": 1}], {})[0]))
