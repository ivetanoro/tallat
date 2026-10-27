import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from motor import notes


class TestNotes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.carpeta = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_d_una_nota_a_la_resposta(self):
        n = notes.afegeix(self.carpeta, "  aquí, el títol més gran  ", paraula=3, inici=1.5, cita="el cabell")
        self.assertEqual((n["id"], n["estat"], n["fil"][0]["text"]), (1, "esborrany", "aquí, el títol més gran"))
        self.assertEqual(notes.pren(self.carpeta), [])  # encara no s'ha enviat
        self.assertEqual(notes.envia(self.carpeta), 1)
        preses = notes.pren(self.carpeta)
        self.assertEqual([p["id"] for p in preses], [1])
        notes.respon(self.carpeta, 1, "Fet: el títol ara és més gran.")
        dades = notes.llegeix(self.carpeta)
        self.assertEqual(dades["notes"][0]["estat"], "feta")
        self.assertEqual([m["de"] for m in dades["notes"][0]["fil"]], ["persona", "claude"])
        self.assertEqual(notes.pren(self.carpeta), [])

    def test_la_ronda_s_envia_sola_i_diu_a_claude_on_mirar(self):
        notes.afegeix(self.carpeta, "una que encara no ha enviat")
        n = notes.afegeix(self.carpeta, "Ronda següent de propostes.", tipus="ronda")
        self.assertEqual(notes.envia(self.carpeta, nomes=n["id"]), 1)  # només la de la ronda
        self.assertEqual([x["estat"] for x in notes.llegeix(self.carpeta)["notes"]], ["esborrany", "enviada"])
        presa = notes.pren(self.carpeta)[0]
        self.assertEqual(presa["tipus"], "ronda")
        self.assertIn("tallat.py grafics", notes.text_per_a_claude(presa, lambda s: f"{s:.0f} s"))

    def test_una_pregunta_i_la_resposta_de_la_persona(self):
        notes.afegeix(self.carpeta, "canvia el color")
        notes.envia(self.carpeta)
        notes.pren(self.carpeta)
        notes.respon(self.carpeta, 1, "De quin color el vols?", pregunta=True)
        self.assertEqual(notes.llegeix(self.carpeta)["notes"][0]["estat"], "pregunta")
        notes.respon_persona(self.carpeta, 1, "blau")  # torna a Claude de seguida, sense «Envia»
        self.assertEqual(notes.llegeix(self.carpeta)["notes"][0]["estat"], "enviada")
        nota = notes.pren(self.carpeta)[0]
        self.assertEqual([m["text"] for m in nota["fil"]], ["canvia el color", "De quin color el vols?", "blau"])
        # Li arriba per segon cop perquè la persona hi ha respost, no perquè Claude no l'hagués resposta.
        self.assertNotIn("Ja te l'havia donat", notes.text_per_a_claude(nota, lambda t: "0:00"))
        text = notes.text_per_a_claude(nota, lambda t: "0:00")
        self.assertIn("Nota 1 (per a tot el vídeo)", text)
        nota["inici"] = 7.9
        self.assertIn("al 0:04 del vídeo, el 0:07 de la gravació",
                      notes.text_per_a_claude(nota, lambda t: f"0:{int(t):02d}", al_video=4.2))
        self.assertIn("Tu: De quin color el vols?", text)

    def test_les_agafades_sense_resposta_es_tornen_a_donar_passada_l_estona(self):
        # Dues esperes alhora (o Claude que torna a esperar abans d'acabar) no reben la mateixa nota dos cops;
        # però si Claude s'atura a mitges, passada l'estona li torna a arribar, i se li diu.
        notes.afegeix(self.carpeta, "una")
        notes.envia(self.carpeta)
        self.assertEqual(len(notes.pren(self.carpeta)), 1)
        self.assertEqual(notes.pren(self.carpeta), [])
        with mock.patch("motor.notes.time.time", return_value=time.time() + notes.REAGAFA + 1):
            [nota] = notes.pren(self.carpeta)
        self.assertEqual(nota["cops"], 2)
        self.assertIn("Ja te l'havia donat", notes.text_per_a_claude(nota, lambda t: "0:00"))

    def test_el_que_la_persona_hi_afegeix_mentre_claude_treballa_no_es_perd(self):
        # Revisió de Codex: Claude agafa «blau», la persona hi afegeix «millor vermell» (des d'una altra pestanya)
        # i Claude respon «fet: blau». La nota no es pot donar per feta: li ha de tornar a arribar.
        notes.afegeix(self.carpeta, "canvia el color")
        notes.envia(self.carpeta)
        notes.pren(self.carpeta)
        notes.respon_persona(self.carpeta, 1, "millor vermell")
        self.assertEqual(notes.llegeix(self.carpeta)["notes"][0]["estat"], "treballant")
        notes.respon(self.carpeta, 1, "Fet: blau.")
        self.assertEqual(notes.llegeix(self.carpeta)["notes"][0]["estat"], "enviada")
        [nota] = notes.pren(self.carpeta)
        self.assertEqual([m["text"] for m in nota["fil"]], ["canvia el color", "millor vermell", "Fet: blau."])
        notes.respon(self.carpeta, 1, "Fet: vermell.")
        self.assertEqual(notes.llegeix(self.carpeta)["notes"][0]["estat"], "feta")

    def test_la_resposta_d_una_vegada_d_abans_no_tanca_la_nota(self):
        # Revisió de Codex: A l'agafa, la persona hi afegeix una cosa, passa l'estona i B la torna a agafar. Si ara A
        # respon (amb el número de la seva vegada, «1.1»), la resposta es desa però la nota continua sent de B.
        notes.afegeix(self.carpeta, "canvia el color")
        notes.envia(self.carpeta)
        [de_a] = notes.pren(self.carpeta)
        self.assertEqual(notes.id_per_respondre(de_a), "1.1")
        self.assertIn("--respon 1.1", notes.text_per_a_claude(de_a, lambda t: "0:00"))
        notes.respon_persona(self.carpeta, 1, "millor vermell")
        with mock.patch("motor.notes.time.time", return_value=time.time() + notes.REAGAFA + 1):
            [de_b] = notes.pren(self.carpeta)
        notes.respon(self.carpeta, 1, "Fet: blau.", cop=1)
        nota = notes.llegeix(self.carpeta)["notes"][0]
        self.assertEqual((nota["estat"], nota["fil"][-1]["text"]), ("treballant", "Fet: blau."))
        with self.assertRaises(ValueError):  # un número de vegada que no existeix no la deixa encallada en silenci
            notes.respon(self.carpeta, 1, "Fet.", cop=de_b["cops"] + 1)
        notes.respon(self.carpeta, 1, "Fet: vermell.", cop=de_b["cops"])
        self.assertEqual(notes.llegeix(self.carpeta)["notes"][0]["estat"], "feta")

    def test_dues_esperes_alhora_no_es_trepitgen_el_senyal(self):
        # Cada procés escriu el seu temporal; i en acabar, només treu el senyal si és seu.
        notes.marca_connexio(self.carpeta)
        self.assertEqual(list(self.carpeta.glob("*.tmp")), [])
        (self.carpeta / notes.CONNEXIO).write_text(json.dumps({"vist": time.time(), "pid": -1}), encoding="utf-8")
        notes.deixa_connexio(self.carpeta)  # el senyal és d'una altra espera: es queda
        self.assertTrue(notes.connectat(self.carpeta))

    def test_nomes_es_treuen_les_que_no_s_han_enviat(self):
        notes.afegeix(self.carpeta, "una")
        notes.afegeix(self.carpeta, "dues")
        notes.esborra(self.carpeta, 1)
        notes.envia(self.carpeta)
        with self.assertRaises(ValueError):
            notes.esborra(self.carpeta, 2)
        with self.assertRaises(ValueError):
            notes.afegeix(self.carpeta, "   ")
        self.assertEqual([n["id"] for n in notes.llegeix(self.carpeta)["notes"]], [2])

    def test_a_la_pagina_es_numeren_per_l_ordre_del_video(self):
        totes = [{"id": 1, "projecte": "a", "inici": 9.0}, {"id": 2, "projecte": "a", "inici": 2.0},
                 {"id": 3, "projecte": "a", "inici": None}, {"id": 4, "projecte": "b", "inici": 5.0},
                 {"id": 5, "projecte": "a", "versio": "v1", "t_versio": 4.0},
                 {"id": 6, "projecte": "a", "versio": "v1", "t_versio": 1.0}]
        numeros = notes.numeros_pagina(totes, lambda n: n["inici"] / 2)
        # Les de tot el vídeo primer; cada projecte i cada versió compten a part.
        self.assertEqual(numeros, {3: 1, 2: 2, 1: 3, 4: 1, 6: 1, 5: 2})
        text = notes.text_per_a_claude({"id": 1, "inici": None, "fil": [{"de": "persona", "text": "hola"}], "estat": "enviada"},
                                       lambda t: "0:00", numero=3)
        self.assertTrue(text.startswith("Nota 1 (a la pàgina, la 3) "))

    def test_un_numero_no_es_torna_a_fer_servir(self):
        # Si es treu l'última nota, la següent no es queda el seu número: la pàgina recorda coses de cada nota pel
        # número (la resposta a mig escriure, quina està desplegada…) i se les trobaria en una altra.
        notes.afegeix(self.carpeta, "una")
        notes.afegeix(self.carpeta, "dues")
        notes.esborra(self.carpeta, 2)
        self.assertEqual(notes.afegeix(self.carpeta, "tres")["id"], 3)
        notes.esborra(self.carpeta, 3)
        notes.esborra(self.carpeta, 1)
        self.assertEqual(notes.afegeix(self.carpeta, "quatre")["id"], 4)
        # Un notes.json d'abans (sense «darrera») continua igual.
        (self.carpeta / notes.FITXER).write_text(json.dumps({"versio": 3, "notes": [{**notes.llegeix(self.carpeta)[
            "notes"][0], "id": 7}]}), encoding="utf-8")
        self.assertEqual(notes.afegeix(self.carpeta, "cinc")["id"], 8)

    def test_la_miniatura_se_n_va_amb_la_nota(self):
        carpeta = self.carpeta / notes.MINIATURES
        carpeta.mkdir()
        (carpeta / "abc.jpg").write_bytes(b"foto")
        (self.carpeta / "altre.jpg").write_bytes(b"no s'ha de tocar")
        notes.afegeix(self.carpeta, "aquí", versio="v.mp4", t_versio=1.0, miniatura="abc.jpg")
        notes.afegeix(self.carpeta, "allà", versio="v.mp4", t_versio=2.0, miniatura="../altre.jpg")
        notes.esborra(self.carpeta, 1)
        notes.esborra(self.carpeta, 2)
        self.assertFalse((carpeta / "abc.jpg").exists())
        self.assertTrue((self.carpeta / "altre.jpg").exists())  # només noms de dins de la carpeta de les miniatures

    def test_envia_nomes_les_del_reel_que_es_veu(self):
        notes.afegeix(self.carpeta, "del vídeo sencer", projecte="/a")
        notes.afegeix(self.carpeta, "del reel", projecte="/a/reels/r1")
        self.assertEqual(notes.envia(self.carpeta, projecte="/a/reels/r1"), 1)
        self.assertEqual([n["estat"] for n in notes.llegeix(self.carpeta)["notes"]], ["esborrany", "enviada"])
        notes.respon_persona(self.carpeta, 1, "i una cosa més")  # encara per enviar: s'hi afegeix i prou
        self.assertEqual(notes.llegeix(self.carpeta)["notes"][0]["estat"], "esborrany")

    def test_dos_processos_alhora_no_perden_notes(self):
        # La pàgina i Claude hi escriuen alhora (a Windows i al Mac): el bloqueig ho ordena.
        def escriu(prefix):
            for i in range(25):
                notes.afegeix(self.carpeta, f"{prefix} {i}")
        fils = [threading.Thread(target=escriu, args=(p,)) for p in ("a", "b", "c")]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        dades = notes.llegeix(self.carpeta)
        self.assertEqual(len(dades["notes"]), 75)
        self.assertEqual(len({n["id"] for n in dades["notes"]}), 75)
        self.assertEqual(dades["versio"], 75)

    def test_un_bloqueig_oblidat_no_ho_atura_tot(self):
        # Si un procés s'acaba a mitges, el fitxer del bloqueig es queda, però ja no bloqueja res.
        (self.carpeta / (notes.FITXER + ".bloqueig")).write_text("")
        notes.afegeix(self.carpeta, "hola")
        self.assertEqual(len(notes.llegeix(self.carpeta)["notes"]), 1)

    def test_dos_processos_de_debo_no_perden_notes(self):
        # La pàgina i Claude són dos processos: el bloqueig del sistema els ha d'ordenar (al Mac i a Windows).
        codi = ("import sys; from pathlib import Path; from motor import notes\n"
                "for i in range(20): notes.afegeix(Path(sys.argv[1]), f'{sys.argv[2]} {i}')")
        arrel = Path(__file__).resolve().parent.parent
        processos = [subprocess.Popen([sys.executable, "-c", codi, str(self.carpeta), nom], cwd=arrel)
                     for nom in ("a", "b", "c")]
        self.assertEqual([p.wait(timeout=60) for p in processos], [0, 0, 0])
        dades = notes.llegeix(self.carpeta)
        self.assertEqual((len(dades["notes"]), len({n["id"] for n in dades["notes"]}), dades["versio"]), (60, 60, 60))

    def test_l_espera_diu_que_hi_es_connectat_i_agafa_les_notes(self):
        estats = []

        def envia_despres():
            time.sleep(0.3)
            estats.append(notes.connectat(self.carpeta))
            notes.afegeix(self.carpeta, "ja")
            notes.envia(self.carpeta)

        threading.Thread(target=envia_despres).start()
        with mock.patch.object(notes, "AGRUPA", 0):
            preses = notes.espera(self.carpeta, 5, cada=0.05)
        self.assertEqual([p["fil"][0]["text"] for p in preses], ["ja"])
        self.assertEqual(estats, [True])  # mentre esperava, la pàgina deia «Connectat amb Claude»
        self.assertFalse(notes.connectat(self.carpeta))  # en acabar, ja no

    def test_a_windows_un_fitxer_obert_no_ho_atura(self):
        # A Windows, substituir un fitxer que un altre procés llegeix falla un moment: s'hi torna.
        real, cops = os.replace, []

        def replace(a, b):
            cops.append(1)
            if len(cops) < 3:
                raise PermissionError("en ús")
            real(a, b)
        with mock.patch("motor.notes.os.replace", side_effect=replace), mock.patch("motor.notes.time.sleep"):
            notes.afegeix(self.carpeta, "hola")
        self.assertEqual(len(cops), 3)
        self.assertEqual(notes.llegeix(self.carpeta)["notes"][0]["fil"][0]["text"], "hola")
        with mock.patch("motor.notes.os.replace", side_effect=PermissionError("en ús")), mock.patch("motor.notes.time.sleep"):
            notes.marca_connexio(self.carpeta)  # el senyal de connexió es perd un segon, però l'espera continua

    def test_les_que_s_envien_seguides_arriben_juntes(self):
        # Qui les envia d'una en una (cada nota, «Envia») les rep juntes: l'espera dona uns segons per si n'hi ha més.
        def envia_dues():
            for text in ("una", "dues"):
                notes.afegeix(self.carpeta, text)
                notes.envia(self.carpeta)
                time.sleep(0.15)
        with mock.patch.object(notes, "AGRUPA", 0.4):
            threading.Thread(target=envia_dues).start()
            preses = notes.espera(self.carpeta, 5, cada=0.05)
        self.assertEqual([p["fil"][0]["text"] for p in preses], ["una", "dues"])

    def test_un_permis_es_pregunta_al_xat(self):
        notes.afegeix(self.carpeta, "posa aquesta imatge d'internet")
        notes.envia(self.carpeta)
        notes.pren(self.carpeta)
        notes.respon(self.carpeta, 1, "T'ho pregunto al xat.", al_xat=True)
        nota = notes.llegeix(self.carpeta)["notes"][0]
        self.assertEqual((nota["estat"], nota["al_xat"]), ("pregunta", True))
        notes.respon(self.carpeta, 1, "Fet.")
        nota = notes.llegeix(self.carpeta)["notes"][0]
        self.assertEqual((nota["estat"], nota["al_xat"]), ("feta", False))

    def test_l_espera_s_acaba_encara_que_no_n_arribi_cap(self):
        t0 = time.time()
        self.assertEqual(notes.espera(self.carpeta, 0.2, cada=0.05), [])
        self.assertLess(time.time() - t0, 2)


class TestOrdreNotes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.carpeta = Path(self.dir.name)
        (self.carpeta / "transcripcio.json").write_text(json.dumps({"paraules": []}), encoding="utf-8")

    def tearDown(self):
        self.dir.cleanup()

    def ordre(self, **kw):
        import tallat
        args = argparse.Namespace(projecte=str(self.carpeta), espera=False, minuts=9, respon=None, pregunta=False,
                                  al_xat=False)
        for k, v in kw.items():
            setattr(args, k, v)
        sortida = io.StringIO()
        with redirect_stdout(sortida):
            tallat.ordre_notes(args)
        return sortida.getvalue()

    def test_espera_ensenya_les_notes_i_respon(self):
        notes.afegeix(self.carpeta, "més gran", paraula=2, inici=72.4, cita="taronja",
                      projecte=str(self.carpeta / "reels" / "r1"), reel="El primer")
        notes.envia(self.carpeta)
        text = self.ordre(espera=True, minuts=0.01)
        self.assertIn("Ha arribat 1 nota", text)
        # El reel no existeix: no se sap on cau al vídeo editat, i es diu.
        self.assertIn("Nota 1 (al 1:12 de la gravació, un tros que ara no surt al vídeo, a «taronja» (paraula 2), "
                      "al reel «El primer»)", text)
        self.assertIn("La persona: més gran", text)
        self.assertIn("reels", text)  # on s'ha de fer
        self.assertIn("--respon 1.1", text)
        self.assertIn("Resposta desada", self.ordre(respon=["1.1", "Fet: ara és més gran."]))
        self.assertIn("[feta]", self.ordre())

    def test_sense_notes(self):
        self.assertIn("Encara no ha arribat cap nota", self.ordre(espera=True, minuts=0.001))
        with self.assertRaises(SystemExit):
            self.ordre(respon=["7", "hola"])


if __name__ == "__main__":
    unittest.main()
