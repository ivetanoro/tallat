# tallat · instruccions per a l'assistent

Aquest fitxer el llegeixen Codex i altres assistents que obren aquesta carpeta. Claude Code fa servir les mateixes instruccions com a connector.

**Si la persona vol editar un vídeo, instal·lar tallat («instal·la tallat»), comprovar-lo o fer qualsevol cosa amb tallat:** llegeix sencer `skills/tallat/SKILL.md` i segueix-lo. Les ordres s'executen des d'aquesta carpeta, amb `.venv/bin/python tallat.py …` (a Windows, `.venv\Scripts\python.exe tallat.py …`). Si `.venv` no hi és, primer cal `./prepara.sh` (a Windows, `powershell -ExecutionPolicy Bypass -File prepara.ps1`).

**Permisos.** Les ordres de tallat necessiten internet (instal·lar, dibuixar els subtítols) i escriure fora d'aquesta carpeta: a `~/.tallat` i a la carpeta de cada projecte, on hi ha els vídeos de la persona. Si treballes en un entorn protegit (sandbox), demana permís per executar-les fora, explicant-li per què en una frase.

**La pàgina de revisió** (`tallat.py revisa`) ha de quedar engegada mentre la persona treballa: llança-la en segon pla (per exemple, `nohup .venv/bin/python tallat.py revisa --projecte CARPETA > ~/.tallat/revisa.log 2>&1 &`; a Windows, en PowerShell i amb la carpeta del projecte entre cometes dobles dins de les simples perquè els espais no la partissin: `Start-Process -WindowStyle Hidden -WorkingDirectory . -FilePath .venv\Scripts\python.exe -ArgumentList 'tallat.py revisa --sense-navegador --projecte "C:\ruta\de la carpeta"' -RedirectStandardOutput $env:USERPROFILE\.tallat\revisa.log -RedirectStandardError $env:USERPROFILE\.tallat\revisa-errors.log`), comprova que respon a http://127.0.0.1:8765/ i dona-li aquesta adreça.

Parla sempre en català senzill: la majoria de persones que fan servir tallat no són programadores. Abans de moure o esborrar res seu, pregunta-ho. Abans de gastar crèdits d'una IA de pagament, digues quin model faràs servir i espera que ho confirmi.

**Si la persona vol canviar el codi de tallat**, segueix les regles del projecte ([CLAUDE.md](CLAUDE.md)): tot en català, marca neutra per defecte, cap vídeo ni transcripció dins del repositori, i codi escrit de zero. Les proves: `.venv/bin/python -m unittest discover -s proves -t .`
