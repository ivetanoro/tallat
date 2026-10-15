"use strict";
// tallat · pàgina de revisió. Tot passa en aquest ordinador: el servidor local desa cada canvi.

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

// Cada petició que canvia alguna cosa porta el codi que el servidor ha posat a la pàgina (perquè
// cap altra web no li pugui enviar ordres) i diu a quin projecte va (per si en una altra pestanya
// s'ha obert un altre projecte).
const TOKEN = document.querySelector('meta[name="tallat-token"]')?.content || "";
const capcaleres = (extra = {}) => ({ "X-Tallat-Token": TOKEN, "X-Tallat-Projecte": P?.clau_projecte || "", ...extra });

async function api(ruta, dades) {
  const opcions = dades === undefined ? {} : {
    method: "POST", headers: capcaleres({ "Content-Type": "application/json" }), body: JSON.stringify(dades),
  };
  return resposta(await fetch(ruta, opcions));
}

async function resposta(r) {
  const json = await r.json().catch(() => ({}));
  if (r.status === 409 && json.error === "projecte-canviat") {
    avis("En una altra pestanya s'ha obert un altre projecte. Torno a carregar aquesta pàgina.", 4000);
    setTimeout(() => location.reload(), 1500);
  }
  if (!r.ok) throw Object.assign(new Error(json.error || r.statusText), { codi: r.status, dades: json });
  return json;
}

const fmt = (s) => {
  s = Math.max(0, s || 0);
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
};
const fmtSegons = (s) => s.toFixed(1).replace(".", ",") + " s";
const limita = (v, a, b) => Math.min(b, Math.max(a, v));
const copia = (o) => JSON.parse(JSON.stringify(o));
const arrodoneix = (n) => Math.round(n * 100) / 100;

// --- Registre de diagnòstic ---------------------------------------------------------------
// La pàgina apunta què fa el reproductor; el servidor ho desa a registre-pagina.log
// dins la carpeta del projecte (no surt de l'ordinador). Serveix per trobar errors.
const registreCua = [];
const registreInici = performance.now();
function registre(tipus, dades = {}) {
  registreCua.push({ t: Math.round(performance.now() - registreInici), tipus, ...dades });
  if (registreCua.length > 600) registreCua.splice(0, 200);
}
setInterval(() => {
  if (!registreCua.length) return;
  const events = registreCua.splice(0);
  fetch("/api/registre", { method: "POST", headers: capcaleres({ "Content-Type": "application/json" }),
    body: JSON.stringify({ events }) }).catch(() => {});
}, 1500);
const ev = (v) => (v ? { id: v.id.replace("video-", ""), t: +v.currentTime.toFixed(3), pausat: v.paused,
  ready: v.readyState, amagat: v.classList.contains("amagat"), muted: v.muted } : null);
window.addEventListener("error", (e) => registre("error-js", { msg: e.message, linia: e.lineno }));
window.addEventListener("unhandledrejection", (e) => registre("promesa-rebutjada", { msg: String(e.reason) }));

const ICONES = {
  treu: '<svg viewBox="0 0 16 16"><path d="M4 8h8"/></svg>',
  deixa: '<svg viewBox="0 0 16 16"><path d="m3.5 8.5 3 3 6-7"/></svg>',
  play: '<svg viewBox="0 0 16 16"><path d="M5 3.5v9l7-4.5z" fill="currentColor" stroke="none"/></svg>',
  finder: '<svg viewBox="0 0 16 16"><path d="M2.5 4.5h4l1.5 1.5h5.5v6.5h-11z"/></svg>',
  esborra: '<svg viewBox="0 0 16 16"><path d="m4.5 4.5 7 7m0-7-7 7"/></svg>',
  recorda: '<svg viewBox="0 0 16 16"><path d="M5 2.5h6v11l-3-2.2-3 2.2z"/></svg>',
};
const MOTIUS = {
  usuari: "Tret per tu", farciment: "Farciment (tret automàticament)", tall: "Paraula a mig dir (treta automàticament)",
  muntatge: "Fora del reel (primer muntatge)", instruccio: "Instrucció de veu (treta automàticament)",
};
const AUTOMATICS = new Set(["farciment", "tall", "instruccio"]); // es pinten en taronja
const PROPOSTES = { "farciment?": "Possible farciment", "expressiu?": "Sons repetits", "repeticio?": "Paraules repetides" };
const QUALITATS = { esborrany: "Esborrany", "1080": "1080", "4k": "4K" };

// --- Estat de la pàgina -----------------------------------------------------------

let P = null;              // projecte (paraules, paràgrafs, origen…)
let estat = null;          // estat d'edició (es desa a edicio.json)
let trams = [];            // trossos conservats, en temps del vídeo original
let acum = [];             // on comença cada tros dins del muntatge
let duradaFinal = 0;
const desfer = [];
const refer = [];
let mode = "talla";
let vista = "directe";
const spans = new Map();   // id de paraula → <span>
let paragrafsEl = [];      // [{el, ids}] per marcar les frases tretes senceres
let esborrany = null;      // {nom, trams, acum, durada} de la versió que es mira
let liniesSub = [];        // subtítols en temps del muntatge (calculats pel servidor)
let estilSub = null;       // estil dels subtítols (de ~/.tallat/brand.json)
let estilsPredefinits = []; // [{id, nom, descripcio, valors}] de config/estils_subtitols.json
let fontsKit = [];         // les lletres del kit: [{familia, pes, url}]
let bibliotecaLletres = { lletres: [], grups: {} };  // les lletres gratuïtes que es poden baixar
let estilTitol = null;      // l'estil del títol del ganxo (del kit)
let estilsTitol = [];       // els estils de títol predefinits
let titolMuntatge = null;   // el títol d'aquest vídeo en temps del muntatge: {text, inici, final}, o null
let editantTitol = false;   // el panell de l'estil del títol és obert
let previaTitol = null;
const MOSTRA_TITOL = { text: "El teu\n*títol*\naquí", inici: 0, final: 3 };  // mentre es tria l'estil sense títol
let editantEstil = false;  // el panell d'estil és obert: el reproductor en mostra una línia d'exemple
let instruccions = [];     // instruccions de veu «Claude, …»
let zoomsTram = [];        // quins trossos porten zoom
let brollsMuntatge = [];   // b-rolls situats al muntatge: [{id, inici, durada, url}]
let stickersMuntatge = []; // stickers situats al muntatge: [{id, inici, durada, url}]
let biblioteca = { broll: [], sticker: [] };  // fitxers de ~/.tallat/broll/ i ~/.tallat/stickers/
let notes = [];
let gust = [];             // regles del teu gust (~/.tallat/gust.json)
let seccionsGust = {};
let darrerDesplacamentManual = 0;

// --- Desar ----------------------------------------------------------------------------

let cua = Promise.resolve();
let pendent = false;
let errorDesant = null;  // si l'últim desament ha fallat (fins que un altre surti bé)
function sincronitza() {
  if (pendent) return;     // diversos canvis seguits viatgen en una sola petició
  pendent = true;
  cua = cua.then(async () => {
    pendent = false;
    try {
      const r = await api("/api/estat", estat);
      errorDesant = null;
      estat.revisio = r.estat.revisio;
      aplicaTrams(r);
      if (!pendent && escoltaPendent != null) { escoltaTall(escoltaPendent); escoltaPendent = null; }
    } catch (e) {
      if (e.codi !== 409 || e.dades?.error === "projecte-canviat") throw e;
      // La pàgina també és oberta en una altra pestanya i allà s'ha desat després.
      errorDesant = null;
      estat = e.dades.estat;
      desfer.length = 0;
      refer.length = 0;
      aplicaTrams(e.dades);
      refresca(true);
      marcaPausa();
      avis("Hi ha hagut canvis des d'un altre lloc (una altra pestanya o Claude, des del xat). He carregat els més nous.", 6000);
    }
  }).catch((e) => { errorDesant = e; avis("No s'ha pogut desar: " + e.message); });
}

// Abans d'exportar, s'han d'haver desat tots els canvis, i bé: si no, el vídeo sortiria sense els
// últims talls. Si mentre s'espera n'arriba un altre, també s'espera.
async function canvisDesats() {
  let esperada;
  do {
    esperada = cua;
    await esperada;
  } while (esperada !== cua);
  if (errorDesant) throw new Error("No s'han pogut desar els últims canvis i el vídeo no els tindria. Torna-ho a provar.");
}

// Claude també pot fer canvis des del xat (paraules destacades, el kit…): la pàgina hi pregunta
// sovint i, si n'hi ha i aquí no hi ha res a mig desar, els carrega.
let versioEstil = null;
async function miraNovetats() {
  if (document.hidden || !estat) return;
  const esperada = cua;
  await esperada;
  if (esperada !== cua || pendent) return;
  try {
    const n = await (await fetch("/api/novetats")).json();
    if (n.clau_projecte !== P.clau_projecte || esperada !== cua || pendent) return;
    if (versioEstil == null) versioEstil = n.estil;
    if (n.estil !== versioEstil) {
      respostaEstil(await api("/api/marca/info"));
    }
    if (n.revisio > estat.revisio) {
      const r = await api("/api/instantania");
      if (esperada !== cua || pendent) return;
      estat = r.estat;
      desfer.length = 0;
      refer.length = 0;
      aplicaTrams(r);
      refresca(true);
      marcaPausa();
      avis("Claude ha fet canvis al vídeo. Ja els veus aquí.", 4000);
    }
  } catch { /* el servidor no respon: ja ho dirà la propera acció */ }
}

function canvia(fn, { repinta = false } = {}) {
  desfer.push(copia(estat));
  if (desfer.length > 300) desfer.shift();
  refer.length = 0;
  fn(estat);
  refresca(repinta);
  sincronitza();
}

function refresca(repinta) {
  if (repinta) pintaText(); else actualitzaParaules();
  pintaTitol();
  actualitzaPropostes();
  actualitzaPauses();
  $("#desfes").disabled = !desfer.length;
  $("#refes").disabled = !refer.length;
}

function desfes() {
  if (!desfer.length) return;
  refer.push(copia(estat));
  estat = { ...desfer.pop(), revisio: estat.revisio };
  refresca(true);
  marcaPausa();
  marcaSubtitols();
  sincronitza();
  avis("Desfet");
}

function refes() {
  if (!refer.length) return;
  desfer.push(copia(estat));
  estat = { ...refer.pop(), revisio: estat.revisio };
  refresca(true);
  marcaPausa();
  marcaSubtitols();
  sincronitza();
}

function aplicaTrams(r) {
  if (r.subtitols) { liniesSub = r.subtitols; previaBruta = true; marcaClaus(); }
  if ("titol" in r) { titolMuntatge = r.titol; previaBruta = true; }
  if (r.paragrafs && P && r !== P && JSON.stringify(r.paragrafs) !== JSON.stringify(P.paragrafs)) {
    P.paragrafs = r.paragrafs;  // l'ordre dels paràgrafs ha canviat (moure'ls, desfer-ho, una altra pestanya)
    pintaText();
  }
  if (r.zooms) zoomsTram = r.zooms;
  if (r.brolls) brollsMuntatge = r.brolls;
  if (r.stickers) stickersMuntatge = r.stickers;
  if (r.zoom) $(".pantalla").style.setProperty("--zoom", r.zoom);
  if (r.instruccions) { instruccions = r.instruccions; if (P) pintaInstruccions(); }
  trams = r.trams;
  duradaFinal = r.durada_final;
  registre("trams", { n: trams.length, primers: trams.slice(0, 3), durada: duradaFinal });
  acum = [];
  let t = 0;
  for (const [a, b] of trams) { acum.push(t); t += b - a; }
  $("#durada-final").textContent = fmt(duradaFinal);
  $("#trossos").textContent = `${trams.length} ${trams.length === 1 ? "tros" : "trossos"}`;
  if (vista === "directe") { pintaMarques(trams, acum, duradaFinal); recolloca(); }
}

// --- Transcripció ---------------------------------------------------------------------

const esFora = (id) => String(id) in estat.esborrades;

function pintaText() {
  const cont = $("#transcripcio");
  cont.textContent = "";
  spans.clear();
  paragrafsEl = [];
  P.paragrafs.forEach((ids, k) => {
    const par = document.createElement("p");
    par.className = "paragraf";
    paragrafsEl.push({ el: par, ids });
    par.append(nansa(k));
    const marca = document.createElement("button");
    marca.className = "marca-temps";
    marca.textContent = fmt(P.paraules[ids[0]].inici);
    marca.title = "Escolta des d'aquí";
    marca.addEventListener("click", () => reprodueixDes(ids[0]));
    par.append(marca);
    for (const id of ids) {
      const pausa = pausaAbans(id);
      if (pausa) par.append(pausa, " ");
      const s = document.createElement("span");
      s.className = "p";
      s.dataset.id = id;
      spans.set(id, s);
      par.append(s, " ");
    }
    cont.append(par);
  });
  actualitzaParaules();
  marcaClaus();
}

// --- Canviar l'ordre dels paràgrafs ---------------------------------------------------------
// Cada paràgraf té una nansa: arrossegant-la (o amb les fletxes) el paràgraf passa a sonar en
// un altre lloc. L'ordre es desa a estat.ordre (trossos d'ids), com el dels reels muntats.

const ICONA_NANSA = '<svg viewBox="0 0 10 16" aria-hidden="true">' +
  [3, 8, 13].map((y) => `<circle cx="2.5" cy="${y}" r="1.4"/><circle cx="7.5" cy="${y}" r="1.4"/>`).join("") + "</svg>";

function nansa(k) {
  const b = document.createElement("button");
  b.className = "nansa";
  b.innerHTML = ICONA_NANSA;
  b.title = "Arrossega per canviar l'ordre";
  b.setAttribute("aria-label", "Mou el paràgraf (amb les fletxes amunt i avall)");
  b.addEventListener("pointerdown", (e) => comencaMou(e, k));
  b.addEventListener("pointermove", segueixMou);
  b.addEventListener("pointerup", acabaMou);
  b.addEventListener("pointercancel", () => deixaMou());
  b.addEventListener("keydown", (e) => {
    if (e.key === "ArrowUp" && k > 0) { e.preventDefault(); mouParagraf(k, k - 1, true); }
    if (e.key === "ArrowDown" && k < P.paragrafs.length - 1) { e.preventDefault(); mouParagraf(k, k + 2, true); }
  });
  return b;
}

let mou = null;  // {de, a, y, mogut, el, indicador, vel}

function comencaMou(e, k) {
  if (e.button !== 0 || mode !== "talla") return;
  e.preventDefault();
  e.currentTarget.setPointerCapture(e.pointerId);
  mou = { de: k, a: null, y: e.clientY, mogut: false, el: paragrafsEl[k].el, indicador: null, vel: 0, darrerY: e.clientY };
}

// On aniria el paràgraf: davant del paràgraf i, o al final (i = nombre de paràgrafs).
function llocDeMou(y) {
  for (let i = 0; i < paragrafsEl.length; i++) {
    const r = paragrafsEl[i].el.getBoundingClientRect();
    if (y < r.top + r.height / 2) return i;
  }
  return paragrafsEl.length;
}

function pintaIndicador() {
  const i = llocDeMou(mou.darrerY);
  mou.a = i;
  const util = i !== mou.de && i !== mou.de + 1;
  mou.indicador.hidden = !util;
  if (!util) return;
  const ref = paragrafsEl[Math.min(i, paragrafsEl.length - 1)].el;
  const top = i < paragrafsEl.length ? ref.offsetTop - 8 : ref.offsetTop + ref.offsetHeight + 4;
  mou.indicador.style.top = `${top}px`;
}

function segueixMou(e) {
  if (!mou) return;
  mou.darrerY = e.clientY;
  if (!mou.mogut) {
    if (Math.abs(e.clientY - mou.y) < 4) return;
    mou.mogut = true;
    mou.el.classList.add("mou");
    document.body.classList.add("movent");
    mou.indicador = document.createElement("div");
    mou.indicador.className = "indicador-mou";
    $("#transcripcio").append(mou.indicador);
    requestAnimationFrame(desplacaMou);
  }
  // A prop de dalt o de baix, la transcripció es desplaça sola.
  const caixa = $(".text").getBoundingClientRect();
  const dalt = caixa.top + $(".eines").offsetHeight + 40;
  mou.vel = e.clientY < dalt ? -Math.min(18, (dalt - e.clientY) / 3)
    : e.clientY > caixa.bottom - 60 ? Math.min(18, (e.clientY - caixa.bottom + 60) / 3) : 0;
  pintaIndicador();
}

function desplacaMou() {
  if (!mou?.mogut) return;
  if (mou.vel) {
    $(".text").scrollTop += mou.vel;
    darrerDesplacamentManual = performance.now();
    pintaIndicador();
  }
  requestAnimationFrame(desplacaMou);
}

function acabaMou() {
  if (!mou) return;
  const { mogut, de, a } = mou;
  deixaMou();
  if (mogut && a != null && a !== de && a !== de + 1) mouParagraf(de, a);
}

function deixaMou() {
  if (!mou) return;
  mou.el.classList.remove("mou");
  mou.indicador?.remove();
  document.body.classList.remove("movent");
  mou = null;
}

// Mou el paràgraf «de» davant del paràgraf «a» (a = nombre de paràgrafs: al final).
function mouParagraf(de, a, teclat = false) {
  const llista = P.paragrafs.slice();
  const [mogut] = llista.splice(de, 1);
  const on = a > de ? a - 1 : a;
  llista.splice(on, 0, mogut);
  // Quines paraules formen part del muntatge: en un reel, les del seu ordre; si no, totes.
  const dins = new Set(mogut);
  if (estat.ordre) for (const [x, y] of estat.ordre) for (let i = +x; i <= +y; i++) dins.add(i);
  else for (const ids of llista) for (const id of ids) dins.add(id);
  const rangs = [];
  for (const ids of llista) {
    if (!ids.some((id) => dins.has(id))) continue;
    const [x, y] = [ids[0], ids[ids.length - 1]];
    const darrer = rangs[rangs.length - 1];
    if (darrer && darrer[1] + 1 === x) darrer[1] = y; else rangs.push([x, y]);
  }
  const natural = !P.reel_actual && rangs.length === 1 && rangs[0][0] === 0 && rangs[0][1] === P.paraules.length - 1;
  P.paragrafs = llista;
  canvia((e) => { e.ordre = natural ? null : rangs; }, { repinta: true });
  registre("mou-paragraf", { de, a, ordre: natural ? null : rangs.length });
  if (teclat) paragrafsEl[on]?.el.querySelector(".nansa").focus();
  else avis(natural ? "Tot torna a sonar en l'ordre de la gravació." : "Paràgraf mogut. Prem ⌘Z per desfer-ho.");
}

function pausaAbans(id) {
  const max = estat.pausa_maxima;
  if (!max || id === 0) return null;
  const silenci = P.paraules[id].inici - P.paraules[id - 1].final;
  if (silenci <= max) return null;
  const b = document.createElement("button");
  b.className = "pausa";
  b.dataset.pausa = id;
  b.textContent = fmtSegons(silenci);
  return b;
}

function actualitzaPauses() {
  for (const b of $$(".pausa")) {
    const id = +b.dataset.pausa;
    // Un silenci només sona si les dues paraules del costat es queden.
    b.hidden = esFora(id) || esFora(id - 1);
    const sencera = estat.pauses_mantingudes.includes(id);
    b.classList.toggle("sencera", sencera);
    b.title = sencera ? "Silenci sencer. Clica per escurçar-lo." :
      `Silenci escurçat a ${fmtSegons(estat.pausa_maxima)}. Clica per deixar-lo sencer.`;
  }
}

function actualitzaParaules() {
  for (const [id, s] of spans) {
    const k = String(id);
    const motiu = estat.esborrades[k];
    const proposta = !motiu && estat.propostes[k];
    const correccio = estat.correccions[k];
    s.classList.toggle("fora", !!motiu);
    s.classList.toggle("auto", AUTOMATICS.has(motiu));
    s.classList.toggle("proposta", !!proposta);
    s.classList.toggle("corregida", correccio != null);
    const text = correccio ?? P.paraules[id].text;
    if (s.textContent !== text) s.textContent = text;
    s.title = motiu ? MOTIUS[motiu] || motiu
      : proposta ? `${PROPOSTES[proposta] || "Proposta"}: toca-la per treure-la`
      : correccio != null ? `Original: ${P.paraules[id].text}` : "";
  }
  for (const { el, ids } of paragrafsEl) el.classList.toggle("tot-fora", ids.every(esFora));
}

function commuta(ids, treure) {
  demanaEscolta(Math.min(...ids));
  canvia((e) => {
    for (const id of ids) {
      const k = String(id);
      delete e.propostes[k];
      if (treure) {
        e.esborrades[k] = "usuari";
        e.mantingudes = e.mantingudes.filter((x) => x !== id);
      } else {
        const motiu = e.esborrades[k];
        delete e.esborrades[k];
        if (motiu && motiu !== "usuari" && !e.mantingudes.includes(id)) e.mantingudes.push(id);
      }
    }
  });
}

// Tocar o arrossegar per sobre de les paraules
let seleccio = null;
const marcades = new Set();

// Una selecció va de la primera paraula a l'última tal com es veuen a la pàgina. Amb paràgrafs
// reordenats, els números de paraula no van seguits: «de la 108 a la 1» són 108, 109, 0 i 1.
let ordreVisual = new Map();  // id → posició a la pàgina (es calcula en començar cada selecció)

function llegeixOrdreVisual() {
  ordreVisual = new Map([...$("#transcripcio").querySelectorAll(".p")].map((s, i) => [+s.dataset.id, i]));
}

function idsEntre(a, b) {
  const ids = [...ordreVisual.keys()];
  const [i, j] = [ordreVisual.get(a), ordreVisual.get(b)].sort((x, y) => x - y);
  return i === undefined || j === undefined ? [] : ids.slice(i, j + 1);
}

function pintaSeleccio() {
  for (const id of marcades) spans.get(id)?.classList.remove("seleccio");
  marcades.clear();
  const ids = seleccio ? idsEntre(seleccio.inici, seleccio.fi) : seleccioFeta;
  for (const id of ids || []) { spans.get(id)?.classList.add("seleccio"); marcades.add(id); }
}

// Clic: anar a la paraula i reproduir des d'allà. Clic dret (o control + clic): treure-la o
// recuperar-la; arrossegant amb el botó dret, totes les que s'hi passen. Arrossegar amb el
// botó esquerre selecciona unes quantes paraules; després, clic dret o ⌫.
let seleccioFeta = null;  // ids de l'última selecció arrossegada, en l'ordre de la pàgina

function commutaIds(ids) {
  if (ids.length) commuta(ids, ids.some((id) => !esFora(id)));
}

function deixaSeleccio() {
  seleccio = null;
  seleccioFeta = null;
  pintaSeleccio();
}

function instalaText() {
  const cont = $("#transcripcio");
  cont.addEventListener("pointerdown", (e) => {
    const dret = e.button === 2 || (e.button === 0 && e.ctrlKey);
    if (e.button !== 0 && !dret) return;
    if (e.target.closest(".nansa")) return;  // moure paràgrafs: ho fa la nansa mateixa
    if (dret) {
      // Al Mac el menú contextual surt en prémer: l'aturem a «contextmenu» i tallem en deixar anar.
      const s = e.target.closest(".p");
      if (!s || mode !== "talla") return;
      e.preventDefault();
      const id = +s.dataset.id;
      if (seleccioFeta?.includes(id)) {
        commutaIds(seleccioFeta);  // clic dret a sobre d'una selecció feta: tota de cop
        deixaSeleccio();
        return;
      }
      seleccioFeta = null;
      llegeixOrdreVisual();
      seleccio = { inici: id, fi: id, mogut: false, dret: true };
      pintaSeleccio();
      return;
    }
    const pausa = e.target.closest(".pausa");
    if (pausa) {
      const id = +pausa.dataset.pausa;
      canvia((est) => {
        est.pauses_mantingudes = est.pauses_mantingudes.includes(id)
          ? est.pauses_mantingudes.filter((x) => x !== id) : [...est.pauses_mantingudes, id];
      });
      return;
    }
    const s = e.target.closest(".p");
    if (!s) { seleccioFeta = null; pintaSeleccio(); return; }
    const id = +s.dataset.id;
    if (mode === "corregeix") { e.preventDefault(); editaParaula(s, id); return; }
    if (mode === "destaca") { e.preventDefault(); commutaDestacada(id); return; }
    e.preventDefault();
    seleccioFeta = null;
    llegeixOrdreVisual();
    seleccio = { inici: id, fi: id, mogut: false };
    pintaSeleccio();
  });
  document.addEventListener("pointermove", (e) => {
    if (!seleccio) return;
    const s = document.elementFromPoint(e.clientX, e.clientY)?.closest?.(".p");
    if (s && +s.dataset.id !== seleccio.fi) { seleccio.fi = +s.dataset.id; seleccio.mogut = true; pintaSeleccio(); }
  });
  document.addEventListener("pointerup", () => {
    if (!seleccio) return;
    const { inici, fi, mogut, dret } = seleccio;
    if (dret) {  // botó dret: treu (o recupera) la paraula o totes les que s'hi han arrossegat
      const ids = idsEntre(inici, fi);
      deixaSeleccio();
      commutaIds(ids);
      return;
    }
    if (!mogut) {  // un clic: hi anem i sona des d'allà
      seleccio = null;
      pintaSeleccio();
      reprodueixDes(inici);
      return;
    }
    seleccioFeta = idsEntre(inici, fi);  // queda marcada fins al clic dret o ⌫
    seleccio = null;  // l'arrossegament s'ha acabat: moure el ratolí ja no la canvia
    pintaSeleccio();
  });
  document.addEventListener("pointercancel", () => {
    if (!seleccio) return;
    if (seleccio.dret) deixaSeleccio();
    else { seleccio = null; pintaSeleccio(); }
  });
  cont.addEventListener("contextmenu", (e) => {
    // El clic dret el fa servir «pointerdown» per tallar: aquí només amaguem el menú.
    if (mode === "talla" && e.target.closest(".p")) e.preventDefault();
  });
  document.addEventListener("keydown", (e) => {
    if (!seleccioFeta || e.target.matches("input, textarea, select") || !["Backspace", "Delete"].includes(e.key)) return;
    e.preventDefault();
    commutaIds(seleccioFeta);
    deixaSeleccio();
  });
  $(".text").addEventListener("wheel", () => { darrerDesplacamentManual = performance.now(); }, { passive: true });
}

// --- Paraules destacades ------------------------------------------------------------------------
// Als subtítols, algunes paraules surten més grans i d'un altre color. tallat en tria soles; en el
// mode «Destaca» se'n poden afegir o treure (i Claude també ho pot fer amb «tallat.py destaca»).

function marcaClaus() {
  const claus = new Set(liniesSub.flatMap((l) => l.paraules.filter((w) => w.clau).map((w) => w.id)));
  for (const [id, s] of spans) s.classList.toggle("clau", claus.has(id));
}

function commutaDestacada(id) {
  if (esFora(id)) { avis("Aquesta paraula no surt al vídeo."); return; }
  const ara = liniesSub.some((l) => l.paraules.some((w) => w.id === id && w.clau));
  canvia((e) => { e.destacades = { ...(e.destacades || {}), [String(id)]: !ara }; });
  spans.get(id)?.classList.toggle("clau", !ara);  // es veu de seguida; el servidor ho confirma
  if (!estilSub?.clau_grans) {
    canviaEstil({ clau_grans: true });
    avis("He activat les paraules destacades a l'estil dels subtítols.", 4000);
  }
}

function editaParaula(s, id) {
  const entrada = document.createElement("input");
  entrada.className = "editor";
  entrada.value = estat.correccions[String(id)] ?? P.paraules[id].text;
  entrada.size = Math.max(3, entrada.value.length + 1);
  s.replaceWith(entrada);
  entrada.focus();
  entrada.select();
  let acabat = false;
  const acaba = (desa) => {
    if (acabat) return;
    acabat = true;
    entrada.replaceWith(s);
    const valor = entrada.value.trim();
    const actual = estat.correccions[String(id)] ?? P.paraules[id].text;
    if (desa && valor !== actual) {
      canvia((e) => {
        if (!valor || valor === P.paraules[id].text) delete e.correccions[String(id)];
        else e.correccions[String(id)] = valor;
      });
    }
  };
  entrada.addEventListener("input", () => { entrada.size = Math.max(3, entrada.value.length + 1); });
  entrada.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") acaba(true);
    if (e.key === "Escape") acaba(false);
  });
  entrada.addEventListener("blur", () => acaba(true));
}

function mostraParaula(id) {
  const s = spans.get(id);
  if (!s) return;
  s.scrollIntoView({ block: "center", behavior: "smooth" });
  s.classList.remove("llum");
  void s.offsetWidth;
  s.classList.add("llum");
}

// --- Propostes ------------------------------------------------------------------------

function context(id) {
  const text = (i) => estat.correccions[String(i)] ?? P.paraules[i]?.text ?? "";
  const abans = [];
  for (let i = id - 1; i >= Math.max(0, id - 3); i--) if (!esFora(i)) abans.unshift(text(i));
  const despres = [];
  for (let i = id + 1; i < Math.min(P.paraules.length, id + 4); i++) if (!esFora(i)) despres.push(text(i));
  const e = (t) => t.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  return `${e(abans.join(" "))} <b>${e(text(id))}</b> ${e(despres.join(" "))}`;
}

function decideix(ids, treure) {
  if (ids.length === 1 && treure) demanaEscolta(ids[0]);
  canvia((e) => {
    for (const id of ids) {
      const k = String(id);
      delete e.propostes[k];
      if (treure) e.esborrades[k] = "usuari";
      else if (!e.mantingudes.includes(id)) e.mantingudes.push(id);
    }
  });
}

function actualitzaPropostes() {
  const grups = {};
  for (const [k, motiu] of Object.entries(estat.propostes)) (grups[motiu] ||= []).push(+k);
  const total = Object.keys(estat.propostes).length;
  $("#compte-propostes").textContent = total || "";
  const cont = $("#propostes");
  cont.textContent = "";
  if (!total) { cont.innerHTML = '<p class="buit">No hi ha propostes pendents.</p>'; return; }
  for (const [motiu, ids] of Object.entries(grups)) {
    ids.sort((a, b) => a - b);
    const grup = document.createElement("div");
    grup.className = "grup-propostes";
    grup.innerHTML = `<div class="grup-cap"><strong>${PROPOSTES[motiu] || motiu} · ${ids.length}</strong>
      <span class="accions"><button class="enllac" data-tot="treu">Treu-les</button><button class="enllac" data-tot="deixa">Deixa-les</button></span></div>`;
    grup.querySelector('[data-tot="treu"]').addEventListener("click", () => decideix(ids, true));
    grup.querySelector('[data-tot="deixa"]').addEventListener("click", () => decideix(ids, false));
    for (const id of ids) {
      const item = document.createElement("div");
      item.className = "item";
      item.innerHTML = `<span class="context">${context(id)}</span>
        <button class="mini treu" title="Treu-la" aria-label="Treu-la">${ICONES.treu}</button>
        <button class="mini deixa" title="Deixa-la" aria-label="Deixa-la">${ICONES.deixa}</button>`;
      item.addEventListener("click", (e) => {
        if (e.target.closest(".treu")) return decideix([id], true);
        if (e.target.closest(".deixa")) return decideix([id], false);
        mostraParaula(id);
        if (vista === "directe") vesAOriginal(P.paraules[id].inici - 1);
      });
      grup.append(item);
    }
    cont.append(grup);
  }
}

// --- Reproductor ------------------------------------------------------------------------

// Un sol vídeo que salta de tros en tros. (Vam provar dos vídeos alternats per evitar la
// micropausa dels salts, però al Safari el segon vídeo deixava de dir per on anava i
// el muntatge sonava sencer, també el que estava tret.)
const R = { v: $("#video-a"), k: 0, reproduint: false, aturaA: null, vigila: { t: -1, des: 0 }, salt: null, posat: false };

// El Safari s'encalla si li demanem un salt mentre encara en fa un altre (passa sobretot quan els
// paràgrafs no van en l'ordre de la gravació i cal saltar enrere o lluny). Els fem d'un en un:
// si n'hi ha un en marxa, el nou espera que acabi i només es fa l'últim que s'ha demanat.
// A més, un salt cap a un tros que encara no s'ha baixat es fa amb el vídeo aturat un instant:
// el Safari els fa bé aturat i, en canvi, sonant de vegades es queda esperant.
function posaTemps(t) {
  R.posat = true;
  if (R.v.seeking) { R.salt = t; return; }
  R.salt = null;
  if (!R.v.paused && !jaCarregat(t)) {
    R.v.pause();
    R.repren = true;
  } else if (R.v.paused && R.reproduint && vista === "directe") {
    // El navegador l'ha aturat sol (passa en arribar al final del fitxer amb els paràgrafs
    // reordenats): sona encara, així que després del salt continua.
    R.repren = true;
  }
  R.v.currentTime = t;
}

function jaCarregat(t) {
  const b = R.v.buffered;
  for (let i = 0; i < b.length; i++) if (t >= b.start(i) && t <= b.end(i) - 0.3) return true;
  return false;
}
const tempsVideo = () => R.salt ?? R.v.currentTime;  // on serà el vídeo quan acabi el salt

// --- Escoltar cada tall ---------------------------------------------------------------------
// En treure o recuperar paraules amb el vídeo aturat, el reproductor fa sonar uns segons
// al voltant del tall perquè se senti l'efecte al moment.
let escoltaPendent = null;
let escoltaActiva = (() => { try { return localStorage.getItem("tallat.escolta") !== "no"; } catch { return true; } })();

function demanaEscolta(id) {
  if (!escoltaActiva || sona()) return;
  escoltaPendent = P.paraules[id].inici;
  if (vista !== "directe") {
    canviaVista("directe");
    avis("Ara veus el muntatge en directe. L'esborrany no té aquest canvi.");
  }
}

// Temps del vídeo original → temps del muntatge (si cau dins d'un tall, l'inici del tros següent).
function muntatgeDe(t) {
  const k = indexTram(t);
  if (k >= trams.length) return duradaFinal;
  return acum[k] + Math.max(0, t - trams[k][0]);
}

function escoltaTall(t) {
  if (!trams.length || sona()) return;
  const m = muntatgeDe(t);
  registre("escolta", { t, m: +m.toFixed(3) });
  vesA(Math.max(0, m - 1.5));
  reprodueix();
  R.aturaA = Math.min(duradaFinal, m + 1.5);
}
const vE = $("#video-esborrany");

// Quin tros conté el temps original t. En un reel muntat els trossos no van en ordre
// de gravació: si t no és dins de cap, el tros que comença just després de t.
function indexTram(t, llista = trams) {
  for (let i = 0; i < llista.length; i++) if (t >= llista[i][0] - 0.001 && t < llista[i][1] - 0.001) return i;
  let millor = llista.length;
  for (let i = 0; i < llista.length; i++) {
    if (llista[i][0] > t && (millor === llista.length || llista[i][0] < llista[millor][0])) millor = i;
  }
  return millor;
}

function tempsMuntatge() {
  if (vista === "esborrany") return vE.currentTime || 0;
  if (!trams.length) return 0;
  const k = Math.min(R.k, trams.length - 1);
  const [a, b] = trams[k];
  return acum[k] + limita(tempsVideo() - a, 0, b - a);
}

function durada() { return vista === "esborrany" ? (esborrany?.durada || vE.duration || 0) : duradaFinal; }

function vesA(m) {
  m = limita(m, 0, durada());
  if (vista === "esborrany") { vE.currentTime = m; return; }
  if (!trams.length) return;
  let k = 0;
  while (k + 1 < trams.length && acum[k + 1] <= m + 1e-6) k++;
  R.k = k;
  posaTemps(trams[k][0] + (m - acum[k]));
  registre("vesA", { m: +m.toFixed(3), k, video: ev(R.v) });
}

function vesAOriginal(t) {
  const k = Math.min(indexTram(Math.max(0, t)), trams.length - 1);
  if (k < 0) return;
  vesA(acum[k] + Math.max(0, t - trams[k][0]));
}

// Si s'ha editat mentre sonava, continuem pel tros que toca.
function recolloca() {
  if (!trams.length) { atura(); return; }
  const t = tempsVideo();
  const k = indexTram(t);
  registre("recolloca", { t: +t.toFixed(3), k, kAbans: R.k });
  if (k >= trams.length) { R.k = trams.length - 1; if (R.reproduint) atura(); return; }
  R.k = k;
  if (t < trams[k][0] - 0.01 && R.reproduint) posaTemps(trams[k][0]);
}

function salta() {
  const k = R.k + 1;
  if (k >= trams.length) { atura(); return; }
  registre("salta", { k, cap: trams[k][0], video: ev(R.v) });
  R.k = k;
  posaTemps(trams[k][0]);
}

function reprodueix() {
  if (vista === "esborrany") { vE.play(); return; }
  if (!trams.length) return;
  // Encara no s'ha posat enlloc (o ja s'ha acabat): comença pel principi del muntatge, que si els
  // paràgrafs s'han canviat d'ordre no és el principi de la gravació.
  if (!R.posat || tempsMuntatge() >= duradaFinal - 0.05) vesA(0);
  const t = tempsVideo();
  const k = indexTram(t);
  if (k >= trams.length) vesA(0);
  else { R.k = k; if (t < trams[k][0]) posaTemps(trams[k][0]); }
  R.reproduint = true;
  R.vigila = { t: -1, des: performance.now() };
  document.body.classList.add("reproduint");
  registre("play", { k: R.k, video: ev(R.v) });
  R.v.play().then(() => registre("play-ok", { video: ev(R.v) })).catch((e) => {
    registre("play-rebutjat", { error: e.name, video: ev(R.v) });
    atura();
    avis("Toca el botó de reproduir per començar.");
  });
}

function atura() {
  if (R.reproduint) registre("atura", { k: R.k, video: ev(R.v) });
  R.repren = false;
  R.aturaA = null;
  R.reproduint = false;
  R.v.pause(); vE.pause();
  document.body.classList.remove("reproduint");
}

// Vigilant: si el vídeo diu que sona però el seu temps no avança, o un salt no acaba mai,
// el despertem (el Safari, de vegades, es queda esperant).
function vigila() {
  if (R.v.seeking && R.reproduint) {
    R.vigila.salt ??= { des: performance.now(), intents: 0 };
    if (performance.now() - R.vigila.salt.des > 800) {
      const objectiu = tempsVideo();
      R.salt = null;
      R.vigila.salt.intents++;
      registre("salt-encallat", { intents: R.vigila.salt.intents, video: ev(R.v) });
      if (R.vigila.salt.intents >= 2) {  // segon intent: recarreguem el vídeo i hi tornem
        R.v.load();
        R.v.addEventListener("loadeddata", () => {
          R.v.currentTime = objectiu;
          if (R.reproduint) R.v.play().catch(() => {});
        }, { once: true });
        R.vigila.salt = { des: performance.now() + 3000, intents: 0 };
      } else {
        R.v.currentTime = objectiu;
        R.vigila.salt.des = performance.now();
      }
    }
    return;
  }
  R.vigila.salt = null;
  if (!R.reproduint || R.v.paused || R.v.seeking || R.v.readyState < 3) { R.vigila.des = performance.now(); return; }
  const t = R.v.currentTime;
  if (t !== R.vigila.t) { R.vigila = { t, des: performance.now() }; return; }
  if (performance.now() - R.vigila.des > 600) {
    registre("congelat", { video: ev(R.v) });
    R.vigila.des = performance.now();
    R.v.currentTime = t + 0.001;
  }
}

const sona = () => (vista === "esborrany" ? !vE.paused : R.reproduint);

function reprodueixDes(id) {
  if (vista !== "directe") canviaVista("directe");
  vesAOriginal(P.paraules[id].inici - 0.05);
  reprodueix();
}

// Bucle sincronitzat amb la pantalla: salta els trossos tallats i marca la paraula que sona.
let darreraMostra = 0;
function bucle() {
  requestAnimationFrame(bucle);
  if (!P) return;
  if (R.reproduint && performance.now() - darreraMostra > 300) {
    darreraMostra = performance.now();
    registre("mostra", { k: R.k, m: +tempsMuntatge().toFixed(3), video: ev(R.v) });
  }
  vigila();
  comprovaTall();
  pintaTemps();
  paraulaActual();
  pintaSubtitols();
  pintaBroll();
  pintaStickers();
  R.v.classList.toggle("zoom", vista === "directe" && !!zoomsTram[Math.min(R.k, trams.length - 1)]);
}

// --- Subtítols en directe ------------------------------------------------------------------------
// Els dibuixa pagina/subtitols.js, el mateix codi que fa servir el vídeo final: el que es veu és el que surt.

let previa = null;          // la línia de temps dels subtítols a la vista prèvia
let previaBruta = true;     // cal tornar-la a construir (han canviat les línies o l'estil)
let previaTemps = NaN;      // l'últim moment dibuixat

function titolVisible() {
  return titolMuntatge || (editantTitol ? { ...MOSTRA_TITOL, final: estilTitol?.durada || 3 } : null);
}

function refaPrevia() {
  previaBruta = false;
  previaTemps = NaN;
  if (!window.TallatSubtitols) { previa = previaTitol = null; return; }
  const titol = titolVisible();
  const amaga = titol && estilTitol?.amaga_subtitols ? [titol.inici, titol.final] : null;
  previa = estilSub ? TallatSubtitols.construeix($("#ts-host"), liniesSub, estilSub, { familia: familiaCss(estilSub), amaga }) : null;
  previaTitol = estilTitol ? TallatSubtitols.titol($("#tt-host"), titol, estilTitol,
    { familia: familiaCss({ font: estilTitol.font || estilSub?.font }) }) : null;
}

function pintaSubtitols() {
  const capa = $("#capa-subtitols");
  const ambSubtitols = (estat?.subtitols !== false || editantEstil) && liniesSub.length > 0;
  const titol = titolVisible();
  const visible = vista === "directe" && (ambSubtitols || !!titol);
  capa.hidden = !visible;
  if (!visible) return;
  $("#ts-host").hidden = !ambSubtitols;
  if (previaBruta) refaPrevia();
  let m = tempsMuntatge();
  // Mentre es tria l'estil del títol amb el vídeo aturat, el títol sempre es veu (ja escrit).
  if (editantTitol && !sona() && titol && !(m >= titol.inici && m < titol.final)) {
    m = Math.max(titol.inici, titol.final - 0.35);
    if (m !== previaTemps) { previa?.seek(m, false); previaTitol?.seek(m, false); previaTemps = m; }
    return;
  }
  if (!previa) { if (m !== previaTemps) { previaTitol?.seek(m, false); previaTemps = m; } return; }
  // Mentre es tria l'estil amb el vídeo aturat, sempre hi ha una línia d'exemple a la vista.
  if (editantEstil && !sona() && liniesSub.length && !liniesSub.some((l) => m >= l.inici && m < l.final)) {
    const l = liniesSub.find((x) => x.inici >= m) || liniesSub[liniesSub.length - 1];
    const w = l.paraules[Math.min(1, l.paraules.length - 1)];
    m = Math.min(l.final - 0.01, w.inici + 0.45);
  }
  if (m !== previaTemps) { previa.seek(m, false); previaTitol?.seek(m, false); previaTemps = m; }
}

const escapaFont = (f) => (/^[\w-]+$/.test(f) ? f : `"${String(f).replace(/["\\]/g, "")}"`);
const familiaCss = (e) => `${escapaFont(e.font || "system-ui")}, system-ui, sans-serif`;

function aplicaEstilSubtitols(e) {
  if (!e) return;
  estilSub = e;
  previaBruta = true;
  pintaResumEstil();
}

// --- Estil dels subtítols (panell) ------------------------------------------------------------

const FONTS = [
  ["system-ui", "San Francisco (la del sistema)"], ["Avenir Next", "Avenir Next"], ["Helvetica Neue", "Helvetica Neue"],
  ["Futura", "Futura"], ["DIN Condensed", "DIN Condensed"], ["Gill Sans", "Gill Sans"], ["Impact", "Impact"],
  ["Arial Black", "Arial Black"], ["Rockwell", "Rockwell"], ["Georgia", "Georgia"],
  ["American Typewriter", "American Typewriter"], ["Marker Felt", "Marker Felt"], ["Chalkboard SE", "Chalkboard SE"],
];
const AGRUPACIONS = { una: [1, 30], poques: [3, 18], frase: [7, 34] };  // [paraules, lletres] per línia
const agrupacioDe = (e) => (e.paraules_per_linia <= 1 ? "una" : e.paraules_per_linia <= 4 ? "poques" : "frase");
const destacatDe = (e) => (e.destaca === false ? "cap" : e.destacat || "color");
// Frase d'exemple per als botons dels estils: «idea» és la paraula clau i porta emoji.
const MOSTRA = [["Tinc", false, null], ["una", false, null], ["idea", true, "💡"], ["genial", false, null]];

// Les lletres del kit (les pujades i les de la biblioteca) es carreguen al navegador amb el seu nom,
// com al vídeo final. Quan n'arriba una de nova, la vista prèvia la fa servir sola.
const fontsCarregades = new Map();  // url → FontFace
async function carregaFontsKit(fonts) {
  fontsKit = fonts || [];
  const vigents = new Set(fontsKit.map((f) => f.url));
  for (const [url, font] of fontsCarregades) {
    if (!vigents.has(url)) { document.fonts.delete(font); fontsCarregades.delete(url); }
  }
  for (const f of fontsKit) {
    if (fontsCarregades.has(f.url)) continue;
    try {
      const font = new FontFace(f.familia, `url(${f.url})`, { weight: String(f.pes) });
      fontsCarregades.set(f.url, font);
      await font.load();
      document.fonts.add(font);
      previaBruta = true;
      pintaResumEstil();
    } catch {
      fontsCarregades.delete(f.url);
      avis(`No he pogut carregar la lletra «${f.familia}». Torna-la a pujar o tria'n una altra.`, 5000);
    }
  }
}

function predefinitActual(e = estilSub) {
  if (!e) return null;
  return estilsPredefinits.find((p) => Object.entries(p.valors).every(([k, v]) =>
    (typeof v === "number" ? Math.abs((e[k] ?? NaN) - v) < 1e-6 : String(e[k]).toUpperCase() === String(v).toUpperCase())));
}

// Dibuixa una mostra quieta d'un estil dins d'una caixa petita, amb el mateix codi que els subtítols.
function pintaMostra(caixa, e, { paraules, alcada, mida }) {
  const host = document.createElement("div");
  caixa.textContent = "";
  caixa.append(host);
  const linia = { inici: 0, final: 9, paraules: paraules.map(([text, clau, emoji], i) =>
    ({ text, clau, emoji, inici: i * 0.3, final: i * 0.3 + 0.28 })) };
  const tl = TallatSubtitols.construeix(host, [linia], e,
    { familia: familiaCss(e), alcada, y: 0.56, amplada: 0.96, mida });
  tl.seek(linia.paraules[linia.paraules.length - 1].inici + 0.5, false);
  host.style.transform = `scale(${caixa.clientWidth / TallatSubtitols.AMPLADA})`;
}

function pintaResumEstil() {
  if (!estilSub || !window.TallatSubtitols) return;
  $("#nom-estil").textContent = predefinitActual()?.nom ?? "Personalitzat";
  pintaMostra($("#mostra-estil"), { ...estilSub, destaca: false, emojis: false, clau_grans: false, fons: "cap" },
    { paraules: [["Aa", false, null]], alcada: 1080, mida: 0.36 });
}

// El desplegable de lletres: les del kit que ha pujat la persona, les del Mac i les gratuïtes (les que
// encara no són al kit porten «bib:»: triar-les les baixa). Amb `laDelsSubtitols`, també «la dels subtítols».
function ompleLletres(select, valor, { laDelsSubtitols = false } = {}) {
  select.textContent = "";
  const grup = (nom) => { const g = document.createElement("optgroup"); g.label = nom; select.append(g); return g; };
  const opcio = (on, v, text) => { const o = document.createElement("option"); o.value = v; o.textContent = text; on.append(o); };
  if (laDelsSubtitols) opcio(select, "", `La dels subtítols (${estilSub?.font === "system-ui" ? "San Francisco" : estilSub?.font || ""})`);
  const alKit = new Set(fontsKit.map((f) => f.familia));
  const deLaBiblioteca = new Set(bibliotecaLletres.lletres.map((l) => l.nom));
  const meves = [...alKit].filter((f) => !deLaBiblioteca.has(f));
  if (meves.length) { const g = grup("Les teves"); for (const f of meves) opcio(g, f, f); }
  const delMac = grup("Del Mac");
  for (const [v, text] of FONTS) opcio(delMac, v, text);
  for (const [id, nom] of Object.entries(bibliotecaLletres.grups || {})) {
    const g = grup(`${nom} · gratuïtes`);
    for (const l of bibliotecaLletres.lletres.filter((x) => x.grup === id)) {
      opcio(g, alKit.has(l.nom) ? l.nom : `bib:${l.id}`, alKit.has(l.nom) ? `${l.nom} ✓` : l.nom);
    }
  }
  const actual = valor || "";
  if (![...select.options].some((o) => o.value === actual)) opcio(select, actual, actual);
  select.value = actual;
}

function marcaSegmentat(id, valor) {
  for (const b of $$(`#${id} button`)) b.setAttribute("aria-checked", String(b.dataset.valor === valor));
}

function pintaPanellEstil() {
  const e = estilSub;
  if (!e || $("#panell-estil").hidden) return;
  const actual = predefinitActual();
  const cont = $("#estils");
  cont.textContent = "";
  for (const p of estilsPredefinits) {
    const b = document.createElement("button");
    b.className = "estil";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(p === actual));
    b.title = p.descripcio;
    b.innerHTML = `<span class="estil-mostra"></span><span class="estil-nom"></span>`;
    b.querySelector(".estil-nom").textContent = p.nom;
    b.addEventListener("click", () => canviaEstil({ ...p.valors }, true));
    cont.append(b);
    if (window.TallatSubtitols) {
      const v = { ...e, ...p.valors };
      const n = v.paraules_per_linia <= 1 ? 1 : v.paraules_per_linia <= 4 ? 3 : 4;
      pintaMostra(b.querySelector(".estil-mostra"), v,
        { paraules: n === 1 ? [MOSTRA[2]] : MOSTRA.slice(0, n), alcada: 675, mida: Math.min(0.2, v.mida * 1.6) });
    }
  }
  marcaSegmentat("e-paraules", agrupacioDe(e));
  marcaSegmentat("e-apareixen", e.apareixen);
  marcaSegmentat("e-aspecte", e.aspecte || "normal");
  marcaSegmentat("e-fons", e.fons || "cap");
  $("#e-animacio").value = e.animacio;
  $("#e-destacat").value = destacatDe(e);
  $("#e-clau").setAttribute("aria-checked", String(!!e.clau_grans));
  $("#e-emojis").setAttribute("aria-checked", String(!!e.emojis));
  $("#e-majuscules").setAttribute("aria-checked", String(!!e.majuscules));
  $("#e-ombra").setAttribute("aria-checked", String(!!e.ombra));

  ompleLletres($("#e-font"), e.font);
  $("#avis-lletra").hidden = !bibliotecaLletres.lletres.length;

  const pes = $("#e-pes");
  if (![...pes.options].some((o) => +o.value === +e.pes)) {
    const o = document.createElement("option"); o.value = e.pes; o.textContent = `Gruix ${e.pes}`; pes.append(o);
  }
  pes.value = String(e.pes);
  $("#e-mida").value = e.mida;
  $("#e-espaiat").value = e.espaiat ?? 0;
  $("#e-interlineat").value = e.interlineat ?? 1.12;
  marcaSegmentat("e-disposicio", e.disposicio || "linia");
  marcaSegmentat("e-alineacio", e.alineacio || "centre");
  $("#camps-clau").hidden = !e.clau_grans;
  $("#e-clau-mida").value = e.clau_mida ?? 1.4;
  $("#e-clau-color").value = (e.clau_color || e.color_actiu).toLowerCase();
  $("#e-clau-sola").setAttribute("aria-checked", String(!!e.clau_sola));
  $("#e-posicio").value = e.posicio_y;
  $("#e-gruix").value = e.gruix_contorn;
  $("#e-color").value = e.color.toLowerCase();
  $("#e-color-actiu").value = e.color_actiu.toLowerCase();
  $("#e-contorn").value = e.contorn.toLowerCase();
  $("#e-fons-color").value = (e.fons_color || "#000000").toLowerCase();
  $("#camp-actiu").classList.toggle("apagat", destacatDe(e) === "cap" && !e.clau_grans && e.aspecte === "normal");
  $("#camp-fons").hidden = e.fons !== "pindola";
  $("#fitxer-estil").textContent = `Fitxer: ${(P?.fitxer_estil || "").replace(/^\/Users\/[^/]+/, "~")}`;
}

// Cada canvi es veu a l'instant; es desa al cap d'un moment (els lliscadors n'envien molts).
let estilPendent = {};
let temporitzadorEstil = null;
function canviaEstil(canvis, mostra = false) {
  aplicaEstilSubtitols({ ...estilSub, ...canvis });
  pintaPanellEstil();
  Object.assign(estilPendent, canvis);
  clearTimeout(temporitzadorEstil);
  temporitzadorEstil = setTimeout(desaEstil, 300);
  if (mostra) mostraAnimacio();
}

async function desaEstil() {
  const canvis = estilPendent;
  estilPendent = {};
  if (!Object.keys(canvis).length) return;
  try {
    await cua;
    respostaEstil(await api("/api/marca", { subtitols: canvis }));
  } catch (e) { avis(e.message, 5000); }
}

function respostaEstil(r) {
  if (r.kits) { kits = r.kits; kitActual = r.kit; pintaKits(); }
  if (r.versio_estil) versioEstil = r.versio_estil;
  if (r.biblioteca_lletres) bibliotecaLletres = r.biblioteca_lletres;
  if (r.fonts_kit) carregaFontsKit(r.fonts_kit);
  if (r.subtitols) liniesSub = r.subtitols;
  if (r.estils_titol) estilsTitol = r.estils_titol;
  if ("titol" in r) titolMuntatge = r.titol;
  // Si mentrestant hi ha hagut més canvis, que no es perdin a la vista.
  aplicaEstilSubtitols({ ...r.estil_subtitols, ...estilPendent });
  if (r.estil_titol) aplicaEstilTitol({ ...r.estil_titol, ...titolPendent });
  pintaPanellEstil();
  pintaPanellTitol();
}

// --- El títol del ganxo -------------------------------------------------------------------------
// Un text dissenyat els primers segons. El text és de cada vídeo (a l'estat: es desfà com la resta);
// l'estil, del kit. Es dibuixa amb pagina/subtitols.js, com al vídeo final.

function aplicaEstilTitol(e) {
  if (!e) return;
  estilTitol = e;
  previaBruta = true;
  pintaResumTitol();
}

function pintaTitol() {
  if (!estat) return;
  const camp = $("#text-titol");
  const t = estat.titol;
  if (document.activeElement !== camp) camp.value = t?.text || "";
  const durada = t?.durada ?? estilTitol?.durada ?? 3;
  $("#durada-titol").value = durada;
  $("#durada-titol-text").textContent = fmtSegons(durada);
  $("#camp-durada-titol").hidden = !t;
}

// El text: a la vista, de seguida; a l'estat (i a desfer), quan s'acaba d'escriure.
let temporitzadorTitol = null;
function canviaTextTitol() {
  const text = $("#text-titol").value;
  const durada = estat.titol?.durada ?? null;
  titolMuntatge = text.trim()
    ? { text, inici: 0, final: Math.min(duradaFinal || 99, durada ?? estilTitol?.durada ?? 3) } : null;
  previaBruta = true;
  $("#camp-durada-titol").hidden = !text.trim();
  clearTimeout(temporitzadorTitol);
  temporitzadorTitol = setTimeout(() => canvia((e) => { e.titol = text.trim() ? { text, durada } : null; }), 700);
}

function canviaDuradaTitol(durada) {
  $("#durada-titol-text").textContent = fmtSegons(durada);
  if (titolMuntatge) { titolMuntatge = { ...titolMuntatge, final: Math.min(duradaFinal || 99, durada) }; previaBruta = true; }
  clearTimeout(temporitzadorTitol);
  temporitzadorTitol = setTimeout(() => canvia((e) => { if (e.titol) e.titol = { ...e.titol, durada }; }), 400);
}

let titolPendent = {};
let temporitzadorEstilTitol = null;
function canviaTitol(canvis, mostra = false) {
  aplicaEstilTitol({ ...estilTitol, ...canvis });
  pintaPanellTitol();
  Object.assign(titolPendent, canvis);
  clearTimeout(temporitzadorEstilTitol);
  temporitzadorEstilTitol = setTimeout(desaEstilTitol, 300);
  if (mostra) mostraTitol();
}

async function desaEstilTitol() {
  const canvis = titolPendent;
  titolPendent = {};
  if (!Object.keys(canvis).length) return;
  try {
    await cua;
    respostaEstil(await api("/api/marca", { titol: canvis }));
  } catch (e) { avis(e.message, 5000); }
}

// Fa sonar el títol des del principi perquè es vegi com entra.
function mostraTitol() {
  if (vista !== "directe" || sona() || !titolMuntatge) return;
  vesA(titolMuntatge.inici);
  reprodueix();
  R.aturaA = Math.min(duradaFinal, titolMuntatge.final + 0.2);
}

function predefinitTitol(e = estilTitol) {
  if (!e) return null;
  return estilsTitol.find((p) => Object.entries(p.valors).every(([k, v]) =>
    (typeof v === "number" ? Math.abs((e[k] ?? NaN) - v) < 1e-6 : String(e[k]).toUpperCase() === String(v).toUpperCase())));
}

// Una mostra quieta d'un estil de títol, amb el mateix codi que el títol de debò.
function pintaMostraTitol(caixa, e, text, alcada) {
  if (!window.TallatSubtitols || !e) return;
  const host = document.createElement("div");
  caixa.textContent = "";
  caixa.append(host);
  const v = { ...e, posicio_y: 0.5, amplada_maxima: 0.94, fons: e.fons === "enfosquit" ? "cap" : e.fons };
  const tl = TallatSubtitols.titol(host, { text, inici: 0, final: 9 }, v,
    { familia: familiaCss({ font: e.font || estilSub?.font }), alcada });
  tl.seek(5, false);
  host.style.transform = `scale(${caixa.clientWidth / TallatSubtitols.AMPLADA})`;
}

function pintaResumTitol() {
  if (!estilTitol) return;
  $("#nom-estil-titol").textContent = predefinitTitol()?.nom ?? "Personalitzat";
  pintaMostraTitol($("#mostra-titol"), { ...estilTitol, mida: 0.3, clau_mida: 1 }, "Aa", 1080);
}

function pintaPanellTitol() {
  const e = estilTitol;
  if (!e || $("#panell-titol").hidden) return;
  const actual = predefinitTitol();
  const cont = $("#estils-titol");
  cont.textContent = "";
  for (const p of estilsTitol) {
    const b = document.createElement("button");
    b.className = "estil";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(p === actual));
    b.title = p.descripcio;
    b.innerHTML = `<span class="estil-mostra"></span><span class="estil-nom"></span>`;
    b.querySelector(".estil-nom").textContent = p.nom;
    b.addEventListener("click", () => canviaTitol({ ...p.valors }, true));
    cont.append(b);
    pintaMostraTitol(b.querySelector(".estil-mostra"), { ...e, ...p.valors, mida: Math.min(0.11, (p.valors.mida || e.mida) * 1.5) },
      "El meu\n*títol*", 675);
  }
  $("#t-animacio").value = e.animacio;
  marcaSegmentat("t-fons", e.fons || "cap");
  marcaSegmentat("t-alineacio", e.alineacio || "centre");
  ompleLletres($("#t-font"), e.font, { laDelsSubtitols: true });
  const pes = $("#t-pes");
  if (![...pes.options].some((o) => +o.value === +e.pes)) {
    const o = document.createElement("option"); o.value = e.pes; o.textContent = `Gruix ${e.pes}`; pes.append(o);
  }
  pes.value = String(e.pes);
  $("#t-majuscules").setAttribute("aria-checked", String(!!e.majuscules));
  $("#t-ombra").setAttribute("aria-checked", String(e.ombra !== false));
  $("#t-amaga").setAttribute("aria-checked", String(!!e.amaga_subtitols));
  $("#t-mida").value = e.mida;
  $("#t-clau-mida").value = e.clau_mida;
  $("#t-espaiat").value = e.espaiat ?? 0;
  $("#t-interlineat").value = e.interlineat ?? 1;
  $("#t-posicio").value = e.posicio_y;
  $("#t-gruix").value = e.gruix_contorn ?? 0;
  $("#t-color").value = e.color.toLowerCase();
  $("#t-clau-color").value = (e.clau_color || e.color).toLowerCase();
  $("#t-contorn").value = e.contorn.toLowerCase();
  $("#t-fons-color").value = (e.fons_color || "#000000").toLowerCase();
  $("#camp-t-fons").hidden = (e.fons || "cap") === "cap";
}

function obreTitol() {
  editantTitol = true;
  previaBruta = true;
  if (vista !== "directe") canviaVista("directe");
  $(".barra").classList.add("editant-estil");
  $("#panell-titol").hidden = false;
  $(".barra").scrollTop = 0;
  pintaPanellTitol();
  if (!titolMuntatge) avis("Encara no has escrit el títol: el reproductor en mostra un d'exemple.", 4000);
  $("#tanca-titol").focus();
}

function tancaTitol() {
  editantTitol = false;
  previaBruta = true;
  $(".barra").classList.remove("editant-estil");
  $("#panell-titol").hidden = true;
  $("#obre-estil-titol").focus();
}

function instalaTitol() {
  $("#text-titol").addEventListener("input", canviaTextTitol);
  $("#durada-titol").addEventListener("input", (e) => canviaDuradaTitol(+e.target.value));
  $("#obre-estil-titol").addEventListener("click", obreTitol);
  $("#tanca-titol").addEventListener("click", tancaTitol);
  $("#t-animacio").addEventListener("change", (e) => canviaTitol({ animacio: e.target.value }, true));
  for (const [id, clau] of [["t-fons", "fons"], ["t-alineacio", "alineacio"]]) {
    for (const b of $$(`#${id} button`)) b.addEventListener("click", () => canviaTitol({ [clau]: b.dataset.valor }, true));
  }
  $("#t-font").addEventListener("change", (e) => {
    const v = e.target.value;
    if (v.startsWith("bib:")) baixaLletra(v.slice(4), "titol");
    else canviaTitol({ font: v || null });
  });
  $("#t-pes").addEventListener("change", (e) => canviaTitol({ pes: +e.target.value }));
  for (const [id, clau, perDefecte] of [["t-majuscules", "majuscules", false], ["t-ombra", "ombra", true],
    ["t-amaga", "amaga_subtitols", false]]) {
    $(`#${id}`).addEventListener("click", () => canviaTitol({ [clau]: !(estilTitol[clau] ?? perDefecte) }));
  }
  for (const [id, clau] of [["t-mida", "mida"], ["t-clau-mida", "clau_mida"], ["t-espaiat", "espaiat"],
    ["t-interlineat", "interlineat"], ["t-posicio", "posicio_y"], ["t-gruix", "gruix_contorn"]]) {
    $(`#${id}`).addEventListener("input", (e) => canviaTitol({ [clau]: +e.target.value }));
  }
  for (const [id, clau] of [["t-color", "color"], ["t-clau-color", "clau_color"], ["t-contorn", "contorn"],
    ["t-fons-color", "fons_color"]]) {
    $(`#${id}`).addEventListener("input", (e) => canviaTitol({ [clau]: e.target.value.toUpperCase() }));
  }
  $("#restableix-titol").addEventListener("click", async () => {
    try {
      clearTimeout(temporitzadorEstilTitol);
      titolPendent = {};
      await cua;
      respostaEstil(await api("/api/marca/restableix", { seccio: "titol" }));
      avis("El títol ha tornat a l'estil de tallat.");
    } catch (e) { avis(e.message); }
  });
}

// --- Kits d'estil -----------------------------------------------------------------------------
// Un kit és un estil amb nom (subtítols, b-roll, stickers i talls). Cada vídeo en fa servir un, i
// el panell d'estil canvia el d'aquest vídeo. Es poden crear, duplicar, exportar (un .zip) i importar.

let kits = [];           // [{id, nom, per_defecte}]
let kitActual = null;    // el kit d'aquest vídeo
let accioNomKit = null;  // «nou», «duplica» o «nom» mentre s'escriu un nom

function pintaKits() {
  const tria = $("#kit");
  tria.textContent = "";
  for (const k of kits) {
    const o = document.createElement("option");
    o.value = k.id;
    o.textContent = k.per_defecte ? `${k.nom} · per defecte` : k.nom;
    tria.append(o);
  }
  tria.value = kitActual;
  const actual = kits.find((k) => k.id === kitActual);
  const defecte = kits.find((k) => k.per_defecte);
  $("#kit-detall").textContent = actual?.per_defecte
    ? "És el kit per defecte: el fan servir els vídeos nous."
    : `Els vídeos nous fan servir «${defecte?.nom || ""}».`;
  $("#kit-defecte").hidden = !!actual?.per_defecte;
  $("#kit-esborra").hidden = !!actual?.per_defecte;
  $("#nom-kit-panell").textContent = actual?.nom || "";
  $("#nom-kit-titol").textContent = actual?.nom || "";
}

function respostaKit(r, missatge) {
  estat = r.estat;
  aplicaTrams(r);
  refresca(true);
  respostaEstil(r);  // l'estil del kit, la lletra i la llista de kits
  if (missatge) avis(missatge, 4000);
}

async function accioKit(ruta, dades, missatge) {
  try {
    await cua;
    respostaKit(await api(ruta, dades), missatge);
  } catch (e) {
    avis(e.message, 5000);
    pintaKits();
  }
}

function demanaNomKit(accio) {
  accioNomKit = accio;
  const actual = kits.find((k) => k.id === kitActual)?.nom || "";
  const camp = $("#nom-kit");
  camp.value = accio === "nom" ? actual : accio === "duplica" ? `${actual} (còpia)` : "";
  camp.placeholder = accio === "nou" ? "Nom del kit nou" : "Nom del kit";
  $("#form-kit").hidden = false;
  camp.focus();
  camp.select();
}

async function importaKit(fitxer) {
  avis(`Important «${fitxer.name}»…`, 20000);
  try {
    await cua;
    const json = await resposta(await fetch(`/api/kit/importa?nom=${encodeURIComponent(fitxer.name)}`,
      { method: "POST", headers: capcaleres({ "Content-Type": "application/zip" }), body: fitxer }));
    respostaKit(json, "Kit importat. Aquest vídeo ja el fa servir.");
  } catch (e) { avis(e.message, 6000); }
}

function instalaKits() {
  $("#kit").addEventListener("change", (e) => {
    const nom = kits.find((k) => k.id === e.target.value)?.nom || "";
    accioKit("/api/kit/tria", { kit: e.target.value }, `Aquest vídeo fa servir el kit «${nom}».`);
  });
  $("#kit-duplica").addEventListener("click", () => demanaNomKit("duplica"));
  $("#kit-nou").addEventListener("click", () => demanaNomKit("nou"));
  $("#kit-nom").addEventListener("click", () => demanaNomKit("nom"));
  const form = $("#form-kit");
  const camp = $("#nom-kit");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const nom = camp.value.trim();
    form.hidden = true;
    if (!nom) return;
    if (accioNomKit === "nom") accioKit("/api/kit/nom", { kit: kitActual, nom }, "Nom canviat.");
    else {
      const duplica = accioNomKit === "duplica";
      accioKit("/api/kit/nou", { nom, copia_de: duplica ? kitActual : null },
        `Kit «${nom}» creat${duplica ? "" : " amb l'estil de tallat"}. Aquest vídeo ja el fa servir.`);
    }
  });
  camp.addEventListener("keydown", (e) => { if (e.key === "Escape") { form.hidden = true; e.stopPropagation(); } });
  camp.addEventListener("blur", () => setTimeout(() => { form.hidden = true; }, 150));
  $("#kit-defecte").addEventListener("click", () =>
    accioKit("/api/kit/per-defecte", { kit: kitActual }, "Els vídeos nous faran servir aquest kit."));
  $("#kit-exporta").addEventListener("click", () => {
    const enllac = document.createElement("a");
    enllac.href = `/api/kit/exporta?kit=${encodeURIComponent(kitActual)}`;
    enllac.download = "";
    document.body.append(enllac);
    enllac.click();
    enllac.remove();
    avis("El kit es baixa en un .zip. Si porta una font teva, comprova que la pots compartir.", 5000);
  });
  $("#kit-importa").addEventListener("click", () => $("#fitxer-kit").click());
  $("#fitxer-kit").addEventListener("change", (e) => {
    const fitxer = e.target.files[0];
    e.target.value = "";
    if (fitxer) importaKit(fitxer);
  });
  // Treure un kit demana un segon clic (es guarda a ~/.tallat/kits-esborrats, per si de cas).
  const treu = $("#kit-esborra");
  let confirma = null;
  treu.addEventListener("click", () => {
    if (!confirma) {
      treu.textContent = "Clica un altre cop per treure'l";
      treu.classList.add("confirma");
      confirma = setTimeout(() => { confirma = null; treu.textContent = "Treu-lo"; treu.classList.remove("confirma"); }, 4000);
      return;
    }
    clearTimeout(confirma);
    confirma = null;
    treu.textContent = "Treu-lo";
    treu.classList.remove("confirma");
    accioKit("/api/kit/esborra", { kit: kitActual }, "Kit tret. Aquest vídeo torna a fer servir el per defecte.");
  });
}

// Fa sonar una línia de subtítols perquè es vegi com entra.
function mostraAnimacio() {
  if (vista !== "directe" || sona() || !liniesSub.length) return;
  const m = tempsMuntatge();
  const linia = liniesSub.find((l) => l.final > m + 0.05) || liniesSub[0];
  vesA(Math.max(0, linia.inici - 0.2));
  reprodueix();
  R.aturaA = Math.min(duradaFinal, linia.final + 0.4);
}

// Una lletra gratuïta de la biblioteca: el servidor la baixa al kit (el primer cop) i la fa servir.
async function baixaLletra(id, seccio = "subtitols") {
  const nom = bibliotecaLletres.lletres.find((l) => l.id === id)?.nom || id;
  avis(`Baixant la lletra «${nom}»…`, 20000);
  try {
    clearTimeout(temporitzadorEstil);
    await desaEstil();
    respostaEstil(await api("/api/marca/lletra", { id, seccio }));
    avis(`Lletra «${nom}» afegida al kit.`);
  } catch (e) {
    avis(e.message, 6000);
    pintaPanellEstil();
    pintaPanellTitol();
  }
}

async function pujaFont(fitxer) {
  avis(`Pujant «${fitxer.name}»…`, 20000);
  try {
    await cua;
    const json = await resposta(await fetch(`/api/marca/font?nom=${encodeURIComponent(fitxer.name)}`,
      { method: "POST", headers: capcaleres(), body: fitxer }));
    respostaEstil(json);
    avis("Font afegida. Ja la veus als subtítols.");
  } catch (e) { avis(e.message, 6000); }
}

function obreEstil() {
  editantEstil = true;
  if (vista !== "directe") canviaVista("directe");
  $(".barra").classList.add("editant-estil");
  $("#panell-estil").hidden = false;
  $(".barra").scrollTop = 0;
  pintaPanellEstil();
  $("#tanca-estil").focus();
}

function tancaEstil() {
  editantEstil = false;
  previaTemps = NaN;
  $(".barra").classList.remove("editant-estil");
  $("#panell-estil").hidden = true;
  $("#obre-estil").focus();
}

// --- Columnes i seccions -----------------------------------------------------------------------
// Les columnes es poden fer més amples o més estretes (arrossegant-ne la vora) i amagar; les
// seccions de la barra lateral es poden plegar. Aquest navegador ho recorda per a la propera vegada.

const desa = (clau, valor) => { try { localStorage.setItem(clau, JSON.stringify(valor)); } catch { /* sense memòria */ } };
const llegeix = (clau, perDefecte) => {
  try { const v = localStorage.getItem(clau); return v == null ? perDefecte : JSON.parse(v); } catch { return perDefecte; }
};
const MIN_TEXT = 400;  // el text (i la barra d'eines) sempre ha de tenir com a mínim aquest espai
const COLUMNES = {
  barra: { variable: "--amplada-barra", min: 200, max: 480, classe: "sense-barra", boto: "#commuta-barra" },
  reproductor: { variable: "--amplada-reproductor", min: 260, max: 760, classe: "sense-reproductor", boto: "#commuta-reproductor" },
};

function ampladaDe(nom) {
  return parseFloat(getComputedStyle(document.body).getPropertyValue(COLUMNES[nom].variable)) || 0;
}

function posaAmplada(nom, px) {
  const c = COLUMNES[nom];
  const altra = nom === "barra" ? "reproductor" : "barra";
  const lloc = window.innerWidth - (document.body.classList.contains(COLUMNES[altra].classe) ? 0 : ampladaDe(altra)) - MIN_TEXT;
  const amplada = Math.round(limita(px, c.min, Math.max(c.min, Math.min(c.max, lloc))));
  document.body.style.setProperty(c.variable, `${amplada}px`);
  return amplada;
}

function mostraColumna(nom, visible) {
  const c = COLUMNES[nom];
  document.body.classList.toggle(c.classe, !visible);
  $(c.boto).setAttribute("aria-pressed", String(visible));
  $(c.boto).title = (visible ? "Amaga " : "Mostra ") +
    (nom === "barra" ? "la columna de l'esquerra (⌃⌘S)" : "el vídeo (⌥⌘V)");
  desa(`tallat.amaga.${nom}`, !visible);
}

function instalaColumnes() {
  for (const [nom, c] of Object.entries(COLUMNES)) {
    const amplada = llegeix(`tallat.amplada.${nom}`, null);
    if (amplada) posaAmplada(nom, amplada);
    mostraColumna(nom, !llegeix(`tallat.amaga.${nom}`, false));
    $(c.boto).addEventListener("click", () => mostraColumna(nom, document.body.classList.contains(c.classe)));

    const vora = $(`#divisor-${nom}`);
    const deixa = () => {
      vora.classList.remove("arrossegant");
      document.body.classList.remove("redimensionant");
      desa(`tallat.amplada.${nom}`, ampladaDe(nom));
    };
    vora.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      vora.setPointerCapture(e.pointerId);
      vora.classList.add("arrossegant");
      document.body.classList.add("redimensionant");
    });
    vora.addEventListener("pointermove", (e) => {
      if (!vora.classList.contains("arrossegant")) return;
      posaAmplada(nom, nom === "barra" ? e.clientX : window.innerWidth - e.clientX);
    });
    vora.addEventListener("pointerup", deixa);
    vora.addEventListener("pointercancel", deixa);
    vora.addEventListener("dblclick", () => {  // torna a la mida normal
      document.body.style.removeProperty(c.variable);
      try { localStorage.removeItem(`tallat.amplada.${nom}`); } catch { /* sense memòria */ }
    });
    vora.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      const mes = (e.key === "ArrowRight") === (nom === "barra") ? 16 : -16;
      desa(`tallat.amplada.${nom}`, posaAmplada(nom, ampladaDe(nom) + mes));
    });
  }
  // Si la finestra es fa més petita, que el text no quedi espremut.
  window.addEventListener("resize", () => {
    for (const nom of Object.keys(COLUMNES)) {
      if (document.body.style.getPropertyValue(COLUMNES[nom].variable)) posaAmplada(nom, ampladaDe(nom));
    }
  });
}

const XEBRO_SECCIO = '<svg class="xebro-seccio" viewBox="0 0 20 20" aria-hidden="true"><path d="m8 5 5 5-5 5"/></svg>';

function instalaSeccions() {
  const plegades = new Set(llegeix("tallat.plegades", []));
  for (const seccio of $$(".barra .seccio[data-seccio]")) {
    const h2 = seccio.querySelector("h2");
    const boto = document.createElement("button");
    boto.className = "plega";
    boto.innerHTML = XEBRO_SECCIO;
    boto.append(...[...h2.childNodes]);  // el títol i el comptador hi passen tal qual
    h2.append(boto);
    const posa = (plegada) => {
      seccio.classList.toggle("plegada", plegada);
      boto.setAttribute("aria-expanded", String(!plegada));
    };
    posa(plegades.has(seccio.dataset.seccio));
    boto.addEventListener("click", () => {
      const plegada = !seccio.classList.contains("plegada");
      posa(plegada);
      if (plegada) plegades.add(seccio.dataset.seccio); else plegades.delete(seccio.dataset.seccio);
      desa("tallat.plegades", [...plegades]);
    });
  }
}

function instalaEstil() {
  // La capa de subtítols treballa a 1080 px d'amplada: l'escalem a la mida del reproductor.
  const capa = $("#capa-subtitols");
  new ResizeObserver(() => {
    for (const host of ["#ts-host", "#tt-host"]) $(host).style.transform = `scale(${capa.clientWidth / 1080})`;
  }).observe(capa);
  if (!window.gsap) registre("sense-gsap", {});  // sense internet: subtítols sense animacions

  $("#obre-estil").addEventListener("click", obreEstil);
  $("#tanca-estil").addEventListener("click", tancaEstil);
  const segmentat = (id, aplica, mostra) => {
    for (const b of $$(`#${id} button`)) b.addEventListener("click", () => canviaEstil(aplica(b.dataset.valor), mostra));
  };
  segmentat("e-paraules", (v) => ({ paraules_per_linia: AGRUPACIONS[v][0], lletres_per_linia: AGRUPACIONS[v][1] }), true);
  segmentat("e-apareixen", (v) => ({ apareixen: v }), true);
  segmentat("e-aspecte", (v) => ({ aspecte: v }));
  segmentat("e-fons", (v) => ({ fons: v }), true);
  segmentat("e-disposicio", (v) => ({ disposicio: v }), true);
  segmentat("e-alineacio", (v) => ({ alineacio: v }));
  $("#e-animacio").addEventListener("change", (e) => canviaEstil({ animacio: e.target.value }, true));
  $("#e-destacat").addEventListener("change", (e) => {
    const v = e.target.value;
    canviaEstil(v === "cap" ? { destaca: false } : { destaca: true, destacat: v }, true);
  });
  const interruptor = (id, clau, mostra = false) =>
    $(`#${id}`).addEventListener("click", () => canviaEstil({ [clau]: !estilSub[clau] }, mostra));
  interruptor("e-clau", "clau_grans");
  interruptor("e-emojis", "emojis", true);
  interruptor("e-majuscules", "majuscules");
  interruptor("e-ombra", "ombra");
  interruptor("e-clau-sola", "clau_sola", true);
  const lliscador = (id, clau) => $(`#${id}`).addEventListener("input", (e) => canviaEstil({ [clau]: +e.target.value }));
  lliscador("e-mida", "mida");
  lliscador("e-posicio", "posicio_y");
  lliscador("e-gruix", "gruix_contorn");
  lliscador("e-espaiat", "espaiat");
  lliscador("e-interlineat", "interlineat");
  lliscador("e-clau-mida", "clau_mida");
  const color = (id, clau) => $(`#${id}`).addEventListener("input", (e) => canviaEstil({ [clau]: e.target.value.toUpperCase() }));
  color("e-color", "color");
  color("e-color-actiu", "color_actiu");
  color("e-contorn", "contorn");
  color("e-fons-color", "fons_color");
  color("e-clau-color", "clau_color");
  $("#e-pes").addEventListener("change", (e) => canviaEstil({ pes: +e.target.value }));
  $("#e-font").addEventListener("change", (e) => {
    const v = e.target.value;
    if (v.startsWith("bib:")) baixaLletra(v.slice(4));
    else canviaEstil({ font: v, font_fitxer: null });
  });
  // El Safari només obre la finestra de triar fitxers des d'un clic en un botó (no des d'un desplegable).
  $("#puja-font").addEventListener("click", () => $("#fitxer-font").click());
  $("#fitxer-font").addEventListener("change", (e) => {
    const fitxer = e.target.files[0];
    e.target.value = "";
    if (fitxer) pujaFont(fitxer);
  });
  $("#restableix-estil").addEventListener("click", async () => {
    try {
      clearTimeout(temporitzadorEstil);
      estilPendent = {};
      await cua;
      respostaEstil(await api("/api/marca/restableix", {}));
      avis("Has tornat a l'estil de tallat.");
    } catch (e) { avis(e.message); }
  });
}

// Salta el que s'ha tret. Es crida a cada fotograma i també quan el vídeo avisa que
// ha avançat (per si el navegador alenteix el bucle de fotogrames).
function comprovaTall() {
  if (R.aturaA != null && R.reproduint && tempsMuntatge() >= R.aturaA) { atura(); }
  if (vista === "directe" && R.reproduint && trams.length && !R.v.seeking && R.salt == null) {
    const t = R.v.currentTime;
    const [a, b] = trams[Math.min(R.k, trams.length - 1)];
    // Passat el final del tros, sempre al següent del muntatge, encara que el navegador hagi anat
    // tard: buscar per temps de la gravació s'hi saltaria els trossos que s'han mogut més amunt.
    if (t >= b - 0.03) salta();
    else if (t < a - 0.3) recolloca();
  }
}

let paraulaMarcada = null;
function paraulaActual() {
  let t;
  if (vista === "directe") t = R.v.currentTime;
  else if (esborrany?.trams) {
    const m = vE.currentTime;
    let k = 0;
    while (k + 1 < esborrany.trams.length && esborrany.acum[k + 1] <= m) k++;
    t = esborrany.trams[k] ? esborrany.trams[k][0] + (m - esborrany.acum[k]) : null;
  }
  let id = null;
  if (t != null) {
    let lo = 0, hi = P.paraules.length - 1;
    while (lo <= hi) {
      const mig = (lo + hi) >> 1;
      if (P.paraules[mig].inici <= t) lo = mig + 1; else hi = mig - 1;
    }
    if (hi >= 0 && t <= P.paraules[hi].final + 0.15) id = hi;
  }
  if (id === paraulaMarcada) return;
  spans.get(paraulaMarcada)?.classList.remove("actual");
  paraulaMarcada = id;
  const s = spans.get(id);
  if (!s) return;
  s.classList.add("actual");
  if (sona() && performance.now() - darrerDesplacamentManual > 3000) {
    const r = s.getBoundingClientRect();
    if (r.top < 120 || r.bottom > innerHeight - 80) s.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

function pintaTemps() {
  const d = durada();
  const m = tempsMuntatge();
  const f = d ? limita(m / d, 0, 1) : 0;
  $("#ple").style.width = `${f * 100}%`;
  $("#capcal").style.left = `${f * 100}%`;
  $("#temps-actual").textContent = fmt(m);
  $("#temps-total").textContent = fmt(d);
}

function pintaMarques(llista, inicis, total) {
  const cont = $("#marques");
  cont.textContent = "";
  if (!total) return;
  for (let k = 1; k < llista.length; k++) {
    const i = document.createElement("i");
    i.style.left = `${(inicis[k] / total) * 100}%`;
    cont.append(i);
  }
}

function instalaReproductor() {
  R.v.src = "/proxy.mp4";
  for (const nom of ["play", "pause", "seeking", "seeked", "waiting", "stalled", "error", "ended"]) {
    R.v.addEventListener(nom, () => registre("v-" + nom, ev(R.v)));
  }
  R.v.addEventListener("error", () => avis("No puc obrir la còpia lleugera del vídeo (proxy.mp4)."));
  R.v.addEventListener("timeupdate", comprovaTall);
  // Si la pàgina deixa de veure's, el navegador alenteix els salts: parem perquè no soni el que s'ha tret.
  document.addEventListener("visibilitychange", () => { if (document.hidden && sona()) atura(); });
  // Primer salt quan ja hi ha dades (no només la informació general): el Safari ho agraeix.
  R.v.addEventListener("loadeddata", () => { if (!R.posat) vesA(0); pintaTemps(); }, { once: true });
  R.v.addEventListener("seeked", () => {
    if (R.salt != null) {  // el salt que esperava
      const t = R.salt;
      R.salt = null;
      posaTemps(t);
      return;
    }
    if (R.repren) {
      R.repren = false;
      if (R.reproduint && vista === "directe") R.v.play().catch(() => {});
    }
  });

  const commutaPlay = () => { R.aturaA = null; sona() ? atura() : reprodueix(); };
  $("#play").addEventListener("click", commutaPlay);
  $("#gran-play").addEventListener("click", commutaPlay);
  $("#enrere").addEventListener("click", () => vesA(tempsMuntatge() - 5));
  $("#endavant").addEventListener("click", () => vesA(tempsMuntatge() + 5));
  vE.addEventListener("play", () => document.body.classList.add("reproduint"));
  vE.addEventListener("pause", () => document.body.classList.remove("reproduint"));

  const linia = $("#linia-temps");
  let arrossega = null;
  const posa = (e) => {
    const r = linia.getBoundingClientRect();
    vesA(limita((e.clientX - r.left) / r.width, 0, 1) * durada());
  };
  linia.addEventListener("pointerdown", (e) => {
    linia.setPointerCapture(e.pointerId);
    arrossega = { sonava: sona() };
    if (arrossega.sonava) atura();
    posa(e);
  });
  linia.addEventListener("pointermove", (e) => { if (arrossega) posa(e); });
  linia.addEventListener("pointerup", () => {
    if (arrossega?.sonava) reprodueix();
    arrossega = null;
  });

  requestAnimationFrame(bucle);
}

// --- Vistes, esborranys i notes -------------------------------------------------------------

function canviaVista(nova) {
  if (nova === vista) return;
  atura();
  vista = nova;
  for (const b of $$("#vista button")) b.setAttribute("aria-checked", String(b.dataset.vista === vista));
  const directe = vista === "directe";
  R.v.classList.toggle("amagat", !directe);
  vE.classList.toggle("amagat", directe);
  $("#nova-nota").hidden = directe;
  $("#escolta").hidden = !directe;
  if (directe) pintaMarques(trams, acum, duradaFinal);
  else if (esborrany) pintaMarques(esborrany.trams || [], esborrany.acum || [], esborrany.durada);
  pintaTemps();
}

async function carregaVersio(nom, aTemps = 0) {
  let talls = null;
  try { talls = await (await fetch(`/exports/${encodeURIComponent(nom.replace(/\.mp4$/, ".talls.json"))}`)).json(); } catch { /* versió sense talls desats */ }
  const inicis = [];
  let t = 0;
  for (const [a, b] of talls || []) { inicis.push(t); t += b - a; }
  esborrany = { nom, trams: talls, acum: inicis, durada: t || null };
  $('#vista [data-vista="esborrany"]').disabled = false;
  vE.src = `/exports/${encodeURIComponent(nom)}`;
  vE.addEventListener("loadedmetadata", () => {
    esborrany.durada ||= vE.duration;
    vE.currentTime = aTemps;
    if (vista === "esborrany") pintaMarques(esborrany.trams || [], esborrany.acum, esborrany.durada);
    pintaTemps();
  }, { once: true });
  canviaVista("esborrany");
  if (vista === "esborrany") pintaMarques(esborrany.trams || [], esborrany.acum, esborrany.durada);
}

function pintaVersions(exports) {
  const cont = $("#versions");
  cont.textContent = "";
  if (!exports.length) { cont.innerHTML = '<p class="buit">Encara no has exportat res.</p>'; return; }
  for (const x of exports) {
    const item = document.createElement("div");
    item.className = "item";
    item.innerHTML = `<span class="context"><b style="color:var(--text)">${QUALITATS[x.qualitat] || "Vídeo"}</b> · ${x.data} · ${x.mida_mb} MB</span>
      <button class="mini" title="Mira-la" aria-label="Mira-la">${ICONES.play}</button>
      <button class="mini" title="Mostra al Finder" aria-label="Mostra al Finder">${ICONES.finder}</button>`;
    const [mira, finder] = item.querySelectorAll(".mini");
    mira.addEventListener("click", (e) => { e.stopPropagation(); carregaVersio(x.nom); });
    finder.addEventListener("click", (e) => { e.stopPropagation(); api("/api/mostra", { nom: x.nom }).catch((err) => avis(err.message)); });
    item.addEventListener("click", () => carregaVersio(x.nom));
    cont.append(item);
  }
  const darrer = exports.find((x) => x.qualitat === "esborrany");
  $('#vista [data-vista="esborrany"]').disabled = !darrer && !esborrany;
}

function pintaNotes() {
  $("#compte-notes").textContent = notes.length || "";
  const cont = $("#notes");
  cont.textContent = "";
  if (!notes.length) {
    cont.innerHTML = '<p class="buit">Construeix l\'esborrany i deixa-hi notes en moments exactes.</p>';
    return;
  }
  for (const n of notes) {
    const item = document.createElement("div");
    item.className = "item nota";
    item.innerHTML = `<span class="temps-petit">${fmt(n.temps)}</span><span class="context"></span>
      <button class="mini recorda" title="Recorda-ho per als vídeos següents" aria-label="Recorda-ho sempre">${ICONES.recorda}</button>
      <button class="mini esborra" title="Esborra la nota" aria-label="Esborra la nota">${ICONES.esborra}</button>`;
    item.querySelector(".context").textContent = n.text;
    item.querySelector(".recorda").addEventListener("click", (e) => {
      e.stopPropagation();
      afegeixRegla(n.text);
    });
    item.querySelector(".esborra").addEventListener("click", (e) => {
      e.stopPropagation();
      notes = notes.filter((x) => x.id !== n.id);
      desaNotes({ esborra: n.id });
    });
    item.addEventListener("click", () => {
      if (esborrany?.nom === n.versio) { canviaVista("esborrany"); vE.currentTime = n.temps; }
      else carregaVersio(n.versio, n.temps);
    });
    cont.append(item);
  }
}

// --- El teu gust ---------------------------------------------------------------------------------
// Regles que serveixen per als vídeos següents. Claude les afegeix quan li dius una correcció
// «per sempre»; aquí es veuen, se'n poden escriure i se'n poden treure.

function pintaGust() {
  $("#compte-gust").textContent = gust.length || "";
  const cont = $("#gust");
  cont.textContent = "";
  if (!gust.length) {
    cont.innerHTML = '<p class="buit">Quan diguis a l\'assistent una correcció «per sempre», sortirà aquí.</p>';
    return;
  }
  for (const r of gust) {
    const item = document.createElement("div");
    item.className = "item regla";
    item.innerHTML = `<span class="regla-text"><span class="regla-cos"></span><span class="regla-detall"></span></span>
      <button class="mini" title="Treu la regla" aria-label="Treu la regla">${ICONES.esborra}</button>`;
    item.querySelector(".regla-cos").textContent = r.text;
    item.querySelector(".regla-detall").textContent = (seccionsGust[r.seccio] || r.seccio) +
      (r.ajust ? " · s'aplica sola" : "");
    item.querySelector(".mini").addEventListener("click", () => treuRegla(r));
    cont.append(item);
  }
}

async function afegeixRegla(text) {
  try {
    gust = (await api("/api/gust", { text })).gust;
    pintaGust();
    avis("Ho recordaré per als vídeos següents.");
  } catch (e) { avis(e.message); }
}

async function treuRegla(r) {
  try {
    await cua;
    const res = await api("/api/gust/treu", { id: r.id });
    gust = res.gust;
    pintaGust();
    if (res.desfet) {  // l'opció que canviava ha tornat a com estava
      if (res.fonts_kit) carregaFontsKit(res.fonts_kit);
      aplicaEstilSubtitols(res.estil_subtitols);
      aplicaTrams(res);
      pintaPanellEstil();
    }
    avis(res.desfet ? "Regla treta. L'opció que canviava ha tornat a com estava." : "Regla treta.");
  } catch (e) { avis(e.message); }
}

// Les notes es desen d'una en una (afegir o esborrar), perquè dues pestanyes no es trepitgin.
async function desaNotes(operacio) {
  pintaNotes();
  try {
    notes = (await api("/api/notes", operacio)).notes;
    pintaNotes();
  } catch (e) { avis("No s'ha pogut desar la nota: " + e.message); }
}

function afegeixNota(text) {
  if (!esborrany) return;
  const m = vE.currentTime;
  let original = null;
  if (esborrany.trams?.length) {
    let k = 0;
    while (k + 1 < esborrany.trams.length && esborrany.acum[k + 1] <= m) k++;
    original = arrodoneix(esborrany.trams[k][0] + (m - esborrany.acum[k]));
  }
  const nota = { id: Date.now(), versio: esborrany.nom, temps: arrodoneix(m), temps_original: original,
                 text, creada: new Date().toISOString() };
  notes.push(nota);
  notes.sort((a, b) => (a.versio === b.versio ? a.temps - b.temps : a.id - b.id));
  desaNotes({ afegeix: nota });
}

// --- Renders --------------------------------------------------------------------------------

let consulta = null;
function seguimentFeina(feina) {
  const caixa = $("#feina");
  const ocupat = feina?.estat === "treballant";
  $("#esborrany").disabled = ocupat;
  $("#final").disabled = ocupat;
  caixa.hidden = !ocupat;
  if (ocupat) {
    const nom = feina.qualitat === "esborrany" ? "Construint l'esborrany"
      : feina.qualitat === "editors" ? "Exportant els trossos" : `Exportant en ${QUALITATS[feina.qualitat]}`;
    if (feina.fase === "editors") {
      $("#feina-text").textContent = "Preparant el projecte per a altres editors…";
      $("#feina-progres").style.width = "50%";
    } else if (feina.fase === "subtitols") {
      $("#feina-text").textContent = "Dibuixant els subtítols…";
      $("#feina-progres").style.width = "12%";
    } else {
      $("#feina-text").textContent = `${nom}… ${feina.progres} %`;
      $("#feina-progres").style.width = `${feina.progres}%`;
    }
    if (!consulta) consulta = setInterval(consultaFeina, 700);
  } else if (consulta) {
    clearInterval(consulta);
    consulta = null;
  }
}

async function consultaFeina() {
  try {
    const r = await api("/api/feina");
    const feina = r.feina;
    seguimentFeina(feina);
    if (feina?.estat === "fet" && feina.fitxer && feina.fitxer !== consultaFeina.darrer) {
      consultaFeina.darrer = feina.fitxer;
      pintaVersions(r.exports);
      if (feina.qualitat === "editors") {
        avis("A punt. T'obro la carpeta: hi ha un LLEGEIX-ME amb els passos.", 6000);
        api("/api/mostra", { nom: feina.fitxer }).catch(() => {});
      } else if (feina.qualitat === "esborrany") {
        avis("L'esborrany és a punt. Mira'l i deixa-hi notes.");
        carregaVersio(feina.fitxer);
      } else {
        avis(`Versió final en ${QUALITATS[feina.qualitat]} a punt.`);
      }
    } else if (feina?.estat === "error") {
      avis("El render ha fallat: " + feina.error, 6000);
    }
  } catch (e) {
    avis("He perdut el contacte amb tallat. Torna a obrir la pàgina de revisió.", 6000);
    seguimentFeina(null);
  }
}

async function comencaRender(qualitat) {
  try {
    await canvisDesats();
    const r = await api("/api/exporta", { qualitat });
    seguimentFeina(r.feina);
  } catch (e) {
    avis(e.message);
  }
}

function obreFinal() {
  const o = P.origen || {};
  $("#final-durada").textContent = `Durada: ${fmt(duradaFinal)} · ${trams.length} trossos`;
  const avisFinal = $("#final-avis");
  if (o.amplada && o.amplada * 16 > o.alcada * 9) {
    const ample = Math.round((o.alcada * 9) / 16);
    avisFinal.textContent = `La gravació és horitzontal: el reel n'aprofita ${ample} × ${o.alcada} píxels. ` +
      "En 4K la imatge s'amplia i no guanya detall respecte a 1080, però hi ha plataformes que la tracten millor.";
    avisFinal.hidden = false;
  } else avisFinal.hidden = true;
  $("#velo").hidden = false;
  $("#full-final").hidden = false;
  $("#confirma-final").focus();
}

function tancaFinal() {
  $("#velo").hidden = true;
  $("#full-final").hidden = true;
}

// --- Reels proposats (primer muntatge) ---------------------------------------------------------

function pintaReels() {
  const cont = $("#reels");
  const reels = P.reels || [];
  $("#compte-reels").textContent = reels.length || "";
  const obert = reels.find((r) => r.id === P.reel_actual);
  $("#tornar").hidden = !P.reel_actual;
  if (P.reel_actual) {
    $("#nom-projecte").textContent = obert?.titol || P.nom;
    $("#marca").textContent = `tallat · ${P.arrel}`;
    document.title = `${obert?.titol || P.nom} · tallat`;
  }
  for (const e of P.errors_reels || []) avis(`reels.json: ${e}`, 6000);
  if (!reels.length) return;
  cont.textContent = "";
  for (const r of reels) {
    const item = document.createElement("div");
    item.className = "item reel" + (r.id === P.reel_actual ? " obert" : "");
    item.title = r.per_que || "";
    item.innerHTML = `<span class="reel-text"><span class="reel-titol"></span><span class="reel-detall"></span></span>
      <span class="reel-durada">${fmt(r.durada)}</span>`;
    item.querySelector(".reel-titol").textContent = r.titol;
    item.querySelector(".reel-detall").textContent = r.ganxo ? `«${r.ganxo}»` : "";
    item.addEventListener("click", () => obre(r.id));
    cont.append(item);
  }
}

async function obre(reel) {
  if (reel === P.reel_actual) return;
  atura();
  try {
    await cua;  // que no quedi cap canvi per desar
    await api("/api/obre", { reel });
    location.reload();
  } catch (e) { avis(e.message); }
}

// --- B-roll en directe ----------------------------------------------------------------------

const vB = $("#video-broll");
function pintaBroll() {
  const m = tempsMuntatge();
  const b = vista === "directe" ? brollsMuntatge.find((x) => m >= x.inici && m < x.inici + x.durada) : null;
  vB.classList.toggle("amagat", !b);
  if (!b) { if (!vB.paused) vB.pause(); return; }
  if (!vB.src.endsWith(b.url)) vB.src = b.url;
  const desitjat = m - b.inici;
  if (vB.readyState >= 1 && Math.abs(vB.currentTime - desitjat) > 0.15) vB.currentTime = desitjat;
  if (R.reproduint && vB.paused) vB.play().catch(() => {});
  if (!R.reproduint && !vB.paused) vB.pause();
}

// Stickers en directe: mateixa posició, mida i rotació que tindran a l'export.
const stickersVius = new Map();
function pintaStickers() {
  const m = tempsMuntatge();
  const e = P?.estil_stickers || {};
  const actius = new Set();
  if (vista === "directe") {
    stickersMuntatge.forEach((st, k) => {
      if (m < st.inici || m >= st.inici + st.durada) return;
      actius.add(st.id);
      if (stickersVius.has(st.id)) return;
      const img = document.createElement("img");
      img.className = "sticker-viu";
      img.src = st.url;
      const x = k % 2 === 0 ? (e.x ?? 0.72) : 1 - (e.x ?? 0.72);
      img.style.left = `${x * 100}%`;
      img.style.top = `${(e.y ?? 0.3) * 100}%`;
      img.style.width = `${(e.mida ?? 0.34) * 100}%`;
      img.style.setProperty("--rot", `${(e.rotacio ?? 8) * (k % 2 === 0 ? 1 : -1)}deg`);
      if (e.ombra === false) img.style.setProperty("--ombra-sticker", "none");
      if (e.animacio === "cap") img.style.animation = "none";
      $("#capa-stickers").append(img);
      stickersVius.set(st.id, img);
    });
  }
  for (const [id, img] of stickersVius) if (!actius.has(id)) { img.remove(); stickersVius.delete(id); }
}

let instruccioPerPujar = null;
async function pujaBroll(iid, fitxer) {
  avis(`Pujant «${fitxer.name}»…`, 20000);
  try {
    await cua;
    const json = await resposta(await fetch(
      `/api/broll/puja?instruccio=${encodeURIComponent(iid)}&nom=${encodeURIComponent(fitxer.name)}`,
      { method: "POST", headers: capcaleres(), body: fitxer }));
    estat = json.estat;
    aplicaTrams(json);
    refresca(true);
    avis("Fet. Mira-ho al reproductor.");
  } catch (e) { avis(e.message, 6000); }
}

async function accioBroll(ruta, dades, missatge) {
  try {
    await cua;
    const r = await api(ruta, dades);
    estat = r.estat;
    aplicaTrams(r);
    refresca(true);
    if (missatge) avis(missatge);
  } catch (e) { avis(e.message, 6000); }
}

function accionsBroll(ins, item) {
  if (!["broll", "sticker"].includes(ins.tipus) || ins.estat !== "acceptada") return null;
  const nom = ins.tipus === "sticker" ? "Sticker" : "B-roll";
  const llista = biblioteca[ins.tipus] || [];
  const fila = document.createElement("span");
  fila.className = "ins-accions";
  if (ins.fitxer) {
    fila.innerHTML = `<span class="fet">${nom} a punt (${String(ins.durada).replace(".", ",")} s)</span>
      <button class="enllac canvia">Canvia'l</button><button class="enllac treu-broll">Treu-lo</button>`;
  } else {
    fila.innerHTML = `<button class="enllac canvia">Puja un fitxer…</button>`;
    if (llista.length) {
      const tria = document.createElement("select");
      tria.innerHTML = `<option value="">o tria'n un de la biblioteca</option>` +
        llista.map(() => `<option></option>`).join("");
      [...tria.options].slice(1).forEach((o, i) => { o.value = llista[i]; o.textContent = llista[i]; });
      tria.addEventListener("click", (e) => e.stopPropagation());
      tria.addEventListener("change", () => tria.value && accioBroll("/api/broll/biblioteca",
        { instruccio: ins.id, nom: tria.value }, `${nom} preparat.`));
      fila.append(tria);
    }
  }
  fila.querySelector(".canvia").addEventListener("click", (e) => {
    e.stopPropagation();
    instruccioPerPujar = ins.id;
    $("#fitxer-broll").click();
  });
  fila.querySelector(".treu-broll")?.addEventListener("click", (e) => {
    e.stopPropagation();
    accioBroll("/api/broll/treu", { instruccio: ins.id }, `${nom} tret.`);
  });
  // També s'hi pot arrossegar un fitxer des del Finder.
  item.addEventListener("dragover", (e) => { e.preventDefault(); item.classList.add("arrossegant"); });
  item.addEventListener("dragleave", () => item.classList.remove("arrossegant"));
  item.addEventListener("drop", (e) => {
    e.preventDefault();
    item.classList.remove("arrossegant");
    const fitxer = e.dataTransfer.files[0];
    if (fitxer) pujaBroll(ins.id, fitxer);
  });
  return fila;
}

// --- Instruccions de veu -------------------------------------------------------------------

const TIPUS_INSTRUCCIO = {
  talla: ["Torna a començar", "En acceptar-la, es treu el primer intent."],
  zoom: ["Zoom", "En acceptar-la, el tros que ve s'apropa."],
  broll: ["B-roll / imatges", "En acceptar-la, hi pots posar un vídeo o una imatge."],
  sticker: ["Sticker", "En acceptar-la, hi pots posar una imatge (PNG amb fons transparent)."],
  altre: ["Altres", "Queda apuntada."],
};

function pintaInstruccions() {
  const seccio = $("#seccio-instruccions");
  seccio.hidden = !instruccions.length;
  const pendents = instruccions.filter((i) => i.estat === "pendent").length;
  $("#compte-instruccions").textContent = pendents ? `${pendents} per decidir` : "";
  const cont = $("#instruccions");
  cont.textContent = "";
  for (const ins of instruccions) {
    const [nom, ajuda] = TIPUS_INSTRUCCIO[ins.tipus] || TIPUS_INSTRUCCIO.altre;
    const item = document.createElement("div");
    item.className = `item instruccio ${ins.estat}`;
    item.title = ajuda;
    item.innerHTML = `<span class="reel-text">
        <span class="ins-tipus"><span class="nom"></span><span class="temps-petit">${fmt(ins.inici)}</span></span>
        <span class="ins-text"></span>
        <span class="ins-estat"></span></span>
      <button class="mini deixa ${ins.estat === "acceptada" ? "actiu" : ""}" title="Accepta-la" aria-label="Accepta-la">${ICONES.deixa}</button>
      <button class="mini treu" title="Descarta-la" aria-label="Descarta-la">${ICONES.esborra}</button>`;
    item.querySelector(".nom").textContent = nom;
    item.querySelector(".ins-text").textContent = `«${ins.text}»`;
    item.querySelector(".ins-estat").textContent =
      ins.estat === "acceptada" ? (["broll", "sticker"].includes(ins.tipus) ? "" : `Acceptada. ${ajuda.replace(/^En acceptar-la, /, "")}`)
        : ins.estat === "descartada" ? "Descartada"
        : ins.dubtosa ? "No he sabut on acaba: no he tret res del vídeo. Treu-ne tu les paraules." : "";
    const accions = accionsBroll(ins, item);
    if (accions) item.querySelector(".reel-text").append(accions);
    item.addEventListener("click", (e) => {
      if (e.target.closest(".deixa")) return decideixInstruccio(ins, ins.estat === "acceptada" ? "pendent" : "acceptada");
      if (e.target.closest(".treu")) return decideixInstruccio(ins, ins.estat === "descartada" ? "pendent" : "descartada");
      const ancora = ins.ancora ?? ins.paraules[1];
      mostraParaula(ancora);
      if (vista === "directe") vesAOriginal(P.paraules[ancora].inici - 1.5);
    });
    cont.append(item);
  }
}

async function decideixInstruccio(ins, nou) {
  try {
    await cua;  // primer, que es desin els canvis pendents
    const r = await api("/api/instruccio", { id: ins.id, estat: nou });
    estat = r.estat;
    aplicaTrams(r);
    refresca(true);
    if (nou === "acceptada" && ins.tipus === "talla") avis("Primer intent tret. El pots recuperar tocant-ne les paraules.");
  } catch (e) { avis(e.message); }
}

// --- Avisos -----------------------------------------------------------------------------------

let temporitzadorAvis = null;
function avis(text, ms = 2600) {
  const el = $("#avis-flotant");
  el.textContent = text;
  el.classList.add("visible");
  clearTimeout(temporitzadorAvis);
  temporitzadorAvis = setTimeout(() => el.classList.remove("visible"), ms);
}

// --- Inici ------------------------------------------------------------------------------------

const AJUDES = {
  talla: "Clic en una paraula per escoltar des d'allà. Clic dret per treure-la o recuperar-la; arrossega amb el clic dret per fer-ho amb unes quantes. Per canviar l'ordre d'un paràgraf, arrossega'l per la nansa ⠿ de l'esquerra.",
  corregeix: "Toca una paraula per corregir com s'escriu als subtítols. <kbd>↩</kbd> per desar, <kbd>esc</kbd> per deixar-ho.",
  destaca: "Toca una paraula per destacar-la als subtítols (més gran i d'un altre color) o per deixar de destacar-la. Les subratllades ja ho estan: les que no triïs, les tria tallat.",
};

function instalaControls() {
  for (const b of $$("#mode button")) {
    b.addEventListener("click", () => {
      mode = b.dataset.mode;
      for (const x of $$("#mode button")) x.setAttribute("aria-checked", String(x === b));
      document.body.classList.toggle("mode-corregeix", mode === "corregeix");
      document.body.classList.toggle("mode-destaca", mode === "destaca");
      $("#ajuda").innerHTML = AJUDES[mode];
      if (mode === "destaca") marcaClaus();
    });
  }
  for (const b of $$("#pauses button")) {
    b.addEventListener("click", () => {
      const v = parseFloat(b.dataset.pausa);
      canvia((e) => { e.pausa_maxima = v > 0 ? v : null; }, { repinta: true });
      marcaPausa();
    });
  }
  for (const b of $$("#vista button")) b.addEventListener("click", () => {
    if (b.dataset.vista === "esborrany" && !esborrany) {
      const darrer = $$("#versions .item")[0];
      if (darrer) darrer.click();
      return;
    }
    canviaVista(b.dataset.vista);
  });
  $("#tornar").addEventListener("click", () => obre(null));
  $("#fitxer-broll").addEventListener("change", (e) => {
    const fitxer = e.target.files[0];
    if (fitxer && instruccioPerPujar) pujaBroll(instruccioPerPujar, fitxer);
    e.target.value = "";
  });
  $("#torna-netejar").addEventListener("click", async () => {
    desfer.push(copia(estat));
    refer.length = 0;
    try {
      const r = await api("/api/neteja", {});
      estat = r.estat;
      aplicaTrams(r);
      refresca(true);
      marcaPausa();
      avis("Neteja feta. Les paraules que havies recuperat es respecten.");
    } catch (e) { avis(e.message); }
  });
  instalaColumnes();
  instalaSeccions();
  instalaEstil();
  instalaKits();
  instalaTitol();
  setInterval(miraNovetats, 3000);
  const subtitolsBoto = $("#subtitols");
  subtitolsBoto.addEventListener("click", () => {
    canvia((e) => { e.subtitols = e.subtitols === false; });
    marcaSubtitols();
    avis(estat.subtitols ? "Els renders portaran subtítols." : "Els renders sortiran sense subtítols.");
  });
  const interruptor = $("#escolta");
  interruptor.setAttribute("aria-checked", String(escoltaActiva));
  interruptor.addEventListener("click", () => {
    escoltaActiva = !escoltaActiva;
    interruptor.setAttribute("aria-checked", String(escoltaActiva));
    try { localStorage.setItem("tallat.escolta", escoltaActiva ? "si" : "no"); } catch { /* sense memòria del navegador */ }
    avis(escoltaActiva ? "Sentiràs cada tall en fer-lo." : "Ja no sonarà res en fer un tall.");
  });
  $("#desfes").addEventListener("click", desfes);
  $("#refes").addEventListener("click", refes);
  $("#esborrany").addEventListener("click", () => comencaRender("esborrany"));
  $("#final").addEventListener("click", obreFinal);
  $("#cancella-final").addEventListener("click", tancaFinal);
  $("#velo").addEventListener("click", tancaFinal);
  const perAEditors = async (dades) => {
    tancaFinal();
    try {
      await canvisDesats();
      seguimentFeina((await api("/api/editors", dades)).feina);
    } catch (e) { avis(e.message); }
  };
  $("#exporta-editors").addEventListener("click", () => perAEditors({ capa: $("#editors-capa").checked }));
  $("#exporta-trossos").addEventListener("click", () => perAEditors({ trossos: true }));
  $("#confirma-final").addEventListener("click", () => {
    const qualitat = document.querySelector('input[name="qualitat"]:checked').value;
    tancaFinal();
    comencaRender(qualitat);
  });
  $("#nova-nota").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = $("#text-nota").value.trim();
    if (!text) return;
    afegeixNota(text);
    $("#text-nota").value = "";
    avis(`Nota afegida a ${fmt(vE.currentTime)}`);
  });
  $("#text-nota").addEventListener("focus", () => vE.pause());
  $("#nova-regla").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = $("#text-regla").value.trim();
    if (!text) return;
    afegeixRegla(text);
    $("#text-regla").value = "";
  });

  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea, select")) return;
    if (!$("#full-final").hidden) { if (e.key === "Escape") tancaFinal(); return; }
    if (editantEstil && e.key === "Escape") { tancaEstil(); return; }
    if (editantTitol && e.key === "Escape") { tancaTitol(); return; }
    if (e.ctrlKey && e.metaKey && e.code === "KeyS") {  // ⌃⌘S, com al Finder
      e.preventDefault();
      mostraColumna("barra", document.body.classList.contains("sense-barra"));
      return;
    }
    if (e.altKey && e.metaKey && e.code === "KeyV") {  // ⌥⌘V
      e.preventDefault();
      mostraColumna("reproductor", document.body.classList.contains("sense-reproductor"));
      return;
    }
    if (e.key === " ") { e.preventDefault(); R.aturaA = null; sona() ? atura() : reprodueix(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); vesA(tempsMuntatge() - 5); }
    else if (e.key === "ArrowRight") { e.preventDefault(); vesA(tempsMuntatge() + 5); }
    else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? refes() : desfes(); }
  });
}

function marcaSubtitols() {
  $("#subtitols").setAttribute("aria-checked", String(estat.subtitols !== false));
}

function marcaPausa() {
  const actual = estat.pausa_maxima || 0;
  for (const b of $$("#pauses button")) b.setAttribute("aria-checked", String(parseFloat(b.dataset.pausa) === actual));
}

async function inicia() {
  instalaControls();
  instalaText();
  instalaReproductor();
  try {
    P = await api("/api/projecte");
  } catch (e) {
    avis("No puc carregar el projecte: " + e.message, 10000);
    return;
  }
  document.title = `${P.nom} · tallat`;
  registre("inici", { navegador: navigator.userAgent, finestra: [innerWidth, innerHeight] });
  $("#nom-projecte").textContent = P.nom;
  $("#durada-original").textContent = fmt(P.durada);
  estat = P.estat;
  notes = P.notes || [];
  aplicaTrams(P);
  pintaText();
  refresca(false);
  marcaPausa();
  marcaSubtitols();
  estilsPredefinits = P.estils_subtitols || [];
  estilsTitol = P.estils_titol || [];
  aplicaEstilTitol(P.estil_titol);
  kits = P.kits || [];
  kitActual = P.kit;
  pintaKits();
  bibliotecaLletres = P.biblioteca_lletres || bibliotecaLletres;
  versioEstil = P.versio_estil;
  carregaFontsKit(P.fonts_kit || []);
  aplicaEstilSubtitols(P.estil_subtitols);
  pintaNotes();
  gust = P.gust || [];
  seccionsGust = P.seccions_gust || {};
  pintaGust();
  pintaVersions(P.exports || []);
  pintaReels();
  try { biblioteca = await api("/api/biblioteca"); } catch { biblioteca = { broll: [], sticker: [] }; }
  pintaInstruccions();
  if (P.feina?.estat === "treballant") seguimentFeina(P.feina);
  consultaFeina.darrer = P.feina?.fitxer;
}

inicia();
