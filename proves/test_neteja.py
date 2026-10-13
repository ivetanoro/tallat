import unittest
from pathlib import Path

from motor import edicio, neteja

LLISTA = neteja.carrega_llista(neteja.LLISTA_PER_DEFECTE)


def paraules(*textos, pas=0.5):
    return [{"id": i, "text": t, "inici": i * pas, "final": i * pas + 0.3, "frase": 0}
            for i, t in enumerate(textos)]


class TestNeteja(unittest.TestCase):
    def test_treu_farciment_i_paraules_a_mig_dir(self):
        p = paraules("Ehm,", "una", "experè--", "una", "experiència", "mmmm.")
        treure, _ = neteja.detecta(p, LLISTA)
        self.assertEqual(treure, {0: "farciment", 2: "tall", 5: "farciment"})

    def test_paraules_dubtoses_nomes_es_proposen(self):
        p = paraules("Això", "és", "normal,", "vale?", "O", "sigui", "que", "sí.")
        treure, proposar = neteja.detecta(p, LLISTA)
        self.assertEqual(treure, {})
        self.assertEqual(proposar, {3: "farciment?", 4: "farciment?", 5: "farciment?"})

    def test_sons_repetits_son_expressius(self):
        p = paraules("volta", "uh,", "uh,", "uh,", "DJ", "set.")
        treure, proposar = neteja.detecta(p, LLISTA)
        self.assertEqual(treure, {})
        self.assertEqual(set(proposar.values()), {"expressiu?"})

    def test_repeticio_doble_es_proposa(self):
        p = paraules("donar", "la,", "la", "teta")
        _, proposar = neteja.detecta(p, LLISTA)
        self.assertEqual(proposar, {1: "repeticio?"})

    def test_u_de_numero_no_es_farciment(self):
        p = paraules("ho", "fan,", "u,", "per", "relaxar-se")
        treure, proposar = neteja.detecta(p, LLISTA)
        self.assertEqual((treure, proposar), ({}, {}))

    def test_la_neteja_respecta_el_que_has_recuperat(self):
        estat = edicio.estat_buit()
        estat["mantingudes"] = [0]
        estat["esborrades"] = {3: "usuari"}
        estat = edicio.aplica_neteja(estat, {0: "farciment", 1: "farciment"}, {})
        self.assertEqual(estat["esborrades"], {3: "usuari", 1: "farciment"})


class TestSilencis(unittest.TestCase):
    def test_silenci_llarg_es_escurça(self):
        p = [{"id": 0, "text": "Hola.", "inici": 1.0, "final": 1.5, "frase": 0, "conservada": True},
             {"id": 1, "text": "Adéu.", "inici": 4.0, "final": 4.5, "frase": 1, "conservada": True}]
        sense = edicio.trams(p, fps=30, durada=10)
        amb = edicio.trams(p, fps=30, durada=10, pausa_maxima=0.4)
        self.assertEqual(len(sense), 1)
        self.assertEqual(len(amb), 2)
        pausa = amb[1][0] - amb[0][1]
        self.assertAlmostEqual(4.0 - 1.5 - pausa, 0.4, delta=2 / 30)  # queden ~0,4 s de silenci


if __name__ == "__main__":
    unittest.main()
