# tallat

**Edites el reel en el que dura un tallat.**

tallat és un editor de reels en català que funciona dins de [Claude](https://claude.com/download) o de [Codex](https://openai.com/codex) (el de ChatGPT). Et graves parlant a càmera, li dius «edita aquest vídeo» i el retalles com si retallessis un text: les paraules que treus desapareixen del vídeo. Després hi poses subtítols animats, b-roll i stickers, i l'exportes en vertical, a punt per a Instagram, TikTok o YouTube Shorts.

És gratuït, de codi obert i tot passa al teu ordinador.

## Què fa

- **Edites el vídeo tocant les paraules.** tallat transcriu el que dius en català i et mostra el text en una pàgina del teu ordinador. Un clic dret en una paraula la treu del vídeo; un altre la recupera.
- **Neteja sola.** Treu els «eh» i els «mmm», et proposa els «vale» i els «o sigui» perquè decideixis tu, i escurça els silencis llargs.
- **Instruccions de veu mentre graves.** «Claude, torno a començar», «tallat, zoom aquí», «Claude, aquí un b-roll d'un vinil girant», «tallat, sticker d'un cor». tallat les troba a la gravació, les treu del vídeo i les aplica.
- **Primer muntatge.** D'una gravació llarga, Claude et proposa entre un i cinc reels, cadascun amb el seu ganxo i el seu final.
- **Subtítols animats i dissenyats.** Disset estils per començar (Clàssic, Karaoke, Neó, Apilat, Esglaó, Rètol…): línies que s'apilen, paraules destacades enormes i d'un altre color (les tries tu o les tria tallat), alineacions de títol, 18 lletres gratuïtes o la teva, i els teus colors. El que veus a la pàgina és el que surt al vídeo.
- **B-roll i stickers.** Fitxers teus, o generats amb la intel·ligència artificial d'imatge o vídeo que tinguis connectada a Claude. El b-roll pot tapar tota la pantalla o sortir en una targeta arrodonida, en una finestra petita, com una foto, amb la pantalla partida o en tres targetes seguides.
- **Canvies l'ordre** dels paràgrafs arrossegant-los.
- **Títol del ganxo.** Un text dissenyat per als primers segons («#3 canvis / **ser creadora** / nivell fàcil»), que pots escriure tu o et proposa Claude, amb el seu estil: en esglaó, com un rètol, a màquina d'escriure amb el fons enfosquit…
- **La teva marca.** La primera vegada, Claude et fa unes preguntes (de què va el teu compte, un reel que t'agradaria haver fet, els teus colors i lletres…) i amb les respostes deixa els subtítols, el títol i el b-roll amb el teu estil. Després la pots retocar a la pàgina.
- **Kits d'estil.** Desa el teu estil (lletra, colors, animacions, durada del b-roll…) amb un nom, fes-ne uns quants per a tipus de vídeo diferents, tria'n un per a cada vídeo i passa'l a qui vulguis en un `.zip`.
- **Recorda el teu gust.** Si dius a Claude «els subtítols, més grans» o «no em treguis mai els *vale*», et pregunta si és per sempre i ho aplica a tots els vídeos següents. Per veure les teves regles, pregunta-li «quines regles tinc?».
- **Exporta** un esborrany ràpid, la versió final en 1080 o 4K vertical, o un projecte per acabar-lo a Premiere, Final Cut, DaVinci Resolve o CapCut.

## Què necessites

- **Un Mac.** De moment tallat només funciona en Mac. S'ha provat en un Mac amb processador Intel; en els Mac nous (M1, M2, M3…) hauria de funcionar igual, però encara no s'hi ha provat.
- **L'app de Claude**, amb un pla que inclogui Claude Code (la pestanya **Code**; el més barat és el Pro). **O bé Codex**, d'OpenAI, amb un pla de ChatGPT que l'inclogui.
- **Uns 5 GB lliures** per a la instal·lació, i espai per als teus vídeos.
- **Opcional:** [Descript](https://www.descript.com) connectat a Claude. Transcriu millor i conserva el farciment perquè el puguis treure tu. Sense Descript, tallat transcriu al teu ordinador amb WhisperX (més lent).
- **Opcional:** una intel·ligència artificial d'imatge o vídeo connectada a Claude (Krea, Higgsfield, OpenArt, Adobe Firefly…), si vols que et generi el b-roll. Abans de gastar-ne crèdits, Claude sempre t'ho pregunta.

## Instal·lació (sense terminal)

### Opció 1: com a connector de Claude

A l'app de Claude, a la pestanya **Code**, escriu al xat aquestes dues línies (d'una en una):

```
/plugin marketplace add ivetanoro/tallat
/plugin install tallat@tallat
```

Després escriu **«instal·la tallat»**.

### Opció 2: baixant la carpeta

1. En aquesta pàgina de GitHub, clica el botó verd **Code** i després **Download ZIP**. Fes doble clic al fitxer per descomprimir-lo.
2. A l'app de Claude, ves a la pestanya **Code** i obre la carpeta `tallat` que acabes de descomprimir. La primera vegada et pregunta si confies en aquesta carpeta: digues que sí.
3. Escriu **«instal·la tallat»**.

### Amb Codex (ChatGPT)

1. Baixa la carpeta com a l'opció 2 (botó **Code** → **Download ZIP**) i descomprimeix-la.
2. Obre la carpeta `tallat` amb Codex.
3. Escriu **«instal·la tallat»**.

Tot funciona igual que amb Claude. Només canvien els connectors opcionals (Descript i les IA per al b-roll): depèn de si aquests serveis en tenen per a Codex.

### Què fa la instal·lació

Claude baixa i prepara tot el que tallat necessita: ffmpeg (per treballar el vídeo), Python i WhisperX (per transcriure), el model de veu català de Softcatalà, i HyperFrames (per dibuixar els subtítols). Són uns 2-3 GB i 10-20 minuts la primera vegada. Tot va a una carpeta teva, `~/.tallat`, i no et demana mai la contrasenya del Mac. Tu només has de clicar **«Permet»** quan Claude et demani permís per fer alguna cosa.

## Com es fa servir

1. Digues a Claude **«edita aquest vídeo»** i arrossega-hi el vídeo (o escriu on és). Claude el transcriu i t'obre la pàgina de revisió al navegador.
2. Retalla'l a la pàgina:

   | Per… | Fes… |
   |---|---|
   | escoltar des d'una paraula | clic a la paraula |
   | treure o recuperar una paraula | clic dret (o control + clic) |
   | treure'n unes quantes de cop | arrossega amb el clic dret per sobre |
   | destacar una paraula als subtítols (o deixar de destacar-la) | mode **Destaca**, a dalt, i clic a la paraula |
   | canviar l'ordre d'un paràgraf | arrossega'l per la nansa ⠿ de l'esquerra |
   | desfer / refer | ⌘Z / ⇧⌘Z |
   | reproduir o aturar | espai |
   | amagar la columna de l'esquerra o la del vídeo | ⌃⌘S / ⌥⌘V |

3. A dalt de la columna de l'esquerra tria el kit; a les pestanyes **Subtítols**, **Gràfics** (el títol del ganxo i el b-roll) i **So** (la neteja de la veu i els efectes de so), com vols que quedi.
4. Clica **Esborrany** (a dalt) i mira'l. El que vulguis canviar, digues-ho a Claude amb el segon, que veus sota el vídeo: «al segon 12, el b-roll és massa llarg». Els vídeos que exportes, a la pestanya **Vídeos**.
5. Quan t'agradi, **Final…** → 4K o 1080. O, si el vols acabar en un altre editor, **Projecte per a Premiere, Final Cut o DaVinci** o **Trossos per a CapCut o iMovie**.

En qualsevol moment pots demanar canvis a Claude amb paraules: «treu la primera frase», «fes-me tres reels d'aquesta gravació», «posa-hi un sticker d'una estrella quan dic *genial*».

## Instruccions de veu

Mentre graves, comença la frase amb «Claude» (o amb «tallat», si fas servir Codex o un altre assistent) i digues què vols:

| Dius | Què passa |
|---|---|
| «Claude, torno a començar» o «tallat, torno a començar» | La presa bona comença aquí: es treu l'intent d'abans. |
| «Claude, zoom aquí» | El tros que ve s'apropa una mica. |
| «Claude, aquí un b-roll d'un vinil girant» | Queda apuntat a la pàgina perquè hi posis (o generis) aquella imatge. |
| «Claude, sticker d'un cor» | Igual, amb un sticker. |

Les instruccions es treuen soles del vídeo, i a la pàgina decideixes si les acceptes. Amb «tallat» només compten les ordres d'aquesta taula: si dius «un tallat amb llet», no passa res.

## On es guarda cada cosa

- **Els teus vídeos i projectes**, on tu diguis, mai dins de la carpeta de tallat.
- **`~/.tallat/`**, la teva configuració: els teus kits d'estil, amb les seves lletres (`kits/`), les regles del teu gust (`gust.json`), la llista de farciment (`farciment.txt`), les biblioteques de b-roll i stickers (`broll/`, `stickers/`) i les eines que s'han instal·lat.

## Privacitat

- Tot es fa al teu ordinador. La pàgina de revisió només es pot obrir des del teu Mac.
- Si fas servir Descript, l'àudio es puja al teu compte de Descript per transcriure'l.
- Si generes b-roll amb intel·ligència artificial, la descripció de la imatge va a aquell servei i gasta crèdits del teu compte.

## Si alguna cosa falla

- Digues a Claude **«comprova tallat»**. Revisa cada peça i et diu què falta.
- Pots tornar a demanar **«instal·la tallat»** tantes vegades com vulguis: no toca res teu (vídeos, projectes ni configuració), només fa el que falta o el que ha quedat a mitges.

## Per a qui vulgui tocar el codi

- `motor/`: el programa (Python): transcripció, talls, subtítols, export.
- `pagina/`: la pàgina de revisió (HTML, CSS i JavaScript, sense dependències).
- `skills/tallat/SKILL.md`: les instruccions que segueix Claude.
- `config/`: els valors per defecte, neutres (estil, estils de subtítols, farciment, emojis).
- `proves/`: les proves (`.venv/bin/python -m unittest discover -s proves -t .`).
- `prepara.sh`: l'instal·lador. `tallat.py comprova`: la revisió de l'equip.

Les regles del projecte són a [CLAUDE.md](CLAUDE.md): tot en català, marca neutra per defecte, cap vídeo dins del repositori i codi escrit de zero.

## Llicència i agraïments

tallat és de codi obert. Copyright © 2026 Ivet Anoro, amb llicència [GNU AGPL v3](LICENSE) (o qualsevol versió posterior). Vol dir:

- Tothom el pot fer servir, estudiar, modificar i compartir, també per guanyar diners amb els vídeos que en surtin.
- Qui en reparteixi una versió modificada, o l'ofereixi com a servei per internet, n'ha de publicar el codi amb aquesta mateixa llicència. Ningú no pot fer-ne una versió tancada.
- **Els vídeos que facis amb tallat són teus.** La llicència només afecta el codi de tallat.

Fa servir, sense incloure'ls (s'instal·len a part, cadascun amb la seva llicència):

- [WhisperX](https://github.com/m-bain/whisperX) (BSD-2) i el model [wav2vec2-large-xlsr-catala](https://huggingface.co/softcatala/wav2vec2-large-xlsr-catala) de Softcatalà (Apache 2.0), per saber quan es diu cada paraula; [Whisper large-v3](https://huggingface.co/Systran/faster-whisper-large-v3) (MIT) per transcriure sense Descript.
- [ffmpeg](https://ffmpeg.org) (de conda-forge) per treballar el vídeo.
- [HyperFrames](https://github.com/heygen-com/hyperframes) (Apache 2.0) i [GSAP](https://gsap.com) per dibuixar els subtítols i els stickers.
- [uv](https://github.com/astral-sh/uv) i [micromamba](https://github.com/mamba-org/mamba) per instal·lar-ho tot.

Algunes idees venen del catàleg d'estils de subtítols de HyperFrames i de l'editor [cooked.](https://github.com/nextwork-projects/ai-video-editor-cooked), sense copiar-ne codi.
