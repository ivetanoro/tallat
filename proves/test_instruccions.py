import unittest

from motor import edicio, instruccions


def paraules(text: str, pausa_despres: dict | None = None):
    """Una paraula cada 0,4 s; pausa_despres = {índex: segons extra de silenci després}."""
    resultat, t = [], 0.0
    for i, w in enumerate(text.split()):
        resultat.append({"id": i, "text": w, "inici": round(t, 3), "final": round(t + 0.3, 3), "frase": 0})
        t += 0.4 + (pausa_despres or {}).get(i, 0)
    return resultat


class TestDeteccio(unittest.TestCase):
    def test_instruccio_al_principi_de_frase(self):
        p = paraules("Això és bo. Claude, aquí posa b-roll d'una rentadora. I continuo parlant.", {8: 0.8})
        trobades = instruccions.detecta(p)
        self.assertEqual(len(trobades), 1)
        self.assertEqual(trobades[0]["tipus"], "broll")
        self.assertEqual(trobades[0]["paraules"], [3, 8])
        self.assertEqual(trobades[0]["ancora"], 9)

    def test_mencio_no_es_instruccio(self):
        p = paraules("vull saber si Claude detecta quan el menciono.")
        self.assertEqual(instruccions.detecta(p), [])

    def test_variants_del_transcriptor(self):
        p = paraules("Fins aquí. Clot, zoom aquí. Ara sí.", {4: 0.8})
        trobades = instruccions.detecta(p)
        self.assertEqual([t["tipus"] for t in trobades], ["zoom"])

    def test_tallat_i_codex_tambe_serveixen(self):
        p = paraules("Fins aquí. Tallat, zoom aquí. Ara sí. Codex, sticker d'un cor. Seguim.", {4: 0.8, 11: 0.8})
        self.assertEqual([t["tipus"] for t in instruccions.detecta(p)], ["zoom", "sticker"])

    def test_un_tallat_qualsevol_no_es_instruccio(self):
        # «tallat» és una paraula normal: sense una ordre coneguda no compta (amb «Claude» sí, com a «altre»)
        p = paraules("Bon dia. Tallat amb llet, si us plau. Claude, recorda-ho.", {6: 0.8})
        self.assertEqual([t["tipus"] for t in instruccions.detecta(p)], ["altre"])

    def test_una_frase_que_comenca_per_clau_no_es_instruccio(self):
        # Segona revisió de Codex: «Clau» és una paraula normal i la frase sencera s'esborrava.
        p = paraules("Bon dia. Clau per entendre el problema: escoltar abans de respondre.", {1: 0.8})
        self.assertEqual(instruccions.detecta(p), [])

    def test_clau_amb_una_ordre_si_que_compta(self):
        p = paraules("Fins aquí. Clau, zoom aquí. Ara sí.", {4: 0.8})
        self.assertEqual([t["tipus"] for t in instruccions.detecta(p)], ["zoom"])

    def test_torno_a_comencar_troba_el_primer_intent(self):
        text = ("Us heu fixat mai que les idees venen tard? Exemple el cotxe "
                "Claude, torno a començar. Us heu fixat mai que les millors idees venen tard?")
        p = paraules(text, {11: 1.0, 15: 0.8})  # silenci abans de «Claude» i després de «començar»
        ins = instruccions.detecta(p)[0]
        self.assertEqual(ins["tipus"], "talla")
        self.assertEqual(ins["treure"], [0, 11])  # del primer «Us» fins a «cotxe»

    def test_les_paraules_de_la_instruccio_es_treuen(self):
        p = paraules("Hola. Claude, zoom aquí. Adéu.", {3: 0.8})
        estat = instruccions.aplica_a_estat(edicio.estat_buit(), instruccions.detecta(p))
        self.assertEqual(sorted(estat["esborrades"]), [1, 2, 3])
        self.assertEqual(set(estat["esborrades"].values()), {"instruccio"})

    def test_una_instruccio_curta_no_s_empassa_la_frase_seguent(self):
        # Revisió de Codex: amb puntuació i pauses curtes, la frase de després quedava dins de la instrucció.
        p = paraules("Claude, zoom aquí. Aquesta frase ha de quedar al vídeo.")
        ins = instruccions.detecta(p)
        self.assertEqual([(i["tipus"], i["paraules"]) for i in ins], [("zoom", [0, 2])])
        self.assertEqual(ins[0]["ancora"], 3)
        estat = instruccions.aplica_a_estat(edicio.estat_buit(), ins)
        self.assertEqual(sorted(estat["esborrades"]), [0, 1, 2])

    def test_sense_puntuacio_acaba_en_un_silenci_llarg(self):
        p = paraules("Claude posa un b-roll d'una rentadora i ara continuo parlant", {5: 1.2})
        self.assertEqual(instruccions.detecta(p)[0]["paraules"], [0, 5])

    def test_una_pausa_curta_dins_la_instruccio_no_la_talla(self):
        p = paraules("Claude, posa un b-roll d'una rentadora. Seguim.", {3: 0.5})
        self.assertEqual(instruccions.detecta(p)[0]["text"], "posa un b-roll d'una rentadora.")

    def test_sense_final_clar_no_es_treu_res(self):
        p = paraules("Claude " + " ".join(f"paraula{i}" for i in range(40)))
        ins = instruccions.detecta(p)
        self.assertTrue(ins[0]["dubtosa"])
        self.assertEqual(instruccions.aplica_a_estat(edicio.estat_buit(), ins)["esborrades"], {})

    def test_tornar_a_detectar_no_perd_feina(self):
        p = paraules("Hola. Claude, b-roll d'un vinil. Adéu.", {5: 0.8})
        velles = instruccions.detecta(p)
        velles[0].update(estat="acceptada", fitxer="broll/i1.mp4", durada=1.5)
        manual = {"id": "m3-1", "tipus": "sticker", "text": "un cor", "paraules": None, "inici": 2.0,
                  "final": 2.0, "ancora": 6, "estat": "acceptada", "manual": True, "fitxer": "stickers/m3-1.png"}
        perduda = {"id": "i99", "tipus": "broll", "text": "una dutxa", "paraules": [99, 100], "inici": 9.0,
                   "final": 9.5, "ancora": 101, "estat": "acceptada", "fitxer": "broll/i99.mp4"}
        noves = instruccions.fusiona(instruccions.detecta(p), velles + [manual, perduda])
        per_id = {n["id"]: n for n in noves}
        self.assertEqual((per_id["i1"]["estat"], per_id["i1"]["fitxer"], per_id["i1"]["durada"]),
                         ("acceptada", "broll/i1.mp4", 1.5))
        self.assertIn("m3-1", per_id)  # la manual es queda
        self.assertIn("i99", per_id)   # ja no es troba, però tenia un fitxer: es queda

    def test_la_neteja_no_les_torna_a_posar(self):
        estat = edicio.estat_buit()
        estat["esborrades"] = {1: "instruccio", 2: "farciment"}
        estat = edicio.aplica_neteja(estat, {}, {})
        self.assertEqual(estat["esborrades"], {1: "instruccio"})


if __name__ == "__main__":
    unittest.main()
