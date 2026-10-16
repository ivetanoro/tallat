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
let editantEstil = false;  // la pestanya Subtítols és oberta: el reproductor en mostra una línia d'exemple
let instruccions = [];     // instruccions de veu «Claude, …»
let zoomsTram = [];        // quins trossos porten zoom
let brollsMuntatge = [];   // b-rolls situats al muntatge: [{id, inici, durada, url}]
let stickersMuntatge = []; // stickers situats al muntatge: [{id, inici, durada, url}]
let biblioteca = { broll: [], sticker: [] };  // fitxers de ~/.tallat/broll/ i ~/.tallat/stickers/
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
  pintaPla();
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
  if ("titol" in r && !titolEsborrany) { titolMuntatge = r.titol; previaBruta = true; }  // no el que s'escriu
  if (r.paragrafs && P && r !== P && JSON.stringify(r.paragrafs) !== JSON.stringify(P.paragrafs)) {
    P.paragrafs = r.paragrafs;  // l'ordre dels paràgrafs ha canviat (moure'ls, desfer-ho, una altra pestanya)
    pintaText();
  }
  if (r.zooms) zoomsTram = r.zooms;
  if (r.brolls) { brollsMuntatge = r.brolls; pintaResumBroll(); }
  if (r.grafics_dibuix) dibuixosGrafics = r.grafics_dibuix;
  if (r.grafics) { graficsMuntatge = r.grafics; previaBruta = true; pintaPla(); }
  if (r.efectes) { efectesMuntatge = r.efectes; pintaSo(); }
  if ("pista_efectes" in r) posaPistaEfectes(r.pista_efectes);
  if (r.stickers) stickersMuntatge = r.stickers;
  if (r.zoom) { zoomVideo = r.zoom; $(".pantalla").style.setProperty("--zoom", r.zoom); }
  if (r.blocs) blocsMuntatge = r.blocs;
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
  $("#seccio-propostes").hidden = !total;
  actualitzaPestanyes();
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
      fesClicable(item);
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
  pintaBloc();
  pintaStickers();
  sonaEfectes();
  pintaMarcCapa();
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
  for (const anterior of [previa, previaTitol, previaGrafics]) anterior?.kill?.();
  if (!window.TallatSubtitols) { previa = previaTitol = previaGrafics = null; return; }
  const titol = titolVisible();
  const grafics = graficsVisibles();
  // Com al vídeo final: mentre hi ha el títol (si l'estil ho diu) o una frase clau, sense subtítols.
  const amaga = [...(titol && estilTitol?.amaga_subtitols ? [[titol.inici, titol.final]] : []),
    ...grafics.filter((g) => g.amaga_subtitols).map((g) => [g.inici, g.final])];
  previa = estilSub ? TallatSubtitols.construeix($("#ts-host"), liniesSub, estilSub, { familia: familiaCss(estilSub), amaga }) : null;
  previaTitol = estilTitol ? TallatSubtitols.titol($("#tt-host"), titol, estilTitol,
    { familia: familiaCss({ font: estilTitol.font || estilSub?.font }) }) : null;
  previaGrafics = window.TallatGrafics && paletaGrafics ? TallatGrafics.construeix($("#tg-host"), grafics, paletaGrafics, OP_GRAFICS) : null;
  // Com al vídeo final: mentre surt el títol, els subtítols que el toquen s'aparten.
  if (titol && previa && previaTitol && !estilTitol?.amaga_subtitols) TallatSubtitols.aparta($("#ts-host"), $("#tt-host"), titol, previa);
}

function pintaSubtitols() {
  const capa = $("#capa-subtitols");
  const ambSubtitols = (estat?.subtitols !== false || editantEstil) && liniesSub.length > 0;
  const titol = titolVisible();
  const visible = vista === "directe" && (ambSubtitols || !!titol || graficsMuntatge.length > 0);
  capa.hidden = !visible;
  if (!visible) return;
  $("#ts-host").hidden = !ambSubtitols;
  if (previaBruta) refaPrevia();
  let m = tempsMuntatge();
  if (editantTitol && !sona() && titol && !(m >= titol.inici && m < titol.final)) {
    // Mentre es tria l'estil del títol amb el vídeo aturat, el títol sempre es veu (ja escrit).
    m = Math.max(titol.inici, titol.final - 0.35);
  } else if (previa && editantEstil && !sona() && liniesSub.length && !liniesSub.some((l) => m >= l.inici && m < l.final)) {
    // Mentre es tria l'estil amb el vídeo aturat, sempre hi ha una línia d'exemple a la vista.
    const l = liniesSub.find((x) => x.inici >= m) || liniesSub[liniesSub.length - 1];
    const w = l.paraules[Math.min(1, l.paraules.length - 1)];
    m = Math.min(l.final - 0.01, w.inici + 0.45);
  }
  if (m === previaTemps) return;
  previa?.seek(m, false);
  previaTitol?.seek(m, false);
  previaGrafics?.seek(m, false);
  previaTemps = m;
}

const escapaFont = (f) => (/^[\w-]+$/.test(f) ? f : `"${String(f).replace(/["\\]/g, "")}"`);
const familiaCss = (e) => `${escapaFont(e.font || "system-ui")}, system-ui, sans-serif`;

function aplicaEstilSubtitols(e) {
  if (!e) return;
  estilSub = e;
  previaBruta = true;
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
      const font = new FontFace(f.familia, `url(${f.url})`, { weight: String(f.pes), style: f.estil || "normal" });
      fontsCarregades.set(f.url, font);
      await font.load();
      document.fonts.add(font);
      previaBruta = true;
    } catch {
      fontsCarregades.delete(f.url);
      avis(`No he pogut carregar la lletra «${f.familia}». Torna-la a pujar o tria'n una altra.`, 5000);
    }
  }
}

// Els valors d'un estil fet amb els colors de la marca, si n'hi ha: la marca mana.
function ambMarca(seccio, valors) {
  const m = estilMarca || {};
  const v = { ...valors };
  if (m.color_destacat) {
    if (seccio === "subtitols") for (const k of ["color_actiu", "clau_color"]) if (k in v) v[k] = m.color_destacat;
    if (seccio === "titol" && "clau_color" in v) v.clau_color = m.color_destacat;
  }
  if (m.color_principal && seccio === "broll" && "vora_color" in v && v.vora_color == null) v.vora_color = m.color_principal;
  return v;
}

// L'estil fet que té tots els valors d'un estil (o null: és «Personalitzat»).
function predefinitDe(llista, e, seccio) {
  if (!e) return null;
  return llista.find((p) => Object.entries(ambMarca(seccio, p.valors)).every(([k, v]) =>
    (typeof v === "number" ? Math.abs((e[k] ?? NaN) - v) < 1e-6 : String(e[k]).toUpperCase() === String(v).toUpperCase())));
}
const predefinitActual = (e = estilSub) => predefinitDe(estilsPredefinits, e, "subtitols");
const predefinitTitol = (e = estilTitol) => predefinitDe(estilsTitol, e, "titol");
const predefinitBroll = (e = estilBroll) => predefinitDe(estilsBroll, e, "broll");

// Un botó de les galeries d'estils fets (subtítols, títol i b-roll). Torna la caixa de la mostra.
function botoEstil(cont, p, actiu, tria) {
  const b = document.createElement("button");
  b.className = "estil";
  b.setAttribute("role", "radio");
  b.setAttribute("aria-checked", String(actiu));
  b.title = p.descripcio;
  b.innerHTML = `<span class="estil-mostra"></span><span class="estil-nom"></span>`;
  b.querySelector(".estil-nom").textContent = p.nom;
  b.addEventListener("click", tria);
  cont.append(b);
  return b.querySelector(".estil-mostra");
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


// El desplegable de lletres: les del kit que ha pujat la persona, les del Mac i les gratuïtes (les que
// encara no són al kit porten «bib:»: triar-les les baixa). Amb `laDelsSubtitols`, també «la dels subtítols».
function ompleLletres(select, valor, { laDelsSubtitols = false, buit = null } = {}) {
  select.textContent = "";
  const grup = (nom) => { const g = document.createElement("optgroup"); g.label = nom; select.append(g); return g; };
  const opcio = (on, v, text) => { const o = document.createElement("option"); o.value = v; o.textContent = text; on.append(o); };
  if (buit) opcio(select, "", buit);
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

let estilsMostrats = false;  // «Més estils» desplegat
function pintaPanellEstil() {
  const e = estilSub;
  if (!e || $("#pestanya-subtitols").hidden) return;
  const actual = predefinitActual();
  const cont = $("#estils");
  cont.textContent = "";
  for (const p of estilsPredefinits) {
    const valors = ambMarca("subtitols", p.valors);
    const mostra = botoEstil(cont, p, p === actual, () => canviaEstil(valors, true));
    if (window.TallatSubtitols) {
      const v = { ...e, ...valors };
      const n = v.paraules_per_linia <= 1 ? 1 : v.paraules_per_linia <= 4 ? 3 : 4;
      pintaMostra(mostra, v,
        { paraules: n === 1 ? [MOSTRA[2]] : MOSTRA.slice(0, n), alcada: 675, mida: Math.min(0.2, v.mida * 1.6) });
    }
  }
  // Es veuen els 6 primers; la resta, amb «Més estils» (o si el triat és un d'aquests).
  const tots = estilsMostrats || estilsPredefinits.indexOf(actual) >= 6;
  cont.classList.toggle("tots", tots);
  $("#mes-estils").hidden = estilsPredefinits.length <= 6;
  $("#mes-estils").textContent = tots ? "Menys estils" : `Més estils (${estilsPredefinits.length - 6})`;
  $("#mes-estils").setAttribute("aria-expanded", String(tots));
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
  $("#e-alineacio").closest(".camp").hidden = e.disposicio === "escampat";  // escampades: cada fila al seu lloc
  marcaSegmentat("e-alineacio", e.alineacio || "centre");
  $("#camps-clau").hidden = !e.clau_grans;
  $("#e-clau-mida").value = e.clau_mida ?? 1.4;
  $("#e-clau-color").value = (e.clau_color || e.color_actiu).toLowerCase();
  ompleLletres($("#e-clau-font"), e.clau_font, { buit: "La mateixa" });
  $("#e-clau-cursiva").setAttribute("aria-checked", String(!!e.clau_cursiva));
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

// --- Desar l'estil ------------------------------------------------------------------------------
// Cada canvi d'estil (subtítols, títol, b-roll o so) es veu a l'instant i es desa al cap d'un moment,
// tots junts (els lliscadors n'envien molts), a la cua de peticions. Cada petició diu a quin kit va:
// si mentrestant el vídeo ha canviat de kit, el servidor no la desa en un altre.
const pendents = { subtitols: {}, titol: {}, broll: {}, so: {}, marca: {} };
let temporitzadorDesa = null;

function apunta(seccio, canvis) {
  Object.assign(pendents[seccio], canvis);
  clearTimeout(temporitzadorDesa);
  temporitzadorDesa = setTimeout(desaEstils, 300);
}

// Envia el que hi hagi pendent; torna la cua (qui ha d'esperar que estigui desat, l'espera).
function desaEstils() {
  clearTimeout(temporitzadorDesa);
  const canvis = {};
  for (const [seccio, valors] of Object.entries(pendents)) {
    if (Object.keys(valors).length) { canvis[seccio] = valors; pendents[seccio] = {}; }
  }
  if (!Object.keys(canvis).length) return cua.catch(() => {});
  const kit = kitActual;
  cua = cua.catch(() => {}).then(async () => {
    try {
      respostaEstil(await api("/api/marca", { ...canvis, kit }));
    } catch (e) {
      avis(e.message, 6000);
      if (e.dades?.kits) respostaEstil(e.dades);  // el kit nou, tal com és
    }
  });
  return cua;
}

// Torna una secció a l'estil de tallat (el que hi hagués pendent d'aquella secció, fora).
async function restableix(seccio, missatge) {
  pendents[seccio] = {};
  await desaEstils();
  try {
    respostaEstil(await api("/api/marca/restableix", { seccio, kit: kitActual }));
    avis(missatge);
  } catch (e) { avis(e.message); }
}

function canviaEstil(canvis, mostra = false) {
  aplicaEstilSubtitols({ ...estilSub, ...canvis });
  pintaPanellEstil();
  apunta("subtitols", canvis);
  if (mostra) mostraAnimacio();
}

// La resposta de qualsevol canvi d'estil o de kit: l'estil i, com que pot canviar el que es veu
// (subtítols, b-roll, efectes de so…), també el muntatge.
function respostaEstil(r) {
  if (r.kits) { kits = r.kits; kitActual = r.kit; pintaKits(); }
  if (r.versio_estil) versioEstil = r.versio_estil;
  if (r.biblioteca_lletres) bibliotecaLletres = r.biblioteca_lletres;
  if (r.fonts_kit) carregaFontsKit(r.fonts_kit);
  if (r.estils_titol) estilsTitol = r.estils_titol;
  if (r.trams) aplicaTrams(r);
  // Si mentrestant hi ha hagut més canvis, que no es perdin a la vista.
  aplicaEstilSubtitols({ ...r.estil_subtitols, ...pendents.subtitols });
  if (r.estil_titol) aplicaEstilTitol({ ...r.estil_titol, ...pendents.titol });
  aplicaMarca(r);
  aplicaBroll(r);
  aplicaSo(r);
  pintaPanellEstil();
  pintaPanellTitol();
}

function aplicaSo(r) {
  if (r.estil_so) { estilSo = { ...r.estil_so, ...pendents.so }; pintaSo(); }
  if (r.sons_propis) $("#s-carpeta").textContent = r.sons_propis.replace(/^\/Users\/[^/]+/, "~");
}

function aplicaBroll(r) {
  if (r.estil_broll) estilBroll = { ...r.estil_broll, ...pendents.broll };
  if (r.estils_broll) estilsBroll = r.estils_broll;
  if (r.mostra_broll) mostraBroll = r.mostra_broll;
  pintaResumBroll();
  pintaPanellBroll();
  if (mostraBrollDespres && !Object.keys(pendents.broll).length) mostraBrollViu();
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
  pintaResumTitol();
  const camp = $("#text-titol");
  const t = titolEsborrany ? { ...estat.titol, ...titolEsborrany } : estat.titol;
  if (document.activeElement !== camp) camp.value = t?.text || "";
  const durada = t?.durada ?? estilTitol?.durada ?? 3;
  $("#durada-titol").value = durada;
  $("#durada-titol-text").textContent = fmtSegons(durada);
  $("#camp-durada-titol").hidden = !t;
}

// El text i la durada: a la vista, de seguida; a l'estat (i a desfer), quan s'acaba d'escriure o de
// moure la barra. Es desen sempre junts, perquè un no trepitgi l'altre si es canvien seguits.
let temporitzadorTitol = null;
let titolEsborrany = null;  // {text, durada} encara per desar

function canviaTitolDelVideo(canvi, espera) {
  titolEsborrany = { text: estat.titol?.text ?? "", durada: estat.titol?.durada ?? null, ...titolEsborrany, ...canvi };
  const { text, durada } = titolEsborrany;
  titolMuntatge = text.trim()
    ? { text, inici: 0, final: Math.min(duradaFinal || 99, durada ?? estilTitol?.durada ?? 3) } : null;
  previaBruta = true;
  $("#camp-durada-titol").hidden = !text.trim();
  clearTimeout(temporitzadorTitol);
  temporitzadorTitol = setTimeout(desaTitolDelVideo, espera);
}

function desaTitolDelVideo() {
  clearTimeout(temporitzadorTitol);
  if (!titolEsborrany) return;
  const { text, durada } = titolEsborrany;
  titolEsborrany = null;
  canvia((e) => { e.titol = text.trim() ? { text, durada } : null; });
}

function canviaTextTitol() {
  canviaTitolDelVideo({ text: $("#text-titol").value }, 700);
}

function canviaDuradaTitol(durada) {
  $("#durada-titol-text").textContent = fmtSegons(durada);
  canviaTitolDelVideo({ durada }, 400);
}

function canviaTitol(canvis, mostra = false) {
  aplicaEstilTitol({ ...estilTitol, ...canvis });
  pintaPanellTitol();
  apunta("titol", canvis);
  if (mostra) mostraTitol();
}

// Fa sonar el títol des del principi perquè es vegi com entra.
function mostraTitol() {
  if (vista !== "directe" || sona() || !titolMuntatge) return;
  vesA(titolMuntatge.inici);
  reprodueix();
  R.aturaA = Math.min(duradaFinal, titolMuntatge.final + 0.2);
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
  const primera = (estat?.titol?.text || "").split("\n")[0].replaceAll("*", "").trim();
  $("#nom-estil-titol").textContent = primera ? `«${primera}» · ${predefinitTitol()?.nom ?? "Personalitzat"}` : "Sense títol";
  pintaMostraTitol($("#mostra-titol"), { ...estilTitol, mida: 0.3, clau_mida: 1 }, "Aa", 1080);
}

function pintaPanellTitol() {
  const e = estilTitol;
  if (!e || $("#panell-titol").hidden) return;
  const actual = predefinitTitol();
  const cont = $("#estils-titol");
  cont.textContent = "";
  for (const p of estilsTitol) {
    const valors = ambMarca("titol", p.valors);
    const mostra = botoEstil(cont, p, p === actual, () => canviaTitol(valors, true));
    pintaMostraTitol(mostra, { ...e, ...valors, mida: Math.min(0.11, (valors.mida || e.mida) * 1.5) },
      "El meu\n*títol*", 675);
  }
  $("#t-animacio").value = e.animacio;
  marcaSegmentat("t-fons", e.fons || "cap");
  marcaSegmentat("t-alineacio", e.alineacio || "centre");
  marcaSegmentat("t-corba-linies", e.corba_linies || "primera");
  $("#t-corba").value = e.corba ?? 0;
  $("#t-corba-linies").hidden = !e.corba;
  ompleLletres($("#t-font"), e.font, { laDelsSubtitols: true });
  const pes = $("#t-pes");
  if (![...pes.options].some((o) => +o.value === +e.pes)) {
    const o = document.createElement("option"); o.value = e.pes; o.textContent = `Gruix ${e.pes}`; pes.append(o);
  }
  pes.value = String(e.pes);
  $("#t-majuscules").setAttribute("aria-checked", String(!!e.majuscules));
  ompleLletres($("#t-clau-font"), e.clau_font, { buit: "La mateixa" });
  $("#t-clau-cursiva").setAttribute("aria-checked", String(!!e.clau_cursiva));
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
  for (const [id, clau] of [["t-fons", "fons"], ["t-alineacio", "alineacio"], ["t-corba-linies", "corba_linies"]]) {
    for (const b of $$(`#${id} button`)) b.addEventListener("click", () => canviaTitol({ [clau]: b.dataset.valor }, true));
  }
  $("#t-font").addEventListener("change", (e) => {
    const v = e.target.value;
    if (v.startsWith("bib:")) baixaLletra(v.slice(4), "titol");
    else canviaTitol({ font: v || null });
  });
  $("#t-pes").addEventListener("change", (e) => canviaTitol({ pes: +e.target.value }));
  $("#t-clau-font").addEventListener("change", (e) => {
    const v = e.target.value;
    if (v.startsWith("bib:")) baixaLletra(v.slice(4), "titol", "clau_font");
    else canviaTitol({ clau_font: v || null });
  });
  for (const [id, clau, perDefecte] of [["t-majuscules", "majuscules", false], ["t-ombra", "ombra", true],
    ["t-clau-cursiva", "clau_cursiva", false],
    ["t-amaga", "amaga_subtitols", false]]) {
    $(`#${id}`).addEventListener("click", () => canviaTitol({ [clau]: !(estilTitol[clau] ?? perDefecte) }));
  }
  for (const [id, clau] of [["t-mida", "mida"], ["t-clau-mida", "clau_mida"], ["t-espaiat", "espaiat"],
    ["t-interlineat", "interlineat"], ["t-posicio", "posicio_y"], ["t-gruix", "gruix_contorn"], ["t-corba", "corba"]]) {
    $(`#${id}`).addEventListener("input", (e) => canviaTitol({ [clau]: +e.target.value }));
  }
  for (const [id, clau] of [["t-color", "color"], ["t-clau-color", "clau_color"], ["t-contorn", "contorn"],
    ["t-fons-color", "fons_color"]]) {
    $(`#${id}`).addEventListener("input", (e) => canviaTitol({ [clau]: e.target.value.toUpperCase() }));
  }
  $("#restableix-titol").addEventListener("click", () => restableix("titol", "El títol ha tornat a l'estil de tallat."));
}

// --- Pestanyes de la columna de l'esquerra ------------------------------------------------------
// Per tasques: Edita (què queda al vídeo), Subtítols, Gràfics (títol i b-roll), So i Vídeos (els
// exportats). Es recorda la darrera. A «Edita», un punt avisa si hi ha coses per decidir.

function triaPestanya(nom, { focus = false } = {}) {
  if (nom === "estil") nom = "subtitols";  // la pestanya d'abans
  if (!$(`#pestanya-${nom}`)) nom = "edita";
  for (const tab of $$("#pestanyes [role=tab]")) {
    const triada = tab.dataset.pestanya === nom;
    tab.setAttribute("aria-selected", String(triada));
    tab.tabIndex = triada ? 0 : -1;
    $(`#pestanya-${tab.dataset.pestanya}`).hidden = !triada;
    if (triada && focus) tab.focus();
  }
  desa("tallat.pestanya", nom);
  const subtitols = nom === "subtitols";
  if (subtitols !== editantEstil) {
    editantEstil = subtitols;
    previaBruta = true;
    previaTemps = NaN;
    if (subtitols) {
      if (vista !== "directe") canviaVista("directe");
      pintaPanellEstil();
    }
  }
  if (nom === "so" && typeof pintaSo === "function") pintaSo();
  if (nom === "grafics" && estat) pintaPla();
}

function actualitzaPestanyes() {
  const perDecidir = instruccions.some((i) => i.estat === "pendent") || Object.keys(estat?.propostes || {}).length > 0;
  $("#punt-edita").hidden = !perDecidir;

}

function instalaPestanyes() {
  const tabs = $$("#pestanyes [role=tab]");
  for (const tab of tabs) tab.addEventListener("click", () => triaPestanya(tab.dataset.pestanya));
  $("#pestanyes").addEventListener("keydown", (e) => {  // fletxes, com qualsevol grup de pestanyes
    const i = tabs.findIndex((t) => t.getAttribute("aria-selected") === "true");
    const j = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
    if (j == null) return;
    e.preventDefault();
    triaPestanya(tabs[(j + tabs.length) % tabs.length].dataset.pestanya, { focus: true });
  });
  triaPestanya(llegeix("tallat.pestanya", "edita"));
  // Els grups plegables dels panells d'estil recorden si estaven oberts.
  const oberts = new Set(llegeix("tallat.grups-oberts", []));
  for (const d of $$("details.grup-estil")) {
    d.open = oberts.has(d.id);
    d.addEventListener("toggle", () => {
      if (d.open) oberts.add(d.id); else oberts.delete(d.id);
      desa("tallat.grups-oberts", [...oberts]);
    });
  }
}

// Les files que es poden clicar (reels, instruccions, propostes, vídeos…) també es poden fer servir
// amb el teclat: es poden enfocar amb ⇥ i ↩ o l'espai fan el mateix que el clic.
function fesClicable(item) {
  item.tabIndex = 0;
}
document.addEventListener("keydown", (e) => {
  if (!e.target.classList?.contains("item") || !["Enter", " "].includes(e.key)) return;
  e.preventDefault();
  e.target.click();
});

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
  $("#sep-treu-kit").hidden = !!actual?.per_defecte;
  $("#nom-kit-panell").textContent = actual?.nom || "";
  $("#nom-kit-titol").textContent = actual?.nom || "";
  $("#nom-kit-broll").textContent = actual?.nom || "";
  $("#nom-kit-marca").textContent = actual?.nom || "";
}

function respostaKit(r, missatge) {
  estat = r.estat;
  respostaEstil(r);  // l'estil del kit, la lletra, la llista de kits i el muntatge
  refresca(true);
  if (missatge) avis(missatge, 4000);
}

async function accioKit(ruta, dades, missatge) {
  try {
    await desaEstils();  // el que hi hagi pendent va al kit d'abans
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
    await desaEstils();
    const json = await resposta(await fetch(`/api/kit/importa?nom=${encodeURIComponent(fitxer.name)}`,
      { method: "POST", headers: capcaleres({ "Content-Type": "application/zip" }), body: fitxer }));
    respostaKit(json, "Kit importat. Aquest vídeo ja el fa servir.");
  } catch (e) { avis(e.message, 6000); }
}

function instalaMenuKit() {
  const boto = $("#menu-kit-boto");
  const menu = $("#menu-kit");
  const items = () => [...menu.querySelectorAll("button")].filter((b) => !b.hidden);
  const tanca = ({ focus = false } = {}) => {
    menu.hidden = true;
    boto.setAttribute("aria-expanded", "false");
    if (focus) boto.focus();
  };
  boto.addEventListener("click", (e) => {
    e.stopPropagation();
    const obrir = menu.hidden;
    menu.hidden = !obrir;
    boto.setAttribute("aria-expanded", String(obrir));
    if (obrir) items()[0]?.focus();
  });
  document.addEventListener("click", (e) => { if (!menu.hidden && !menu.contains(e.target)) tanca(); });
  menu.addEventListener("keydown", (e) => {
    const llista = items();
    const i = llista.indexOf(document.activeElement);
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); tanca({ focus: true }); }
    else if (e.key === "ArrowDown") { e.preventDefault(); llista[(i + 1) % llista.length]?.focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); llista[(i - 1 + llista.length) % llista.length]?.focus(); }
  });
  // Després de fer una acció, el menú es tanca (llevat del primer clic de «Treu-lo», que demana confirmació).
  for (const b of menu.querySelectorAll("button")) {
    b.addEventListener("click", () => setTimeout(() => { if (!b.classList.contains("confirma")) tanca(); }));
  }
}

function instalaKits() {
  instalaMenuKit();
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
async function baixaLletra(id, seccio = "subtitols", clau = "font") {
  const nom = bibliotecaLletres.lletres.find((l) => l.id === id)?.nom || id;
  avis(`Baixant la lletra «${nom}»…`, 20000);
  try {
    await desaEstils();
    respostaEstil(await api("/api/marca/lletra", { id, seccio, clau, kit: kitActual }));
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
    await desaEstils();
    const json = await resposta(await fetch(`/api/marca/font?nom=${encodeURIComponent(fitxer.name)}`,
      { method: "POST", headers: capcaleres(), body: fitxer }));
    respostaEstil(json);
    avis("Font afegida. Ja la veus als subtítols.");
  } catch (e) { avis(e.message, 6000); }
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
    for (const host of ["#ts-host", "#tg-host", "#tt-host"]) $(host).style.transform = `scale(${capa.clientWidth / 1080})`;
  }).observe(capa);
  if (!window.gsap) registre("sense-gsap", {});  // sense internet: subtítols sense animacions
  $("#grup-trets").addEventListener("toggle", pintaPla);  // les miniatures, quan es veuen

  $("#mes-estils").addEventListener("click", () => { estilsMostrats = !$("#estils").classList.contains("tots"); pintaPanellEstil(); });
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
  interruptor("e-clau-cursiva", "clau_cursiva");
  $("#e-clau-font").addEventListener("change", (e) => {
    const v = e.target.value;
    if (v.startsWith("bib:")) baixaLletra(v.slice(4), "subtitols", "clau_font");
    else canviaEstil({ clau_font: v || null });
  });
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
  $("#restableix-estil").addEventListener("click", () => restableix("subtitols", "Has tornat a l'estil de tallat."));
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

// --- Vistes i esborranys --------------------------------------------------------------------

function canviaVista(nova) {
  if (nova === vista) return;
  atura();
  vista = nova;
  for (const b of $$("#vista button")) b.setAttribute("aria-checked", String(b.dataset.vista === vista));
  const directe = vista === "directe";
  R.v.classList.toggle("amagat", !directe);
  vE.classList.toggle("amagat", directe);
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
  $("#compte-videos").textContent = exports.length || "";
  const cont = $("#versions");
  cont.textContent = "";
  if (!exports.length) { cont.innerHTML = '<p class="buit">Encara no n\'has exportat cap. Fes-ne un amb «Esborrany» o «Final…», a dalt.</p>'; return; }
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
    fesClicable(item);
    cont.append(item);
  }
  const darrer = exports.find((x) => x.qualitat === "esborrany");
  $('#vista [data-vista="esborrany"]').disabled = !darrer && !esborrany;
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
      pintaCarpeta(r);
      if (feina.qualitat === "editors") {
        mostraFet(feina, "Projecte per a altres editors a punt (hi ha un LLEGEIX-ME amb els passos)");
        mostraAlFinder(feina);
      } else if (feina.qualitat === "esborrany") {
        avis("L'esborrany és a punt. Mira'l i digues a Claude què vols canviar (amb el segon, que veus sota el vídeo).", 6000);
        carregaVersio(feina.fitxer);
      } else {
        mostraFet(feina, `Vídeo en ${QUALITATS[feina.qualitat]} a punt`);
      }
    } else if (feina?.estat === "error") {
      avis("El render ha fallat: " + feina.error, 6000);
    }
  } catch (e) {
    avis("He perdut el contacte amb tallat. Torna a obrir la pàgina de revisió.", 6000);
    seguimentFeina(null);
  }
}

// Quan s'acaba un export, l'avís es queda (fins que es tanca): què s'ha fet, on és i un botó per veure'l.
let darrerFet = null;
function mostraFet(feina, text) {
  darrerFet = feina;
  $("#fet-text").textContent = `${text}: ${feina.copia || feina.fitxer}`;
  $("#fet-export").hidden = false;
}

function mostraAlFinder(feina) {
  return api("/api/mostra", feina.copia ? { copia: feina.copia } : { nom: feina.fitxer }).catch((e) => avis(e.message));
}

function pintaCarpeta(r) {
  if (!r?.carpeta_exports) return;
  $("#final-carpeta").textContent = r.carpeta_exports;
  $("#carpeta-projecte").hidden = !r.carpeta_propia;
  $("#final-carpeta").title = r.carpeta_propia ? "I també a la carpeta del projecte (pestanya Vídeos)" : "";
}

async function triaCarpeta(accio) {
  try {
    const r = await api("/api/exports/carpeta", { accio });
    pintaCarpeta(r);
  } catch (e) { avis(e.message); }
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
  $("#fet-export").hidden = true;
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
  $("#seccio-reels").hidden = !reels.length;  // si encara no n'hi ha, no ocupa lloc
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
    fesClicable(item);
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
// On va cada b-roll (pantalla sencera, targeta, pantalla partida o carrusel) ho calcula el servidor
// (motor/targetes.py), i és el mateix que fa servir el vídeo final. Aquí només es dibuixa.

const brollsVius = new Map();  // id del b-roll → la seva targeta a la pantalla

function estilTargeta(el, c) {
  const sig = JSON.stringify(c);
  if (el.dataset.sig === sig) return;
  el.dataset.sig = sig;
  Object.assign(el.style, {
    left: `${c.x}px`, top: `${c.y}px`, width: `${c.w}px`, height: `${c.h}px`, borderRadius: `${c.radi}px`,
    borderWidth: `${c.vora}px`, borderColor: c.vora_color, background: c.vora ? c.vora_color : "#000",
    boxShadow: c.ombra ? "0 14px 48px rgba(0, 0, 0, 0.45)" : "none",
  });
}

function targetaBroll(c, contingut) {
  const el = document.createElement("div");
  el.className = "targeta-broll";
  el.append(contingut);
  estilTargeta(el, c);
  return el;
}

// L'animació d'entrada, amb les mateixes fórmules que l'export (motor/targetes.py):
// si en canvies una, canvia també l'altra.
function animacioBroll(b, m) {
  const p = Math.min(1, Math.max(0, (m - b.inici) / (b.entrada || 0.4)));
  const cubica = 1 - (1 - p) ** 3;
  let escala = 1, dx = 0, dy = 0, opacitat = 1;
  if (b.animacio === "pop") {
    const q = p - 1;
    escala = 0.8 + 0.2 * (1 + 2.70158 * q ** 3 + 1.70158 * q ** 2);
    opacitat = Math.min(1, p / 0.4);
  } else if (b.animacio === "puja") { dy = 96 * (1 - cubica); opacitat = p; }
  else if (b.animacio === "llisca") { dx = 380 * b.direccio * (1 - cubica); opacitat = p; }
  else if (b.animacio === "fos") opacitat = p;
  return { transform: `translate(${dx}px, ${dy}px) rotate(${b.caixa.rotacio}deg) scale(${escala})`, opacity: String(opacitat) };
}

function pintaBroll() {
  const m = tempsMuntatge();
  const actius = vista === "directe" ? brollsMuntatge.filter((b) => m >= b.inici && m < (b.fins ?? b.inici + b.durada)) : [];
  const partida = actius.some((b) => b.partida);
  for (const v of $$(".pantalla > video")) v.classList.toggle("partida", partida && v === R.v);
  $("#capa-broll").classList.toggle("partida", partida);
  const ids = new Set(actius.map((b) => b.id));
  for (const [id, el] of brollsVius) {
    if (!ids.has(id)) { el.firstChild.pause(); el.remove(); brollsVius.delete(id); }
  }
  for (const b of actius) {
    let el = brollsVius.get(b.id);
    if (!el) {
      const v = document.createElement("video");
      Object.assign(v, { muted: true, playsInline: true, preload: "auto", src: b.url });
      el = targetaBroll(b.caixa, v);
      $("#br-host").append(el);
      brollsVius.set(b.id, el);
    }
    estilTargeta(el, b.caixa);
    el.style.zIndex = String(brollsMuntatge.indexOf(b));
    Object.assign(el.style, animacioBroll(b, m));
    const v = el.firstChild;
    if (!v.src.endsWith(b.url)) v.src = b.url;
    // Al carrusel, quan el clip s'acaba, la targeta es queda quieta a l'últim fotograma.
    const quiet = m - b.inici >= b.durada - 0.05;
    const desitjat = Math.min(m - b.inici, Math.max(0, b.durada - 0.05));
    if (v.readyState >= 1 && Math.abs(v.currentTime - desitjat) > 0.15) v.currentTime = desitjat;
    if (R.reproduint && !quiet && v.paused) v.play().catch(() => {});
    if ((!R.reproduint || quiet) && !v.paused) v.pause();
  }
}

// Una miniatura quieta: la pantalla, la persona i on van les targetes.
function miniBroll(cont, mostra) {
  if (!cont || !mostra) return;
  const mini = document.createElement("div");
  mini.className = "mini-broll";
  mini.classList.toggle("partida", mostra.some((b) => b.partida));
  for (const b of mostra) {
    const el = targetaBroll(b.caixa, document.createElement("i"));
    el.style.transform = `rotate(${b.caixa.rotacio}deg)`;
    mini.append(el);
  }
  cont.textContent = "";
  cont.append(mini);
  mini.style.transform = `scale(${cont.clientHeight / 1920}) translate(-540px, -960px)`;
}

// --- L'estil del b-roll (panell) ----------------------------------------------------------------

let estilBroll = null;   // la secció «broll» del kit
let estilsBroll = [];    // les maneres predefinides, cada una amb la seva miniatura
let mostraBroll = [];    // la miniatura de l'estil d'ara
let editantBroll = false;
let mostraBrollDespres = false;  // fer sonar el primer b-roll quan arribi la disposició nova


function pintaResumBroll() {
  if (!estilBroll) return;
  const n = brollsMuntatge.length;
  $("#nom-estil-broll").textContent = `${predefinitBroll()?.nom ?? "Personalitzat"}`
    + (n ? ` · ${n === 1 ? "1 en aquest vídeo" : `${n} en aquest vídeo`}` : "");
  miniBroll($("#mostra-broll"), mostraBroll);
}

function pintaPanellBroll() {
  const e = estilBroll;
  if (!e || $("#panell-broll").hidden) return;
  const actual = predefinitBroll();
  const cont = $("#estils-broll");
  cont.textContent = "";
  for (const p of estilsBroll) {
    miniBroll(botoEstil(cont, p, p === actual, () => canviaBroll(ambMarca("broll", p.valors), true)), p.mostra);
  }
  const disposicio = e.disposicio || "pantalla";
  const ambForma = disposicio === "targeta" || disposicio === "carrusel";
  $("#camp-b-mida").hidden = disposicio !== "targeta";
  $("#camp-b-posicio").hidden = !ambForma;
  $("#b-posicio-x").hidden = $("#b-posicio-x").nextElementSibling.hidden = disposicio !== "targeta";
  $("#grup-b-forma").hidden = !ambForma;
  $("#b-animacio").value = e.animacio || "cap";
  $("#b-mida").value = e.mida;
  $("#b-posicio-y").value = e.posicio_y;
  $("#b-posicio-x").value = e.posicio_x;
  marcaSegmentat("b-proporcio", e.proporcio || "4:5");
  $("#b-radi").value = e.radi;
  $("#b-vora").value = e.vora;
  $("#b-rotacio").value = e.rotacio ?? 0;
  $("#b-ombra").setAttribute("aria-checked", String(e.ombra !== false));
  $("#b-vora-kit").setAttribute("aria-checked", String(!e.vora_color));
  const accent = estilSub?.clau_color || estilSub?.color_actiu || "#FFFFFF";
  $("#b-vora-color").value = (e.vora_color || accent).toLowerCase();
  $("#camp-b-vora-color").hidden = !(e.vora > 0);
}

function canviaBroll(canvis, mostra = false) {
  estilBroll = { ...estilBroll, ...canvis };
  pintaPanellBroll();
  if (mostra) mostraBrollDespres = true;
  apunta("broll", canvis);
}

// Fa sonar el primer b-roll del vídeo perquè es vegi com entra.
function mostraBrollViu() {
  mostraBrollDespres = false;
  const b = brollsMuntatge[0];
  if (vista !== "directe" || sona() || !b) return;
  vesA(Math.max(0, b.inici - 0.3));
  reprodueix();
  R.aturaA = Math.min(duradaFinal, (b.fins ?? b.inici + b.durada) + 0.2);
}

function obreBroll() {
  editantBroll = true;
  if (vista !== "directe") canviaVista("directe");
  $(".barra").classList.add("editant-estil");
  $("#panell-broll").hidden = false;
  $(".barra").scrollTop = 0;
  pintaPanellBroll();
  if (!brollsMuntatge.length) avis("Aquest vídeo encara no té b-roll: les miniatures ensenyen com quedarà.", 4000);
  $("#tanca-broll").focus();
}

function tancaBroll() {
  editantBroll = false;
  $(".barra").classList.remove("editant-estil");
  $("#panell-broll").hidden = true;
  $("#obre-estil-broll").focus();
}

function instalaBroll() {
  new ResizeObserver(() => {
    $("#br-host").style.transform = `scale(${$("#capa-broll").clientWidth / 1080})`;
  }).observe($("#capa-broll"));
  $("#obre-estil-broll").addEventListener("click", obreBroll);
  $("#tanca-broll").addEventListener("click", tancaBroll);
  $("#b-animacio").addEventListener("change", (e) => canviaBroll({ animacio: e.target.value }, true));
  for (const b of $$("#b-proporcio button")) b.addEventListener("click", () => canviaBroll({ proporcio: b.dataset.valor }, true));
  for (const [id, clau] of [["b-mida", "mida"], ["b-posicio-y", "posicio_y"], ["b-posicio-x", "posicio_x"],
    ["b-radi", "radi"], ["b-vora", "vora"], ["b-rotacio", "rotacio"]]) {
    $(`#${id}`).addEventListener("input", (e) => canviaBroll({ [clau]: +e.target.value }));
  }
  $("#b-ombra").addEventListener("click", () => canviaBroll({ ombra: estilBroll.ombra === false }));
  $("#b-vora-kit").addEventListener("click", () =>
    canviaBroll({ vora_color: estilBroll.vora_color ? null : $("#b-vora-color").value.toUpperCase() }));
  $("#b-vora-color").addEventListener("input", (e) => canviaBroll({ vora_color: e.target.value.toUpperCase() }));
  $("#restableix-broll").addEventListener("click", () => restableix("broll", "El b-roll ha tornat a l'estil de tallat."));
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

// --- El pla de gràfics ---------------------------------------------------------------------------
// Claude els proposa frase a frase des del xat (`tallat.py grafics proposa`) i aquí es revisen:
// Mantén (t'agrada: Claude no el tocarà), Canvia (amb una nota per a Claude) o Treu. Les decisions
// són a l'estat (es desfan com la resta) i es dibuixen amb pagina/grafics.js, com al vídeo final.

let graficsMuntatge = [];  // els que surten al vídeo, en temps del muntatge (els calcula el servidor)
let dibuixosGrafics = {};  // com es dibuixa cada gràfic del pla, també els que no surten (per a les miniatures)
let paletaGrafics = null;  // els colors i les lletres de la marca
const OP_GRAFICS = { imatges: "/imatges-grafics/" };  // on són les captures i les fotos dels gràfics
let previaGrafics = null;
let notaOberta = null;     // l'id del gràfic que té la nota oberta
const targetesGrafic = new Map();  // id → {el, sig}: només es refà la que canvia

const ESTATS_GRAFIC = { mantingut: "Mantingut", canvia: "Per canviar" };

const graficDe = (id) => (estat?.grafics || []).find((g) => g.id === id);
// Els trets desapareixen de seguida, sense esperar el servidor.
const graficsVisibles = () => graficsMuntatge.filter((g) => graficDe(g.id)?.estat !== "tret");

// Per a la miniatura: el gràfic sencer, ja entrat (també els trets i els que ja no surten al vídeo).
function perDibuixar(g) {
  const d = dibuixosGrafics[g.id];
  return d && { ...d, inici: 0, final: 1e5, punts: (d.punts || []).map((p) => ({ ...p, t: 0 })) };
}

function textGrafic(g) {
  const text = (g.text || (g.tipus === "crida" ? estilMarca?.crida || "La crida de la teva marca" : "")).replaceAll("*", "");
  if (g.tipus === "llista") return [text, ...g.punts.map((p) => `· ${p.text}`)].filter(Boolean).join("  ");
  if (g.tipus === "xat") return [text, ...g.punts.map((p) => `${p.costat === "enviat" ? "→" : "←"} ${p.text}`)].filter(Boolean).join("  ");
  if (g.tipus === "notificacio") return `${g.de ? `${g.de}: ` : ""}«${text}»`;
  if (g.tipus === "numero") return `${g.xifra}${text ? ` · ${text}` : ""}`;
  if (g.tipus === "web") return text ? `Web: ${text}` : "Captura d'una web";
  if (g.tipus === "ventall") {
    const n = g.punts.length;
    return [text, n ? `${n} ${n === 1 ? "foto" : "fotos"}` : "Encara sense fotos"].filter(Boolean).join(" · ");
  }
  return `«${text}»`;
}

function targetaGrafic(g) {
  const s = graficsMuntatge.find((x) => x.id === g.id);
  const falta = !!dibuixosGrafics[g.id]?.falta;  // la web o el ventall sense imatges: no surt fins que n'hi hagi
  const el = document.createElement("div");
  el.className = `grafic ${g.estat}${s || g.estat === "tret" || falta ? "" : " fora"}`;
  el.innerHTML = `<button class="mini-grafic"><span class="mg-host"></span></button>
    <div class="grafic-cos">
      <div class="grafic-cap"><strong></strong><span class="temps-petit"></span><span class="grafic-estat"></span></div>
      <p class="grafic-text"></p>
      <div class="grafic-imatges" hidden></div>
      <p class="grafic-nota" hidden></p>
      <p class="grafic-motiu" hidden></p>
      <div class="segmentat ample decisio" role="group" aria-label="Què en fem">
        <button data-estat="mantingut">Mantén</button><button data-estat="canvia">Canvia</button><button data-estat="tret">Treu</button>
      </div>
      <button class="enllac torna" hidden>Torna'l a posar</button>
      <form class="nota-grafic" hidden>
        <textarea class="camp-text" rows="2" maxlength="600" aria-label="Què hi vols diferent"
                  placeholder="Què hi vols diferent? Ho llegirà Claude."></textarea>
        <div class="nota-accions"><button type="submit" class="boto principal">Desa la nota</button>
          <button type="button" class="enllac cancel">Cancel·la</button></div>
      </form>
    </div>`;
  el.querySelector("strong").textContent = dibuixosGrafics[g.id]?.nom || g.tipus;
  el.querySelector(".temps-petit").textContent = s ? fmtSegons(s.inici) : g.estat === "tret" ? ""
    : falta ? (g.tipus === "web" ? "falta la captura" : "falta alguna foto") : "ja no surt al vídeo";
  if (g.tipus === "web" || g.tipus === "ventall") pintaImatgesGrafic(el.querySelector(".grafic-imatges"), g);
  el.querySelector(".grafic-estat").textContent = ESTATS_GRAFIC[g.estat] || "";
  el.querySelector(".grafic-text").textContent = textGrafic(g);
  if (g.nota) Object.assign(el.querySelector(".grafic-nota"), { hidden: false, textContent: `Nota: ${g.nota}` });
  if (g.motiu) Object.assign(el.querySelector(".grafic-motiu"), { hidden: false, textContent: g.motiu });
  const mini = el.querySelector(".mini-grafic");
  mini.setAttribute("aria-label", s ? `Mira'l al vídeo (${fmtSegons(s.inici)})` : "Miniatura");
  mini.disabled = !s;
  for (const b of el.querySelectorAll(".decisio button")) b.setAttribute("aria-pressed", String(b.dataset.estat === g.estat));
  el.querySelector(".decisio").hidden = g.estat === "tret";
  el.querySelector(".torna").hidden = g.estat !== "tret";
  const form = el.querySelector(".nota-grafic");
  form.hidden = notaOberta !== g.id;
  form.querySelector("textarea").value = g.nota || "";

  el.addEventListener("click", (e) => {
    if (e.target.closest(".puja-imatge")) return triaImatgesGrafic(g);
    const treu = e.target.closest(".treu-foto");
    if (treu) return canviaGrafic(g.id, { punts: g.punts.filter((_, k) => k !== Number(treu.dataset.k)) });
    const boto = e.target.closest(".decisio button");
    if (boto) return decideixGrafic(g.id, boto.dataset.estat);
    if (e.target.closest(".torna")) return decideixGrafic(g.id, "proposat");
    if (e.target.closest(".cancel")) { notaOberta = null; form.hidden = true; return; }
    if (e.target.closest(".mini-grafic, .grafic-text") && s) vesA(s.inici + Math.min(0.8, (s.final - s.inici) / 2));
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    desaNotaGrafic(g.id, form.querySelector("textarea").value);
  });
  form.querySelector("textarea").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); form.requestSubmit(); }
    if (e.key === "Escape") { notaOberta = null; form.hidden = true; }
  });
  return el;
}

// Les imatges de la web (la captura) i del ventall (les fotos, que es poden treure una a una).
function pintaImatgesGrafic(cont, g) {
  cont.hidden = false;
  const fotos = g.tipus === "web" ? (g.imatge ? [g.imatge] : []) : g.punts.map((p) => p.imatge);
  fotos.forEach((nom, k) => {
    const foto = document.createElement("span");
    foto.className = "foto-grafic";
    const img = document.createElement("img");
    Object.assign(img, { src: OP_GRAFICS.imatges + encodeURIComponent(nom), alt: "" });
    foto.append(img);
    if (g.tipus === "ventall") {
      const treu = document.createElement("button");
      Object.assign(treu, { className: "treu-foto", title: "Treu aquesta foto" });
      treu.dataset.k = k;
      treu.setAttribute("aria-label", "Treu aquesta foto");
      treu.innerHTML = '<svg viewBox="0 0 20 20"><path d="m6 6 8 8m0-8-8 8"/></svg>';
      foto.append(treu);
    }
    cont.append(foto);
  });
  if (g.tipus === "ventall" && fotos.length >= 6) return;
  const puja = document.createElement("button");
  puja.className = `boto petit puja-imatge${fotos.length ? "" : " principal"}`;
  puja.textContent = g.tipus === "web" ? (fotos.length ? "Canvia la captura" : "Puja la captura")
    : fotos.length ? "Afegeix fotos" : "Puja les fotos";
  cont.append(puja);
}

function triaImatgesGrafic(g) {
  const tria = document.createElement("input");
  Object.assign(tria, { type: "file", accept: "image/png,image/jpeg,image/webp,image/gif", multiple: g.tipus === "ventall" });
  tria.addEventListener("change", () => pujaImatgesGrafic(g.id, [...tria.files]));
  tria.click();
}

async function pujaImatgesGrafic(id, fitxers) {
  if (!fitxers.length) return;
  avis(fitxers.length > 1 ? `Pujant ${fitxers.length} imatges…` : "Pujant la imatge…", 20000);
  try {
    await cua;
    let json = null;
    for (const fitxer of fitxers) {
      json = await resposta(await fetch(
        `/api/grafics/imatge?grafic=${encodeURIComponent(id)}&nom=${encodeURIComponent(fitxer.name)}`,
        { method: "POST", headers: capcaleres(), body: fitxer }));
    }
    estat = json.estat;
    aplicaTrams(json);
    refresca(true);
    avis("Fet. Mira-ho al vídeo.");
  } catch (e) { avis(e.message, 6000); }
}

// La miniatura: el gràfic dibuixat petit, amb el mateix codi que el vídeo. Torna la seva línia de
// temps, per esborrar-la quan es refà la targeta.
function pintaMiniGrafic(el, g) {
  const host = el.querySelector(".mg-host");
  const dibuix = perDibuixar(g);
  if (!window.TallatGrafics || !paletaGrafics || !dibuix) return null;
  const arrel = document.createElement("div");
  host.replaceChildren(arrel);
  // Amb bloc de color: el fons de la marca i, a baix, la targeta on va el vídeo.
  const mini = el.querySelector(".mini-grafic");
  mini.style.background = dibuix.bloc ? paletaGrafics[dibuix.bloc] || "" : "";
  if (dibuix.bloc) {
    const targeta = document.createElement("div");
    targeta.className = "mg-targeta";
    Object.assign(targeta.style, { left: `${BLOC.x}px`, top: `${BLOC.y}px`, width: `${BLOC.w}px`, height: `${BLOC.h}px` });
    host.prepend(targeta);
  }
  const tl = TallatGrafics.construeix(arrel, [dibuix], paletaGrafics, OP_GRAFICS).seek(50, false);
  host.style.transform = `scale(${el.querySelector(".mini-grafic").clientWidth / 1080})`;
  return tl;
}

function ompleGrafics(cont, llista) {
  const ids = new Set(llista.map((g) => g.id));
  for (const el of [...cont.children]) if (!ids.has(el.dataset.id)) el.remove();
  for (const g of llista) {
    const s = graficsMuntatge.find((x) => x.id === g.id);
    const sig = JSON.stringify([g, s, dibuixosGrafics[g.id], paletaGrafics, notaOberta === g.id,
      g.tipus === "crida" && estilMarca?.crida]);
    let fet = targetesGrafic.get(g.id);
    if (!fet || fet.sig !== sig) {
      if (fet && fet.el.querySelector("textarea") === document.activeElement) continue;  // s'hi escriu una nota
      const el = targetaGrafic(g);
      el.dataset.id = g.id;
      fet?.tl?.kill?.();  // l'animació de la miniatura d'abans
      fet?.el.replaceWith(el);
      fet = { el, sig };
      targetesGrafic.set(g.id, fet);
    }
    cont.append(fet.el);  // en ordre (si ja hi és, només es mou)
    if (!fet.pintada && fet.el.isConnected && fet.el.querySelector(".mini-grafic").clientWidth) {
      fet.tl = pintaMiniGrafic(fet.el, g);
      fet.pintada = true;
    }
  }
}

function pintaPla() {
  if (!estat) return;
  const tots = estat.grafics || [];
  const vius = tots.filter((g) => g.estat !== "tret");
  const trets = tots.filter((g) => g.estat === "tret");
  const perRevisar = vius.filter((g) => g.estat === "proposat").length;
  const notes = vius.filter((g) => g.estat === "canvia").length;
  $("#compte-grafics").textContent = perRevisar ? `${perRevisar} per revisar` : vius.length ? String(vius.length) : "";
  $("#punt-grafics").hidden = !perRevisar;
  $("#ajuda-grafics").textContent = !tots.length
    ? "Encara no hi ha cap pla. Demana'l a Claude, al xat: «proposa'm gràfics»."
    : notes ? `Quan acabis, digues a Claude: «mira les notes dels gràfics» (${notes === 1 ? "n'hi ha una" : `n'hi ha ${notes}`}).`
    : "Toca'n un per veure'l al vídeo. Si en vols canviar algun, toca «Canvia» i escriu-li una nota per a Claude.";
  for (const [id, fet] of targetesGrafic) if (!graficDe(id)) { fet.tl?.kill?.(); targetesGrafic.delete(id); }
  ompleGrafics($("#pla-grafics"), vius);
  ompleGrafics($("#grafics-trets"), trets);
  $("#grup-trets").hidden = !trets.length;
  $("#compte-trets").textContent = String(trets.length);
}

function decideixGrafic(id, nou) {
  const g = graficDe(id);
  if (!g) return;
  if (nou === "canvia") {  // primer s'escriu la nota; l'estat canvia en desar-la
    notaOberta = notaOberta === id ? null : id;
    pintaPla();
    if (notaOberta) targetesGrafic.get(id)?.el.querySelector("textarea").focus();
    return;
  }
  if (g.estat === nou) nou = "proposat";  // tornar a tocar el botó el desfà
  notaOberta = null;
  canvia((e) => { Object.assign(e.grafics.find((x) => x.id === id), { estat: nou, nota: "" }); });
  previaBruta = true;
  if (nou === "tret") avis("Tret. El trobaràs a «Trets», a sota, si el vols tornar a posar.");
}

function desaNotaGrafic(id, text) {
  const nota = text.trim();
  notaOberta = null;
  canvia((e) => { Object.assign(e.grafics.find((x) => x.id === id), { estat: nota ? "canvia" : "proposat", nota }); });
  if (nota) avis("Nota desada. Quan acabis, digues a Claude: «mira les notes dels gràfics».", 4000);
}

// --- Editar tocant el vídeo ---------------------------------------------------------------------
// Es toquen els subtítols o el títol al vídeo: queden marcats i es poden arrossegar amunt i avall, i
// una barra petita en canvia l'estil (en dibuixos), el color (els de la marca) i la mida. Visual:
// sense haver de llegir res.

let capaTriada = null;   // "subtitols", "titol" o "grafic:<id>"
let arrossegantCapa = null;  // {y0, valor0, alcada, valor}

const dinsDe = (r, e) => r && e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top - 8 && e.clientY <= r.bottom + 8;

// On es veu ara (px de pantalla) la línia de subtítols, el títol o un gràfic; null si no es veu.
function caixaCapa(quin) {
  if (vista !== "directe" || $("#capa-subtitols").hidden) return null;
  if (quin.startsWith("grafic:")) {
    const lloc = $(`#tg-host .tg-lloc[data-id="${CSS.escape(quin.slice(7))}"]`);
    if (!lloc || getComputedStyle(lloc).visibility !== "visible" || Number(getComputedStyle(lloc).opacity) < 0.1) return null;
    const r = lloc.firstElementChild?.getBoundingClientRect();
    return r && r.height ? r : null;
  }
  if (quin === "titol") {
    const host = $("#tt-host");
    const bloc = host.querySelector(".tt-bloc");
    if (!bloc || getComputedStyle(host).visibility !== "visible") return null;
    const r = bloc.getBoundingClientRect();
    return r.height ? r : null;
  }
  const host = $("#ts-host");
  if (host.hidden || getComputedStyle(host).opacity === "0") return null;
  const linia = [...host.children].find((el) => el.classList.contains("ts-linia") && getComputedStyle(el).visibility === "visible");
  const cont = linia?.firstElementChild;
  if (!cont) return null;
  // Apilades o escampades: només les files que ja han sortit (les altres hi són, però no es veuen).
  const files = [...cont.querySelectorAll(".ts-fila")].filter((f) => Number(getComputedStyle(f).opacity) > 0.05);
  const rects = (files.length ? files : [cont]).map((el) => el.getBoundingClientRect()).filter((r) => r.height);
  if (!rects.length) return null;
  const [left, top] = [Math.min(...rects.map((r) => r.left)), Math.min(...rects.map((r) => r.top))];
  const [right, bottom] = [Math.max(...rects.map((r) => r.right)), Math.max(...rects.map((r) => r.bottom))];
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

const estilDe = (quin) => (quin === "titol" ? estilTitol : estilSub);
// Els gràfics que es veuen ara, de dalt a baix de la llista (el primer que es toca és el de més amunt).
const graficsALaVista = () => [...$("#tg-host").querySelectorAll(".tg-lloc[data-id]")].map((el) => `grafic:${el.dataset.id}`);
const canviaCapa = (quin, canvis) => (quin === "titol" ? canviaTitol(canvis) : canviaEstil(canvis));

function triaCapa(quin) {
  capaTriada = quin;
  $(".pantalla").classList.add("editant");  // el botó gran de reproduir no tapa el que s'edita
  pintaBarraCapa();
}

function deixaCapa() {
  capaTriada = null;
  $(".pantalla").classList.remove("editant");
  arrossegantCapa = null;
  $("#marc-capa").hidden = true;
  $("#barra-capa").hidden = true;
}

// Cada fotograma: el marc segueix el que s'ha triat (les paraules entren, la línia canvia…).
function pintaMarcCapa() {
  if (!capaTriada) return;
  const r = caixaCapa(capaTriada);
  if (!r && !arrossegantCapa) { deixaCapa(); return; }
  if (!r) return;
  const base = $("#capa-edita").getBoundingClientRect();
  Object.assign($("#marc-capa").style, {
    left: `${r.left - base.left - 6}px`, top: `${r.top - base.top - 6}px`,
    width: `${r.width + 12}px`, height: `${r.height + 12}px`,
  });
  $("#marc-capa").hidden = false;
  // La barra, a la meitat on no hi ha el que s'edita.
  $("#barra-capa").classList.toggle("a-dalt", r.top + r.height / 2 - base.top > base.height / 2);
}

function pintaBarraCapa() {
  const barra = $("#barra-capa");
  barra.textContent = "";
  const quin = capaTriada;
  if (quin?.startsWith("grafic:")) { pintaBarraGrafic(quin.slice(7)); return; }
  const e = estilDe(quin);
  if (!quin || !e) { barra.hidden = true; return; }
  barra.hidden = false;
  // Els estils fets, en dibuixos.
  const estils = document.createElement("div");
  estils.className = "barra-estils";
  barra.append(estils);
  const llista = quin === "titol" ? estilsTitol : estilsPredefinits;
  const actual = quin === "titol" ? predefinitTitol() : predefinitActual();
  for (const p of llista.slice(0, 6)) {
    const valors = ambMarca(quin, p.valors);
    const mostra = botoEstil(estils, p, p === actual, () => { canviaCapa(quin, valors); pintaBarraCapa(); });
    if (!window.TallatSubtitols) continue;
    if (quin === "titol") pintaMostraTitol(mostra, { ...e, ...valors, mida: 0.3, clau_mida: 1, corba: 0 }, "*Aa*", 1080);
    else pintaMostra(mostra, { ...e, ...valors }, { paraules: [MOSTRA[0], MOSTRA[2]], alcada: 1080, mida: 0.2 });
  }
  // Els colors de la marca (i el d'ara), en rodones.
  const fila = document.createElement("div");
  fila.className = "barra-fila";
  barra.append(fila);
  const m = estilMarca || {};
  // Sense marca, el blanc de sempre; amb marca, només els seus colors (n'hi ha que no volen mai el blanc pur).
  const colors = [...new Set([e.color, m.color_text, m.color_destacat, m.color_principal, m.color_secundari, m.color_clar,
    marcaFeta() ? null : "#FFFFFF"].filter(Boolean).map((c) => c.toUpperCase()))].slice(0, 6);
  for (const c of colors) {
    const b = document.createElement("button");
    b.className = "rodona";
    b.style.background = c;
    b.setAttribute("aria-label", `Color ${c}`);
    b.setAttribute("aria-pressed", String((e.color || "").toUpperCase() === c));
    b.addEventListener("click", () => { canviaCapa(quin, { color: c }); pintaBarraCapa(); });
    fila.append(b);
  }
  // La mida.
  const mida = document.createElement("input");
  Object.assign(mida, { type: "range", min: quin === "titol" ? 0.035 : 0.04, max: quin === "titol" ? 0.14 : 0.12,
    step: 0.002, value: e.mida ?? 0.075 });
  mida.setAttribute("aria-label", "Mida");
  mida.addEventListener("input", () => canviaCapa(quin, { mida: Number(mida.value) }));
  const icona = document.createElement("span");
  icona.className = "barra-icona";
  icona.setAttribute("aria-hidden", "true");
  icona.textContent = "A";
  fila.append(icona, mida);
  // Més opcions (el panell sencer) i tancar.
  const mes = document.createElement("button");
  mes.className = "enllac";
  mes.textContent = quin === "titol" ? "Text i més" : "Més";
  mes.addEventListener("click", () => {
    const q = quin;
    deixaCapa();
    if (q === "titol") { triaPestanya("grafics"); obreTitol(); } else triaPestanya("subtitols");
  });
  const tanca = document.createElement("button");
  tanca.className = "icona";
  tanca.setAttribute("aria-label", "Tanca");
  tanca.innerHTML = '<svg viewBox="0 0 20 20"><path d="m5.5 5.5 9 9m0-9-9 9"/></svg>';
  tanca.addEventListener("click", deixaCapa);
  fila.append(mes, tanca);
  pintaMarcCapa();
}

// --- Bloc de color ----------------------------------------------------------------------------------
// Mentre surt un gràfic amb bloc, el vídeo s'encongeix (suau) fins a una targeta a baix i a sobre hi ha
// el color de la marca. La mateixa geometria i el mateix ritme que l'export (motor/grafics.py, BLOC i
// pas_bloc; motor/exporta.py, _filtre_bloc). Tot en px de 1080 × 1920.

const BLOC = { x: 151, y: 838, w: 778, h: 972, retall_y: 160 };
const ANIMACIO_BLOC = 0.45;
let blocsMuntatge = [];  // [{inici, final, color}] en temps del muntatge (els calcula el servidor)
let zoomVideo = 1.15;
let darrerBloc = "";

function pasBloc(t, inici, final) {
  const d = Math.min(ANIMACIO_BLOC, (final - inici) / 2);
  if (d <= 0) return 0;
  const p = Math.min(1, Math.max(0, Math.min((t - inici) / d, (final - t) / d)));
  return p * p * (3 - 2 * p);
}

function pintaBloc() {
  const m = tempsMuntatge();
  const bloc = vista === "directe" ? blocsMuntatge.find((b) => m >= b.inici && m < b.final) : null;
  const e = bloc ? pasBloc(m, bloc.inici, bloc.final) : 0;
  const v = R.v;
  const z = v.classList.contains("zoom") ? zoomVideo : 1;
  const sig = bloc ? `${bloc.color}|${e.toFixed(4)}|${z}` : "";
  if (sig === darrerBloc) return;
  darrerBloc = sig;
  const capa = $("#capa-bloc");
  capa.hidden = !bloc;
  if (bloc) capa.style.background = bloc.color;
  if (!e) {
    for (const video of $$(".pantalla > video")) {
      for (const p of ["transform", "clip-path", "box-shadow"]) video.style.removeProperty(p);
    }
    return;
  }
  // El vídeo (amb el zoom, si en té) s'escala des del centre i baixa; el que surt de la targeta no es veu.
  const s = 1 - (1 - BLOC.w / 1080) * e;
  const ty = ((BLOC.y - BLOC.retall_y * BLOC.w / 1080) * e) / 1920 + 0.5 * (s - 1);
  const sz = s * z;
  const local = (o, t) => 0.5 + (o - 0.5 - t) / sz;  // d'on es veu a la pantalla a on és dins del vídeo
  const pc = (x) => `${(x * 100).toFixed(3)}%`;
  const dalt = local((BLOC.y * e) / 1920, ty);
  const baix = 1 - local(1 - ((1920 - BLOC.y - BLOC.h) * e) / 1920, ty);
  const costat = local((BLOC.x * e) / 1080, 0);
  v.style.transform = `translateY(${pc(ty)}) scale(${sz.toFixed(5)})`;
  v.style.clipPath = `inset(${pc(dalt)} ${pc(costat)} ${pc(baix)} round calc(var(--radi-gran) * ${((1 - e) / sz).toFixed(4)}))`;
  v.style.boxShadow = "none";
}

// La barra d'un gràfic: l'estil (net, mac, scrapbook, editorial) en dibuixos, i Mantén, Canvia, Treu.
// Si el canvies o el mous, és que t'agrada: queda mantingut (Claude ja no el tocarà).
function canviaGrafic(id, canvis) {
  canvia((e) => {
    const g = e.grafics.find((x) => x.id === id);
    if (g) Object.assign(g, canvis, g.estat === "proposat" ? { estat: "mantingut" } : {});
  });
  previaBruta = true;
}

function pintaBarraGrafic(id) {
  const barra = $("#barra-capa");
  const g = graficDe(id);
  const d = dibuixosGrafics[id];
  if (!g || !d) { deixaCapa(); return; }
  barra.hidden = false;
  const estils = document.createElement("div");
  estils.className = "barra-estils quatre";
  barra.append(estils);
  for (const estil of ["net", "mac", "scrapbook", "editorial"]) {
    const b = document.createElement("button");
    b.className = "estil";
    b.setAttribute("aria-pressed", String((g.estil || d.estil) === estil));
    b.setAttribute("aria-label", `Estil ${estil}`);
    b.innerHTML = '<span class="estil-mostra"></span>';
    b.addEventListener("click", () => { canviaGrafic(id, { estil }); setTimeout(pintaBarraCapa, 0); });
    estils.append(b);
    if (window.TallatGrafics && paletaGrafics) {
      const host = document.createElement("div");
      b.firstChild.append(host);
      const mostra = { ...d, estil, posicio: "mig", limits: [0, 1920], inici: 0, final: 1e5,
        punts: (d.punts || []).map((p) => ({ ...p, t: 0 })) };
      TallatGrafics.construeix(host, [mostra], paletaGrafics, OP_GRAFICS).seek(50, false);
      host.style.transform = `scale(${b.firstChild.clientWidth / 1080})`;
      host.style.transformOrigin = "0 0";
      host.style.marginTop = `${(b.firstChild.clientHeight - b.firstChild.clientWidth * 1920 / 1080) / 2}px`;
    }
  }
  // El bloc de color: el vídeo es fa petit a baix i el gràfic té el fons de la marca.
  const filaBloc = document.createElement("div");
  filaBloc.className = "barra-fila";
  barra.append(filaBloc);
  const bloc = document.createElement("button");
  bloc.className = "boto petit bloc-color";
  const ambBloc = !!d.bloc;  // si no s'ha dit, el de cada tipus (la web i les fotos, amb bloc)
  bloc.setAttribute("aria-pressed", String(ambBloc));
  bloc.title = "El vídeo es fa petit a baix i el gràfic surt sobre el color de la teva marca";
  bloc.innerHTML = '<span class="mostra-bloc"></span><span></span>';
  bloc.lastChild.textContent = ambBloc ? "Amb bloc de color" : "Bloc de color";
  const rol = ["mac", "scrapbook"].includes(g.estil || d.estil) ? "principal" : "fosc";
  if (paletaGrafics?.[rol]) bloc.style.setProperty("--color-bloc", paletaGrafics[rol]);
  bloc.addEventListener("click", () => { canviaGrafic(id, { bloc: !ambBloc }); setTimeout(pintaBarraCapa, 0); });
  filaBloc.append(bloc);
  const fila = document.createElement("div");
  fila.className = "barra-fila";
  barra.append(fila);
  for (const [estat, text] of [["mantingut", "Mantén"], ["canvia", "Canvia"], ["tret", "Treu"]]) {
    const b = document.createElement("button");
    b.className = `boto petit decisio-${estat}`;
    b.textContent = text;
    b.setAttribute("aria-pressed", String(g.estat === estat));
    b.addEventListener("click", () => {
      if (estat === "canvia") {  // la nota s'escriu a la llista dels gràfics
        deixaCapa();
        triaPestanya("grafics");
        decideixGrafic(id, "canvia");
        targetesGrafic.get(id)?.el.scrollIntoView({ block: "center", behavior: "smooth" });
        return;
      }
      decideixGrafic(id, estat);
      if (estat === "tret") deixaCapa(); else setTimeout(pintaBarraCapa, 0);
    });
    fila.append(b);
  }
  const tanca = document.createElement("button");
  tanca.className = "icona";
  tanca.setAttribute("aria-label", "Tanca");
  tanca.innerHTML = '<svg viewBox="0 0 20 20"><path d="m5.5 5.5 9 9m0-9-9 9"/></svg>';
  tanca.addEventListener("click", deixaCapa);
  fila.append(tanca);
  pintaMarcCapa();
}

function instalaEdicioAlVideo() {
  const pantalla = $(".pantalla");
  const host = (quin) => (quin === "titol" ? $("#tt-host") : $("#ts-host"));
  const prefix = (quin) => (quin === "titol" ? "tt" : "ts");
  pantalla.addEventListener("pointerdown", (e) => {
    if (vista !== "directe" || e.button !== 0 || e.target.closest("#gran-play, #barra-capa")) return;
    const quin = e.target.closest("#marc-capa") ? capaTriada
      : [...graficsALaVista(), "titol", "subtitols"].find((q) => dinsDe(caixaCapa(q), e));
    if (!quin) { deixaCapa(); return; }
    e.preventDefault();
    if (sona()) atura();
    if (quin !== capaTriada) triaCapa(quin);
    // I d'entrada es pot arrossegar amunt i avall.
    const alcada = $("#capa-subtitols").clientHeight || 1;
    let valor0;
    if (quin.startsWith("grafic:")) {  // el centre del gràfic, ara
      const r = caixaCapa(quin);
      valor0 = r ? (r.top + r.height / 2 - $("#capa-subtitols").getBoundingClientRect().top) / alcada : 0.5;
    } else valor0 = estilDe(quin)?.posicio_y ?? (quin === "titol" ? 0.25 : 0.7);
    arrossegantCapa = { quin, y0: e.clientY, valor0, valor: valor0, alcada };
    pantalla.setPointerCapture(e.pointerId);
  });
  pantalla.addEventListener("pointermove", (e) => {
    const a = arrossegantCapa;
    if (!a) return;
    a.valor = limita(a.valor0 + (e.clientY - a.y0) / a.alcada, 0.08, 0.92);
    // Mentre s'arrossega, només es mou (no es refà res): el canvi es desa en deixar-lo anar.
    if (a.quin.startsWith("grafic:")) {
      const lloc = $(`#tg-host .tg-lloc[data-id="${CSS.escape(a.quin.slice(7))}"]`);
      if (lloc) lloc.style.translate = `0 ${(a.valor - a.valor0) * 1920}px`;
      return;
    }
    host(a.quin).style.setProperty(`--${prefix(a.quin)}-y`, `${a.valor * 100}%`);
    host(a.quin).style.setProperty(`--${prefix(a.quin)}-ancora`, `${-a.valor * 100}%`);
  });
  const deixa = () => {
    const a = arrossegantCapa;
    arrossegantCapa = null;
    if (!a || Math.abs(a.valor - a.valor0) <= 0.002) return;
    if (a.quin.startsWith("grafic:")) canviaGrafic(a.quin.slice(7), { posicio: Math.round(a.valor * 1000) / 1000 });
    else canviaCapa(a.quin, { posicio_y: Math.round(a.valor * 1000) / 1000 });
  };
  pantalla.addEventListener("pointerup", deixa);
  pantalla.addEventListener("pointercancel", deixa);
}

// --- La visita guiada (el primer cop) -----------------------------------------------------------
// Unes quantes passes curtes: s'enfosqueix la pàgina, s'il·lumina una part i una frase diu què és.
// Surt sola el primer cop; després, amb el «?» de dalt.

const PASSES_GUIA = [
  ["#seccio-reels", "Aquí hi ha els reels que t'ha proposat Claude. Toca'n un per obrir-lo."],
  [".text", "Això és el que dius. Toca una paraula per escoltar-la. Amb el clic dret la treus del vídeo (i la tornes a posar)."],
  [".pantalla", "Toca els subtítols, el títol o un gràfic al vídeo per canviar-los. Arrossega'ls per moure'ls."],
  ["#pestanyes", "Aquí tens els subtítols, els gràfics, el so i els vídeos que exportes."],
  ["#esborrany", "Esborrany: el vídeo sencer per mirar-lo. Final…: el desa a punt per penjar."],
];
let passaGuia = -1;
let passesVisibles = [];

function esVeu(el) {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && !el.closest("[hidden]");
}

function obreGuia() {
  passesVisibles = PASSES_GUIA.filter(([sel]) => esVeu($(sel)));
  if (!passesVisibles.length) return;
  passaGuia = 0;
  $("#guia").hidden = false;
  pintaGuia();
  $("#guia-seguent").focus();
}

function tancaGuia() {
  passaGuia = -1;
  $("#guia").hidden = true;
  desa("tallat.guia-vista", true);
}

function pintaGuia() {
  if (passaGuia < 0) return;
  const [sel, text] = passesVisibles[passaGuia];
  const r = $(sel).getBoundingClientRect();
  const marge = 6;
  Object.assign($("#guia-forat").style, {
    left: `${r.left - marge}px`, top: `${r.top - marge}px`, width: `${r.width + 2 * marge}px`, height: `${r.height + 2 * marge}px`,
  });
  $("#guia-text").textContent = text;
  $("#guia-pas").textContent = `${passaGuia + 1} de ${passesVisibles.length}`;
  const darrera = passaGuia === passesVisibles.length - 1;
  $("#guia-seguent").textContent = darrera ? "Som-hi" : "Següent";
  $("#guia-salta").hidden = darrera;
  // La bombolla, al costat on hi ha més lloc (sota, sobre, a la dreta o a l'esquerra).
  const b = $("#guia-bombolla");
  const amplada = Math.min(320, innerWidth - 24);
  b.style.width = `${amplada}px`;
  const alcada = b.offsetHeight || 120;
  let x = limita(r.left + r.width / 2 - amplada / 2, 12, innerWidth - amplada - 12);
  let y;
  if (innerHeight - r.bottom > alcada + 24) y = r.bottom + 14;
  else if (r.top > alcada + 24) y = r.top - alcada - 14;
  else {  // un element molt alt (la columna del text, el vídeo): al costat
    y = limita(r.top + 24, 12, innerHeight - alcada - 12);
    x = innerWidth - r.right > amplada + 24 ? r.right + 14 : Math.max(12, r.left - amplada - 14);
  }
  Object.assign(b.style, { left: `${x}px`, top: `${y}px` });
}

function instalaGuia() {
  $("#obre-guia").addEventListener("click", obreGuia);
  $("#guia-salta").addEventListener("click", tancaGuia);
  $("#guia-seguent").addEventListener("click", () => {
    if (passaGuia >= passesVisibles.length - 1) tancaGuia();
    else { passaGuia++; pintaGuia(); }
  });
  addEventListener("resize", pintaGuia);
  document.addEventListener("keydown", (e) => {
    if (passaGuia >= 0 && e.key === "Escape") { e.stopPropagation(); tancaGuia(); }
  }, true);
}

// --- La teva marca, pas a pas -------------------------------------------------------------------
// Quatre passos visuals dins la pàgina: els colors, les lletres, l'estil dels gràfics i la crida.
// No va al principi: s'ofereix quan arribes als subtítols o als gràfics (o des de «La teva marca»).

const PALETES = [
  { nom: "Clàssica", color_text: "#FFFFFF", color_principal: "#1D1D1F", color_destacat: "#FFD60A", color_secundari: "#8E8E93", color_clar: "#F5F5F7", color_fosc: "#111111" },
  { nom: "Càlida", color_text: "#FFF8F0", color_principal: "#C2410C", color_destacat: "#FDBA74", color_secundari: "#7C2D12", color_clar: "#FFF1E6", color_fosc: "#2B1608" },
  { nom: "Fresca", color_text: "#FFFFFF", color_principal: "#0F766E", color_destacat: "#5EEAD4", color_secundari: "#F59E0B", color_clar: "#F0FDFA", color_fosc: "#0B2A27" },
  { nom: "Pastel", color_text: "#FFFFFF", color_principal: "#DB6A9A", color_destacat: "#FDE68A", color_secundari: "#93C5FD", color_clar: "#FDF2F8", color_fosc: "#3B2440" },
  { nom: "Nit", color_text: "#F8FAFC", color_principal: "#6366F1", color_destacat: "#A5B4FC", color_secundari: "#F472B6", color_clar: "#EEF2FF", color_fosc: "#0F172A" },
  { nom: "Revista", color_text: "#FAFAF9", color_principal: "#B91C1C", color_destacat: "#FDE047", color_secundari: "#57534E", color_clar: "#F5F5F4", color_fosc: "#1C1917" },
];
const PARELLES = [
  { nom: "Moderna", lletra_titols: "poppins", lletra_text: "inter", lletra_accent: "playfair-display" },
  { nom: "Revista", lletra_titols: "fraunces", lletra_text: "dm-sans", lletra_accent: "instrument-serif" },
  { nom: "Impacte", lletra_titols: "anton", lletra_text: "archivo", lletra_accent: "fraunces" },
  { nom: "Elegant", lletra_titols: "dm-serif-display", lletra_text: "dm-sans", lletra_accent: "dm-serif-display" },
  { nom: "Amable", lletra_titols: "fredoka", lletra_text: "poppins", lletra_accent: "caveat" },
  { nom: "Neta", lletra_titols: "inter-tight", lletra_text: "inter", lletra_accent: "fraunces" },
];
const TITOLS_ASSISTENT = ["Els teus colors", "Les teves lletres", "Com són els teus gràfics", "La teva crida"];
let assistent = null;  // {pas, colors, parella, energia, grafics, crida}

const marcaFeta = (m = estilMarca) => !!m && COLORS_MARCA.some(([, k]) => m[k]);

function pintaOfertaMarca() {
  for (const b of $$("[data-obre-assistent]")) b.hidden = marcaFeta() || !estilMarca;
}

// Les lletres de la biblioteca, per veure-les escrites (de la mateixa web d'on es baixen en triar-les).
const lletresVistes = new Map();
function carregaLletraBiblioteca(id) {
  const l = bibliotecaLletres.lletres.find((x) => x.id === id);
  if (!l || lletresVistes.has(id)) return l?.nom;
  const paquet = l.variable ? `@fontsource-variable/${id}` : `@fontsource/${id}`;
  const fitxer = l.variable ? `${id}-latin-wght-normal` : `${id}-latin-${(l.pesos || [400])[0]}-normal`;
  const font = new FontFace(l.nom, `url(https://cdn.jsdelivr.net/npm/${paquet}@5.3.0/files/${fitxer}.woff2)`,
    l.variable ? { weight: "100 900" } : {});
  lletresVistes.set(id, font);
  font.load().then((f) => document.fonts.add(f)).catch(() => {});
  return l.nom;
}
const nomLletra = (id) => bibliotecaLletres.lletres.find((x) => x.id === id)?.nom || id;

function obreAssistent() {
  const m = estilMarca || {};
  assistent = {
    pas: 0,
    colors: marcaFeta(m) ? Object.fromEntries(COLORS_MARCA.map(([, k]) => [k, m[k] || null])) : { ...PALETES[0] },
    parella: null,
    energia: energies(m),
    grafics: m.grafics || "normal",
    crida: m.crida || "",
  };
  delete assistent.colors.nom;
  $("#velo").hidden = false;
  $("#full-marca").hidden = false;
  pintaAssistent();
}

function tancaAssistent() {
  assistent = null;
  $("#velo").hidden = true;
  $("#full-marca").hidden = true;
}

function opcioAssistent(cont, triada, fes) {
  const b = document.createElement("button");
  b.className = "opcio-assistent";
  b.setAttribute("aria-pressed", String(triada));
  b.addEventListener("click", fes);
  cont.append(b);
  return b;
}

function pintaAssistent() {
  const a = assistent;
  if (!a) return;
  $("#titol-assistent").textContent = TITOLS_ASSISTENT[a.pas];
  $$("#passes-assistent i").forEach((el, k) => el.classList.toggle("fet", k <= a.pas));
  $("#assistent-enrere").textContent = a.pas ? "Enrere" : "Ara no";
  $("#assistent-seguent").textContent = a.pas === 3 ? "Fet" : "Següent";
  const cos = $("#cos-assistent");
  cos.textContent = "";
  const graella = document.createElement("div");
  graella.className = "graella-assistent";
  cos.append(graella);
  if (a.pas === 0) {
    for (const p of PALETES) {
      const triada = COLORS_MARCA.every(([, k]) => (a.colors[k] || "").toUpperCase() === p[k]);
      const b = opcioAssistent(graella, triada, () => { a.colors = { ...p }; delete a.colors.nom; pintaAssistent(); });
      b.innerHTML = '<span class="rodones"></span><span class="nom-opcio"></span>';
      for (const k of ["color_principal", "color_destacat", "color_secundari", "color_clar", "color_fosc"]) {
        const r = document.createElement("i");
        r.style.background = p[k];
        b.firstChild.append(r);
      }
      b.lastChild.textContent = p.nom;
    }
    // Els meus colors: els sis, un per un.
    const propis = document.createElement("div");
    propis.className = "colors-marca colors-assistent";
    for (const [, k] of COLORS_MARCA) {
      const l = document.createElement("label");
      l.className = "color";
      l.innerHTML = '<input type="color"><span></span>';
      l.firstChild.value = (a.colors[k] || "#8E8E93").toLowerCase();
      l.lastChild.textContent = { color_text: "Text", color_principal: "Principal", color_destacat: "Destacat",
        color_secundari: "Secundari", color_clar: "Clar", color_fosc: "Fosc" }[k];
      l.firstChild.addEventListener("input", (e) => { a.colors[k] = e.target.value.toUpperCase(); });
      propis.append(l);
    }
    const detalls = document.createElement("details");
    detalls.className = "grup-estil";
    detalls.innerHTML = "<summary>Els meus colors</summary>";
    detalls.append(propis);
    cos.append(detalls);
  } else if (a.pas === 1) {
    for (const p of PARELLES) {
      const b = opcioAssistent(graella, a.parella === p, () => { a.parella = p; pintaAssistent(); });
      b.classList.add("lletres-opcio");
      const t = document.createElement("strong");
      t.textContent = "El teu títol";
      t.style.fontFamily = `"${carregaLletraBiblioteca(p.lletra_titols)}"`;
      const x = document.createElement("span");
      x.textContent = "i així es llegeix el text";
      x.style.fontFamily = `"${carregaLletraBiblioteca(p.lletra_text)}"`;
      const c = document.createElement("em");
      c.textContent = "la paraula clau";
      c.style.fontFamily = `"${carregaLletraBiblioteca(p.lletra_accent)}"`;
      c.style.color = a.colors.color_principal || "inherit";
      b.append(t, x, c);
    }
    if (fontsKit.length) {
      const b = opcioAssistent(graella, a.parella === "kit", () => { a.parella = "kit"; pintaAssistent(); });
      b.classList.add("lletres-opcio");
      b.innerHTML = "<strong>Les meves</strong><span>Les lletres que ja tens al kit</span>";
    }
  } else if (a.pas === 2) {
    const paleta = { ...(paletaGrafics || {}), text: a.colors.color_text, principal: a.colors.color_principal,
      destacat: a.colors.color_destacat || a.colors.color_text, secundari: a.colors.color_secundari || a.colors.color_principal,
      clar: a.colors.color_clar || "#FFFFFF", fosc: a.colors.color_fosc || "#111111" };
    if (a.parella && a.parella !== "kit") {
      Object.assign(paleta, { lletra_titols: nomLletra(a.parella.lletra_titols), lletra_text: nomLletra(a.parella.lletra_text),
        lletra_accent: nomLletra(a.parella.lletra_accent) });
    }
    for (const [estil, nom] of [["net", "Net"], ["mac", "Mac"], ["scrapbook", "Scrapbook"], ["editorial", "Editorial"]]) {
      const triat = a.energia.includes(estil);
      const b = opcioAssistent(graella, triat, () => {
        const nou = new Set(a.energia);
        if (nou.has(estil) && nou.size > 1) nou.delete(estil); else nou.add(estil);
        a.energia = [...nou];
        pintaAssistent();
      });
      b.classList.add("grafic-opcio");
      b.innerHTML = '<span class="mostra-grafic"><span></span></span><span class="nom-opcio"></span>';
      b.lastChild.textContent = nom;
      if (window.TallatGrafics) {
        const host = b.querySelector(".mostra-grafic > span");
        const mostra = { id: estil, tipus: estil === "editorial" ? "frase" : "llista", estil, posicio: "mig", limits: [0, 1920],
          inici: 0, final: 1e5, text: estil === "editorial" ? "una *idea* clara" : "3 coses",
          punts: estil === "editorial" ? [] : [{ text: "una", t: 0 }, { text: "dues", t: 0 }] };
        requestAnimationFrame(() => {
          TallatGrafics.construeix(host, [mostra], paleta, OP_GRAFICS).seek(50, false);
          const caixa = b.querySelector(".mostra-grafic");
          host.style.transform = `scale(${caixa.clientWidth / 1080})`;
          host.style.marginTop = `${(caixa.clientHeight - caixa.clientWidth * 1920 / 1080) / 2}px`;
        });
      }
    }
    const quants = document.createElement("div");
    quants.className = "segmentat ample";
    quants.setAttribute("role", "radiogroup");
    quants.setAttribute("aria-label", "Quants gràfics");
    for (const [v, t] of [["pocs", "Pocs"], ["normal", "Normal"], ["molts", "Molts"]]) {
      const b = document.createElement("button");
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(a.grafics === v));
      b.textContent = t;
      b.addEventListener("click", () => { a.grafics = v; pintaAssistent(); });
      quants.append(b);
    }
    cos.append(quants);
  } else {
    graella.remove();
    const camp = document.createElement("input");
    camp.type = "text";
    camp.className = "camp-text";
    camp.maxLength = 600;
    camp.placeholder = "Per exemple: desa't aquest vídeo per quan el necessitis";
    camp.value = a.crida;
    camp.setAttribute("aria-label", "La teva crida a l'acció");
    camp.addEventListener("input", () => { a.crida = camp.value; });
    cos.append(camp);
    setTimeout(() => camp.focus(), 50);
  }
}

async function acabaAssistent() {
  const a = assistent;
  tancaAssistent();
  canviaMarca({ ...a.colors, energia: a.energia, grafics: a.grafics, crida: a.crida.trim() });
  pintaPanellMarca();
  if (a.parella && a.parella !== "kit") {
    for (const clau of ["lletra_titols", "lletra_text", "lletra_accent"]) await baixaLletra(a.parella[clau], "marca", clau);
  } else {
    await desaEstils();
  }
  avis("Fet. Els subtítols, el títol i els gràfics ja tenen la teva marca.", 5000);
}

function instalaAssistent() {
  for (const b of $$("[data-obre-assistent]")) b.addEventListener("click", obreAssistent);
  $("#assistent-enrere").addEventListener("click", () => {
    if (!assistent || assistent.pas === 0) tancaAssistent();
    else { assistent.pas--; pintaAssistent(); }
  });
  $("#assistent-seguent").addEventListener("click", () => {
    if (!assistent) return;
    if (assistent.pas === 3) acabaAssistent();
    else { assistent.pas++; pintaAssistent(); }
  });
  document.addEventListener("keydown", (e) => {
    if (assistent && e.key === "Escape") { e.stopPropagation(); tancaAssistent(); }
  }, true);
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
  // Amb fitxer, surt al vídeo encara que estigui pendent (motor/projecte.py, _recursos): que es vegi.
  if (!["broll", "sticker"].includes(ins.tipus) || !(ins.estat === "acceptada" || (ins.fitxer && ins.estat !== "descartada"))) return null;
  const nom = ins.tipus === "sticker" ? "Sticker" : "B-roll";
  const llista = biblioteca[ins.tipus] || [];
  const fila = document.createElement("span");
  fila.className = "ins-accions";
  if (ins.fitxer) {
    fila.innerHTML = `<span class="fet">${nom} a punt (${String(ins.durada).replace(".", ",")} s)</span>
      <button class="enllac canvia discret">Canvia'l</button><button class="enllac treu-broll discret">Treu-lo</button>`;
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
      ${ins.manual  // les que afegeix Claude ja hi són: no cal acceptar-les (es poden treure)
        ? (ins.estat === "descartada" ? '<button class="enllac torna-ins">Torna-la a posar</button>' : '<span class="al-video">Al vídeo</span>')
        : `<button class="mini deixa ${ins.estat === "acceptada" ? "actiu" : ""}" title="Accepta-la" aria-label="Accepta-la">${ICONES.deixa}</button>`}
      <button class="mini treu" title="Descarta-la" aria-label="Descarta-la">${ICONES.esborra}</button>`;
    item.querySelector(".nom").textContent = nom;
    item.querySelector(".ins-text").textContent = `«${ins.text}»`;
    item.querySelector(".ins-estat").classList.toggle("important", !!ins.dubtosa && ins.estat === "pendent");
    item.querySelector(".ins-estat").textContent =
      ins.estat === "acceptada" ? (["broll", "sticker"].includes(ins.tipus) || ins.manual ? "" : `Acceptada. ${ajuda.replace(/^En acceptar-la, /, "")}`)
        : ins.estat === "descartada" ? "Descartada"
        : ins.sense_paraula ? "Sembla una instrucció, però no has dit «Claude». Si l'acceptes, en trec les paraules del vídeo."
        : ins.dubtosa ? "No he sabut on acaba: no he tret res del vídeo. Treu-ne tu les paraules." : "";
    const accions = accionsBroll(ins, item);
    if (accions) item.querySelector(".reel-text").append(accions);
    item.addEventListener("click", (e) => {
      if (e.target.closest(".deixa")) return decideixInstruccio(ins, ins.estat === "acceptada" ? "pendent" : "acceptada");
      if (e.target.closest(".torna-ins")) return decideixInstruccio(ins, "acceptada");
      if (e.target.closest(".treu")) {
        return decideixInstruccio(ins, ins.estat === "descartada" ? (ins.manual ? "acceptada" : "pendent") : "descartada");
      }
      const ancora = ins.ancora ?? ins.paraules[1];
      mostraParaula(ancora);
      if (vista === "directe") vesAOriginal(P.paraules[ancora].inici - 1.5);
    });
    fesClicable(item);
    cont.append(item);
  }
  actualitzaPestanyes();
}

async function decideixInstruccio(ins, nou) {
  try {
    await cua;  // primer, que es desin els canvis pendents
    const r = await api("/api/instruccio", { id: ins.id, estat: nou });
    estat = r.estat;
    aplicaTrams(r);
    refresca(true);
    if (nou === "acceptada" && ins.tipus === "talla") avis("Primer intent tret. El pots recuperar tocant-ne les paraules.");
    else if (nou === "acceptada" && ins.sense_paraula) avis("Fet: he tret la instrucció del vídeo.");
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
  instalaEdicioAlVideo();
  instalaGuia();
  instalaAssistent();
  instalaKits();
  instalaTitol();
  instalaBroll();
  instalaSo();
  instalaMarca();
  instalaPestanyes();
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
  $("#canvia-carpeta").addEventListener("click", () => triaCarpeta("tria"));
  $("#carpeta-projecte").addEventListener("click", () => triaCarpeta("projecte"));
  $("#fet-mostra").addEventListener("click", () => darrerFet && mostraAlFinder(darrerFet));
  $("#fet-tanca").addEventListener("click", () => { $("#fet-export").hidden = true; });
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

  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea, select")) return;
    if (capaTriada && e.key === "Escape") { deixaCapa(); return; }
    if (!$("#full-final").hidden) { if (e.key === "Escape") tancaFinal(); return; }
    if (editantTitol && e.key === "Escape") { tancaTitol(); return; }
    if (editantBroll && e.key === "Escape") { tancaBroll(); return; }
    if (editantMarca && e.key === "Escape") { tancaMarca(); return; }
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
    // Amb el teclat, l'espai prem el botó que té el focus (Mantén, Treu…); si no, reprodueix o atura.
    if (e.key === " " && e.target.closest?.("button") && e.target.matches(":focus-visible")) return;
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
  aplicaTrams(P);
  pintaText();
  refresca(false);
  marcaPausa();
  marcaSubtitols();
  estilsPredefinits = P.estils_subtitols || [];
  estilsTitol = P.estils_titol || [];
  aplicaEstilTitol(P.estil_titol);
  aplicaMarca(P);
  aplicaBroll(P);
  aplicaSo(P);
  kits = P.kits || [];
  kitActual = P.kit;
  pintaKits();
  bibliotecaLletres = P.biblioteca_lletres || bibliotecaLletres;
  versioEstil = P.versio_estil;
  carregaFontsKit(P.fonts_kit || []);
  aplicaEstilSubtitols(P.estil_subtitols);
  pintaPanellEstil();
  pintaVersions(P.exports || []);
  pintaCarpeta(P);
  pintaReels();
  try { biblioteca = await api("/api/biblioteca"); } catch { biblioteca = { broll: [], sticker: [] }; }
  pintaInstruccions();
  if (P.feina?.estat === "treballant") seguimentFeina(P.feina);
  consultaFeina.darrer = P.feina?.fitxer;
  if (!llegeix("tallat.guia-vista", false)) setTimeout(obreGuia, 600);  // el primer cop, la visita guiada
}


// --- So --------------------------------------------------------------------------------------
// La neteja de la veu i els efectes de so (motor/so.py). Els efectes sonen a la vista prèvia amb
// la mateixa pista que es barreja al vídeo final; la veu neta només s'escolta a les mostres (i a
// l'esborrany i el final).

let estilSo = null;        // la secció «so» del kit
let efectesMuntatge = [];  // [{clau, nom, so, t, actiu}]
let mostresSo = null;      // {abans, despres, sons: {nom: url}}
let mostraNivell = null;   // de quin nivell de neteja és la mostra «neta»
const aEfectes = $("#audio-efectes");

function posaPistaEfectes(url) {
  if (!url) { aEfectes.removeAttribute("src"); aEfectes.load(); return; }
  if (!aEfectes.src.endsWith(url)) aEfectes.src = url;
}

function sonaEfectes() {
  const actiu = vista === "directe" && R.reproduint && aEfectes.getAttribute("src");
  if (!actiu) { if (!aEfectes.paused) aEfectes.pause(); return; }
  const m = tempsMuntatge();
  if (aEfectes.readyState >= 1 && Math.abs(aEfectes.currentTime - m) > 0.12) aEfectes.currentTime = m;
  if (aEfectes.paused) aEfectes.play().catch(() => {});
}

// Les mostres es demanen d'una en una (cada una fa treballar ffmpeg) i, si s'està canviant el
// nivell de la neteja, quan el canvi ja és al kit: si no, el servidor faria la del nivell d'abans.
let mostresEnCurs = null;
function carregaMostresSo() {
  const nivell = estilSo?.soroll || "suau";
  if (mostresEnCurs || Object.keys(pendents.so).length) return;
  if (mostresSo && mostraNivell === nivell) return;
  $("#s-preparant").hidden = false;
  mostresEnCurs = (async () => {
    try {
      await cua;
      const r = await api("/api/so/mostres", {});
      mostresSo = r;
      mostraNivell = nivell;
      $("#s-abans").src = r.abans;
      $("#s-despres").src = r.despres;
    } catch (e) {
      avis(e.message, 6000);
      mostresSo = mostresSo || { sons: {} };  // no ho tornem a provar sense parar
      mostraNivell = nivell;
    }
    $("#s-preparant").hidden = true;
    mostresEnCurs = null;
    pintaSo();  // si mentrestant ha canviat el nivell, ara es demana la bona
  })();
}

function pintaSo() {
  if (!estilSo || $("#pestanya-so").hidden) return;
  const e = estilSo;
  const neteja = e.neteja !== false;
  $("#s-neteja").setAttribute("aria-checked", String(neteja));
  $("#camp-s-soroll").hidden = !neteja;
  $("#s-despres-caixa").hidden = !neteja;
  marcaSegmentat("s-soroll", e.soroll || "suau");
  marcaSegmentat("s-efectes", e.efectes || "pocs");
  $("#s-volum").value = e.volum_efectes ?? 0.5;
  $("#camp-s-volum").hidden = e.efectes === "cap";
  carregaMostresSo();

  const actius = efectesMuntatge.filter((x) => x.actiu).length;
  $("#compte-efectes").textContent = efectesMuntatge.length ? `${actius} de ${efectesMuntatge.length}` : "";
  const llista = $("#llista-efectes");
  llista.textContent = "";
  if (e.efectes === "cap") return;
  if (!efectesMuntatge.length) {
    llista.innerHTML = `<p class="buit">Aquest vídeo encara no té res que soni: surten amb el b-roll, els stickers i el títol${e.efectes === "molts" ? ", i amb les paraules destacades" : ""}.</p>`;
    return;
  }
  for (const x of efectesMuntatge) {
    const fila = document.createElement("div");
    fila.className = `efecte${x.actiu ? "" : " apagat"}`;
    const escolta = document.createElement("button");
    escolta.className = "icona";
    escolta.title = "Escolta aquest so";
    escolta.setAttribute("aria-label", `Escolta el so de ${x.nom}`);
    escolta.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>`;
    escolta.addEventListener("click", () => {
      const url = mostresSo?.sons?.[x.so];
      if (url) new Audio(url).play().catch(() => {});
    });
    const moment = document.createElement("button");
    moment.className = "moment";
    moment.textContent = fmt(x.t);
    moment.title = "Ves a aquest moment";
    moment.addEventListener("click", () => vesA(Math.max(0, x.t - 0.5)));
    const nom = document.createElement("span");
    nom.className = "nom-efecte";
    nom.textContent = x.nom;
    const interruptor = document.createElement("button");
    interruptor.className = "interruptor";
    interruptor.setAttribute("role", "switch");
    interruptor.setAttribute("aria-checked", String(x.actiu));
    interruptor.setAttribute("aria-label", `So de ${x.nom} al ${fmt(x.t)}`);
    interruptor.innerHTML = `<span class="pista" aria-hidden="true"><span class="bola"></span></span>`;
    interruptor.addEventListener("click", () => canvia((est) => {
      const apagats = new Set(est.sons_apagats || []);
      if (apagats.has(x.clau)) apagats.delete(x.clau); else apagats.add(x.clau);
      est.sons_apagats = [...apagats].sort();
    }));
    fila.append(escolta, moment, nom, interruptor);
    llista.append(fila);
  }
}

function canviaSo(canvis) {
  estilSo = { ...estilSo, ...canvis };
  pintaSo();
  apunta("so", canvis);
}

function instalaSo() {
  $("#s-neteja").addEventListener("click", () => canviaSo({ neteja: estilSo.neteja === false }));
  for (const [id, clau] of [["s-soroll", "soroll"], ["s-efectes", "efectes"]]) {
    for (const b of $$(`#${id} button`)) b.addEventListener("click", () => canviaSo({ [clau]: b.dataset.valor }));
  }
  $("#s-volum").addEventListener("input", (e) => canviaSo({ volum_efectes: +e.target.value }));
}

// --- La teva marca ------------------------------------------------------------------------------
// Els colors i les lletres, cadascun amb la seva feina, i com són els vídeos de la persona. La fa
// l'entrevista de marca al xat; aquí es retoca. En desar-la, el servidor l'escampa pel kit
// (subtítols, títol i b-roll) i els estils fets se'n queden els colors.

let estilMarca = null;
let editantMarca = false;
const COLORS_MARCA = [["m-color-text", "color_text"], ["m-color-principal", "color_principal"],
  ["m-color-destacat", "color_destacat"], ["m-color-secundari", "color_secundari"], ["m-color-clar", "color_clar"],
  ["m-color-fosc", "color_fosc"]];
const energies = (m) => [].concat(m?.energia || "net");  // un o uns quants estils de gràfics
const LLETRES_MARCA = [["m-lletra-titols", "lletra_titols"], ["m-lletra-text", "lletra_text"],
  ["m-lletra-accent", "lletra_accent"], ["m-lletra-ma", "lletra_ma"]];
const TEXTOS_MARCA = [["m-prohibits", "colors_prohibits"], ["m-crida", "crida"], ["m-compte", "compte"],
  ["m-public", "public"], ["m-referencia", "referencia"]];

function aplicaMarca(r) {
  if (r.paleta_grafics) { paletaGrafics = r.paleta_grafics; previaBruta = true; }
  if (!r.estil_marca) return;
  estilMarca = { ...r.estil_marca, ...pendents.marca };
  pintaPla();
  pintaResumMarca();
  pintaPanellMarca();
}

function pintaResumMarca() {
  const m = estilMarca;
  if (!m) return;
  pintaOfertaMarca();
  const colors = COLORS_MARCA.map(([, clau]) => m[clau]).filter(Boolean);
  $$("#mostra-marca i").forEach((el, k) => { el.style.background = colors[k] || ""; });
  const feta = colors.length || m.compte;
  $("#nom-marca").textContent = feta ? (m.compte || m.crida || "Colors i lletres") : "Encara no: toca aquí i fes-la en 4 passos";
}

function pintaPanellMarca() {
  const m = estilMarca;
  if (!m || $("#panell-marca").hidden) return;
  for (const [id, clau] of COLORS_MARCA) $(`#${id}`).value = (m[clau] || "#8E8E93").toLowerCase();
  for (const [id, clau] of LLETRES_MARCA) {
    if (document.activeElement !== $(`#${id}`)) ompleLletres($(`#${id}`), m[clau], { buit: "Sense triar" });
  }
  for (const [id, clau] of TEXTOS_MARCA) if (document.activeElement !== $(`#${id}`)) $(`#${id}`).value = m[clau] || "";
  const triats = energies(m);
  for (const b of $$("#m-energia button")) b.setAttribute("aria-pressed", String(triats.includes(b.dataset.valor)));
  $("#m-majuscules-ma").setAttribute("aria-checked", String(!!m.majuscules_ma));
  $("#m-majuscules-ma").disabled = !m.lletra_ma;  // sense lletra de mà, no hi ha res per posar en majúscules
  $("#m-majuscules-ma").title = m.lletra_ma ? "" : "Tria primer una lletra de mà";
  marcaSegmentat("m-grafics", m.grafics || "normal");
}

function canviaMarca(canvis) {
  estilMarca = { ...estilMarca, ...canvis };
  pintaResumMarca();
  apunta("marca", canvis);
}

function obreMarca() {
  editantMarca = true;
  $(".barra").classList.add("editant-estil");
  $("#panell-marca").hidden = false;
  $(".barra").scrollTop = 0;
  pintaPanellMarca();
  $("#tanca-marca").focus();
}

function tancaMarca() {
  editantMarca = false;
  $(".barra").classList.remove("editant-estil");
  $("#panell-marca").hidden = true;
  $("#obre-marca").focus();
}

function instalaMarca() {
  $("#obre-marca").addEventListener("click", () => (marcaFeta() ? obreMarca() : obreAssistent()));
  $("#tanca-marca").addEventListener("click", tancaMarca);
  for (const [id, clau] of COLORS_MARCA) {
    $(`#${id}`).addEventListener("input", (e) => canviaMarca({ [clau]: e.target.value.toUpperCase() }));
  }
  for (const [id, clau] of LLETRES_MARCA) {
    $(`#${id}`).addEventListener("change", (e) => {
      const v = e.target.value;
      if (v.startsWith("bib:")) baixaLletra(v.slice(4), "marca", clau);
      else { canviaMarca({ [clau]: v || null }); pintaPanellMarca(); }
    });
  }
  for (const [id, clau] of TEXTOS_MARCA) $(`#${id}`).addEventListener("input", (e) => canviaMarca({ [clau]: e.target.value }));
  $("#m-majuscules-ma").addEventListener("click", () => { canviaMarca({ majuscules_ma: !estilMarca?.majuscules_ma }); pintaPanellMarca(); });
  for (const b of $$("#m-grafics button")) b.addEventListener("click", () => { canviaMarca({ grafics: b.dataset.valor }); pintaPanellMarca(); });
  for (const b of $$("#m-energia button")) {
    b.addEventListener("click", () => {
      const triats = new Set(energies(estilMarca));
      if (triats.has(b.dataset.valor)) triats.delete(b.dataset.valor); else triats.add(b.dataset.valor);
      if (!triats.size) return;  // almenys un
      canviaMarca({ energia: [...triats] });
      pintaPanellMarca();
    });
  }
}

inicia();
