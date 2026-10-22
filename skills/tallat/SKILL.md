---
name: tallat
description: Editor de reels en català, per paraules. Fes-la servir quan algú vulgui editar un vídeo de cap parlant (talking head) amb tallat, treure'n el farciment, fer el primer muntatge d'una gravació llarga (proposar reels), revisar-lo a la pàgina de revisió o exportar-lo en vertical 9:16.
---

# tallat

Tot en català, amb paraules senzilles: la majoria de persones que el fan servir no són programadores.

Aquestes instruccions serveixen per a qualsevol assistent que pugui fer servir el terminal (Claude Code, Codex…): on diu «l'assistent», ets tu.

## Com parles amb la persona

La majoria no són programadores i volen que sigui fàcil. **Guia-la pas a pas:**
- **Missatges curts.** Com a molt 4-6 línies. Si tens més coses a dir, digues la més important i pregunta si vol la resta.
- **Un pas cada cop.** Digues què has fet, què ha de fer ella ara (una sola cosa) i què vindrà després.
- **Negretes** per al que ha de fer o mirar («Clica **Exporta**», «a **Com es veu**, toca **Gràfics**»), i **llistes** quan hi ha més d'una cosa. Res de paràgrafs llargs.
- **Res de tecnicismes:** ni ordres, ni noms de fitxers interns, ni codi, si no els demana. «He tallat els silencis llargs», no «he executat neteja amb pausa 0,35».
- **Quan triï,** dona-li 2-4 opcions concretes (amb botons si l'assistent en té) i recomana'n una.
- **Paraules:** a la persona, digues-ne **el teu estil** (els colors, les lletres i com són els seus vídeos), mai «marca» ni «kit»: la majoria no tenen una marca, tenen un estil. Si en té uns quants, «els teus estils».
- **En les feines llargues** (transcriure, exportar), avisa abans de quant trigarà i ves-li dient com va. Quan acabi, digues-li clarament que ha acabat i on és el resultat.

**On funciona:** a l'ordinador de la persona (un Mac o un Windows; a Windows, encara en proves), des de la pestanya Code de l'app de Claude o des de Codex. Si et trobes en un entorn que no és el seu ordinador (un contenidor al núvol, sense `~/.tallat` ni el seu `$HOME`, amb internet limitat, o el xat normal o Cowork), no improvisis l'edició pel teu compte: digues-li que obri tallat a la pestanya **Code** de l'app de Claude al seu Mac (o amb Codex) i que hi escrigui «instal·la tallat».

## Instal·lació (la primera vegada)

Quan la persona digui «instal·la tallat», o una ordre falli perquè falta una eina (ffmpeg, WhisperX, Node…):
1. Explica-li en una frase què passarà: es baixen uns 2-3 GB (ffmpeg, Node, Python, WhisperX, el navegador de HyperFrames i el model de veu català), triga 10-20 minuts, tot va a la seva carpeta d'usuari (`~/.tallat`) i no demana mai la contrasenya.
2. Si no fa servir Descript per transcriure, afegeix `--amb-whisper` (baixa 3 GB més, el model de transcripció).
3. Executa `./prepara.sh` des de la carpeta de tallat (a **Windows**: `powershell -ExecutionPolicy Bypass -File prepara.ps1`, i `-AmbWhisper` en lloc de `--amb-whisper`). És llarg: fes-ho en una pestanya del terminal on la persona ho vegi, o en segon pla, i ves-li dient com va. Es pot tornar a executar sense por: només fa el que falta.
4. En acabar, l'instal·lador mateix executa `tallat.py comprova`. Si hi ha cap ✗, llegeix el missatge, torna a executar l'instal·lador i, si continua, explica-li què passa amb paraules senzilles.

**Actualitzar** («actualitza tallat», «hi ha una versió nova?»): si és un connector de Claude Code, `claude plugin update tallat@tallat` des del terminal (o que la persona escrigui `/plugin marketplace update tallat`) i després una sessió nova; perquè li arribin soles, que activi **Enable auto-update** a `/plugin` → **Marketplaces** → **tallat**. Si és una carpeta baixada, que la torni a baixar i la posi al lloc de l'antiga (si és un clon de git, `git pull`). Després, si `.venv` no hi és, l'instal·lador només refà l'enllaç.

`tallat.py comprova` revisa en qualsevol moment que tot hi sigui (✓ bé, ! avís, ✗ cal arreglar). Descript és opcional: es connecta des de la configuració de connectors de l'assistent (a Claude, la de claude.ai).

## Ordres

Des de la carpeta de tallat: la que conté `tallat.py`, dues carpetes per sobre d'aquest `SKILL.md` (si s'ha instal·lat com a connector, és la carpeta del connector; a Claude Code, `${CLAUDE_PLUGIN_ROOT}`), amb l'entorn `.venv`. Si `.venv` no hi és (la primera vegada, o després d'actualitzar el connector), executa l'instal·lador: si ja està tot instal·lat, només refà l'enllaç i triga uns segons. **A Windows**, a totes les ordres d'aquí sota, en lloc de `.venv/bin/python` escriu `.venv/Scripts/python.exe` (amb barres «/» funciona tant a PowerShell com al Git Bash de Claude Code).

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
.venv/bin/python tallat.py marca [--projecte CARPETA | --kit ID] [CLAU=VALOR …]
.venv/bin/python tallat.py grafics --projecte CARPETA [--json]
.venv/bin/python tallat.py grafics proposa|canvia PLA.json --projecte CARPETA [--de-nou]
.venv/bin/python tallat.py grafics fotogrames --projecte CARPETA
```

La carpeta del projecte ha de ser **fora del repositori** (els vídeos i el que diu la persona no es publiquen mai).

## El teu estil (l'entrevista de marca)

La marca diu com són els vídeos de la persona: els seus colors i lletres (cadascun amb una feina), l'estil i la quantitat de gràfics, i la seva crida a l'acció. Viu al kit (secció `marca`), i en desar-la els colors i les lletres s'escampen sols: el **text** al text dels subtítols i del títol, el **fosc** (en lloc del negre) als contorns i a les ombres, el **destacat** a la paraula que sona i a les destacades (subtítols i títol; si no n'hi ha, el del text), el **principal** a les vores del b-roll i als gràfics (etiquetes, llistes, la crida), el **secundari** i el **clar** als gràfics (notes, cintes, targetes), la lletra de **text** als subtítols, la de **títols** al títol del ganxo, la d'**accent** a les paraules destacades, en cursiva, i la de **mà** a les notes i anotacions dels gràfics i a l'estil scrapbook (si no n'hi ha, la d'accent). Els estils fets de la pàgina en respecten els colors.

**Primer, a la pàgina.** Els colors, les lletres, l'estil dels gràfics i la crida es fan a la pàgina de revisió, en 4 passos visuals (a **Com es veu**, la fila **Estil**; també s'ofereix sol als panells Subtítols i Gràfics). **No la posis abans del primer vídeo:** que la persona comenci a editar de seguida. Quan arribi als subtítols o als gràfics, o si diu «vull els meus colors», digues-li que toqui **Estil** a la pàgina (a **Com es veu**).

**L'entrevista al xat és opcional.** Fes-la si la persona la demana («fem el meu estil», «vull els meus colors») o si vol que l'ajudis a decidir. Si ja té els colors i les lletres de la pàgina, salta aquestes preguntes. **No li preguntis de què va el seu compte ni qui el mira:** pot semblar que t'hi fiques, i el tema ja el saps pel que diu als vídeos. Si te'n parla ella, apunta-ho (`compte`, `public`) i fes-ho servir per als títols i els gràfics.

**Com:** al xat, **una pregunta cada cop** (si en una resposta n'hi ha contestat unes quantes, no les tornis a fer: resumeix el que has entès i passa a la següent que falti), amb paraules senzilles i 2-4 opcions concretes quan es pugui (més «una altra cosa»). Si diu «no ho sé», proposa-li tu una opció a partir del que ja t'ha dit i segueix. Les preguntes:
1. **Ensenya'm un reel que t'hauria agradat fer** (un enllaç o una captura). És la pregunta més important: mira'l (si és un enllaç, obre'l al navegador; si no el pots veure, demana una captura) i treu-ne els colors, com són els subtítols, els gràfics i el ritme. Pregunta-li què li agrada.
2. Els teus colors (codis com #FF7DB8 o en paraules: «rosa suau i negre»). Quin va al text damunt del vídeo? Quin és el principal, i quin destaca les paraules clau (o cap: van del color del text)? Un de clar per a fons i un de fosc per a ombres? (Si la persona té una guia de marca, demana-la-hi: o te l'enganxa o et diu explícitament on llegir-la.)
3. Colors o estils que no vols mai.
4. Lletres: per als títols, per al text, una d'accent per a la paraula emotiva (una amb cursiva queda molt bé) i, si en té, una de mà per a les notes (la seva lletra feta font, per exemple; pregunta-li si sempre va en majúscules: `majuscules_ma=sí`). Si en té de pròpies (fitxers .ttf, .otf…), afegeix-les al kit amb `tallat.py kit font FITXER --kit ID [--familia NOM]` (el gruix i la cursiva es dedueixen del nom del fitxer) i recorda-li que, si passa el kit a algú, ha de mirar si la llicència ho permet. Si no en té, proposa-li 2-3 combinacions de la biblioteca gratuïta (`tallat.py kit lletres`; les que tenen cursiva: Inter, Inter Tight, Archivo, Montserrat, Poppins, DM Sans, Fraunces, Playfair Display, DM Serif Display, Instrument Serif). Per exemple: DM Sans + Fraunces + Instrument Serif (editorial), Poppins + Poppins + Playfair Display (net i càlid), Archivo + Anton + Instrument Serif (impacte).
5. Els subtítols: d'una paraula, frases curtes o la frase sencera? Amb les paraules clau més grans? En minúscules? (Tria'n l'estil fet que hi encaixi i posa'l amb la pàgina o al `kit.json`.)
6. L'estil dels gràfics, un o uns quants: net i minimalista, Mac (finestres, menús, carpetes, elements d'interfície), juganer (scrapbook: stickers, retalls, notes) o editorial (titulars grans, com una revista).
7. Quants gràfics: pocs (un cada 8-12 s, sobretot tu a càmera), normal (cada 4-6 s) o molts (cada 2-4 s).
8. Efectes de so: cap, pocs o molts.
9. El ritme dels talls: natural, àgil o ràpid (`talls.pausa_maxima` 0,5 / 0,35 / 0,25).
10. La teva crida a l'acció habitual («comenta GUIA i te l'envio», «segueix-me per a la part 2»…).

**En acabar:** ensenya-li un resum curt i pregunta «hi canviaries res?». Després:
- Desa-ho: `tallat.py marca --projecte X referencia="…" color_text=#… color_principal=#… color_destacat=#… color_secundari=#… color_clar=#… color_fosc=#… colors_prohibits="…" lletra_titols=… lletra_text=… lletra_accent=… lletra_ma=… majuscules_ma=sí|no energia=mac,scrapbook grafics=pocs|normal|molts crida="…"`. Les lletres de la biblioteca es poden dir pel nom o per l'id i es baixen soles (amb la cursiva).
- Si vol un kit nou per a la marca, crea'l abans (`tallat.py kit nou "La meva marca"` i `kit tria`).
- La resta (subtítols, so, ritme), als seus apartats del kit. Cada «no vull mai…» que digui, com a regla del gust (`tallat.py gust afegeix`).
- Obre-li la pàgina (`tallat.py revisa`) perquè ho vegi: a **Com es veu**, la fila **Estil** porta a la llista d'estils, i el seu ho ensenya i ho deixa retocar.

**Després:** quan facis el muntatge o proposis títols i gràfics, llegeix la marca (`tallat.py marca --projecte X`) i fes-la servir: el compte i el públic per al to, l'energia i la quantitat per als gràfics, i la crida a l'acció al final. Si la marca i el teu gust no coincideixen, mana la marca.

## Transcriure

- **Amb Descript** (millor text, conserva el farciment): importa l'àudio al compte de la persona amb el connector de Descript (projecte privat, idioma `ca`), exporta la transcripció en SRT, desa-la a la carpeta del projecte i executa `transcriu --srt`. WhisperX només hi calcula el temps de cada paraula.
- **Sense Descript**: `transcriu` sense `--srt` fa servir WhisperX sencer. És més lent i esborra part del farciment; avisa-ho.
- **El temps de cada paraula** el calcula el model de veu català de Softcatalà (el que ja instal·la `prepara.sh`; gratuït i sense internet): tot el text contra tot el so, i les vores de les paraules es retallen als silencis reals. És el que fa que els talls caiguin al lloc i que els subtítols vagin a temps. No es refia dels temps de l'SRT. Cada paraula es desa amb la seva confiança; els números i els símbols no es poden escoltar i a la pàgina surten subratllats amb punts (temps aproximat).
- **Per comparar els temps amb els de Descript** (p. ex. si la persona diu que un tall sona malament): `tallat.py compara-temps --projecte X --srt fitxer.srt`. Diu quant s'assemblen i on difereixen més; escolta aquells punts per saber quin encerta. Amb un SRT d'una paraula per subtítol es comparen totes les paraules.
- **Si els talls sonen malament o els subtítols van a destemps en un projecte fet abans** (amb l'alineador d'abans): `tallat.py realinea --projecte X`. No toca el text ni l'edició; desa la transcripció d'abans al costat. Després, cal tornar a obrir la pàgina de revisió.
- **Si hi ha una pausa llarga que no surt com a pastilla a la pàgina** (no es pot escurçar): sovint és dins d'una paraula que l'alineador ha estirat per sobre del silenci. En un projecte fet abans de l'arranjament, `tallat.py realinea --projecte X --nomes-vores` retalla les vores amb el mapa de veu que ja hi ha (en segons, sense tornar a escoltar el vídeo).

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
- **Sense «Claude»**: si la persona s'oblida de dir-ho (o el transcriptor no ho entén i escriu «Mira», «Llavors»…), tallat també troba les frases curtes que comencen amb una ordre clara («sticker de…», «b-roll…», «tallem…», «torno a començar», «fes zoom»). Queden **dubtoses** (`sense_paraula`): no se'n treu res del vídeo fins que la persona les accepta a la pàgina (llavors se'n treuen les paraules; si ho desfà, hi tornen). Repassa-les amb ella: «He trobat 2 frases que semblen instruccions, però no has dit "Claude". Mira-les a **Edita → Instruccions de veu**».
- **Consell per a la propera gravació**: la primera vegada que treballeu amb instruccions de veu (o si n'hi ha de dubtoses), digues-li en una línia: «Quan gravis, comença cada instrucció amb **"Claude,"** i fes una petita pausa abans: per exemple, *"Claude, sticker d'un cor."*».
- Si una instrucció no s'ha detectat i l'afegeixes a mà, treu-ne també les paraules on la deia: `tallat.py afegeix sticker --paraula ID --text "…" --treu A-B` (A i B, la primera i l'última paraula de la instrucció; es poden recuperar a la pàgina).
- En proposar reels, no hi incloguis les paraules de les instruccions ni marques com «Continuo» que només serveixen per a la gravació.

## B-roll i stickers

tallat no depèn de cap IA: només necessita un fitxer per a cada instrucció acceptada.

- **Fitxers propis**: a la pàgina de revisió, cada instrucció de b-roll o de sticker acceptada té «Puja un fitxer…» (o s'hi pot arrossegar) i, si n'hi ha, un desplegable amb la biblioteca (`~/.tallat/broll/`, `~/.tallat/stickers/`). Els stickers de la biblioteca s'assignen sols si el nom del fitxer surt a la instrucció («sticker d'un cor» → `cor.png`).
- **Generats amb IA (opcional)**: si la persona té connectada a l'assistent una IA d'imatge o vídeo (Krea, Higgsfield, OpenArt, Adobe Firefly…), ofereix-li generar-los. Abans de generar, digues-li quin model faràs servir i que gastarà crèdits del seu compte, i espera que ho confirmi.
  - B-roll: vídeo vertical 9:16, el més curt que permeti el model (tallat n'agafa 1-1,5 s); o una imatge (tallat hi fa un zoom lent). Escriu la descripció en anglès, concreta i visual, sense text ni cares de persones reals.
  - Stickers: imatge PNG amb el fons transparent (si la IA no en sap fer, treu-ne el fons amb una altra eina o demana-li a la persona).
  - Baixa el fitxer a la carpeta del projecte i registra'l: `tallat.py broll ID FITXER` o `tallat.py sticker ID FITXER`.
- Per afegir-ne en un moment sense instrucció de veu: `tallat.py afegeix broll|sticker|zoom --paraula ID --text "…"` (amb `--treu A-B` si la persona la va dir en veu alta i se n'han de treure les paraules).
- **No generis cares de persones reals** (famosos, coneguts): proposa un pla que evoqui la referència o demana imatges pròpies.

### Com surt el b-roll a la pantalla

- Es tria a la pàgina: **Com es veu** → **B-roll**. Maneres fetes (`config/estils_broll.json`): **Pantalla sencera** (tapa la imatge, tall sec, com sempre), **Targeta** (una targeta gran arrodonida; la persona es veu al voltant), **Finestra** (petita a la cantonada, amb vora del color del kit), **Foto** (vora blanca gruixuda i inclinada), **Pantalla partida** (el b-roll a la meitat de dalt i la persona a la de baix) i **Tres targetes** (els b-rolls seguits, a menys d'un segon l'un de l'altre, entren d'un en un en fins a tres targetes una al costat de l'altra i s'hi queden fins que s'acaba l'últim).
- Es desa al kit, secció `broll`: `disposicio` (`pantalla`, `targeta`, `partida`, `carrusel`), `mida` i `posicio_x`/`posicio_y` (de la targeta), `proporcio` (9:16, 3:4, 4:5, 1:1, 16:9), `radi` (cantonades), `vora` i `vora_color` (null: el color destacat dels subtítols), `ombra`, `rotacio` i `animacio` (pop, puja, llisca, fos o cap).
- On va cada targeta es calcula en un sol lloc (`motor/targetes.py`): la vista prèvia i el vídeo final són iguals. Al projecte per a Premiere o Final Cut, el b-roll en targeta hi va més petit, retallat i al seu lloc, però sense les cantonades arrodonides, la vora ni l'ombra.
- Si la persona fa servir **Tres targetes**, digues-li que funciona amb b-rolls seguits (un darrere l'altre); si només n'hi ha un de sol, surt una sola targeta al mig.

## Estil dels subtítols

- Es tria a la pàgina de revisió: **Com es veu** → **Subtítols** (la columna de l'esquerra té, sota el nom, un desplegable per triar el vídeo sencer o un dels reels; després **Per revisar** —les instruccions de veu i les paraules que tallat proposa treure—; **Com es veu**: una fila per a l'**Estil**, els **Subtítols**, el **Títol del ganxo**, els **Gràfics**, el **B-roll** i el **So**, cadascuna amb el que hi ha triat; en tocar-ne una s'obre el seu panell, i **‹ Enrere** torna a la llista; i, al final, **Ritme**: Original, Pausat, Normal o Àgil, com de curts queden els silencis. Els vídeos exportats són a **Exporta**). Hi ha 18 estils predefinits (Clàssic, Net, Una paraula, Frase, Caixa, Karaoke, Impacte, Elegant, Cortina, Revista, Neó, Degradat, Emojis, i els dissenyats: Apilat, Escampat, Esglaó, Titular, Rètol) i es pot ajustar tot: quantes paraules surten, si apareixen d'una en una o totes de cop, l'animació (pop, fos, impacte, cortina, gruix o cap), com es destaca la paraula que sona (color, caixa, karaoke o més gran), l'aspecte (normal, neó o degradat), una píndola de fons, emojis, la lletra, la mida, la posició i els colors.
- **Disposició** (`disposicio`): `linia` (cada línia substitueix l'anterior), `apilat` (les línies d'una frase s'apilen una sota l'altra fins que la frase acaba o n'hi ha `linies_max`) o `escampat` (com un collage: les paraules de la frase surten en files curtes a llocs, mides i inclinacions diferents; les destacades, soles i grans; les curtes, més petites. La mateixa frase fa sempre el mateix collage, i l'alineació no hi compta). **Alineació** (`alineacio`): `centre`, `esquerra`, `dreta` o `esglao` (per torns a l'esquerra i a la dreta; les línies que només tenen paraules destacades, al mig, com un títol). `espaiat` (entre lletres; negatiu = juntes, com als títols de revista) i `interlineat` (entre línies).
- **Paraules destacades** (`clau_grans`): surten `clau_mida` vegades més grans i amb `clau_color` (null: el color del destacat), amb la lletra `clau_font` (null: la mateixa; la marca hi posa la d'accent) i en cursiva amb `clau_cursiva`; amb `clau_sola`, cada una va sola a la seva línia (amb `apilat` fa el look de títol: «és tan / AMBICIÓS / o / EMPRENEDOR»). tallat en tria soles (els números i la paraula llarga més important de cada línia). La persona les pot canviar a la pàgina (marca la paraula i ⌘B, o **Destaca** a la barreta que surt a sobre de les paraules marcades; allà mateix hi ha **Corregeix** i **Treu**), i tu amb `tallat.py destaca --projecte X --si ID… --no ID…` (sense opcions, et diu quines surten ara, amb el seu número). Quan la persona vulgui subtítols dissenyats, revisa-les: una per idea, les que porten el pes del missatge (substantius, xifres, adjectius forts), mai paraules pont. La pàgina oberta es posa al dia sola en uns segons.
- **Lletres**: les del Mac, 18 de gratuïtes (Inter, Inter Tight, Archivo, Anton, Bebas Neue, Montserrat, Poppins, Fraunces, Playfair Display, Caveat…; `tallat.py kit lletres`) que es baixen dins del kit el primer cop que es trien (`tallat.py kit lletra ID`, o a la pàgina), i les que puja la persona. Totes les lletres que no són del Mac viuen a la carpeta `fonts/` del kit i viatgen amb ell.
- La vista prèvia i el vídeo final fan servir el mateix codi d'animació (`pagina/subtitols.js`): el que es veu a la pàgina és el que surt.
- Es desa al **kit d'estil** del vídeo (vegeu més avall), a la secció `subtitols`. Si la persona et demana un canvi al xat, edita el `kit.json` d'aquell kit: cada opció hi té una nota que l'explica. Els estils predefinits són a `config/estils_subtitols.json`; els emojis, a `config/emojis.json` (la persona en pot afegir a `~/.tallat/emojis.json`).

## Títol del ganxo

- Un text dissenyat que surt els primers segons del vídeo (com els rètols dels reels: «#3 canvis / *ser creadora* / nivell fàcil»). Cada línia és una línia; el que va `*entre asteriscs*` surt destacat (més gran i del color destacat). El text és de cada vídeo (a l'estat: es desfà amb ⌘Z); l'estil, del kit (secció `titol`): lletra (null: la dels subtítols), mida, `clau_mida`, colors, contorn, ombra, `alineacio` (també `esglao`: les línies a banda i banda i les només destacades, al mig), posició, `animacio` (puja, pop, fos, cortina, `maquina` —lletra a lletra amb cursor— o cap), `fons` (cap, `enfosquit` —el vídeo s'enfosqueix— o `pindola` —una caixa darrere cada línia), `corba` (de -1 a 1: 0 recta, positiu en arc com el de Sant Martí, negatiu com un somriure) i `corba_linies` (`primera`, `totes` o `darrera`; les línies corbades no porten caixa), `durada` i `amaga_subtitols`. Estils fets: Esglaó, Rètol, Màquina, Revista, Caixa i Arc (`config/estils_titol.json`).
- A la pàgina: **Com es veu** → **Títol del ganxo** (el text, la durada i l'estil, en un sol panell). Al xat: `tallat.py titol`.
- Quan facis el primer muntatge o la persona demani un títol, proposa-n'hi un i ensenya-l'hi abans de posar-lo: 2-4 línies curtes, en la seva veu, amb una sola part destacada (la idea que fa quedar-se a mirar), sense paraules buides ni promeses que el vídeo no compleix. Si el títol repeteix el que es diu, recomana «sense subtítols mentre surt el títol».

## Pla de gràfics

Gràfics que proposes tu, frase a frase, i que la persona revisa a la pàgina (**Com es veu** → **Gràfics**): una graella de miniatures; en tocar-ne una s'obre amb **Canvia** (amb una nota per a tu) i **Treu**. Si no hi toca res, li va bé (es queda «proposat»; si el mou, li canvia l'estil o hi puja imatges, passa a «mantingut»). Els proposats ja surten a la vista prèvia i al vídeo; els trets, no. Es desen a l'estat del vídeo (`grafics`), lligats a paraules (si es mouen els talls, segueixen la seva frase), i es dibuixen amb `pagina/grafics.js`, el mateix codi a la vista prèvia i al vídeo final.

**Tipus** (els de text no necessiten cap fitxer; la web i les fotos, imatges):
- `frase`: una frase clau en gran (com a molt 140 lletres; millor menys de 60). El que va `*entre asteriscs*` surt amb la lletra d'accent i el color destacat. Mentre surt, els subtítols s'amaguen (`amaga_subtitols: false` si no ho vols).
- `etiqueta`: una o dues paraules en una etiqueta petita, per marcar l'estructura («mite», «pas 1», «el truc», «error»).
- `llista`: una targeta amb un títol curt (opcional, a `text`) i 2-5 `punts` que surten un a un: posa a cada punt la `paraula` on es diu, i fes que la llista duri fins a l'últim (`fins`). Com la frase, amaga els subtítols mentre surt.
- `crida`: la crida a l'acció, al final i un sol cop. Sense `paraula`, va als últims segons; sense `text`, diu la de la marca.
- `notificacio`: una notificació del mòbil que cau de dalt: qui l'envia a `de` («mama», «el banc», «Instagram»; com a molt 30 lletres) i el missatge a `text`. Per a quan la persona explica que algú li diu o li escriu una cosa.
- `xat`: una conversa en bombolles. Els missatges van a `punts`, cadascun amb `costat` (`rebut`, a l'esquerra, o `enviat`, a la dreta; si no, per torns) i la `paraula` on es diu; abans dels rebuts surten els tres punts d'«escrivint…». A `text`, el nom de l'altra persona (opcional). Amaga els subtítols.
- `numero`: una xifra gran que compta des de zero, amb la `xifra` com s'escriu («73 %», «10.000 €», «3 de cada 4»: compta el primer número) i un `text` curt a sota. Només amb xifres que la persona diu de debò.
- `anotacio`: una nota escrita a mà (`text`, com a molt 40 lletres) amb una `forma` que es dibuixa sola: `fletxa` (de la nota cap al mig de la pantalla, cap a la persona), `cercle` (al voltant de la nota) o `subratllat`; `costat`: `esquerra` o `dreta`. Va amb la lletra de mà i el color secundari de la marca, sigui quin sigui l'estil. Per a comentaris irònics o aclariments («jo, fa 3 anys», «spoiler: no»).
- `web`: una captura de pantalla dins d'una finestra de navegador, que baixa a poc a poc si la captura és llarga. A `text`, l'adreça que surt a la barra («elmeuweb.cat/curs»); a `imatge`, la captura. Per a quan la persona parla d'una web, una eina o un producte en línia. Si et diu l'adreça, fes-ne la captura: `tallat.py grafics captura URL --grafic gN --projecte X` (amb el gràfic ja desat; sense `--grafic`, et diu el nom de la imatge per posar-lo al pla). Si la web demana iniciar sessió o surt un avís de galetes, millor que la persona hi pugi la seva captura a la pàgina.
- `ventall`: de 2 a 6 fotos obertes en ventall que surten una a una. Cada foto és un punt: `{"imatge": "~/Desktop/foto.jpg", "text": "abans", "paraula": 52}` (`text`: un peu curt, opcional; la `paraula` on es diu). A `text`, un títol (opcional). Per a «abans i després», un procés, uns quants exemples. Fes servir només fotos que la persona t'hagi donat.
- La web i el ventall van amb **bloc de color** per defecte (`"bloc": false` per treure'l) i amaguen els subtítols. Les imatges poden ser camins de fitxers del Mac: en desar el pla, tallat les copia al projecte. Si encara no en tenen, el gràfic no surt al vídeo i la pestanya Gràfics de la pàgina hi mostra **Puja la captura** o **Puja les fotos**: digues-ho a la persona.

**Estils** (`estil`): `net`, `mac` (targetes i finestres d'interfície), `scrapbook` (paper, cinta, lletra de mà) o `editorial` (titulars, ratlles, números). Fes servir només els de la marca (`energia`); si n'hi ha uns quants, barreja'ls amb criteri (per exemple, mac per a llistes i crides, scrapbook per a frases emotives, editorial per a etiquetes). Si no en poses, va el primer de la marca. **Lloc** (`posicio`): `dalt`, `mig`, `baix` o un número de 0 (dalt) a 1 (baix), on va el centre del gràfic (per defecte: frase i etiqueta a dalt, llista i crida a baix; si dos gràfics coincideixen al mateix lloc, tallat en mou un). Mai no en surten de la **zona segura d'Instagram** (el 14 % de dalt i el 35 % de baix queden lliures, i 120 px a cada costat, pels botons): tallat els hi fa cabre sols. Tampoc no tapen els subtítols; els que els amaguen (`amaga_subtitols`) poden ocupar el seu lloc. **Durada**: frase 2,8 s, etiqueta 2,2, llista 4,5, crida 3,5, notificació 3, xat 5, número 2,8, anotació 2,5, web 4, ventall 4,5; amb `fins` (una paraula), dura fins que s'acaba aquella paraula.

**Bloc de color** (`"bloc": true`): mentre surt el gràfic, el fons es fa del color de la marca (el fosc; el principal amb `mac` i `scrapbook`), el vídeo es fa petit amb una animació suau fins a una targeta a baix (s'hi continua veient la cara) i el gràfic té tot l'espai de dalt. Per defecte va al mig d'aquest espai i amaga els subtítols. Si dos gràfics amb bloc van seguits, el vídeo s'hi queda petit. Va bé per a les llistes, la web, les fotos i els moments «diapositiva», sobretot quan la cara omple el requadre i no hi ha lloc lliure; no n'abusis (un o dos per vídeo) i, mentre dura, no hi posis cap altre gràfic. La persona l'activa o el treu tocant el gràfic al vídeo. Només surt als vídeos que exporta tallat, no al projecte per a altres editors.

**Quan:** quan la persona digui «proposa'm gràfics», «posa-hi gràfics» o similar. En acabar el primer muntatge, ofereix-l'hi (no l'imposis).

**Com:**
1. `tallat.py grafics --projecte X` et dona la marca (l'estil i quants gràfics, la crida), les frases del vídeo tal com sonen ara (el segon i el número de la primera i l'última paraula) i el pla que hi ha. Llegeix també `tallat.py gust`.
2. Fes el pla:
   - Quants: els de la marca (`pocs`, un cada 8-12 s; `normal`, cada 4-6 s; `molts`, cada 2-4 s).
   - Un gràfic per idea, on ajudi a entendre o a quedar-se: la frase que porta el pes del missatge (`frase`), l'estructura (`etiqueta`), les enumeracions (`llista`), el que algú li va dir o escriure (`notificacio`, `xat`), les xifres (`numero`), els comentaris de costat (`anotacio`), una web o una eina de la qual parla (`web`), les fotos que t'hagi donat (`ventall`) i la crida al final. Varia els tipus: no en posis tres d'iguals seguits.
   - No tapis el títol del ganxo (els primers segons) ni posis dos gràfics al mateix lloc alhora.
   - **On queda millor:** després de desar-lo, fes `tallat.py grafics fotogrames --projecte X` i mira la imatge que et diu (un fotograma per gràfic, en ordre; enfosquit, on no pot anar res; el requadre groc, on sí). Tria el lloc de cada un segons el que hi ha al fotograma: que no tapi els ulls ni la boca, ni el que s'ensenya (un objecte, una pantalla). Si la cara omple el requadre, els petits (etiquetes, frases d'una línia) a dalt, sobre el front, i els grans (llistes, targetes) a baix, en lloc dels subtítols. Desa els llocs amb `grafics canvia`.
   - En la veu de la persona i amb el seu gust (minúscules, sense paraules prohibides, sense prometre res que el vídeo no compleix). Escurça: un gràfic no és el subtítol.
3. Escriu-lo en un fitxer JSON (fora del repositori de tallat, per exemple a la carpeta del projecte) i desa'l amb `tallat.py grafics proposa PLA.json --projecte X`. És una llista:
   ```json
   [{"tipus": "etiqueta", "paraula": 3, "text": "3 coses", "estil": "editorial", "motiu": "anuncia l'estructura"},
    {"tipus": "llista", "paraula": 10, "fins": 36, "text": "abans de començar", "estil": "mac",
     "punts": [{"text": "no cal tenir-ho clar", "paraula": 14}, {"text": "constància > talent", "paraula": 23}]},
    {"tipus": "frase", "paraula": 37, "fins": 41, "text": "no és mandra, és *cansament*", "estil": "scrapbook"},
    {"tipus": "crida", "estil": "mac"}]
   ```
   `motiu` (opcional) és una frase curta que la persona veu al panell dels gràfics: per què hi va. Un pla nou substitueix els proposats que hi havia; els mantinguts, els que tenen una nota i els trets es queden (amb `--de-nou`, tot de nou). Com que la persona no ha de marcar els que li agraden, **si ja hi ha un pla, no en facis un de nou sencer sense preguntar-li-ho**: per atendre les notes o afegir-ne, fes servir `canvia`.
4. Explica-li en dues o tres frases què hi has posat i que ho revisi a **Com es veu** → **Gràfics** (la pàgina es posa al dia sola).

**Les notes:** quan digui «mira les notes» (o similar), `tallat.py grafics --projecte X`: els que diuen `CANVIA` porten la nota a sota. Si una nota parla del lloc («més avall», «em tapa la cara»), mira'n el fotograma (`grafics fotogrames`) abans de triar-ne un altre. Fes el que demana cada nota i desa només aquells gràfics, amb el mateix `id` i sencers (tipus, paraula, text…), amb `tallat.py grafics canvia NOTES.json --projecte X`: la resta del pla no es toca. Un gràfic canviat torna a «proposat» i perd la nota. Si una nota demana un gràfic que encara no existeix (una finestra de web, imatges, el vídeo dins d'un marc…), digues-li que encara no n'hi ha i proposa-li el més semblant.

## So

- **Com es veu** → **So**, a la pàgina; es desa al kit, secció `so`.
- **Neteja de la veu** (`neteja`, sí per defecte): treu el brunzit greu i el soroll de fons (`soroll`: `suau`, `mitja` o `fort`), dona claredat, suavitza les «s», comprimeix una mica i iguala el volum a -14 LUFS (el de les xarxes), en dues passades. S'aplica a l'esborrany i al vídeo final; a la vista prèvia sona la veu original, però la pàgina en deixa escoltar deu segons abans i després. Si la persona diu que la veu sona estranya o «enllaunada», baixa el `soroll` a `suau` o apaga la neteja.
- **Efectes de so** (`efectes`: `cap`, `pocs` —whoosh al b-roll i a la frase clau, pop als stickers i a la llista, campaneta al títol i a la crida, o teclat si el títol és a màquina d'escriure— o `molts` —també un pop a cada etiqueta i a cada punt de la llista i un tic a les paraules destacades; `volum_efectes` de 0 a 1). Els fabrica tallat amb codi (`motor/so.py`): sense fitxers de fora ni llicències. Cada efecte d'un vídeo es pot apagar a la llista de la pestanya So (queda a l'estat, `sons_apagats`). La persona hi pot posar els seus sons a `~/.tallat/sons/` amb el nom del que substitueixen (whoosh, pop, tecla, brill o tic; WAV, MP3, M4A o AIFF).
- Tots els efectes es barregen en una sola pista: la mateixa sona a la vista prèvia i va al vídeo final. Al projecte per a Premiere o Final Cut i als trossos per a CapCut va a part (`efectes-de-so.wav`, a posar a l'inici); allà la veu no va neta.

## Kits d'estil

- Un kit és un estil amb nom: els subtítols (amb la lletra pròpia, si en té), el b-roll, els stickers i els talls. La persona en pot tenir uns quants («Reels ràpids», «Vídeos tranquils»…) i cada vídeo en fa servir un. Un reel fa servir el de la seva gravació, si no se n'hi tria un altre.
- Són a `~/.tallat/kits/<id>/kit.json`, amb les fonts a `fonts/`, fora del repositori. `~/.tallat/kits/kits.json` diu quin és el **per defecte**: el dels vídeos nous, i el que canvien les regles del gust. Els valors que falten a un kit es prenen de l'estil neutre (`config/brand.example.json`).
- La primera vegada, l'estil que la persona ja tenia (`~/.tallat/brand.json`) es converteix en el kit «El meu estil». brand.json no es toca, però ja no es fa servir.
- A la pàgina de revisió, **Com es veu** → **Estil**: la llista d'estils (tocar-ne un el fa servir en aquest vídeo i n'obre el panell, amb els colors, les lletres i, al peu, les accions). Es pot triar el kit del vídeo, duplicar-lo, fer-ne un de nou amb l'estil de tallat, canviar-li el nom, fer-lo per defecte, exportar-lo (un `.zip` per passar-lo a algú) i importar-ne. Al xat: `tallat.py kit` i les seves ordres. L'id d'un kit (el nom de la carpeta) no canvia encara que se li canviï el nom.
- Quan la persona vulgui un estil «per a un tipus de vídeo» o «per passar-lo a algú», proposa-li un kit. Si un kit porta una font pròpia i el vol passar a algú, recorda-li que comprovi que la font es pot compartir.
- «Treure» un kit no l'esborra: va a `~/.tallat/kits-esborrats/`. El kit per defecte no es pot treure.

## Acabar-lo en un altre editor

Si la persona vol retocar el vídeo a Premiere, Final Cut, DaVinci Resolve o CapCut: `tallat.py editors` (o, a la pàgina, **Exporta** → «Per acabar-lo en un altre editor» → «Premiere, Final Cut o DaVinci»). Escriu a `exports/` una carpeta amb el projecte (`.fcpxml` per a Final Cut i DaVinci, `.xml` per a Premiere), els subtítols en `.srt`, el b-roll i els stickers a `recursos/`, i un `LLEGEIX-ME.txt` amb els passos de cada editor. CapCut i iMovie no importen projectes: per a ells, `tallat.py editors --trossos` (a la pàgina, «CapCut o iMovie») treu cada tros com un clip numerat (01.mp4, 02.mp4…) amb el zoom aplicat, el b-roll i els stickers amb el moment al nom, i el `.srt`; arrossegats tots alhora a la línia de temps queden en ordre (es poden escurçar, no allargar). Amb `--amb-subtitols` hi afegeix els subtítols, el títol del ganxo i els gràfics de tallat com a capa transparent (tarda uns minuts); sense, el títol i els gràfics no hi són. Els talls apunten al vídeo original: que no el mogui.

## El teu gust (regles per als vídeos següents)

- **Abans de decidir res** (neteja, primer muntatge i reels, instruccions, b-roll i stickers, gràfics, estil), llegeix les regles amb `tallat.py gust` i segueix-les. Les que porten un ajust ja s'apliquen soles.
- **Quan la persona reacciona a un resultat** («massa lent», «els subtítols són petits», «no em treguis els vale»):
  1. Busca el comportament que hi ha darrere, no només el cas concret: «aquest b-roll és massa llarg» vol dir «b-roll més curt», no «treu aquest b-roll».
  2. Pregunta-li (amb opcions de resposta si en pots fer; si no, amb una pregunta curta) si és **per a aquest vídeo** o **per sempre** (recomana «per sempre»). Si ja ho ha dit («sempre», «només aquí»), no ho preguntis.
  3. Si és per sempre, desa-ho: `tallat.py gust afegeix SECCIO "la regla en paraules de la persona" [--ajust clau=valor]`. Si és només per a aquest vídeo, fes-ho al projecte i prou.
- Seccions: `talls`, `subtitols`, `grafics`, `broll`, `stickers`, `so`, `reels`, `altres`.
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
| sense efectes de so / més efectes | `so.efectes="cap"` / `"molts"` |
| el b-roll en targeta / a pantalla sencera | `broll.disposicio="targeta"` / `"pantalla"` |
| stickers més petits / més grans | `stickers.mida=0.25` |

- Per treure'n una: `tallat.py gust treu NUMERO` (l'opció torna a com estava). Les regles només es porten al xat (a la pàgina no hi són): si la persona pregunta quines té, ensenya-les-hi en paraules senzilles.

## Exportar

- L'esborrany és per revisar. El vídeo final es fa a la pàgina (**Exporta** → **Vídeo final**), que diu **a quina carpeta es desa** i té **Canvia…** (la finestra del Mac o de Windows per triar carpeta; tallat la recorda). Al xat, `tallat.py exporta` fa el mateix i desa a la mateixa carpeta.
- Els vídeos sempre queden també a la carpeta del projecte (a **Exporta**, a **Els teus vídeos**); a la carpeta triada hi van com un enllaç al mateix fitxer (no ocupen més lloc al mateix disc).
- Quan acabi, digues-li el nom del fitxer i on és. A la pàgina queda un avís amb **Mostra-la al Finder** (a Windows, **a l'Explorador**).
- Per a Premiere: després d'importar el `.xml`, cal fer **doble clic a la seqüència** (si s'arrossega a una seqüència nova, el Premiere la converteix en un sol clip).

## Revisar l'esborrany

- La pàgina no té notes: la persona mira l'esborrany (o el muntatge En directe) i et diu al xat què vol canviar, amb el segon que veu sota el vídeo («al segon 12, el b-roll és massa llarg»).
- Per saber què hi ha en aquell moment, `tallat.py moment SEGONS --projecte X` (amb `--esborrany` si parla de l'esborrany: si ha canviat coses després, els temps no coincideixen amb el muntatge d'ara). Et diu el segon de la gravació, les paraules del voltant amb el seu número (» la que sona, [entre claudàtors] les tretes) i si hi surt el títol, un gràfic del pla, un b-roll o un sticker. Si no està clar de quina vista parla, pregunta-l'hi.
- Fes el canvi i explica-li què has fet. Si la correcció sembla «per sempre» (el b-roll sempre és massa llarg), segueix el que diu «El teu gust».

## Regles

- No llegeixis ni copiïs cap carpeta de marca personal tret que la persona ho demani explícitament.
- No esborris ni moguis fitxers de la persona sense que t'ho confirmi.
- No es renderitza res en 4K fins que la persona ho aprova a la pàgina («Final…»).
