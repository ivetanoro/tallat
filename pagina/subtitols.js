/* tallat · subtítols animats.
 *
 * El mateix codi dibuixa els subtítols a la vista prèvia de la pàgina de revisió i al
 * vídeo final (dins d'una composició de HyperFrames): el que es veu és el que surt.
 * Treballa sempre sobre una caixa de 1080 px d'amplada; qui el fa servir l'escala.
 *
 *   const tl = TallatSubtitols.construeix(element, linies, estil, { familia });
 *   tl.seek(segons);
 *   TallatSubtitols.titol(element, { text, inici, final }, estilTitol, { tl, familia });
 *
 * El títol del ganxo: cada línia del text és una línia; el que va *entre asteriscs* surt destacat.
 *
 * `linies`: [{inici, final, bloc, paraules: [{text, inici, final, clau, emoji}]}] en temps del muntatge.
 * Amb `disposicio: "apilat"`, les línies d'un mateix `bloc` s'apilen una sota l'altra (la posició
 * marca on queda el bloc: a dalt creix cap avall, a baix creix cap amunt). Amb `"escampat"`, les
 * paraules del bloc surten en files curtes a llocs, mides i inclinacions diferents (com un collage;
 * sempre igual per a una mateixa frase). Si no, cada línia substitueix l'anterior.
 * Al títol, `corba` (de -1 a 1) corba en arc les línies que diu `corba_linies`.
 * Fa servir GSAP si hi és; si no (sense internet), en dona una versió sense animacions.
 */
(function (global) {
  "use strict";

  const AMPLADA = 1080;
  const ESTILS_CSS = `
.ts-capa { position: absolute; left: 0; top: 0; width: ${AMPLADA}px; pointer-events: none; }
.ts-linia { position: absolute; inset: 0; visibility: hidden; }
.ts-tipus {
  font-family: var(--ts-font); font-weight: var(--ts-pes); font-size: var(--ts-mida);
  color: var(--ts-color); text-transform: var(--ts-majuscules); font-kerning: normal;
  letter-spacing: var(--ts-espaiat); line-height: var(--ts-interlineat);
}
.ts-text {
  position: absolute; left: 50%; top: var(--ts-y); width: var(--ts-amplada); margin: 0;
  transform: translate(-50%, -50%); text-align: center;
}
.ts-bloc {
  position: absolute; left: calc((100% - var(--ts-amplada)) / 2); top: var(--ts-y); width: var(--ts-amplada);
  transform: translateY(var(--ts-ancora));
}
.ts-fila { margin: 0; text-align: center; opacity: 0; }  /* opacitat, no visibilitat: així s'amaguen amb el bloc */
.ts-al-esquerra > .ts-text, .ts-fila.ts-al-esquerra { text-align: left; }
.ts-al-dreta > .ts-text, .ts-fila.ts-al-dreta { text-align: right; }
.ts-fons {
  display: inline-block; max-width: 100%; padding: 0.12em 0.5em 0.16em; border-radius: 0.6em;
  background: var(--ts-fons);
}
.ts-p { display: inline-block; position: relative; }
.ts-t { display: inline-block; position: relative; z-index: 1; }
.ts-normal .ts-t { -webkit-text-stroke: var(--ts-gruix) var(--ts-contorn); paint-order: stroke fill; text-shadow: var(--ts-ombra); }
.ts-neo .ts-t {
  text-shadow: 0 0 0.04em #fff, 0 0 0.14em var(--ts-actiu), 0 0 0.38em var(--ts-actiu), 0 0 0.8em var(--ts-actiu);
}
.ts-degradat .ts-t {
  padding: 0 0.04em; margin: 0 -0.04em;
  background: linear-gradient(180deg, var(--ts-color) 10%, var(--ts-actiu) 95%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
  filter: var(--ts-ombra-filtre);
}
.ts-clau .ts-t {
  font-size: calc(var(--ts-clau-mida) * 1em); line-height: 1;
  font-family: var(--ts-clau-font, inherit); font-style: var(--ts-clau-estil, normal); font-weight: var(--ts-clau-pes, inherit);
}
.ts-normal .ts-clau .ts-t, .ts-neo .ts-clau .ts-t { color: var(--ts-clau-color); }
.ts-d-caixa .ts-p, .ts-d-gran .ts-p { margin: 0 0.07em; }
.ts-caixa-p {
  position: absolute; inset: -0.04em -0.12em -0.02em; z-index: 0; border-radius: 0.18em;
  background: var(--ts-actiu); opacity: 0;
}
.ts-emoji {
  position: absolute; left: 50%; bottom: 86%; width: 1.3em; margin-left: -0.65em; z-index: 2;
  font-size: 1.35em; line-height: 1; text-align: center; font-style: normal; font-weight: 400;
  -webkit-text-stroke: 0; text-shadow: none; -webkit-text-fill-color: initial; opacity: 0;
}
.tt-capa { position: absolute; left: 0; top: 0; width: ${AMPLADA}px; pointer-events: none; visibility: hidden; }
.tt-enfosquit { position: absolute; inset: 0; background: var(--tt-fons); opacity: 0; }
.tt-bloc {
  position: absolute; left: calc((100% - var(--tt-amplada)) / 2); top: var(--tt-y); width: var(--tt-amplada);
  transform: translateY(var(--tt-ancora)); text-align: center; font-kerning: normal;
  font-family: var(--tt-font); font-weight: var(--tt-pes); font-size: var(--tt-mida); color: var(--tt-color);
  text-transform: var(--tt-majuscules); letter-spacing: var(--tt-espaiat); line-height: var(--tt-interlineat);
}
.tt-fila { margin: 0; min-height: calc(var(--tt-interlineat) * 1em); }
.tt-fila.tt-te-clau { min-height: calc(var(--tt-interlineat) * var(--tt-clau-mida) * 1em); }
.tt-fila.ts-al-esquerra { text-align: left; }
.tt-fila.ts-al-dreta { text-align: right; }
.tt-text { -webkit-text-stroke: var(--tt-gruix) var(--tt-contorn); paint-order: stroke fill; text-shadow: var(--tt-ombra); }
.tt-clau {
  font-size: calc(var(--tt-clau-mida) * 1em); color: var(--tt-clau-color); line-height: 1;
  font-family: var(--tt-clau-font, inherit); font-style: var(--tt-clau-estil, normal); font-weight: var(--tt-clau-pes, inherit);
}
.tt-pindola .tt-dins {
  padding: 0.04em 0.28em 0.08em; border-radius: 0.22em; background: var(--tt-fons);
  -webkit-box-decoration-break: clone; box-decoration-break: clone;
}
.tt-c, .tt-cursor { display: none; }
.tt-corba { display: block; overflow: visible; filter: drop-shadow(var(--tt-ombra)); }
.tt-corba text {
  fill: var(--tt-color); stroke: var(--tt-contorn); stroke-width: var(--tt-gruix); stroke-linejoin: round;
  paint-order: stroke fill;
}
.tt-corba .tt-clau { fill: var(--tt-clau-color); }
.tt-cursor { font-weight: 300; margin-left: 0.03em; -webkit-text-stroke: 0; }`;

  function posaCss(doc) {
    if (doc.getElementById("tallat-subtitols-css")) return;
    const s = doc.createElement("style");
    s.id = "tallat-subtitols-css";
    s.textContent = ESTILS_CSS;
    doc.head.append(s);
  }

  function rgba(hex, alfa) {
    const n = parseInt(String(hex || "#000000").slice(1), 16) || 0;
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alfa})`;
  }

  // Negre o blanc, el que es llegeixi millor damunt d'un color.
  function contrast(hex) {
    const n = parseInt(String(hex || "#000000").slice(1), 16) || 0;
    const llum = 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255);
    return llum > 160 ? "#000000" : "#FFFFFF";
  }

  // La família d'una lletra per al CSS: «system-ui» tal qual, «Fraunces» entre cometes (com fa el Python).
  const GENERIQUES = new Set(["system-ui", "serif", "sans-serif", "monospace", "cursive", "fantasy"]);
  function familiaDe(nom) {
    const net = String(nom || "").replace(/["'\\;{}<>]/g, "").trim();
    if (!net) return null;
    return GENERIQUES.has(net) ? net : `"${net}", system-ui, sans-serif`;
  }

  // Les paraules destacades amb una lletra pròpia (la d'accent de la marca): la família, la cursiva i
  // un gruix normal (les lletres d'accent no solen tenir negreta). Torna les variables CSS que toquen.
  function lletraClau(estil, prefix) {
    const familia = familiaDe(estil.clau_font);
    return {
      [`--${prefix}-clau-font`]: familia,
      [`--${prefix}-clau-estil`]: estil.clau_cursiva ? "italic" : null,
      [`--${prefix}-clau-pes`]: familia ? "400" : null,
    };
  }

  function element(doc, etiqueta, classe, text) {
    const el = doc.createElement(etiqueta);
    if (classe) el.className = classe;
    if (text != null) el.textContent = text;
    return el;
  }

  // Com entren les paraules (o la línia sencera).
  function entra(tl, objectius, t, animacio, k, pes) {
    switch (animacio) {
      case "fos":
        return tl.fromTo(objectius, { opacity: 0 }, { opacity: 1, duration: 0.18, ease: "power1.out" }, t);
      case "cap":
        return tl.fromTo(objectius, { opacity: 0 }, { opacity: 1, duration: 0.01 }, t);
      case "impacte": {
        const costat = k % 2 ? 1 : -1;  // alterna des de quin costat entra
        return tl.fromTo(objectius, { opacity: 0, scale: 1.9, x: 90 * costat, rotation: -7 * costat },
          { opacity: 1, scale: 1, x: 0, rotation: 0, duration: 0.24, ease: "expo.out" }, t);
      }
      case "cortina":
        return tl.fromTo(objectius, { clipPath: "inset(-60% 100% -40% 0%)" },
          { clipPath: "inset(-60% -10% -40% -10%)", duration: 0.32, ease: "power2.out" }, t);
      case "pes":
        return tl.fromTo(objectius, { opacity: 0, fontWeight: 200 },
          { opacity: 1, fontWeight: pes, duration: 0.45, ease: "power2.out" }, t);
      default:  // pop
        return tl.fromTo(objectius, { opacity: 0, scale: 0.82, y: 10 },
          { opacity: 1, scale: 1, y: 0, duration: 0.14, ease: "back.out(2.2)" }, t);
    }
  }

  // Un número entre 0 i 1 que sembla a l'atzar però que sempre és el mateix per a cada n.
  function atzar(n) {
    const x = Math.sin(n * 12.9898 + 78.233) * 43758.5453;
    return x - Math.floor(x);
  }

  // Escampades: les paraules de cada línia, en files curtes. Les destacades van soles.
  function filesEscampades(linies, estil) {
    const files = [];
    for (const linia of linies) {
      let grup = [];
      const tanca = () => {
        if (grup.length) files.push({ ...linia, inici: grup[0].inici, paraules: grup });
        grup = [];
      };
      for (const w of linia.paraules) {
        if (estil.clau_grans && w.clau) { tanca(); grup.push(w); tanca(); continue; }
        grup.push(w);
        if (grup.length >= 2 || grup.map((x) => x.text).join(" ").length > 12) tanca();
      }
      tanca();
    }
    return files;
  }

  function construeix(arrel, linies, estil, op) {
    op = op || {};
    const doc = arrel.ownerDocument;
    const gsap = global.gsap;
    posaCss(doc);

    const aspecte = ["neo", "degradat"].includes(estil.aspecte) ? estil.aspecte : "normal";
    let destacat = estil.destaca === false ? "cap" : (estil.destacat || "color");
    if (destacat === "color" && aspecte === "degradat") destacat = "gran";  // el degradat no canvia de color
    const animacio = estil.animacio || "pop";
    const deCop = estil.apareixen === "linia";
    const pes = Number(estil.pes) || 800;
    const ombra = estil.ombra !== false;
    const escampat = estil.disposicio === "escampat";
    const apilat = estil.disposicio === "apilat" || escampat;  // escampades: també per blocs
    const alineacio = ["esquerra", "dreta", "esglao"].includes(estil.alineacio) ? estil.alineacio : "centre";
    // Esglaó: les línies van a l'esquerra i a la dreta per torns; les que només són paraules destacades,
    // al mig (com un títol: «#3 canvis» a l'esquerra, «SER CREADORA» al mig, «nivell fàcil» a la dreta).
    let torn = 0;
    const alinea = (linia) => {
      if (alineacio !== "esglao") return alineacio;
      if (estil.clau_grans && linia.paraules.length && linia.paraules.every((w) => w.clau)) return "centre";
      return torn++ % 2 ? "dreta" : "esquerra";
    };
    const colorClau = estil.clau_color || estil.color_actiu;
    const y = op.y ?? estil.posicio_y;

    arrel.className = `ts-capa ts-${aspecte} ts-d-${destacat}`;
    arrel.style.height = `${op.alcada || 1920}px`;
    const v = {
      "--ts-y": `${y * 100}%`,
      "--ts-ancora": `${-y * 100}%`,  // un bloc apilat: a dalt creix cap avall; a baix, cap amunt
      "--ts-amplada": `${(op.amplada ?? estil.amplada_maxima) * 100}%`,
      "--ts-font": op.familia || "system-ui, sans-serif",
      "--ts-pes": pes,
      "--ts-mida": `${(op.mida ?? estil.mida) * AMPLADA}px`,
      "--ts-color": estil.color,
      "--ts-actiu": estil.color_actiu,
      "--ts-contorn": estil.contorn,
      "--ts-gruix": `${(estil.gruix_contorn || 0) * 2}em`,
      "--ts-majuscules": estil.majuscules ? "uppercase" : "none",
      "--ts-espaiat": `${Number(estil.espaiat) || 0}em`,
      "--ts-interlineat": Number(estil.interlineat) || 1.12,
      "--ts-clau-mida": Number(estil.clau_mida) || 1.4,
      "--ts-clau-color": colorClau,
      // L'ombra, del color del contorn (el fosc de la marca; si no, negre).
      "--ts-ombra": ombra ? `0 0.06em 0.2em ${rgba(estil.contorn, 0.45)}` : "none",
      "--ts-ombra-filtre": ombra ? `drop-shadow(0 0.04em 0.1em ${rgba(estil.contorn, 0.5)})` : "none",
      "--ts-fons": rgba(estil.fons_color, 0.62),
      ...lletraClau(estil, "ts"),
    };
    for (const [k, valor] of Object.entries(v)) {
      if (valor == null) arrel.style.removeProperty(k); else arrel.style.setProperty(k, valor);
    }
    arrel.textContent = "";

    // Una línia: el fons (si n'hi ha) i les paraules.
    function fila(p, linia) {
      const fons = estil.fons === "pindola" ? element(doc, "span", "ts-fons") : null;
      const cont = fons || p;
      if (fons) p.append(fons);
      const paraules = linia.paraules.map((w, j) => {
        const el = element(doc, "span", `ts-p${estil.clau_grans && w.clau ? " ts-clau" : ""}`);
        const caixa = destacat === "caixa" ? element(doc, "span", "ts-caixa-p") : null;
        if (caixa) el.append(caixa);
        const t = element(doc, "span", "ts-t", w.text);
        el.append(t);
        const emoji = estil.emojis && w.emoji ? element(doc, "span", "ts-emoji", w.emoji) : null;
        if (emoji) el.append(emoji);
        if (j) cont.append(" ");
        cont.append(el);
        return { w, p: el, t, caixa, emoji };
      });
      return { linia, p, fons, paraules };
    }

    // Blocs: apilades, les línies d'un mateix bloc; si no, cada línia és un bloc.
    const blocs = [];
    for (const linia of linies) {
      const darrer = blocs[blocs.length - 1];
      if (apilat && darrer && linia.bloc != null && darrer.id === linia.bloc) darrer.linies.push(linia);
      else blocs.push({ id: linia.bloc, linies: [linia] });
    }
    const construides = blocs.map((b, i) => {
      const el = element(doc, "div", "ts-linia");
      let files;
      if (escampat) {
        const cos = element(doc, "div", "ts-bloc ts-tipus");
        el.append(cos);
        // Cada fila a una banda (esquerra, dreta i, de tant en tant, al mig), amb un marge, una mida
        // i una inclinació diferents. Depèn de les paraules: la mateixa frase fa sempre el mateix collage.
        const llavor = Math.floor(atzar((b.linies[0].paraules[0]?.id ?? i) + 0.3) * 2);
        files = filesEscampades(b.linies, estil).map((linia, k) => {
          const g = (linia.paraules[0].id ?? i * 31 + k) * 1.7 + k;
          const gran = linia.paraules.every((w) => estil.clau_grans && w.clau);
          const petita = !gran && linia.paraules.every((w) => w.text.replace(/[^\p{L}\p{N}]/gu, "").length <= 3);
          const costat = k % 3 === 2 ? "centre" : (k + llavor) % 2 ? "dreta" : "esquerra";
          const p = element(doc, "p", `ts-fila ts-al-${costat}`);
          const marge = `${Math.round(2 + atzar(g) * (gran ? 14 : 22))}%`;
          if (costat === "esquerra") p.style.paddingLeft = marge;
          if (costat === "dreta") p.style.paddingRight = marge;
          p.style.fontSize = gran ? `${(0.82 + atzar(g + 0.2) * 0.36).toFixed(3)}em` : petita ? "0.8em" : "1em";
          p.style.transform = `rotate(${((atzar(g + 0.5) - 0.5) * (gran ? 6 : 9)).toFixed(2)}deg)`;
          cos.append(p);
          return fila(p, linia);
        });
      } else if (apilat) {
        const cos = element(doc, "div", "ts-bloc ts-tipus");
        el.append(cos);
        torn = 0;  // cada bloc comença a l'esquerra
        files = b.linies.map((linia) => {
          const p = element(doc, "p", `ts-fila ts-al-${alinea(linia)}`);
          cos.append(p);
          return fila(p, linia);
        });
      } else {
        el.classList.add(`ts-al-${alinea(b.linies[0])}`);
        const p = element(doc, "p", "ts-text ts-tipus");
        el.append(p);
        files = [fila(p, b.linies[0])];
      }
      arrel.append(el);
      const seq = files.flatMap((f) => f.paraules.map((x) => ({ ...x, fila: f })));  // en l'ordre que sonen
      return { el, files, seq, inici: b.linies[0].inici, final: b.linies[b.linies.length - 1].final };
    });

    const amaga = Array.isArray(op.amaga) ? op.amaga : null;  // [inici, final]: el títol hi és, ells no
    if (!gsap) return senseAnimacions(construides, estil, destacat, apilat, arrel, amaga);

    const tl = op.tl || gsap.timeline({ paused: true });
    if (amaga) {
      tl.set(arrel, { opacity: 0 }, amaga[0]);
      tl.set(arrel, { opacity: 1 }, amaga[1]);
    }
    let n = 0;  // línia de tot el vídeo (per alternar d'on entren)
    for (const b of construides) {
      // Els blocs i les línies es mostren i s'amaguen amb un canvi instantani.
      tl.set(b.el, { visibility: "visible" }, b.inici);
      tl.set(b.el, { visibility: "hidden" }, b.final);
      for (const f of b.files) {
        if (apilat) tl.set(f.p, { opacity: 1 }, f.linia.inici);
        if (f.fons) tl.fromTo(f.fons, { opacity: 0, scale: 0.94 }, { opacity: 1, scale: 1, duration: 0.16, ease: "power2.out" }, f.linia.inici);
        if (deCop) {
          entra(tl, animacio === "cortina" ? f.p : f.paraules.map((x) => x.p), f.linia.inici, animacio, n, pes);
        } else {
          f.paraules.forEach((x, j) => entra(tl, x.p, x.w.inici, animacio, n * 7 + j, pes));
        }
        n++;
      }
      b.seq.forEach((x, j) => {
        const ara = x.w.inici;
        const fi = j + 1 < b.seq.length ? b.seq[j + 1].w.inici : x.fila.linia.final;
        const colorDeSempre = x.p.classList.contains("ts-clau") ? colorClau : estil.color;
        if (destacat === "color") {
          tl.set(x.t, { color: estil.color_actiu }, ara);
          tl.set(x.t, { color: colorDeSempre }, fi);
        } else if (destacat === "karaoke") {
          tl.set(x.t, { color: estil.color_actiu }, ara);  // es queda pintada fins al final
        } else if (destacat === "caixa") {
          tl.fromTo(x.caixa, { opacity: 0, scale: 0.7 }, { opacity: 1, scale: 1, duration: 0.12, ease: "back.out(2)" }, ara);
          tl.to(x.caixa, { opacity: 0, duration: 0.08 }, Math.max(ara + 0.12, fi));
          if (aspecte !== "degradat") {  // damunt la caixa, la lletra que es llegeixi millor
            tl.set(x.t, { color: contrast(estil.color_actiu), textShadow: "none", webkitTextStrokeWidth: 0 }, ara);
            tl.set(x.t, { color: colorDeSempre, textShadow: "", webkitTextStrokeWidth: "" }, fi);
          }
        } else if (destacat === "gran") {
          tl.to(x.t, { scale: 1.12, duration: 0.1, ease: "power2.out" }, ara);
          tl.to(x.t, { scale: 1, duration: 0.12, ease: "power2.inOut" }, Math.max(ara + 0.1, fi));
        }
        if (x.emoji) {
          tl.fromTo(x.emoji, { opacity: 0, scale: 0, y: 30, rotation: -25 },
            { opacity: 1, scale: 1, y: 0, rotation: 0, duration: 0.4, ease: "back.out(2.6)" }, ara);
        }
      });
    }
    return tl;
  }

  // Sense GSAP: les línies apareixen senceres i la paraula que sona canvia de color.
  function senseAnimacions(construides, estil, destacat, apilat, arrel, amaga) {
    return {
      seek(t) {
        if (amaga) arrel.style.opacity = t >= amaga[0] && t < amaga[1] ? 0 : 1;
        for (const b of construides) {
          const visible = t >= b.inici && t < b.final;
          b.el.style.visibility = visible ? "visible" : "hidden";
          if (!visible) continue;
          if (apilat) for (const f of b.files) f.p.style.opacity = t >= f.linia.inici ? 1 : 0;
          for (const x of b.seq) if (x.emoji) x.emoji.style.opacity = 1;
          if (destacat === "cap") continue;
          b.seq.forEach((x, j) => {
            const fi = j + 1 < b.seq.length ? b.seq[j + 1].w.inici : x.fila.linia.final;
            const sona = t >= x.w.inici && (destacat === "karaoke" || t < fi);
            if (x.caixa) x.caixa.style.opacity = sona ? 1 : 0;
            else x.t.style.color = sona ? estil.color_actiu : "";
          });
        }
        return this;
      },
    };
  }

  // --- El títol del ganxo ---------------------------------------------------------------------

  // «#3 canvis\n*ser creadora*\nnivell fàcil» → [[{text, clau}], …] (una llista de trossos per línia).
  function llegeixTitol(text) {
    return String(text || "").split("\n").map((l) => l.trim()).filter(Boolean).map((l) =>
      l.split("*").map((tros, k) => ({ text: tros, clau: k % 2 === 1 })).filter((x) => x.text));
  }

  // Una línia del títol en arc: el text segueix un camí (SVG), amb la mateixa lletra i colors.
  // `corba` > 0 fa un arc com el de Sant Martí; < 0, com un somriure.
  let arcs = 0;
  function liniaCorba(doc, p, trossos, costat, corba, estil, maquina, bloc) {
    const NS = "http://www.w3.org/2000/svg";
    const ample = (estil.amplada_maxima ?? 0.86) * AMPLADA;
    const lletra = (estil.mida ?? 0.07) * AMPLADA * (trossos.some((x) => x.clau) ? (Number(estil.clau_mida) || 1) : 1);
    const sageta = Math.abs(corba) * 0.2 * ample;
    const alcada = lletra * 1.3 + sageta;
    const base = corba > 0 ? lletra * 1.05 + sageta : lletra * 1.05;  // on comença i acaba l'arc
    const radi = (ample * ample / 4 + sageta * sageta) / (2 * sageta);
    const id = `tt-arc-${++arcs}`;
    const svg = doc.createElementNS(NS, "svg");
    svg.setAttribute("class", "tt-corba");
    svg.setAttribute("width", ample);
    svg.setAttribute("height", alcada);
    svg.setAttribute("viewBox", `0 0 ${ample} ${alcada}`);
    const cami = doc.createElementNS(NS, "path");
    cami.setAttribute("id", id);
    cami.setAttribute("d", `M 0 ${base} A ${radi} ${radi} 0 0 ${corba > 0 ? 1 : 0} ${ample} ${base}`);
    const text = doc.createElementNS(NS, "text");
    const sobre = doc.createElementNS(NS, "textPath");
    sobre.setAttribute("href", `#${id}`);
    sobre.setAttribute("startOffset", costat === "esquerra" ? "0%" : costat === "dreta" ? "100%" : "50%");
    text.setAttribute("text-anchor", costat === "esquerra" ? "start" : costat === "dreta" ? "end" : "middle");
    const lletres = [];
    for (const tros of trossos) {
      const t = doc.createElementNS(NS, "tspan");
      if (tros.clau) t.setAttribute("class", "tt-clau");
      if (maquina) {
        for (const c of tros.text) {
          const l = doc.createElementNS(NS, "tspan");
          l.setAttribute("class", "tt-c");
          l.textContent = c;
          t.append(l);
          lletres.push(l);
        }
      } else t.textContent = tros.text;
      sobre.append(t);
    }
    let cursor = null;
    if (maquina) {
      cursor = doc.createElementNS(NS, "tspan");
      cursor.setAttribute("class", "tt-cursor");
      cursor.textContent = "|";
      sobre.append(cursor);
    }
    text.append(sobre);
    const defs = doc.createElementNS(NS, "defs");  // el camí no es dibuixa: només el segueix el text
    defs.append(cami);
    svg.append(defs, text);
    p.append(svg);
    bloc.append(p);
    // SVG no dibuixa el text que no cap a l'arc: si és massa llarg, el fem més petit fins que hi cap.
    // Es mira ara i quan acaben d'arribar les lletres (el vídeo final dibuixa abans de tenir-les).
    const arc = 2 * radi * Math.asin(Math.min(1, ample / 2 / radi));
    const ajusta = () => {
      text.style.fontSize = "";
      const abans = lletres.map((l) => l.style.display);  // a màquina d'escriure, potser encara amagades
      for (const l of lletres) l.style.display = "inline";
      let llarg = 0;
      try { llarg = text.getComputedTextLength(); } catch { llarg = 0; }
      lletres.forEach((l, k) => { l.style.display = abans[k]; });
      if (llarg > arc * 0.96) text.style.fontSize = `${((arc * 0.96) / llarg).toFixed(4)}em`;
    };
    ajusta();
    if (doc.fonts && doc.fonts.status !== "loaded") doc.fonts.ready.then(ajusta);
    return { p, lletres, cursor };
  }

  function titol(arrel, t, estil, op) {
    op = op || {};
    const doc = arrel.ownerDocument;
    const gsap = global.gsap;
    posaCss(doc);
    arrel.textContent = "";
    arrel.className = "tt-capa";
    const linies = t ? llegeixTitol(t.text) : [];
    if (!linies.length) return op.tl || { seek() { return this; } };

    const inici = Number(t.inici) || 0;
    const final = Math.max(inici + 0.2, Number(t.final) || inici + (Number(estil.durada) || 3));
    const animacio = estil.animacio || "puja";
    const maquina = animacio === "maquina";
    const y = estil.posicio_y ?? 0.25;
    arrel.style.height = `${op.alcada || 1920}px`;
    const v = {
      "--tt-y": `${y * 100}%`, "--tt-ancora": `${-y * 100}%`,
      "--tt-amplada": `${(estil.amplada_maxima ?? 0.86) * 100}%`,
      "--tt-font": op.familia || "system-ui, sans-serif",
      "--tt-pes": Number(estil.pes) || 800,
      "--tt-mida": `${(estil.mida ?? 0.07) * AMPLADA}px`,
      "--tt-color": estil.color, "--tt-clau-color": estil.clau_color || estil.color,
      "--tt-clau-mida": Number(estil.clau_mida) || 1,
      "--tt-contorn": estil.contorn, "--tt-gruix": `${(estil.gruix_contorn || 0) * 2}em`,
      "--tt-majuscules": estil.majuscules ? "uppercase" : "none",
      "--tt-espaiat": `${Number(estil.espaiat) || 0}em`, "--tt-interlineat": Number(estil.interlineat) || 1,
      "--tt-ombra": estil.ombra !== false ? `0 0.05em 0.18em ${rgba(estil.contorn, 0.45)}` : "none",
      "--tt-fons": estil.fons === "enfosquit" ? rgba(estil.fons_color, 0.5) : (estil.fons_color || "#000000"),
      ...lletraClau(estil, "tt"),
    };
    for (const [k, valor] of Object.entries(v)) {
      if (valor == null) arrel.style.removeProperty(k); else arrel.style.setProperty(k, valor);
    }

    const enfosquit = estil.fons === "enfosquit" ? element(doc, "div", "tt-enfosquit") : null;
    if (enfosquit) arrel.append(enfosquit);
    const bloc = element(doc, "div", `tt-bloc${estil.fons === "pindola" ? " tt-pindola" : ""}`);
    arrel.append(bloc);
    let torn = 0;
    const alinea = (trossos) => {
      const a = ["esquerra", "dreta", "esglao"].includes(estil.alineacio) ? estil.alineacio : "centre";
      if (a !== "esglao") return a;
      if (trossos.every((x) => x.clau)) return "centre";
      return torn++ % 2 ? "dreta" : "esquerra";
    };
    const corba = Math.max(-1, Math.min(1, Number(estil.corba) || 0));
    const quines = estil.corba_linies || "primera";
    const esCorba = (k) => corba !== 0 &&
      (quines === "totes" || (quines === "darrera" ? k === linies.length - 1 : k === 0));
    const files = linies.map((trossos, k) => {
      const costat = alinea(trossos);
      const p = element(doc, "p", `tt-fila ts-al-${costat}${trossos.some((x) => x.clau) ? " tt-te-clau" : ""}`);
      if (esCorba(k)) return liniaCorba(doc, p, trossos, costat, corba, estil, maquina, bloc);
      const dins = element(doc, "span", "tt-dins");
      p.append(dins);
      const lletres = [];
      for (const tros of trossos) {
        const s = element(doc, "span", `tt-text${tros.clau ? " tt-clau" : ""}`, maquina ? null : tros.text);
        if (maquina) {
          for (const c of tros.text) { const l = element(doc, "span", "tt-c", c); s.append(l); lletres.push(l); }
        }
        dins.append(s);
      }
      const cursor = maquina ? element(doc, "span", "tt-cursor", "|") : null;
      if (cursor) dins.append(cursor);
      bloc.append(p);
      return { p, lletres, cursor };
    });

    if (!gsap) {  // sense animacions: el títol hi és sencer mentre dura
      for (const f of files) for (const l of f.lletres) l.style.display = "inline";
      if (enfosquit) enfosquit.style.opacity = 1;
      return { seek(s) { arrel.style.visibility = s >= inici && s < final ? "visible" : "hidden"; return this; } };
    }

    const tl = op.tl || gsap.timeline({ paused: true });
    tl.set(arrel, { visibility: "visible" }, inici);
    tl.set(arrel, { visibility: "hidden" }, final);
    if (enfosquit) {
      tl.fromTo(enfosquit, { opacity: 0 }, { opacity: 1, duration: 0.3, ease: "power1.out" }, inici);
      tl.fromTo(enfosquit, { opacity: 1 }, { opacity: 0, duration: 0.25, immediateRender: false }, Math.max(inici, final - 0.25));
    }
    tl.fromTo(bloc, { opacity: 1 }, { opacity: 0, duration: 0.2, immediateRender: false }, Math.max(inici, final - 0.2));
    files.forEach((f, k) => {
      const t0 = inici + 0.1 * k;
      if (animacio === "puja") tl.fromTo(f.p, { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.45, ease: "power3.out" }, t0);
      else if (animacio === "pop") tl.fromTo(f.p, { opacity: 0, scale: 0.7 }, { opacity: 1, scale: 1, duration: 0.35, ease: "back.out(2)" }, inici + 0.08 * k);
      else if (animacio === "fos") tl.fromTo(f.p, { opacity: 0 }, { opacity: 1, duration: 0.4, ease: "power1.out" }, inici + 0.12 * k);
      else if (animacio === "cortina") {
        tl.fromTo(f.p, { clipPath: "inset(-30% 100% -30% 0%)" }, { clipPath: "inset(-30% -5% -30% -5%)", duration: 0.5, ease: "power2.out" }, inici + 0.12 * k);
      }
    });
    if (maquina) {
      // Lletra a lletra, amb el cursor al final del que ja s'ha escrit; quan acaba, el cursor fa pampallugues.
      const total = files.reduce((n, f) => n + f.lletres.length, 0) || 1;
      const pas = Math.min(0.06, Math.max(0.015, ((final - inici) * 0.55) / total));
      let ara = inici + 0.2;
      files.forEach((f, k) => {
        tl.set(f.cursor, { display: "inline" }, ara);
        for (const l of f.lletres) { tl.set(l, { display: "inline" }, ara); ara += pas; }
        if (k + 1 < files.length) { tl.set(f.cursor, { display: "none" }, ara); ara += pas * 3; }
      });
      const darrer = files[files.length - 1].cursor;
      for (let s = ara + 0.3; s < final - 0.1; s += 0.5) {
        tl.set(darrer, { opacity: 0 }, s);
        tl.set(darrer, { opacity: 1 }, s + 0.25);
      }
    }
    return tl;
  }

  global.TallatSubtitols = { construeix, titol, llegeixTitol, AMPLADA };
})(typeof window !== "undefined" ? window : globalThis);
