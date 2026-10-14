---
name: tallat
description: Editor de reels en català, per paraules. Fes-la servir quan algú vulgui editar un vídeo de cap parlant (talking head) amb tallat, treure'n el farciment, fer el primer muntatge d'una gravació llarga (proposar reels), revisar-lo a la pàgina de revisió o exportar-lo en vertical 9:16.
---

# tallat

Tot en català, amb paraules senzilles: la majoria de persones que el fan servir no són programadores.

## Instal·lació (la primera vegada)

Quan la persona digui «instal·la tallat», o una ordre falli perquè falta una eina (ffmpeg, WhisperX, Node…):
1. Explica-li en una frase què passarà: es baixen uns 2-3 GB (ffmpeg, Node, Python, WhisperX, el navegador de HyperFrames i el model de veu català), triga 10-20 minuts, tot va a la seva carpeta d'usuari (`~/.tallat` i `.venv`) i no demana mai la contrasenya.
2. Si no fa servir Descript per transcriure, afegeix `--amb-whisper` (baixa 3 GB més, el model de transcripció).
3. Executa `./prepara.sh` des de la carpeta de tallat. És llarg: fes-ho en una pestanya del terminal on la persona ho vegi, o en segon pla, i ves-li dient com va. Es pot tornar a executar sense por: només fa el que falta.
4. En acabar, `prepara.sh` mateix executa `tallat.py comprova`. Si hi ha cap ✗, llegeix el missatge, torna a executar `./prepara.sh` i, si continua, explica-li què passa amb paraules senzilles.

`tallat.py comprova` revisa en qualsevol moment que tot hi sigui (✓ bé, ! avís, ✗ cal arreglar). Descript és opcional: es connecta a Claude des de la configuració de connectors de claude.ai.

## Ordres

Des de la carpeta de tallat, amb l'entorn `.venv`:

```bash
.venv/bin/python tallat.py transcriu VIDEO --projecte CARPETA [--srt FITXER.srt]
.venv/bin/python tallat.py revisa --projecte CARPETA
.venv/bin/python tallat.py guio --projecte CARPETA
.venv/bin/python tallat.py reels --projecte CARPETA
.venv/bin/python tallat.py reel ID --projecte CARPETA
.venv/bin/python tallat.py exporta --projecte CARPETA [--qualitat esborrany|1080|4k] [--sense-subtitols]
.venv/bin/python tallat.py editors --projecte CARPETA [--amb-subtitols] [--trossos]
.venv/bin/python tallat.py gust [afegeix SECCIO "TEXT" [--ajust clau=valor] | treu NUMERO]
```

La carpeta del projecte ha de ser **fora del repositori** (els vídeos i el que diu la persona no es publiquen mai).

## Transcriure

- **Amb Descript** (millor text, conserva el farciment): importa l'àudio al compte de la persona amb el connector de Descript (projecte privat, idioma `ca`), exporta la transcripció en SRT, desa-la a la carpeta del projecte i executa `transcriu --srt`. WhisperX només hi calcula el temps de cada paraula.
- **Sense Descript**: `transcriu` sense `--srt` fa servir WhisperX sencer. És més lent i esborra part del farciment; avisa-ho.

## Primer muntatge (proposar reels d'una gravació llarga)

1. Executa `guio` i llegeix `guio.txt`. Cada línia és un paràgraf: `[P número · inici–final · paraules primera–última] text`.
2. Si cal triar paraules soltes, consulta els ids a `transcripcio.json` (`paraules[i].id`, `text`).
3. Escriu `reels.json` a la carpeta del projecte:

```json
{
  "reels": [
    {
      "id": "nom-curt",
      "titol": "Títol en català",
      "ganxo": "La frase exacta amb què comença",
      "per_que": "Una o dues frases: per què funciona sol i quines preses has triat",
      "paraules": [[0, 9], [446, 461], [463, 481]]
    }
  ]
}
```

   - `paraules` són trossos d'ids **inclosos els extrems**, **en l'ordre en què han de sonar**. Pots canviar l'ordre de la gravació si el reel ho demana.
4. Executa `reels` per validar-ho i veure'n la durada. Corregeix els errors que surtin.
   - A la pàgina de revisió, la persona també pot canviar l'ordre dels paràgrafs arrossegant-los per la nansa ⠿ (es desa a `edicio.json` → `ordre`, igual que el d'un reel).
5. La persona els veu a la pàgina de revisió («Reels proposats») i en tria un, que s'obre ja muntat. També es pot crear amb `reel ID`.

### Criteris per triar

- **S'aguanta sol**: s'entén sense haver vist res més. Si un reel necessita context, posa-hi la frase que l'explica o descarta'l.
- **Ganxo als primers 3 segons**: una pregunta, una afirmació sorprenent o una escena concreta. Si la persona ja ha gravat un ganxo, fes-lo servir.
- **Tanca bé**: acaba amb una frase de tancament (un remat, un consell, una conclusió), no a mitja idea.
- **La millor presa**: quan una frase es repeteix, tria la presa més neta: sense paraules a mig dir, fluida i, en cas de dubte, l'última completa. No n'ajuntis dues de la mateixa frase.
- **Ni una paraula inventada**: només es pot fer servir el que s'ha dit; no reescriguis el text.
- **Durada**: normalment entre 15 i 60 segons. Si una gravació dona per a un reel llarg i un de curt, proposa'ls tots dos.
- **Entre 1 i 5 reels** per gravació. Millor pocs i bons.
- Deixa el farciment («eh», «mmm») dins dels trossos: la neteja automàtica ja el treu i la persona el pot recuperar.

## Instruccions de veu («Claude, …»)

- `transcriu` les detecta sola; `instruccions` les torna a detectar en un projecte que ja existeix.
- Només compten si «Claude» obre una frase (després d'un punt o d'una pausa). El transcriptor de vegades escriu «Clot», «Cloud» o «Clau»: també compten.
- Les paraules de la instrucció es treuen del vídeo (motiu «instruccio») i queden a `instruccions.json` per decidir a la pàgina:
  - **talla** («torno a començar», «talla des d'aquí»): la presa bona comença aquí. Si en acceptar-la es troba el primer intent de la frase que ve després, es treu.
  - **zoom**: s'apropa el tros que comença just després de la instrucció.
  - **broll**, **sticker**, **altre**: queden apuntades per a les fases següents.
- En proposar reels, no hi incloguis les paraules de les instruccions ni marques com «Continuo» que només serveixen per a la gravació.

## B-roll i stickers

tallat no depèn de cap IA: només necessita un fitxer per a cada instrucció acceptada.

- **Fitxers propis**: a la pàgina de revisió, cada instrucció de b-roll o de sticker acceptada té «Puja un fitxer…» (o s'hi pot arrossegar) i, si n'hi ha, un desplegable amb la biblioteca (`~/.tallat/broll/`, `~/.tallat/stickers/`). Els stickers de la biblioteca s'assignen sols si el nom del fitxer surt a la instrucció («sticker d'un cor» → `cor.png`).
- **Generats amb IA (opcional)**: si la persona té connectada a Claude una IA d'imatge o vídeo (Krea, Higgsfield, OpenArt, Adobe Firefly…), ofereix-li generar-los. Abans de generar, digues-li quin model faràs servir i que gastarà crèdits del seu compte, i espera que ho confirmi.
  - B-roll: vídeo vertical 9:16, el més curt que permeti el model (tallat n'agafa 1-1,5 s); o una imatge (tallat hi fa un zoom lent). Escriu la descripció en anglès, concreta i visual, sense text ni cares de persones reals.
  - Stickers: imatge PNG amb el fons transparent (si la IA no en sap fer, treu-ne el fons amb una altra eina o demana-li a la persona).
  - Baixa el fitxer a la carpeta del projecte i registra'l: `tallat.py broll ID FITXER` o `tallat.py sticker ID FITXER`.
- Per afegir-ne en un moment sense instrucció de veu: `tallat.py afegeix broll|sticker|zoom --paraula ID --text "…"`.
- **No generis cares de persones reals** (famosos, coneguts): proposa un pla que evoqui la referència o demana imatges pròpies.

## Estil dels subtítols

- Es tria a la pàgina de revisió: **Subtítols → Estil**. Hi ha 13 estils predefinits (Clàssic, Net, Una paraula, Frase, Caixa, Karaoke, Impacte, Elegant, Cortina, Revista, Neó, Degradat, Emojis) i es pot ajustar tot: quantes paraules surten, si apareixen d'una en una o totes de cop, l'animació (pop, fos, impacte, cortina, gruix o cap), com es destaca la paraula que sona (color, caixa, karaoke o més gran), l'aspecte (normal, neó o degradat), una píndola de fons, les paraules clau més grans o amb emoji, la lletra (o una font pròpia), la mida, la posició i els colors.
- La vista prèvia i el vídeo final fan servir el mateix codi d'animació (`pagina/subtitols.js`): el que es veu a la pàgina és el que surt.
- Es desa a `~/.tallat/brand.json` (secció `subtitols`) i serveix per a tots els vídeos de la persona. Si et demana un canvi al xat, edita aquest fitxer: cada opció hi té una nota que l'explica. Els estils predefinits són a `config/estils_subtitols.json`; els emojis, a `config/emojis.json` (la persona en pot afegir a `~/.tallat/emojis.json`).

## Acabar-lo en un altre editor

Si la persona vol retocar el vídeo a Premiere, Final Cut, DaVinci Resolve o CapCut: `tallat.py editors` (o, a la pàgina, Final… → «Prepara el projecte»). Escriu a `exports/` una carpeta amb el projecte (`.fcpxml` per a Final Cut i DaVinci, `.xml` per a Premiere), els subtítols en `.srt`, el b-roll i els stickers a `recursos/`, i un `LLEGEIX-ME.txt` amb els passos de cada editor. CapCut i iMovie no importen projectes: per a ells, `tallat.py editors --trossos` (a la pàgina, «Trossos per a CapCut o iMovie») treu cada tros com un clip numerat (01.mp4, 02.mp4…) amb el zoom aplicat, el b-roll i els stickers amb el moment al nom, i el `.srt`; arrossegats tots alhora a la línia de temps queden en ordre (es poden escurçar, no allargar). Amb `--amb-subtitols` hi afegeix els subtítols animats de tallat com a capa transparent (tarda uns minuts). Els talls apunten al vídeo original: que no el mogui.

## El teu gust (regles per als vídeos següents)

- **Abans de decidir res** (neteja, primer muntatge i reels, instruccions, b-roll i stickers, estil), llegeix les regles amb `tallat.py gust` i segueix-les. Les que porten un ajust ja s'apliquen soles.
- **Quan la persona reacciona a un resultat** («massa lent», «els subtítols són petits», «no em treguis els vale»):
  1. Busca el comportament que hi ha darrere, no només el cas concret: «aquest b-roll és massa llarg» vol dir «b-roll més curt», no «treu aquest b-roll».
  2. Pregunta-li (amb les opcions de resposta) si és **per a aquest vídeo** o **per sempre** (recomana «per sempre»). Si ja ho ha dit («sempre», «només aquí»), no ho preguntis.
  3. Si és per sempre, desa-ho: `tallat.py gust afegeix SECCIO "la regla en paraules de la persona" [--ajust clau=valor]`. Si és només per a aquest vídeo, fes-ho al projecte i prou.
- Seccions: `talls`, `subtitols`, `broll`, `stickers`, `reels`, `altres`.
- Ajustos (si n'hi ha un que encaixa, posa'l; si no, la regla només amb text):

| Diu | `--ajust` |
|---|---|
| talls massa lents / massa ràpids | `talls.pausa_maxima=0.25` (més ràpid) o `0.5` (més lent); per als projectes nous |
| no em treguis «X» / treu sempre «X» / només proposa «X» | `farciment.deixa=X` / `farciment.treu=X` / `farciment.proposa=X` |
| subtítols més grans / més petits | `subtitols.mida=0.09` (la mida actual és al fitxer d'estil; la normal, 0,075) |
| més / menys paraules a la pantalla | `subtitols.paraules_per_linia=1` (una), `3`, `7` (frase) |
| subtítols més amunt / més avall | `subtitols.posicio_y=0.6` (0 dalt, 1 baix) |
| color de la paraula destacada | `subtitols.color_actiu="#FF375F"` |
| b-roll més curt / més llarg | `broll.durada=1.0` |
| stickers més petits / més grans | `stickers.mida=0.25` |

- Per treure'n una: `tallat.py gust treu NUMERO` (l'opció torna a com estava). A la pàgina de revisió també es veuen, s'hi poden escriure i treure, i cada nota de l'esborrany té «Recorda-ho sempre».

## Regles

- No llegeixis ni copiïs cap carpeta de marca personal tret que la persona ho demani explícitament.
- No esborris ni moguis fitxers de la persona sense que t'ho confirmi.
- No es renderitza res en 4K fins que la persona ho aprova a la pàgina («Final…»).
