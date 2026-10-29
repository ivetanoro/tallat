import http.client
import io
import json
import re
import socket
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from motor import marca, servidor
from motor.projecte import Projecte


def port_lliure() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestServidor(unittest.TestCase):
    """Un servidor de veritat sobre un projecte petit (sense vídeo)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.casa = tempfile.TemporaryDirectory()  # els kits d'aquesta prova
        self.pegats = [mock.patch.object(marca, "KITS", Path(self.casa.name) / "kits"),
                       mock.patch.object(marca, "USUARI", Path(self.casa.name) / "brand.json")]
        for pegat in self.pegats:
            pegat.start()
        self.carpeta = Path(self.dir.name)
        paraules = [{"id": i, "text": t, "inici": i * 0.5, "final": i * 0.5 + 0.4, "frase": 0}
                    for i, t in enumerate("Hola. Això és una prova.".split())]
        (self.carpeta / "transcripcio.json").write_text(json.dumps(
            {"video": str(self.carpeta / "no-hi-es.mov"), "fps": "30", "durada": 3.0, "paraules": paraules}),
            encoding="utf-8")
        (self.carpeta / "instruccions.json").write_text(json.dumps([
            {"id": "i1", "tipus": "broll", "text": "un vinil", "paraules": None, "inici": 0.5, "final": 0.5,
             "ancora": 1, "estat": "acceptada", "manual": True}]), encoding="utf-8")
        self.port = port_lliure()
        self.servidor = servidor.crea_servidor(Projecte(self.carpeta), self.port)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        pagina = self.peticio("GET", "/")[1]
        self.token = re.search(r'name="tallat-token" content="([^"]+)"', pagina).group(1)
        self.clau = json.loads(self.peticio("GET", "/api/projecte")[1])["clau_projecte"]

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        for pegat in self.pegats:
            pegat.stop()
        self.dir.cleanup()
        self.casa.cleanup()

    def peticio(self, metode, ruta, cos=None, capcaleres=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest(metode, ruta, skip_host=True)
        c.putheader("Host", host or f"127.0.0.1:{self.port}")
        for k, v in (capcaleres or {}).items():
            c.putheader(k, v)
        dades = cos if isinstance(cos, bytes) else (json.dumps(cos).encode() if cos is not None else b"")
        c.putheader("Content-Length", str(len(dades)))
        c.endheaders()
        if dades:
            c.send(dades)
        r = c.getresponse()
        resultat = (r.status, r.read().decode("utf-8", "replace"))
        c.close()
        return resultat

    def bones(self, **mes):
        return {"X-Tallat-Token": self.token, "X-Tallat-Projecte": self.clau,
                "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.port}", **mes}

    def test_les_notes_per_a_claude(self):
        from motor import notes
        estat, cos = self.peticio("POST", "/api/notes", {"accio": "afegeix", "text": "aquí, més gran", "paraula": 1},
                                  self.bones())
        self.assertEqual(estat, 200)
        dades = json.loads(cos)
        self.assertEqual([(n["id"], n["estat"], n["paraula"]) for n in dades["notes"]], [(1, "esborrany", 1)])
        nota = dades["notes"][0]  # el segon i el que es diu al voltant els posa el servidor, de la transcripció
        self.assertIsInstance(nota["inici"], float)
        self.assertTrue(nota["cita"])
        self.assertEqual(Path(dades["projecte"]).resolve(), self.carpeta.resolve())
        self.assertFalse(dades["connectat"])
        self.assertEqual(self.peticio("POST", "/api/notes", {"accio": "afegeix", "text": "x", "paraula": 99},
                                      self.bones())[0], 400)
        self.assertEqual(self.peticio("POST", "/api/notes", {"accio": "envia"},
                                      self.bones(**{"X-Tallat-Projecte": "un-altre"}))[0], 409)
        self.assertEqual(self.peticio("POST", "/api/notes", {"accio": "envia"}, self.bones())[0], 200)
        # Claude l'espera i la respon: la pàgina ho veu a les novetats i a /api/notes.
        notes.marca_connexio(self.carpeta)
        novetats = json.loads(self.peticio("GET", "/api/novetats")[1])
        self.assertTrue(novetats["connectat"])
        self.assertEqual(Path(notes.pren(self.carpeta)[0]["projecte"]).resolve(), self.carpeta.resolve())
        notes.respon(self.carpeta, 1, "Fet.")
        dades = json.loads(self.peticio("GET", "/api/notes")[1])
        self.assertEqual(dades["notes"][0]["estat"], "feta")
        self.assertGreater(dades["versio_notes"], novetats["versio_notes"])

    def test_les_notes_de_revisa(self):
        # A Revisa, la nota és d'una versió (un esborrany) i d'un segon d'aquell vídeo: la paraula surt dels talls
        # d'aquella versió, i es desa la miniatura. «Envia» des de Revisa només envia les d'aquella versió.
        import base64
        exports = self.carpeta / "exports"
        exports.mkdir()
        (exports / "prova_esborrany_1.mp4").write_bytes(b"video")
        (exports / "prova_esborrany_1.talls.json").write_text("[[0.5, 3.0]]", encoding="utf-8")
        jpeg = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff una foto").decode()
        estat, cos = self.peticio("POST", "/api/notes", {"accio": "afegeix", "text": "aquí més gran",
                                                         "versio": "prova_esborrany_1.mp4", "t": 0.6,
                                                         "miniatura": jpeg}, self.bones())
        self.assertEqual(estat, 200)
        nota = json.loads(cos)["notes"][0]
        self.assertEqual((nota["versio"], nota["t_versio"], nota["paraula"]), ("prova_esborrany_1.mp4", 0.6, 2))
        self.assertEqual(self.peticio("GET", f"/notes-miniatures/{nota['miniatura']}")[0], 200)
        self.assertEqual(self.peticio("POST", "/api/notes", {"accio": "afegeix", "text": "x", "versio": "no-hi-es.mp4",
                                                             "t": 1}, self.bones())[0], 400)
        self.peticio("POST", "/api/notes", {"accio": "afegeix", "text": "editant", "paraula": 1}, self.bones())
        dades = json.loads(self.peticio("POST", "/api/notes", {"accio": "envia", "versio": "prova_esborrany_1.mp4"},
                                        self.bones())[1])
        self.assertEqual([n["estat"] for n in dades["notes"]], ["enviada", "esborrany"])
        novetats = json.loads(self.peticio("GET", "/api/novetats")[1])
        self.assertEqual(novetats["darrer_export"], "prova_esborrany_1.mp4")
        # Mentre s'exporta (encara sense talls), la versió nova no compta (Codex).
        (exports / "prova_esborrany_2.mp4").write_bytes(b"a mitges")
        self.assertEqual(json.loads(self.peticio("GET", "/api/novetats")[1])["darrer_export"], "prova_esborrany_1.mp4")

    def test_si_no_es_pot_desar_una_nota_la_pagina_ho_diu(self):
        # El disc ple o la carpeta sense permís: abans la connexió es tallava i la pàgina deia «Load failed».
        import base64
        from motor import notes
        exports = self.carpeta / "exports"
        exports.mkdir()
        (exports / "prova_esborrany_1.mp4").write_bytes(b"video")
        (exports / "prova_esborrany_1.talls.json").write_text("[[0.5, 3.0]]", encoding="utf-8")
        jpeg = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff una foto").decode()
        with mock.patch.object(notes, "_escriu", side_effect=OSError(28, "No space left on device")):
            estat, cos = self.peticio("POST", "/api/notes", {"accio": "afegeix", "text": "aquí", "versio":
                                                             "prova_esborrany_1.mp4", "t": 0.6, "miniatura": jpeg},
                                      self.bones())
        self.assertEqual(estat, 500)
        self.assertEqual(json.loads(cos)["error"], "No he pogut desar la nota a la carpeta del projecte (el disc és ple).")
        self.assertEqual(list((self.carpeta / notes.MINIATURES).iterdir()), [])  # la miniatura no es queda sola

    def test_una_nota_de_revisa_al_comencament_d_un_tall_i_al_final(self):
        # Codex: al començament d'un tros (amb marge), la paraula d'abans pot ser una de les tretes; i al final de tot,
        # el reproductor pot dir el segon exacte que dura la versió.
        exports = self.carpeta / "exports"
        exports.mkdir()
        (exports / "v_esborrany_1.mp4").write_bytes(b"video")
        (exports / "v_esborrany_1.talls.json").write_text("[[0.97, 3.0]]", encoding="utf-8")
        afegeix = lambda t: self.peticio("POST", "/api/notes", {"accio": "afegeix", "text": "x", "versio": "v_esborrany_1.mp4",
                                                                "t": t}, self.bones())
        estat, cos = afegeix(0)
        nota = json.loads(cos)["notes"][-1]
        self.assertEqual((estat, nota["paraula"], nota["inici"]), (200, 2, 0.97))  # «és», no «Això» (treta)
        self.assertEqual(afegeix(2.03)[0], 200)
        self.assertEqual(afegeix(2.5)[0], 400)

    def test_un_zoom_posat_des_del_xat_arriba_a_la_pagina_oberta(self):
        # Posar un zoom o un sticker amb una ordre només toca instruccions.json: la pàgina oberta també ho ha de saber.
        abans = json.loads(self.peticio("GET", "/api/novetats")[1])["revisio"]
        Projecte(self.carpeta).afegeix_instruccio("zoom", 2, "més a prop", None)
        self.assertGreater(json.loads(self.peticio("GET", "/api/novetats")[1])["revisio"], abans)
        # I el que la pàgina mateixa canvia no compta com un canvi de fora.
        ara = json.loads(self.peticio("GET", "/api/novetats")[1])["revisio"]
        self.assertEqual(json.loads(self.peticio("GET", "/api/novetats")[1])["revisio"], ara)

    def test_les_imatges_dels_grafics(self):
        from motor import grafics
        p = Projecte(self.carpeta)
        p.estat["grafics"] = grafics.fusiona([], [{"tipus": "ventall", "paraula": 1}, {"tipus": "frase", "paraula": 2, "text": "x"}])
        p.estat["revisio"] = 5
        p.desa()
        bones = {k: v for k, v in self.bones().items() if k != "Content-Type"}
        self.assertEqual(self.peticio("POST", "/api/grafics/imatge?grafic=g1&nom=x.exe", b"hola", bones)[0], 400)
        self.assertEqual(self.peticio("POST", "/api/grafics/imatge?grafic=g2&nom=x.png", b"hola", bones)[0], 404)
        estat, cos = self.peticio("POST", "/api/grafics/imatge?grafic=g1&nom=foto.png", b"una foto", bones)
        self.assertEqual(estat, 200)
        g1 = json.loads(cos)["estat"]["grafics"][0]
        self.assertEqual((len(g1["punts"]), g1["estat"]), (1, "mantingut"))
        nom = g1["punts"][0]["imatge"]
        self.assertEqual(self.peticio("GET", f"/imatges-grafics/{nom}")[1], "una foto")
        # Un abans i després amb les dues fotos, però una que ja no hi és: la nova va al seu lloc.
        p = Projecte(self.carpeta)
        p.estat["grafics"].append(grafics.net({"id": "g3", "tipus": "abans", "paraula": 3, "punts": [nom, "0000aaaa.jpg"]}))
        p.desa()
        estat, cos = self.peticio("POST", "/api/grafics/imatge?grafic=g3&nom=despres.png", b"una altra", bones)
        self.assertEqual(estat, 200, cos)
        g3 = next(x for x in json.loads(cos)["estat"]["grafics"] if x["id"] == "g3")
        self.assertEqual(len(g3["punts"]), 2)
        self.assertNotEqual(g3["punts"][1]["imatge"], "0000aaaa.jpg")
        self.assertEqual(self.peticio("GET", "/imatges-grafics/../transcripcio.json")[0], 403)

    def test_la_previsualitzacio_continua(self):
        from motor import exporta

        class Projecte_:
            def __init__(self, carpeta):
                self.carpeta = carpeta

            def fitxer(self, nom):
                return self.carpeta / nom

            @property
            def proxy(self):
                return self.carpeta / "proxy.mp4"

            def previa(self, trams):
                return self.carpeta / "previa" / f"previa_{len(trams)}.mp4"

        def fes(proxy, trams, desti):
            desti.parent.mkdir(exist_ok=True)
            desti.write_bytes(b"mp4")

        projecte = Projecte_(self.carpeta)
        (self.carpeta / "proxy.mp4").write_bytes(b"x")
        previa = servidor.Previa()
        with mock.patch.object(exporta, "fes_previa", side_effect=fes):
            self.assertEqual(previa.demana(projecte, [(0, 1)])["estat"], "fent")
            for _ in range(100):  # el fil acaba de seguida
                if previa.fent is None:
                    break
                time.sleep(0.01)
            r = previa.demana(projecte, [(0, 1)])
            self.assertEqual((r["estat"], r["url"]), ("fet", "/previa/previa_1.mp4"))
            for n in range(2, 8):  # se'n fan més: només se'n guarden quatre, i mai la que s'ha demanat ara
                previa.demana(projecte, [(0, 1)] * n)
                for _ in range(100):
                    if previa.fent is None:
                        break
                    time.sleep(0.01)
                previa.demana(projecte, [(0, 1)])
        noms = sorted(p.name for p in (self.carpeta / "previa").glob("previa_*.mp4"))
        self.assertEqual(len(noms), 4)
        self.assertIn("previa_1.mp4", noms)
        # Els vídeos curts de l'antic «Escolta cada tall» se'n van amb la neteja.
        (self.carpeta / "previa" / "escolta_abc.mp4").write_bytes(b"mp4")
        with mock.patch.object(exporta, "fes_previa", side_effect=fes):
            previa.demana(projecte, [(0, 1)] * 9)
            for _ in range(100):
                if previa.fent is None:
                    break
                time.sleep(0.01)
        self.assertFalse((self.carpeta / "previa" / "escolta_abc.mp4").exists())
        self.assertEqual(previa.demana(projecte, [])["estat"], "no")

    def test_si_el_continu_falla_es_diu_i_no_es_torna_a_provar_de_seguida(self):
        # Revisió de Codex: si ffmpeg fallava, cada pregunta tornava a començar la feina i deia «fent», i la
        # pàgina (que espera el continu per fer sonar el vídeo) esperava per sempre.
        from motor import exporta

        class Projecte_:
            def __init__(self, carpeta):
                self.carpeta = carpeta

            def fitxer(self, nom):
                return self.carpeta / nom

            @property
            def proxy(self):
                return self.carpeta / "proxy.mp4"

            def previa(self, trams):
                return self.carpeta / "previa" / f"previa_{len(trams)}.mp4"

        def acaba(previa):
            for _ in range(200):
                if previa.fent is None:
                    return
                time.sleep(0.01)

        projecte = Projecte_(self.carpeta)
        (self.carpeta / "proxy.mp4").write_bytes(b"x")
        previa = servidor.Previa()
        intents = []

        def falla(proxy, trams, desti):
            intents.append(desti)
            raise RuntimeError("ffmpeg no ha pogut fer la previsualització")

        with mock.patch.object(exporta, "fes_previa", side_effect=falla), mock.patch.object(servidor.traceback, "print_exc"):
            self.assertEqual(previa.demana(projecte, [(0, 1)])["estat"], "fent")
            acaba(previa)
            for _ in range(3):  # ara diu que no s'ha pogut, i no ho torna a provar a cada pregunta
                r = previa.demana(projecte, [(0, 1)])
                self.assertEqual(r["estat"], "error")
                self.assertIn("ffmpeg", r["error"])
            self.assertEqual(len(intents), 1)
            # Uns altres talls sí que es proven.
            self.assertEqual(previa.demana(projecte, [(0, 1)] * 2)["estat"], "fent")
            acaba(previa)
            # Passada l'estona, es torna a provar (potser era un moment de disc ple).
            ara = time.time()
            with mock.patch.object(servidor.time, "time", return_value=ara + servidor.REPROVA_PREVIA + 1):
                self.assertEqual(previa.demana(projecte, [(0, 1)])["estat"], "fent")
            acaba(previa)
        self.assertEqual(len(intents), 3)

        def fes(proxy, trams, desti):
            desti.parent.mkdir(exist_ok=True)
            desti.write_bytes(b"mp4")

        with mock.patch.object(exporta, "fes_previa", side_effect=fes):
            with mock.patch.object(servidor.time, "time", return_value=time.time() + 2 * servidor.REPROVA_PREVIA):
                self.assertEqual(previa.demana(projecte, [(0, 1)])["estat"], "fent")
            acaba(previa)
            self.assertEqual(previa.demana(projecte, [(0, 1)])["estat"], "fet")
        self.assertNotIn(projecte.previa([(0, 1)]), previa.fallades)

    def test_si_no_es_pot_copiar_a_la_carpeta_l_export_no_falla(self):
        from motor import exporta
        with mock.patch.object(exporta, "copia_a_carpeta", side_effect=PermissionError(13, "Permission denied")):
            copia, avis = servidor._copia(self.carpeta / "video.mp4")
        self.assertIsNone(copia)
        self.assertIn("carpeta del projecte", avis)

    def test_nomes_amb_el_nom_d_aquest_mac(self):
        self.assertEqual(self.peticio("GET", "/api/projecte", host="dolenta.example")[0], 403)

    def test_peticions_d_altres_webs_rebutjades(self):
        kit = {"nom": "Kit d'una altra web"}
        self.assertEqual(self.peticio("POST", "/api/kit/nou", kit, {"Content-Type": "application/json"})[0], 403)
        self.assertEqual(self.peticio("POST", "/api/kit/nou", kit, self.bones(Origin="http://dolenta.example"))[0], 403)
        self.assertEqual(self.peticio("POST", "/api/kit/nou", kit, self.bones(**{"Content-Type": "text/plain"}))[0], 415)
        self.assertEqual([k["id"] for k in json.loads(self.peticio("GET", "/api/projecte")[1])["kits"]], ["el-meu-estil"])

    def test_una_altra_pestanya_amb_un_altre_projecte(self):
        estat, cos = self.peticio("POST", "/api/kit/nou", {"nom": "x"}, self.bones(**{"X-Tallat-Projecte": "un-altre"}))
        self.assertEqual((estat, json.loads(cos)["error"]), (409, "projecte-canviat"))

    def test_ja_no_hi_ha_regles_a_la_pagina(self):
        # Es van treure per simplificar: les regles del gust es diuen a Claude, al xat. (Les notes hi han
        # tornat d'una altra manera: Claude les espera i hi respon; vegeu test_les_notes_per_a_claude.)
        for ruta in ("/api/gust", "/api/gust/treu"):
            self.assertEqual(self.peticio("POST", ruta, {}, self.bones())[0], 404)
        dades = json.loads(self.peticio("GET", "/api/projecte")[1])
        self.assertNotIn("notes", dades)
        self.assertNotIn("gust", dades)

    def test_pujades_dolentes_no_deixen_res(self):
        bones = self.bones(**{"Content-Type": "application/octet-stream"})
        self.assertEqual(self.peticio("POST", "/api/broll/puja?instruccio=i1&nom=x.exe", b"hola", bones)[0], 400)
        self.assertEqual(self.peticio("POST", "/api/broll/puja?instruccio=i9&nom=x.png", b"hola", bones)[0], 404)
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)  # declara 3 GB i no n'envia cap
        c.putrequest("POST", "/api/broll/puja?instruccio=i1&nom=x.mp4", skip_host=True)
        for k, v in {**bones, "Host": f"127.0.0.1:{self.port}", "Content-Length": str(3 * 1024 ** 3)}.items():
            c.putheader(k, v)
        c.endheaders()
        self.assertEqual(c.getresponse().status, 413)
        c.close()
        pujats = self.carpeta / "broll" / "pujats"
        self.assertEqual(list(pujats.iterdir()) if pujats.exists() else [], [])

    def test_un_desament_lent_no_trepitja_el_reel_tornat_a_obrir(self):
        # Segona revisió de Codex: una petició començada abans de tornar a obrir el reel es desava
        # sobre l'estat vell i esborrava els canvis fets després.
        (self.carpeta / "reels.json").write_text(json.dumps({"reels": [{"id": "r", "paraules": [[0, 4]]}]}),
                                                 encoding="utf-8")
        self.assertEqual(self.peticio("POST", "/api/obre", {"reel": "r"}, self.bones())[0], 200)
        dades = json.loads(self.peticio("GET", "/api/projecte")[1])
        clau = dades["clau_projecte"]
        # Pestanya A: envia les capçaleres, però el cos arriba tard.
        lenta = {**dades["estat"], "esborrades": {"1": "usuari"}}
        cos = json.dumps(lenta).encode()
        a = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        a.putrequest("POST", "/api/estat", skip_host=True)
        for k, v in {**self.bones(**{"X-Tallat-Projecte": clau}), "Host": f"127.0.0.1:{self.port}",
                     "Content-Length": str(len(cos))}.items():
            a.putheader(k, v)
        a.endheaders()
        time.sleep(0.3)
        # Pestanya B: surt del reel, el torna a obrir i hi desa un canvi.
        self.peticio("POST", "/api/obre", {}, self.bones())
        self.peticio("POST", "/api/obre", {"reel": "r"}, self.bones())
        nou = {**json.loads(self.peticio("GET", "/api/projecte")[1])["estat"], "esborrades": {"2": "usuari"}}
        self.assertEqual(self.peticio("POST", "/api/estat", nou, self.bones(**{"X-Tallat-Projecte": clau}))[0], 200)
        a.send(cos)
        self.assertEqual(a.getresponse().status, 409)
        a.close()
        desat = json.loads((self.carpeta / "reels" / "r" / "edicio.json").read_text(encoding="utf-8"))
        self.assertIn("2", desat["esborrades"])
        self.assertNotIn("1", desat["esborrades"])

    def test_l_estil_d_un_video_i_fes_lo_servir_en_tots(self):
        dades = json.loads(self.peticio("GET", "/api/projecte")[1])
        self.assertTrue(any(e["id"] == "net" for e in dades["estils_video"]))
        nou = {**dades["estat"], "estil": {"subtitols": {"mida": 0.11, "pes": "molt"}, "grafics": "mac"}}
        estat, cos = self.peticio("POST", "/api/estat", nou, self.bones())
        self.assertEqual(estat, 200)
        r = json.loads(cos)
        self.assertEqual(r["estat"]["estil"], {"subtitols": {"mida": 0.11}, "grafics": "mac"})
        self.assertEqual(Projecte(self.carpeta).estil()["subtitols"]["mida"], 0.11)
        kit = Projecte(self.carpeta).kit()
        self.assertNotEqual(marca.carrega(kit=kit)["subtitols"]["mida"], 0.11)  # el kit, encara no
        # La pàgina rep l'estil del kit (hi posa al damunt el del vídeo).
        self.assertNotEqual(json.loads(self.peticio("GET", "/api/projecte")[1])["estil_subtitols"]["mida"], 0.11)
        estat, cos = self.peticio("POST", "/api/estil/a-tots", {}, self.bones())
        self.assertEqual(estat, 200)
        r = json.loads(cos)
        self.assertEqual(r["estat"]["estil"], {})
        self.assertEqual(r["estil_subtitols"]["mida"], 0.11)
        self.assertEqual(marca.carrega(kit=kit)["marca"]["energia"], ["mac"])

    def test_el_tauler_vots_i_ronda(self):
        dades = json.loads(self.peticio("GET", "/api/projecte")[1])
        grafics_ = [{"id": "g1", "tipus": "frase", "paraula": 1, "text": "una", "grup": "a1"},
                    {"id": "g2", "tipus": "etiqueta", "paraula": 1, "text": "dues", "grup": "a1", "vot": "potser", "nota": "més gran"}]
        nou = {**dades["estat"], "grafics": grafics_, "ronda": 1,
               "vots": {"broll:i1": {"vot": "potser", "nota": " més  curt ", "nom": "B-roll", "paraula": 1}, "zoom:x": {"vot": "no"}}}
        estat, cos = self.peticio("POST", "/api/estat", nou, self.bones())
        self.assertEqual(estat, 200)
        r = json.loads(cos)
        self.assertEqual(r["estat"]["vots"], {"broll:i1": {"vot": "potser", "nota": "més curt", "nom": "B-roll", "paraula": 1}})
        self.assertEqual(r["estat"]["grafics"][1]["estat"], "canvia")
        self.assertEqual([g["id"] for g in r["grafics"]], ["g1"])  # al vídeo, només una de les dues
        self.assertEqual([g["id"] for g in r["grafics_alternatives"]], ["g2"])  # l'altra, per al tauler
        # «Demana la ronda següent»: una nota per a tot el vídeo, que surt de seguida.
        estat, cos = self.peticio("POST", "/api/notes", {"accio": "ronda", "text": "menys coses"}, self.bones())
        self.assertEqual(estat, 200)
        nota = json.loads(cos)["notes"][-1]
        self.assertEqual((nota["tipus"], nota["estat"], nota["paraula"], nota["ronda"]), ("ronda", "enviada", None, 1))
        self.assertEqual(nota["fil"][0]["text"], "Ronda següent de propostes. Per a tota la ronda: «menys coses».")

    def test_un_so_posat_a_ma_sona_al_seu_moment(self):
        dades = json.loads(self.peticio("GET", "/api/projecte")[1])
        nou = {**dades["estat"], "sons": [{"id": "s1", "so": "pop", "paraula": 2}, {"so": "rugit", "paraula": 1}]}
        estat, cos = self.peticio("POST", "/api/estat", nou, self.bones())
        self.assertEqual(estat, 200)
        r = json.loads(cos)
        self.assertEqual(r["estat"]["sons"], [{"id": "s1", "so": "pop", "paraula": 2}])
        efecte = next(e for e in r["efectes"] if e["clau"] == "so:s1")
        self.assertAlmostEqual(efecte["t"], 1.0, delta=0.1)  # la paraula 2 comença a 1 s
        self.assertTrue(r["pista_efectes"])
        # També amb els efectes apagats al kit («cap»): l'has posat tu.
        marca.desa("so", {"efectes": "cap"}, kit=Projecte(self.carpeta).kit())
        r = json.loads(self.peticio("GET", "/api/instantania")[1])
        self.assertEqual([e["clau"] for e in r["efectes"]], ["so:s1"])

    def test_un_b_roll_posat_des_de_la_pagina(self):
        import shutil
        import subprocess
        if not shutil.which("ffmpeg"):
            self.skipTest("cal ffmpeg")
        foto = self.carpeta / "foto.png"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", str(foto)],
                       check=True)
        bones = self.bones(**{"Content-Type": "application/octet-stream"})
        estat, cos = self.peticio("POST", "/api/broll/puja?paraula=3&nom=foto.png", foto.read_bytes(), bones)
        self.assertEqual(estat, 200, cos)
        r = json.loads(cos)
        nou = next(i for i in r["instruccions"] if i.get("pagina"))
        self.assertEqual((nou["tipus"], nou["ancora"], nou["estat"]), ("broll", 3, "acceptada"))
        self.assertTrue((self.carpeta / nou["fitxer"]).exists())
        self.assertEqual([b["id"] for b in r["brolls"]], [nou["id"]])
        # Un fitxer que no és un vídeo ni una imatge de debò: no en queda res.
        estat, _ = self.peticio("POST", "/api/broll/puja?paraula=4&nom=dolenta.png", b"no soc una imatge", bones)
        self.assertEqual(estat, 400)
        self.assertEqual(sum(1 for i in Projecte(self.carpeta).instruccions() if i.get("pagina")), 1)
        # Els de les instruccions de veu no s'esborren; els de la pàgina, sí (amb els seus fitxers).
        self.assertEqual(self.peticio("POST", "/api/broll/esborra", {"instruccio": "i1"}, self.bones())[0], 400)
        estat, cos = self.peticio("POST", "/api/broll/esborra", {"instruccio": nou["id"]}, self.bones())
        self.assertEqual(estat, 200)
        self.assertFalse(any(i.get("pagina") for i in json.loads(cos)["instruccions"]))
        self.assertFalse((self.carpeta / nou["fitxer"]).exists())

    def test_canviar_com_entra_un_video_horitzontal_refa_la_copia(self):
        import shutil
        import subprocess
        import time
        if not shutil.which("ffmpeg"):
            self.skipTest("cal ffmpeg")
        video = self.carpeta / "no-hi-es.mov"  # el del projecte: ara sí que hi és, i és horitzontal
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=1:r=25", "-f", "lavfi",
                        "-i", "sine=d=1", "-shortest", "-pix_fmt", "yuv420p", str(video)], check=True)
        dades = json.loads(self.peticio("GET", "/api/projecte")[1])
        estat, cos = self.peticio("POST", "/api/estat", {**dades["estat"], "encaix": "difumina"}, self.bones())
        self.assertEqual((estat, json.loads(cos)["estat"]["encaix"]), (200, "difumina"))  # i no s'encalla
        for _ in range(100):  # la còpia es fa en segon pla; la pàgina ho pregunta a les novetats
            n = json.loads(self.peticio("GET", "/api/novetats")[1])
            if not n["copia_fent"] and (self.carpeta / "proxy-difumina.mp4").exists():
                break
            time.sleep(0.1)
        self.assertEqual((n["copia"].split(":")[0], n["copia_error"]), ("proxy-difumina.mp4", None))
        self.assertEqual(self.peticio("GET", "/proxy.mp4")[0], 200)  # i és la que serveix

    def test_un_sticker_posat_des_del_tauler(self):
        import shutil
        import subprocess
        if not shutil.which("ffmpeg"):
            self.skipTest("cal ffmpeg")
        foto = self.carpeta / "cor.png"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", str(foto)],
                       check=True)
        bones = self.bones(**{"Content-Type": "application/octet-stream"})
        self.assertEqual(self.peticio("POST", "/api/broll/puja?paraula=3&tipus=sticker&nom=x.mp4", b"hola", bones)[0], 400)
        estat, cos = self.peticio("POST", "/api/broll/puja?paraula=3&tipus=sticker&nom=cor.png", foto.read_bytes(), bones)
        self.assertEqual(estat, 200, cos)
        r = json.loads(cos)
        nou = next(i for i in r["instruccions"] if i.get("pagina"))
        self.assertEqual((nou["tipus"], nou["ancora"], nou["estat"]), ("sticker", 3, "acceptada"))
        self.assertTrue((self.carpeta / nou["fitxer"]).exists())
        self.assertIn(nou["id"], [s["id"] for s in r["stickers"]])
        # Arrossegat a la targeta: es desa a l'estat i el sticker surt allà.
        estat, cos = self.peticio("POST", "/api/estat", {**r["estat"], "llocs_stickers": {nou["id"]: {"x": 0.2, "y": 0.75}}},
                                  self.bones())
        self.assertEqual(estat, 200, cos)
        st = next(s for s in json.loads(cos)["stickers"] if s["id"] == nou["id"])
        self.assertEqual((st["x"], st["y"]), (0.2, 0.75))
        # Treure'l del tauler l'esborra (amb el fitxer), com el b-roll posat des de la pàgina, i també on s'havia
        # arrossegat i el seu vot: un sticker nou amb el mateix id no n'ha d'heretar res.
        p = Projecte(self.carpeta)
        p.estat["vots"] = {f"sticker:{nou['id']}": {"vot": "potser", "nota": "més petit", "nom": "Sticker", "paraula": 3}}
        p.desa()
        estat, cos = self.peticio("POST", "/api/broll/esborra", {"instruccio": nou["id"]}, self.bones())
        self.assertEqual(estat, 200)
        r = json.loads(cos)
        self.assertFalse(any(i.get("pagina") for i in r["instruccions"]))
        self.assertFalse((self.carpeta / nou["fitxer"]).exists())
        self.assertEqual((r["estat"]["llocs_stickers"], r["estat"]["vots"]), ({}, {}))

    def test_treure_una_peca_nomes_esborra_fitxers_de_tallat(self):
        fora = Path(self.dir.name).parent / f"no-m-esborris-{self.port}.txt"
        fora.write_text("important", encoding="utf-8")
        self.addCleanup(fora.unlink, missing_ok=True)
        llista = json.loads((self.carpeta / "instruccions.json").read_text(encoding="utf-8"))
        llista.append({"id": "m1-9", "tipus": "sticker", "text": "sticker", "paraules": None, "inici": 0.5, "final": 0.5,
                       "ancora": 1, "estat": "acceptada", "manual": True, "pagina": True, "fitxer": f"../{fora.name}",
                       "original": str(fora)})
        (self.carpeta / "instruccions.json").write_text(json.dumps(llista), encoding="utf-8")
        estat, _ = self.peticio("POST", "/api/broll/esborra", {"instruccio": "m1-9"}, self.bones())
        self.assertEqual(estat, 200)
        self.assertTrue(fora.exists())  # fora de broll/ i stickers/: no es toca

    def test_els_fitxers_servits_no_poden_executar_scripts(self):
        # Segona revisió de Codex: un sticker SVG amb un script, obert directament, podia llegir el codi de la pàgina.
        (self.carpeta / "stickers").mkdir()
        (self.carpeta / "stickers" / "i1.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', encoding="utf-8")
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", "/stickers/i1.svg")
        r = c.getresponse()
        r.read()
        c.close()
        self.assertEqual(r.status, 200)
        self.assertIn("sandbox", r.getheader("Content-Security-Policy", ""))
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")

    def test_dues_pujades_amb_el_mateix_nom_no_es_barregen(self):
        sticker = {"id": "i2", "tipus": "sticker", "text": "un cor", "paraules": None, "inici": 1.0, "final": 1.0,
                   "ancora": 2, "estat": "acceptada", "manual": True}
        ins = json.loads((self.carpeta / "instruccions.json").read_text(encoding="utf-8"))
        (self.carpeta / "instruccions.json").write_text(json.dumps(ins + [sticker]), encoding="utf-8")
        bones = self.bones(**{"Content-Type": "application/octet-stream"})
        resultats = []

        def puja(contingut):
            resultats.append(self.peticio("POST", "/api/broll/puja?instruccio=i2&nom=image.png", contingut, bones)[0])
        fils = [threading.Thread(target=puja, args=(bytes([65 + k]) * 300_000,)) for k in range(4)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        self.assertEqual(resultats, [200] * 4)
        final = (self.carpeta / "stickers" / "i2.png").read_bytes()
        self.assertEqual(len(set(final)), 1)  # sencer d'una sola pujada, no barrejat
        self.assertEqual([f.name for f in (self.carpeta / "broll" / "pujats").iterdir()], [])

    def test_kits_triar_crear_exportar_i_importar(self):
        dades = json.loads(self.peticio("GET", "/api/projecte")[1])
        self.assertEqual((dades["kit"], [k["id"] for k in dades["kits"]]), ("el-meu-estil", ["el-meu-estil"]))
        # Un kit nou, còpia del d'ara, per a aquest vídeo; el panell d'estil hi desa.
        estat, cos = self.peticio("POST", "/api/kit/nou", {"nom": "Per a reels", "copia_de": "el-meu-estil"}, self.bones())
        self.assertEqual((estat, json.loads(cos)["kit"]), (200, "per-a-reels"))
        self.peticio("POST", "/api/marca", {"subtitols": {"color": "#123456"}}, self.bones())
        self.assertEqual(marca.carrega(kit="per-a-reels")["subtitols"]["color"], "#123456")
        self.assertEqual(marca.carrega(kit="el-meu-estil")["subtitols"]["color"], "#FFFFFF")  # l'altre no canvia
        # Es baixa en un .zip i es pot tornar a importar.
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", "/api/kit/exporta?kit=per-a-reels")
        r = c.getresponse()
        zip_ = r.read()
        c.close()
        self.assertIn("per-a-reels.tallat-kit.zip", r.getheader("Content-Disposition"))
        self.assertIn("kit.json", zipfile.ZipFile(io.BytesIO(zip_)).namelist())
        estat, cos = self.peticio("POST", "/api/kit/importa?nom=kit.zip", zip_,
                                  self.bones(**{"Content-Type": "application/zip"}))
        importat = json.loads(cos)
        self.assertEqual(estat, 200)
        self.assertEqual(marca.carrega(kit=importat["kit"])["subtitols"]["color"], "#123456")
        # Triar-ne un altre, i errors.
        self.assertEqual(json.loads(self.peticio("POST", "/api/kit/tria", {"kit": "el-meu-estil"}, self.bones())[1])["kit"],
                         "el-meu-estil")
        self.assertEqual(self.peticio("POST", "/api/kit/tria", {"kit": "no-hi-es"}, self.bones())[0], 404)
        self.assertEqual(self.peticio("POST", "/api/kit/esborra", {"kit": "el-meu-estil"}, self.bones())[0], 400)
        self.assertEqual(self.peticio("POST", "/api/kit/importa?nom=x.zip", b"no soc un zip",
                                      self.bones(**{"Content-Type": "application/zip"}))[0], 400)


    def test_un_canvi_per_a_un_kit_que_ja_no_es_el_del_video_no_es_desa(self):
        # La pàgina ha tocat el so al kit d'abans i, abans de desar-ho, el vídeo ha canviat de kit.
        self.peticio("POST", "/api/kit/nou", {"nom": "B", "copia_de": "el-meu-estil"}, self.bones())
        estat, cos = self.peticio("POST", "/api/marca", {"so": {"neteja": False}, "kit": "el-meu-estil"}, self.bones())
        self.assertEqual(estat, 409)
        self.assertEqual(json.loads(cos)["kit"], "b")  # la resposta porta el kit d'ara
        self.assertTrue(marca.carrega(kit="b")["so"]["neteja"])
        self.assertTrue(marca.carrega(kit="el-meu-estil")["so"]["neteja"])
        self.assertEqual(self.peticio("POST", "/api/marca/restableix", {"seccio": "so", "kit": "el-meu-estil"},
                                      self.bones())[0], 409)
        # Amb el kit bo (o sense dir-ne cap, com abans), sí.
        self.assertEqual(self.peticio("POST", "/api/marca", {"so": {"neteja": False}, "kit": "b"}, self.bones())[0], 200)
        self.assertFalse(marca.carrega(kit="b")["so"]["neteja"])

if __name__ == "__main__":
    unittest.main()
