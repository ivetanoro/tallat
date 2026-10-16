/* tallat · els gràfics del pla: frase clau, etiqueta, llista i crida.
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
 * A la frase i a la crida, el que va *entre asteriscs* surt destacat. La notificació porta qui l'envia
 * (`de`), el xat els missatges a `punts` (cadascun amb `costat`: rebut o enviat), el número la `xifra`
 * ({abans, valor, decimals, despres, milers}) i l'anotació la `forma` (cercle, subratllat o fletxa) i el
 * `costat` on va. L'anotació s'escriu amb la lletra de mà i el color secundari de la marca.
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
.tg-scrapbook.tg-notificacio .tg-cos::before {
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
}`;

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

  const inicial = (text) => (String(text || "").trim()[0] || "✉").toUpperCase();

  // La xifra al moment `v` del compte: «10.000 €», «2,5 h» (com s'escriu en català).
  function formata(x, v) {
    if (!x) return "";
    let [enter, dec] = Number(v).toFixed(x.decimals || 0).split(".");
    if (x.milers || enter.length > 4) enter = enter.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return `${x.abans || ""}${enter}${dec ? `,${dec}` : ""}${x.despres || ""}`;
  }

  function cos(doc, g) {
    const c = element(doc, "div", "tg-cos");
    if (g.tipus === "frase") {
      const n = String(g.text || "").length;
      c.dataset.escala = n > 90 ? 0.74 : n > 55 ? 0.86 : 1;
      c.style.setProperty("--tg-escala", c.dataset.escala);
      ambDestacat(doc, c, g.text);
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
  // La notificació cau de dalt, com al mòbil.
  function entra(tl, c, g) {
    const t = g.inici;
    if (g.tipus === "notificacio" && g.estil !== "editorial") {
      tl.fromTo(c, { opacity: 0, y: -130, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.55, ease: "back.out(1.4)" }, t);
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
  const ALCADA_MAXIMA = { frase: 330, llista: 470, crida: 230, notificacio: 300, xat: 560, numero: 400 };
  function encaixa({ g, lloc, c }) {
    const maxima = ALCADA_MAXIMA[g.tipus];
    if (!maxima) return;
    const frase = g.tipus === "frase";
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
      const lloc = element(doc, "div", `tg-lloc tg-${g.tipus} tg-${g.estil || "net"}${costat}`);
      const c = cos(doc, g);
      lloc.append(c);
      arrel.append(lloc);
      return { g, lloc, c, punts: [...c.querySelectorAll("li, .tg-fila-xat")] };
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
              if (el.matches("li")) el.style.opacity = surt; else el.querySelector(".tg-bombolla").style.opacity = surt;
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
      if (g.tipus === "numero" && g.xifra) {  // compta des de zero
        const xifra = c.querySelector(".tg-xifra");
        const compte = { v: 0 };
        tl.fromTo(compte, { v: 0 }, {
          v: g.xifra.valor, duration: 1.0, ease: "power2.out",
          onUpdate: () => { xifra.textContent = formata(g.xifra, compte.v); },
        }, g.inici + 0.15);
      }
      let abans = g.inici;
      punts.forEach((el, k) => {
        const t = g.punts[k].t;
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
