import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PREPARA = Path(__file__).resolve().parent.parent / "prepara.sh"

# Un uv de mentida, que es comporta com el de debò en el que importa aquí: no fa cap entorn en una
# carpeta que no sigui buida i no sigui ja un entorn.
UV_FALS = """#!/bin/sh
for desti; do :; done
if [ -d "$desti" ] && [ -n "$(ls -A "$desti")" ] && [ ! -f "$desti/pyvenv.cfg" ]; then
  echo "error: no és un entorn i no és buida: $desti" >&2
  exit 2
fi
mkdir -p "$desti/bin" && touch "$desti/pyvenv.cfg" && ln -sf "{python}" "$desti/bin/python"
"""


@unittest.skipIf(sys.platform == "win32", "prova prepara.sh, l'instal·lador del Mac (a Windows és prepara.ps1)")
class TestEntornPython(unittest.TestCase):
    def executa(self, tallat: Path, carpeta: Path) -> subprocess.CompletedProcess:
        """Només el pas de l'entorn de Python de prepara.sh, amb el uv de mentida."""
        linies = PREPARA.read_text(encoding="utf-8").splitlines()
        inici = next(i for i, l in enumerate(linies) if l.startswith('VENV="$TALLAT/venv"'))
        final = next(i for i, l in enumerate(linies) if l.startswith('fet "$("$PY" --version)'))
        guio = "\n".join(['set -u', 'falla() { echo "FALLA: $1" >&2; exit 1; }', 'fet() { echo "fet: $1"; }',
                          *linies[inici:final + 1]])
        entorn = {**os.environ, "TALLAT": str(tallat), "BIN": str(tallat / "bin"), "CARPETA": str(carpeta),
                  "PY": str(carpeta / ".venv" / "bin" / "python")}
        return subprocess.run(["bash", "-c", guio], env=entorn, capture_output=True, text=True, encoding="utf-8", timeout=60)

    def test_un_entorn_a_mitges_no_bloqueja_els_reintents(self):
        # Revisió de Codex: una instal·lació interrompuda deixava ~/.tallat/venv a mitges i uv ja no en
        # volia fer cap de nou: tornar a instal·lar fallava sempre.
        with tempfile.TemporaryDirectory() as d:
            tallat, carpeta = Path(d) / "tallat-casa", Path(d) / "repo"
            (tallat / "bin").mkdir(parents=True)
            carpeta.mkdir()
            uv = tallat / "bin" / "uv"
            uv.write_text(UV_FALS.replace("{python}", sys.executable), encoding="utf-8")
            uv.chmod(0o755)
            (tallat / "venv" / "lib").mkdir(parents=True)  # a mitges: hi ha coses, però cap Python
            (tallat / "venv" / "lib" / "res.txt").write_text("x", encoding="utf-8")
            r = self.executa(tallat, carpeta)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((tallat / "venv" / "pyvenv.cfg").exists())
            self.assertFalse((tallat / "venv.vell").exists())
            self.assertEqual(os.readlink(carpeta / ".venv"), str(tallat / "venv"))
            # I una segona vegada, amb l'entorn ja bo, no el toca.
            r = self.executa(tallat, carpeta)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
