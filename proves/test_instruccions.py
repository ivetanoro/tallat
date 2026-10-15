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

    def test_la_neteja_no_les_torna_a_posar(self):
        estat = edicio.estat_buit()
        estat["esborrades"] = {1: "instruccio", 2: "farciment"}
        estat = edicio.aplica_neteja(estat, {}, {})
        self.assertEqual(estat["esborrades"], {1: "instruccio"})


if __name__ == "__main__":
    unittest.main()
