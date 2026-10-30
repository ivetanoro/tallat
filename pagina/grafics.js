/* tallat · els gràfics del pla: frase clau, marcador, etiqueta, ratllat, llista, crida, segueix-me, notificació,
 * comentari, publicació, xat, notes, número, progrés, anotació, REC, web (una captura dins d'una finestra), ventall
 * (unes quantes fotos), abans i després i carrusel.
 *
 * Com els subtítols, el mateix codi els dibuixa a la vista prèvia i al vídeo final (dins de la
 * composició de HyperFrames). Treballa sobre una caixa de 1080 × 1920 px; qui el fa servir l'escala.
 * Cal haver carregat abans subtitols.js (en fa servir els colors i les lletres).
 *
 *   const tl = TallatGrafics.construeix(element, grafics, paleta, { tl });
 *   tl.seek(segons);
 *
 * `grafics`: [{id, tipus, inici, final, text, punts: [{text, t}], estil, posicio, limits}], en temps del
 * muntatge (els calcula motor/grafics.py). `estil`: net, mac, scrapbook o editorial. `posicio`: dalt,
 * mig, baix o un número (on va el centre, de 0 a 1); `limits`: [dalt, baix] en px, la zona segura
 * d'Instagram sense els subtítols. El gràfic no en surt mai.
 * `paleta`: {text, principal, destacat, secundari, clar, fosc, lletra_titols, lletra_text, lletra_accent}.
 * A la frase i a la crida, el que va *entre asteriscs* surt destacat; al marcador (una frase), hi passa un marcador
 * (si no n'hi ha, per tota la frase). La notificació porta qui l'envia
 * (`de`), el comentari qui l'ha escrit (`de`), el ratllat el que es ratlla i el que hi va (els dos `punts`), el xat els missatges a `punts` (cadascun amb `costat`: rebut o enviat), el número la `xifra`
 * ({abans, valor, decimals, despres, milers}), el progrés la xifra, quina part s'omple (`fraccio`, de 0 a 1) i la
 * `forma` (cercle o barra), i l'anotació la `forma` (cercle, subratllat o fletxa) i el
 * `costat` on va. L'anotació s'escriu amb la lletra de mà i el color secundari de la marca.
 * La web porta la captura a `imatge` (i l'adreça de la barra a `text`); el ventall, les fotos als `punts`
 * (cadascuna amb `imatge` i un peu, `text`). `op.imatges`: on són les imatges (per defecte, «imatges/»).
 * Sense GSAP (sense internet), els gràfics surten sencers mentre duren.
 */
(function (global) {
  "use strict";

  const ESTILS_CSS = `
.tg-capa { position: absolute; left: 0; top: 0; width: 1080px; height: 1920px; pointer-events: none; }
/* 120 px a cada costat: a la dreta hi ha els botons d'Instagram. L'alçada la posa colloca(). */
.tg-lloc { position: absolute; left: 120px; top: 269px; width: 840px; display: flex; justify-content: center; visibility: hidden; }
.tg-lloc.tg-etiqueta { justify-content: flex-start; }
.tg-cos { position: relative; box-sizing: border-box; max-width: 100%; font-kerning: normal; overflow-wrap: break-word; }
.tg-clau { font-family: var(--tg-f-accent); font-style: italic; font-weight: 400; color: var(--tg-destacat); }

.tg-frase .tg-cos {
  font-family: var(--tg-f-titols); font-weight: 700; color: var(--tg-text); text-align: center;
  font-size: calc(104px * var(--tg-escala)); line-height: 1.04; letter-spacing: -0.02em;
}
.tg-net.tg-frase .tg-cos { text-shadow: 0 4px 22px var(--tg-ombra); }
.tg-mac.tg-frase .tg-cos {
  font-family: var(--tg-f-text); font-size: calc(78px * var(--tg-escala)); letter-spacing: -0.01em; line-height: 1.1;
  color: var(--tg-fosc); background: var(--tg-clar); padding: 40px 54px 44px; border-radius: 44px;
  box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-mac .tg-clau, .tg-scrapbook .tg-clau { color: var(--tg-principal); }
.tg-scrapbook.tg-frase .tg-cos {
  font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-weight: 400; font-size: calc(92px * var(--tg-escala)); line-height: 1.06;
  color: var(--tg-fosc); background: var(--tg-clar); padding: 46px 54px 42px; border-radius: 6px; rotate: -2deg;
  box-shadow: 8px 10px 0 var(--tg-ombra-suau);
}
.tg-scrapbook .tg-clau { font-style: normal; }
.tg-scrapbook.tg-frase .tg-cos::before, .tg-scrapbook.tg-llista .tg-cos::before, .tg-scrapbook.tg-crida .tg-cos::before,
.tg-scrapbook.tg-notificacio .tg-cos::before, .tg-scrapbook.tg-comentari .tg-cos::before, .tg-scrapbook.tg-web .tg-cos::before,
.tg-scrapbook.tg-ratllat .tg-cos::before, .tg-scrapbook.tg-publicacio .tg-cos::before, .tg-scrapbook.tg-notes .tg-cos::before {
  content: ""; position: absolute; left: 50%; top: -24px; width: 190px; height: 48px; margin-left: -95px;
  background: var(--tg-cinta); rotate: 3deg;
}
.tg-editorial.tg-frase .tg-cos {
  font-weight: 400; font-size: calc(118px * var(--tg-escala)); line-height: 1; letter-spacing: -0.03em;
  padding: 28px 0 30px; border-top: 3px solid var(--tg-text); border-bottom: 3px solid var(--tg-text);
  text-shadow: 0 3px 18px var(--tg-ombra-suau);
}

.tg-etiqueta .tg-cos { font-family: var(--tg-f-text); font-size: 52px; font-weight: 700; line-height: 1; white-space: nowrap; }
.tg-net.tg-etiqueta .tg-cos { background: var(--tg-principal); color: var(--tg-sobre-principal); padding: 18px 32px 20px; border-radius: 999px; }
.tg-mac.tg-etiqueta .tg-cos {
  font-weight: 600; color: var(--tg-fosc); background: var(--tg-clar); padding: 18px 32px 20px 28px; border-radius: 999px;
  box-shadow: 0 14px 34px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-mac.tg-etiqueta .tg-cos::before {
  content: ""; display: inline-block; width: 18px; height: 18px; margin-right: 14px; border-radius: 50%;
  background: var(--tg-principal); vertical-align: 3px;
}
.tg-scrapbook.tg-etiqueta .tg-cos {
  font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-weight: 400; font-size: 66px; color: var(--tg-sobre-secundari);
  background: var(--tg-secundari); padding: 12px 30px 16px; border-radius: 3px; rotate: -4deg;
  box-shadow: 5px 6px 0 var(--tg-ombra-suau);
}
.tg-editorial.tg-etiqueta .tg-cos {
  font-size: 40px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.2em; color: var(--tg-text);
  padding-bottom: 14px; border-bottom: 3px solid var(--tg-destacat); text-shadow: 0 2px 14px var(--tg-ombra);
}

.tg-llista .tg-cos { width: 840px; font-family: var(--tg-f-text); color: var(--tg-fosc); text-align: left; }
.tg-llista h3 { margin: 0 0 18px; font-family: var(--tg-f-titols); font-size: 66px; font-weight: 700; line-height: 1.05; }
.tg-llista ol { list-style: none; margin: 0; padding: 0; }
.tg-llista li { position: relative; padding: 16px 0 16px 84px; font-size: 54px; line-height: 1.15; opacity: 0; }
.tg-llista li::before { position: absolute; left: 0; top: 18px; display: flex; align-items: center; justify-content: center; }
.tg-net.tg-llista .tg-cos { background: var(--tg-principal); color: var(--tg-sobre-principal); padding: 44px 50px 40px; border-radius: 30px; }
.tg-net.tg-llista li::before {
  content: attr(data-n); width: 58px; height: 58px; border-radius: 50%; font-size: 32px; font-weight: 800;
  background: var(--tg-sobre-principal); color: var(--tg-principal);
}
.tg-mac.tg-llista .tg-cos {
  background: var(--tg-clar); border-radius: 34px; padding-bottom: 28px; overflow: hidden;
  box-shadow: 0 34px 80px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-barra { display: flex; gap: 14px; align-items: center; height: 72px; padding: 0 30px; border-bottom: 1.5px solid var(--tg-linia); }
.tg-barra i { width: 22px; height: 22px; border-radius: 50%; background: var(--tg-linia-forta); }
.tg-mac.tg-llista h3 { margin: 30px 46px 4px; }
.tg-mac.tg-llista ol { padding: 14px 46px 0; }
.tg-mac.tg-llista li::before {
  content: "✓"; width: 56px; height: 56px; border-radius: 15px; font-size: 36px; font-weight: 700;
  background: var(--tg-principal); color: var(--tg-sobre-principal);
}
.tg-scrapbook.tg-llista .tg-cos {
  font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); background: var(--tg-clar); padding: 58px 52px 40px; border-radius: 4px;
  rotate: 1.5deg; box-shadow: 9px 11px 0 var(--tg-ombra-suau);
}
.tg-scrapbook.tg-llista .tg-cos::before { left: 70px; margin-left: 0; rotate: -6deg; }
.tg-scrapbook.tg-llista h3 { display: inline-block; font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-weight: 400; border-bottom: 5px solid var(--tg-sobre-paper); }
.tg-scrapbook.tg-llista li { font-size: 62px; }
.tg-scrapbook.tg-llista li::before { content: "✓"; top: 10px; width: 58px; font-size: 58px; color: var(--tg-principal); }
.tg-editorial.tg-llista .tg-cos { color: var(--tg-text); text-shadow: 0 2px 16px var(--tg-ombra); }
.tg-editorial.tg-llista h3 {
  font-family: var(--tg-f-text); font-size: 36px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.18em;
  padding-bottom: 16px; border-bottom: 2px solid var(--tg-text);
}
.tg-editorial.tg-llista li { padding-left: 112px; font-family: var(--tg-f-titols); font-size: 64px; border-bottom: 1.5px solid var(--tg-ratlla); }
.tg-editorial.tg-llista li::before {
  content: attr(data-n); top: 14px; font-family: var(--tg-f-accent); font-style: italic; font-size: 62px; color: var(--tg-destacat);
}

.tg-crida .tg-cos { font-family: var(--tg-f-text); font-size: 60px; font-weight: 800; line-height: 1.12; text-align: center; }
.tg-fletxa { font-style: normal; white-space: nowrap; }
.tg-net.tg-crida .tg-cos { background: var(--tg-principal); color: var(--tg-sobre-principal); padding: 28px 50px 32px; border-radius: 999px; }
.tg-net.tg-crida .tg-clau, .tg-net.tg-llista .tg-clau { color: inherit; }
.tg-mac.tg-crida .tg-cos {
  display: flex; align-items: center; gap: 30px; text-align: left; font-size: 56px; font-weight: 700;
  color: var(--tg-fosc); background: var(--tg-clar); padding: 26px 44px 26px 26px; border-radius: 38px;
  box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-icona {
  flex: none; display: flex; align-items: center; justify-content: center; width: 112px; height: 112px;
  border-radius: 30px; font-size: 62px; background: var(--tg-principal); color: var(--tg-sobre-principal);
}
.tg-scrapbook.tg-crida .tg-cos {
  font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-weight: 400; font-size: 74px; color: var(--tg-sobre-secundari);
  background: var(--tg-secundari); padding: 46px 50px 42px; border-radius: 4px; rotate: 2.5deg;
  box-shadow: 8px 10px 0 var(--tg-ombra-suau);
}
.tg-editorial.tg-crida .tg-cos {
  font-family: var(--tg-f-titols); font-weight: 400; font-size: 80px; color: var(--tg-text);
  padding-bottom: 12px; border-bottom: 6px solid var(--tg-destacat); text-shadow: 0 3px 18px var(--tg-ombra-suau);
}

.tg-notificacio .tg-cos {
  width: 840px; display: flex; gap: 26px; align-items: flex-start; padding: 28px 36px 30px 28px; text-align: left;
  font-family: var(--tg-f-text); color: var(--tg-fosc); background: var(--tg-clar); border-radius: 44px;
  box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-app {
  flex: none; display: flex; align-items: center; justify-content: center; width: 96px; height: 96px;
  border-radius: 24px; font-size: 50px; font-weight: 700; background: var(--tg-principal); color: var(--tg-sobre-principal);
}
.tg-notif-cos { flex: 1; min-width: 0; }
.tg-notif-cap { display: flex; align-items: baseline; gap: 16px; font-size: 40px; font-weight: 700; line-height: 1.15; }
.tg-notif-cap span:last-child { margin-left: auto; font-size: 32px; font-weight: 400; opacity: 0.55; }
.tg-notif-text { margin-top: 6px; font-size: 46px; line-height: 1.2; }
.tg-net.tg-notificacio .tg-cos { background: var(--tg-principal); color: var(--tg-sobre-principal); box-shadow: none; }
.tg-net.tg-notificacio .tg-app { background: var(--tg-sobre-principal); color: var(--tg-principal); }
.tg-scrapbook.tg-notificacio .tg-cos { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); border-radius: 4px; rotate: -1.5deg; box-shadow: 8px 10px 0 var(--tg-ombra-suau); }
.tg-editorial.tg-notificacio .tg-cos {
  color: var(--tg-text); background: none; box-shadow: none; border-radius: 0; padding: 26px 0;
  border-top: 3px solid var(--tg-text); border-bottom: 3px solid var(--tg-text); text-shadow: 0 2px 14px var(--tg-ombra);
}

/* El marcador: la part marcada, amb el color destacat al darrere i el text del color que s'hi llegeix. Es dibuixa
   d'esquerra a dreta (--tg-marcat) i, si ocupa dues línies, a cadascuna. */
.tg-marca {
  display: inline-block; color: var(--tg-sobre-destacat); text-shadow: none;
  padding: 0 0.2em; margin: 0 -0.17em; border-radius: 0.08em;  /* la franja tapa també l'espai entre paraules */
  background: linear-gradient(var(--tg-destacat), var(--tg-destacat)) no-repeat 0 55% / var(--tg-marcat, 100%) 80%;
}
.tg-editorial .tg-marca { color: inherit; background-size: var(--tg-marcat, 100%) 30%; background-position: 0 90%; }
.tg-scrapbook .tg-marca { border-radius: 0.3em 0.05em 0.35em 0.08em; }

/* El ratllat: el que es diu primer, que es ratlla, i a sota el que hi va, més gran. */
.tg-ratllat .tg-cos {
  display: flex; flex-direction: column; align-items: center; text-align: center;
  font-family: var(--tg-f-titols); font-weight: 700; color: var(--tg-text); letter-spacing: -0.01em;
}
.tg-rt-titol { font-size: 46px; font-weight: 600; line-height: 1.1; margin-bottom: 6px; opacity: 0.85; }
.tg-vell { position: relative; font-size: 86px; line-height: 1.06; }
.tg-ratlla {
  position: absolute; left: -5%; right: -5%; top: 54%; height: 13px; margin-top: -6px; border-radius: 7px;
  background: var(--tg-destacat); transform-origin: 0 50%; rotate: -3deg;
}
.tg-nou { font-size: 118px; line-height: 1.02; letter-spacing: -0.02em; color: var(--tg-destacat); }
.tg-net.tg-ratllat .tg-cos { text-shadow: 0 4px 22px var(--tg-ombra); }
.tg-mac.tg-ratllat .tg-cos, .tg-scrapbook.tg-ratllat .tg-cos { color: var(--tg-fosc); background: var(--tg-clar); text-shadow: none; }
.tg-mac.tg-ratllat .tg-cos {
  font-family: var(--tg-f-text); padding: 38px 64px 46px; border-radius: 44px;
  box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-scrapbook.tg-ratllat .tg-cos {
  font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-weight: 400; padding: 46px 64px 42px;
  border-radius: 6px; rotate: -2deg; box-shadow: 8px 10px 0 var(--tg-ombra-suau);
}
/* Sobre la targeta clara, la paraula nova va amb el marcador (vegeu .tg-marca), ja dibuixat. */
.tg-mac.tg-ratllat .tg-ratlla, .tg-scrapbook.tg-ratllat .tg-ratlla { background: var(--tg-principal); }
.tg-scrapbook.tg-ratllat .tg-ratlla { rotate: -7deg; height: 11px; }
.tg-editorial.tg-ratllat .tg-cos {
  font-weight: 400; padding: 28px 0 30px; border-top: 3px solid var(--tg-text); border-bottom: 3px solid var(--tg-text);
  text-shadow: 0 3px 18px var(--tg-ombra-suau);
}
.tg-editorial.tg-ratllat .tg-ratlla { height: 6px; margin-top: -3px; rotate: 0deg; border-radius: 0; background: var(--tg-text); }
.tg-editorial.tg-ratllat .tg-nou { font-family: var(--tg-f-accent); font-style: italic; font-weight: 400; }

/* El comentari: una targeta com les de sota dels vídeos (sense ser de cap xarxa): la inicial de qui l'ha escrit, el
   nom, un cor i el que diu. */
.tg-comentari .tg-cos {
  display: grid; grid-template-columns: auto 1fr auto; gap: 4px 24px; align-items: center; min-width: 560px;
  padding: 30px 38px 34px 30px; text-align: left; font-family: var(--tg-f-text); color: var(--tg-fosc);
  background: var(--tg-clar); border-radius: 44px; box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-avatar {
  grid-row: span 2; align-self: start; display: flex; align-items: center; justify-content: center; width: 92px; height: 92px;
  border-radius: 50%; font-style: normal; font-size: 46px; font-weight: 700; background: var(--tg-principal); color: var(--tg-sobre-principal);
}
.tg-com-qui { font-size: 38px; font-weight: 700; line-height: 1.15; opacity: 0.7; }
.tg-cor { grid-row: span 2; align-self: center; width: 52px; height: 52px; fill: none; stroke: currentColor; stroke-width: 2.2; opacity: 0.55; }
.tg-com-text { font-size: 52px; line-height: 1.18; }
.tg-net.tg-comentari .tg-cos { box-shadow: 0 18px 44px var(--tg-ombra-suau); }
.tg-net.tg-comentari .tg-cor { stroke: var(--tg-destacat); opacity: 1; }
.tg-scrapbook.tg-comentari .tg-cos { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); border-radius: 4px; rotate: -2deg; box-shadow: 8px 10px 0 var(--tg-ombra-suau); }
.tg-editorial.tg-comentari .tg-cos {
  color: var(--tg-text); background: none; box-shadow: none; border-radius: 0; padding: 26px 0;
  border-top: 3px solid var(--tg-text); border-bottom: 3px solid var(--tg-text); text-shadow: 0 2px 14px var(--tg-ombra);
}
.tg-editorial.tg-comentari .tg-avatar { background: none; color: var(--tg-text); border: 3px solid var(--tg-text); }

.tg-xat .tg-cos { width: 840px; display: flex; flex-direction: column; gap: 14px; font-family: var(--tg-f-text); }
.tg-xat-qui {
  align-self: center; display: flex; align-items: center; gap: 14px; margin-bottom: 6px; padding: 10px 28px 10px 10px;
  border-radius: 999px; font-size: 34px; font-weight: 600; background: var(--tg-clar); color: var(--tg-fosc);
  box-shadow: 0 10px 30px var(--tg-ombra-suau);
}
.tg-xat-qui i {
  display: flex; align-items: center; justify-content: center; width: 54px; height: 54px; border-radius: 50%;
  font-style: normal; font-size: 28px; font-weight: 700; background: var(--tg-principal); color: var(--tg-sobre-principal);
}
.tg-fila-xat { position: relative; display: flex; }
.tg-fila-xat.tg-enviat { justify-content: flex-end; }
.tg-bombolla {
  max-width: 680px; padding: 24px 34px 26px; border-radius: 46px; font-size: 50px; line-height: 1.2; opacity: 0;
  background: var(--tg-clar); color: var(--tg-fosc); box-shadow: 0 12px 34px var(--tg-ombra-suau);
  border-bottom-left-radius: 12px; transform-origin: 0% 100%;
}
.tg-enviat .tg-bombolla {
  background: var(--tg-principal); color: var(--tg-sobre-principal);
  border-bottom-left-radius: 46px; border-bottom-right-radius: 12px; transform-origin: 100% 100%;
}
.tg-enviat .tg-clau, .tg-net.tg-notificacio .tg-clau { color: inherit; }
.tg-escriu {
  position: absolute; left: 0; top: 0; display: flex; gap: 10px; padding: 30px 32px; border-radius: 44px;
  border-bottom-left-radius: 12px; background: var(--tg-clar); opacity: 0;
}
.tg-escriu i { width: 18px; height: 18px; border-radius: 50%; background: var(--tg-linia-forta); }
.tg-net.tg-xat .tg-rebut .tg-bombolla, .tg-net.tg-xat .tg-escriu { background: var(--tg-secundari); color: var(--tg-sobre-secundari); }
.tg-net.tg-xat .tg-bombolla { box-shadow: none; }
.tg-scrapbook.tg-xat .tg-bombolla { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); border-radius: 6px; box-shadow: 5px 6px 0 var(--tg-ombra-suau); }
.tg-editorial.tg-xat .tg-bombolla {
  color: var(--tg-text); background: var(--tg-vel); box-shadow: none; border: 2.5px solid var(--tg-text);
}
.tg-editorial.tg-xat .tg-enviat .tg-bombolla { color: var(--tg-destacat); border-color: var(--tg-destacat); }

.tg-numero .tg-cos { text-align: center; color: var(--tg-text); font-family: var(--tg-f-titols); }
.tg-xifra {
  display: block; font-size: 220px; font-weight: 800; line-height: 0.95; letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums; white-space: nowrap; text-shadow: 0 6px 30px var(--tg-ombra);
}
.tg-xifra-text {
  display: block; margin-top: 14px; font-family: var(--tg-f-text); font-size: 46px; font-weight: 600; line-height: 1.15;
  text-shadow: 0 3px 16px var(--tg-ombra);
}
.tg-net.tg-numero .tg-xifra { color: var(--tg-destacat); }
.tg-mac.tg-numero .tg-cos {
  padding: 40px 56px 44px; border-radius: 44px; color: var(--tg-fosc); background: var(--tg-clar);
  box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-mac.tg-numero .tg-xifra { font-size: 180px; color: var(--tg-principal); text-shadow: none; }
.tg-mac.tg-numero .tg-xifra-text { text-shadow: none; }
.tg-scrapbook.tg-numero .tg-xifra { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-weight: 400; rotate: -3deg; }
.tg-scrapbook.tg-numero .tg-xifra-text { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-weight: 400; }
.tg-editorial.tg-numero .tg-xifra { font-weight: 400; font-size: 250px; }
.tg-editorial.tg-numero .tg-xifra-text {
  display: inline-block; padding-top: 18px; font-size: 34px; text-transform: uppercase; letter-spacing: 0.16em;
  border-top: 3px solid var(--tg-text);
}

/* El progrés: el número que compta, dins d'un cercle o damunt d'una barra que s'omple fins a la part que diu. */
.tg-anell { position: relative; width: 430px; height: 430px; margin: 0 auto; }
.tg-anell svg { position: absolute; inset: 0; width: 100%; height: 100%; rotate: -90deg; overflow: visible; }
.tg-anell circle { fill: none; stroke-width: 11; }
.tg-pista { stroke: var(--tg-ratlla); }
.tg-arc { stroke: var(--tg-destacat); stroke-linecap: round; stroke-dasharray: 1; }
/* Dins del cercle, una xifra llarga («3 de cada 4», «10.000 €») es fa més petita i no en surt (--tg-lletres). */
.tg-anell .tg-xifra {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; white-space: nowrap;
  font-size: min(118px, calc(570px / var(--tg-lletres, 4)));
}
.tg-progres .tg-cos { min-width: 600px; }
.tg-barra-prog { position: relative; height: 46px; margin-top: 26px; border-radius: 23px; overflow: hidden; background: var(--tg-ratlla); }
.tg-barra-prog i { position: absolute; inset: 0; border-radius: inherit; background: var(--tg-destacat); transform-origin: 0 50%; }
.tg-progres .tg-barra-prog + .tg-xifra-text { margin-top: 22px; }
.tg-mac.tg-numero .tg-anell .tg-xifra { font-size: min(104px, calc(570px / var(--tg-lletres, 4))); }
.tg-mac.tg-progres .tg-pista, .tg-scrapbook.tg-progres .tg-pista { stroke: var(--tg-linia-forta); }
.tg-mac.tg-progres .tg-barra-prog, .tg-scrapbook.tg-progres .tg-barra-prog { background: var(--tg-linia-forta); }
.tg-mac.tg-progres .tg-arc, .tg-scrapbook.tg-progres .tg-arc { stroke: var(--tg-principal); }
.tg-mac.tg-progres .tg-xifra { color: var(--tg-fosc); }  /* el color ja el porta el cercle o la barra */
.tg-mac.tg-progres .tg-barra-prog i, .tg-scrapbook.tg-progres .tg-barra-prog i { background: var(--tg-principal); }
.tg-scrapbook.tg-progres .tg-cos {
  padding: 46px 56px 42px; color: var(--tg-fosc); background: var(--tg-clar); border-radius: 6px; rotate: -2deg;
  box-shadow: 8px 10px 0 var(--tg-ombra-suau);
}
.tg-scrapbook.tg-progres .tg-xifra, .tg-scrapbook.tg-progres .tg-xifra-text { text-shadow: none; }
.tg-scrapbook.tg-progres .tg-barra-prog { border-radius: 6px; rotate: -1deg; }
.tg-editorial.tg-progres .tg-anell circle { stroke-width: 4; }
.tg-editorial.tg-progres .tg-arc { stroke: var(--tg-text); stroke-linecap: butt; }
.tg-editorial.tg-progres .tg-anell .tg-xifra { font-size: min(140px, calc(640px / var(--tg-lletres, 4))); }
.tg-editorial.tg-progres .tg-barra-prog { height: 10px; border-radius: 0; }
.tg-editorial.tg-progres .tg-barra-prog i { background: var(--tg-text); }
.tg-editorial.tg-progres .tg-barra-prog + .tg-xifra-text { border-top: 0; padding-top: 0; }  /* la barra ja fa de ratlla */

.tg-lloc.tg-anotacio { justify-content: flex-start; }
.tg-lloc.tg-anotacio.tg-a-dreta { justify-content: flex-end; }
.tg-anotacio .tg-cos {
  max-width: 560px; padding: 24px 34px; font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-size: 74px; line-height: 1.05;
  color: var(--tg-tinta); filter: drop-shadow(0 1px 2px var(--tg-ombra-forta)) drop-shadow(0 0 12px var(--tg-ombra));
}
.tg-a-dreta .tg-cos { text-align: right; }
.tg-nota { display: inline-block; }
.tg-traca { position: absolute; left: 0; top: 0; width: 1px; height: 1px; overflow: visible; }
.tg-traca path {
  fill: none; stroke: var(--tg-tinta); stroke-width: 7; stroke-linecap: round; stroke-linejoin: round;
  stroke-dasharray: 1; stroke-dashoffset: 0;
}

/* La web: una finestra de navegador amb la captura, que baixa a poc a poc si és llarga. */
.tg-web .tg-cos {
  --tg-rf: 26px; width: 840px; border-radius: var(--tg-rf); background: var(--tg-clar);
  box-shadow: 0 34px 80px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-adreca {
  flex: 1; min-width: 0; margin-left: 14px; padding: 0 24px; height: 46px; line-height: 46px; border-radius: 999px;
  background: var(--tg-linia); color: var(--tg-fosc); font-family: var(--tg-f-text); font-size: 26px; text-align: center;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.tg-pantalla { position: relative; height: 460px; overflow: hidden; background: #FFFFFF; border-radius: 0 0 var(--tg-rf) var(--tg-rf); }
.tg-pantalla img { display: block; width: 100%; height: 100%; object-fit: cover; object-position: 50% 0%; }
.tg-falta {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: 30px;
  font-family: var(--tg-f-text); font-size: 44px; font-weight: 600; text-align: center; color: var(--tg-fosc);
  background: repeating-linear-gradient(-45deg, var(--tg-linia) 0 22px, transparent 22px 44px);
}
.tg-mac.tg-web .tg-barra i:nth-child(1) { background: #FF5F57; }
.tg-mac.tg-web .tg-barra i:nth-child(2) { background: #FEBC2E; }
.tg-mac.tg-web .tg-barra i:nth-child(3) { background: #28C840; }
.tg-net.tg-web .tg-cos { --tg-rf: 22px; box-shadow: 0 26px 60px var(--tg-ombra); }
.tg-net.tg-web .tg-barra { background: var(--tg-principal); border-bottom: 0; border-radius: var(--tg-rf) var(--tg-rf) 0 0; }
.tg-net.tg-web .tg-barra i { background: var(--tg-sobre-principal); opacity: 0.45; }
.tg-net.tg-web .tg-adreca { background: var(--tg-sobre-principal); color: var(--tg-principal); }
.tg-scrapbook.tg-web .tg-cos { --tg-rf: 3px; padding: 14px 14px 18px; rotate: -1.5deg; box-shadow: 8px 10px 0 var(--tg-ombra-suau); }
.tg-scrapbook.tg-web .tg-adreca { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-size: 32px; background: none; }
.tg-editorial.tg-web .tg-cos { --tg-rf: 0px; background: var(--tg-vel); box-shadow: none; border: 3px solid var(--tg-text); }
.tg-editorial.tg-web .tg-barra { height: 64px; border-bottom: 3px solid var(--tg-text); }
.tg-editorial.tg-web .tg-barra i { display: none; }
.tg-editorial.tg-web .tg-adreca {
  margin: 0; background: none; color: var(--tg-text); font-size: 24px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.16em; text-shadow: 0 2px 10px var(--tg-ombra);
}

/* El ventall: les fotos obertes com cartes, que surten una a una. */
.tg-ventall .tg-cos { width: 840px; text-align: center; }
.tg-ventall h3 {
  margin: 0 0 10px; font-family: var(--tg-f-titols); font-size: 64px; font-weight: 700; line-height: 1.05;
  color: var(--tg-text); text-shadow: 0 3px 18px var(--tg-ombra);
}
.tg-ventall h3 .tg-clau { color: var(--tg-destacat); }  /* el títol va damunt del fons, no d'una targeta */
.tg-cartes { position: relative; height: 540px; }
.tg-carta {
  position: absolute; left: 50%; top: 40px; width: 300px; margin: 0 0 0 -150px; box-sizing: border-box; padding: 14px;
  border-radius: 24px; background: var(--tg-clar); box-shadow: 0 26px 60px var(--tg-ombra-suau); opacity: 0;
  transform-origin: 50% 90%;
}
.tg-carta.tg-buida { opacity: 1; }
.tg-carta img, .tg-falta-foto { display: block; width: 100%; aspect-ratio: 4 / 5; object-fit: cover; border-radius: 12px; }
.tg-falta-foto { background: repeating-linear-gradient(-45deg, var(--tg-linia) 0 22px, transparent 22px 44px); }
/* El peu, a l'esquerra: la foto següent tapa la dreta de l'anterior. */
.tg-carta figcaption {
  margin-top: 12px; padding-left: 4px; font-family: var(--tg-f-text); font-size: 32px; font-weight: 600; line-height: 1.1;
  color: var(--tg-fosc); text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.tg-mac.tg-ventall .tg-carta { padding: 0; border-radius: 30px; overflow: hidden; box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia); }
.tg-mac.tg-ventall .tg-carta img, .tg-mac.tg-ventall .tg-falta-foto { border-radius: 0; }
.tg-mac.tg-ventall figcaption { margin: 0; padding: 18px 24px 22px; }
.tg-scrapbook.tg-ventall h3 { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-weight: 400; }
.tg-scrapbook.tg-ventall .tg-carta { padding: 16px 16px 22px; border-radius: 3px; box-shadow: 6px 8px 0 var(--tg-ombra-suau); }
.tg-scrapbook.tg-ventall .tg-carta::before {
  content: ""; position: absolute; left: 50%; top: -20px; width: 150px; height: 40px; margin-left: -75px;
  background: var(--tg-cinta); rotate: -4deg;
}
.tg-scrapbook.tg-ventall .tg-carta img, .tg-scrapbook.tg-ventall .tg-falta-foto { border-radius: 0; }
.tg-scrapbook.tg-ventall figcaption { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-weight: 400; font-size: 42px; }
.tg-editorial.tg-ventall h3 { font-weight: 400; letter-spacing: -0.02em; }
.tg-editorial.tg-ventall .tg-carta { padding: 0; border-radius: 0; background: none; box-shadow: 0 20px 50px var(--tg-ombra-suau); }
.tg-editorial.tg-ventall .tg-carta img, .tg-editorial.tg-ventall .tg-falta-foto { border-radius: 0; border: 3px solid var(--tg-text); box-sizing: border-box; }
.tg-editorial.tg-ventall figcaption {
  font-size: 24px; text-transform: uppercase; letter-spacing: 0.16em; color: var(--tg-text); text-shadow: 0 2px 10px var(--tg-ombra);
}
/* La publicació citada: una targeta de post (sense ser de cap xarxa): qui l'ha escrit, què diu i les icones de sota. */
.tg-publicacio .tg-cos {
  width: 840px; padding: 40px 46px 34px; text-align: left; font-family: var(--tg-f-text); color: var(--tg-fosc);
  background: var(--tg-clar); border-radius: 40px; box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-pub-cap { display: flex; align-items: center; gap: 22px; margin-bottom: 22px; }
.tg-pub-cap .tg-avatar { grid-row: auto; width: 84px; height: 84px; font-size: 40px; }
.tg-pub-nom { font-size: 40px; font-weight: 700; }
.tg-pub-text { font-size: 52px; line-height: 1.24; }
.tg-pub-peu { display: flex; gap: 70px; margin-top: 28px; opacity: 0.5; }
.tg-pub-peu svg { width: 46px; height: 46px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.tg-net.tg-publicacio .tg-cos { box-shadow: 0 18px 44px var(--tg-ombra-suau); }
.tg-scrapbook.tg-publicacio .tg-cos { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); border-radius: 4px; rotate: -1.5deg; box-shadow: 8px 10px 0 var(--tg-ombra-suau); }
.tg-editorial.tg-publicacio .tg-cos {
  color: var(--tg-text); background: none; box-shadow: none; border-radius: 0; padding: 30px 0 26px;
  border-top: 3px solid var(--tg-text); border-bottom: 3px solid var(--tg-text); text-shadow: 0 2px 14px var(--tg-ombra);
}
.tg-editorial.tg-publicacio .tg-avatar { background: none; color: var(--tg-text); border: 3px solid var(--tg-text); }
.tg-editorial.tg-publicacio .tg-pub-text { font-family: var(--tg-f-titols); font-size: 60px; }

/* Les notes del mòbil: una nota que s'escriu sola, línia a línia, amb el cursor on s'escriu. */
.tg-notes .tg-cos {
  width: 840px; overflow: hidden; text-align: left; font-family: var(--tg-f-text); color: var(--tg-fosc);
  background: var(--tg-clar); border-radius: 40px; box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-notes-barra {
  display: flex; justify-content: space-between; padding: 26px 40px 18px; font-size: 36px; font-weight: 600;
  color: var(--tg-principal); border-bottom: 1.5px solid var(--tg-linia);
}
.tg-notes-full { padding: 24px 44px 40px; }
.tg-notes-full h3 { margin: 0 0 14px; font-size: 56px; font-weight: 800; line-height: 1.1; }
.tg-linia-nota { position: relative; margin: 0; min-height: 1.3em; font-size: 46px; line-height: 1.3; }
.tg-escrit-ple { visibility: hidden; }  /* el lloc del text sencer: la nota no canvia de mida mentre s'escriu */
.tg-escrit-viu { position: absolute; left: 0; top: 0; right: 0; }
.tg-cursor { display: inline-block; width: 4px; height: 1.05em; margin-left: 3px; vertical-align: -0.15em; background: var(--tg-principal); opacity: 0; }
.tg-net.tg-notes .tg-cos { box-shadow: 0 18px 44px var(--tg-ombra-suau); }
.tg-scrapbook.tg-notes .tg-cos { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); border-radius: 4px; rotate: -1.5deg; box-shadow: 8px 10px 0 var(--tg-ombra-suau);
  background: repeating-linear-gradient(transparent 0 58px, var(--tg-linia) 58px 60px), var(--tg-clar); }
.tg-editorial.tg-notes .tg-cos { color: var(--tg-text); background: var(--tg-vel); box-shadow: none; border-radius: 0; border: 3px solid var(--tg-text); }
.tg-editorial.tg-notes .tg-notes-barra { color: var(--tg-text); border-bottom-color: var(--tg-text); text-transform: uppercase; letter-spacing: 0.12em; font-size: 28px; }

/* «Segueix-me»: la targeta del compte i un botó que es prem sol (un dit el toca i passa a «Seguint»). */
.tg-segueix .tg-cos {
  position: relative; width: 840px; display: flex; align-items: center; gap: 26px; padding: 30px 32px 30px 30px;
  text-align: left; font-family: var(--tg-f-text); color: var(--tg-fosc); background: var(--tg-clar); border-radius: 999px;
  box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia);
}
.tg-segueix .tg-avatar { grid-row: auto; flex: none; width: 110px; height: 110px; font-size: 54px; }
.tg-seg-dades { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.tg-seg-dades b { font-size: 44px; line-height: 1.1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tg-seg-dades span { font-size: 32px; line-height: 1.2; opacity: 0.65; }
.tg-seg-boto { position: relative; flex: none; display: grid; }
.tg-seg-boto > span {
  grid-area: 1 / 1; padding: 22px 40px; border-radius: 999px; font-size: 38px; font-weight: 700; text-align: center; white-space: nowrap;
}
.tg-seg-a { background: var(--tg-principal); color: var(--tg-sobre-principal); }
.tg-seg-b { background: var(--tg-linia); color: var(--tg-fosc); opacity: 0; }
.tg-dit {
  position: absolute; left: 50%; top: 50%; width: 90px; height: 90px; margin: -45px 0 0 -45px; border-radius: 50%;
  background: rgba(255, 255, 255, 0.55); box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.12); opacity: 0; pointer-events: none;
}
.tg-net.tg-segueix .tg-cos { box-shadow: 0 18px 44px var(--tg-ombra-suau); }
.tg-scrapbook.tg-segueix .tg-cos { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); border-radius: 6px; rotate: -1.5deg; box-shadow: 8px 10px 0 var(--tg-ombra-suau); }
.tg-editorial.tg-segueix .tg-cos {
  color: var(--tg-text); background: none; box-shadow: none; border-radius: 0; padding: 26px 0;
  border-top: 3px solid var(--tg-text); border-bottom: 3px solid var(--tg-text); text-shadow: 0 2px 14px var(--tg-ombra);
}
.tg-editorial.tg-segueix .tg-avatar { background: none; color: var(--tg-text); border: 3px solid var(--tg-text); }
.tg-editorial.tg-segueix .tg-seg-a { border-radius: 0; }
.tg-editorial.tg-segueix .tg-seg-b { border-radius: 0; color: var(--tg-text); background: none; border: 3px solid var(--tg-text); }

/* El REC: el marc d'una càmera que grava, a tota la zona segura (l'alçada la posa cos()). */
.tg-rec .tg-cos { width: 840px; box-sizing: border-box; color: var(--tg-text); font-family: ui-monospace, "SF Mono", Menlo, monospace; text-shadow: 0 2px 10px var(--tg-ombra); }
.tg-rec-cant { position: absolute; width: calc(80px * var(--tg-rec-k, 1)); height: calc(80px * var(--tg-rec-k, 1)); border: 0 solid currentColor; filter: drop-shadow(0 2px 6px var(--tg-ombra)); }
.tg-rec-cant:nth-of-type(1) { left: 0; top: 0; border-width: 7px 0 0 7px; }
.tg-rec-cant:nth-of-type(2) { right: 0; top: 0; border-width: 7px 7px 0 0; }
.tg-rec-cant:nth-of-type(3) { left: 0; bottom: 0; border-width: 0 0 7px 7px; }
.tg-rec-cant:nth-of-type(4) { right: 0; bottom: 0; border-width: 0 7px 7px 0; }
.tg-rec-dalt, .tg-rec-baix { position: absolute; left: 44px; right: 44px; display: flex; justify-content: space-between; align-items: center;
  font-size: calc(46px * var(--tg-rec-k, 1)); font-weight: 600; letter-spacing: 0.04em; }
.tg-rec-dalt { top: calc(40px * var(--tg-rec-k, 1)); } .tg-rec-baix { bottom: calc(40px * var(--tg-rec-k, 1)); }
.tg-rec-punt { display: inline-block; width: 30px; height: 30px; margin-right: 16px; border-radius: 50%; background: #FF3B30; vertical-align: 2px; }
.tg-rec-bat { display: inline-block; position: relative; width: 74px; height: 36px; border: 4px solid currentColor; border-radius: 8px; box-sizing: border-box; }
.tg-rec-bat::before { content: ""; position: absolute; left: 4px; top: 4px; bottom: 4px; width: 62%; border-radius: 3px; background: currentColor; }
.tg-rec-bat::after { content: ""; position: absolute; right: -11px; top: 8px; width: 6px; height: 12px; border-radius: 0 3px 3px 0; background: currentColor; }
.tg-mac.tg-rec .tg-rec-cant { border-radius: 26px; }
.tg-scrapbook.tg-rec .tg-cos { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); }
.tg-scrapbook.tg-rec .tg-rec-cant { border-radius: 6px; rotate: -2deg; }
.tg-editorial.tg-rec .tg-rec-cant { width: 60px; height: 60px; border-width: 3px; }
.tg-editorial.tg-rec .tg-rec-cant:nth-of-type(1) { border-width: 3px 0 0 3px; } .tg-editorial.tg-rec .tg-rec-cant:nth-of-type(2) { border-width: 3px 3px 0 0; }
.tg-editorial.tg-rec .tg-rec-cant:nth-of-type(3) { border-width: 0 0 3px 3px; } .tg-editorial.tg-rec .tg-rec-cant:nth-of-type(4) { border-width: 0 3px 3px 0; }
.tg-editorial.tg-rec .tg-rec-dalt, .tg-editorial.tg-rec .tg-rec-baix { font-size: 34px; letter-spacing: 0.16em; }

/* Abans i després: les dues fotos, una damunt de l'altra; una ratlla s'hi mou i descobreix el després. */
.tg-abans .tg-cos, .tg-carrusel .tg-cos { width: 840px; text-align: center; }
.tg-abans h3, .tg-carrusel h3 {
  margin: 0 0 18px; font-family: var(--tg-f-titols); font-size: 64px; font-weight: 700; line-height: 1.05;
  color: var(--tg-text); text-shadow: 0 3px 18px var(--tg-ombra);
}
.tg-abans h3 .tg-clau, .tg-carrusel h3 .tg-clau { color: var(--tg-destacat); }
.tg-comparacio { --tg-tall: 50%; position: relative; height: 760px; overflow: hidden; border-radius: 30px; background: var(--tg-vel);
  box-shadow: 0 30px 70px var(--tg-ombra-suau); }
.tg-ab { position: absolute; inset: 0; margin: 0; }
.tg-ab img, .tg-ab .tg-falta-foto { width: 100%; height: 100%; aspect-ratio: auto; object-fit: cover; border-radius: 0; }
.tg-ab-despres { clip-path: inset(0 0 0 var(--tg-tall)); }
.tg-ab figcaption {
  position: absolute; bottom: 26px; padding: 10px 22px; border-radius: 999px; font-family: var(--tg-f-text); font-size: 34px;
  font-weight: 700; background: var(--tg-clar); color: var(--tg-fosc);
}
.tg-ab-abans figcaption { left: 26px; } .tg-ab-despres figcaption { right: 26px; }
.tg-ab-linia { position: absolute; top: 0; bottom: 0; left: var(--tg-tall); width: 8px; margin-left: -4px; background: var(--tg-clar);
  box-shadow: 0 0 18px var(--tg-ombra); }
.tg-ab-linia::after { content: ""; position: absolute; left: 50%; top: 50%; width: 66px; height: 66px; margin: -33px 0 0 -33px;
  border-radius: 50%; background: var(--tg-clar); box-shadow: 0 4px 16px var(--tg-ombra); }
.tg-mac.tg-abans .tg-comparacio { box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia); }
.tg-scrapbook.tg-abans .tg-comparacio { border-radius: 4px; rotate: -1.5deg; border: 16px solid var(--tg-clar); box-shadow: 8px 10px 0 var(--tg-ombra-suau); }
.tg-scrapbook.tg-abans figcaption, .tg-scrapbook.tg-abans h3, .tg-scrapbook.tg-carrusel h3 { font-family: var(--tg-f-ma); text-transform: var(--tg-ma-majuscules); font-weight: 400; }
.tg-editorial.tg-abans .tg-comparacio { border-radius: 0; border: 3px solid var(--tg-text); }
.tg-editorial.tg-abans figcaption { border-radius: 0; font-size: 26px; text-transform: uppercase; letter-spacing: 0.16em; }
.tg-editorial.tg-abans .tg-ab-linia { width: 4px; margin-left: -2px; }
.tg-editorial.tg-abans .tg-ab-linia::after { display: none; }

/* El carrusel: les fotos giren en roda; les del davant, més grans i més clares (les posa rodaCarrusel). */
.tg-roda { position: relative; height: 640px; }
.tg-carta-roda {
  position: absolute; left: 50%; top: 50%; width: 420px; margin: -262px 0 0 -210px; box-sizing: border-box; padding: 12px;
  border-radius: 26px; background: var(--tg-clar); box-shadow: 0 24px 60px var(--tg-ombra-suau);
}
.tg-carta-roda img, .tg-carta-roda .tg-falta-foto { display: block; width: 100%; aspect-ratio: 4 / 5; object-fit: cover; border-radius: 16px; }
.tg-mac.tg-carrusel .tg-carta-roda { padding: 0; overflow: hidden; box-shadow: 0 30px 70px var(--tg-ombra-suau), 0 0 0 1.5px var(--tg-linia); }
.tg-mac.tg-carrusel .tg-carta-roda img { border-radius: 0; }
.tg-scrapbook.tg-carrusel .tg-carta-roda { padding: 14px 14px 40px; border-radius: 3px; box-shadow: 6px 8px 0 var(--tg-ombra-suau); }
.tg-scrapbook.tg-carrusel .tg-carta-roda img { border-radius: 0; }
.tg-editorial.tg-carrusel .tg-carta-roda { padding: 0; border-radius: 0; background: none; border: 3px solid var(--tg-text); }
.tg-editorial.tg-carrusel .tg-carta-roda img { border-radius: 0; }`;

  const { rgba, familiaDe } = global.TallatSubtitols;

  function posaCss(doc) {
    if (doc.getElementById("tallat-grafics-css")) return;
    const s = doc.createElement("style");
    s.id = "tallat-grafics-css";
    s.textContent = ESTILS_CSS;
    doc.head.append(s);
  }

  function lluminositat(hex) {
    const n = parseInt(String(hex || "#000000").slice(1), 16) || 0;
    return 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255);
  }

  // El text damunt d'un color de la marca: el clar o el fosc de la marca, el que es llegeixi millor.
  const distancia = (a, b) => Math.abs(lluminositat(a) - lluminositat(b));
  const sobre = (color, p) => (distancia(color, p.fosc) > distancia(color, p.clar) ? p.fosc : p.clar);
  // El que es dibuixa damunt del paper (el clar): la cinta i els subratllats. El secundari, si s'hi veu;
  // si no (un blau cel damunt d'un crema), el principal.
  const sobrePaper = (p) => (distancia(p.secundari, p.clar) >= 60 ? p.secundari : p.principal);

  function variables(p) {
    return {
      "--tg-text": p.text, "--tg-principal": p.principal, "--tg-destacat": p.destacat,
      "--tg-secundari": p.secundari, "--tg-clar": p.clar, "--tg-fosc": p.fosc,
      "--tg-sobre-principal": sobre(p.principal, p), "--tg-sobre-secundari": sobre(p.secundari, p),
      "--tg-sobre-destacat": sobre(p.destacat, p),
      "--tg-ombra": rgba(p.fosc, 0.45), "--tg-ombra-suau": rgba(p.fosc, 0.28), "--tg-ombra-forta": rgba(p.fosc, 0.8),
      "--tg-vel": rgba(p.fosc, 0.42),
      "--tg-linia": rgba(p.fosc, 0.1), "--tg-linia-forta": rgba(p.fosc, 0.2),
      "--tg-cinta": rgba(sobrePaper(p), 0.72), "--tg-sobre-paper": sobrePaper(p), "--tg-ratlla": rgba(p.text, 0.45),
      "--tg-tinta": p.secundari,
      "--tg-f-titols": familiaDe(p.lletra_titols) || "system-ui, sans-serif",
      "--tg-f-text": familiaDe(p.lletra_text) || "system-ui, sans-serif",
      "--tg-f-accent": familiaDe(p.lletra_accent) || "system-ui, sans-serif",
      "--tg-f-ma": familiaDe(p.lletra_ma || p.lletra_accent) || "system-ui, sans-serif",
      "--tg-ma-majuscules": p.majuscules_ma ? "uppercase" : "none",  // n'hi ha que només van en majúscules
    };
  }

  function element(doc, etiqueta, classe, text) {
    const el = doc.createElement(etiqueta);
    if (classe) el.className = classe;
    if (text != null) el.textContent = text;
    return el;
  }

  // «no és *mandra*» → text normal i, entre asteriscs, la part destacada.
  function ambDestacat(doc, pare, text) {
    String(text || "").split("*").forEach((tros, k) => {
      if (tros) pare.append(k % 2 ? element(doc, "span", "tg-clau", tros) : doc.createTextNode(tros));
    });
  }

  // El marcador, paraula a paraula: cada paraula és una caixa de l'alçada de la línia (no de la lletra, que n'hi ha
  // amb molt d'aire a dalt i a baix), i així la franja és igual amb totes les lletres i no tapa la línia del costat.
  function ambMarcador(doc, pare, text) {
    const t = String(text || "");
    if (/^\s/.test(t)) pare.append(doc.createTextNode(" "));
    t.split(/\s+/).filter(Boolean).forEach((mot, k) => {
      if (k) pare.append(doc.createTextNode(" "));
      pare.append(element(doc, "span", "tg-marca", mot));
    });
    if (/\s$/.test(t)) pare.append(doc.createTextNode(" "));
  }

  const inicial = (text) => (String(text || "").trim()[0] || "✉").toUpperCase();

  // La xifra al moment `v` del compte: «10.000 €», «2,5 h» (com s'escriu en català).
  function formata(x, v) {
    if (!x) return "";
    let [enter, dec] = Number(v).toFixed(x.decimals || 0).split(".");
    if (x.milers || enter.length > 4) enter = enter.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return `${x.abans || ""}${enter}${dec ? `,${dec}` : ""}${x.despres || ""}`;
  }

  // Les fotos del ventall, obertes: girades i esteses, les de les puntes una mica més avall.
  function obreVentall(cartes, g) {
    const n = cartes.length;
    const mig = (n - 1) / 2;
    const angle = n > 1 ? Math.min(12, 30 / (n - 1)) : 0;
    const pas = n > 1 ? Math.min(230, 540 / (n - 1)) : 0;
    cartes.forEach((carta, k) => {
      const d = k - mig;
      const tremolor = g.estil === "scrapbook" ? (atzar(g.id || g.text, k + 1) - 0.5) * 6 : 0;
      carta.style.left = `calc(50% + ${(d * pas).toFixed(1)}px)`;
      carta.style.top = `${(40 + Math.abs(d) * 22).toFixed(1)}px`;
      carta.style.rotate = `${(d * angle + tremolor).toFixed(2)}deg`;
    });
  }

  // Una icona de traç (les de sota de la publicació), en un quadrat de 24.
  function icona(doc, d) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = doc.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    const cami = doc.createElementNS(NS, "path");
    cami.setAttribute("d", d);
    svg.append(cami);
    return svg;
  }
  const COR = "M12 20.5S3.5 15.4 3.5 9.3A4.6 4.6 0 0 1 12 6.9a4.6 4.6 0 0 1 8.5 2.4c0 6.1-8.5 11.2-8.5 11.2z";
  const ICONES_PUBLICACIO = ["M4 5.5h16v10H9l-5 4z", "M7 7h11l-3-3M17 17H6l3 3M18 7v5M6 17v-5", COR];

  // Les fotos del carrusel en roda, girada `angle` (radiants): les del davant, més grans, més clares i a sobre.
  function rodaCarrusel(cartes, angle) {
    const n = cartes.length;
    const mida = Number(cartes[0]?.parentElement?.dataset.mida || 1);  // com de gran és la roda (l'espai que té)
    cartes.forEach((carta, k) => {
      const a = angle + (k * 2 * Math.PI) / n;
      const davant = (Math.cos(a) + 1) / 2;  // 1, al davant; 0, al darrere
      const radi = Math.max(120, 420 - 0.79 * 210 * mida - 10);  // la foto del costat, sencera dins dels 840 px
      carta.style.transform = `translateX(${(Math.sin(a) * radi).toFixed(1)}px) translateY(${((1 - davant) * -40 * mida).toFixed(1)}px) ` +
        `scale(${((0.58 + 0.42 * davant) * mida).toFixed(3)})`;
      carta.style.opacity = (0.5 + 0.5 * davant).toFixed(3);
      carta.style.zIndex = String(Math.round(davant * 100));
    });
  }

  // Quan s'escriu cada línia de les notes, i quant triga (com si s'escrivís de debò).
  const durEscriu = (text) => Math.min(1.4, 0.15 + String(text || "").length * 0.045);

  function cos(doc, g, op) {
    const imatge = (nom) => (op.imatges ?? "imatges/") + encodeURIComponent(nom);
    const c = element(doc, "div", "tg-cos");
    if (g.tipus === "frase" || g.tipus === "marcador") {
      const n = String(g.text || "").length;
      c.dataset.escala = n > 90 ? 0.74 : n > 55 ? 0.86 : 1;
      c.style.setProperty("--tg-escala", c.dataset.escala);
      if (g.tipus === "frase") ambDestacat(doc, c, g.text);
      else {  // la part *entre asteriscs* (o tota la frase) porta el marcador
        const trossos = String(g.text || "").split("*");
        trossos.forEach((tros, k) => {
          if (k % 2 || trossos.length < 3) ambMarcador(doc, c, tros); else if (tros) c.append(doc.createTextNode(tros));
        });
      }
    } else if (g.tipus === "etiqueta") {
      c.textContent = g.text;
    } else if (g.tipus === "llista") {
      if (g.estil === "mac") {
        const barra = element(doc, "div", "tg-barra");
        barra.append(element(doc, "i"), element(doc, "i"), element(doc, "i"));
        c.append(barra);
      }
      if (g.text) { const h = element(doc, "h3"); ambDestacat(doc, h, g.text); c.append(h); }
      const ol = element(doc, "ol");
      (g.punts || []).forEach((p, k) => {
        const li = element(doc, "li", null, p.text);
        li.dataset.n = g.estil === "editorial" ? String(k + 1).padStart(2, "0") : String(k + 1);
        ol.append(li);
      });
      c.append(ol);
    } else if (g.tipus === "notificacio") {
      c.append(element(doc, "div", "tg-app", inicial(g.de)));
      const dins = element(doc, "div", "tg-notif-cos");
      const cap = element(doc, "div", "tg-notif-cap");
      cap.append(element(doc, "span", null, g.de || ""), element(doc, "span", null, "ara"));
      const text = element(doc, "div", "tg-notif-text");
      ambDestacat(doc, text, g.text);
      dins.append(cap, text);
      c.append(dins);
    } else if (g.tipus === "ratllat") {
      const [vell, nou] = g.punts || [];
      if (g.text) c.append(element(doc, "div", "tg-rt-titol", g.text));
      const v = element(doc, "div", "tg-vell", vell?.text || "");
      v.append(element(doc, "i", "tg-ratlla"));
      const n = element(doc, "div", "tg-nou");
      if (g.estil === "mac" || g.estil === "scrapbook") ambMarcador(doc, n, nou?.text); else n.textContent = nou?.text || "";
      c.append(v, n);
    } else if (g.tipus === "publicacio") {
      const cap = element(doc, "div", "tg-pub-cap");
      cap.append(element(doc, "i", "tg-avatar", inicial(g.de)), element(doc, "b", "tg-pub-nom", g.de || ""));
      const text = element(doc, "div", "tg-pub-text");
      ambDestacat(doc, text, g.text);
      const peu = element(doc, "div", "tg-pub-peu");
      for (const d of ICONES_PUBLICACIO) peu.append(icona(doc, d));
      c.append(cap, text, peu);
    } else if (g.tipus === "notes") {
      const barra = element(doc, "div", "tg-notes-barra");
      barra.append(element(doc, "span", null, "‹ Notes"), element(doc, "span", null, "Fet"));
      const full = element(doc, "div", "tg-notes-full");
      if (g.text) full.append(element(doc, "h3", null, g.text));
      for (const p of g.punts || []) {
        const linia = element(doc, "p", "tg-linia-nota");
        const viu = element(doc, "span", "tg-escrit-viu");
        viu.append(element(doc, "span", "tg-escrit", p.text), element(doc, "i", "tg-cursor"));
        linia.append(element(doc, "span", "tg-escrit-ple", p.text), viu);
        full.append(linia);
      }
      c.append(barra, full);
    } else if (g.tipus === "segueix") {
      const dades = element(doc, "div", "tg-seg-dades");
      dades.append(element(doc, "b", null, g.de || ""));
      if (g.text) dades.append(element(doc, "span", null, g.text));
      const boto = element(doc, "span", "tg-seg-boto");
      boto.append(element(doc, "span", "tg-seg-a", "Segueix"), element(doc, "span", "tg-seg-b", "Seguint ✓"), element(doc, "i", "tg-dit"));
      c.append(element(doc, "i", "tg-avatar", inicial(g.de)), dades, boto);
    } else if (g.tipus === "rec") {
      // A tota la zona on pot anar (la mateixa que fa servir colloca).
      const [dalt, baix] = g.limits || [269, 1248];
      const alt = Math.max(160, baix - dalt);
      c.style.height = `${alt}px`;
      c.style.setProperty("--tg-rec-k", Math.min(1, alt / 640).toFixed(3));
      for (let k = 0; k < 4; k++) c.append(element(doc, "i", "tg-rec-cant"));
      const dalt_ = element(doc, "div", "tg-rec-dalt");
      const rec = element(doc, "span");
      rec.append(element(doc, "i", "tg-rec-punt"), doc.createTextNode("REC"));
      dalt_.append(rec, element(doc, "i", "tg-rec-bat"));
      const baix_ = element(doc, "div", "tg-rec-baix");
      baix_.append(element(doc, "span", "tg-rec-temps", "00:00:00"), element(doc, "span", null, g.text || ""));
      c.append(dalt_, baix_);
    } else if (g.tipus === "abans" || g.tipus === "carrusel") {
      if (g.text) { const h = element(doc, "h3"); ambDestacat(doc, h, g.text); c.append(h); }
      const foto = (p, classe) => {
        const fig = element(doc, "figure", classe);
        if (p?.imatge) {
          const img = element(doc, "img");
          Object.assign(img, { src: imatge(p.imatge), alt: "" });
          fig.append(img);
        } else fig.append(element(doc, "div", "tg-falta-foto"));
        return fig;
      };
      // Les fotos ocupen l'alçada que hi ha (amb el bloc de color, la de sobre la targeta del vídeo).
      const [dalt, baix] = g.limits || [269, 1248];
      const lliure = baix - dalt - (g.text ? 100 : 0);
      if (g.tipus === "abans") {
        const comp = element(doc, "div", "tg-comparacio");
        comp.style.height = `${Math.round(Math.max(320, Math.min(900, lliure)))}px`;
        const [a, d] = g.punts || [];
        const fa = foto(a, "tg-ab tg-ab-abans");
        fa.append(element(doc, "figcaption", null, a?.text || "abans"));
        const fd = foto(d, "tg-ab tg-ab-despres");
        fd.append(element(doc, "figcaption", null, d?.text || "després"));
        comp.append(fa, fd, element(doc, "i", "tg-ab-linia"));
        c.append(comp);
      } else {
        const roda = element(doc, "div", "tg-roda");
        const alt = Math.max(360, Math.min(640, lliure));
        roda.style.height = `${Math.round(alt)}px`;
        roda.dataset.mida = (alt / 640).toFixed(3);
        const fotos = (g.punts || []).length ? g.punts : [{}, {}, {}, {}];  // sense fotos: on aniran
        for (const p of fotos) roda.append(foto(p, "tg-carta-roda"));
        rodaCarrusel([...roda.children], 0);
        c.append(roda);
      }
    } else if (g.tipus === "comentari") {
      const NS = "http://www.w3.org/2000/svg";
      const cor = doc.createElementNS(NS, "svg");
      cor.setAttribute("class", "tg-cor");
      cor.setAttribute("viewBox", "0 0 24 24");
      const cami = doc.createElementNS(NS, "path");
      cami.setAttribute("d", "M12 20.5S3.5 15.4 3.5 9.3A4.6 4.6 0 0 1 12 6.9a4.6 4.6 0 0 1 8.5 2.4c0 6.1-8.5 11.2-8.5 11.2z");
      cor.append(cami);
      const text = element(doc, "div", "tg-com-text");
      ambDestacat(doc, text, g.text);
      c.append(element(doc, "i", "tg-avatar", inicial(g.de)), element(doc, "span", "tg-com-qui", g.de || ""), cor, text);
    } else if (g.tipus === "xat") {
      if (g.text) {
        const qui = element(doc, "div", "tg-xat-qui");
        qui.append(element(doc, "i", null, inicial(g.text)), element(doc, "span", null, g.text));
        c.append(qui);
      }
      for (const p of g.punts || []) {
        const fila = element(doc, "div", `tg-fila-xat tg-${p.costat === "enviat" ? "enviat" : "rebut"}`);
        const bombolla = element(doc, "div", "tg-bombolla");
        ambDestacat(doc, bombolla, p.text);
        fila.append(bombolla);
        if (p.costat !== "enviat") {  // els tres punts d'«escrivint…», al lloc del missatge que arriba
          const escriu = element(doc, "div", "tg-escriu");
          escriu.append(element(doc, "i"), element(doc, "i"), element(doc, "i"));
          fila.append(escriu);
        }
        c.append(fila);
      }
    } else if (g.tipus === "numero") {
      c.append(element(doc, "span", "tg-xifra", formata(g.xifra, g.xifra?.valor ?? 0)));
      if (g.text) { const t = element(doc, "span", "tg-xifra-text"); ambDestacat(doc, t, g.text); c.append(t); }
    } else if (g.tipus === "progres") {
      const xifra = element(doc, "span", "tg-xifra", formata(g.xifra, g.xifra?.valor ?? 0));
      if (g.forma === "barra") {
        const barra = element(doc, "div", "tg-barra-prog");
        const ple = element(doc, "i");
        ple.style.transform = `scaleX(${g.fraccio ?? 0})`;  // sense GSAP, ja ple fins on toca
        barra.append(ple);
        c.append(xifra, barra);
      } else {
        const NS = "http://www.w3.org/2000/svg";
        const anell = element(doc, "div", "tg-anell");
        anell.style.setProperty("--tg-lletres", Math.max(4, xifra.textContent.length));
        const svg = doc.createElementNS(NS, "svg");
        svg.setAttribute("viewBox", "0 0 120 120");
        for (const classe of ["tg-pista", "tg-arc"]) {
          const cercle = doc.createElementNS(NS, "circle");
          for (const [k, v] of [["cx", 60], ["cy", 60], ["r", 54], ["class", classe], ["pathLength", 1]]) cercle.setAttribute(k, v);
          if (classe === "tg-arc") cercle.style.strokeDashoffset = 1 - (g.fraccio ?? 0);
          svg.append(cercle);
        }
        anell.append(svg, xifra);
        c.append(anell);
      }
      if (g.text) { const t = element(doc, "span", "tg-xifra-text"); ambDestacat(doc, t, g.text); c.append(t); }
    } else if (g.tipus === "web") {
      const barra = element(doc, "div", "tg-barra");
      barra.append(element(doc, "i"), element(doc, "i"), element(doc, "i"), element(doc, "span", "tg-adreca", g.text || ""));
      const pantalla = element(doc, "div", "tg-pantalla");
      if (g.imatge) {
        const img = element(doc, "img");
        Object.assign(img, { src: imatge(g.imatge), alt: "" });
        pantalla.append(img);
      } else {
        pantalla.append(element(doc, "div", "tg-falta", "Falta la captura"));
      }
      c.append(barra, pantalla);
    } else if (g.tipus === "ventall") {
      if (g.text) { const h = element(doc, "h3"); ambDestacat(doc, h, g.text); c.append(h); }
      const cartes = element(doc, "div", "tg-cartes");
      const fotos = (g.punts || []).length ? g.punts : [{}, {}, {}];  // sense fotos: on aniran
      for (const p of fotos) {
        const carta = element(doc, "figure", p.imatge ? "tg-carta" : "tg-carta tg-buida");
        if (p.imatge) {
          const img = element(doc, "img");
          Object.assign(img, { src: imatge(p.imatge), alt: "" });
          carta.append(img);
        } else {
          carta.append(element(doc, "div", "tg-falta-foto"));
        }
        if (p.text) carta.append(element(doc, "figcaption", null, p.text));
        cartes.append(carta);
      }
      obreVentall([...cartes.children], g);
      c.append(cartes);
    } else if (g.tipus === "anotacio") {
      const NS = "http://www.w3.org/2000/svg";
      const svg = doc.createElementNS(NS, "svg");
      svg.setAttribute("class", "tg-traca");
      const cami = doc.createElementNS(NS, "path");
      cami.setAttribute("pathLength", "1");  // així es dibuixa igual de llarg com sigui
      svg.append(cami);
      c.append(element(doc, "span", "tg-nota", g.text), svg);
    } else {  // crida
      const text = g.text || "";
      if (g.estil === "mac") {
        c.append(element(doc, "span", "tg-icona", "→"));
        const s = element(doc, "span");
        ambDestacat(doc, s, text);
        c.append(s);
      } else {
        ambDestacat(doc, c, text);
        // L'espai que no es trenca: la fletxa no queda mai sola en una línia.
        if (g.estil !== "scrapbook") c.append(element(doc, "span", "tg-fletxa", "\u00a0→"));
      }
    }
    return c;
  }

  // Com entra cada estil: net puja, mac s'acosta suau, scrapbook s'enganxa, editorial es descobreix.
  // La notificació cau de dalt, com al mòbil; el comentari salta a la vista i, al cap d'un moment, el cor fa un batec.
  function entra(tl, c, g) {
    const t = g.inici;
    if (g.tipus === "notificacio" && g.estil !== "editorial") {
      tl.fromTo(c, { opacity: 0, y: -130, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.55, ease: "back.out(1.4)" }, t);
    } else if (g.tipus === "comentari" && g.estil !== "editorial") {
      tl.fromTo(c, { opacity: 0, y: 40, scale: 0.86 }, { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: "back.out(1.7)" }, t);
      const cor = c.querySelector(".tg-cor");
      if (cor) tl.fromTo(cor, { scale: 1 }, { scale: 1.3, duration: 0.16, yoyo: true, repeat: 1, ease: "power2.out" }, t + 0.75);
    } else if (g.estil === "mac") {
      tl.fromTo(c, { opacity: 0, scale: 0.9, y: 22 }, { opacity: 1, scale: 1, y: 0, duration: 0.5, ease: "expo.out" }, t);
    } else if (g.estil === "scrapbook") {
      tl.fromTo(c, { opacity: 0, scale: 1.18, rotation: 7 }, { opacity: 1, scale: 1, rotation: 0, duration: 0.38, ease: "back.out(2.2)" }, t);
    } else if (g.estil === "editorial") {
      tl.fromTo(c, { clipPath: "inset(-12% 100% -12% -2%)" }, { clipPath: "inset(-12% -6% -12% -2%)", duration: 0.65, ease: "power2.inOut" }, t);
    } else {
      tl.fromTo(c, { opacity: 0, y: 36 }, { opacity: 1, y: 0, duration: 0.45, ease: "power3.out" }, t);
    }
  }

  // Si un gràfic és massa alt (un text llarg, una lletra ampla), es fa més petit fins que hi cap: la
  // frase, amb la lletra (el text torna a repartir-se en línies); la llista i la crida, senceres.
  // Mai més alt que l'espai que té (amb el bloc de color, el de sobre la targeta).
  const ALCADA_MAXIMA = { frase: 330, marcador: 330, ratllat: 420, progres: 640, publicacio: 560, notes: 620, segueix: 260,
    abans: 900, carrusel: 760, llista: 470, crida: 230, notificacio: 300, comentari: 360, xat: 560, numero: 400, web: 700,
    ventall: 680 };
  function encaixa({ g, lloc, c }) {
    if (!ALCADA_MAXIMA[g.tipus]) return;
    const maxima = Math.min(ALCADA_MAXIMA[g.tipus], g.limits ? g.limits[1] - g.limits[0] : Infinity);
    const frase = g.tipus === "frase" || g.tipus === "marcador";
    const base = frase ? Number(c.dataset.escala) : 1;
    const posa = (k) => (frase ? c.style.setProperty("--tg-escala", (base * k).toFixed(3)) : (c.style.zoom = k === 1 ? "" : k.toFixed(2)));
    posa(1);
    for (let k = 0.95; k >= 0.6 && lloc.offsetHeight > maxima; k -= 0.05) posa(k);
  }

  // L'alçada de cada gràfic dins dels seus límits (se'n mesura l'alçada: depèn del text i de la lletra).
  function colloca({ g, lloc }) {
    const [dalt, baix] = g.limits || [269, 1248];
    const h = lloc.offsetHeight;
    const p = g.posicio;
    let top = typeof p === "number" ? p * 1920 - h / 2 : p === "baix" ? baix - h : p === "mig" ? (dalt + baix - h) / 2 : dalt;
    top = Math.max(dalt, Math.min(top, baix - h));
    lloc.style.top = `${Math.round(top)}px`;
  }

  // Un número entre 0 i 1 que sembla a l'atzar però que sempre és el mateix per a cada gràfic.
  function atzar(text, k) {
    let n = k * 7919;
    for (const ch of String(text)) n = (n * 31 + ch.charCodeAt(0)) % 100003;
    const x = Math.sin(n) * 43758.5453;
    return x - Math.floor(x);
  }

  // El traç de l'anotació, fet a mà al voltant de la nota (es fa quan ja se'n sap la mida).
  function traca({ g, c }) {
    const nota = c.querySelector(".tg-nota");
    const cami = c.querySelector(".tg-traca path");
    if (!nota || !cami) return;
    const x = nota.offsetLeft, y = nota.offsetTop, w = nota.offsetWidth, h = nota.offsetHeight;
    const a = (k) => atzar(g.id || g.text, k) - 0.5;  // una mica de tremolor, sempre el mateix
    const f = (n) => n.toFixed(1);
    let d;
    if (g.forma === "cercle") {
      const cx = x + w / 2, cy = y + h / 2, rx = w / 2 + 34, ry = h / 2 + 24;
      const punts = [];
      for (let k = 0; k <= 52; k++) {  // una volta i una mica més: com quan es fa a mà
        const angle = -2.3 + (k / 52) * (Math.PI * 2 + 0.45);
        const r = 1 + 0.05 * Math.sin(3 * angle + a(1) * 6) + (k / 52) * 0.06;
        punts.push(`${f(cx + Math.cos(angle) * rx * r)} ${f(cy + Math.sin(angle) * ry * r)}`);
      }
      d = `M ${punts.join(" L ")}`;
    } else if (g.forma === "subratllat") {
      const y0 = y + h + 6;
      d = `M ${f(x - 8)} ${f(y0 + a(1) * 8)} Q ${f(x + w / 2)} ${f(y0 + 14)} ${f(x + w + 10)} ${f(y0 - 4)}` +
        ` M ${f(x + w * 0.12)} ${f(y0 + 20)} Q ${f(x + w * 0.55)} ${f(y0 + 28 + a(2) * 6)} ${f(x + w * 0.9)} ${f(y0 + 16)}`;
    } else {  // fletxa: de la nota cap al mig de la pantalla
      const s = g.costat === "dreta" ? -1 : 1;
      const x0 = g.costat === "dreta" ? x - 18 : x + w + 18, y0 = y + h * 0.55;
      const x1 = x0 + s * 190, y1 = y0 + 120 + a(1) * 30;
      const cx = x0 + s * 160, cy = y0 - 20;
      const angle = Math.atan2(y1 - cy, x1 - cx);
      const punta = (gir) => `${f(x1 - 36 * Math.cos(angle + gir))} ${f(y1 - 36 * Math.sin(angle + gir))}`;
      d = `M ${f(x0)} ${f(y0)} Q ${f(cx)} ${f(cy)} ${f(x1)} ${f(y1)} M ${punta(0.5)} L ${f(x1)} ${f(y1)} L ${punta(-0.5)}`;
    }
    cami.setAttribute("d", d);
  }

  function construeix(arrel, grafics, paleta, op) {
    op = op || {};
    const doc = arrel.ownerDocument;
    const gsap = global.gsap;
    posaCss(doc);
    arrel.textContent = "";
    arrel.className = "tg-capa";
    const p = paleta || {};
    for (const [k, valor] of Object.entries(variables({ clar: "#FFFFFF", fosc: "#111111", ...p }))) {
      if (valor == null) arrel.style.removeProperty(k); else arrel.style.setProperty(k, valor);
    }
    const fets = (grafics || []).map((g) => {
      const costat = g.tipus === "anotacio" && g.costat === "dreta" ? " tg-a-dreta" : "";
      // El marcador és una frase, i el progrés, un número (en fan servir l'aspecte).
      const tipus = g.tipus === "marcador" ? "frase tg-marcador" : g.tipus === "progres" ? "numero tg-progres" : g.tipus;
      const lloc = element(doc, "div", `tg-lloc tg-${tipus} tg-${g.estil || "net"}${costat}`);
      if (g.id) lloc.dataset.id = g.id;  // la pàgina hi troba el que es toca al vídeo
      const c = cos(doc, g, op);
      lloc.append(c);
      arrel.append(lloc);
      return { g, lloc, c, punts: [...c.querySelectorAll("li, .tg-fila-xat, .tg-carta:not(.tg-buida)")] };
    });
    const mesura = () => { for (const f of fets) { encaixa(f); colloca(f); traca(f); } };
    mesura();
    // El vídeo final pot dibuixar abans de tenir les lletres: quan arriben, es torna a mesurar.
    if (doc.fonts && doc.fonts.status !== "loaded") doc.fonts.ready.then(mesura);

    if (!gsap) {
      return {
        seek(t) {
          for (const f of fets) {
            f.lloc.style.visibility = t >= f.g.inici && t < f.g.final ? "visible" : "hidden";
            f.punts.forEach((el, k) => {
              const surt = t >= (f.g.punts[k]?.t ?? 0) ? 1 : 0;
              if (el.matches("li, .tg-carta")) el.style.opacity = surt; else el.querySelector(".tg-bombolla").style.opacity = surt;
            });
          }
          return this;
        },
      };
    }
    const tl = op.tl || gsap.timeline({ paused: true });
    for (const { g, lloc, c, punts } of fets) {
      tl.set(lloc, { visibility: "visible" }, g.inici);
      tl.set(lloc, { visibility: "hidden" }, g.final);
      if (g.tipus === "anotacio") {  // s'escriu i després es dibuixa el traç
        tl.fromTo(c.querySelector(".tg-nota"), { clipPath: "inset(-30% 100% -30% -10%)" },
          { clipPath: "inset(-30% -10% -30% -10%)", duration: 0.5, ease: "power1.inOut" }, g.inici);
        tl.fromTo(c.querySelector(".tg-traca path"), { strokeDashoffset: 1 },
          { strokeDashoffset: 0, duration: 0.55, ease: "power1.inOut" }, g.inici + 0.35);
      } else {
        entra(tl, c, g);
      }
      if ((g.tipus === "numero" || g.tipus === "progres") && g.xifra) {  // compta des de zero
        const xifra = c.querySelector(".tg-xifra");
        const compte = { v: 0 };
        tl.fromTo(compte, { v: 0 }, {
          v: g.xifra.valor, duration: 1.0, ease: "power2.out",
          onUpdate: () => { xifra.textContent = formata(g.xifra, compte.v); },
        }, g.inici + 0.15);
      }
      if (g.tipus === "progres") {  // i, alhora, el cercle o la barra s'omplen fins a la seva part
        const f = g.fraccio ?? 0;
        const arc = c.querySelector(".tg-arc");
        if (arc) tl.fromTo(arc, { strokeDashoffset: 1 }, { strokeDashoffset: 1 - f, duration: 1.0, ease: "power2.out" }, g.inici + 0.15);
        const ple = c.querySelector(".tg-barra-prog i");
        if (ple) tl.fromTo(ple, { scaleX: 0 }, { scaleX: f, duration: 1.0, ease: "power2.out" }, g.inici + 0.15);
      }
      const img = g.tipus === "web" && c.querySelector(".tg-pantalla img");
      if (img) {  // si la captura és més llarga que la finestra, baixa a poc a poc (com quan es llegeix)
        tl.fromTo(img, { objectPosition: "50% 0%" }, { objectPosition: "50% 100%", ease: "sine.inOut",
          duration: Math.max(0.5, g.final - g.inici - 1.6) }, g.inici + 0.8);
      }
      const marques = g.tipus === "marcador" ? [...c.querySelectorAll(".tg-marca")] : [];
      marques.forEach((marca, k) => {  // el marcador passa quan la frase ja hi és, paraula darrere paraula
        const pas = Math.min(0.22, 0.6 / marques.length);
        tl.fromTo(marca, { "--tg-marcat": "0%" }, { "--tg-marcat": "100%", duration: pas + 0.05, ease: "none" }, g.inici + 0.35 + k * pas);
      });
      if (g.tipus === "notes") {  // cada línia s'escriu lletra a lletra quan es diu, amb el cursor al final
        c.querySelectorAll(".tg-linia-nota").forEach((linia, k) => {
          const escrit = linia.querySelector(".tg-escrit");
          const cursor = linia.querySelector(".tg-cursor");
          const text = g.punts[k]?.text || "";
          const t = Math.max(g.inici + 0.35, g.punts[k]?.t ?? g.inici + 0.35);
          const dur = durEscriu(text);
          const compte = { n: 0 };
          const posa = () => { escrit.textContent = text.slice(0, Math.round(compte.n)); };
          posa();
          tl.fromTo(compte, { n: 0 }, { n: text.length, duration: dur, ease: "none", onUpdate: posa }, t);
          tl.fromTo(cursor, { opacity: 0 }, { opacity: 1, duration: 0.01 }, t);
          tl.to(cursor, { opacity: 0, duration: 0.01 }, k + 1 < g.punts.length ? Math.max(t + dur, g.punts[k + 1].t ?? 0) : g.final);
        });
      }
      if (g.tipus === "segueix") {  // un dit toca el botó, que s'enfonsa i passa a «Seguint»
        const t = g.inici + Math.min(1.2, Math.max(0.6, (g.final - g.inici) * 0.4));
        const dit = c.querySelector(".tg-dit");
        tl.fromTo(dit, { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.25, ease: "power2.out" }, t - 0.25);
        tl.fromTo(c.querySelector(".tg-seg-boto"), { scale: 1 }, { scale: 0.92, duration: 0.1, yoyo: true, repeat: 1 }, t);
        tl.fromTo(c.querySelector(".tg-seg-b"), { opacity: 0 }, { opacity: 1, duration: 0.15 }, t + 0.1);
        tl.fromTo(c.querySelector(".tg-seg-a"), { opacity: 1 }, { opacity: 0, duration: 0.15, immediateRender: false }, t + 0.1);
        tl.to(dit, { opacity: 0, scale: 1.4, duration: 0.3 }, t + 0.25);
      }
      if (g.tipus === "rec") {  // el punt vermell parpelleja i el temps corre
        const punt = c.querySelector(".tg-rec-punt");
        const cops = Math.max(0, Math.floor((Math.min(g.final, g.inici + 3600) - g.inici - 0.5) / 0.5));
        tl.fromTo(punt, { opacity: 1 }, { opacity: 0.15, duration: 0.5, ease: "steps(1)", repeat: cops, yoyo: true,
          immediateRender: false }, g.inici + 0.5);
        const temps = c.querySelector(".tg-rec-temps");
        const rellotge = { s: 0 };
        const dos = (n) => String(Math.floor(n)).padStart(2, "0");
        tl.fromTo(rellotge, { s: 0 }, { s: g.final - g.inici, duration: g.final - g.inici, ease: "none",
          onUpdate: () => { temps.textContent = `00:${dos(rellotge.s / 60)}:${dos(rellotge.s % 60)}`; } }, g.inici);
      }
      if (g.tipus === "abans") {  // la ratlla es mou i descobreix el després (quan es diu, si es diu on)
        const t = Math.max(g.inici + 0.6, g.punts?.[1]?.t ?? g.inici + 0.9);
        tl.fromTo(c.querySelector(".tg-comparacio"), { "--tg-tall": "100%" }, { "--tg-tall": "50%", duration: 0.9, ease: "power2.inOut" }, t);
      }
      if (g.tipus === "carrusel") {  // la roda gira a poc a poc mentre dura
        const cartes = [...c.querySelectorAll(".tg-carta-roda")];
        const gir = { a: 0 };
        tl.fromTo(gir, { a: 0 }, { a: -Math.PI * 1.2, duration: Math.max(0.5, g.final - g.inici), ease: "sine.inOut",
          onUpdate: () => rodaCarrusel(cartes, gir.a) }, g.inici);
      }
      if (g.tipus === "ratllat" && g.punts?.[1]) {  // quan es diu la paraula nova, es ratlla la d'abans i surt la nova
        const t = Math.max(g.inici + 0.45, g.punts[1].t);
        tl.fromTo(c.querySelector(".tg-ratlla"), { scaleX: 0 }, { scaleX: 1, duration: 0.3, ease: "power2.inOut" }, t - 0.3);
        tl.fromTo(c.querySelector(".tg-vell"), { opacity: 1 }, { opacity: 0.6, duration: 0.25, immediateRender: false }, t);
        tl.fromTo(c.querySelector(".tg-nou"), { opacity: 0, y: 26, scale: 0.9 },
          { opacity: 1, y: 0, scale: 1, duration: 0.42, ease: "back.out(1.8)" }, t);
      }
      let abans = g.inici;
      punts.forEach((el, k) => {
        const t = g.punts[k].t;
        if (el.matches(".tg-carta")) {  // cada foto arriba de sota i es posa al seu lloc del ventall
          tl.fromTo(el, { opacity: 0, y: 170, scale: 0.86 }, { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: "back.out(1.5)" }, t);
          return;
        }
        if (el.matches("li")) {
          tl.fromTo(el, { opacity: 0, x: -26 }, { opacity: 1, x: 0, duration: 0.35, ease: "power3.out" }, t);
          return;
        }
        // Un missatge: abans dels que arriben, els tres punts d'«escrivint…» (si hi ha temps).
        const escriu = el.querySelector(".tg-escriu");
        if (escriu && t - 0.65 > abans + 0.2) {
          tl.set(escriu, { opacity: 1 }, t - 0.65);
          escriu.querySelectorAll("i").forEach((punt, j) => {
            tl.fromTo(punt, { opacity: 0.35 }, { opacity: 1, duration: 0.18, repeat: 1, yoyo: true }, t - 0.6 + j * 0.12);
          });
          tl.set(escriu, { opacity: 0 }, t);
        }
        tl.fromTo(el.querySelector(".tg-bombolla"), { opacity: 0, scale: 0.75 },
          { opacity: 1, scale: 1, duration: 0.2, ease: "back.out(1.7)" }, t);
        abans = t;
      });
      tl.fromTo(lloc, { opacity: 1 }, { opacity: 0, duration: 0.22, immediateRender: false }, Math.max(g.inici, g.final - 0.22));
    }
    return tl;
  }

  global.TallatGrafics = { construeix, formata };
})(typeof window !== "undefined" ? window : globalThis);
