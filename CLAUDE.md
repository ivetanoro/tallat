# tallat

Editor de reels en català que funciona dins de Claude Code. Codi obert amb llicència AGPL v3 (fitxer LICENSE).

## Regles del projecte
- Tota la interfície, els missatges i la documentació, en català.
- Marca neutra per defecte. Cap marca personal dins del codi: cada persona configura la seva (els seus kits d'estil a `~/.tallat/kits`, `brand.md`, `brand.json`), i aquests fitxers no es publiquen.
- Vídeos, àudios, transcripcions i exports mai dins del repositori.
- Codi escrit de zero. Es poden agafar idees d'altres projectes, però no codi.
- `motor/nucli/` és una còpia del repositori `nucli` (el codi que tallat comparteix amb altres eines: el format de l'estil, el farciment, el mapa de la veu i la peça de votar). No s'edita aquí: es canvia al `nucli` i es fa `python3 sincronitza.py`. El vot és sempre Sí · Potser · No, i l'estil es passa en un `.estil.zip` (format `estil/1`).
