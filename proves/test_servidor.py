import http.client
import json
import re
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from motor import servidor
from motor.projecte import Projecte


def port_lliure() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestServidor(unittest.TestCase):
    """Un servidor de veritat sobre un projecte petit (sense vídeo)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
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
        self.dir.cleanup()

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

    def test_nomes_amb_el_nom_d_aquest_mac(self):
        self.assertEqual(self.peticio("GET", "/api/projecte", host="dolenta.example")[0], 403)

    def test_peticions_d_altres_webs_rebutjades(self):
        nota = {"afegeix": {"id": 1, "versio": "v", "temps": 1, "text": "hola"}}
        self.assertEqual(self.peticio("POST", "/api/notes", nota, {"Content-Type": "application/json"})[0], 403)
        self.assertEqual(self.peticio("POST", "/api/notes", nota, self.bones(Origin="http://dolenta.example"))[0], 403)
        self.assertEqual(self.peticio("POST", "/api/notes", nota, self.bones(**{"Content-Type": "text/plain"}))[0], 415)
        self.assertEqual(json.loads(self.peticio("GET", "/api/projecte")[1])["notes"], [])

    def test_una_altra_pestanya_amb_un_altre_projecte(self):
        nota = {"afegeix": {"id": 1, "versio": "v", "temps": 1, "text": "hola"}}
        estat, cos = self.peticio("POST", "/api/notes", nota, self.bones(**{"X-Tallat-Projecte": "un-altre"}))
        self.assertEqual((estat, json.loads(cos)["error"]), (409, "projecte-canviat"))

    def test_les_notes_de_dues_pestanyes_no_es_trepitgen(self):
        self.peticio("POST", "/api/notes", {"afegeix": {"id": 1, "versio": "v", "temps": 1, "text": "A"}}, self.bones())
        estat, cos = self.peticio("POST", "/api/notes", {"afegeix": {"id": 2, "versio": "v", "temps": 2, "text": "B"}},
                                  self.bones())
        self.assertEqual([n["text"] for n in json.loads(cos)["notes"]], ["A", "B"])
        estat, cos = self.peticio("POST", "/api/notes", {"esborra": 1}, self.bones())
        self.assertEqual([n["text"] for n in json.loads(cos)["notes"]], ["B"])

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


if __name__ == "__main__":
    unittest.main()
