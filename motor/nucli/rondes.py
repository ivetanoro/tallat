"""Els vots de les rondes, els mateixos a tallat, personalitza i matcha (vegeu RONDES.md i pagina/rondes.js).

Es veuen com a Sí · Potser · No. Internament són "si", "potser" i "no"; cada eina els pot desar amb els noms
que ja tenia, i `vot()` els porta al comú.
"""
from __future__ import annotations

VOTS = ("si", "potser", "no")
ETIQUETES = {"si": "Sí", "potser": "Potser", "no": "No"}
INTERNS = {
    "comu": {"si": "si", "potser": "potser", "no": "no"},
    "tallat": {"si": "si", "potser": "potser", "no": "no"},
    "personalitza": {"si": "guarda", "potser": "potser", "no": "fora"},
    "matcha": {"si": "aprovada", "potser": "canvi", "no": "treta"},
}


def vot(valor) -> str | None:
    """El vot comú d'un valor de qualsevol eina («guarda» → «si», «treta» → «no»…), o None."""
    if valor in VOTS:
        return valor
    for mapa in INTERNS.values():
        for comu, intern in mapa.items():
            if intern == valor:
                return comu
    return None


def etiqueta(valor) -> str:
    """Com es diu a la pantalla (Sí, Potser, No), o «sense valorar»."""
    v = vot(valor)
    return ETIQUETES[v] if v else "sense valorar"
