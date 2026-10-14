/* tallat · subtítols animats.
 *
 * El mateix codi dibuixa els subtítols a la vista prèvia de la pàgina de revisió i al
 * vídeo final (dins d'una composició de HyperFrames): el que es veu és el que surt.
 * Treballa sempre sobre una caixa de 1080 px d'amplada; qui el fa servir l'escala.
 *
 *   const tl = TallatSubtitols.construeix(element, linies, estil, { familia });
 *   tl.seek(segons);
 *
 * `linies`: [{inici, final, paraules: [{text, inici, final, clau, emoji}]}] en temps del muntatge.
 * Fa servir GSAP si hi és; si no (sense internet), en dona una versió sense animacions.
 */
(function (global) {
  "use strict";

  const AMPLADA = 1080;
  const ESTILS_CSS = `
.ts-capa { position: absolute; left: 0; top: 0; width: ${AMPLADA}px; pointer-events: none; }
.ts-linia { position: absolute; inset: 0; visibility: hidden; }
.ts-text {
  position: absolute; left: 50%; top: var(--ts-y); width: var(--ts-amplada); margin: 0;
  transform: translate(-50%, -50%); text-align: center; line-height: 1.12;
  font-family: var(--ts-font); font-weight: var(--ts-pes); font-size: var(--ts-mida);
  color: var(--ts-color); text-transform: var(--ts-majuscules); font-kerning: normal;
}
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
.ts-clau .ts-t { font-size: 1.4em; line-height: 1; }
.ts-normal .ts-clau .ts-t, .ts-neo .ts-clau .ts-t { color: var(--ts-actiu); }
.ts-d-caixa .ts-p, .ts-d-gran .ts-p { margin: 0 0.07em; }
.ts-caixa-p {
  position: absolute; inset: -0.04em -0.12em -0.02em; z-index: 0; border-radius: 0.18em;
  background: var(--ts-actiu); opacity: 0;
}
.ts-emoji {
  position: absolute; left: 50%; bottom: 86%; width: 1.3em; margin-left: -0.65em; z-index: 2;
  font-size: 1.35em; line-height: 1; text-align: center; font-style: normal; font-weight: 400;
  -webkit-text-stroke: 0; text-shadow: none; -webkit-text-fill-color: initial; opacity: 0;
}`;

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

    arrel.className = `ts-capa ts-${aspecte} ts-d-${destacat}`;
    arrel.style.height = `${op.alcada || 1920}px`;
    const v = {
      "--ts-y": `${(op.y ?? estil.posicio_y) * 100}%`,
      "--ts-amplada": `${(op.amplada ?? estil.amplada_maxima) * 100}%`,
      "--ts-font": op.familia || "system-ui, sans-serif",
      "--ts-pes": pes,
      "--ts-mida": `${(op.mida ?? estil.mida) * AMPLADA}px`,
      "--ts-color": estil.color,
      "--ts-actiu": estil.color_actiu,
      "--ts-contorn": estil.contorn,
      "--ts-gruix": `${(estil.gruix_contorn || 0) * 2}em`,
      "--ts-majuscules": estil.majuscules ? "uppercase" : "none",
      "--ts-ombra": ombra ? "0 0.06em 0.2em rgba(0, 0, 0, 0.45)" : "none",
      "--ts-ombra-filtre": ombra ? "drop-shadow(0 0.04em 0.1em rgba(0, 0, 0, 0.5))" : "none",
      "--ts-fons": rgba(estil.fons_color, 0.62),
    };
    for (const [k, valor] of Object.entries(v)) arrel.style.setProperty(k, valor);
    arrel.textContent = "";

    const construides = linies.map((linia) => {
      const el = element(doc, "div", "ts-linia");
      const text = element(doc, "p", "ts-text");
      const fons = estil.fons === "pindola" ? element(doc, "span", "ts-fons") : null;
      const cont = fons || text;
      if (fons) text.append(fons);
      const paraules = linia.paraules.map((w, j) => {
        const p = element(doc, "span", `ts-p${estil.clau_grans && w.clau ? " ts-clau" : ""}`);
        const caixa = destacat === "caixa" ? element(doc, "span", "ts-caixa-p") : null;
        if (caixa) p.append(caixa);
        const t = element(doc, "span", "ts-t", w.text);
        p.append(t);
        const emoji = estil.emojis && w.emoji ? element(doc, "span", "ts-emoji", w.emoji) : null;
        if (emoji) p.append(emoji);
        if (j) cont.append(" ");
        cont.append(p);
        return { w, p, t, caixa, emoji };
      });
      el.append(text);
      arrel.append(el);
      return { linia, el, text, fons, paraules };
    });

    if (!gsap) return senseAnimacions(construides, estil, destacat);

    const tl = op.tl || gsap.timeline({ paused: true });
    construides.forEach(({ linia, el, text, fons, paraules }, i) => {
      // Les línies es mostren i s'amaguen amb un canvi instantani a l'inici i al final.
      tl.set(el, { visibility: "visible" }, linia.inici);
      tl.set(el, { visibility: "hidden" }, linia.final);
      if (fons) tl.fromTo(fons, { opacity: 0, scale: 0.94 }, { opacity: 1, scale: 1, duration: 0.16, ease: "power2.out" }, linia.inici);
      if (deCop) {
        entra(tl, animacio === "cortina" ? text : paraules.map((x) => x.p), linia.inici, animacio, i, pes);
      } else {
        paraules.forEach((x, j) => entra(tl, x.p, x.w.inici, animacio, i * 7 + j, pes));
      }
      paraules.forEach((x, j) => {
        const ara = x.w.inici;
        const fi = j + 1 < paraules.length ? paraules[j + 1].w.inici : linia.final;
        if (destacat === "color") {
          tl.set(x.t, { color: estil.color_actiu }, ara);
          tl.set(x.t, { color: x.p.classList.contains("ts-clau") ? estil.color_actiu : estil.color }, fi);
        } else if (destacat === "karaoke") {
          tl.set(x.t, { color: estil.color_actiu }, ara);  // es queda pintada fins al final de la línia
        } else if (destacat === "caixa") {
          tl.fromTo(x.caixa, { opacity: 0, scale: 0.7 }, { opacity: 1, scale: 1, duration: 0.12, ease: "back.out(2)" }, ara);
          tl.to(x.caixa, { opacity: 0, duration: 0.08 }, Math.max(ara + 0.12, fi));
          if (aspecte !== "degradat") {  // damunt la caixa, la lletra que es llegeixi millor
            tl.set(x.t, { color: contrast(estil.color_actiu), textShadow: "none", webkitTextStrokeWidth: 0 }, ara);
            tl.set(x.t, { color: x.p.classList.contains("ts-clau") ? estil.color_actiu : estil.color,
              textShadow: "", webkitTextStrokeWidth: "" }, fi);
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
    });
    return tl;
  }

  // Sense GSAP: les línies apareixen senceres i la paraula que sona canvia de color.
  function senseAnimacions(construides, estil, destacat) {
    return {
      seek(t) {
        for (const { linia, el, paraules } of construides) {
          const visible = t >= linia.inici && t < linia.final;
          el.style.visibility = visible ? "visible" : "hidden";
          if (!visible || destacat === "cap") continue;
          paraules.forEach((x, j) => {
            const fi = j + 1 < paraules.length ? paraules[j + 1].w.inici : linia.final;
            const sona = t >= x.w.inici && (destacat === "karaoke" || t < fi);
            if (x.caixa) x.caixa.style.opacity = sona ? 1 : 0;
            else x.t.style.color = sona ? estil.color_actiu : "";
          });
          for (const x of paraules) if (x.emoji) x.emoji.style.opacity = 1;
        }
        return this;
      },
    };
  }

  global.TallatSubtitols = { construeix, AMPLADA };
})(typeof window !== "undefined" ? window : globalThis);
