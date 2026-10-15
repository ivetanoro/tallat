import tempfile
import unittest
from pathlib import Path
from unittest import mock

from motor import marca, subtitols

ESTIL = marca.carrega(marca.PER_DEFECTE)["subtitols"]


def paraules(*specs):
    """specs: (text, inici, final[, conservada])"""
    return [{"id": i, "text": s[0], "inici": s[1], "final": s[2], "frase": 0,
             "conservada": s[3] if len(s) > 3 else True} for i, s in enumerate(specs)]


class TestGrups(unittest.TestCase):
    def test_temps_al_muntatge_salta_el_que_es_treu(self):
        p = paraules(("Hola,", 1.0, 1.4), ("eh,", 1.6, 2.0, False), ("com", 2.2, 2.4), ("estàs?", 2.5, 3.0))
        linies = subtitols.grups(p, [(0.96, 1.6), (2.0, 3.04)], ESTIL)
        textos = [w["text"] for l in linies for w in l["paraules"]]
        self.assertEqual(textos, ["Hola", "com", "estàs?"])  # sense coma, amb interrogant
        com = linies[0]["paraules"][1]
        self.assertAlmostEqual(com["inici"], 0.64 + (2.2 - 2.0), places=3)

    def test_maxim_de_paraules_per_linia(self):
        p = paraules(*[(f"p{i}", i * 0.3, i * 0.3 + 0.25) for i in range(7)])
        linies = subtitols.grups(p, [(0, 3)], dict(ESTIL, paraules_per_linia=3))
        self.assertEqual([len(l["paraules"]) for l in linies], [3, 3, 1])

    def test_final_de_frase_i_pausa_obren_linia(self):
        p = paraules(("Sí.", 0.0, 0.3), ("Molt", 0.4, 0.6), ("bé", 0.7, 0.9), ("ara", 2.0, 2.2))
        linies = subtitols.grups(p, [(0, 3)], ESTIL)
        self.assertEqual([[w["text"] for w in l["paraules"]] for l in linies], [["Sí"], ["Molt", "bé"], ["ara"]])

    def test_correccio_es_fa_servir(self):
        p = paraules(("satura", 0.0, 0.4))
        p[0]["correccio"] = "s'atura"
        self.assertEqual(subtitols.grups(p, [(0, 1)], ESTIL)[0]["paraules"][0]["text"], "s'atura")

    def test_cap_linia_passa_del_final(self):
        p = paraules(("final", 0.0, 0.9))
        self.assertLessEqual(subtitols.grups(p, [(0, 1)], ESTIL)[-1]["final"], 1.0)

    def test_composicio_registra_el_timeline(self):
        p = paraules(("Hola", 0.0, 0.4))
        html = subtitols.composicio(subtitols.grups(p, [(0, 1)], ESTIL), ESTIL, 1.0)
        self.assertIn('data-composition-id="subtitols"', html)
        self.assertIn('window.__timelines["subtitols"] = tl', html)

    def test_composicio_fa_servir_el_codi_compartit(self):
        p = paraules(("Hola", 0.0, 0.4), ("món", 0.5, 0.9))
        linies = subtitols.grups(p, [(0, 1)], ESTIL)
        estil = dict(ESTIL, apareixen="linia", animacio="impacte")
        html = subtitols.composicio(linies, estil, 1.0, escala=0.5)
        self.assertIn('<script src="subtitols.js"></script>', html)
        self.assertIn("TallatSubtitols.construeix(", html)
        self.assertIn('"animacio": "impacte"', html)
        self.assertIn('"text": "món"', html)
        self.assertIn("transform: scale(0.5)", html)
        self.assertTrue(subtitols.CODI_ANIMACIO.exists())

    def test_res_del_text_trenca_el_script(self):
        p = paraules(("</script><b>", 0.0, 0.4))
        html = subtitols.composicio(subtitols.grups(p, [(0, 1)], ESTIL), ESTIL, 1.0)
        self.assertNotIn("</script><b>", html)

    def test_nom_de_font_amb_espais(self):
        self.assertEqual(subtitols.familia_css(dict(ESTIL, font="Avenir Next"), False), '"Avenir Next", sans-serif')
        self.assertEqual(subtitols.familia_css(dict(ESTIL, font="system-ui"), False), "system-ui, sans-serif")
        self.assertNotIn("}", subtitols.familia_css(dict(ESTIL, font='x"; } body {'), False))
        self.assertIn("SubtitolsMarca", subtitols.familia_css(ESTIL, True))


class TestParaulesClau(unittest.TestCase):
    def test_numeros_i_paraula_important(self):
        p = paraules(("en", 0.0, 0.1), ("tinc", 0.2, 0.3), ("25", 0.4, 0.5), ("de", 0.6, 0.7), ("música", 0.8, 0.9))
        linia = subtitols.grups(p, [(0, 1)], dict(ESTIL, paraules_per_linia=7, lletres_per_linia=40))[0]
        claus = [w["text"] for w in linia["paraules"] if w["clau"]]
        self.assertEqual(claus, ["25", "música"])
        self.assertEqual([w["emoji"] for w in linia["paraules"]], [None, None, None, None, "🎵"])

    def test_emojis(self):
        self.assertEqual(subtitols.emoji_de("d'idees,"), "💡")
        self.assertEqual(subtitols.emoji_de("Minuts"), "⏰")  # «minut*» vol dir qualsevol paraula que comenci així
        self.assertIsNone(subtitols.emoji_de("que"))


class TestMemoriaDelRender(unittest.TestCase):
    def test_canviar_la_font_amb_el_mateix_nom_torna_a_dibuixar(self):
        # Revisió de Codex: la vista prèvia ja feia servir la font nova, però el vídeo reaprofitava el dibuix vell.
        dibuixos = []

        def hyperframes(ordre, **_):
            sortida = Path(ordre[ordre.index("--output") + 1])
            sortida.write_bytes(b"mov")
            dibuixos.append(sortida)
            return mock.Mock(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(subtitols.subprocess, "run", hyperframes):
            font = Path(d) / "la-meva.ttf"
            font.write_bytes(b"lletra antiga")
            estil = {**ESTIL, "font_fitxer": str(font)}
            linies = [{"inici": 0.0, "final": 1.0, "paraules": [{"text": "hola", "inici": 0.0, "final": 1.0}]}]
            primer = subtitols.renderitza(linies, estil, 1.0, Path(d), "esborrany")
            self.assertEqual(subtitols.renderitza(linies, estil, 1.0, Path(d), "esborrany"), primer)
            self.assertEqual(len(dibuixos), 1)
            font.write_bytes(b"lletra nova")
            self.assertNotEqual(subtitols.renderitza(linies, estil, 1.0, Path(d), "esborrany"), primer)
            self.assertEqual(len(dibuixos), 2)


if __name__ == "__main__":
    unittest.main()
