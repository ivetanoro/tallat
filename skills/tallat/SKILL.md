---
name: tallat
description: Editor de reels en català, per paraules. Fes-la servir quan algú vulgui editar un vídeo de cap parlant (talking head) amb tallat, treure'n el farciment, fer el primer muntatge d'una gravació llarga (proposar reels), revisar-lo a la pàgina de revisió o exportar-lo en vertical 9:16.
---

# tallat

Tot en català, amb paraules senzilles: la majoria de persones que el fan servir no són programadores.

Aquestes instruccions serveixen per a qualsevol assistent que pugui fer servir el terminal (Claude Code, Codex…): on diu «l'assistent», ets tu.

## Instal·lació (la primera vegada)

Quan la persona digui «instal·la tallat», o una ordre falli perquè falta una eina (ffmpeg, WhisperX, Node…):
1. Explica-li en una frase què passarà: es baixen uns 2-3 GB (ffmpeg, Node, Python, WhisperX, el navegador de HyperFrames i el model de veu català), triga 10-20 minuts, tot va a la seva carpeta d'usuari (`~/.tallat`) i no demana mai la contrasenya.
2. Si no fa servir Descript per transcriure, afegeix `--amb-whisper` (baixa 3 GB més, el model de transcripció).
3. Executa `./prepara.sh` des de la carpeta de tallat. És llarg: fes-ho en una pestanya del terminal on la persona ho vegi, o en segon pla, i ves-li dient com va. Es pot tornar a executar sense por: només fa el que falta.
4. En acabar, `prepara.sh` mateix executa `tallat.py comprova`. Si hi ha cap ✗, llegeix el missatge, torna a executar `./prepara.sh` i, si continua, explica-li què passa amb paraules senzilles.

`tallat.py comprova` revisa en qualsevol moment que tot hi sigui (✓ bé, ! avís, ✗ cal arreglar). Descript és opcional: es connecta des de la configuració de connectors de l'assistent (a Claude, la de claude.ai).

## Ordres

Des de la carpeta de tallat: la que conté `tallat.py`, dues carpetes per sobre d'aquest `SKILL.md` (si s'ha instal·lat com a connector, és la carpeta del connector; a Claude Code, `${CLAUDE_PLUGIN_ROOT}`), amb l'entorn `.venv`. Si `.venv` no hi és (la primera vegada, o després d'actualitzar el connector), executa `./prepara.sh`: si ja està tot instal·lat, només refà l'enllaç i triga uns segons.

```bash
.venv/bin/python tallat.py transcriu VIDEO --projecte CARPETA [--srt FITXER.srt]
.venv/bin/python tallat.py revisa --projecte CARPETA
.venv/bin/python tallat.py guio --projecte CARPETA
.venv/bin/python tallat.py reels --projecte CARPETA
.venv/bin/python tallat.py reel ID --projecte CARPETA
.venv/bin/python tallat.py exporta --projecte CARPETA [--qualitat esborrany|1080|4k] [--sense-subtitols]
.venv/bin/python tallat.py editors --projecte CARPETA [--amb-subtitols] [--trossos]
.venv/bin/python tallat.py gust [afegeix SECCIO "TEXT" [--ajust clau=valor] | treu NUMERO]
.venv/bin/python tallat.py moment SEGONS --projecte CARPETA [--esborrany]
.venv/bin/python tallat.py kit [nou NOM [--copia-de ID] | nom ID NOM | per-defecte ID | tria ID --projecte CARPETA | exporta ID [--a CARPETA] | importa FITXER.zip | esborra ID | lletres | lletra ID [--kit KIT]]
.venv/bin/python tallat.py destaca --projecte CARPETA [--si ID…] [--no ID…] [--automatic]
.venv/bin/python tallat.py titol --projecte CARPETA ["LÍNIA | *DESTACAT* | LÍNIA"] [--durada S] [--treu]
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

## Instruccions de veu («Claude, …» o «tallat, …»)

- `transcriu` les detecta sola; `instruccions` les torna a detectar en un projecte que ja existeix.
- Només compten si la paraula obre una frase (després d'un punt o d'una pausa). El transcriptor de vegades escriu «Clot», «Cloud» o «Clau»: també compten.
- «tallat, …» i «Codex, …» també serveixen (no tothom fa servir Claude), però només si el que ve després és una ordre coneguda (torno a començar, zoom, b-roll, sticker): «un tallat amb llet» no és cap instrucció.
- La instrucció acaba al primer final de frase o en un silenci d'un segon. Si no se'n troba el final (més de 25 paraules), queda marcada com a `dubtosa` i no se'n treu res del vídeo: mira-la amb la persona.
- Les paraules de la instrucció es treuen del vídeo (motiu «instruccio») i queden a `instruccions.json` per decidir a la pàgina:
  - **talla** («torno a començar», «talla des d'aquí»): la presa bona comença aquí. Si en acceptar-la es troba el primer intent de la frase que ve després, es treu.
  - **zoom**: s'apropa el tros que comença just després de la instrucció.
  - **broll**, **sticker**, **altre**: queden apuntades per a les fases següents.
- En proposar reels, no hi incloguis les paraules de les instruccions ni marques com «Continuo» que només serveixen per a la gravació.

## B-roll i stickers

tallat no depèn de cap IA: només necessita un fitxer per a cada instrucció acceptada.

- **Fitxers propis**: a la pàgina de revisió, cada instrucció de b-roll o de sticker acceptada té «Puja un fitxer…» (o s'hi pot arrossegar) i, si n'hi ha, un desplegable amb la biblioteca (`~/.tallat/broll/`, `~/.tallat/stickers/`). Els stickers de la biblioteca s'assignen sols si el nom del fitxer surt a la instrucció («sticker d'un cor» → `cor.png`).
- **Generats amb IA (opcional)**: si la persona té connectada a l'assistent una IA d'imatge o vídeo (Krea, Higgsfield, OpenArt, Adobe Firefly…), ofereix-li generar-los. Abans de generar, digues-li quin model faràs servir i que gastarà crèdits del seu compte, i espera que ho confirmi.
  - B-roll: vídeo vertical 9:16, el més curt que permeti el model (tallat n'agafa 1-1,5 s); o una imatge (tallat hi fa un zoom lent). Escriu la descripció en anglès, concreta i visual, sense text ni cares de persones reals.
  - Stickers: imatge PNG amb el fons transparent (si la IA no en sap fer, treu-ne el fons amb una altra eina o demana-li a la persona).
  - Baixa el fitxer a la carpeta del projecte i registra'l: `tallat.py broll ID FITXER` o `tallat.py sticker ID FITXER`.
- Per afegir-ne en un moment sense instrucció de veu: `tallat.py afegeix broll|sticker|zoom --paraula ID --text "…"`.
- **No generis cares de persones reals** (famosos, coneguts): proposa un pla que evoqui la referència o demana imatges pròpies.

### Com surt el b-roll a la pantalla

- Es tria a la pàgina: pestanya **Estil** → **B-roll**. Maneres fetes (`config/estils_broll.json`): **Pantalla sencera** (tapa la imatge, tall sec, com sempre), **Targeta** (una targeta gran arrodonida; la persona es veu al voltant), **Finestra** (petita a la cantonada, amb vora del color del kit), **Foto** (vora blanca gruixuda i inclinada), **Pantalla partida** (el b-roll a la meitat de dalt i la persona a la de baix) i **Tres targetes** (els b-rolls seguits, a menys d'un segon l'un de l'altre, entren d'un en un en fins a tres targetes una al costat de l'altra i s'hi queden fins que s'acaba l'últim).
- Es desa al kit, secció `broll`: `disposicio` (`pantalla`, `targeta`, `partida`, `carrusel`), `mida` i `posicio_x`/`posicio_y` (de la targeta), `proporcio` (9:16, 3:4, 4:5, 1:1, 16:9), `radi` (cantonades), `vora` i `vora_color` (null: el color destacat dels subtítols), `ombra`, `rotacio` i `animacio` (pop, puja, llisca, fos o cap).
- On va cada targeta es calcula en un sol lloc (`motor/targetes.py`): la vista prèvia i el vídeo final són iguals. Al projecte per a Premiere o Final Cut, el b-roll en targeta hi va més petit, retallat i al seu lloc, però sense les cantonades arrodonides, la vora ni l'ombra.
- Si la persona fa servir **Tres targetes**, digues-li que funciona amb b-rolls seguits (un darrere l'altre); si només n'hi ha un de sol, surt una sola targeta al mig.

## Estil dels subtítols

- Es tria a la pàgina de revisió: pestanya **Estil** → **Subtítols** (la columna de l'esquerra té tres pestanyes: **Edita** —reels, instruccions de veu, propostes i silencis—, **Estil** —el kit, els subtítols, el títol i el b-roll— i **Vídeos** —els exportats). Hi ha 17 estils predefinits (Clàssic, Net, Una paraula, Frase, Caixa, Karaoke, Impacte, Elegant, Cortina, Revista, Neó, Degradat, Emojis, i els dissenyats: Apilat, Esglaó, Titular, Rètol) i es pot ajustar tot: quantes paraules surten, si apareixen d'una en una o totes de cop, l'animació (pop, fos, impacte, cortina, gruix o cap), com es destaca la paraula que sona (color, caixa, karaoke o més gran), l'aspecte (normal, neó o degradat), una píndola de fons, emojis, la lletra, la mida, la posició i els colors.
- **Disposició** (`disposicio`): `linia` (cada línia substitueix l'anterior) o `apilat` (les línies d'una frase s'apilen una sota l'altra fins que la frase acaba o n'hi ha `linies_max`). **Alineació** (`alineacio`): `centre`, `esquerra`, `dreta` o `esglao` (per torns a l'esquerra i a la dreta; les línies que només tenen paraules destacades, al mig, com un títol). `espaiat` (entre lletres; negatiu = juntes, com als títols de revista) i `interlineat` (entre línies).
- **Paraules destacades** (`clau_grans`): surten `clau_mida` vegades més grans i amb `clau_color` (null: el color del destacat); amb `clau_sola`, cada una va sola a la seva línia (amb `apilat` fa el look de títol: «és tan / AMBICIÓS / o / EMPRENEDOR»). tallat en tria soles (els números i la paraula llarga més important de cada línia). La persona les pot canviar al mode **Destaca** de la pàgina, i tu amb `tallat.py destaca --projecte X --si ID… --no ID…` (sense opcions, et diu quines surten ara, amb el seu número). Quan la persona vulgui subtítols dissenyats, revisa-les: una per idea, les que porten el pes del missatge (substantius, xifres, adjectius forts), mai paraules pont. La pàgina oberta es posa al dia sola en uns segons.
- **Lletres**: les del Mac, 18 de gratuïtes (Inter, Inter Tight, Archivo, Anton, Bebas Neue, Montserrat, Poppins, Fraunces, Playfair Display, Caveat…; `tallat.py kit lletres`) que es baixen dins del kit el primer cop que es trien (`tallat.py kit lletra ID`, o a la pàgina), i les que puja la persona. Totes les lletres que no són del Mac viuen a la carpeta `fonts/` del kit i viatgen amb ell.
- La vista prèvia i el vídeo final fan servir el mateix codi d'animació (`pagina/subtitols.js`): el que es veu a la pàgina és el que surt.
- Es desa al **kit d'estil** del vídeo (vegeu més avall), a la secció `subtitols`. Si la persona et demana un canvi al xat, edita el `kit.json` d'aquell kit: cada opció hi té una nota que l'explica. Els estils predefinits són a `config/estils_subtitols.json`; els emojis, a `config/emojis.json` (la persona en pot afegir a `~/.tallat/emojis.json`).

## Títol del ganxo

- Un text dissenyat que surt els primers segons del vídeo (com els rètols dels reels: «#3 canvis / *ser creadora* / nivell fàcil»). Cada línia és una línia; el que va `*entre asteriscs*` surt destacat (més gran i del color destacat). El text és de cada vídeo (a l'estat: es desfà amb ⌘Z); l'estil, del kit (secció `titol`): lletra (null: la dels subtítols), mida, `clau_mida`, colors, contorn, ombra, `alineacio` (també `esglao`: les línies a banda i banda i les només destacades, al mig), posició, `animacio` (puja, pop, fos, cortina, `maquina` —lletra a lletra amb cursor— o cap), `fons` (cap, `enfosquit` —el vídeo s'enfosqueix— o `pindola` —una caixa darrere cada línia), `durada` i `amaga_subtitols`. Estils fets: Esglaó, Rètol, Màquina, Revista i Caixa (`config/estils_titol.json`).
- A la pàgina: pestanya **Estil** → **Títol del ganxo** (el text, la durada i l'estil, en un sol panell). Al xat: `tallat.py titol`.
- Quan facis el primer muntatge o la persona demani un títol, proposa-n'hi un i ensenya-l'hi abans de posar-lo: 2-4 línies curtes, en la seva veu, amb una sola part destacada (la idea que fa quedar-se a mirar), sense paraules buides ni promeses que el vídeo no compleix. Si el títol repeteix el que es diu, recomana «sense subtítols mentre surt el títol».

## Kits d'estil

- Un kit és un estil amb nom: els subtítols (amb la lletra pròpia, si en té), el b-roll, els stickers i els talls. La persona en pot tenir uns quants («Reels ràpids», «Vídeos tranquils»…) i cada vídeo en fa servir un. Un reel fa servir el de la seva gravació, si no se n'hi tria un altre.
- Són a `~/.tallat/kits/<id>/kit.json`, amb les fonts a `fonts/`, fora del repositori. `~/.tallat/kits/kits.json` diu quin és el **per defecte**: el dels vídeos nous, i el que canvien les regles del gust. Els valors que falten a un kit es prenen de l'estil neutre (`config/brand.example.json`).
- La primera vegada, l'estil que la persona ja tenia (`~/.tallat/brand.json`) es converteix en el kit «El meu estil». brand.json no es toca, però ja no es fa servir.
- A la pàgina de revisió, pestanya **Estil** → **Kit d'estil** (les accions, al menú «…»): triar el kit del vídeo, duplicar-lo, fer-ne un de nou amb l'estil de tallat, canviar-li el nom, fer-lo per defecte, exportar-lo (un `.zip` per passar-lo a algú) i importar-ne. Al xat: `tallat.py kit` i les seves ordres. L'id d'un kit (el nom de la carpeta) no canvia encara que se li canviï el nom.
- Quan la persona vulgui un estil «per a un tipus de vídeo» o «per passar-lo a algú», proposa-li un kit. Si un kit porta una font pròpia i el vol passar a algú, recorda-li que comprovi que la font es pot compartir.
- «Treure» un kit no l'esborra: va a `~/.tallat/kits-esborrats/`. El kit per defecte no es pot treure.

## Acabar-lo en un altre editor

Si la persona vol retocar el vídeo a Premiere, Final Cut, DaVinci Resolve o CapCut: `tallat.py editors` (o, a la pàgina, Final… → «Projecte per a Premiere, Final Cut o DaVinci»). Escriu a `exports/` una carpeta amb el projecte (`.fcpxml` per a Final Cut i DaVinci, `.xml` per a Premiere), els subtítols en `.srt`, el b-roll i els stickers a `recursos/`, i un `LLEGEIX-ME.txt` amb els passos de cada editor. CapCut i iMovie no importen projectes: per a ells, `tallat.py editors --trossos` (a la pàgina, «Trossos per a CapCut o iMovie») treu cada tros com un clip numerat (01.mp4, 02.mp4…) amb el zoom aplicat, el b-roll i els stickers amb el moment al nom, i el `.srt`; arrossegats tots alhora a la línia de temps queden en ordre (es poden escurçar, no allargar). Amb `--amb-subtitols` hi afegeix els subtítols animats de tallat com a capa transparent (tarda uns minuts). Els talls apunten al vídeo original: que no el mogui.

## El teu gust (regles per als vídeos següents)

- **Abans de decidir res** (neteja, primer muntatge i reels, instruccions, b-roll i stickers, estil), llegeix les regles amb `tallat.py gust` i segueix-les. Les que porten un ajust ja s'apliquen soles.
- **Quan la persona reacciona a un resultat** («massa lent», «els subtítols són petits», «no em treguis els vale»):
  1. Busca el comportament que hi ha darrere, no només el cas concret: «aquest b-roll és massa llarg» vol dir «b-roll més curt», no «treu aquest b-roll».
  2. Pregunta-li (amb opcions de resposta si en pots fer; si no, amb una pregunta curta) si és **per a aquest vídeo** o **per sempre** (recomana «per sempre»). Si ja ho ha dit («sempre», «només aquí»), no ho preguntis.
  3. Si és per sempre, desa-ho: `tallat.py gust afegeix SECCIO "la regla en paraules de la persona" [--ajust clau=valor]`. Si és només per a aquest vídeo, fes-ho al projecte i prou.
- Seccions: `talls`, `subtitols`, `broll`, `stickers`, `reels`, `altres`.
- Els ajustos d'estil es fan al **kit per defecte**. Si el vídeo fa servir un altre kit i la persona vol el canvi també allà, fes-lo al seu `kit.json` (o a la pàgina, amb aquell kit triat).
- Ajustos (si n'hi ha un que encaixa, posa'l; si no, la regla només amb text):

| Diu | `--ajust` |
|---|---|
| talls massa lents / massa ràpids | `talls.pausa_maxima=0.25` (més ràpid) o `0.5` (més lent); per als projectes nous |
| no em treguis «X» / treu sempre «X» / només proposa «X» | `farciment.deixa=X` / `farciment.treu=X` / `farciment.proposa=X` |
| subtítols més grans / més petits | `subtitols.mida=0.09` (la mida actual és al kit; la normal, 0,075) |
| més / menys paraules a la pantalla | `subtitols.paraules_per_linia=1` (una), `3`, `7` (frase) |
| subtítols més amunt / més avall | `subtitols.posicio_y=0.6` (0 dalt, 1 baix) |
| color de la paraula destacada | `subtitols.color_actiu="#FF375F"` |
| b-roll més curt / més llarg | `broll.durada=1.0` |
| el b-roll en targeta / a pantalla sencera | `broll.disposicio="targeta"` / `"pantalla"` |
| stickers més petits / més grans | `stickers.mida=0.25` |

- Per treure'n una: `tallat.py gust treu NUMERO` (l'opció torna a com estava). Les regles només es porten al xat (a la pàgina no hi són): si la persona pregunta quines té, ensenya-les-hi en paraules senzilles.

## Revisar l'esborrany

- La pàgina no té notes: la persona mira l'esborrany (o el muntatge En directe) i et diu al xat què vol canviar, amb el segon que veu sota el vídeo («al segon 12, el b-roll és massa llarg»).
- Per saber què hi ha en aquell moment, `tallat.py moment SEGONS --projecte X` (amb `--esborrany` si parla de l'esborrany: si ha canviat coses després, els temps no coincideixen amb el muntatge d'ara). Et diu el segon de la gravació, les paraules del voltant amb el seu número (» la que sona, [entre claudàtors] les tretes) i si hi surt el títol, un b-roll o un sticker. Si no està clar de quina vista parla, pregunta-l'hi.
- Fes el canvi i explica-li què has fet. Si la correcció sembla «per sempre» (el b-roll sempre és massa llarg), segueix el que diu «El teu gust».

## Regles

- No llegeixis ni copiïs cap carpeta de marca personal tret que la persona ho demani explícitament.
- No esborris ni moguis fitxers de la persona sense que t'ho confirmi.
- No es renderitza res en 4K fins que la persona ho aprova a la pàgina («Final…»).
