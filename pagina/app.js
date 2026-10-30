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

// Al Mac les dreceres van amb ⌘ i els fitxers es mostren al Finder; a Windows, amb Ctrl i a l'Explorador.
const ES_MAC = /Mac|iP(hone|ad|od)/.test(navigator.platform || navigator.userAgent);
const GESTOR = ES_MAC ? "al Finder" : "a l'Explorador";
// A Windows, Ctrl+Alt és AltGr (la tecla de @, € o # als teclats catalans): les dreceres de les columnes
// van amb Ctrl+Maj (revisió de Codex).
const TECLES_WINDOWS = { "⌘Z": "Ctrl+Z", "⇧⌘Z": "Ctrl+Maj+Z", "⌃⌘S": "Ctrl+Maj+E", "⌥⌘V": "Ctrl+Maj+V", "⌘B": "Ctrl+B",
  "↩": "Retorn" };
const ambAltGr = (e) => !!e.getModifierState?.("AltGraph");
const tecla = (mac) => (ES_MAC ? mac : TECLES_WINDOWS[mac] || mac);

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
let editantEstil = false;  // el panell dels subtítols és obert: el reproductor en mostra una línia d'exemple
let instruccions = [];     // instruccions de veu «Claude, …»
let zoomsTram = [];        // quins trossos porten zoom
let brollsMuntatge = [];   // b-rolls situats al muntatge: [{id, inici, durada, url}]
let stickersMuntatge = []; // stickers situats al muntatge: [{id, inici, durada, url, x, y, mida, rotacio}]
let biblioteca = { broll: [], sticker: [] };  // fitxers de ~/.tallat/broll/ i ~/.tallat/stickers/
let darrerDesplacamentManual = 0;

// --- Desar ----------------------------------------------------------------------------

let cua = Promise.resolve();
let pendent = false;
let errorDesant = null;  // si l'últim desament ha fallat (fins que un altre surti bé)
let temporitzadorSincro = null;  // un desament que espera una mica (els lliscadors d'estil: no cada pas)
function sincronitzaAviat(ms = 300) {
  clearTimeout(temporitzadorSincro);
  temporitzadorSincro = setTimeout(() => { temporitzadorSincro = null; sincronitza(); }, ms);
}
// Abans de fer res que depengui del que hi ha desat, el que esperava una mica s'envia ara. Torna la cua.
function esperaDesats() {
  if (temporitzadorSincro) sincronitza();
  return cua;
}
function sincronitza() {
  clearTimeout(temporitzadorSincro);  // aquesta petició ja ho porta tot
  temporitzadorSincro = null;
  if (pendent) return;     // diversos canvis seguits viatgen en una sola petició
  pendent = true;
  cua = cua.then(async () => {
    pendent = false;
    try {
      const r = await api("/api/estat", estat);
      errorDesant = null;
      estat.revisio = r.estat.revisio;
      aplicaTrams(r);
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
  if (temporitzadorSincro) sincronitza();
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
  if (document.hidden || !estat || temporitzadorSincro) return;  // amb canvis per enviar, primer s'envien
  const esperada = cua;
  await esperada;
  if (esperada !== cua || pendent) return;
  try {
    const n = await (await fetch("/api/novetats")).json();
    if (n.clau_projecte !== P.clau_projecte || esperada !== cua || pendent) return;
    if (n.versio_notes !== versioNotes) respostaNotes(await api("/api/notes"));
    if (n.darrer_export !== darrerExport) {
      darrerExport = n.darrer_export;
      const f = await api("/api/feina");
      pintaVersions(f.exports);
      actualitzaVersions(f.exports);
    }
    else if (n.connectat !== claudeConnectat) { claudeConnectat = n.connectat; pintaNotes(); }
    pintaEncaix(n.copia_fent);
    if (n.copia_error && n.copia_error !== errorCopiaVist) avis(n.copia_error, 6000);
    errorCopiaVist = n.copia_error;
    if (n.copia && n.copia !== P.copia) canviaCopia(n.copia);  // la còpia lleugera ara és una altra
    if (versioEstil == null) versioEstil = n.estil;
    if (n.estil !== versioEstil) {
      respostaEstil(await api("/api/marca/info"));
    }
    if (n.revisio > estat.revisio) {
      const r = await api("/api/instantania");
      if (esperada !== cua || pendent) return;
      const rondaNova = (r.estat.ronda || 0) > (estat.ronda || 0);
      estat = r.estat;
      desfer.length = 0;
      refer.length = 0;
      aplicaTrams(r);
      refresca(true);
      marcaPausa();
      if (!rondaNova) avis("Claude ha fet canvis al vídeo. Ja els veus aquí.", 4000);
      else if ($("#tauler").hidden) avis(`La ronda ${estat.ronda} és a punt: la tens a Vesteix.`, 5000);
    }
  } catch { /* el servidor no respon: ja ho dirà la propera acció */ }
}

let canvisFets = 0;  // quants canvis s'han fet aquí (una pujada que torna no ha de trepitjar els que són més nous)
function canvia(fn, { repinta = false } = {}) {
  canvisFets++;
  desfer.push(copia(estat));
  if (desfer.length > 300) desfer.shift();
  refer.length = 0;
  fn(estat);
  refresca(repinta);
  sincronitza();
}

function refresca(repinta) {
  recalculaEstils();
  if (repinta) pintaText(); else actualitzaParaules();
  pintaTitol();
  pintaVesteix();
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
  if (r.mostra_broll) mostraBroll = r.mostra_broll;  // la miniatura de com surt el b-roll (l'estil d'aquest vídeo)
  if (r.mostres_grafics) mostresGrafics = r.mostres_grafics;
  if (r.brolls) { brollsMuntatge = r.brolls; pintaResumBroll(); if (mostraBrollDespres) setTimeout(mostraBrollViu, 0); }
  if (r.grafics_dibuix) dibuixosGrafics = r.grafics_dibuix;
  if (r.grafics) { graficsMuntatge = r.grafics; previaBruta = true; }
  if (r.grafics_alternatives) graficsAlternatius = r.grafics_alternatives;
  if (r.efectes) { efectesMuntatge = r.efectes; pintaSo(); }
  if ("pista_efectes" in r) posaPistaEfectes(r.pista_efectes);
  if (r.stickers) stickersMuntatge = r.stickers;
  if (r.zoom) { zoomVideo = r.zoom; $(".pantalla").style.setProperty("--zoom", r.zoom); }
  if (r.blocs) blocsMuntatge = r.blocs;
  if (r.instruccions) { instruccions = r.instruccions; if (P) pintaInstruccions(); }
  const [tramsAbans, acumAbans] = [trams, acum];
  const canviats = JSON.stringify(r.trams) !== JSON.stringify(trams);
  // On som de la gravació, amb els talls d'abans (el vídeo continu era d'aquells talls).
  const onSom = canviats && continu() ? originalDe(tempsMuntatge(), tramsAbans, acumAbans) : null;
  trams = r.trams;
  duradaFinal = r.durada_final;
  registre("trams", { n: trams.length, primers: trams.slice(0, 3), durada: duradaFinal });
  acum = [];
  let t = 0;
  for (const [a, b] of trams) { acum.push(t); t += b - a; }
  $("#durada-final").textContent = fmt(duradaFinal);
  if (canviats) {
    previaLlesta = null;
    const sonava = vista === "directe" && (R.reproduint || R.espera);
    senseEspera = false;  // talls nous: el seu continu sí que s'espera
    if (onSom != null) passaAProxy(onSom);
    // En un vídeo llarg, refer el continu costa: s'espera que s'hagi acabat de retallar una estona.
    programaPrevia(duradaFinal > 300 ? 4000 : 600);
    // Si sonava, s'atura aquí i torna a sonar sol, sense salts, quan el continu dels talls nous és a punt.
    if (sonava && caldraEsperar()) { atura(); esperaContinu(); }
  }
  if (vista === "directe") { pintaMarques(trams, acum, duradaFinal); recolloca(); }
  if (notesCarregades) pintaNotes();
  pintaVesteix();
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
      // Un número o un símbol: l'alineador no el pot escoltar i el temps és aproximat (confianca null).
      if (P.paraules[id].confianca === null) s.classList.add("aprox");
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
  if (e.button !== 0) return;
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
  else avis(natural ? "Tot torna a sonar en l'ordre de la gravació." : `Paràgraf mogut. Prem ${tecla("⌘Z")} per desfer-ho.`);
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
      : correccio != null ? `Original: ${P.paraules[id].text}`
      : P.paraules[id].confianca === null ? "Temps aproximat: escolta-ho abans de tallar aquí" : "";
  }
  for (const { el, ids } of paragrafsEl) el.classList.toggle("tot-fora", ids.every(esFora));
}

function commuta(ids, treure) {
  passaADirecte(Math.min(...ids));
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

// Les paraules que toca la selecció normal del navegador (arrossegant, doble clic, triple clic, ⇧ + clic),
// si és dins del text; en l'ordre de la pàgina.
function idsSeleccioNativa() {
  const sel = getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return [];
  const rang = sel.getRangeAt(0);
  const cont = $("#transcripcio");
  if (!cont.contains(rang.commonAncestorContainer)) return [];
  return [...cont.querySelectorAll(".p")].filter((s) => rang.intersectsNode(s)).map((s) => +s.dataset.id);
}

function pintaSeleccio() {
  for (const id of marcades) spans.get(id)?.classList.remove("seleccio");
  marcades.clear();
  // Amb la selecció del navegador ja es veu què hi ha triat: només es pinta la paraula d'un clic.
  const ids = seleccio ? idsEntre(seleccio.inici, seleccio.fi) : seleccioNativa ? [] : seleccioFeta;
  for (const id of ids || []) { spans.get(id)?.classList.add("seleccio"); marcades.add(id); }
  pintaBarreta();
}

// --- La barreta de les paraules marcades ---------------------------------------------------------
// Sobre les paraules marcades (amb un clic o seleccionant-les), el que s'hi pot fer, amb la seva drecera:
// Destaca (⌘B, com la negreta d'un document), Corregeix (↩, com canviar el nom d'un fitxer; d'una en una)
// i Treu (⌫; si ja eren fora, Recupera). Tot al mateix lloc: no cal canviar de mode.

function claus() {
  return new Set(liniesSub.flatMap((l) => l.paraules.filter((w) => w.clau).map((w) => w.id)));
}

function pintaBarreta() {
  const b = $("#barreta");
  const ids = seleccioFeta || [];
  const editor = $("#transcripcio .editor");
  if (!ids.length && !editor) { b.hidden = true; return; }
  const totesFora = ids.length && ids.every((id) => esFora(id));
  const destacades = claus();
  $("#b-destaca").setAttribute("aria-pressed", String(ids.some((id) => !esFora(id)) &&
    ids.filter((id) => !esFora(id)).every((id) => destacades.has(id))));
  $("#b-corregeix").disabled = ids.length > 1;
  $("#b-corregeix").title = ids.length > 1 ? "Es corregeix d'una en una: marca'n només una" : "";
  $("#b-corregeix").setAttribute("aria-pressed", String(!!editor));
  $("#b-treu-text").textContent = totesFora ? "Recupera" : "Treu";
  b.hidden = false;
  colocaBarreta();
}

// A sobre de la primera paraula marcada (o a sota, si a dalt no hi cap); s'amaga si queda fora de la vista.
// «A dalt» acaba on acaba la barra d'eines (Desfés, Exporta…): a la primera línia, la tapava.
function colocaBarreta() {
  const b = $("#barreta");
  if (b.hidden) return;
  const ancora = $("#transcripcio .editor") || spans.get(seleccioFeta?.[0]);
  const text = $(".text").getBoundingClientRect();
  const r = ancora?.getBoundingClientRect();
  if (!r || !r.height || r.bottom < text.top || r.top > text.bottom) { b.style.visibility = "hidden"; return; }
  b.style.visibility = "";
  const x = Math.min(Math.max(r.left + r.width / 2 - b.offsetWidth / 2, text.left + 8), text.right - b.offsetWidth - 8);
  const sostre = Math.max(text.top, $(".eines").getBoundingClientRect().bottom - 8);
  const dalt = r.top - b.offsetHeight - 8;
  b.style.left = `${x}px`;
  b.style.top = `${dalt < sostre ? r.bottom + 8 : dalt}px`;
}

// Les paraules es queden marcades: un altre ⌫ (o «Recupera», a la barreta) les torna a posar.
function treuMarcades() {
  const ids = seleccioFeta;
  if (!ids?.length) return;
  commutaIds(ids);
  if (seleccioNativa) {  // la selecció del navegador passa a ser una marca, com la d'un clic
    seleccioNativa = false;
    getSelection().removeAllRanges();
  }
  seleccioFeta = ids;
  pintaSeleccio();
}

function corregeixMarcada() {
  if (seleccioFeta?.length !== 1) return;
  const id = seleccioFeta[0];
  if (spans.get(id)?.isConnected) editaParaula(spans.get(id), id);
}

function instalaBarreta() {
  $("#b-destaca").addEventListener("click", () => {
    const editor = $("#transcripcio .editor");
    if (editor) { editor.dispatchEvent(new KeyboardEvent("keydown", { key: "b", code: "KeyB", metaKey: ES_MAC, ctrlKey: !ES_MAC })); return; }
    if (seleccioFeta?.length) commutaDestacades(seleccioFeta);
  });
  $("#b-corregeix").addEventListener("click", corregeixMarcada);
  $("#b-treu").addEventListener("click", treuMarcades);
  // Que un clic a la barreta no desfaci la selecció del text ni tregui el focus de la correcció.
  $("#barreta").addEventListener("pointerdown", (e) => e.preventDefault());
  for (const [id, mac] of [["b-destaca", "⌘B"], ["b-corregeix", "↩"]]) $(`#${id} kbd`).textContent = tecla(mac);
  let pendent = false;
  const recoloca = () => {
    if (pendent) return;
    pendent = true;
    requestAnimationFrame(() => { pendent = false; colocaBarreta(); });
  };
  $(".text").addEventListener("scroll", recoloca, { passive: true });
  addEventListener("resize", recoloca);
}

// Com en un document de text: es selecciona com sempre (arrossegant, doble clic, triple clic, ⇧ + clic) i
// ⌫ treu les paraules (o, si ja eren fora, les torna a posar). Un clic marca la paraula i sona des d'allà.
// El clic dret (o control + clic) també les treu o les recupera; arrossegant-lo, totes les que s'hi passen.
let seleccioFeta = null;  // ids de les paraules marcades, en l'ordre de la pàgina
let seleccioNativa = false;  // si les ha triat la selecció del navegador (i no un clic)
let clicParaula = null;  // {id, x, y}: on s'ha premut, per saber si ha estat un clic o una selecció

function commutaIds(ids) {
  if (ids.length) commuta(ids, ids.some((id) => !esFora(id)));
}

function deixaSeleccio() {
  seleccio = null;
  seleccioFeta = null;
  seleccioNativa = false;
  if (idsSeleccioNativa().length) getSelection().removeAllRanges();
  pintaSeleccio();
}

function instalaText() {
  const cont = $("#transcripcio");
  cont.addEventListener("pointerdown", (e) => {
    const dret = e.button === 2 || (ES_MAC && e.button === 0 && e.ctrlKey);  // ⌃clic és el clic dret del Mac
    if (e.button !== 0 && !dret) return;
    if (e.target.closest(".nansa")) return;  // moure paràgrafs: ho fa la nansa mateixa
    if (dret) {
      // Al Mac el menú contextual surt en prémer: l'aturem a «contextmenu» i tallem en deixar anar.
      const s = e.target.closest(".p");
      if (!s) return;
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
    // La selecció la fa el navegador: aquí només s'apunta on s'ha premut (per si és un clic).
    clicParaula = s && !e.shiftKey ? { id: +s.dataset.id, x: e.clientX, y: e.clientY } : null;
    if (!seleccioNativa) { seleccioFeta = null; pintaSeleccio(); }
  });
  document.addEventListener("selectionchange", () => {
    const ids = idsSeleccioNativa();
    if (ids.length) {
      seleccioFeta = ids;
      seleccioNativa = true;
    } else if (seleccioNativa) {
      seleccioFeta = null;
      seleccioNativa = false;
    } else return;
    pintaSeleccio();
  });
  document.addEventListener("pointermove", (e) => {
    if (!seleccio) return;
    const s = document.elementFromPoint(e.clientX, e.clientY)?.closest?.(".p");
    if (s && +s.dataset.id !== seleccio.fi) { seleccio.fi = +s.dataset.id; seleccio.mogut = true; pintaSeleccio(); }
  });
  document.addEventListener("pointerup", (e) => {
    const clic = clicParaula;
    clicParaula = null;
    if (clic && !seleccio) {
      // Un clic (sense arrossegar ni seleccionar res): la paraula queda marcada i sona des d'allà.
      if (Math.hypot(e.clientX - clic.x, e.clientY - clic.y) > 4 || idsSeleccioNativa().length) return;
      seleccioFeta = [clic.id];
      seleccioNativa = false;
      pintaSeleccio();
      reprodueixDes(clic.id);
      return;
    }
    if (!seleccio) return;
    const { inici, fi } = seleccio;  // el botó dret: treu (o recupera) la paraula o les que s'hi han arrossegat
    const ids = idsEntre(inici, fi);
    deixaSeleccio();
    commutaIds(ids);
  });
  document.addEventListener("pointercancel", () => {
    clicParaula = null;
    if (seleccio) deixaSeleccio();
  });
  cont.addEventListener("contextmenu", (e) => {
    // El clic dret el fa servir «pointerdown» per tallar: aquí només amaguem el menú.
    if (e.target.closest(".p")) e.preventDefault();
  });
  document.addEventListener("keydown", (e) => {
    if (!seleccioFeta || revisant || vestint || e.target.matches?.("input, textarea, select")) return;
    if (["#full-final", "#full-marca", "#guia"].some((s) => !$(s).hidden)) return;  // hi ha una finestra a sobre
    if (e.key === "Escape") { deixaSeleccio(); return; }
    if (esDestaca(e)) { e.preventDefault(); commutaDestacades(seleccioFeta); return; }
    // ↩ (o F2, com a Windows) corregeix; si el focus és en un botó, ↩ és d'aquell botó.
    if ((e.key === "Enter" || e.key === "F2") && !e.target.closest?.("button, a, summary")) {
      e.preventDefault();
      corregeixMarcada();
      return;
    }
    if (!["Backspace", "Delete"].includes(e.key)) return;
    e.preventDefault();
    treuMarcades();
  });
  $(".text").addEventListener("wheel", () => { darrerDesplacamentManual = performance.now(); }, { passive: true });
}

// --- Paraules destacades ------------------------------------------------------------------------
// Als subtítols, algunes paraules surten més grans i d'un altre color. tallat en tria soles; amb la
// barreta (o ⌘B) se'n poden afegir o treure (i Claude també ho pot fer amb «tallat.py destaca»).

// Les destacades es veuen sempre: en negreta les que has triat tu, i una mica més gruixudes les que tria
// tallat sol (n'hi ha moltes: en negreta, el text costava de llegir).
function marcaClaus() {
  const destacades = claus();
  const teves = estat?.destacades || {};
  for (const [id, s] of spans) {
    s.classList.toggle("clau", destacades.has(id));
    s.classList.toggle("clau-teva", destacades.has(id) && teves[String(id)] === true);
  }
  pintaBarreta();
}

// ⌘B (Ctrl+B a Windows), com la negreta d'un document.
const esDestaca = (e) => e.code === "KeyB" && !e.altKey && !e.shiftKey && (ES_MAC ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey);

// Destaca les paraules (les que surten al vídeo) o, si ja ho eren totes, les deixa de destacar. Un sol pas de desfer.
function commutaDestacades(ids) {
  const dins = ids.filter((id) => !esFora(id));
  if (!dins.length) { avis(ids.length === 1 ? "Aquesta paraula no surt al vídeo." : "Aquestes paraules no surten al vídeo."); return; }
  const destacades = claus();
  const posa = !dins.every((id) => destacades.has(id));
  canvia((e) => { e.destacades = { ...(e.destacades || {}), ...Object.fromEntries(dins.map((id) => [String(id), posa])) }; });
  for (const id of dins) {  // es veu de seguida; el servidor ho confirma
    spans.get(id)?.classList.toggle("clau", posa);
    spans.get(id)?.classList.toggle("clau-teva", posa);
  }
  $("#transcripcio .editor")?.classList.toggle("clau", posa);
  $("#b-destaca").setAttribute("aria-pressed", String(posa));
  if (posa && !estilSub?.clau_grans) {
    canviaEstil({ clau_grans: true });
    avis("He activat les paraules destacades a l'estil dels subtítols.", 4000);
  } else {  // si ja ho era, ⌘B la treu: que es vegi què ha passat
    const n = dins.length === 1 ? "" : ` (${dins.length})`;
    avis(posa ? `Destacada${n}: als subtítols surt més gran.` : `Ja no surt destacada${n}.`, 2200);
  }
}

function editaParaula(s, id) {
  const entrada = document.createElement("input");
  entrada.className = s.classList.contains("clau") ? "editor clau" : "editor";
  entrada.setAttribute("aria-label", "Corregeix la paraula (↩ per desar, Esc per deixar-ho)");
  entrada.value = estat.correccions[String(id)] ?? P.paraules[id].text;
  entrada.size = Math.max(3, entrada.value.length + 1);
  s.replaceWith(entrada);
  entrada.focus();
  entrada.select();
  pintaBarreta();
  let acabat = false;
  const acaba = (desa) => {
    if (acabat) return;
    acabat = true;
    entrada.replaceWith(s);
    pintaBarreta();
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
    if (esDestaca(e)) { e.preventDefault(); commutaDestacades([id]); }
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
  if (ids.length === 1 && treure) passaADirecte(ids[0]);
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
  $("#grup-propostes").hidden = !total;
  pintaRevisar();
  const cont = $("#propostes");
  cont.textContent = "";
  if (!total) return;
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

// Dos vídeos, però només un sona: mentre s'edita, la còpia lleugera sencera, que salta de tros en tros
// (#video-a); quan el servidor té el muntatge d'aquests talls en un sol vídeo continu, aquest
// (#video-m), que sona sense salts: als salts, el Safari s'encalla uns quants dècims de segon.
// (Vam provar dos vídeos alternats a cada tall, però al Safari el segon deixava de dir per on anava.)
const R = { v: $("#video-a"), proxy: $("#video-a"), muntatge: $("#video-m"), k: 0, reproduint: false, aturaA: null,
  vigila: { t: -1, des: 0 }, rescats: null, salt: null, recarrega: null, preparant: null, posat: false, espera: false };
const continu = () => R.v === R.muntatge;
let previaLlesta = null;  // {url, trams (JSON)} quan #video-m ja té el muntatge dels talls d'ara
let esperaPrevia = null;  // el temporitzador de la petició
let previaPendent = false;  // s'està fent (o s'ha de demanar) el continu dels talls d'ara

// En quin tros del muntatge cau el temps m (amb uns talls i els seus inicis).
function trosDe(m, llista = trams, inicis = acum) {
  let k = 0;
  while (k + 1 < llista.length && inicis[k + 1] <= m + 1e-6) k++;
  return k;
}
// Temps del muntatge → temps de la gravació.
const originalDe = (m, llista = trams, inicis = acum) => {
  const k = trosDe(m, llista, inicis);
  return llista[k] ? llista[k][0] + (m - inicis[k]) : 0;
};

function mostraVideoActiu() {
  const directe = vista === "directe";
  for (const v of [R.proxy, R.muntatge]) v.classList.toggle("amagat", !directe || v !== R.v);
}

// Demana el muntatge continu dels talls d'ara (un moment després de l'últim canvi).
function programaPrevia(ms = 900) {
  previaPendent = true;
  clearTimeout(esperaPrevia);
  esperaPrevia = setTimeout(demanaPrevia, ms);
}

async function demanaPrevia() {
  if (!trams.length) { previaPendent = false; return; }
  try {
    await esperaDesats();  // primer, que el servidor tingui els canvis
    const r = await api("/api/previa", {});
    if (JSON.stringify(r.trams) !== JSON.stringify(trams)) return;  // ja hi ha hagut un altre canvi
    if (r.estat === "fent") { programaPrevia(300); return; }  // ara ja va de pressa: es pregunta sovint
    if (r.estat !== "fet") {
      if (r.error) registre("previa-error", { msg: r.error });
      previaNoArriba();
      return;
    }
    const json = JSON.stringify(r.trams);
    if (R.muntatge.dataset.url !== r.url) {
      R.muntatge.dataset.url = r.url;
      R.muntatge.src = r.url;
      // Només cal saber-ne la durada. La imatge, el Safari no la baixa d'un vídeo que no es veu fins que
      // s'hi salta o sona (esperant «loadeddata», de vegades passaven més de 20 s): el salt de passaAMuntatge
      // (o el play) ja la fa baixar.
      await new Promise((resol, falla) => {
        R.muntatge.addEventListener("loadedmetadata", resol, { once: true });
        R.muntatge.addEventListener("error", falla, { once: true });
      });
    }
    if (JSON.stringify(trams) !== json) return;
    previaLlesta = { url: r.url, trams: json };
    previaPendent = false;
    senseEspera = false;
    intentsSonant = 0;
    registre("previa", { url: r.url });
    if (R.reproduint) passaAMuntatgeSonant(); else passaAMuntatge();
  } catch (e) {
    previaNoArriba();
    registre("previa-error", { msg: String(e?.message || e) });
  }
}

// El play espera el continu: si encara es prepara, el vídeo no arrenca amb la còpia que salta. Quan el
// continu és a punt, s'hi passa amb el vídeo aturat (és quan el canvi va bé al Safari) i comença a sonar sol.
// Com a molt ESPERA_CONTINU: si encara no hi és (un vídeo molt llarg, el Mac molt carregat), sona la còpia que
// salta i, quan arribi el continu, s'hi passa mentre sona (com abans). No s'ha d'esperar mai per sempre (Codex).
const ESPERA_CONTINU = 20000;
let senseEspera = false;  // ja s'ha esperat prou per aquests talls: fins que canviïn o arribi el continu, no s'espera
const caldraEsperar = () => vista === "directe" && trams.length > 1 && !continu() && !previaAPunt() && previaPendent
  && !senseEspera;
let rellotgeEspera = null;
function esperaContinu() {
  R.espera = true;
  document.body.classList.add("reproduint");  // el botó ja diu pausa: es pot cancel·lar
  registre("espera-continu", { video: ev(R.v) });
  clearTimeout(rellotgeEspera);
  rellotgeEspera = setTimeout(() => {
    if (!R.espera) return;
    registre("espera-massa", { video: ev(R.v) });
    senseEspera = true;
    R.espera = false;
    reprodueix();
  }, ESPERA_CONTINU);
}
// Si el continu no es pot fer, sona la còpia que salta: millor amb salts que no sonar.
function previaNoArriba() {
  previaPendent = false;
  if (R.espera) { R.espera = false; reprodueix(); }
}

const previaAPunt = () => !!previaLlesta && previaLlesta.trams === JSON.stringify(trams);
let intentCanvi = 0;  // cada intent de passar al vídeo continu té el seu número: els d'abans ja no fan res

// El vídeo continu passa a ser el que es veu i sona, al punt m del muntatge. L'únic lloc on es fa el
// canvi: el que hi hagi a mig fer s'oblida i el vídeo continu sempre queda amb so.
function activaMuntatge(m) {
  intentCanvi++;
  oblidaRecarrega();
  R.preparant = null;
  intentsSonant = 0;
  const M = R.muntatge;
  M.muted = false;
  M.volume = 1;
  M.playbackRate = 1;
  R.proxy.pause();
  R.salt = null;
  R.rescats = null;
  R.repren = false;
  R.v = M;
  R.k = trosDe(m);
  R.posat = true;
  registre("continu", { m: +m.toFixed(3) });
}

// Amb el vídeo aturat: es posa al mateix punt i, quan hi és, se'n canvia (sense que es vegi el salt).
// Només a la vista en directe: a la de l'esborrany, el temps és el d'un altre vídeo.
function passaAMuntatge() {
  if (continu() || !previaAPunt() || R.reproduint || vista !== "directe") return;
  // Mai un salt a sobre d'un altre (el Safari s'hi encalla i després ja no diu per on va): primer, que acabi.
  if (R.muntatge.seeking) { R.muntatge.addEventListener("seeked", passaAMuntatge, { once: true }); return; }
  const intent = ++intentCanvi;
  R.preparant = intent;  // el continu és d'aquest intent: els d'abans ja no el poden tocar
  const m = tempsMuntatge();
  const fet = () => {
    if (intent !== intentCanvi || R.reproduint || continu() || !previaAPunt()) return;
    if (Math.abs(tempsMuntatge() - m) > 0.05) { passaAMuntatge(); return; }  // mentrestant s'ha mogut
    activaMuntatge(m);
    mostraVideoActiu();
    if (R.espera) { R.espera = false; reprodueix(); }
  };
  // Si encara no en té la imatge (el Safari), el salt la fa baixar: no es canvia fins que hi és (no es veuria res).
  if (Math.abs(R.muntatge.currentTime - m) < 0.02 && R.muntatge.readyState >= 2) { fet(); return; }
  R.muntatge.addEventListener("seeked", fet, { once: true });
  R.muntatge.currentTime = m;
}

// Mentre sona: el vídeo continu es posa una mica més endavant i comença a sonar en silenci una mica
// abans que la còpia que salta hi arribi. Llavors se n'ajusta la velocitat (en silenci no es nota) fins
// que tots dos diuen el mateix moment, i el so passa de l'un a l'altre amb un fos curt. Abans canviava
// tan bon punt arrencava, i es podien saltar o repetir fins a dues dècimes (revisió de Codex). Si
// mentrestant passa qualsevol altra cosa (s'atura, es torna a fer play, canvien els talls), l'intent
// s'oblida sense tocar res.
let intentsSonant = 0;  // intents seguits sense poder sincronitzar (el Mac va molt carregat): com a molt 3

function passaAMuntatgeSonant() {
  if (continu() || !previaAPunt() || !R.reproduint || vista !== "directe") return;
  if (intentsSonant >= 3) return;  // ja es canviarà quan s'aturi (passaAMuntatge)
  if (R.muntatge.seeking) return;  // encara salta (un salt a sobre d'un altre l'encallaria): quan s'aturi
  intentsSonant++;
  const intent = ++intentCanvi;
  R.preparant = intent;
  const M = R.muntatge;
  const objectiu = tempsMuntatge() + 0.5;
  if (objectiu >= duradaFinal - 1) return;
  const viu = () => intent === intentCanvi && R.reproduint && !continu() && previaAPunt();
  // Només desfà el que encara és d'aquest intent: un intent nou pot estar preparant el mateix vídeo, i
  // abans un d'antic l'aturava (revisió de Codex). Mai toca el vídeo que ja sona.
  const deixa = () => {
    if (R.preparant !== intent) return;
    R.preparant = null;
    if (M !== R.v) { M.pause(); M.muted = false; M.volume = 1; M.playbackRate = 1; }
    R.proxy.volume = 1;
  };
  const deNou = () => { deixa(); passaAMuntatgeSonant(); };
  M.muted = true;
  // Si el salt del continu no acaba (el Safari, de vegades), no s'espera per sempre: es torna a provar (com a molt
  // 3 cops; si no, es canvia quan s'aturi).
  setTimeout(() => {
    if (viu() && R.preparant === intent && M.seeking) { registre("salt-continu-encallat", { video: ev(M) }); deNou(); }
  }, 2500);
  M.addEventListener("seeked", () => {
    const espera = () => {
      if (!viu()) { deixa(); return; }
      const ara = tempsMuntatge();
      if (ara > objectiu) { deNou(); return; }  // s'ha passat (un salt lent): de nou
      if (ara < objectiu - 0.25) { setTimeout(espera, 15); return; }
      M.play().then(() => requestAnimationFrame(ajusta)).catch(deixa);
    };
    espera();
  }, { once: true });
  M.currentTime = objectiu;

  const t0 = performance.now();
  function ajusta() {
    if (!viu()) { deixa(); return; }
    // Mentre la còpia salta d'un tros a l'altre o es recarrega, el seu temps no és de fiar: s'espera.
    if (!R.proxy.seeking && R.salt == null && R.recarrega == null) {
      const d = M.currentTime - tempsMuntatge();  // > 0: el continu va per davant
      if (Math.abs(d) <= 0.02) {
        registre("sincronitzat", { d: +d.toFixed(3), ms: Math.round(performance.now() - t0) });
        M.playbackRate = 1;
        fon();
        return;
      }
      // Massa lluny o massa estona: no es canvia sense estar sincronitzats (es repetirien o saltarien
      // segons); es torna a provar des de més endavant.
      if (Math.abs(d) > 0.6 || performance.now() - t0 > 4000) {
        registre("no-sincronitza", { d: +d.toFixed(3), ms: Math.round(performance.now() - t0) });
        deNou();
        return;
      }
      M.playbackRate = d > 0 ? 0.85 : 1.15;
    }
    requestAnimationFrame(ajusta);
  }
  function fon() {  // 60 ms: el continu puja i la còpia baixa, i llavors ja només sona el continu
    const des = performance.now();
    M.volume = 0;
    M.muted = false;
    const pas = () => {
      if (!viu()) { deixa(); return; }
      const x = Math.min(1, (performance.now() - des) / 60);
      M.volume = x;
      R.proxy.volume = 1 - x;
      if (x < 1) { requestAnimationFrame(pas); return; }
      activaMuntatge(M.currentTime);
      R.proxy.volume = 1;
      mostraVideoActiu();
    };
    requestAnimationFrame(pas);
  }
}

// Els talls han canviat: el vídeo continu ja no hi correspon. Tornem a la còpia que salta, al mateix
// moment de la gravació, i, si sonava, continua sonant.
function passaAProxy(tOriginal) {
  intentCanvi++;  // el que hi hagués a mig fer cap al continu, s'oblida
  if (!continu()) return;
  oblidaRecarrega();
  R.muntatge.pause();
  R.salt = null;  // un salt del continu que esperava: ja no és d'aquest vídeo
  R.rescats = null;
  R.v = R.proxy;
  mostraVideoActiu();
  // El salt el fa posaTemps: si sona, continua sonant quan el salt ha acabat (no abans: el Safari s'encalla).
  vesAOriginal(tOriginal);
  registre("salts", { t: +tOriginal.toFixed(3) });
}

// El Safari s'encalla si li demanem un salt mentre encara en fa un altre (passa sobretot quan els
// paràgrafs no van en l'ordre de la gravació i cal saltar enrere o lluny). Els fem d'un en un:
// si n'hi ha un en marxa, el nou espera que acabi i només es fa l'últim que s'ha demanat.
// A més, un salt cap a un tros que encara no s'ha baixat es fa amb el vídeo aturat un instant:
// el Safari els fa bé aturat i, en canvi, sonant de vegades es queda esperant.
function posaTemps(t) {
  R.posat = true;
  if (R.recarrega != null) { R.recarrega = t; return; }  // s'hi anirà quan s'acabi de recarregar
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
const tempsVideo = () => R.recarrega ?? R.salt ?? R.v.currentTime;  // on serà el vídeo quan acabi el salt

// Si es treuen o es recuperen paraules mirant l'esborrany, es passa al muntatge en directe (és on es veu el canvi),
// aturat al tall que s'acaba de fer: si no, quedava on era el directe i calia tornar a buscar-lo (Codex).
// (Abans, a més, sonaven uns segons al voltant del tall; l'Ivet ho va treure: prenia el control a qui ho
// comprova pel seu compte.)
function passaADirecte(id) {
  if (sona() || vista === "directe") return;
  canviaVista("directe");
  if (id != null) vesAOriginal(P.paraules[id].inici);
  avis("Ara veus el muntatge en directe. L'esborrany no té aquest canvi.");
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
  if (continu()) return Math.min(tempsVideo(), duradaFinal);
  const k = Math.min(R.k, trams.length - 1);
  const [a, b] = trams[k];
  return acum[k] + limita(tempsVideo() - a, 0, b - a);
}

function durada() { return vista === "esborrany" ? (esborrany?.durada || vE.duration || 0) : duradaFinal; }

function vesA(m) {
  m = limita(m, 0, durada());
  if (vista === "esborrany") { vE.currentTime = m; return; }
  if (!trams.length) return;
  R.posat = true;
  const k = trosDe(m);
  R.k = k;
  if (continu()) {
    if (R.recarrega != null) R.recarrega = m;  // s'hi anirà quan s'acabi de recarregar
    // Arrossegant la barra arriben trenta salts per segon: si n'hi ha un en marxa, només es fa l'últim
    // quan acabi (un a sobre de l'altre encallaven el Safari: sonava, però el temps no avançava).
    else if (R.v.seeking) R.salt = m;
    else { R.salt = null; R.v.currentTime = m; }
    registre("vesA", { m: +m.toFixed(3), k, continu: true });
    return;
  }
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
  if (R.recarrega != null) return;  // el vídeo s'està recarregant: el seu temps no val
  if (!trams.length) { atura(); return; }
  if (continu()) return;
  const t = tempsVideo();
  const k = indexTram(t);
  registre("recolloca", { t: +t.toFixed(3), k, kAbans: R.k });
  if (k >= trams.length) { R.k = trams.length - 1; if (R.reproduint) atura(); return; }
  R.k = k;
  if (t < trams[k][0] - 0.01 && R.reproduint) posaTemps(trams[k][0]);
}

// El so torna a pujar en 40 ms després d'un salt de la còpia (vegeu comprovaTall).
function pujaVolum(v) {
  if (v.volume >= 1) return;
  const des = performance.now(), de = v.volume;
  const pas = () => {
    const x = Math.min(1, (performance.now() - des) / 40);
    v.volume = de + (1 - de) * x;
    if (x < 1) requestAnimationFrame(pas);
  };
  requestAnimationFrame(pas);
}

function salta() {
  const k = R.k + 1;
  if (k >= trams.length) { atura(); return; }
  registre("salta", { k, cap: trams[k][0], video: ev(R.v) });
  R.k = k;
  posaTemps(trams[k][0]);
}

function reprodueix() {
  R.proxy.volume = 1;  // si s'havia aturat enmig d'un fos
  if (vista === "esborrany") { vE.play(); return; }
  if (!trams.length) return;
  if (caldraEsperar()) { esperaContinu(); return; }
  R.espera = false;
  // El continu és a punt (i no salta encara: un salt a sobre d'un altre l'encallaria): hi passem ja.
  if (!continu() && previaAPunt() && !R.muntatge.seeking) {
    const m = R.posat && tempsMuntatge() < duradaFinal - 0.05 ? tempsMuntatge() : 0;
    activaMuntatge(m);
    if (Math.abs(R.v.currentTime - m) < 0.01) mostraVideoActiu();
    else {
      R.v.addEventListener("seeked", mostraVideoActiu, { once: true });  // es veu quan ja hi és
      R.v.currentTime = m;
    }
  }
  // Encara no s'ha posat enlloc (o ja s'ha acabat): comença pel principi del muntatge, que si els
  // paràgrafs s'han canviat d'ordre no és el principi de la gravació.
  if (!R.posat || tempsMuntatge() >= duradaFinal - 0.05) vesA(0);
  if (!continu()) {
    const t = tempsVideo();
    const k = indexTram(t);
    if (k >= trams.length) vesA(0);
    else { R.k = k; if (t < trams[k][0]) posaTemps(trams[k][0]); }
  }
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
  intentsSonant = 0;
  R.espera = false;
  if (R.reproduint) registre("atura", { k: R.k, video: ev(R.v) });
  R.repren = false;
  R.aturaA = null;
  R.reproduint = false;
  R.v.pause(); vE.pause();
  document.body.classList.remove("reproduint");
  passaAMuntatge();
}

// Recarrega el vídeo que sona i el torna al moment `objectiu` (un salt encallat que no es desencalla).
// Mentre es recarrega, el vídeo diu que és al segon 0: R.recarrega guarda on ha de ser, perquè ningú no
// es pensi que hi ha d'anar de debò (abans, el reproductor tornava a començar pel principi del muntatge).
let generacioRecarrega = 0;
function recarregaVideo(objectiu) {
  const v = R.v, gen = ++generacioRecarrega;
  R.recarrega = objectiu;
  const allibera = () => { if (gen === generacioRecarrega) R.recarrega = null; };
  setTimeout(allibera, 8000);  // si no es recarrega mai, que el reproductor no quedi aturat per sempre
  v.addEventListener("loadeddata", () => {
    // Si mentrestant s'ha canviat de vídeo, no es toca res; si s'ha navegat, R.recarrega ja diu on anar.
    if (gen !== generacioRecarrega || v !== R.v || R.recarrega == null) return;
    v.addEventListener("seeked", allibera, { once: true });
    v.currentTime = R.recarrega;
    if (R.reproduint) v.play().catch(() => {});
  }, { once: true });
  v.addEventListener("error", allibera, { once: true });
  v.load();
}
// Canviar de vídeo (de la còpia al continu o al revés) deixa sense efecte una recàrrega a mitges.
function oblidaRecarrega() {
  generacioRecarrega++;
  R.recarrega = null;
}

// Quantes vegades seguides l'hem hagut de despertar al mateix lloc. Abans, el salt encallat i el vídeo
// congelat es despertaven l'un a l'altre per torns i el comptador tornava a zero a cada torn: el Safari
// es quedava així per sempre (sonava, però el temps i els subtítols no avançaven).
function rescat() {
  const t = tempsVideo();
  if (R.rescats && Math.abs(t - R.rescats.t) < 0.3) R.rescats.n++;
  else R.rescats = { t, n: 1 };
  return R.rescats.n;
}

// Tres vegades al mateix lloc: el vídeo continu es deixa per la còpia que salta (que funciona) i es
// tornarà a carregar de nou amb el canvi següent; la còpia, es recarrega.
function rendeixte() {
  const objectiu = tempsVideo();
  R.rescats = null;
  R.vigila.salt = null;
  registre("rendeix", { continu: continu(), video: ev(R.v) });
  if (continu()) {
    previaLlesta = null;
    R.muntatge.dataset.url = "";  // la propera vista prèvia el torna a carregar sencer
    passaAProxy(originalDe(objectiu));
  } else {
    R.salt = null;
    recarregaVideo(objectiu);
    R.vigila.salt = { des: performance.now() + 3000, intents: 0 };
  }
}

// Vigilant: si el vídeo diu que sona però el seu temps no avança, o un salt no acaba mai,
// el despertem (el Safari, de vegades, es queda esperant).
function vigila() {
  if (R.v.seeking && R.reproduint) {
    R.vigila.salt ??= { des: performance.now(), intents: 0 };
    if (performance.now() - R.vigila.salt.des > 800) {
      const objectiu = tempsVideo();
      R.vigila.salt.intents++;
      registre("salt-encallat", { intents: R.vigila.salt.intents, video: ev(R.v) });
      if (rescat() >= 3) { rendeixte(); return; }
      R.salt = null;
      // El vídeo continu es recarrega de seguida: un salt a sobre del que no acaba l'encalla més.
      if (continu() || R.vigila.salt.intents >= 2) {  // la còpia: al segon intent
        recarregaVideo(objectiu);
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
  if (R.rescats && t > R.rescats.t + 0.3) R.rescats = null;  // ara sí que avança
  if (t !== R.vigila.t) { R.vigila = { t, des: performance.now() }; return; }
  if (performance.now() - R.vigila.des > 600) {
    registre("congelat", { video: ev(R.v) });
    R.vigila.des = performance.now();
    if (rescat() >= 3) { rendeixte(); return; }
    R.v.currentTime = t + 0.001;
  }
}

const sona = () => (vista === "esborrany" ? !vE.paused : R.reproduint || R.espera);  // esperant el continu, també

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
  pintaCarrega();
  R.v.classList.toggle("zoom", vista === "directe" && !!zoomsTram[Math.min(R.k, trams.length - 1)]);
}

// Si el vídeo que sona no avança durant més de 0,3 s (carrega, o un salt lent del Safari), surt la rodeta: que es
// vegi que carrega i no sembli que tallat va malament. Per sota, no (a cada tall faria pampallugues). I mentre
// sona la còpia que salta de tros en tros (just després d'un canvi), el rètol diu que es prepara la que no salta.
let carrega = { t: -1, des: 0, visible: false };
function pintaCarrega() {
  const v = vista === "esborrany" ? vE : R.v;
  const ara = performance.now();
  let encallat = false;
  const sonaDeDebo = vista === "esborrany" ? !vE.paused : R.reproduint;  // mentre espera el continu, no
  if (!sonaDeDebo || v.currentTime !== carrega.t) carrega = { ...carrega, t: v.currentTime, des: ara };
  else encallat = ara - carrega.des > 300;
  if (encallat !== carrega.visible) {
    carrega.visible = encallat;
    $("#carregant").hidden = !encallat;
  }
  // Només mentre de debò es prepara, soni o no (si no s'ha pogut fer, no). Si ja és a punt i s'ha provat
  // tres cops de canviar-hi mentre sonava, es canviarà quan s'aturi.
  const preparant = vista === "directe" && !continu() && trams.length > 1
    && (previaAPunt() ? R.reproduint && intentsSonant < 3 : previaPendent);
  if ($("#preparant").hidden === preparant) $("#preparant").hidden = !preparant;
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

// Les lletres que porta l'ordinador (les mateixes que fa servir el vídeo final, que es dibuixa en aquest ordinador).
const FONTS = ES_MAC ? [
  ["system-ui", "San Francisco (la del sistema)"], ["Avenir Next", "Avenir Next"], ["Helvetica Neue", "Helvetica Neue"],
  ["Futura", "Futura"], ["DIN Condensed", "DIN Condensed"], ["Gill Sans", "Gill Sans"], ["Impact", "Impact"],
  ["Arial Black", "Arial Black"], ["Rockwell", "Rockwell"], ["Georgia", "Georgia"],
  ["American Typewriter", "American Typewriter"], ["Marker Felt", "Marker Felt"], ["Chalkboard SE", "Chalkboard SE"],
] : [
  ["system-ui", "Segoe UI (la del sistema)"], ["Bahnschrift", "Bahnschrift"], ["Arial", "Arial"],
  ["Arial Black", "Arial Black"], ["Impact", "Impact"], ["Verdana", "Verdana"], ["Trebuchet MS", "Trebuchet MS"],
  ["Georgia", "Georgia"], ["Segoe Print", "Segoe Print"], ["Comic Sans MS", "Comic Sans MS"],
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

// Què posa cada color i cada lletra de la marca (motor/marca.py, ENLLACOS_MARCA).
const DE_LA_MARCA = {
  subtitols: { color: "color_text", contorn: "color_fosc", color_actiu: "color_destacat", clau_color: "color_destacat",
    font: "lletra_text", clau_font: "lletra_accent" },
  titol: { color: "color_text", contorn: "color_fosc", clau_color: "color_destacat", font: "lletra_titols", clau_font: "lletra_accent" },
  broll: { vora_color: "color_principal" },
};

// Els valors d'un estil fet sense el que hi posa la marca: la marca mana (el servidor l'hi posa al damunt, i triar un
// estil fet no ha de deixar els seus colors en aquest vídeo). Sense color destacat, mana el del text.
function ambMarca(seccio, valors) {
  const m = estilMarca || {};
  const v = { ...valors };
  for (const [k, rol] of Object.entries(DE_LA_MARCA[seccio] || {})) {
    const deLaMarca = rol === "color_destacat" ? m.color_destacat || m.color_text : m[rol];
    if (deLaMarca) delete v[k];
  }
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

// Les galeries es tornen a dibuixar senceres (en triar, i quan arriba la resposta del desament): si el
// focus era en una opció, torna a la mateixa (revisió de Codex: es perdia, i les fletxes movien el vídeo).
let focusGaleria = null;  // {cont, nom}
function buidaGaleria(cont) {
  const b = cont.contains(document.activeElement) ? document.activeElement.closest(".estil") : null;
  focusGaleria = b ? { cont, nom: b.dataset.nom } : null;
  cont.textContent = "";
}

// Un botó de les galeries d'estils fets (subtítols, títol i b-roll). Torna la caixa de la mostra.
function botoEstil(cont, p, actiu, tria) {
  const b = document.createElement("button");
  b.className = "estil";
  b.dataset.nom = p.nom;
  b.setAttribute("role", "radio");
  b.setAttribute("aria-checked", String(actiu));
  b.title = p.descripcio;
  b.innerHTML = `<span class="estil-mostra"></span><span class="estil-nom"></span>`;
  b.querySelector(".estil-nom").textContent = p.nom;
  b.addEventListener("click", tria);
  cont.append(b);
  if (focusGaleria?.cont === cont && focusGaleria.nom === p.nom) {
    b.focus();
    focusGaleria = null;
  }
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
// Amb `curta`, primer només les del teu estil (i les que has pujat) i «Més lletres…», que obre la llista sencera.
function ompleLletres(select, valor, { laDelsSubtitols = false, buit = null, curta = false } = {}) {
  select._omple = () => ompleLletres(select, valor, { laDelsSubtitols, buit, curta });
  select.textContent = "";
  const grup = (nom) => { const g = document.createElement("optgroup"); g.label = nom; select.append(g); return g; };
  const opcio = (on, v, text) => { const o = document.createElement("option"); o.value = v; o.textContent = text; on.append(o); };
  if (buit) opcio(select, "", buit);
  if (laDelsSubtitols) opcio(select, "", `La dels subtítols (${estilSub?.font === "system-ui" ? "San Francisco" : estilSub?.font || ""})`);
  const alKit = new Set(fontsKit.map((f) => f.familia));
  const deLaBiblioteca = new Set(bibliotecaLletres.lletres.map((l) => l.nom));
  const meves = [...alKit].filter((f) => !deLaBiblioteca.has(f));
  const delEstil = [...new Set(["lletra_titols", "lletra_text", "lletra_accent", "lletra_ma"]
    .map((c) => estilMarca?.[c]).filter(Boolean).concat(meves))];
  if (curta && delEstil.length && select.dataset.totes !== "1") {
    const g = grup("Les del teu estil");
    for (const f of delEstil) {
      const l = bibliotecaLletres.lletres.find((x) => x.nom === f || x.id === f);
      opcio(g, l && !alKit.has(l.nom) ? `bib:${l.id}` : l?.nom || f, l?.nom || f);
    }
    if (valor && ![...select.options].some((o) => o.value === valor)) opcio(select, valor, FONTS.find(([v]) => v === valor)?.[1] || valor);
    opcio(select, "__mes__", "Més lletres…");
    select.value = valor || "";
    return;
  }
  if (meves.length) { const g = grup("Les teves"); for (const f of meves) opcio(g, f, f); }
  const delSistema = grup(ES_MAC ? "Del Mac" : "De Windows");
  for (const [v, text] of FONTS) opcio(delSistema, v, text);
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

// «Més lletres…»: la llista sencera, al mateix desplegable (abans que ho sàpiguen els altres «change»).
document.addEventListener("change", (e) => {
  const select = e.target;
  if (!(select instanceof HTMLSelectElement) || select.value !== "__mes__") return;
  e.stopImmediatePropagation();
  select.dataset.totes = "1";
  select._omple?.();
  try { select.showPicker?.(); } catch { /* el Safari no el té: es torna a clicar */ }
}, true);

function marcaSegmentat(id, valor) {
  for (const b of $$(`#${id} button`)) b.setAttribute("aria-checked", String(b.dataset.valor === valor));
}

let estilsMostrats = false;  // «Més estils» desplegat
function pintaPanellEstil() {
  const e = estilSub;
  pintaResumSub();
  if (!e || $("#panell-estil").hidden) return;
  const actual = predefinitActual();
  const cont = $("#estils");
  buidaGaleria(cont);
  // Plegats, es veuen els 6 primers; si el triat és dels de més avall, ocupa el sisè lloc.
  const ordre = [...estilsPredefinits];
  if (!estilsMostrats && ordre.indexOf(actual) >= 6) ordre.splice(5, 0, ...ordre.splice(ordre.indexOf(actual), 1));
  for (const p of ordre) {
    const valors = ambMarca("subtitols", p.valors);
    const mostra = botoEstil(cont, p, p === actual, () => canviaEstil(valors, true));
    if (window.TallatSubtitols) {
      const v = { ...e, ...valors };
      const n = v.paraules_per_linia <= 1 ? 1 : v.paraules_per_linia <= 4 ? 3 : 4;
      pintaMostra(mostra, v,
        { paraules: n === 1 ? [MOSTRA[2]] : MOSTRA.slice(0, n), alcada: 675, mida: Math.min(0.2, v.mida * 1.6) });
    }
  }
  const tots = estilsMostrats;
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

  ompleLletres($("#e-font"), e.font, { curta: true });
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
  ompleLletres($("#e-clau-font"), e.clau_font, { buit: "La mateixa", curta: true });
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
}

// --- Desar l'estil ------------------------------------------------------------------------------
// Cada canvi d'estil (subtítols, títol, b-roll o so) es veu a l'instant i es desa al cap d'un moment,
// tots junts (els lliscadors n'envien molts), a la cua de peticions. Cada petició diu a quin kit va:
// si mentrestant el vídeo ha canviat de kit, el servidor no la desa en un altre.
const pendents = { subtitols: {}, titol: {}, broll: {}, so: {}, marca: {} };
let temporitzadorDesa = null;

// --- L'estil de cada vídeo ---
// Els subtítols, el títol, el b-roll i el so: el kit diu com són a tots els vídeos d'aquell estil, i cada vídeo hi
// canvia el que vulgui (l'estat, «estil»: es desfà amb ⌘Z i no toca els altres vídeos). «Fes-lo servir en tots els
// vídeos» ho passa al kit. Els colors i les lletres (la marca) són sempre del kit (motor/marca.py, amb_estil_video).
const SECCIONS_VIDEO = ["subtitols", "titol", "broll", "so"];
const kitEstil = { subtitols: null, titol: null, broll: null, so: null };  // com són al kit (el de tots els vídeos)
const propiDe = (seccio) => estat?.estil?.[seccio] || {};
const ambVideo = (seccio) => kitEstil[seccio] && { ...kitEstil[seccio], ...propiDe(seccio) };
let signaturaEstils = "";

// Torna a calcular l'estil de cada secció (el del kit amb el del vídeo) si ha canviat: desfer, Claude, un altre kit…
function recalculaEstils() {
  if (!kitEstil.subtitols || !estat) return;  // encara no ha arribat l'estil
  const sig = JSON.stringify([kitEstil, estat?.estil]);
  if (sig === signaturaEstils) return;
  signaturaEstils = sig;
  if (kitEstil.subtitols) aplicaEstilSubtitols(ambVideo("subtitols"));
  if (kitEstil.titol) aplicaEstilTitol(ambVideo("titol"));
  if (kitEstil.broll) { estilBroll = ambVideo("broll"); pintaResumBroll(); pintaPanellBroll(); }
  if (kitEstil.so) { estilSo = ambVideo("so"); pintaSo(); }
  for (const [id, seccio] of [["#restableix-estil", "subtitols"], ["#restableix-titol", "titol"], ["#restableix-broll", "broll"]]) {
    $(id).hidden = !Object.keys(propiDe(seccio)).length;
  }
  pintaPanellEstil();
  pintaPanellTitol();
  pintaResumEstilVideo();
  if (!$("#full-estil").hidden) pintaEstilsVideo();
}

// Un canvi d'estil d'aquest vídeo. Els canvis seguits de la mateixa opció (un lliscador) són un sol pas per desfer.
let darrerCanviEstil = { clau: "", t: 0 };
function canviaEstilVideo(seccio, canvis) {
  const clau = `${seccio}:${Object.keys(canvis).sort().join(",")}`;
  const ara = performance.now();
  if (clau !== darrerCanviEstil.clau || ara - darrerCanviEstil.t > 900) {
    desfer.push(copia(estat));
    if (desfer.length > 300) desfer.shift();
    refer.length = 0;
  }
  darrerCanviEstil = { clau, t: ara };
  estat.estil = { ...(estat.estil || {}), [seccio]: { ...propiDe(seccio), ...canvis } };
  recalculaEstils();
  for (const b of $$("#desfes, [data-desfes]")) b.disabled = !desfer.length;
  for (const b of $$("#refes, [data-refes]")) b.disabled = !refer.length;
  pintaVesteix();
  sincronitzaAviat();  // un lliscador envia molts canvis seguits: s'envia l'últim
}

function apunta(seccio, canvis) {
  if (SECCIONS_VIDEO.includes(seccio)) { canviaEstilVideo(seccio, canvis); return; }
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

// Torna una secció a l'estil de tallat (el que hi hagués pendent d'aquella secció, fora). Les d'un vídeo, a l'estil
// del kit (el dels altres vídeos): se'n treu el que aquest vídeo hi havia canviat.
async function restableix(seccio, missatge) {
  if (SECCIONS_VIDEO.includes(seccio)) {
    canvia((e) => { const x = { ...(e.estil || {}) }; delete x[seccio]; e.estil = x; });
    avis("Ha tornat a l'estil dels altres vídeos.");
    return;
  }
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
  if (r.estils_video) estilsVideo = r.estils_video;
  aplicaMarca(r);
  aplicaBroll(r);
  aplicaSo(r);
  if (r.estil_subtitols) kitEstil.subtitols = r.estil_subtitols;
  if (r.estil_titol) kitEstil.titol = r.estil_titol;
  recalculaEstils();
  pintaPanellEstil();
  pintaPanellTitol();
}

function aplicaSo(r) {
  if (r.estil_so) { kitEstil.so = r.estil_so; signaturaEstils = ""; recalculaEstils(); }
}

function aplicaBroll(r) {
  if (r.estil_broll) { kitEstil.broll = r.estil_broll; signaturaEstils = ""; recalculaEstils(); }
  if (r.estils_broll) estilsBroll = r.estils_broll;
  if (r.mostra_broll) mostraBroll = r.mostra_broll;
  pintaResumBroll();
  pintaPanellBroll();

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

// Ensenya el títol sense fer sonar res: si ara no es veu, el vídeo hi va (aturat), amb el títol ja entrat.
function mostraTitol() {
  if (vista !== "directe" || sona() || !titolMuntatge) return;
  const m = tempsMuntatge();
  if (m >= titolMuntatge.inici && m < titolMuntatge.final) return;
  vesA(Math.max(titolMuntatge.inici, Math.min(titolMuntatge.final - 0.35, titolMuntatge.inici + 1.2)));
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
  $("#nom-estil-titol").textContent = primera ? `«${primera}»` : "Sense títol";
}

function pintaPanellTitol() {
  const e = estilTitol;
  if (!e || $("#panell-titol").hidden) return;
  const actual = predefinitTitol();
  const cont = $("#estils-titol");
  buidaGaleria(cont);
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
  ompleLletres($("#t-font"), e.font, { laDelsSubtitols: true, curta: true });
  const pes = $("#t-pes");
  if (![...pes.options].some((o) => +o.value === +e.pes)) {
    const o = document.createElement("option"); o.value = e.pes; o.textContent = `Gruix ${e.pes}`; pes.append(o);
  }
  pes.value = String(e.pes);
  $("#t-majuscules").setAttribute("aria-checked", String(!!e.majuscules));
  ompleLletres($("#t-clau-font"), e.clau_font, { buit: "La mateixa", curta: true });
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
  tancaElQueHiHagi();
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
  $("#obre-estil-titol").addEventListener("click", () => obreALaDreta("titol"));
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

// --- La columna de l'esquerra: l'inici i els panells --------------------------------------------
// A l'inici, què queda al vídeo (reels, instruccions de veu, propostes i silencis) i, a Vesteix, «Tot el vídeo»: una
// fila per panell (l'estil, els subtítols, el títol, el b-roll i el so), amb el que hi ha
// triat. Un panell s'obre al lloc de l'inici i «‹ Enrere» (o Esc) hi torna; mai n'hi ha dos d'oberts.

function tancaElQueHiHagi() {
  if (editantMarca) tancaMarca();
  if (editantTitol) tancaTitol();
  if (editantBroll) tancaBroll();
  if (editantEstil) tancaSubtitols();
  for (const id of ["estils", "so"]) $(`#panell-${id}`).hidden = true;
  $(".barra").classList.remove("editant-estil");
}

// Els panells que no canvien què ensenya el reproductor: la llista d'estils, els gràfics i el so.
function obrePanell(id) {
  tancaElQueHiHagi();
  $(".barra").classList.add("editant-estil");
  $(`#panell-${id}`).hidden = false;
  $(".barra").scrollTop = 0;
  $(`#tanca-${id}`).focus();
}

function tancaPanell(id) {
  $(".barra").classList.remove("editant-estil");
  $(`#panell-${id}`).hidden = true;
  $(`#obre-${id}`).focus();
}

function obreEstils() {
  obrePanell("estils");
  pintaKits();
}

function obreSo() {
  obrePanell("so");
  pintaSo();
}

function obreSubtitols() {
  tancaElQueHiHagi();
  editantEstil = true;
  previaBruta = true;
  previaTemps = NaN;
  if (vista !== "directe") canviaVista("directe");
  $(".barra").classList.add("editant-estil");
  $("#panell-estil").hidden = false;
  $(".barra").scrollTop = 0;
  pintaPanellEstil();
  $("#tanca-subtitols").focus();
}

function tancaSubtitols() {
  editantEstil = false;
  previaBruta = true;
  previaTemps = NaN;
  $(".barra").classList.remove("editant-estil");
  $("#panell-estil").hidden = true;
  $("#obre-subtitols").focus();
}

// Del panell d'un estil, a la llista d'estils; de la resta, a l'inici. False si no n'hi havia cap d'obert.
function tornaEnrere() {
  if (editantMarca) { tancaMarca(); return true; }
  if (!$("#panell-estils").hidden) { tancaPanell("estils"); obreMarca(); return true; }
  if (editantTitol) { tancaTitol(); return true; }
  if (editantBroll) { tancaBroll(); return true; }
  if (editantEstil) { tancaSubtitols(); return true; }
  const obert = ["so"].find((id) => !$(`#panell-${id}`).hidden);
  if (obert) tancaPanell(obert);
  return !!obert;
}

function pintaResumSub() {
  if (!estat) return;
  // Com són, en paraules (l'estil de tot el vídeo ja es diu a la fila «Estil»).
  const e = estilSub || {};
  const quantes = { una: "D'una en una", poques: "Dues o tres", frase: "La frase" }[agrupacioDe(e)];
  const on = { dalt: "a dalt", mig: "al mig", baix: "a baix" }[mesProper(LLOCS_SUB, e.posicio_y, 0.12)] || "";
  $("#nom-estil-sub").textContent = estat.subtitols === false ? "Sense subtítols" : [quantes, on].filter(Boolean).join(", ");
}

function instalaColumna() {
  $("#obre-estils").addEventListener("click", obreMarca);  // «Colors i lletres»: els del kit d'aquest vídeo
  $("#obre-guardats").addEventListener("click", () => { tancaMarca(); obreEstils(); });
  $("#tanca-estils").addEventListener("click", () => { tancaPanell("estils"); obreMarca(); });
  $("#obre-subtitols").addEventListener("click", () => obreALaDreta("subtitols"));
  $("#obre-estil-video").addEventListener("click", obreEstilVideo);
  $("#tanca-estil-video").addEventListener("click", tancaEstilVideo);
  $("#tanca-subtitols").addEventListener("click", tancaSubtitols);
  $("#obre-so").addEventListener("click", obreSo);
  $("#tanca-so").addEventListener("click", () => tancaPanell("so"));
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
  const llista = $("#llista-kits");
  llista.textContent = "";
  for (const k of kits) {
    const actual = k.id === kitActual;
    const b = document.createElement("button");
    b.className = "fila-estil";
    const mostra = document.createElement("span");
    mostra.className = `mostra-estil mostra-marca${actual ? " mostra-actual" : ""}`;
    mostra.setAttribute("aria-hidden", "true");
    for (let n = 0; n < 4; n++) {
      const color = document.createElement("i");
      color.style.background = k.colors?.[n] || "";
      mostra.append(color);
    }
    const text = document.createElement("span");
    text.className = "fila-estil-text";
    const nom = document.createElement("strong");
    nom.textContent = k.nom;
    const detall = document.createElement("span");
    detall.textContent = [actual && "En aquest vídeo", k.per_defecte && "Per defecte"].filter(Boolean).join(" · ");
    text.append(nom, detall);
    b.append(mostra, text);
    if (actual) b.insertAdjacentHTML("beforeend", '<svg class="marca-actual" viewBox="0 0 20 20" aria-hidden="true"><path d="m4.5 10.5 3.5 3.5 7.5-8"/></svg>');
    b.insertAdjacentHTML("beforeend", '<svg class="xebro" viewBox="0 0 20 20" aria-hidden="true"><path d="m8 5 5 5-5 5"/></svg>');
    b.classList.toggle("actual", actual);
    b.setAttribute("aria-label", `${k.nom}${actual ? ", el d'aquest vídeo" : ""}`);
    b.addEventListener("click", () => obreKit(k));
    llista.append(b);
  }
  const actual = kits.find((k) => k.id === kitActual);
  $("#kit-defecte").hidden = !!actual?.per_defecte;
  $("#kit-esborra").hidden = !!actual?.per_defecte;
  pintaResumMarca();
}

// Tocar un estil: el fa servir aquest vídeo (si no el feia servir ja) i l'obre. Només es pot canviar
// l'estil del vídeo; per tornar al d'abans, es toca aquell. Si encara no té colors, el panell ofereix
// l'assistent dels 2 passos, però s'obre igualment (revisió de Codex: si no, no es podia gestionar).
async function obreKit(k) {
  if (k.id !== kitActual) {
    await accioKit("/api/kit/tria", { kit: k.id }, `Aquest vídeo ara fa servir l'estil «${k.nom}».`);
    if (k.id !== kitActual) return;  // no s'ha pogut canviar (ja ho ha dit l'avís)
  }
  obreMarca();
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
  camp.placeholder = accio === "nou" ? "Nom de l'estil nou" : "Nom de l'estil";
  $(`#kit-${accio}`).closest(".accions-kit").after($("#form-kit"));
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
    respostaKit(json, "Estil importat. Aquest vídeo ja el fa servir.");
  } catch (e) { avis(e.message, 6000); }
}

function instalaKits() {
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
        `Estil «${nom}» creat${duplica ? "" : " (el de tallat)"}. Aquest vídeo ja el fa servir.`);
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
    avis("L'estil es baixa en un .zip. Si porta una lletra teva, comprova que la pots compartir.", 5000);
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
    tancaMarca();
    obreEstils();
    accioKit("/api/kit/esborra", { kit: kitActual }, "Estil tret. Aquest vídeo torna a fer servir el per defecte.");
  });
}

// Ensenya el canvi sense fer sonar res (el vídeo no arrenca sol, com tampoc ho fa l'antic «Escolta cada tall»): si
// ara no es veu cap línia de subtítols, el vídeo va (aturat) a la següent, ja entrada.
function mostraAnimacio() {
  if (vista !== "directe" || sona() || !liniesSub.length) return;
  const m = tempsMuntatge();
  if (liniesSub.some((l) => m >= l.inici && m < l.final)) return;
  const linia = liniesSub.find((l) => l.final > m + 0.05) || liniesSub[0];
  vesA(Math.min(linia.final - 0.05, linia.inici + 0.6));
}

// Una lletra gratuïta de la biblioteca: el servidor la baixa al kit (el primer cop) i la fa servir.
async function baixaLletra(id, seccio = "subtitols", clau = "font") {
  const nom = bibliotecaLletres.lletres.find((l) => l.id === id)?.nom || id;
  avis(`Baixant la lletra «${nom}»…`, 20000);
  if (SECCIONS_VIDEO.includes(seccio)) {  // es baixa a les lletres del kit, i la fa servir aquest vídeo
    try {
      const r = await api("/api/marca/lletra", { id, nomes_baixa: true, kit: kitActual });
      respostaEstil(r);
      apunta(seccio, { [clau]: r.familia, ...(seccio === "subtitols" && clau === "font" ? { font_fitxer: null } : {}) });
      avis(`Lletra «${nom}» posada.`);
    } catch (e) {
      avis(e.message, 6000);
    }
    pintaPanellEstil();
    pintaPanellTitol();
    return;
  }
  try {
    await desaEstils();
    respostaEstil(await api("/api/marca/lletra", { id, seccio, clau, kit: kitActual }));
    avis(`Lletra «${nom}» afegida al teu estil.`);
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

// Entre 701 i 1100 px, la columna de l'esquerra d'Edita és un calaix (estil.css): el botó l'obre i el tanca, sense
// amagar-la per a quan la finestra torni a ser ampla.
const ESTRETA = matchMedia("(max-width: 1100px) and (min-width: 701px)");
const ambCalaix = () => ESTRETA.matches && !vestint && !revisant;

function obreCalaix(obert) {
  document.body.classList.toggle("calaix-obert", obert);
  $("#commuta-barra").setAttribute("aria-pressed", String(obert));
  $("#commuta-barra").title = obert ? "Tanca la columna de l'esquerra" : "Obre la columna de l'esquerra (el ritme i el que t'ha proposat tallat)";
}

function mostraColumna(nom, visible) {
  const c = COLUMNES[nom];
  if (nom === "barra" && ambCalaix()) { obreCalaix(visible); return; }
  document.body.classList.toggle(c.classe, !visible);
  $(c.boto).setAttribute("aria-pressed", String(visible));
  $(c.boto).title = (visible ? "Amaga " : "Mostra ") +
    (nom === "barra" ? `la columna de l'esquerra (${tecla("⌃⌘S")})` : `el vídeo (${tecla("⌥⌘V")})`);
  desa(`tallat.amaga.${nom}`, !visible);
  if (nom === "reproductor" && visible) notesTornenASortir();
}

function instalaColumnes() {
  for (const [nom, c] of Object.entries(COLUMNES)) {
    const amplada = llegeix(`tallat.amplada.${nom}`, null);
    if (amplada) posaAmplada(nom, amplada);
    mostraColumna(nom, !llegeix(`tallat.amaga.${nom}`, false));
    $(c.boto).addEventListener("click", () => mostraColumna(nom, nom === "barra" && ambCalaix()
      ? !document.body.classList.contains("calaix-obert") : document.body.classList.contains(c.classe)));

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
  // En canviar de mida (o d'estació), el calaix es tanca i el botó torna a dir si la columna es veu.
  const canviaMida = () => {
    document.body.classList.remove("calaix-obert");
    if (ambCalaix()) obreCalaix(false);
    else mostraColumna("barra", !llegeix("tallat.amaga.barra", false));
  };
  ESTRETA.addEventListener("change", canviaMida);
  canviaMida();
  // Amb el calaix obert, tocar fora (el text o el vídeo) o Esc el tanquen.
  document.addEventListener("pointerdown", (e) => {
    if (document.body.classList.contains("calaix-obert") && !e.target.closest(".barra, #commuta-barra, .full, .velo")) obreCalaix(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.body.classList.contains("calaix-obert") && !$(".barra").classList.contains("editant-estil")) {
      obreCalaix(false);
    }
  });
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
    if (!h2) continue;  // el kit, a dalt: sense títol ni plegar
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

  $("#mes-estils").addEventListener("click", () => { estilsMostrats = !estilsMostrats; pintaPanellEstil(); });
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
  if (vista === "directe" && continu()) {  // el vídeo continu no salta: només cal saber on som
    R.k = trosDe(tempsMuntatge());
    if (R.reproduint && (R.v.ended || R.v.currentTime >= duradaFinal - 0.02)) atura();
    return;
  }
  if (vista === "directe" && R.reproduint && trams.length && !R.v.seeking && R.salt == null && R.recarrega == null) {
    const t = R.v.currentTime;
    const [a, b] = trams[Math.min(R.k, trams.length - 1)];
    // Passat el final del tros, sempre al següent del muntatge, encara que el navegador hagi anat
    // tard: buscar per temps de la gravació s'hi saltaria els trossos que s'han mogut més amunt.
    // Just abans del salt el so baixa (i després del salt torna a pujar, pujaVolum): sense aquest fos,
    // a cada tall de la còpia que salta se sentia un clic.
    if (t >= b - 0.03) salta();
    else if (t < a - 0.3) recolloca();
    else if (t >= b - 0.07) R.v.volume = limita((b - 0.03 - t) / 0.04, 0, 1);
  }
}

// El segon de la gravació que es veu ara (al muntatge o a l'esborrany).
function tempsOriginalAra() {
  if (vista === "directe") return continu() ? originalDe(tempsMuntatge()) : tempsVideo();
  if (!esborrany?.trams) return null;
  const m = vE.currentTime;
  let k = 0;
  while (k + 1 < esborrany.trams.length && esborrany.acum[k + 1] <= m) k++;
  return esborrany.trams[k] ? esborrany.trams[k][0] + (m - esborrany.acum[k]) : null;
}

// L'última paraula que comença abans del segon t de la gravació (-1 si encara no n'ha començat cap).
function paraulaAbans(t) {
  let lo = 0, hi = P.paraules.length - 1;
  while (lo <= hi) {
    const mig = (lo + hi) >> 1;
    if (P.paraules[mig].inici <= t) lo = mig + 1; else hi = mig - 1;
  }
  return hi;
}

let paraulaMarcada = null;
function paraulaActual() {
  const t = tempsOriginalAra();
  let id = null;
  if (t != null) {
    const hi = paraulaAbans(t);
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
  if (!momentNota) $("#temps-nota").textContent = fmt(m);
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
  R.proxy.src = urlCopia();
  for (const v of [R.proxy, R.muntatge]) {
    for (const nom of ["play", "pause", "seeking", "seeked", "waiting", "stalled", "error", "ended"]) {
      v.addEventListener(nom, () => registre("v-" + nom, ev(v)));
    }
    v.addEventListener("timeupdate", () => { if (v === R.v) comprovaTall(); });
  }
  R.proxy.addEventListener("error", () => avis("No puc obrir la còpia lleugera del vídeo (proxy.mp4)."));
  // Si el vídeo continu falla, es continua amb la còpia que salta.
  R.muntatge.addEventListener("error", () => {
    registre("continu-error", { codi: R.muntatge.error?.code, video: ev(R.muntatge) });
    previaLlesta = null;
    if (continu()) passaAProxy(originalDe(tempsMuntatge()));
  });
  // El salt del vídeo continu que esperava que acabés l'anterior (vegeu vesA).
  R.muntatge.addEventListener("seeked", () => {
    if (!continu() || R.salt == null || R.recarrega != null) return;
    const m = R.salt;
    R.salt = null;
    R.muntatge.currentTime = m;
  });
  // Si la pàgina deixa de veure's, el navegador alenteix els salts: parem perquè no soni el que s'ha tret.
  document.addEventListener("visibilitychange", () => { if (document.hidden && sona()) atura(); });
  // Primer salt quan ja hi ha dades (no només la informació general): el Safari ho agraeix.
  R.proxy.addEventListener("loadeddata", () => { if (!R.posat) vesA(0); pintaTemps(); programaPrevia(0); }, { once: true });
  R.proxy.addEventListener("seeked", () => {
    if (continu()) return;  // els salts són de la còpia lleugera
    pujaVolum(R.proxy);
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
  mostraVideoActiu();
  vE.classList.toggle("amagat", directe);
  if (directe) { pintaMarques(trams, acum, duradaFinal); passaAMuntatge(); }
  else if (esborrany) pintaMarques(esborrany.trams || [], esborrany.acum || [], esborrany.durada);
  pintaMarquesNotes();
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
  $("#vista").hidden = false;  // fins que no hi ha cap esborrany, no cal triar què veus
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
  $("#seccio-versions").hidden = !exports.length;
  if (!exports.length) return;
  for (const x of exports) {
    const item = document.createElement("div");
    item.className = "item";
    item.innerHTML = `<span class="context"><b style="color:var(--text)">${QUALITATS[x.qualitat] || "Vídeo"}</b> · ${x.data} · ${x.mida_mb} MB</span>
      <button class="mini" title="Mira-la" aria-label="Mira-la">${ICONES.play}</button>
      <button class="mini" title="Mostra-la ${GESTOR}" aria-label="Mostra-la ${GESTOR}">${ICONES.finder}</button>`;
    const [mira, finder] = item.querySelectorAll(".mini");
    mira.addEventListener("click", (e) => { e.stopPropagation(); tancaFinal(); carregaVersio(x.nom); });
    finder.addEventListener("click", (e) => { e.stopPropagation(); api("/api/mostra", { nom: x.nom }).catch((err) => avis(err.message)); });
    item.addEventListener("click", () => { tancaFinal(); carregaVersio(x.nom); });
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
  $("#final").disabled = ocupat;
  caixa.hidden = !ocupat;
  $("#revisa-feina").hidden = !ocupat;
  $("#vesteix-feina").hidden = !ocupat;
  $("#tauler-feina").hidden = !ocupat;
  for (const b of [$("#nova-versio"), $("#primera-versio"), $("#vesteix-exporta"), $("#tauler-exporta"), $("#ja-esta")]) {
    b.disabled = ocupat;
  }
  if (ocupat) {
    const nom = feina.qualitat === "esborrany" ? "Construint l'esborrany"
      : feina.qualitat === "editors" ? "Exportant els trossos" : `Exportant en ${QUALITATS[feina.qualitat]}`;
    if (feina.fase === "editors") {
      $("#feina-text").textContent = "Preparant el projecte per a altres editors…";
      $("#feina-progres").style.width = "50%";
    } else if (feina.fase === "subtitols") {
      $("#feina-text").textContent = "Dibuixant els subtítols…";
      $("#feina-progres").style.width = "12%";
    } else if (feina.fase === "fons") {
      $("#feina-text").textContent = `Fent el fons difuminat… ${feina.progres} %`;
      $("#feina-progres").style.width = `${feina.progres}%`;
    } else {
      $("#feina-text").textContent = `${nom}… ${feina.progres} %`;
      $("#feina-progres").style.width = `${feina.progres}%`;
    }
    for (const lloc of ["revisa", "vesteix", "tauler"]) {
      $(`#${lloc}-feina-text`).textContent = $("#feina-text").textContent;
      $(`#${lloc}-feina-progres`).style.width = $("#feina-progres").style.width;
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
      if (feina.avis) setTimeout(() => avis(feina.avis, 8000), 6500);  // després de l'avís de «fet»
      pintaVersions(r.exports);
      pintaCarpeta(r);
      if (feina.qualitat === "editors") {
        mostraFet(feina, "Projecte per a altres editors a punt (hi ha un LLEGEIX-ME amb els passos)");
        mostraAlFinder(feina);
      } else if (feina.qualitat === "esborrany") {
        darrerExport = r.exports[0]?.nom ?? darrerExport;
        actualitzaVersions(r.exports);
        if (!revisant) {
          avis(`L'esborrany és a punt${feina.copia ? " (també a la teva carpeta)" : ""}. Mira'l i digues a Claude què vols canviar (amb el segon, que veus sota el vídeo).`, 6000);
          carregaVersio(feina.fitxer);
        }
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
  // El nom de la carpeta (el camí sencer, en passar-hi el ratolí).
  $("#final-carpeta").textContent = `Es desa a «${r.carpeta_exports.split("/").filter(Boolean).pop()}»`;
  $("#final-carpeta").title = r.carpeta_exports + (r.carpeta_propia ? " (i també a la carpeta del projecte)" : "");
  $("#carpeta-projecte").hidden = !r.carpeta_propia;
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

// Un vídeo horitzontal entra al vertical retallat (el centre) o sencer, amb el fons difuminat. Si es canvia, el
// servidor refà la còpia lleugera (amb l'enquadrament nou) i la pàgina es torna a carregar quan és a punt.
const esHoritzontal = () => { const o = P?.origen || {}; return !!o.amplada && o.amplada * 16 > o.alcada * 9; };
let errorCopiaVist = null;
function pintaEncaix(fent = false) {
  $("#fila-encaix").hidden = !esHoritzontal();
  for (const b of $$("#encaix button")) b.setAttribute("aria-checked", String(b.dataset.encaix === (estat?.encaix || "retalla")));
  $("#encaix-fent").hidden = !fent;
}

// La còpia lleugera que serveix el servidor, amb la seva versió a l'adreça (si canvia, el navegador no se'n queda
// l'antiga). Quan n'arriba una de nova, el vídeo i les targetes la fan servir sense tornar a carregar la pàgina.
const urlCopia = () => `/proxy.mp4?v=${encodeURIComponent(P?.copia || "")}`;
function canviaCopia(versio) {
  P.copia = versio;
  const v = R.proxy;
  const [t, sonava] = [v.currentTime, !v.paused];
  v.src = urlCopia();
  v.addEventListener("loadedmetadata", () => {
    v.currentTime = t;
    if (sonava) v.play().catch(() => {});
  }, { once: true });
  aturaCarta();
  for (const c of cartesTauler.values()) c.sig = "";  // es tornen a fer amb els fotogrames nous
  previaLlesta = null;
  programaPrevia(0);
  if (vestint) pintaTauler();
  avis("Ja tens el vídeo enquadrat de la manera nova.", 3500);
}

function obreFinal() {
  const o = P.origen || {};
  $("#fet-export").hidden = true;
  $("#final-durada").textContent = fmt(duradaFinal);
  const avisFinal = $("#final-avis");
  if (esHoritzontal()) {
    const ample = Math.round((o.alcada * 9) / 16);
    avisFinal.textContent = (estat.encaix === "difumina"
      ? "La gravació és horitzontal: surt sencera, al mig, amb el mateix vídeo difuminat a dalt i a baix. "
      : `La gravació és horitzontal: el reel n'aprofita ${ample} × ${o.alcada} píxels (el centre). Si la vols sencera, ` +
        "a Vesteix tria «Fons difuminat». ") +
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
  $("#nom-reel").textContent = obert ? obert.titol : P.reel_actual ? "Aquest reel" : "Vídeo sencer";
  $("#marca").hidden = !P.reel_actual;
  if (P.reel_actual) {
    $("#nom-projecte").textContent = obert?.titol || P.nom;
    $("#marca").textContent = `De la gravació «${P.arrel}»`;
    document.title = `${obert?.titol || P.nom} · tallat`;
  }
  for (const e of P.errors_reels || []) avis(`reels.json: ${e}`, 6000);
  // Si encara no n'hi ha, no ocupa lloc; però dins d'un reel sempre hi és, per tornar al vídeo sencer
  // (revisió de Codex: si reels.json faltava o no es podia llegir, no hi havia manera de tornar-hi).
  $("#tria-reel").hidden = !reels.length && !P.reel_actual;
  if (!reels.length && !P.reel_actual) return;
  cont.textContent = "";
  // El primer, el vídeo sencer (la gravació tal com és, sense separar-la en reels).
  const sencer = document.createElement("div");
  sencer.className = "item reel sencer" + (P.reel_actual ? "" : " obert");
  sencer.innerHTML = `<span class="reel-text"><span class="reel-titol">Vídeo sencer</span>
      <span class="reel-detall">Tota la gravació, sense separar-la en reels</span></span>
    <span class="reel-durada">${P.origen?.durada ? fmt(P.origen.durada) : ""}</span>`;
  sencer.addEventListener("click", () => obre(null));
  fesClicable(sencer);
  cont.append(sencer);
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

// Els grups d'opcions (role=radiogroup: «Ritme», els dels panells) es fan servir amb les fletxes, com els
// de debò, i les fletxes ja no arriben a les dreceres del reproductor (revisió de Codex: movien el vídeo).
function instalaGrupsOpcions() {
  document.addEventListener("keydown", (e) => {
    const grup = e.target.closest?.('[role="radiogroup"]');
    if (!grup || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
    const opcions = [...grup.querySelectorAll('[role="radio"]')].filter((b) => !b.disabled && b.offsetParent);
    const i = opcions.indexOf(e.target.closest('[role="radio"]'));
    if (i < 0) return;
    e.preventDefault();
    e.stopPropagation();  // a la captura: no arriba a cap altra drecera
    const pas = ["ArrowRight", "ArrowDown"].includes(e.key) ? 1 : -1;
    const j = (i + pas + opcions.length) % opcions.length;
    opcions[j].click();
    // Les galeries d'estils (i l'assistent) es tornen a dibuixar en triar: el focus va a l'opció nova
    // (revisió de Codex: es perdia, i la fletxa següent tornava a moure el vídeo).
    const ara = grup.isConnected ? grup : grup.id ? document.getElementById(grup.id)
      : document.querySelector(`[role="radiogroup"][aria-label="${CSS.escape(grup.getAttribute("aria-label") || "")}"]`);
    const noves = ara ? [...ara.querySelectorAll('[role="radio"]')].filter((b) => !b.disabled && b.offsetParent) : [];
    (opcions[j].isConnected ? opcions[j] : noves[j])?.focus();
  }, true);
}

function instalaReels() {
  const boto = $("#boto-reel");
  const menu = $("#menu-reels");
  const tanca = ({ focus = false } = {}) => {
    menu.hidden = true;
    boto.setAttribute("aria-expanded", "false");
    if (focus) boto.focus();
  };
  boto.addEventListener("click", (e) => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
    boto.setAttribute("aria-expanded", String(!menu.hidden));
    if (!menu.hidden) menu.querySelector(".item.obert, .item")?.focus();
  });
  document.addEventListener("click", (e) => { if (!menu.hidden && !menu.contains(e.target)) tanca(); });
  menu.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); tanca({ focus: true }); } });
}

async function obre(reel) {
  $("#menu-reels").hidden = true;
  if ((reel || null) === (P.reel_actual || null)) return;
  atura();
  try {
    await esperaDesats();  // que no quedi cap canvi per desar
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
  buidaGaleria(cont);
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

// Ensenya el b-roll sense fer sonar res: si ara no se'n veu cap, el vídeo va (aturat) al primer, ja entrat.
function mostraBrollViu() {
  mostraBrollDespres = false;
  if (vista !== "directe" || sona() || !brollsMuntatge.length) return;
  const m = tempsMuntatge();
  if (brollsMuntatge.some((b) => m >= b.inici && m < (b.fins ?? b.inici + b.durada))) return;
  const b = brollsMuntatge[0];
  vesA(b.inici + Math.min(0.5, b.durada / 2));
}

function obreBroll() {
  tancaElQueHiHagi();
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

// Stickers en directe: mateixa posició, mida i rotació que tindran a l'export (les calcula el servidor:
// motor/stickers.py, lloc).
const stickersVius = new Map();
function situaSticker(img, st) {
  st = { ...st, ...(estat?.llocs_stickers?.[st.id] || {}) };  // el lloc d'aquí (arrossegat, desfet) mana
  Object.assign(img.style, { left: `${st.x * 100}%`, top: `${st.y * 100}%`, width: `${st.mida * 100}%` });
  img.style.setProperty("--rot", `${st.rotacio}deg`);
}

function pintaStickers() {
  const m = tempsMuntatge();
  const e = P?.estil_stickers || {};
  const actius = new Set();
  if (vista === "directe") {
    stickersMuntatge.forEach((st) => {
      if (m < st.inici || m >= st.inici + st.durada) return;
      actius.add(st.id);
      if (stickersVius.has(st.id)) { situaSticker(stickersVius.get(st.id), st); return; }  // potser l'han mogut
      const img = document.createElement("img");
      img.className = "sticker-viu";
      img.src = st.url;
      situaSticker(img, st);
      if (e.ombra === false) img.style.setProperty("--ombra-sticker", "none");
      if (e.animacio === "cap") img.style.animation = "none";
      $("#capa-stickers").append(img);
      stickersVius.set(st.id, img);
    });
  }
  for (const [id, img] of stickersVius) if (!actius.has(id)) { img.remove(); stickersVius.delete(id); }
}

// --- Els gràfics -----------------------------------------------------------------------------------
// Els proposa Claude des del xat (`tallat.py grafics proposa`) i la persona els vota al tauler de Vesteix. Són a
// l'estat (es desfan com la resta) i es dibuixen amb pagina/grafics.js, com al vídeo final.

let graficsMuntatge = [];  // els que surten al vídeo, en temps del muntatge (els calcula el servidor)
let dibuixosGrafics = {};  // com es dibuixa cada gràfic del pla, també els que no surten (per a les miniatures)
let paletaGrafics = null;  // els colors i les lletres de la marca
let mostresGrafics = {};   // com queda cada tipus amb l'estil del vídeo (a les cartes de l'estil)
const OP_GRAFICS = { imatges: "/imatges-grafics/" };  // on són les captures i les fotos dels gràfics
let previaGrafics = null;

const graficDe = (id) => (estat?.grafics || []).find((g) => g.id === id);
// Els trets desapareixen de seguida, sense esperar el servidor.
const graficsVisibles = () => graficsMuntatge.filter((g) => graficDe(g.id)?.estat !== "tret");

// El gràfic sencer, ja entrat (per a les miniatures).
function sencer(d) {
  return d && { ...d, inici: 0, final: 1e5, punts: (d.punts || []).map((p) => ({ ...p, t: 0 })) };
}

function textGrafic(g) {
  const text = (g.text || (g.tipus === "crida" ? estilMarca?.crida || "La teva crida habitual" : "")).replaceAll("*", "");
  if (g.tipus === "llista") return [text, ...g.punts.map((p) => `· ${p.text}`)].filter(Boolean).join("  ");
  if (g.tipus === "xat") return [text, ...g.punts.map((p) => `${p.costat === "enviat" ? "→" : "←"} ${p.text}`)].filter(Boolean).join("  ");
  if (["notificacio", "comentari", "publicacio"].includes(g.tipus)) return `${g.de ? `${g.de}: ` : ""}«${text}»`;
  if (g.tipus === "notes") return [text, ...g.punts.map((p) => `· ${p.text}`)].filter(Boolean).join("  ");
  if (g.tipus === "segueix") return [g.de || "El teu compte", text].filter(Boolean).join(" · ");
  if (g.tipus === "rec") return text ? `REC · ${text}` : "El marc d'una càmera que grava";
  if (g.tipus === "ratllat") return [text, g.punts.map((p) => p.text).join(" → ")].filter(Boolean).join(" ");
  if (g.tipus === "numero" || g.tipus === "progres") return `${g.xifra}${text ? ` · ${text}` : ""}`;
  if (g.tipus === "web") return text ? `Web: ${text}` : "Captura d'una web";
  if (g.tipus in MAX_FOTOS) {
    const n = g.punts.length;
    return [text, n ? `${n} ${n === 1 ? "foto" : "fotos"}` : "Encara sense fotos"].filter(Boolean).join(" · ");
  }
  return `«${text}»`;
}

// Les imatges de la web (la captura) i del ventall (les fotos, que es poden treure una a una).
function pintaImatgesGrafic(cont, g) {
  cont.textContent = "";
  cont.hidden = false;
  const fotos = g.tipus === "web" ? (g.imatge ? [g.imatge] : []) : g.punts.map((p) => p.imatge);
  fotos.forEach((nom, k) => {
    const foto = document.createElement("span");
    foto.className = "foto-grafic";
    const img = document.createElement("img");
    Object.assign(img, { src: OP_GRAFICS.imatges + encodeURIComponent(nom), alt: "" });
    foto.append(img);
    if (g.tipus in MAX_FOTOS) {
      const treu = document.createElement("button");
      Object.assign(treu, { className: "treu-foto", title: "Treu aquesta foto" });
      treu.setAttribute("aria-label", "Treu aquesta foto");
      treu.innerHTML = '<svg viewBox="0 0 20 20"><path d="m6 6 8 8m0-8-8 8"/></svg>';
      treu.addEventListener("click", () => canviaGrafic(g.id, { punts: g.punts.filter((_, i) => i !== k) }));
      foto.append(treu);
    }
    cont.append(foto);
  });
  if (g.tipus in MAX_FOTOS && fotos.length >= MAX_FOTOS[g.tipus]) return;
  const puja = document.createElement("button");
  puja.className = `boto petit puja-imatge${fotos.length ? "" : " principal"}`;
  puja.textContent = g.tipus === "web" ? (fotos.length ? "Canvia la captura" : "Puja la captura")
    : fotos.length ? "Afegeix fotos" : "Puja les fotos";
  puja.addEventListener("click", () => triaImatgesGrafic(g));
  cont.append(puja);
}

// Amb un camp de fitxers que viu a la pàgina (#fitxer-grafic): el Safari no sempre obre la finestra
// des d'un camp que no hi és.
let graficPerPujar = null;
function triaImatgesGrafic(g) {
  graficPerPujar = g.id;
  const tria = $("#fitxer-grafic");
  tria.multiple = g.tipus in MAX_FOTOS;
  tria.click();
}

async function pujaImatgesGrafic(id, fitxers) {
  if (!fitxers.length) return;
  avis(fitxers.length > 1 ? `Pujant ${fitxers.length} imatges…` : "Pujant la imatge…", 20000);
  const url = (f) => `/api/grafics/imatge?grafic=${encodeURIComponent(id)}&nom=${encodeURIComponent(f.name)}`;
  try { await canvisDesats(); } catch (e) { avis(e.message, 6000); return; }  // un gràfic acabat de posar: que ja hi sigui
  const fusiona = (servidor) => {  // la foto nova (o la captura) del gràfic, damunt del que s'ha canviat aquí
    const [g, aqui] = [servidor.grafics?.find((x) => x.id === id), estat.grafics?.find((x) => x.id === id)];
    if (g && aqui) Object.assign(aqui, { imatge: g.imatge, punts: g.punts, estat: g.estat, vot: g.vot });
  };
  if (await pujaFitxers(fitxers, url, fusiona)) avis("Fet. Mira-ho al vídeo.");
}

// Un gràfic dibuixat petit dins de `caixa`, amb el mateix codi que el vídeo. `centra`: el mig de la pantalla (on van
// les mostres) al mig de la caixa. Torna la seva línia de temps, per esborrar-la quan es refà.
function dibuixaMini(caixa, d, { centra = false } = {}) {
  if (!window.TallatGrafics || !paletaGrafics || !d || !caixa.clientWidth) return null;
  const host = document.createElement("div");
  host.className = "mg-host";
  const arrel = document.createElement("div");
  host.append(arrel);
  caixa.replaceChildren(host);
  const tl = TallatGrafics.construeix(arrel, [sencer(d)], paletaGrafics, OP_GRAFICS).seek(50, false);
  const s = caixa.clientWidth / 1080;
  host.style.transform = `scale(${s})`;
  if (!centra) return tl;
  // Centrat a la caixa i tan gran com hi càpiga (una etiqueta petita, a la mida d'una llista).
  const [w, h] = [caixa.clientWidth, caixa.clientHeight];
  const base = host.getBoundingClientRect();
  const r = arrel.querySelector(".tg-lloc")?.firstElementChild?.getBoundingClientRect();
  if (!r?.width || !r.height) { host.style.marginTop = `${h / 2 - 960 * s}px`; return tl; }
  const caixaG = { x: (r.left - base.left) / s, y: (r.top - base.top) / s, w: r.width / s, h: r.height / s };
  const z = Math.min((w * 0.82) / caixaG.w, (h * 0.66) / caixaG.h, s * 2.4);
  host.style.transform = `translate(${w / 2 - (caixaG.x + caixaG.w / 2) * z}px, ${h * 0.44 - (caixaG.y + caixaG.h / 2) * z}px) scale(${z})`;
  return tl;
}

// Si el canvies o el mous, és que t'agrada: queda mantingut (Claude ja no el tocarà).
function canviaGrafic(id, canvis) {
  canvia((e) => {
    const g = e.grafics.find((x) => x.id === id);
    if (g) Object.assign(g, canvis, g.estat === "proposat" || g.estat === "canvia" ? { estat: "mantingut", vot: "si" } : {});
  });
  previaBruta = true;
}

// Tret: no surt, però es guarda (perquè Claude no el torni a proposar) i es pot tornar a posar.
function treuGrafic(id, treure = true) {
  canvia((e) => { Object.assign(e.grafics.find((x) => x.id === id), { estat: treure ? "tret" : "mantingut", nota: "", vot: treure ? "no" : "si" }); });
  previaBruta = true;
}

// --- Vesteix --------------------------------------------------------------------------------------
// L'estació de com es veu el vídeo. A l'esquerra, el que val per a tot el vídeo (l'estil, els subtítols, el títol, els
// colors…); al mig, el tauler amb totes les peces, que es voten. Mentre es retoca el que és de tot el vídeo, hi ha el
// vídeo gran i, a la dreta, l'editor (o una peça tocada al vídeo); a la pestanya del costat, les notes per a Claude.
// Els colors de cada mena de peça (lila els gràfics, verd el b-roll, blau els zooms, taronja el so) són els mateixos a
// tot arreu.

let vestint = false;
let pestanyaDreta = "peces";  // a la dreta de Vesteix: «peces» (la triada o totes) o «notes» (les notes per a Claude)
let pecaTriada = null;      // {tipus: "grafic" | "broll" | "zoom" | "so", id}
let pecaPerVeure = null;    // la que s'acaba d'afegir: quan el servidor en sap el moment, el vídeo hi va
let tretsOberts = false;
let liniesDreta = [];

const NOMS_SO = { whoosh: "Whoosh", pop: "Pop", tecla: "Teclat", brill: "Brillantor", tic: "Tic" };
const TIPUS_GALERIA = [["frase", "Frase"], ["marcador", "Marcador"], ["etiqueta", "Etiqueta"], ["ratllat", "Ratllat"], ["llista", "Llista"],
  ["numero", "Número"], ["progres", "Progrés"], ["notificacio", "Notificació"], ["comentari", "Comentari"], ["publicacio", "Publicació"],
  ["xat", "Xat"], ["notes", "Notes"], ["anotacio", "Anotació"], ["rec", "REC"], ["web", "Web"], ["ventall", "Fotos"],
  ["abans", "Abans i després"], ["carrusel", "Carrusel"], ["crida", "Crida"], ["segueix", "Segueix-me"]];
// Els de fotos (punts amb imatge) i quantes s'hi poden posar.
const MAX_FOTOS = { ventall: 6, abans: 2, carrusel: 6 };
const NOMS_GRAFIC = Object.fromEntries(TIPUS_GALERIA);
// Com al servidor (motor/grafics.py): un text més llarg no s'hi desaria.
const MIDA_TEXT_GRAFIC = { frase: 140, marcador: 140, etiqueta: 40, ratllat: 40, llista: 80, crida: 90, notificacio: 120, comentari: 140, xat: 30, numero: 60, progres: 60,
  anotacio: 40, web: 60, ventall: 60, publicacio: 220, notes: 60, segueix: 60, rec: 30, abans: 60, carrusel: 60 };
const DURADES_GRAFIC = { frase: 2.8, marcador: 2.8, etiqueta: 2.2, ratllat: 3.0, llista: 4.5, crida: 3.5, notificacio: 3.0, comentari: 3.5, xat: 5.0, numero: 2.8, progres: 3.0,
  anotacio: 2.5, web: 4.0, ventall: 4.5, publicacio: 4.0, notes: 5.0, segueix: 3.5, rec: 4.0, abans: 4.5, carrusel: 5.0 };
const ICONES_PECA = {
  grafic: '<svg viewBox="0 0 24 24"><path d="M11 3.5l1.9 5.1 5.1 1.9-5.1 1.9L11 17.5l-1.9-5.1L4 10.5l5.1-1.9z"/></svg>',
  broll: '<svg viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="14" rx="2.5"/><path d="m3.5 15 4.5-4 4 3.5 3-2.5 5.5 4.5"/><circle cx="15.5" cy="9" r="1.5"/></svg>',
  zoom: '<svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/><rect x="8.5" y="8.5" width="7" height="7" rx="1.5"/></svg>',
  so: '<svg viewBox="0 0 24 24"><path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/></svg>',
  subtitols: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 11.5h4M14 11.5h3M7 15h10"/></svg>',
  titol: '<svg viewBox="0 0 24 24"><path d="M6 6.5V5h12v1.5M12 5v14M9.5 19h5"/></svg>',
};

// La paraula on va una peça nova: la que es diu on és el vídeo (o, en un silenci, la que ve). Si no surt al vídeo
// (s'ha tret), la següent que sí.
function paraulaPerAfegir() {
  const n = P?.paraules.length || 0;
  if (!n) return null;
  const t = tempsOriginalAra();
  let id = t == null ? 0 : paraulaAbans(t);
  if (id < 0 || (t != null && t > P.paraules[id].final)) id++;
  id = limita(id, 0, n - 1);
  for (let k = id; k < n; k++) if (!esFora(k)) return k;
  for (let k = id - 1; k >= 0; k--) if (!esFora(k)) return k;
  return null;
}

// El que es diu a partir d'una paraula (fins al final de la frase, o abans, en una coma o uns dos punts si ja n'hi ha
// prou): el text de partida dels gràfics nous. Que no quedi tallat a mitges («poca llet i»).
function textDes(id, max) {
  const paraules = [];
  for (let k = id; k < P.paraules.length && paraules.length < max; k++) {
    if (esFora(k)) continue;
    const text = String(estat.correccions?.[k] ?? P.paraules[k].text).trim();
    paraules.push(text);
    if (/[.?!…]["'»”]*$/.test(text) || (paraules.length >= 3 && /[,:;]$/.test(text))) break;
  }
  return paraules.join(" ").replace(/^[«"“¿¡]+/, "").replace(/[.,;:!?…«»"“”]+$/, "");
}
// Quina part s'omple d'un progrés (com al servidor: motor/grafics.py, fraccio): «70 %», «3 de 5», «7/10», «3 de cada 4».
// null si no ho diu (o si és negatiu o d'un total de zero): no es desaria.
function fraccioProgres(text) {
  const m = /(-?)(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?/.exec(text || "");
  if (!m || m[1]) return null;
  const nombre = (enter, dec) => Number(`${enter.replaceAll(".", "")}.${dec || 0}`);
  const valor = nombre(m[2], m[3]);
  const resta = text.slice(m.index + m[0].length);
  if (/%/.test(resta)) return Math.min(1, valor / 100);
  const t = /(?:\bde(?:\s+cada)?\b|\/|\bsobre\b)\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?/.exec(resta);
  const total = t ? nombre(t[1], t[2]) : 0;
  return total > 0 ? Math.min(1, valor / total) : null;
}
const retalla = (text, mida) => (text.length > mida ? text.slice(0, mida).replace(/\s+\S*$/, "") : text);

function graficNou(tipus, paraula) {
  const frase = textDes(paraula, 7);
  const g = { tipus, paraula, text: "", punts: [], estat: "mantingut", nota: "", vot: "si", origen: "teu" };
  if (tipus === "frase" || tipus === "marcador") g.text = retalla(frase, 60) || "La teva frase";
  else if (tipus === "etiqueta" || tipus === "anotacio") g.text = retalla(textDes(paraula, 2), 30) || "Aquí";
  else if (tipus === "llista") g.punts = [{ text: "Primer" }, { text: "Segon" }, { text: "Tercer" }];
  else if (tipus === "ratllat") g.punts = [{ text: retalla(textDes(paraula, 2), 30) || "abans" }, { text: "ara" }];
  else if (tipus === "xat") g.punts = [{ text: retalla(frase, 70) || "Hola!", costat: "rebut" }, { text: "De veritat?", costat: "enviat" }];
  else if (tipus === "notificacio") Object.assign(g, { de: "Missatge", text: retalla(frase, 100) || "Tens un missatge" });
  else if (tipus === "comentari") Object.assign(g, { de: "algú", text: retalla(frase, 100) || "I això com es fa?" });
  else if (tipus === "publicacio") Object.assign(g, { de: "algú", text: retalla(frase, 160) || "El que diu la publicació" });
  else if (tipus === "notes") Object.assign(g, { text: "Notes", punts: [{ text: retalla(frase, 70) || "La primera línia" }] });
  else if (tipus === "segueix") Object.assign(g, { de: retalla(estilMarca?.compte || "", 30) });
  else if (tipus === "numero") {
    const xifra = textDes(paraula, 14).match(/\d+(?:[.,]\d+)*(?:\s?%)?/);
    g.xifra = xifra ? xifra[0] : "3";
  } else if (tipus === "progres") {
    const xifra = textDes(paraula, 14).match(/\d+(?:[.,]\d+)*\s?%|\d+\s*(?:de|\/)\s*\d+/);
    Object.assign(g, { xifra: xifra ? xifra[0] : "70 %", forma: "cercle" });
  }
  if (tipus === "anotacio") g.forma = "fletxa";
  if (tipus === "crida") g.text = retalla(estilMarca?.crida || "Segueix-me per a més", 90);
  return g;
}

// L'id d'una peça nova: el número més alt + 1, comptant-hi els de les que ja no hi són però en queda el so apagat
// (sons_apagats va per id: si es tornés a fer servir, la peça nova sortiria muda).
function idNou(llista, lletra) {
  const prefix = lletra === "g" ? "grafic:" : "so:";
  const apagats = (estat?.sons_apagats || []).filter((c) => c.startsWith(prefix + lletra)).map((c) => c.slice(prefix.length));
  const numeros = [...llista.map((x) => String(x.id)), ...apagats].map((id) => Number(id.slice(1)) || 0);
  return `${lletra}${Math.max(0, ...numeros) + 1}`;
}

function afegeixPeca(fes) {
  const paraula = paraulaPerAfegir();
  if (paraula == null) { avis("Aquest vídeo no té cap paraula on posar-ho."); return; }
  if (sona()) atura();
  fes(paraula);
}

function afegeixGrafic(tipus) {
  afegeixPeca((paraula) => {
    // L'id el posa la pàgina (com el servidor: el número més alt + 1), per poder-lo triar de seguida.
    const g = { id: idNou(estat.grafics || [], "g"), ...graficNou(tipus, paraula) };
    canvia((e) => { e.grafics = [...(e.grafics || []), g]; });
    previaBruta = true;
    pecaPerVeure = { tipus: "grafic", id: g.id };
    triaPeca("grafic", g.id, { enfoca: true });
    if (tipus === "web" || tipus in MAX_FOTOS) triaImatgesGrafic(g);  // dins del mateix clic: el Safari l'obre
  });
}

// Un zoom és el d'un tros: es coneix pel segon de la gravació on comença el tros (si els talls canvien, el número del
// tros canvia, però aquest segon no).
const idZoom = (k) => (trams[k] ? trams[k][0].toFixed(3) : "");
const tramDeZoom = (id) => trams.findIndex(([a]) => a.toFixed(3) === String(id));

function afegeixZoom() {
  afegeixPeca((paraula) => {
    const k = indexTram(P.paraules[paraula].inici);
    if (zoomsTram[k]) { triaPeca("zoom", idZoom(k)); avis("Aquest tros ja té zoom."); return; }
    canvia((e) => { e.zooms = [...new Set([...(e.zooms || []), paraula])].sort((a, b) => a - b); });
    pecaPerVeure = { tipus: "zoom", id: idZoom(k) };
    triaPeca("zoom", idZoom(k));
  });
}

function afegeixSo(nom) {
  afegeixPeca((paraula) => {
    const s = { id: idNou(estat.sons || [], "s"), so: nom, paraula };
    canvia((e) => { e.sons = [...(e.sons || []), s]; });
    escoltaSo(nom);
    pecaPerVeure = { tipus: "so", id: s.id };
    triaPeca("so", s.id);
  });
}

function escoltaSo(nom) {
  const url = mostresSo?.sons?.[nom];
  if (url) new Audio(url).play().catch(() => {});
  else carregaMostresSo();
}

// El b-roll es prepara al servidor (amb ffmpeg): es posa a la paraula, un fitxer de la biblioteca o un de pujat.
let paraulaBrollNou = null;
async function afegeixBrollDeBiblioteca(nom) {
  const paraula = paraulaPerAfegir();
  if (paraula == null) return;
  if (sona()) atura();
  avis("Preparant el b-roll…", 20000);
  const abans = new Set(brollsMuntatge.map((b) => b.id));
  await accioBroll("/api/broll/biblioteca", { paraula, nom }, "B-roll posat.");
  triaBrollNou(abans);
}

function triaFitxerBroll() {
  const paraula = paraulaPerAfegir();
  if (paraula == null) return;
  if (sona()) atura();
  paraulaBrollNou = paraula;
  instruccioPerPujar = null;
  $("#fitxer-broll").click();
}

async function pujaBrollNou(fitxer) {
  const paraula = paraulaBrollNou;
  paraulaBrollNou = null;
  avis(`Pujant «${fitxer.name}»…`, 30000);
  const abans = new Set(brollsMuntatge.map((b) => b.id));
  const url = (f) => `/api/broll/puja?paraula=${paraula}&nom=${encodeURIComponent(f.name)}`;
  if (await pujaFitxers([fitxer], url)) { avis("B-roll posat."); triaBrollNou(abans); }
}

function triaBrollNou(abans) {
  const nou = brollsMuntatge.find((b) => !abans.has(b.id));
  if (!nou) return;
  triaPeca("broll", nou.id);
  vesA(nou.inici + 0.4);
}

// Totes les peces del vídeo, per ordre: {tipus, id, t (muntatge, o null si no surt), nom, detall, claude}.
function pecesDelVideo() {
  const peces = [];
  for (const g of estat?.grafics || []) {
    if (g.estat === "tret") continue;
    const s = graficsMuntatge.find((x) => x.id === g.id);
    const falta = dibuixosGrafics[g.id]?.falta;
    const conegut = g.id in dibuixosGrafics;  // si s'acaba de posar, el servidor encara no hi ha dit res
    peces.push({ tipus: "grafic", id: g.id, t: s ? s.inici : null, nom: NOMS_GRAFIC[g.tipus] || g.tipus,
      detall: textGrafic(g), claude: g.estat === "proposat" || g.estat === "canvia",
      avis: s || !conegut ? "" : falta ? (g.tipus === "web" ? "Falta la captura" : "Falten les fotos") : "No surt al vídeo" });
  }
  for (const b of brollsMuntatge) {
    const ins = instruccions.find((i) => i.id === b.id);
    peces.push({ tipus: "broll", id: b.id, t: b.inici, nom: "B-roll",
      detall: ins?.pagina ? `${fmtSegons(b.durada)}` : `«${ins?.text || "b-roll"}»` });
  }
  zoomsTram.forEach((z, k) => {
    if (z && k < trams.length) peces.push({ tipus: "zoom", id: idZoom(k), t: acum[k], nom: "Zoom",
      detall: `Fins al tall (${fmtSegons(trams[k][1] - trams[k][0])})` });
  });
  for (const s of estat?.sons || []) {
    const e = efectesMuntatge.find((x) => x.clau === `so:${s.id}`);
    peces.push({ tipus: "so", id: s.id, t: e ? e.t : null, nom: NOMS_SO[s.so] || s.so, detall: "Efecte de so",
      avis: e ? "" : "No surt al vídeo" });
  }
  return peces.sort((a, b) => (a.t ?? 1e9) - (b.t ?? 1e9));
}

const pecaDe = (tipus, id) => pecesDelVideo().find((p) => p.tipus === tipus && String(p.id) === String(id));

// A la dreta de Vesteix, una pestanya o l'altra: cadascuna amb tota l'alçada (un sol lloc per baixar).
function mostraDreta(quina) {
  pestanyaDreta = quina;
  $("#vesteix-dreta").dataset.pestanya = quina;
  pintaPestanyesDreta();
  if (quina === "notes" && notesCarregades) pintaNotes();  // ara es veuen: les respostes noves ja compten com a vistes
}

function pintaPestanyesDreta() {
  for (const b of $$("#pestanyes-dreta button")) {
    b.setAttribute("aria-selected", String(b.dataset.dreta === pestanyaDreta));
    b.tabIndex = b.dataset.dreta === pestanyaDreta ? 0 : -1;
  }
  if (!estat) return;
  const peces = pecesDelVideo().length;
  $("#compte-peces").textContent = peces ? String(peces) : "";
  const notes = notesCarregades ? notesVisibles() : [];
  $("#compte-notes-dreta").textContent = notes.length ? String(notes.length) : "";
  $("#punt-notes-dreta").hidden = pestanyaDreta === "notes" || !notes.some((n) => esNova(n) || n.estat === "pregunta");
}

function triaPeca(tipus, id, { enfoca = false, ves = false } = {}) {
  pecaTriada = { tipus, id };
  if (pestanyaDreta !== "peces") mostraDreta("peces");
  const p = pecaDe(tipus, id);
  if (ves && p?.t != null) vesA(p.t + (tipus === "grafic" ? 0.6 : 0.1));
  pintaDreta({ refes: true, enfoca });
}

function deixaPeca() {
  pecaTriada = null;
  if (capaTriada) deixaCapa();
  pintaDreta({ refes: true });
}

// Quan el servidor ja sap on va la peça que s'acaba de posar, el vídeo s'hi atura (amb el gràfic ja entrat).
function miraPecaNova() {
  if (!pecaPerVeure) return;
  const p = pecaDe(pecaPerVeure.tipus, pecaPerVeure.id);
  if (!p || p.t == null) return;
  pecaPerVeure = null;
  if (!sona()) vesA(p.t + (p.tipus === "grafic" ? 0.6 : 0.1));
}

function pintaVesteix() {
  if (!estat) return;
  pintaEncaix();
  miraPecaNova();
  if (!vestint) return;
  actualitzaTauler();
  pintaTauler();
  pintaDreta();
}

// --- El tauler ---
// Totes les peces del vídeo en l'ordre en què surten, cadascuna en una targeta amb el seu tros de vídeo, com quedarà:
// amb el mateix codi que el vídeo final (subtítols, títol, gràfics, b-roll, stickers, zoom i bloc de color). Les quietes
// ensenyen un fotograma, amb les peces movent-se al damunt; la que assenyales es mou de debò, amb un sol vídeo que va
// de targeta en targeta (deu vídeos alhora alentirien l'ordinador). Cada peça es vota: Sí, Potser o No, amb una nota.
// Els vots dels gràfics van dins del gràfic (motor/grafics.py); els de la resta, a l'estat (`vots`).

let graficsAlternatius = [];  // les alternatives que no surten al vídeo, situades com si hi sortissin
let filtreTauler = "totes";
const votatsAra = new Set();    // els que s'han dit «No» ara: es queden a la vista, per si et repenses
const cartesTauler = new Map(); // clau de la peça → {el, p, tls, ctx, sig}
const grupsTauler = new Map();  // grup d'alternatives → l'element que les agrupa
const visiblesTauler = new Set();
let ambSoTauler = false;
let rondaPintada = null;          // la ronda que hi havia l'últim cop que es va pintar el tauler
let esperaTreta = null;           // la nota de ronda de la qual has tret l'espera («Continua votant»)
let novetatRonda = null;          // {ronda, nous, canviats}: l'avís de dalt quan n'arriba una de nova, fins que el tanques
const NOMS_VOT = { si: "Sí", potser: "Potser", no: "No" };
const ICONA_SO = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/></svg>';
const ICONA_MUT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="m22 9-6 6M16 9l6 6"/></svg>';
const ICONES_TAULER = {
  so: '<span class="ona-so" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span>',
  zoom: '<svg class="marc-zoom" viewBox="0 0 48 48" aria-hidden="true"><path d="M6 16V6h10M42 16V6H32M6 32v10h10M42 32v10H32"/></svg>',
};

// El tauler es veu a Vesteix, menys mentre es retoca el que és de tot el vídeo (amb el vídeo gran).
const taulerVisible = () => vestint && !pecaTriada && !$(".barra").classList.contains("editant-estil");

function actualitzaTauler() {
  const si = taulerVisible();
  document.body.classList.toggle("amb-tauler", si);
  if ($("#tauler").hidden === !si) return;
  $("#tauler").hidden = !si;
  if (si) { if (sona()) atura(); pintaTauler(); } else aturaCarta();
}

// Totes les peces, per ordre: {clau, tipus, id, t (on comença al muntatge, o null), final, nom, detall, avis, i el
// tros que es mou a la targeta: t0–t1, i el moment del fotograma, tp}.
function pecesTauler() {
  if (!estat || !P) return [];
  const peces = [];
  const situats = new Map([...graficsMuntatge, ...graficsAlternatius].map((s) => [s.id, s]));
  for (const g of estat.grafics || []) {
    const s = situats.get(g.id) || null;
    let t = s ? s.inici : null;
    if (t == null && g.paraula != null && g.paraula < P.paraules.length && !esFora(g.paraula)) t = muntatgeDe(P.paraules[g.paraula].inici);
    const falta = dibuixosGrafics[g.id]?.falta;
    peces.push({ clau: `grafic:${g.id}`, tipus: "grafic", id: g.id, g, s, t,
      final: s ? s.final : t != null ? t + (g.durada || DURADES_GRAFIC[g.tipus] || 2.5) : null,
      nom: NOMS_GRAFIC[g.tipus] || g.tipus, detall: g.motiu || textGrafic(g),
      avis: s || g.estat === "tret" ? "" : falta ? (g.tipus === "web" ? "Falta la captura" : "Falten les fotos") : "Ara no surt al vídeo" });
  }
  for (const b of brollsMuntatge) {
    const ins = instruccions.find((i) => i.id === b.id);
    peces.push({ clau: `broll:${b.id}`, tipus: "broll", id: b.id, b, ins, t: b.inici, final: b.fins ?? b.inici + b.durada,
      nom: "B-roll", detall: ins && !ins.pagina ? `«${ins.text}»` : `Dura ${fmtSegons(b.durada)}` });
  }
  for (const st of stickersMuntatge) {
    const ins = instruccions.find((i) => i.id === st.id);
    peces.push({ clau: `sticker:${st.id}`, tipus: "sticker", id: st.id, st, ins, t: st.inici, final: st.inici + st.durada,
      nom: "Sticker", detall: ins?.pagina ? "El teu sticker" : ins ? `«${ins.text}»` : "" });
  }
  zoomsTram.forEach((z, k) => {
    if (!z || k >= trams.length) return;
    const d = trams[k][1] - trams[k][0];
    peces.push({ clau: `zoom:${idZoom(k)}`, tipus: "zoom", id: idZoom(k), k, t: acum[k], final: acum[k] + d, nom: "Zoom",
      detall: `S'apropa fins al tall (${fmtSegons(d)})` });
  });
  for (const so of estat.sons || []) {
    const e = efectesMuntatge.find((x) => x.clau === `so:${so.id}`);
    peces.push({ clau: `so:${so.id}`, tipus: "so", id: so.id, so, t: e ? e.t : null, final: e ? e.t + 0.6 : null,
      nom: NOMS_SO[so.so] || "So", detall: "Un efecte de so", avis: e ? "" : "Ara no surt al vídeo" });
  }
  for (const p of peces) {
    if (p.t == null) continue;
    // Una mica abans i una mica després (dels zooms, els primers segons; de les peces llargues, els primers sis).
    p.t0 = Math.max(0, p.t - 0.4);
    p.t1 = Math.min(duradaFinal, Math.max(p.t + 1.2, Math.min(p.final, p.t + (p.tipus === "zoom" ? 3 : 6)) + 0.4));
    p.tp = Math.min(p.t1 - 0.05, p.t + Math.min(1, Math.max(0.2, (p.final - p.t) / 2)));
  }
  return peces.sort((a, b) => (a.t ?? 1e9) - (b.t ?? 1e9) || a.clau.localeCompare(b.clau));
}

// El vot d'una peça: el que hi ha dit la persona. Els gràfics de Claude sense vot són «per mirar» (""); la resta de
// peces són seves (les ha posat ella o les ha dit en veu alta): sí, si no diu el contrari.
function votDe(p) {
  if (p.tipus !== "grafic") return estat.vots?.[p.clau]?.vot || "si";
  return p.g.vot || { mantingut: "si", tret: "no", canvia: "potser" }[p.g.estat] || "";
}
const notaDe = (p) => (p.tipus === "grafic" ? p.g.nota : estat.vots?.[p.clau]?.nota) || "";
// Com al servidor (motor/grafics.py, net): el vot mana sobre l'estat.
const estatDeVot = (vot, nota) => (vot === "no" ? "tret" : vot === "potser" || (vot === "si" && nota) ? "canvia"
  : vot === "si" ? "mantingut" : "proposat");

// Perquè Claude sàpiga de quina peça li parles: què és i a quina paraula comença (la que sona, o la que ve).
function sobreLaPeca(p) {
  let id = -1;
  if (p.t != null && P.paraules.length) {
    const t = originalDe(p.t);
    id = Math.max(0, paraulaAbans(t));
    if (t > P.paraules[id].final && id + 1 < P.paraules.length) id++;
  }
  return { nom: `${p.nom}${p.ins?.text ? ` «${retalla(p.ins.text, 40)}»` : ""}`, paraula: id >= 0 ? id : null };
}

function vota(p, vot) {
  if (p.tipus === "grafic") {
    const nou = votDe(p) === vot ? "" : vot;  // tornar a tocar el que ja hi ha el treu: torna a estar per mirar
    canvia((e) => {
      const g = e.grafics.find((x) => x.id === p.id);
      if (!g) return;
      Object.assign(g, { vot: nou, estat: estatDeVot(nou, g.nota) });
      // De dues opcions per al mateix moment, només una: dir Sí a l'una és dir No a les altres.
      if (nou === "si" && g.grup) {
        for (const altra of e.grafics) {
          if (altra !== g && altra.grup === g.grup && altra.estat !== "tret") Object.assign(altra, { vot: "no", estat: "tret" });
        }
      }
    });
    previaBruta = true;
    if (nou === "no") votatsAra.add(p.clau);
    return;
  }
  if (vot === "no") { treuDelTauler(p); return; }
  if (votDe(p) === vot) return;
  canvia((e) => { e.vots = { ...(e.vots || {}), [p.clau]: { ...sobreLaPeca(p), nota: notaDe(p), vot } }; });
}

function treuDelTauler(p) {
  if (p.tipus === "broll") {
    if (p.ins?.pagina && !confirm("Vols treure aquest b-roll? Se n'esborra el fitxer i no es pot desfer.")) return;
    treuBroll(p.id);
  } else if (p.tipus === "sticker") {
    if (p.ins?.pagina) {
      if (confirm("Vols treure aquest sticker? Se n'esborra el fitxer i no es pot desfer.")) accioBroll("/api/broll/esborra", { instruccio: p.id }, "Sticker tret.");
    } else if (p.ins) decideixInstruccio(p.ins, "descartada").then((ok) => ok && avis("Sticker tret (la instrucció de veu queda descartada)."));
  } else if (p.tipus === "zoom") treuZoom(p.id);
  else treuSo(p.id);
}

function desaNotaPeca(p, text) {
  const nota = textPla(text).slice(0, 600);
  if (nota === notaDe(p)) return;
  if (p.tipus === "grafic") {
    canvia((e) => {
      const g = e.grafics.find((x) => x.id === p.id);
      if (!g) return;
      const vot = g.vot || (nota ? "potser" : "");  // una nota sense vot és que hi vols un canvi
      Object.assign(g, { nota, vot, estat: vot ? estatDeVot(vot, nota) : g.estat });
    });
    return;
  }
  canvia((e) => { e.vots = { ...(e.vots || {}), [p.clau]: { ...sobreLaPeca(p), vot: votDe(p), nota } }; });
}

// De dues alternatives, la triada es queda (sí) i les altres se'n van (no); amb `id` null, cap.
function triaAlternativa(membres, id) {
  canvia((e) => {
    for (const g of e.grafics) {
      if (!membres.includes(g.id)) continue;
      const vot = g.id === id ? "si" : "no";
      Object.assign(g, { vot, estat: estatDeVot(vot, g.nota) });
    }
  });
  previaBruta = true;
  avis(id ? "Triada. L'altra ja no surt." : "Cap de les dues. Claude no les tornarà a proposar.");
}

// Les alternatives (dos gràfics del mateix grup) que encara no s'han triat van juntes: [{p} | {grup, peces}].
function elementsTauler(peces) {
  const grups = new Map();
  for (const p of peces) {
    if (p.tipus !== "grafic" || !p.g.grup || p.g.estat === "tret") continue;
    if (!grups.has(p.g.grup)) grups.set(p.g.grup, []);
    grups.get(p.g.grup).push(p);
  }
  const indecisos = new Set([...grups].filter(([, ps]) => ps.length > 1 && !ps.some((p) => votDe(p) === "si")).map(([k]) => k));
  const fets = new Set();
  const sortida = [];
  for (const p of peces) {
    const grup = p.tipus === "grafic" && p.g.estat !== "tret" ? p.g.grup : null;
    if (grup && indecisos.has(grup)) {
      if (!fets.has(grup)) { fets.add(grup); sortida.push({ grup, peces: grups.get(grup) }); }
    } else sortida.push({ p });
  }
  return sortida;
}

const votElement = (x) => (x.grup ? "" : votDe(x.p));
function passaFiltre(x, filtre) {
  const vot = votElement(x);
  if (filtre === "totes") return vot !== "no" || votatsAra.has(x.p.clau);
  if (filtre === "mirar") return vot === "";
  return vot === filtre;
}

function pintaTauler() {
  if (!estat || $("#tauler").hidden) return;
  const peces = pecesTauler();
  const elements = elementsTauler(peces);
  for (const b of $$("#filtres-tauler button")) {
    const f = b.dataset.filtre;
    b.setAttribute("aria-checked", String(f === filtreTauler));
    const n = elements.filter((x) => passaFiltre(x, f)).length;
    b.querySelector(".compte").textContent = n ? String(n) : "";
  }
  const ronda = estat.ronda || 0;
  const novaRonda = rondaPintada != null && ronda > rondaPintada;
  rondaPintada = ronda;
  if (novaRonda) {
    const deLaRonda = (estat.grafics || []).filter((g) => g.ronda === ronda && g.estat !== "tret");
    novetatRonda = { ronda, nous: deLaRonda.filter((g) => g.novetat === "nou").length,
      canviats: deLaRonda.filter((g) => g.novetat === "canviat").length };
  }
  $("#xip-ronda").hidden = ronda < 1;
  $("#xip-ronda").textContent = `Ronda ${ronda}`;
  const hiHa = peces.length > 0;
  $("#tauler-buit").hidden = hiHa;
  $("#ronda").hidden = !hiHa;
  $("#filtres-tauler").hidden = !hiHa;
  // Sense cap gràfic de Claude encara, el que hi ha són les teves peces: el botó en demana les primeres propostes.
  const deClaude = peces.some((p) => p.tipus === "grafic" && p.g.estat !== "tret" && p.g.origen !== "teu");
  const capGrafic = !peces.some((p) => p.tipus === "grafic" && p.g.estat !== "tret");
  $("#titol-tauler").firstChild.textContent = deClaude ? "Propostes de Claude " : "Les peces del vídeo ";
  $("#demana-ronda").textContent = capGrafic ? "Demana propostes a Claude" : "Demana la ronda següent";
  const falten = elements.filter((x) => votElement(x) === "").length;
  $("#falten").innerHTML = falten ? `Te'n falten <b>${falten}</b> per mirar` : "Ho tens tot mirat.";
  $("#ja-esta").hidden = falten > 0;
  pintaEstatRonda();
  const sigDibuix = JSON.stringify([estilSub, paletaGrafics, estat.subtitols !== false, zoomVideo,
    P.estil_stickers || null]);
  const cont = $("#graella-tauler");
  const vius = new Set();
  const ordre = [];
  for (const x of elements.filter((y) => passaFiltre(y, filtreTauler))) {
    if (x.grup) {
      const el = grupTauler(x, sigDibuix, vius);
      ordre.push(el);
    } else {
      const c = cartaTauler(x.p, sigDibuix);
      vius.add(x.p.clau);
      ordre.push(c.el);
    }
  }
  for (const [clau, c] of cartesTauler) {
    if (vius.has(clau)) continue;
    if (TV.c === c) aturaCarta();
    for (const tl of c.tls || []) tl?.kill?.();
    observaTauler.unobserve(c.el);
    visiblesTauler.delete(c);
    c.el.remove();
    cartesTauler.delete(clau);
  }
  for (const [grup, el] of grupsTauler) if (!ordre.includes(el)) { el.remove(); grupsTauler.delete(grup); }
  // Al seu lloc, sense moure les que ja hi són (moure la que es mou l'aturaria).
  let abans = null;
  for (const el of ordre) {
    const seguent = abans ? abans.nextSibling : cont.firstChild;
    if (el !== seguent) cont.insertBefore(el, seguent);
    abans = el;
  }
  $("#buit-filtre").hidden = ordre.length > 0 || !hiHa;
  // Les capes es dibuixen ja a la pàgina: els gràfics i els subtítols en mesuren la mida.
  escalaTauler();
  for (const c of cartesTauler.values()) {
    if (c.refes && !c.movent) { c.refes = false; capaCarta(c); }  // mentre s'arrossega un sticker, no
    if (c.tornaAMoure) {
      c.tornaAMoure = false;
      if (c.el.querySelector(".clip").matches(":hover, :focus-within")) activaCarta(c);
    }
  }
  if (novaRonda) revelaRonda(cont, ordre);
}

// Una ronda nova: el tauler torna a dalt, les targetes hi entren d'una en una i el número de la ronda fa un salt.
function revelaRonda(cont, ordre) {
  cont.scrollTo({ top: 0 });
  $("#novetat-ronda").scrollIntoView({ block: "nearest" });  // amb el mòbil, la que es desplaça és la pàgina
  ordre.forEach((el, i) => el.style.setProperty("--i", String(Math.min(i, 12))));
  for (const [el, classe] of [[cont, "ronda-nova"], [$("#xip-ronda"), "salta"]]) {
    el.classList.remove(classe);
    void el.offsetWidth;  // perquè l'animació torni a començar
    el.classList.add(classe);
  }
  clearTimeout(revelaRonda.temps);
  revelaRonda.temps = setTimeout(() => cont.classList.remove("ronda-nova"), 1500);
}

function grupTauler(x, sigDibuix, vius) {
  let el = grupsTauler.get(x.grup);
  if (!el) {
    el = document.createElement("div");
    el.className = "grup-tauler";
    el.innerHTML = `<div class="grup-cap"><strong></strong><span>Tria'n una</span></div><div class="grup-cartes"></div>
      <button class="enllac cap-de-les-dues">Cap de les dues</button>`;
    grupsTauler.set(x.grup, el);
  }
  const p0 = x.peces[0];
  const frase = p0.g.paraula != null && P.paraules[p0.g.paraula] ? textDes(p0.g.paraula, 9) : "";
  el.querySelector(".grup-cap strong").textContent = `${x.peces.length === 2 ? "Dues" : x.peces.length} opcions${frase ? ` per a «${frase}»` : ""}`;
  const ids = x.peces.map((p) => p.id);
  el.querySelector(".cap-de-les-dues").onclick = () => triaAlternativa(ids, null);
  const cartes = el.querySelector(".grup-cartes");
  // Les targetes que ja hi són, s'hi queden (treure-les i tornar-les a posar aturaria la que es mou).
  const llista = x.peces.map((p) => { vius.add(p.clau); return cartaTauler(p, sigDibuix, { alternativa: ids }).el; });
  if (llista.some((carta, k) => cartes.children[k] !== carta) || cartes.children.length !== llista.length) cartes.replaceChildren(...llista);
  return el;
}

// --- Una targeta ---

function cartaTauler(p, sigDibuix, { alternativa = null } = {}) {
  let c = cartesTauler.get(p.clau);
  if (!c) {
    const el = document.createElement("article");
    el.innerHTML = `<div class="carta-cap"><span class="temps"></span><span class="tipus-peca"><i></i><span></span></span>
        <span class="insignia" hidden></span></div>
      <div class="clip" tabindex="0" role="group">
        <div class="clip-fons"></div><img class="clip-media clip-imatge" alt="" hidden>
        <div class="mg-host clip-capa"></div><div class="clip-marca"></div>
        <button class="clip-so" type="button"></button><span class="clip-progres"><i></i></span>
      </div>
      <p class="carta-motiu"></p><p class="carta-avis" hidden></p>
      <div class="carta-accions"></div>
      <div class="carta-nota"></div>`;
    c = { el, p, tls: [], ctx: null, sig: "", desfase: Math.random() * 3, brollsVius: new Map() };
    cartesTauler.set(p.clau, c);
    cartaDe.set(el, c);
    instalaClip(c);
    observaTauler.observe(el);
  }
  c.p = p;
  const { el } = c;
  el.className = `carta-tauler peca-${p.tipus}${votDe(p) === "no" ? " vot-no" : ""}${TV.c === c ? " activa" : ""}`;
  el.querySelector(".temps").textContent = p.t != null ? fmt(p.t) : "—";
  el.querySelector(".tipus-peca span").textContent = p.nom;
  // Nova o canviada en aquesta ronda (de la segona endavant: a la primera, totes ho són), o teva.
  const ins = el.querySelector(".insignia");
  const g = p.g;
  const ronda = estat.ronda || 0;
  const nova = g && g.ronda && g.ronda === ronda && ronda > 1 && g.novetat;
  const teva = !g || g.origen === "teu";
  ins.hidden = !nova && !teva;
  ins.className = `insignia ${nova ? (g.novetat === "nou" ? "nova" : "canviada") : "teva"}`;
  ins.textContent = nova ? (g.novetat === "nou" ? "Nova" : "Canviada") : "Teva";
  el.querySelector(".carta-motiu").textContent = p.detall;
  const avis_ = el.querySelector(".carta-avis");
  avis_.hidden = !p.avis;
  avis_.textContent = p.avis;
  const clip = el.querySelector(".clip");
  clip.setAttribute("aria-label", `${p.nom}${p.t != null ? `, al ${fmt(p.t)}` : ""}. Retorn: mira-ho`);
  pintaAccionsCarta(c, alternativa);
  pintaNotaCarta(c, !!alternativa);
  const ctx = contextCarta(p);
  // Si només ha canviat on és el sticker (l'has arrossegat), es mou al seu lloc nou i prou: ni es refà la targeta ni
  // el vídeo torna a començar.
  const sense = { ...ctx, stickers: ctx.stickers.map(({ x, y, ...st }) => st) };
  const sig = sigDibuix + JSON.stringify([p.t0, p.t1, p.tp, sense, p.tipus === "grafic" ? dibuixosGrafics[p.id] : null]);
  if (sig === c.sig) {  // potser només ha canviat on és (o s'ha desfet): sempre al lloc que toca
    c.ctx = ctx;
    for (const st of ctx.stickers) {
      const img = c.stHost?.querySelector(`[data-id="${CSS.escape(st.id)}"]`);
      if (img && !c.movent) situaSticker(img, st);
    }
  }
  if (sig !== c.sig) {
    c.sig = sig;
    c.ctx = ctx;
    if (TV.c === c) { aturaCarta(); c.tornaAMoure = true; }  // si encara l'assenyales, es torna a moure refeta
    c.refes = true;  // quan ja sigui a la pàgina
  }
  return c;
}

function pintaAccionsCarta(c, alternativa) {
  const cont = c.el.querySelector(".carta-accions");
  const p = c.p;
  const sig = JSON.stringify([alternativa, votDe(p), p.avis, p.g?.tipus]);
  if (cont.dataset.sig === sig) return;
  cont.dataset.sig = sig;
  cont.textContent = "";
  if (alternativa) {
    const b = document.createElement("button");
    b.className = "boto ample tria-alternativa";
    b.textContent = "Aquesta";
    b.addEventListener("click", () => triaAlternativa(alternativa, p.id));
    cont.append(b);
    return;
  }
  if (p.tipus === "grafic" && dibuixosGrafics[p.id]?.falta) {
    const b = document.createElement("button");
    b.className = "boto petit ample principal";
    b.textContent = p.g.tipus === "web" ? "Puja la captura" : "Puja les fotos";
    b.addEventListener("click", () => triaImatgesGrafic(p.g));
    cont.append(b);
  }
  const seg = document.createElement("div");
  seg.className = "segmentat petit vots-carta";
  seg.setAttribute("role", "radiogroup");
  seg.setAttribute("aria-label", `T'agrada: ${p.nom}?`);
  const vot = votDe(p);
  for (const v of ["si", "potser", "no"]) {
    const b = document.createElement("button");
    b.setAttribute("role", "radio");
    b.dataset.vot = v;
    b.setAttribute("aria-checked", String(vot === v));
    b.textContent = NOMS_VOT[v];
    b.addEventListener("click", () => vota(cartesTauler.get(p.clau)?.p || p, v));
    seg.append(b);
  }
  cont.append(seg);
}

// La nota de cada peça: «+ Nota» l'obre; es desa sola mentre s'escriu. Mentre s'hi escriu, no es refà.
function pintaNotaCarta(c, alternativa) {
  const cont = c.el.querySelector(".carta-nota");
  if (cont.contains(document.activeElement)) return;
  const p = c.p;
  const nota = notaDe(p);
  cont.hidden = alternativa && !nota;
  const sig = JSON.stringify([nota, c.notaOberta, alternativa]);
  if (cont.dataset.sig === sig) return;
  cont.dataset.sig = sig;
  cont.textContent = "";
  if (!nota && !c.notaOberta) {
    if (alternativa) return;
    const b = document.createElement("button");
    b.className = "enllac afegeix-nota";
    b.textContent = "+ Nota";
    b.addEventListener("click", () => { c.notaOberta = true; pintaNotaCarta(c, false); cont.querySelector("textarea")?.focus(); });
    cont.append(b);
    return;
  }
  const camp = document.createElement("textarea");
  Object.assign(camp, { className: "camp-text nota-carta", rows: 2, value: nota, maxLength: 600,
    placeholder: "Què hi canviaries? «més petit», «a baix», «una altra paraula»…" });
  camp.setAttribute("aria-label", `La teva nota per a Claude: ${p.nom}`);
  let espera = null;
  const desa_ = () => { clearTimeout(espera); espera = null; desaNotaPeca(cartesTauler.get(p.clau)?.p || p, camp.value); };
  camp.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(desa_, 700); ajustaAlcada(camp); });
  camp.addEventListener("blur", () => {
    if (espera) desa_();
    c.notaOberta = false;  // si hi ha nota, ja es veu; si no, torna a ser «+ Nota»
    if (!camp.value.trim()) setTimeout(() => pintaNotaCarta(c, false), 0);
  });
  camp.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); camp.blur(); } });
  cont.append(camp);
  requestAnimationFrame(() => ajustaAlcada(camp));
}

// El que es veu a la targeta: només la seva peça (les altres tenen la seva targeta), sobre el vídeo amb els subtítols
// d'aquell moment. Un gràfic porta el seu bloc de color, si en té.
function contextCarta(p) {
  const res = { grafs: [], linies: [], amaga: [], brolls: [], stickers: [], blocs: [], zoom: null };
  if (p.tipus === "grafic") {
    const d = dibuixosGrafics[p.id];
    // Si un altre gràfic hi feia bloc, aquest anava a sota; sol, torna al seu lloc.
    const propi = p.t == null ? d && sencer(d) : p.s ? { ...p.s, limits: d?.limits ?? p.s.limits } : d && sencer(d);
    if (propi) res.grafs.push(propi);
    if (propi?.bloc && p.t != null && paletaGrafics?.[propi.bloc]) {
      res.blocs.push({ inici: propi.inici, final: propi.final, color: paletaGrafics[propi.bloc] });
    }
  }
  if (p.t == null) return res;
  const dins = (x0, x1) => x0 < p.t1 && x1 > p.t0;
  res.amaga = res.grafs.filter((g) => g.amaga_subtitols).map((g) => [g.inici, g.final]);
  res.linies = estat.subtitols !== false && estilSub ? liniesSub.filter((l) => dins(l.inici, l.final)) : [];
  if (p.tipus === "broll") res.brolls = [p.b];
  if (p.tipus === "sticker") res.stickers = [p.st];
  if (p.tipus === "zoom") res.zoom = p.k;
  return res;
}

function capaCarta(c) {
  for (const tl of c.tls) tl?.kill?.();
  c.tls = [];
  c.brollsVius = new Map();
  const { el, p, ctx } = c;
  const host = el.querySelector(".clip-capa");
  host.textContent = "";
  const capa = (classe = "capa-mostra") => { const d = document.createElement("div"); d.className = classe; host.append(d); return d; };
  c.brHost = capa("capa-br");
  const ts = capa();
  const tlSub = window.TallatSubtitols && ctx.linies.length
    ? TallatSubtitols.construeix(ts, ctx.linies, estilSub, { familia: familiaCss(estilSub), amaga: ctx.amaga }) : null;
  if (tlSub) c.tls.push(tlSub);
  if (window.TallatGrafics && paletaGrafics && ctx.grafs.length) c.tls.push(TallatGrafics.construeix(capa(), ctx.grafs, paletaGrafics, OP_GRAFICS));
  c.stHost = capa("capa-st");
  // La marca de les peces que no es veuen soles: el so (unes ones) i el zoom (un marc).
  el.querySelector(".clip-marca").innerHTML = ICONES_TAULER[p.tipus] || "";
  pintaSoCarta(c);
  // El fotograma (de la còpia lleugera, en temps de la gravació: no canvia encara que canviïn els talls).
  const img = el.querySelector(".clip-imatge");
  if (p.t == null) { img.hidden = true; } else {
    const t = originalDe(p.tp);
    c.fotograma = t;
    fotogramaDe(urlCopia(), t, true).then((dades) => {
      if (c.fotograma !== t || !dades) return;
      img.src = dades;
      img.hidden = false;
    });
  }
  escalaCarta(c);
  pintaClip(c, p.tp ?? 1.5);
}

function escalaCarta(c) {
  const w = c.el.querySelector(".clip").clientWidth;
  if (w) c.el.querySelector(".clip-capa").style.transform = `scale(${w / 1080})`;
}
function escalaTauler() { for (const c of cartesTauler.values()) escalaCarta(c); }

// Com es veu el tros en el moment m (del muntatge): les capes, el zoom, el bloc de color, el b-roll i els stickers.
function pintaClip(c, m) {
  for (const tl of c.tls) tl?.seek(m, false);
  const { el, ctx } = c;
  const media = TV.c === c ? TV.v : el.querySelector(".clip-imatge");
  const z = ctx.zoom != null && trosDe(m) === ctx.zoom ? zoomVideo : 1;
  const bloc = ctx.blocs.find((b) => m >= b.inici && m < b.final);
  const e = bloc ? pasBloc(m, bloc.inici, bloc.final) : 0;
  const actius = ctx.brolls.filter((b) => m >= b.inici && m < (b.fins ?? b.inici + b.durada));
  const partida = actius.some((b) => b.partida);
  el.querySelector(".clip-fons").style.background = bloc ? bloc.color : "";
  if (media) {
    let estil = { transform: z > 1 ? `scale(${z})` : "", clipPath: "" };
    if (e) estil = transformBloc(e, z, "0px");
    else if (partida) estil = { transform: `translateY(25%) scale(${z})`, clipPath: `inset(${50 - 25 / z}% ${50 - 50 / z}%)` };
    Object.assign(media.style, estil);
  }
  // El b-roll: a les quietes, un fotograma del clip; a la que es mou, el clip.
  const ids = new Set(actius.map((b) => b.id));
  for (const [id, t] of c.brollsVius) if (!ids.has(id)) { t.firstChild.pause?.(); t.remove(); c.brollsVius.delete(id); }
  for (const b of actius) {
    const viu = TV.c === c;
    let t = c.brollsVius.get(b.id);
    if (t && (t.firstChild.tagName === "VIDEO") !== viu) { t.firstChild.pause?.(); t.remove(); t = null; c.brollsVius.delete(b.id); }
    if (!t) {
      let contingut;
      if (viu) {
        contingut = document.createElement("video");
        Object.assign(contingut, { muted: true, playsInline: true, preload: "auto", src: b.url });
      } else {
        contingut = document.createElement("img");
        contingut.alt = "";
        fotogramaDe(b.url, Math.min(0.5, b.durada / 2)).then((dades) => { if (dades) contingut.src = dades; });
      }
      t = targetaBroll(b.caixa, contingut);
      c.brHost.append(t);
      c.brollsVius.set(b.id, t);
    }
    estilTargeta(t, b.caixa);
    Object.assign(t.style, animacioBroll(b, m));
    if (viu) {
      const v = t.firstChild;
      const desitjat = Math.min(m - b.inici, Math.max(0, b.durada - 0.05));
      if (v.readyState >= 1 && Math.abs(v.currentTime - desitjat) > 0.2) v.currentTime = desitjat;
      if (v.paused && !TV.v.paused) v.play().catch(() => {});
    }
  }
  pintaStickersCarta(c, m);
}

// Els stickers, com a pintaStickers (la mateixa posició, mida i rotació), en un tros de 1080 × 1920. A la targeta
// del sticker, s'hi pot arrossegar (vegeu mouSticker); mentre es mou, no es refà.
function pintaStickersCarta(c, m) {
  if (c.movent) return;
  const e = P?.estil_stickers || {};
  const sig = c.ctx.stickers.filter((st) => m >= st.inici && m < st.inici + st.durada).map((st) => st.id).join(",");
  if (c.stHost.dataset.sig === sig) return;
  c.stHost.dataset.sig = sig;
  c.stHost.textContent = "";
  for (const st of c.ctx.stickers) {
    if (!(m >= st.inici && m < st.inici + st.durada)) continue;
    const img = document.createElement("img");
    img.className = "sticker-viu";
    img.src = st.url;
    img.alt = "";
    img.dataset.id = st.id;
    if (c.p.tipus === "sticker") {
      img.classList.add("es-mou");
      img.title = "Arrossega'l on el vulguis";
    }
    situaSticker(img, st);
    if (e.ombra === false) img.style.setProperty("--ombra-sticker", "none");
    if (e.animacio === "cap") img.style.animation = "none";
    c.stHost.append(img);
  }
}

function pintaSoCarta(c) {
  const b = c.el.querySelector(".clip-so");
  b.innerHTML = ambSoTauler ? ICONA_SO : ICONA_MUT;
  b.title = ambSoTauler ? "Sense so" : "Amb so";
  b.setAttribute("aria-label", b.title);
  b.setAttribute("aria-pressed", String(ambSoTauler));
}

// Un sticker es mou arrossegant-lo a la seva targeta: el vídeo s'atura mentre dura i, en deixar-lo, es desa on és
// (`llocs_stickers`, a l'estat: es desfà com la resta) i surt allà al vídeo final.
function mouSticker(c, e) {
  const img = e.target.closest(".sticker-viu.es-mou");
  if (!img || e.button !== 0) return false;
  e.preventDefault();
  e.stopPropagation();
  const caixa = c.stHost.getBoundingClientRect();
  const r = img.getBoundingClientRect();
  const agafat = [e.clientX - (r.left + r.width / 2), e.clientY - (r.top + r.height / 2)];  // on l'has agafat
  const sonava = TV.c === c && TV.v && !TV.v.paused;
  if (sonava) TV.v.pause();
  c.movent = img.dataset.id;
  img.classList.add("movent");
  img.setPointerCapture(e.pointerId);
  let lloc = null;
  const mou = (ev) => {
    lloc = { x: limita((ev.clientX - agafat[0] - caixa.left) / caixa.width, 0.04, 0.96),
      y: limita((ev.clientY - agafat[1] - caixa.top) / caixa.height, 0.04, 0.96) };
    Object.assign(img.style, { left: `${lloc.x * 100}%`, top: `${lloc.y * 100}%` });
  };
  let acabat = false;
  const deixa = (ev) => {
    if (acabat) return;
    acabat = true;
    img.removeEventListener("pointermove", mou);
    for (const nom of ["pointerup", "pointercancel", "lostpointercapture"]) img.removeEventListener(nom, deixa);
    img.classList.remove("movent");
    c.movent = null;
    if (c.refes) { c.refes = false; capaCarta(c); }  // si mentrestant ha canviat alguna altra cosa
    c.mogutAra = performance.now();  // el clic que ve després de deixar-lo no és un toc a la targeta
    const id = img.dataset.id;
    if (lloc) {
      const x = Math.round(lloc.x * 1000) / 1000;
      const y = Math.round(lloc.y * 1000) / 1000;
      canvia((est) => { est.llocs_stickers = { ...(est.llocs_stickers || {}), [id]: { x, y } }; });
    }
    if (ev.pointerType === "mouse" && !c.el.querySelector(".clip").matches(":hover")) { if (TV.c === c) aturaCarta(); }
    else if (sonava && TV.c === c) TV.v.play().catch(() => {});
  };
  img.addEventListener("pointermove", mou);
  for (const nom of ["pointerup", "pointercancel", "lostpointercapture"]) img.addEventListener(nom, deixa);
  return true;
}

function instalaClip(c) {
  const clip = c.el.querySelector(".clip");
  clip.addEventListener("pointerdown", (e) => mouSticker(c, e));
  clip.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") activaCarta(c); });
  clip.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse" && TV.c === c && !c.movent) aturaCarta(); });
  clip.addEventListener("click", (e) => {
    if (e.target.closest(".clip-so") || performance.now() - (c.mogutAra || 0) < 300) return;
    if (e.pointerType !== "mouse") TV.c === c ? aturaCarta() : activaCarta(c);  // amb el dit, un toc la mou o l'atura
  });
  clip.addEventListener("keydown", (e) => {
    if ((e.key !== "Enter" && e.key !== " ") || e.target !== clip) return;  // l'altaveu, que faci de botó
    e.preventDefault();
    TV.c === c ? aturaCarta() : activaCarta(c);
  });
  clip.addEventListener("blur", (e) => { if (TV.c === c && !clip.contains(e.relatedTarget)) aturaCarta(); });
  c.el.querySelector(".clip-so").addEventListener("click", (e) => {
    e.stopPropagation();
    ambSoTauler = !ambSoTauler;
    for (const x of cartesTauler.values()) pintaSoCarta(x);
    if (TV.c !== c) activaCarta(c);
    else if (TV.v) TV.v.muted = !ambSoTauler;
    if (ambSoTauler && TV.v) TV.v.play().catch(() => {});
  });
}

// --- La targeta que es mou: un sol vídeo, el continu dels talls d'ara si ja és a punt (el temps és el del muntatge) o,
// si no, la còpia lleugera, que salta de tros en tros. ---

const TV = { v: null, c: null, raf: 0, k: 0, continu: false, so: -1 };

function videoTauler() {
  if (!TV.v) {
    TV.v = document.createElement("video");
    Object.assign(TV.v, { muted: true, playsInline: true, preload: "auto", className: "clip-media clip-viu" });
    TV.v.setAttribute("aria-hidden", "true");
  }
  return TV.v;
}

function activaCarta(c) {
  if (TV.c === c) return;
  aturaCarta();
  if (c.p.t == null || !trams.length) return;
  TV.c = c;
  c.el.classList.add("activa");
  const v = videoTauler();
  const font = previaLlesta && previaLlesta.trams === JSON.stringify(trams) ? previaLlesta.url : urlCopia();
  TV.continu = font !== urlCopia();
  if (v.getAttribute("src") !== font) v.src = font;
  v.muted = !ambSoTauler;
  c.el.querySelector(".clip-imatge").after(v);
  c.el.querySelector(".clip-imatge").hidden = true;
  for (const t of c.brollsVius.values()) t.remove();  // els del b-roll passen a ser clips
  c.brollsVius.clear();
  TV.so = -1;
  posaTempsTauler(c.p.t0);
  v.play().catch(() => {});
  TV.raf = requestAnimationFrame(pasTauler);
}

function posaTempsTauler(m) {
  const v = TV.v;
  if (TV.continu) { v.currentTime = m; return; }
  TV.k = Math.min(trosDe(m), trams.length - 1);
  v.currentTime = trams[TV.k][0] + Math.max(0, m - acum[TV.k]);
}

const tempsTauler = () => (TV.continu ? TV.v.currentTime : acum[TV.k] + (TV.v.currentTime - trams[TV.k][0]));

function pasTauler() {
  const c = TV.c;
  if (!c) return;
  const v = TV.v;
  if (!TV.continu && !v.seeking && v.currentTime >= trams[TV.k][1] - 0.03) {
    // La còpia lleugera: al final del tros, salta al següent (o torna a començar).
    if (TV.k + 1 < trams.length && acum[TV.k + 1] < c.p.t1) { TV.k++; v.currentTime = trams[TV.k][0]; }
    else posaTempsTauler(c.p.t0);
  }
  let m = v.seeking ? NaN : tempsTauler();
  if (m >= c.p.t1 || v.ended) {
    const acabat = v.ended;
    posaTempsTauler(c.p.t0);
    if (acabat) v.play().catch(() => {});  // al final del fitxer s'atura sol: assignar-li el temps no el reprèn
    m = c.p.t0;
    TV.so = -1;
  }
  if (Number.isFinite(m)) {
    pintaClip(c, m);
    c.el.querySelector(".clip-progres i").style.width = `${limita((m - c.p.t0) / (c.p.t1 - c.p.t0), 0, 1) * 100}%`;
    // L'efecte de so de la targeta, quan arriba el seu moment (si s'hi escolta).
    if (c.p.tipus === "so" && ambSoTauler && TV.so < c.p.t && m >= c.p.t) escoltaSo(c.p.so.so);
    TV.so = m;
  }
  TV.raf = requestAnimationFrame(pasTauler);
}

function aturaCarta() {
  const c = TV.c;
  if (!c) return;
  cancelAnimationFrame(TV.raf);
  TV.c = null;
  TV.v.pause();
  TV.v.remove();
  for (const t of c.brollsVius.values()) { t.firstChild.pause?.(); t.remove(); }
  c.brollsVius.clear();
  c.el.classList.remove("activa");
  const img = c.el.querySelector(".clip-imatge");
  img.hidden = !img.getAttribute("src");
  c.el.querySelector(".clip-progres i").style.width = "0";
  pintaClip(c, c.p.tp ?? 0);
}

// Les quietes que es veuen: les peces s'hi mouen (sobre el fotograma), a poc a poc i amb una pausa al final.
const MOU_QUIETES = !matchMedia("(prefers-reduced-motion: reduce)").matches;
const cartaDe = new WeakMap();  // l'element de cada targeta → la targeta
const observaTauler = new IntersectionObserver((entrades) => {
  for (const e of entrades) {
    const c = cartaDe.get(e.target);
    if (!c) continue;
    if (e.isIntersecting) visiblesTauler.add(c); else visiblesTauler.delete(c);
  }
});
let darrerPasQuietes = 0;
function animaQuietes(ara) {
  requestAnimationFrame(animaQuietes);
  if (!MOU_QUIETES || document.hidden || $("#tauler").hidden || $("#tauler").classList.contains("esperant")
    || ara - darrerPasQuietes < 40) return;  // 25 per segon; mentre Claude prepara la ronda, quietes
  darrerPasQuietes = ara;
  for (const c of visiblesTauler) {
    if (c === TV.c || c.p.t == null || !c.tls.length) continue;
    const d = c.p.t1 - c.p.t0;
    const fase = ((ara / 1000 + c.desfase) % (d + 1.2));
    pintaClip(c, fase > d ? c.p.tp : c.p.t0 + fase);
  }
}
requestAnimationFrame(animaQuietes);

// --- Els fotogrames de les quietes: un sol vídeo amagat que salta d'un moment a l'altre, d'un en un. ---

const fotogrames = new Map();         // "url|t" → imatge (data URL) o null
const fotogramesPendents = new Map();
const cuaFotogrames = [];
const capturadors = new Map();        // un vídeo per fitxer (la còpia lleugera i cada b-roll): canviar-lo és lent

function fotogramaDe(url, t, retalla = false) {
  const clau = `${url}|${t.toFixed(2)}|${retalla}`;
  if (fotogrames.has(clau)) return Promise.resolve(fotogrames.get(clau));
  if (!fotogramesPendents.has(clau)) {
    fotogramesPendents.set(clau, new Promise((resol) => {
      cuaFotogrames.push({ url, t, retalla, clau, resol });
      if (cuaFotogrames.length === 1) capturaSeguent();
    }));
  }
  return fotogramesPendents.get(clau);
}

async function capturaSeguent() {
  const feina = cuaFotogrames[0];
  if (!feina) return;
  const dades = await captura(feina.url, feina.t, feina.retalla).catch(() => null);
  fotogrames.set(feina.clau, dades);
  fotogramesPendents.delete(feina.clau);
  cuaFotogrames.shift();
  feina.resol(dades);
  capturaSeguent();
}

function capturadorDe(url) {
  let v = capturadors.get(url);
  if (v) return v;
  if (capturadors.size >= 4) {  // els quatre darrers; el més vell se'n va
    const [vell, el] = capturadors.entries().next().value;
    el.removeAttribute("src");
    el.load();
    el.remove();
    capturadors.delete(vell);
  }
  v = document.createElement("video");
  Object.assign(v, { muted: true, playsInline: true, preload: "auto", className: "capturador" });
  v.setAttribute("aria-hidden", "true");
  document.body.append(v);  // el Safari no dibuixa un vídeo que no és a la pàgina
  capturadors.set(url, v);
  return v;
}

function captura(url, t, retalla) {
  return new Promise((resol) => {
    const v = capturadorDe(url);
    let temps = null;
    const acaba = (r) => { clearTimeout(temps); v.removeEventListener("seeked", fet); v.removeEventListener("error", falla); resol(r); };
    const fet = () => {
      try {
        const c = document.createElement("canvas");
        // Les de la targeta, retallades com el vídeo (9:16); les del b-roll, senceres (la targeta ja les retalla).
        if (retalla) [c.width, c.height] = [270, 480];
        else { const r = Math.min(1, 360 / Math.max(v.videoWidth, v.videoHeight)); [c.width, c.height] = [Math.round(v.videoWidth * r), Math.round(v.videoHeight * r)]; }
        const r = Math.max(c.width / v.videoWidth, c.height / v.videoHeight);
        const [w, h] = [v.videoWidth * r, v.videoHeight * r];
        c.getContext("2d").drawImage(v, (c.width - w) / 2, (c.height - h) / 2, w, h);
        acaba(c.toDataURL("image/jpeg", 0.78));
      } catch { acaba(null); }
    };
    const falla = () => acaba(null);
    temps = setTimeout(() => acaba(null), 8000);
    v.addEventListener("error", falla, { once: true });
    const salta = () => {
      const desti = limita(t, 0, Math.max(0, (v.duration || t + 1) - 0.05));
      if (Math.abs(v.currentTime - desti) < 0.001 && v.readyState >= 2) { fet(); return; }
      v.addEventListener("seeked", fet, { once: true });
      v.currentTime = desti;
    };
    if (v.getAttribute("src") !== url) { v.src = url; v.addEventListener("loadeddata", salta, { once: true }); } else salta();
  });
}

// --- La ronda següent ---

const notaRondaDarrera = () => notesVisibles().filter((n) => n.tipus === "ronda").at(-1) || null;

function pintaEstatRonda() {
  const n = notaRondaDarrera();
  const hiHa = !$("#ronda").hidden;
  const el = hiHa ? $("#estat-ronda") : $("#estat-ronda-buit");
  (hiHa ? $("#estat-ronda-buit") : $("#estat-ronda")).hidden = true;
  const boto = hiHa ? $("#demana-ronda") : $("#primeres-propostes");
  const enCurs = n && ["enviada", "treballant"].includes(n.estat);
  boto.disabled = !!enCurs;
  const darrer = n?.fil.filter((m) => m.de === "claude").at(-1);
  // Mentre Claude la prepara (fins que arriba una ronda més nova que la que hi havia en demanar-la), les targetes es
  // queden quietes i esvaïdes, amb un rètol al mig.
  const ara = estat.ronda || 0;
  const espera = hiHa && !!enCurs && (n.estat === "treballant" || claudeConnectat) && ara <= (n.ronda ?? ara)
    && esperaTreta !== n.id;
  $("#tauler").classList.toggle("esperant", espera);
  $("#esperant-ronda").hidden = !espera;
  $("#esperant-ronda-titol").textContent = ara ? `Claude prepara la ronda ${ara + 1}…` : "Claude prepara les propostes…";
  // Quan arriba: a dalt, què hi ha de nou i el que en diu Claude.
  const nov = novetatRonda;
  $("#novetat-ronda").hidden = !nov;
  const resposta = nov && n?.estat === "feta" && darrer ? darrer.text : "";
  if (nov) {
    const parts = [nov.nous && `${nov.nous} ${nov.nous === 1 ? "proposta nova" : "propostes noves"}`,
      nov.canviats && `${nov.canviats} ${nov.canviats === 1 ? "canviada" : "canviades"}`].filter(Boolean);
    $("#novetat-ronda-titol").textContent = `La ronda ${nov.ronda} és a punt.`;
    $("#novetat-ronda-compte").textContent = parts.length ? `Hi ha ${parts.join(" i ")}.` : "";
    $("#novetat-ronda-claude").hidden = !resposta;
    $("#novetat-ronda-claude").textContent = `Claude: ${resposta}`;
  }
  let text = "";
  if (espera) text = "";
  else if (n?.estat === "enviada") {
    text = claudeConnectat ? "Enviada a Claude. Ara s'hi posa." : "Enviada. Claude encara no hi és: escriu-li «mira les meves notes» al xat.";
  } else if (n?.estat === "treballant") text = "Claude hi treballa…";
  else if (n?.estat === "pregunta" && darrer) text = `Claude et pregunta: ${darrer.text} (respon-li a Edita, a les notes)`;
  else if (n?.estat === "feta" && darrer && !resposta && Date.now() / 1000 - darrer.quan < 15 * 60) text = `Claude: ${darrer.text}`;
  el.hidden = !text;
  el.textContent = text;
  el.classList.toggle("en-curs", !!enCurs);
}

let demanantRonda = false;
async function demanaRonda() {
  const camp = $("#nota-ronda");
  // Amb Retorn al camp de la nota també s'hi arriba: que no se'n demanin dues mentre n'hi ha una en curs.
  const boto = $("#tauler-buit").hidden ? $("#demana-ronda") : $("#primeres-propostes");
  if (demanantRonda || boto.disabled) return;
  demanantRonda = true;
  try {
    await canvisDesats();  // que Claude vegi els vots d'ara
    respostaNotes(await api("/api/notes", { accio: "ronda", text: $("#tauler-buit").hidden ? camp.value : "" }));
    camp.value = "";
    votatsAra.clear();
    novetatRonda = null;
    avis("Enviat a Claude. Quan acabi, ho veuràs aquí.", 4000);
  } catch (e) { avis(e.message, 5000); }
  demanantRonda = false;
  pintaTauler();
}

// --- Una peça teva («+ Afegeix»): què és, el fitxer i la paraula on surt. Es posa com les instruccions a mà (la
// targeta diu «Teva» i ja és un Sí). ---

const afegint = { tipus: null, fitxer: null, mostra: null };

function obreAfegeix() {
  if (sona()) atura();
  aturaCarta();
  $("#afegeix-que").hidden = false;
  $("#afegeix-on").hidden = true;
  $("#velo").hidden = false;
  $("#full-afegeix").hidden = false;
  $("#full-afegeix [data-afegeix]").focus();
}

function tancaAfegeix() {
  $("#full-afegeix").hidden = true;
  if ($("#full-final").hidden && $("#full-estil").hidden && $("#full-marca").hidden) $("#velo").hidden = true;
  if (afegint.mostra) URL.revokeObjectURL(afegint.mostra);
  Object.assign(afegint, { tipus: null, fitxer: null, mostra: null });
  $("#afegeix-peca").focus({ preventScroll: true });
}

function triaFitxerPeca(tipus) {
  afegint.tipus = tipus;
  const tria = $("#fitxer-peca");
  tria.accept = tipus === "sticker" ? "image/png,image/webp,image/gif,image/svg+xml" : "image/*,video/*";
  tria.value = "";
  tria.click();
}

function fitxerPecaTriat(fitxer) {
  if (!fitxer || !afegint.tipus) return;
  afegint.fitxer = fitxer;
  if (afegint.mostra) URL.revokeObjectURL(afegint.mostra);
  afegint.mostra = fitxer.type.startsWith("image/") ? URL.createObjectURL(fitxer) : null;
  const img = $("#afegeix-mostra");
  img.hidden = !afegint.mostra;
  if (afegint.mostra) img.src = afegint.mostra;
  $("#afegeix-nom").textContent = `${afegint.tipus === "sticker" ? "Sticker" : "Imatge o vídeo"}: «${fitxer.name}»`;
  pintaFrasesAfegeix();
  $("#afegeix-que").hidden = true;
  $("#afegeix-on").hidden = false;
  $("#frases-afegeix button")?.focus();
}

// Les frases del vídeo tal com sonen ara, amb cada paraula per tocar (i el segon on comença cada frase).
function pintaFrasesAfegeix() {
  const cont = $("#frases-afegeix");
  cont.textContent = "";
  const paraules = [];
  for (let k = 0; k < P.paraules.length; k++) if (!esFora(k)) paraules.push({ k, t: muntatgeDe(P.paraules[k].inici) });
  paraules.sort((a, b) => a.t - b.t);
  let fila = null;
  let compte = 0;
  for (const { k, t } of paraules) {
    if (!fila) {
      fila = document.createElement("div");
      fila.className = "frase-afegeix";
      fila.innerHTML = `<span class="temps">${fmt(t)}</span><span class="paraules"></span>`;
      cont.append(fila);
      compte = 0;
    }
    const text = String(estat.correccions?.[k] ?? P.paraules[k].text).trim();
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.paraula = String(k);
    b.textContent = text;
    b.setAttribute("aria-label", `${text}, al ${fmt(t)}`);
    fila.lastElementChild.append(b, " ");
    if (/[.?!…]["'»”]*$/.test(text) || ++compte >= 16) fila = null;
  }
}

async function posaPecaTeva(paraula) {
  const { tipus, fitxer } = afegint;
  if (!tipus || !fitxer) return;
  tancaAfegeix();
  avis(`Pujant «${fitxer.name}»…`, 30000);
  const abans = new Set(instruccions.map((i) => i.id));
  const url = (f) => `/api/broll/puja?paraula=${paraula}&tipus=${tipus}&nom=${encodeURIComponent(f.name)}`;
  if (!(await pujaFitxers([fitxer], url))) return;
  avis(tipus === "sticker" ? "Sticker posat. El tens al tauler." : "Posat. El tens al tauler.", 4000);
  const nova = instruccions.find((i) => !abans.has(i.id));
  if (!nova) return;
  if (!["totes", "si"].includes(filtreTauler)) {  // les peces teves són Sí: amb un altre filtre no es veuria
    filtreTauler = "totes";
    pintaTauler();
  }
  requestAnimationFrame(() => mostraCarta(`${tipus}:${nova.id}`));
}

// Porta la targeta a la vista i la fa brillar un moment (la que s'acaba de posar).
function mostraCarta(clau) {
  const c = cartesTauler.get(clau);
  if (!c) return;
  c.el.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  c.el.classList.remove("llum");
  void c.el.offsetWidth;
  c.el.classList.add("llum");
}

function instalaTauler() {
  for (const b of $$("#filtres-tauler button")) {
    b.addEventListener("click", () => { filtreTauler = b.dataset.filtre; pintaTauler(); });
  }
  $("#demana-ronda").addEventListener("click", demanaRonda);
  $("#ja-esta").addEventListener("click", () => { canviaEstacio("revisa"); comencaRender("esborrany"); });
  $("#afegeix-peca").addEventListener("click", obreAfegeix);
  for (const b of $$("#encaix button")) {
    b.addEventListener("click", () => {
      if ((estat.encaix || "retalla") === b.dataset.encaix) return;
      canvia((e) => { e.encaix = b.dataset.encaix; });
      pintaEncaix(true);
    });
  }
  $("#tanca-afegeix").addEventListener("click", tancaAfegeix);
  for (const b of $$("#full-afegeix [data-afegeix]")) b.addEventListener("click", () => triaFitxerPeca(b.dataset.afegeix));
  $("#fitxer-peca").addEventListener("change", (e) => fitxerPecaTriat(e.target.files[0]));
  $("#afegeix-un-altre").addEventListener("click", () => triaFitxerPeca(afegint.tipus));
  $("#frases-afegeix").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-paraula]");
    if (b) posaPecaTeva(Number(b.dataset.paraula));
  });
  $("#full-afegeix").addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); tancaAfegeix(); } });
  $("#continua-votant").addEventListener("click", () => { esperaTreta = notaRondaDarrera()?.id ?? null; pintaEstatRonda(); });
  $("#tanca-novetat-ronda").addEventListener("click", () => { novetatRonda = null; pintaEstatRonda(); });
  $("#primeres-propostes").addEventListener("click", demanaRonda);
  $("#nota-ronda").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); demanaRonda(); } });
  $("#tauler-exporta").addEventListener("click", obreFinal);
  $("#torna-tauler").addEventListener("click", () => { tancaElQueHiHagi(); deixaPeca(); });
  new ResizeObserver(escalaTauler).observe($("#graella-tauler"));
  // Quan s'obre o es tanca un panell de l'esquerra (els colors, el b-roll, el so…), el tauler s'amaga o torna.
  new MutationObserver(() => { if (vestint) actualitzaTauler(); }).observe($(".barra"), { attributes: true, attributeFilter: ["class"] });
}

// --- La dreta: totes les peces o la que has tocat ---

function pintaDreta({ refes = false, enfoca = false } = {}) {
  if (!vestint || !estat) return;
  actualitzaTauler();
  $("#torna-tauler").hidden = !!pecaTriada;  // amb una peça oberta, ja hi és, a dalt de l'editor
  pintaPestanyesDreta();
  for (const b of $$("[data-desfes]")) b.disabled = !desfer.length;
  for (const b of $$("[data-refes]")) b.disabled = !refer.length;
  const cont = $("#peca");
  const perVenir = pecaPerVeure && pecaPerVeure.tipus === pecaTriada?.tipus && pecaPerVeure.id === pecaTriada?.id;
  const deTotElVideo = ["subtitols", "titol"].includes(pecaTriada?.tipus);
  if (pecaTriada && !perVenir && !deTotElVideo && !pecaDe(pecaTriada.tipus, pecaTriada.id) && !(pecaTriada.tipus === "grafic" && graficDe(pecaTriada.id))) {
    pecaTriada = null;
    refes = true;
  }
  const sig = JSON.stringify([pecaTriada, pecaTriada ? editorSig() : pecesDelVideo(), tretsOberts, paletaGrafics,
    pecaTriada ? null : (estat.grafics || []).filter((g) => g.estat === "tret").map((g) => g.id)]);
  if (!refes && sig === cont.dataset.sig) return;
  cont.dataset.sig = sig;
  // Si s'hi escriu, el camp es refà amb el que hi havia escrit i el cursor al mateix lloc.
  const actiu = document.activeElement;
  const escrit = cont.contains(actiu) && actiu.dataset.camp
    ? { camp: actiu.dataset.camp, valor: actiu.value, a: actiu.selectionStart, b: actiu.selectionEnd } : null;
  for (const tl of liniesDreta) tl?.kill?.();
  liniesDreta = [];
  cont.textContent = "";
  if (pecaTriada) pintaEditor(cont, enfoca && !escrit);
  else pintaLlistaPeces(cont);
  const camp = escrit && cont.querySelector(`[data-camp="${escrit.camp}"]`);
  if (camp) {
    camp.value = escrit.valor;
    camp.focus({ preventScroll: true });
    camp.setSelectionRange(escrit.a, escrit.b);
  }
}

function editorSig() {
  const { tipus, id } = pecaTriada;
  if (tipus === "subtitols") return [estilSub, estat.subtitols, estat.estil?.subtitols];
  if (tipus === "titol") return [estilTitol, estat.titol, estat.estil?.titol];
  if (tipus === "grafic") return [graficDe(id), dibuixosGrafics[id], graficsMuntatge.find((x) => x.id === id)?.inici];
  if (tipus === "broll") return [brollsMuntatge.find((b) => b.id === id), instruccions.find((i) => i.id === id)];
  if (tipus === "zoom") { const k = tramDeZoom(id); return [zoomsTram[k], trams[k], acum[k]]; }
  return [(estat.sons || []).find((s) => s.id === id), efectesMuntatge.find((x) => x.clau === `so:${id}`)?.t];
}

function filaPeca(p) {
  const b = document.createElement("button");
  b.className = `fila-peca peca-${p.tipus}`;
  b.innerHTML = `<span class="icona-peca" aria-hidden="true">${ICONES_PECA[p.tipus]}</span>
    <span class="fila-peca-text"><strong></strong><span></span></span><span class="temps-peca"></span>`;
  b.querySelector("strong").textContent = p.nom;
  b.querySelector(".fila-peca-text span").textContent = p.avis || p.detall;
  b.querySelector(".fila-peca-text span").classList.toggle("avis-peca", !!p.avis);
  b.querySelector(".temps-peca").textContent = p.t != null ? fmt(p.t) : "";
  if (p.claude) {
    const de = document.createElement("span");
    de.className = "de-claude";
    de.textContent = "Claude";
    de.title = "L'ha proposat Claude";
    b.querySelector("strong").after(de);
  }
  b.setAttribute("aria-label", `${p.nom}${p.t != null ? `, al ${fmt(p.t)}` : ""}: ${p.avis || p.detall}`);
  b.addEventListener("click", () => triaPeca(p.tipus, p.id, { ves: true }));
  return b;
}

function pintaLlistaPeces(cont) {
  const peces = pecesDelVideo();
  const cap = document.createElement("h2");
  cap.className = "cap-peces";
  cap.innerHTML = 'Al vídeo <span class="compte"></span>';
  cap.querySelector(".compte").textContent = peces.length ? String(peces.length) : "";
  cont.append(cap);
  if (!peces.length) {
    const p = document.createElement("p");
    p.className = "buit-peces";
    p.textContent = "Encara no hi ha cap peça. Al tauler, demana-li propostes a Claude.";
    cont.append(p);
  }
  const llista = document.createElement("div");
  llista.className = "llista-peces";
  for (const p of peces) llista.append(filaPeca(p));
  cont.append(llista);
  const trets = (estat.grafics || []).filter((g) => g.estat === "tret");
  if (!trets.length) return;
  const fila = document.createElement("button");
  fila.className = "fila-fetes";
  fila.setAttribute("aria-expanded", String(tretsOberts));
  fila.innerHTML = '<span></span><svg class="xebro" viewBox="0 0 20 20" aria-hidden="true"><path d="m8 5 5 5-5 5"/></svg>';
  fila.firstChild.textContent = `${trets.length} ${trets.length === 1 ? "gràfic tret" : "gràfics trets"}`;
  fila.addEventListener("click", () => { tretsOberts = !tretsOberts; pintaDreta({ refes: true }); });
  cont.append(fila);
  if (!tretsOberts) return;
  for (const g of trets) {
    const f = document.createElement("div");
    f.className = "fila-tret";
    f.innerHTML = '<span class="fila-peca-text"><strong></strong><span></span></span><button class="enllac">Torna\'l a posar</button>';
    f.querySelector("strong").textContent = NOMS_GRAFIC[g.tipus] || g.tipus;
    f.querySelector(".fila-peca-text span").textContent = textGrafic(g);
    f.querySelector("button").addEventListener("click", () => { treuGrafic(g.id, false); triaPeca("grafic", g.id, { ves: true }); });
    cont.append(f);
  }
}

function pintaVesHi(ves, p) {
  ves.hidden = p?.t == null;
  if (p?.t != null) ves.textContent = fmt(p.t);
}

// La capçalera de l'editor: tornar a la llista, què és i quan surt (en tocar-ho, el vídeo hi va).
function capEditor(cont, p, nom) {
  const cap = document.createElement("div");
  cap.className = `cap-editor peca-${pecaTriada.tipus}`;
  cap.innerHTML = `<button class="enllac tornar">‹ Tauler</button>
    <div class="titol-editor"><span class="icona-peca" aria-hidden="true">${ICONES_PECA[pecaTriada.tipus]}</span>
    <h2></h2><button class="temps-nota ves-hi" title="Ves a aquest moment"></button></div>`;
  cap.querySelector("h2").textContent = nom;
  pintaVesHi(cap.querySelector(".ves-hi"), p);
  cap.querySelector(".ves-hi").addEventListener("click", () => {
    const q = pecaTriada && pecaDe(pecaTriada.tipus, pecaTriada.id);
    if (q?.t != null) vesA(q.t + (q.tipus === "grafic" ? 0.6 : 0.1));
  });
  cap.querySelector(".tornar").addEventListener("click", deixaPeca);
  cont.append(cap);
  if (p?.avis) {
    const a = document.createElement("p");
    a.className = "avis-peca";
    a.textContent = p.tipus === "grafic" && dibuixosGrafics[p.id]?.falta ? `${p.avis}: fins que no hi siguin, no surt al vídeo.`
      : `${p.avis}: la seva frase s'ha tret.`;
    cont.append(a);
  }
}

function camp(cont, etiqueta, control, ajuda) {
  const c = document.createElement("label");
  c.className = "camp camp-peca";
  const e = document.createElement("span");
  e.className = "etiqueta";
  e.textContent = etiqueta;
  c.append(e, control);
  if (ajuda) {
    const p = document.createElement("span");
    p.className = "detall ajuda-camp";
    p.textContent = ajuda;
    c.append(p);
  }
  cont.append(c);
  return c;
}

function segmentatPeca(cont, etiqueta, opcions, actual, tria) {
  const c = document.createElement("div");
  c.className = "camp camp-peca";
  const e = document.createElement("span");
  e.className = "etiqueta";
  e.textContent = etiqueta;
  const seg = document.createElement("div");
  seg.className = "segmentat ample";
  seg.setAttribute("role", "radiogroup");
  seg.setAttribute("aria-label", etiqueta);
  for (const [valor, text] of opcions) {
    const b = document.createElement("button");
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(valor === actual));
    b.textContent = text;
    b.addEventListener("click", () => tria(valor));
    seg.append(b);
  }
  c.append(e, seg);
  cont.append(c);
}

// Un camp de text que desa sol mentre s'escriu (una mica després). `valid`: si el text encara no serveix (buit,
// per exemple), no es desa: el servidor llençaria el gràfic sencer.
let temporitzadorPeca = null;
function campText(valor, { mida, linies = 1, placeholder = "", valid = (v) => v.trim(), desa, clau }) {
  const el = document.createElement(linies > 1 ? "textarea" : "input");
  el.dataset.camp = `${pecaTriada?.id}:${clau}`;
  if (linies > 1) el.rows = linies; else el.type = "text";
  Object.assign(el, { value: valor, placeholder, className: "camp-text" });
  if (mida) el.maxLength = mida;
  el.autocomplete = "off";
  const fes = () => { clearTimeout(temporitzadorPeca); temporitzadorPeca = null; if (valid(el.value)) desa(el.value); };
  el.addEventListener("input", () => { clearTimeout(temporitzadorPeca); temporitzadorPeca = setTimeout(fes, 700); });
  el.addEventListener("blur", () => { if (temporitzadorPeca) fes(); });
  el.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.stopPropagation(); el.blur(); }
    if (e.key === "Enter" && linies === 1) { e.preventDefault(); el.blur(); }
  });
  return el;
}

const textPla = (v) => " ".concat(v).split(/\s+/).filter(Boolean).join(" ");

function pintaEditor(cont, enfoca) {
  const { tipus, id } = pecaTriada;
  const p = pecaDe(tipus, id);
  const cos = document.createElement("div");
  cos.className = "cos-editor";
  const posa = () => cont.append(cos);  // a la pàgina abans d'omplir-lo: les miniatures en mesuren la mida
  if (tipus === "grafic") {
    const g = graficDe(id);
    capEditor(cont, p, NOMS_GRAFIC[g.tipus] || g.tipus);
    posa();
    editorGrafic(cos, g);
  } else if (tipus === "broll") {
    capEditor(cont, p, "B-roll");
    posa();
    editorBroll(cos, id);
  } else if (tipus === "subtitols") {
    capEditor(cont, null, "Subtítols");
    posa();
    editorSubtitols(cos);
  } else if (tipus === "titol") {
    capEditor(cont, null, "Títol del ganxo");
    posa();
    editorTitol(cos);
  } else if (tipus === "zoom") {
    capEditor(cont, p, "Zoom");
    posa();
    const t = document.createElement("p");
    t.className = "detall";
    const k = tramDeZoom(id);
    t.textContent = k >= 0 ? `El vídeo s'apropa en tot aquest tros, d'un tall al següent: de ${fmt(acum[k])} a `
      + `${fmt(acum[k] + trams[k][1] - trams[k][0])}.` : "";
    cos.append(t);
    accionsPeca(cos, "Treu el zoom", () => treuZoom(id));
  } else {
    const s = (estat.sons || []).find((x) => x.id === id);
    capEditor(cont, p, NOMS_SO[s?.so] || "So");
    posa();
    editorSo(cos, s);
  }
  if (enfoca) cos.querySelector("textarea, input")?.focus({ preventScroll: true });
}

function accionsPeca(cos, textTreu, treu, extra) {
  const fila = document.createElement("div");
  fila.className = "accions-peca";
  if (extra) fila.append(extra);
  const b = document.createElement("button");
  b.className = "enllac perill";
  b.textContent = textTreu;
  b.addEventListener("click", treu);
  fila.append(b);
  cos.append(fila);
}

function editorGrafic(cos, g) {
  const id = g.id;
  const d = dibuixosGrafics[id];
  const mida = MIDA_TEXT_GRAFIC[g.tipus];
  const ambText = (etiqueta, ajuda, opcions = {}) => camp(cos, etiqueta, campText(g.text, { mida, clau: "text", ...opcions,
    desa: (v) => canviaGrafic(id, { text: textPla(v) }) }), ajuda);
  if (g.motiu && (g.estat === "proposat" || g.estat === "canvia")) {
    const m = document.createElement("p");
    m.className = "motiu-claude";
    m.textContent = `Claude: ${g.motiu}`;
    cos.append(m);
  }
  if (g.estat === "canvia" && g.nota) {
    const n = document.createElement("p");
    n.className = "detall nota-grafic-vella";
    n.textContent = `La teva nota: ${g.nota}`;
    cos.append(n);
  }
  if (g.tipus === "web" || g.tipus in MAX_FOTOS) {
    const imatges = document.createElement("div");
    imatges.className = "grafic-imatges";
    pintaImatgesGrafic(imatges, g);
    cos.append(imatges);
  }
  if (g.tipus === "frase") ambText("El text", "El que posis *entre asteriscs* surt destacat.", { linies: 2 });
  else if (g.tipus === "marcador") ambText("El text", "El que posis *entre asteriscs* porta el marcador (si no n'hi poses, tota la frase).", { linies: 2 });
  else if (g.tipus === "etiqueta" || g.tipus === "anotacio") ambText("El text");
  else if (g.tipus === "crida") ambText("El text", "", { placeholder: estilMarca?.crida || "Segueix-me per a més",
    valid: (v) => v.trim() || estilMarca?.crida });
  else if (g.tipus === "notificacio" || g.tipus === "comentari") {
    camp(cos, g.tipus === "comentari" ? "Qui l'ha escrit" : "Qui l'envia",
      campText(g.de || "", { mida: 30, clau: "de", valid: () => true, desa: (v) => canviaGrafic(id, { de: textPla(v) }) }));
    ambText(g.tipus === "comentari" ? "El comentari" : "El missatge", "", { linies: 2 });
  } else if (g.tipus === "numero") {
    camp(cos, "La xifra", campText(g.xifra || "", { mida: 24, clau: "xifra", valid: (v) => /\d/.test(v),
      desa: (v) => canviaGrafic(id, { xifra: textPla(v) }) }), "Compta des de zero: 73 %, 10.000 €…");
    ambText("El text de sota", "", { valid: () => true });
  } else if (g.tipus === "progres") {
    camp(cos, "La xifra", campText(g.xifra || "", { mida: 24, clau: "xifra", valid: (v) => fraccioProgres(v) != null,
      desa: (v) => canviaGrafic(id, { xifra: textPla(v) }) }), "Un percentatge (70 %) o una part d'un total (3 de 5, 7/10).");
    ambText("El text de sota", "", { valid: () => true });
    segmentatPeca(cos, "Forma", [["cercle", "Cercle"], ["barra", "Barra"]], g.forma || "cercle", (forma) => canviaGrafic(id, { forma }));
  } else if (g.tipus === "web") ambText("L'adreça de dalt", "", { placeholder: "elteuweb.cat", valid: () => true });
  else if (g.tipus in MAX_FOTOS) ambText("Un títol", "", { valid: () => true, placeholder: "Si no en vols, deixa-ho buit" });
  else if (g.tipus === "publicacio" || g.tipus === "segueix") {
    camp(cos, g.tipus === "segueix" ? "El compte" : "Qui l'ha escrit",
      campText(g.de || "", { mida: 30, clau: "de", valid: () => true, desa: (v) => canviaGrafic(id, { de: textPla(v) }) }));
    ambText(g.tipus === "segueix" ? "Una línia de presentació" : "El que diu", "",
      g.tipus === "segueix" ? { valid: () => true, placeholder: "un vídeo nou cada setmana" } : { linies: 3 });
  } else if (g.tipus === "rec") ambText("A la cantonada de baix (si vols)", "", { valid: () => true, placeholder: "dia 1" });
  if (g.tipus === "ratllat") {
    ambText("A dalt (si vols)", "", { valid: () => true, placeholder: "no és…" });
    camp(cos, "El que es ratlla i el que hi va, un a cada línia",
      campText(g.punts.map((x) => x.text).join("\n"), { linies: 2, clau: "punts",
        valid: (v) => v.split("\n").filter((l) => l.trim()).length >= 2,
        desa: (v) => canviaGrafic(id, { punts: v.split("\n").map((l) => textPla(l).slice(0, 80)).filter(Boolean).slice(0, 2)
          .map((text, k) => ({ text, paraula: g.punts[k]?.text === text ? g.punts[k].paraula : null })) }) }));
  }
  if (g.tipus === "llista" || g.tipus === "xat" || g.tipus === "notes") {
    if (g.tipus !== "xat") ambText("El títol", "", { valid: () => true, placeholder: "Si no en vols, deixa-ho buit" });
    const valor = g.punts.map((x) => x.text).join("\n");
    camp(cos, g.tipus === "xat" ? "Els missatges, un a cada línia" : g.tipus === "notes" ? "Les línies de la nota" : "Els punts, un a cada línia",
      campText(valor, { linies: Math.min(6, Math.max(3, g.punts.length + 1)), clau: "punts",
        valid: (v) => v.split("\n").some((l) => l.trim()),
        desa: (v) => canviaGrafic(id, { punts: v.split("\n").map((l) => textPla(l).slice(0, 80)).filter(Boolean).slice(0, 6)
          .map((text, k) => ({ text, paraula: null, ...(g.tipus === "xat" ? { costat: g.punts[k]?.costat || (k % 2 ? "enviat" : "rebut") } : {}) })) }) }),
      g.tipus === "xat" ? "Un a l'esquerra (el que reps) i l'altre a la dreta (el que envies), per torns."
        : g.tipus === "notes" ? "S'escriuen d'una en una." : "Surten d'un en un.");
  }
  if (g.tipus === "anotacio") {
    segmentatPeca(cos, "Forma", [["fletxa", "Fletxa"], ["cercle", "Cercle"], ["subratllat", "Subratllat"]], g.forma || "fletxa",
      (forma) => canviaGrafic(id, { forma }));
    segmentatPeca(cos, "Costat", [["esquerra", "Esquerra"], ["dreta", "Dreta"]], g.costat || "esquerra",
      (costat) => canviaGrafic(id, { costat }));
  }
  // L'estil, en dibuixos (els quatre; primer els de la marca).
  if (d && window.TallatGrafics && paletaGrafics) {
    const c = document.createElement("div");
    c.className = "camp camp-peca";
    c.innerHTML = '<span class="etiqueta">Estil</span><div class="estils-grafic" role="radiogroup" aria-label="Estil del gràfic"></div>';
    const fila = c.querySelector(".estils-grafic");
    cos.append(c);
    for (const [estil, nom] of [["net", "Net"], ["mac", "Mac"], ["scrapbook", "Scrapbook"], ["editorial", "Editorial"]]) {
      const b = document.createElement("button");
      b.className = "estil";
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String((g.estil || d.estil) === estil));
      b.innerHTML = '<span class="estil-mostra"></span><span class="nom-estil"></span>';
      b.querySelector(".nom-estil").textContent = nom;
      b.addEventListener("click", () => canviaGrafic(id, { estil }));
      fila.append(b);
      const tl = dibuixaMini(b.firstChild, { ...d, estil, posicio: "mig", limits: [0, 1920] }, { centra: true });
      if (tl) liniesDreta.push(tl);
    }
  }
  const posicio = typeof g.posicio === "number" ? null : g.posicio || d?.posicio;
  segmentatPeca(cos, "On surt", [["dalt", "Dalt"], ["mig", "Mig"], ["baix", "Baix"]], posicio,
    (valor) => canviaGrafic(id, { posicio: valor }));
  // La durada (si no es diu, la de cada tipus; amb «fins», fins a una paraula: tocar-la ho treu).
  const durada = g.durada ?? DURADES_GRAFIC[g.tipus];
  const fila = document.createElement("div");
  fila.className = "camp camp-peca";
  fila.innerHTML = `<label class="etiqueta">Quant dura <span class="valor"></span></label>`;
  const rang = document.createElement("input");
  Object.assign(rang, { type: "range", min: 1, max: 10, step: 0.5, value: durada });
  rang.setAttribute("aria-label", "Quant dura");
  const valor = fila.querySelector(".valor");
  valor.textContent = g.fins != null && g.durada == null ? "fins a una paraula" : fmtSegons(durada);
  rang.addEventListener("input", () => { valor.textContent = fmtSegons(Number(rang.value)); });
  rang.addEventListener("change", () => canviaGrafic(id, { durada: Number(rang.value), fins: null }));
  fila.append(rang);
  cos.append(fila);
  const bloc = document.createElement("button");
  bloc.className = "interruptor";
  bloc.setAttribute("role", "switch");
  bloc.setAttribute("aria-checked", String(!!d?.bloc));
  bloc.innerHTML = '<span class="pista" aria-hidden="true"><span class="bola"></span></span>Bloc de color: el vídeo es fa petit a baix';
  bloc.addEventListener("click", () => canviaGrafic(id, { bloc: !d?.bloc }));
  cos.append(bloc);
  const demana = document.createElement("button");
  demana.className = "enllac";
  demana.textContent = "Demana-li un canvi a Claude";
  demana.addEventListener("click", () => notaSobre(g));
  accionsPeca(cos, "Treu el gràfic", treuPecaTriada, demana);
}

// Una nota per a Claude sobre una peça: va al moment de la peça i ja diu de quina parla.
function notaSobre(g) {
  mostraDreta("notes");
  const s = graficsMuntatge.find((x) => x.id === g.id);
  if (s) vesA(s.inici + 0.6);
  const camp = $("#text-nota");
  momentNota = g.paraula != null && g.paraula < P.paraules.length
    ? { paraula: g.paraula, m: muntatgeDe(P.paraules[g.paraula].inici) } : null;
  pintaMomentNota();
  const prefix = `Al gràfic «${retalla(textGrafic(g).replace(/^«|»$/g, ""), 30)}»: `;
  if (!camp.value.trim()) camp.value = prefix;
  camp.focus();
  camp.setSelectionRange(camp.value.length, camp.value.length);
  ajustaAlcada(camp);
}

function editorBroll(cos, id) {
  const b = brollsMuntatge.find((x) => x.id === id);
  const ins = instruccions.find((i) => i.id === id);
  if (b?.url) {
    const v = document.createElement("video");
    Object.assign(v, { src: b.url, muted: true, loop: true, playsInline: true, autoplay: true, className: "mostra-broll-peca" });
    v.setAttribute("aria-hidden", "true");
    cos.append(v);
  }
  if (ins && !ins.pagina) {
    const t = document.createElement("p");
    t.className = "detall";
    t.textContent = `Ve de la instrucció de veu «${ins.text}».`;
    cos.append(t);
  }
  const canvia_ = document.createElement("button");
  canvia_.className = "boto petit";
  canvia_.textContent = "Canvia'l per un altre fitxer";
  canvia_.addEventListener("click", () => { instruccioPerPujar = id; paraulaBrollNou = null; $("#fitxer-broll").click(); });
  accionsPeca(cos, "Treu el b-roll", () => treuBroll(id), canvia_);
}

function treuBroll(id) {
  const ins = instruccions.find((i) => i.id === id);
  deixaPeca();
  if (ins?.pagina) accioBroll("/api/broll/esborra", { instruccio: id }, "B-roll tret.");
  else if (ins) decideixInstruccio(ins, "descartada").then((ok) => ok && avis("B-roll tret (la instrucció de veu queda descartada)."));
}

function treuZoom(id) {
  const [a, b] = trams[tramDeZoom(id)] || [];
  deixaPeca();
  if (a == null) return;
  const dins = (id) => id >= 0 && id < P.paraules.length && P.paraules[id].inici >= a - 0.05 && P.paraules[id].inici < b;
  canvia((e) => { e.zooms = (e.zooms || []).filter((id) => !dins(id)); });
  // Els d'una instrucció de veu («Claude, zoom»): es descarta.
  for (const ins of instruccions) {
    if (ins.tipus === "zoom" && ins.estat === "acceptada" && ins.ancora != null && dins(ins.ancora)) decideixInstruccio(ins, "descartada");
  }
  avis("Zoom tret.");
}

function editorSo(cos, s) {
  if (!s) return;
  const c = document.createElement("div");
  c.className = "camp camp-peca";
  c.innerHTML = '<span class="etiqueta">Quin so</span><div class="sons-peca" role="radiogroup" aria-label="Quin so"></div>';
  const fila = c.querySelector(".sons-peca");
  for (const [nom, text] of Object.entries(NOMS_SO)) {
    const b = document.createElement("button");
    b.className = "boto petit";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(s.so === nom));
    b.textContent = text;
    b.addEventListener("click", () => {
      escoltaSo(nom);
      canvia((e) => { Object.assign(e.sons.find((x) => x.id === s.id), { so: nom }); });
    });
    fila.append(b);
  }
  cos.append(c);
  const escolta = document.createElement("button");
  escolta.className = "boto petit";
  escolta.textContent = "Escolta'l";
  escolta.addEventListener("click", () => escoltaSo(s.so));
  accionsPeca(cos, "Treu el so", treuPecaTriada, escolta);
}

function treuSo(id) {
  deixaPeca();
  canvia((e) => { e.sons = (e.sons || []).filter((x) => x.id !== id); });
  avis("So tret.");
}

function treuPecaTriada() {
  const { tipus, id } = pecaTriada;
  if (tipus === "subtitols" || tipus === "titol") return;  // no són peces: es treuen des del seu editor
  if (tipus === "grafic") {
    treuGrafic(id);
    deixaPeca();
    avis("Tret. El trobaràs a sota de la llista si el vols tornar a posar.");
  } else if (tipus === "broll") treuBroll(id);
  else if (tipus === "zoom") treuZoom(id);
  else treuSo(id);
}

// --- L'estil del vídeo: tot el vídeo d'un sol toc ---------------------------------------------------
// Cada estil (config/estils_video.json) porta els subtítols, el títol, els gràfics i el b-roll, sense colors ni
// lletres: són sempre els de la persona. Les cartes es dibuixen damunt d'un fotograma del vídeo, amb el mateix codi
// que el vídeo, i amb el que diu de debò: el que veus és el que surt.

let estilsVideo = [];      // [{id, nom, descripcio, subtitols, titol, broll, grafics}]
let liniesEstilsVideo = [];

const iguals = (a, b) => (typeof b === "number" ? Math.abs((a ?? NaN) - b) < 1e-6 : String(a) === String(b));

// El que fa servir el vídeo (si en té tots els valors), o null: retocat, o el del kit sense cap estil d'aquests.
function estilVideoActual() {
  const g = estat?.estil?.grafics || [].concat(estilMarca?.energia || "net")[0];
  return estilsVideo.find((e) => e.grafics === g && ["subtitols", "titol", "broll"].every((s) => {
    const ara = ambVideo(s) || {};
    return Object.entries(e[s]).every(([k, v]) => iguals(ara[k], v));
  })) || null;
}

function pintaResumEstilVideo() {
  if (!estat) return;
  const actual = estilVideoActual();
  const propi = Object.keys(estat.estil || {}).length > 0;
  $("#nom-estil-video").textContent = actual ? actual.nom : propi ? "Retocat" : "El dels altres vídeos";
  $("#caixa-a-tots").hidden = !propi;
}

function triaEstilVideo(e) {
  canvia((est) => {
    const on = est.estil?.subtitols?.posicio_y;  // on els has posat en aquest vídeo, s'hi queden
    est.estil = { ...(est.estil?.so ? { so: est.estil.so } : {}),
      subtitols: { ...e.subtitols, ...(on != null ? { posicio_y: on } : {}) }, titol: { ...e.titol }, broll: { ...e.broll },
      grafics: e.grafics };
    // Els gràfics també: els que tenien un estil triat, el de l'estil nou (⌘Z ho desfà tot).
    for (const g of est.grafics || []) g.estil = null;
  });
  previaBruta = true;
  avis(`Estil «${e.nom}». Mira com queda al vídeo.`);
}

async function estilATots() {
  try {
    await canvisDesats();
    const r = await api("/api/estil/a-tots", {});
    estat = r.estat;
    respostaEstil(r);
    refresca(true);
    avis(Object.keys(estat.estil || {}).length
      ? "Fet. Els colors i les lletres que has canviat només aquí es queden només en aquest vídeo: els de tots són a «Colors i lletres»."
      : "Fet: tots els vídeos amb aquest estil el fan servir.", 6000);
  } catch (e) { avis(e.message, 6000); }
}

// Un fotograma del vídeo d'ara (el que es veu), per al fons de les cartes. Null si encara no n'hi ha.
function fotogramaDelVideo() {
  const v = R.v;
  if (!v || v.readyState < 2 || !v.videoWidth) return null;
  try {
    const c = document.createElement("canvas");
    [c.width, c.height] = [270, 480];
    const r = Math.max(c.width / v.videoWidth, c.height / v.videoHeight);
    const [w, h] = [v.videoWidth * r, v.videoHeight * r];
    c.getContext("2d").drawImage(v, (c.width - w) / 2, (c.height - h) / 2, w, h);
    return c.toDataURL("image/jpeg", 0.8);
  } catch { return null; }
}

// Les paraules de mostra: les del principi del vídeo (les que es queden), com les diu.
function paraulesDeMostra() {
  const k = P?.paraules.findIndex((_, i) => !esFora(i)) ?? -1;
  const text = k >= 0 ? textDes(k, 7) : "";
  const paraules = text.split(/\s+/).filter(Boolean);
  return paraules.length >= 3 ? paraules : ["tinc", "una", "idea", "genial"];
}

// Una mostra dels subtítols d'un estil: les paraules en línies com les faria (una, poques o la frase), totes ja dites.
function liniesDeMostra(e) {
  const paraules = paraulesDeMostra();
  const n = Math.max(1, Math.min(paraules.length, e.paraules_per_linia || 3));
  const apilat = ["apilat", "escampat"].includes(e.disposicio);
  const grups = apilat ? [paraules.slice(0, n), paraules.slice(n, 2 * n)].filter((g) => g.length) : [paraules.slice(0, n)];
  let t = 0;
  return grups.map((g) => {
    const inici = t;
    const ws = g.map((text) => { const w = { text: text.replace(/[.,;:!?…«»"]+$/g, ""), inici: t, final: t + 0.28, clau: false }; t += 0.3; return w; });
    return { inici, final: 9, paraules: ws, bloc: 0 };
  });
}

function obreEstilVideo() {
  if (sona()) atura();
  $("#velo").hidden = false;
  $("#full-estil").hidden = false;
  pintaEstilsVideo();
  ($("#estils-video [aria-checked='true']") || $("#estils-video .carta-estil"))?.focus();
}

function tancaEstilVideo() {
  $("#full-estil").hidden = true;
  if ($("#full-final").hidden && $("#full-marca").hidden) $("#velo").hidden = true;
  $("#obre-estil-video").focus({ preventScroll: true });
}

function pintaEstilsVideo() {
  const cont = $("#estils-video");
  for (const tl of liniesEstilsVideo) tl?.kill?.();
  liniesEstilsVideo = [];
  cont.textContent = "";
  if (!estilsVideo.length || !kitEstil.subtitols) return;
  const fons = fotogramaDelVideo();
  const actual = estilVideoActual();
  const textTitol = estat?.titol?.text || "El teu\n*títol*";
  for (const e of estilsVideo) {
    const b = document.createElement("button");
    b.className = "carta-estil";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(actual === e));
    b.title = e.descripcio;
    b.innerHTML = '<span class="carta-estil-mostra"><span class="mg-host"></span></span><span class="carta-estil-nom"></span>';
    b.querySelector(".carta-estil-nom").textContent = e.nom;
    b.setAttribute("aria-label", `${e.nom}: ${e.descripcio}`);
    b.addEventListener("click", () => { triaEstilVideo(e); pintaEstilsVideo(); });
    cont.append(b);
    const mostra = b.querySelector(".carta-estil-mostra");
    if (fons) mostra.style.backgroundImage = `url(${fons})`;
    if (!window.TallatSubtitols || !mostra.clientWidth) continue;
    const host = mostra.querySelector(".mg-host");
    host.style.transform = `scale(${mostra.clientWidth / 1080})`;
    // Com al vídeo: l'estil del kit, amb el de la carta al damunt (on són ara els subtítols, s'hi queden).
    const sub = { ...kitEstil.subtitols, ...e.subtitols, posicio_y: estilSub?.posicio_y ?? kitEstil.subtitols.posicio_y };
    const tit = { ...kitEstil.titol, ...e.titol };
    const capa = () => { const d = document.createElement("div"); d.className = "capa-mostra"; host.append(d); return d; };
    const linies = liniesDeMostra(sub);
    liniesEstilsVideo.push(TallatSubtitols.construeix(capa(), linies, sub, { familia: familiaCss(sub) })
      .seek(linies.at(-1).paraules.at(-1).inici + 0.6, false));
    liniesEstilsVideo.push(TallatSubtitols.titol(capa(), { text: textTitol, inici: 0, final: 9 }, tit,
      { familia: familiaCss({ font: tit.font || sub.font }) }).seek(9 - 0.35, false));  // ja escrit (com a la pàgina)
    if (window.TallatGrafics && paletaGrafics && mostresGrafics.etiqueta) {
      const d = { ...sencer(mostresGrafics.etiqueta), estil: e.grafics, posicio: 0.44 };
      liniesEstilsVideo.push(TallatGrafics.construeix(capa(), [d], paletaGrafics, OP_GRAFICS).seek(50, false));
    }
  }
}

// --- Els subtítols i el títol, a la dreta (com les peces) ---

// Les tres coses que es poden canviar de seguida (la resta, a «Més ajustos»): valors i el més proper.
const MIDES_SUB = [["petita", "Petita", 0.056], ["mitjana", "Mitjana", 0.07], ["gran", "Gran", 0.09]];
const LLOCS_SUB = [["dalt", "Dalt", 0.18], ["mig", "Mig", 0.5], ["baix", "Baix", 0.74]];
const MIDES_TITOL = [["petit", "Petit", 0.05], ["mitja", "Mitjà", 0.066], ["gran", "Gran", 0.086]];
const LLOCS_TITOL = [["dalt", "Dalt", 0.16], ["mig", "Mig", 0.42], ["baix", "Baix", 0.66]];
const mesProper = (opcions, v, marge) => opcions.find(([, , x]) => Math.abs((v ?? -9) - x) <= marge)?.[0] ?? null;

function obreALaDreta(tipus) {
  if (!vestint) canviaEstacio("vesteix");
  tancaElQueHiHagi();
  if (tipus === "titol" && titolMuntatge && !sona()) vesA(titolMuntatge.inici + Math.min(1, (titolMuntatge.final - titolMuntatge.inici) / 2));
  if (tipus === "subtitols" && !sona() && liniesSub.length) {
    const m = tempsMuntatge();
    if (!liniesSub.some((l) => m >= l.inici && m < l.final)) {
      const l = liniesSub.find((x) => x.inici >= m) || liniesSub[0];
      vesA(l.inici + Math.min(0.6, (l.final - l.inici) / 2));
    }
  }
  triaPeca(tipus, tipus, { enfoca: tipus === "titol" && !estat?.titol?.text });
}

function editorSubtitols(cos) {
  const e = estilSub || {};
  const amb = estat.subtitols !== false;
  const sw = document.createElement("button");
  sw.className = "interruptor";
  sw.setAttribute("role", "switch");
  sw.setAttribute("aria-checked", String(amb));
  sw.innerHTML = '<span class="pista" aria-hidden="true"><span class="bola"></span></span>Posa subtítols al vídeo';
  sw.addEventListener("click", () => $("#subtitols").click());
  cos.append(sw);
  if (!amb) return;
  segmentatPeca(cos, "Paraules alhora", [["una", "Una"], ["poques", "Dues o tres"], ["frase", "La frase"]], agrupacioDe(e),
    (v) => canviaEstil({ paraules_per_linia: AGRUPACIONS[v][0], lletres_per_linia: AGRUPACIONS[v][1] }, true));
  segmentatPeca(cos, "La paraula que dius", [["cap", "Igual"], ["color", "Color"], ["caixa", "Caixa"], ["gran", "Més gran"]],
    destacatDe(e), (v) => canviaEstil(v === "cap" ? { destaca: false } : { destaca: true, destacat: v }, true));
  if (destacatDe(e) === "color" && (e.color_actiu || "").toUpperCase() === (e.color || "").toUpperCase()) {
    const pista = document.createElement("p");
    pista.className = "detall";
    pista.innerHTML = 'Ara és del mateix color que la resta. Tria un color <b>Destacat</b> a «Colors i lletres» perquè es vegi. ';
    const b = document.createElement("button");
    b.className = "enllac";
    b.textContent = "Obre «Colors i lletres»";
    b.addEventListener("click", obreMarca);
    pista.append(b);
    cos.append(pista);
  }
  segmentatPeca(cos, "Mida", MIDES_SUB.map(([v, t]) => [v, t]), mesProper(MIDES_SUB, e.mida, 0.007),
    (v) => canviaEstil({ mida: MIDES_SUB.find((x) => x[0] === v)[2] }));
  segmentatPeca(cos, "On surten", LLOCS_SUB.map(([v, t]) => [v, t]), mesProper(LLOCS_SUB, e.posicio_y, 0.08),
    (v) => canviaEstil({ posicio_y: LLOCS_SUB.find((x) => x[0] === v)[2] }));
  const pista = document.createElement("p");
  pista.className = "detall";
  pista.textContent = "També els pots arrossegar al vídeo, amunt o avall.";
  cos.append(pista);
  accionsSeccio(cos, "subtitols", () => { tancaElQueHiHagi(); obreSubtitols(); $("#grup-e-mes").open = true; });
}

function editorTitol(cos) {
  const e = estilTitol || {};
  const text = titolEsborrany?.text ?? estat.titol?.text ?? "";
  const camp = document.createElement("textarea");
  Object.assign(camp, { className: "camp-text", rows: 3, value: text, placeholder: "El teu\n*títol*" });
  camp.dataset.camp = "titol:text";
  camp.addEventListener("input", () => {
    canviaTitolDelVideo({ text: camp.value }, 700);
    // El títol surt al principi: si el vídeo és més endavant, hi va, perquè es vegi el que s'escriu.
    if (titolMuntatge && !sona() && tempsMuntatge() >= titolMuntatge.final) vesA(Math.min(1, titolMuntatge.final / 2));
  });
  camp.addEventListener("blur", () => desaTitolDelVideo());
  const c = document.createElement("label");
  c.className = "camp camp-peca";
  c.innerHTML = '<span class="etiqueta">El text</span>';
  c.append(camp);
  const ajuda = document.createElement("span");
  ajuda.className = "detall ajuda-camp";
  ajuda.textContent = "Cada línia, una línia del títol. El que posis *entre asteriscs* surt destacat.";
  c.append(ajuda);
  cos.append(c);
  if (!text.trim()) return;
  const durada = titolEsborrany?.durada ?? estat.titol?.durada ?? e.durada ?? 3;
  const fila = document.createElement("div");
  fila.className = "camp camp-peca";
  fila.innerHTML = '<span class="etiqueta">Quant dura <span class="valor"></span></span>';
  const valor = fila.querySelector(".valor");
  valor.textContent = fmtSegons(durada);
  const rang = document.createElement("input");
  Object.assign(rang, { type: "range", min: 1, max: 8, step: 0.5, value: durada });
  rang.setAttribute("aria-label", "Quant dura el títol");
  rang.addEventListener("input", () => { valor.textContent = fmtSegons(+rang.value); canviaTitolDelVideo({ durada: +rang.value }, 400); });
  fila.append(rang);
  cos.append(fila);
  segmentatPeca(cos, "Mida", MIDES_TITOL.map(([v, t]) => [v, t]), mesProper(MIDES_TITOL, e.mida, 0.007),
    (v) => canviaTitol({ mida: MIDES_TITOL.find((x) => x[0] === v)[2] }));
  segmentatPeca(cos, "On surt", LLOCS_TITOL.map(([v, t]) => [v, t]), mesProper(LLOCS_TITOL, e.posicio_y, 0.08),
    (v) => canviaTitol({ posicio_y: LLOCS_TITOL.find((x) => x[0] === v)[2] }));
  accionsSeccio(cos, "titol", () => { tancaElQueHiHagi(); obreTitol(); }, () => {
    canviaTitolDelVideo({ text: "" }, 0);
    deixaPeca();
    avis("Títol tret.");
  });
}

// El peu dels editors dels subtítols i del títol: «Més ajustos» (el panell sencer, a l'esquerra), tornar a l'estil
// dels altres vídeos (si aquest l'ha canviat) i, al títol, treure'l.
function accionsSeccio(cos, seccio, mesAjustos, treu) {
  const fila = document.createElement("div");
  fila.className = "accions-peca";
  const mes = document.createElement("button");
  mes.className = "boto petit";
  mes.textContent = "Més ajustos…";
  mes.addEventListener("click", mesAjustos);
  fila.append(mes);
  if (Object.keys(propiDe(seccio)).length) {
    const torna = document.createElement("button");
    torna.className = "enllac";
    torna.textContent = "Com els altres vídeos";
    torna.title = "Torna a l'estil dels altres vídeos";
    torna.addEventListener("click", () => restableix(seccio));
    fila.append(torna);
  }
  if (treu) {
    const b = document.createElement("button");
    b.className = "enllac perill";
    b.textContent = "Treu el títol";
    b.addEventListener("click", treu);
    fila.append(b);
  }
  cos.append(fila);
}

function instalaVesteix() {
  instalaTauler();
  for (const b of $$("#pestanyes-dreta button")) b.addEventListener("click", () => mostraDreta(b.dataset.dreta));
  $("#pestanyes-dreta").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    e.preventDefault();
    mostraDreta(pestanyaDreta === "peces" ? "notes" : "peces");
    $(`#pestanyes-dreta [data-dreta="${pestanyaDreta}"]`).focus();
  });
  mostraDreta("peces");
  for (const b of $$("[data-desfes]")) b.addEventListener("click", desfes);
  for (const b of $$("[data-refes]")) b.addEventListener("click", refes);
  $("#vesteix-exporta").addEventListener("click", obreFinal);
  $("#estil-a-tots").addEventListener("click", estilATots);
  $("#estil-com-tots").addEventListener("click", () => {
    canvia((e) => { e.estil = {}; });
    avis("Ha tornat a l'estil dels altres vídeos.");
  });
  $("#a-colors").addEventListener("click", () => { tancaEstilVideo(); obreMarca(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#full-estil").hidden) { e.stopPropagation(); tancaEstilVideo(); }
  }, true);
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
  const [tipus, id] = quin.startsWith("grafic:") ? ["grafic", quin.slice(7)] : [quin, quin];
  if (!(pecaTriada?.tipus === tipus && pecaTriada.id === id)) triaPeca(tipus, id);
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

// Al vídeo, només el marc (i arrossegar amunt i avall): el que s'ha tocat es retoca a la dreta de Vesteix.
function pintaBarraCapa() {
  $("#barra-capa").hidden = true;
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

// Com s'encongeix el vídeo (amb el zoom z) quan el bloc de color és al pas e: {transform, clipPath}.
function transformBloc(e, z, radi = "var(--radi-gran)") {
  const s = 1 - (1 - BLOC.w / 1080) * e;
  const ty = ((BLOC.y - BLOC.retall_y * BLOC.w / 1080) * e) / 1920 + 0.5 * (s - 1);
  const sz = s * z;
  const local = (o, t) => 0.5 + (o - 0.5 - t) / sz;  // d'on es veu a la pantalla a on és dins del vídeo
  const pc = (x) => `${(x * 100).toFixed(3)}%`;
  const dalt = local((BLOC.y * e) / 1920, ty);
  const baix = 1 - local(1 - ((1920 - BLOC.y - BLOC.h) * e) / 1920, ty);
  const costat = local((BLOC.x * e) / 1080, 0);
  return { transform: `translateY(${pc(ty)}) scale(${sz.toFixed(5)})`,
    clipPath: `inset(${pc(dalt)} ${pc(costat)} ${pc(baix)} round calc(${radi} * ${((1 - e) / sz).toFixed(4)}))` };
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
  Object.assign(v.style, transformBloc(e, z));
  v.style.boxShadow = "none";
}

function instalaEdicioAlVideo() {
  const pantalla = $(".pantalla");
  const host = (quin) => (quin === "titol" ? $("#tt-host") : $("#ts-host"));
  const prefix = (quin) => (quin === "titol" ? "tt" : "ts");
  pantalla.addEventListener("pointerdown", (e) => {
    // Només a Vesteix: a Edita, el vídeo és per mirar-lo (s'hi edita el text).
    if (!vestint || vista !== "directe" || e.button !== 0 || e.target.closest("#gran-play, #barra-capa")) return;
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

// Els textos de la pàgina que diuen una drecera o el Finder, com es diuen en aquest ordinador.
function instalaTecles() {
  if (ES_MAC) return;
  for (const [sel, mac] of [["#desfes", "⌘Z"], ["#refes", "⇧⌘Z"], ["#commuta-barra", "⌃⌘S"], ["#commuta-reproductor", "⌥⌘V"]]) {
    const b = $(sel);
    if (b) b.title = b.title.replace(mac, tecla(mac));
  }
  $("#fet-mostra").textContent = `Mostra-la ${GESTOR}`;
}

// --- La visita guiada (el primer cop) -----------------------------------------------------------
// Unes quantes passes curtes: s'enfosqueix la pàgina, s'il·lumina una part i una frase diu què és.
// Surt sola el primer cop; després, amb el «?» de dalt.

const PASSES_GUIA = [
  ["#tria-reel", "Aquí tries què edites: el vídeo sencer o un dels reels que t'ha proposat Claude."],
  ["#seccio-revisar", "Aquí hi ha el que t'ha proposat tallat: les instruccions de veu i les paraules que potser vols treure."],
  [".text", `Això és el que dius. Toca una paraula per escoltar-la. Per treure'n, selecciona-les i prem ⌫. A sobre ` +
    `surt una barreta per destacar-les (${tecla("⌘B")}) o corregir-les (${tecla("↩")}).`],
  [".pantalla", "Aquí veus el vídeo tal com queda, amb els talls que fas al text."],
  ["#notes", "Per demanar-li coses a Claude: atura el vídeo on vulguis, escriu una nota (o prem N) i, quan acabis, " +
    "toca Envia a Claude. Claude les fa i et respon a sota de cada una."],
  [".estacions", "Tres passos. A Edita, el text. A Vesteix, com es veu: l'estil de tot el vídeo i un tauler amb les " +
    "propostes de Claude, que votes. A Revisa, mires l'esborrany sencer i hi deixes notes. Pots anar endavant i enrere quan vulguis."],
  ['[data-seccio="ritme"]', "I aquí, el ritme: com de curts vols els silencis entre frases."],
  ["#final", "Quan estigui a punt, toca Exporta: un esborrany per mirar-lo, el vídeo final o per a un altre editor."],
];
let passaGuia = -1;
let passesVisibles = [];
// Puja quan la pàgina canvia prou perquè qui ja havia vist la visita la torni a veure (2: la pàgina simplificada;
// 3: les tres estacions).
const VERSIO_GUIA = 3;

function esVeu(el) {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && !el.closest("[hidden]");
}
// El primer que es veu (les estacions, per exemple, hi són a la columna de l'esquerra i a la barra del text).
const visible = (sel) => $$(sel).find(esVeu);

function obreGuia() {
  passesVisibles = PASSES_GUIA.filter(([sel]) => visible(sel));
  if (!passesVisibles.length) return;
  passaGuia = 0;
  $("#guia").hidden = false;
  pintaGuia();
  $("#guia-seguent").focus();
}

function tancaGuia() {
  passaGuia = -1;
  $("#guia").hidden = true;
  desa("tallat.guia-vista", VERSIO_GUIA);
}

function pintaGuia() {
  if (passaGuia < 0) return;
  const [sel, text] = passesVisibles[passaGuia];
  const el = visible(sel);
  let r = el.getBoundingClientRect();
  if (r.top < 0 || r.bottom > innerHeight) {  // més avall de la columna («Ritme», per exemple): s'hi baixa
    el.scrollIntoView({ block: "nearest" });
    r = el.getBoundingClientRect();
  }
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
// Dos passos visuals dins la pàgina: els colors i les lletres.
// No va al principi: s'ofereix quan arribes als subtítols o als gràfics (o des d'«El teu estil»).

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
const TITOLS_ASSISTENT = ["Els teus colors", "Les teves lletres"];
let assistent = null;  // {pas, colors, parella}

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
  $("#assistent-seguent").textContent = a.pas === TITOLS_ASSISTENT.length - 1 ? "Fet" : "Següent";
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
      b.innerHTML = "<strong>Les meves</strong><span>Les lletres que ja tens al teu estil</span>";
    }
  }
}

async function acabaAssistent() {
  const a = assistent;
  tancaAssistent();
  canviaMarca({ ...a.colors });
  pintaPanellMarca();
  if (a.parella && a.parella !== "kit") {
    for (const clau of ["lletra_titols", "lletra_text", "lletra_accent"]) await baixaLletra(a.parella[clau], "marca", clau);
  } else {
    await desaEstils();
  }
  avis("Fet. Els subtítols, el títol i els gràfics ja tenen el teu estil.", 5000);
}

function instalaAssistent() {
  for (const b of $$("[data-obre-assistent]")) b.addEventListener("click", obreAssistent);
  $("#assistent-enrere").addEventListener("click", () => {
    if (!assistent || assistent.pas === 0) tancaAssistent();
    else { assistent.pas--; pintaAssistent(); }
  });
  $("#assistent-seguent").addEventListener("click", () => {
    if (!assistent) return;
    if (assistent.pas === TITOLS_ASSISTENT.length - 1) acabaAssistent();
    else { assistent.pas++; pintaAssistent(); }
  });
  document.addEventListener("keydown", (e) => {
    if (assistent && e.key === "Escape") { e.stopPropagation(); tancaAssistent(); }
  }, true);
}

let instruccioPerPujar = null;
// Puja fitxers un darrere l'altre (el cos de la petició és el fitxer) i aplica la darrera resposta bona,
// també si un dels del mig falla: els d'abans ja són al servidor.
// Si mentre es pujava s'ha canviat alguna cosa aquí, l'estat d'aquí es queda (i s'hi posa el que ha fet la pujada,
// amb `fusiona`): si no, la resposta trepitjaria el canvi abans d'enviar-lo.
async function pujaFitxers(fitxers, url, fusiona = null) {
  let json = null;
  const abans = canvisFets;
  try {
    await esperaDesats();
    for (const fitxer of fitxers) {
      json = await resposta(await fetch(url(fitxer), { method: "POST", headers: capcaleres(), body: fitxer }));
    }
    return true;
  } catch (e) {
    avis(e.message, 6000);
    return false;
  } finally {
    if (json) {
      if (canvisFets === abans) estat = json.estat;
      else { fusiona?.(json.estat); estat.revisio = json.estat.revisio; }
      aplicaTrams(json);
      refresca(true);
    }
  }
}

async function pujaBroll(iid, fitxer) {
  avis(`Pujant «${fitxer.name}»…`, 20000);
  const url = (f) => `/api/broll/puja?instruccio=${encodeURIComponent(iid)}&nom=${encodeURIComponent(f.name)}`;
  if (await pujaFitxers([fitxer], url)) avis("Fet. Mira-ho al reproductor.");
}

async function accioBroll(ruta, dades, missatge) {
  try {
    await esperaDesats();
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

// «Per revisar»: les instruccions de veu i les paraules proposades, junts. El compte és el que queda per decidir.
// Els b-rolls posats a Vesteix també són instruccions (fetes a mà), però no són de veu: no surten aquí.
const instruccionsDeVeu = () => instruccions.filter((i) => !i.pagina);

function pintaRevisar() {
  const propostes = Object.keys(estat?.propostes || {}).length;
  const pendents = instruccionsDeVeu().filter((i) => i.estat === "pendent").length + propostes;
  $("#seccio-revisar").hidden = !instruccionsDeVeu().length && !propostes;
  $("#compte-revisar").textContent = pendents ? String(pendents) : "fet ✓";
}

// S'atura al primer error (revisió de Codex: deia que les havia acceptat totes encara que fallessin).
async function acceptaInstruccions() {
  const pendents = instruccions.filter((i) => i.estat === "pendent" && !i.manual);
  let fetes = 0;
  for (const ins of pendents) {
    if (!(await decideixInstruccio(ins, "acceptada"))) {
      if (fetes) setTimeout(() => avis(`Només n'he acceptat ${fetes} de ${pendents.length}: torna-ho a provar.`, 5000), 3000);
      return;
    }
    fetes++;
  }
  if (fetes) avis(`${fetes === 1 ? "Instrucció acceptada" : `${fetes} instruccions acceptades`}.`);
}

function pintaInstruccions() {
  $("#grup-instruccions").hidden = !instruccionsDeVeu().length;
  const pendents = instruccions.filter((i) => i.estat === "pendent" && !i.manual).length;
  $("#accepta-instruccions").hidden = pendents < 2;
  pintaRevisar();
  const cont = $("#instruccions");
  cont.textContent = "";
  for (const ins of instruccionsDeVeu()) {
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
}

// Torna true si el servidor l'ha desada (si no, ja ho ha dit l'avís).
async function decideixInstruccio(ins, nou) {
  try {
    await esperaDesats();  // primer, que es desin els canvis pendents
    const r = await api("/api/instruccio", { id: ins.id, estat: nou });
    estat = r.estat;
    aplicaTrams(r);
    refresca(true);
    if (nou === "acceptada" && ins.tipus === "talla") avis("Primer intent tret. El pots recuperar tocant-ne les paraules.");
    else if (nou === "acceptada" && ins.sense_paraula) avis("Fet: he tret la instrucció del vídeo.");
    return true;
  } catch (e) {
    avis(e.message);
    return false;
  }
}

// --- Notes per a Claude -----------------------------------------------------------------------
// La persona atura el vídeo on vol, escriu què vol que faci Claude (o una nota per a tot el vídeo) i,
// quan acaba, les envia. Claude les espera des del xat (`tallat.py notes --espera`), les fa i hi respon:
// aquí es veu la resposta a sota de cada nota. Es desen a notes.json, a la gravació sencera; la pàgina
// ensenya les del que s'edita (el vídeo sencer o un reel). Cada nota va a la paraula que sonava.
// Sota el vídeo hi ha poc lloc: cada nota és una línia (en tocar-la, s'obre la conversa, una sola alhora),
// agrupades pel que toca fer; les fetes, plegades en una fila.

let notesTotes = [];
let projecteNotes = null;      // la carpeta del que s'edita: se'n veuen les notes
let versioNotes = null;
let notesCarregades = false;
let claudeConnectat = false;   // Claude espera les notes ara mateix
let momentNota = null;         // on va la nota que s'escriu: {paraula, m} o {tot: true}; null: on és el vídeo
let notaDesplegada = null;         // la nota que es veu sencera (la resta, d'una línia)
let fetesObertes = false;
let vistes = null;             // {id: missatges que s'han vist}: les respostes de Claude encara no vistes porten un punt
const respostesObertes = new Set();  // notes fetes on s'ha tocat «Respon»
const esborranysResposta = new Map(); // el que s'escriu a cada resposta: no es perd en plegar-la o obrir-ne una altra
const ESTATS_NOTA = { esborrany: "Per enviar", enviada: "Enviada", treballant: "Claude hi treballa…", feta: "Feta",
  pregunta: "Et pregunta" };

// Les del que s'edita (el vídeo sencer o un reel). Les d'editar no són de cap versió; les de Revisa, sí.
const notesDelProjecte = () => notesTotes.filter((n) => n.projecte === projecteNotes);
const notesVisibles = () => notesDelProjecte().filter((n) => !n.versio);

// El segon del vídeo editat on cau un segon de la gravació (si aquell tros s'ha tret, on comença el següent).
function muntatgeDe(t) {
  const k = indexTram(t);
  if (k >= trams.length) return duradaFinal;
  return acum[k] + limita(t - trams[k][0], 0, trams[k][1] - trams[k][0]);
}

async function carregaNotes() {
  try { respostaNotes(await api("/api/notes")); } catch { /* sense notes: la secció queda buida */ }
}

function respostaNotes(r) {
  const abans = new Map(notesTotes.map((n) => [n.id, n.estat]));
  notesTotes = r.notes || [];
  projecteNotes = r.projecte ?? projecteNotes;
  versioNotes = r.versio_notes;
  if ("connectat" in r) claudeConnectat = r.connectat;
  if (notesCarregades) avisaRespostes(abans);
  notesCarregades = true;
  carregaVistes();
  pintaNotes();
  pintaRevisa();
}

// El primer cop en aquest navegador, el que ja hi ha es dona per vist (si no, tot sortiria com a nou).
const clauVistes = () => `tallat.notes-vistes.${projecteNotes}`;
function carregaVistes() {
  if (vistes) return;
  vistes = llegeix(clauVistes(), null);
  if (!vistes) {
    vistes = Object.fromEntries(notesTotes.map((n) => [n.id, n.fil.length]));
    desa(clauVistes(), vistes);
  }
}
const esNova = (n) => n.fil.at(-1)?.de === "claude" && (vistes?.[n.id] ?? 0) < n.fil.length;
function marcaVista(n) {
  if (!vistes || vistes[n.id] === n.fil.length) return;
  vistes[n.id] = n.fil.length;
  desa(clauVistes(), vistes);
}

// Quan Claude acaba una nota o pregunta alguna cosa, un avís curt (la nota es veu a la llista).
function avisaRespostes(abans) {
  const ara = notesDelProjecte().filter((n) => ["enviada", "treballant"].includes(abans.get(n.id)));
  const fetes = ara.filter((n) => n.estat === "feta").length;
  const pregunta = ara.find((n) => n.estat === "pregunta");
  if (pregunta) avis(`Claude et pregunta una cosa a la nota ${numNota(pregunta)}.`, 5000);
  else if (fetes) avis(fetes === 1 ? "Claude ha fet una nota." : `Claude ha fet ${fetes} notes.`, 4000);
}

function etiquetaEstat(n) {
  if (n.estat === "pregunta" && n.al_xat) return "Respon-li al xat";
  if (n.estat === "enviada" && notesDelProjecte().some((m) => m.estat === "treballant")) return "A la cua";
  if (n.estat === "enviada" && !claudeConnectat) return "S'espera Claude";
  return ESTATS_NOTA[n.estat] || n.estat;
}

// Les notes sense moment (per a tot el vídeo), primer; les altres, per l'ordre del vídeo.
function ordreNotes(a, b) {
  if ((a.inici == null) !== (b.inici == null)) return a.inici == null ? -1 : 1;
  return a.inici == null ? a.id - b.id : muntatgeDe(a.inici) - muntatgeDe(b.inici) || a.id - b.id;
}

// El número que veus de cada nota: per l'ordre del vídeo (1, 2, 3… d'esquerra a dreta; les de tot el vídeo, primer)
// i, a Revisa, dins de la seva versió. No és l'id: Claude veu tots dos (tallat.py notes, _numeros_pagina).
function numNota(n) {
  const llista = n.versio ? notesDelProjecte().filter((m) => m.versio === n.versio)
    .sort((a, b) => (a.t_versio ?? 0) - (b.t_versio ?? 0) || a.id - b.id) : notesVisibles().sort(ordreNotes);
  return llista.findIndex((m) => m.id === n.id) + 1 || n.id;
}

// Els grups, per ordre: el que et necessita, el que encara no has enviat, el que té Claude i el que espera torn
// (si Claude ja en té, les noves no s'hi barregen: van a la cua). Les fetes, al final i plegades.
function pintaNotes() {
  if (estat && !$("#tauler").hidden) pintaEstatRonda();  // la nota de la ronda, al tauler
  const visibles = notesVisibles().sort(ordreNotes);
  const llista = $("#llista-notes");
  // Repintar no ha de fer perdre on era el teclat: cada control porta una clau i, després, es torna a enfocar.
  const actiu = document.activeElement;
  const focus = actiu?.closest?.("#llista-notes") ? actiu.dataset.focus : null;
  const cursor = actiu?.tagName === "TEXTAREA" ? actiu.selectionStart : null;
  if (notaDesplegada != null && !visibles.some((n) => n.id === notaDesplegada)) notaDesplegada = null;
  llista.textContent = "";
  const de = (...estats) => visibles.filter((n) => estats.includes(n.estat));
  const treballant = de("treballant");
  const grups = [
    ["necessita", "Et necessita", de("pregunta")],
    ["enviar", "Per enviar", de("esborrany")],
    ["claude", "A Claude", treballant.length ? treballant : de("enviada")],
    ["cua", "A la cua", treballant.length ? de("enviada") : []],
  ];
  for (const [clau, titol, notes] of grups) {
    if (!notes.length) continue;
    llista.append(capGrup(clau, titol, notes.length));
    for (const n of notes) llista.append(notaALaLlista(n));
    if (clau === "cua") {
      const p = document.createElement("p");
      p.className = "detall cua-notes";
      p.textContent = `Claude les farà quan acabi ${treballant.length === 1 ? "la que té ara" : `les ${treballant.length} d'ara`}.`;
      llista.append(p);
    }
  }
  const fetes = de("feta");
  if (fetes.length) {
    const fila = document.createElement("button");
    fila.className = "fila-fetes";
    fila.dataset.focus = "fetes";
    fila.setAttribute("aria-expanded", String(fetesObertes));
    fila.innerHTML = '<span class="ok" aria-hidden="true">✓</span><span></span>'
      + '<svg class="xebro" viewBox="0 0 20 20" aria-hidden="true"><path d="m8 5 5 5-5 5"/></svg>';
    fila.children[1].textContent = fetes.length === 1 ? "1 feta" : `${fetes.length} fetes`;
    fila.addEventListener("click", () => { fetesObertes = !fetesObertes; pintaNotes(); });
    llista.append(fila);
    // Plegades, menys les que tenen una resposta que encara no has vist (o la que tens oberta).
    const aLaVista = fetesObertes ? fetes : fetes.filter((n) => esNova(n) || n.id === notaDesplegada);
    for (const n of aLaVista) llista.append(notaALaLlista(n));
  }
  if (focus) {
    const el = llista.querySelector(`[data-focus="${focus}"]`);
    if (el) {
      el.focus({ preventScroll: true });
      if (cursor != null && el.tagName === "TEXTAREA") el.setSelectionRange(cursor, cursor);
    }
  }
  // Si es veu sencera, la resposta ja s'ha vist; però no si la columna del vídeo està amagada (Codex).
  const oberta = visibles.find((n) => n.id === notaDesplegada);
  if (oberta && notesALaVista()) marcaVista(oberta);
  $("#compte-notes").textContent = visibles.length ? String(visibles.length) : "";
  const noves = visibles.filter(esNova).length;
  $("#noves-notes").textContent = noves ? `· ${noves === 1 ? "1 nova" : `${noves} noves`}` : "";
  pintaConnexio();
  pintaMarquesNotes();
  if (vestint) pintaPestanyesDreta();
}

function capGrup(clau, titol, quantes) {
  const cap = document.createElement("h3");
  cap.className = `grup-notes grup-${clau}`;
  cap.textContent = titol;
  if (clau === "enviar") {
    const b = document.createElement("button");
    b.className = "boto suau petit";
    b.id = "envia-notes";
    b.dataset.focus = "envia";
    b.textContent = `Envia a Claude (${quantes})`;
    b.addEventListener("click", enviaNotes);
    cap.append(b);
  }
  return cap;
}

function notaALaLlista(n) {
  return n.id === notaDesplegada ? elementNota(n, esborranysResposta.get(n.id) || "") : liniaNota(n);
}

const notesALaVista = () => !document.hidden && !!$("#notes").offsetParent;

// Una nota en una línia: el número, el moment i de què va (si Claude pregunta, la pregunta); a la dreta, un punt
// si hi ha una resposta que no has vist, o la rodeta si Claude hi treballa.
function liniaNota(n) {
  const b = document.createElement("button");
  b.className = `linia-nota estat-${n.estat}`;
  b.dataset.id = n.id;
  b.dataset.focus = `linia-${n.id}`;
  b.setAttribute("aria-expanded", "false");
  const num = document.createElement("span");
  num.className = "num-nota";
  num.textContent = numNota(n);
  const temps = document.createElement("span");
  temps.className = "linia-temps-nota";
  temps.textContent = n.inici != null ? fmt(muntatgeDe(n.inici)) : "Tot";
  const text = document.createElement("span");
  text.className = "linia-text";
  const darrer = n.fil.at(-1);
  text.textContent = n.estat === "pregunta" && darrer?.de === "claude" ? `Claude: ${darrer.text}` : n.fil[0]?.text || "";
  b.append(num, temps, text);
  if (esNova(n)) {
    const punt = document.createElement("span");
    punt.className = "punt-nou";
    punt.setAttribute("aria-label", "resposta nova");
    b.append(punt);
  } else if (n.estat === "treballant") {
    const roda = document.createElement("span");
    roda.className = "roda-nota";
    roda.setAttribute("aria-label", "Claude hi treballa");
    b.append(roda);
  }
  b.setAttribute("aria-label", `Nota ${numNota(n)}, ${n.inici != null ? `al ${temps.textContent}` : "per a tot el vídeo"}: `
    + `${text.textContent.replace(/[.!?…]+$/, "")}. ${etiquetaEstat(n)}`);
  b.addEventListener("click", () => mostraNota(n.id));
  return b;
}

// Obre una nota sencera (i tanca la que hi hagués oberta); si ja ho era, la torna a plegar. El focus va a la
// capçalera de la nota oberta, o a la línia de la que s'ha plegat.
function mostraNota(id, { obre = false } = {}) {
  notaDesplegada = obre || notaDesplegada !== id ? id : null;
  pintaNotes();
  const el = $(`#llista-notes [data-id="${id}"]`);
  el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  (el?.querySelector(".nota-plega") || el)?.focus({ preventScroll: true, focusVisible: false });
}

// Quan la columna del vídeo torna a sortir (o la pestanya), la nota oberta es veu: ja compta com a vista.
function notesTornenASortir() { if (notesCarregades) pintaNotes(); }

function elementNota(n, escrit) {
  const li = document.createElement("div");
  li.className = `nota estat-${n.estat}`;
  li.dataset.id = n.id;
  const cap = document.createElement("div");
  cap.className = "nota-cap";
  const plega = document.createElement("button");
  plega.className = "nota-plega";
  plega.dataset.focus = `plega-${n.id}`;
  plega.setAttribute("aria-expanded", "true");
  plega.setAttribute("aria-label", `Plega la nota ${numNota(n)}`);
  // Tocar la capçalera (menys el temps, que porta el vídeo a aquell moment) la torna a plegar.
  cap.addEventListener("click", (e) => { if (!e.target.closest(".nota-temps")) mostraNota(n.id); });
  const num = document.createElement("span");
  num.className = "num-nota";
  num.textContent = numNota(n);
  plega.append(num);
  cap.append(plega);
  if (n.inici != null) {
    const temps = document.createElement("button");
    temps.className = "nota-temps";
    temps.dataset.focus = `temps-${n.id}`;
    temps.textContent = fmt(muntatgeDe(n.inici));
    temps.title = "Ves a aquest moment del vídeo";
    temps.addEventListener("click", () => vesANota(n));
    cap.append(temps);
  }
  const cita = document.createElement("span");
  cita.className = "nota-cita";
  cita.textContent = n.inici != null && n.cita ? `«${n.cita}»` : "Per a tot el vídeo";
  cap.append(cita);
  li.append(cap);
  for (const m of n.fil) {
    const p = document.createElement("p");
    if (m.de === "claude") {
      p.className = "nota-claude";
      const qui = document.createElement("b");
      qui.textContent = "Claude";
      p.append(qui, document.createTextNode(m.text));
    } else {
      p.className = "nota-text";
      p.textContent = m.text;
    }
    li.append(p);
  }
  if (n.estat === "pregunta" && n.al_xat) {
    const p = document.createElement("p");
    p.className = "nota-al-xat";
    p.textContent = "Aquesta pregunta respon-la al xat de Claude, no aquí: és un permís (per exemple, baixar un fitxer d'internet).";
    li.append(p);
  } else if (n.estat === "pregunta" || (n.estat === "feta" && respostesObertes.has(n.id))) li.append(formResposta(n, escrit));
  const peu = document.createElement("div");
  peu.className = "nota-peu";
  const xip = document.createElement("span");
  xip.className = "xip-nota";
  xip.textContent = etiquetaEstat(n);
  peu.append(xip);
  const enllac = (text, fn) => {
    const b = document.createElement("button");
    b.className = "enllac";
    b.dataset.focus = `${text}-${n.id}`;
    b.textContent = text;
    b.addEventListener("click", fn);
    peu.append(b);
  };
  if (n.estat === "esborrany") enllac("Treu", () => treuNota(n.id));
  if (n.estat === "feta" && !respostesObertes.has(n.id)) {
    enllac("Respon", () => {
      respostesObertes.add(n.id);
      pintaNotes();
      $(`.respon-nota textarea[data-id="${n.id}"]`)?.focus();
    });
  }
  li.append(peu);
  return li;
}

function formResposta(n, escrit) {
  const form = document.createElement("form");
  form.className = "respon-nota";
  const camp = document.createElement("textarea");
  Object.assign(camp, { rows: 1, maxLength: 4000, value: escrit,
    placeholder: n.estat === "pregunta" ? "Respon…" : "Què vols que hi canviï?" });
  camp.dataset.id = n.id;
  camp.dataset.focus = `resposta-${n.id}`;
  camp.setAttribute("aria-label", `Resposta a la nota ${numNota(n)}`);
  const b = document.createElement("button");
  b.type = "submit";
  b.dataset.focus = `envia-${n.id}`;
  b.className = "boto petit";
  b.textContent = "Envia";
  form.append(camp, b);
  form.addEventListener("submit", (e) => { e.preventDefault(); respon(n.id, camp); });
  camp.addEventListener("input", () => { esborranysResposta.set(n.id, camp.value); ajustaAlcada(camp); });
  camp.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); respon(n.id, camp); }
    else if (e.key === "Escape") { e.stopPropagation(); camp.blur(); }
  });
  queueMicrotask(() => ajustaAlcada(camp));
  return form;
}

// Un camp de text que creix amb el que s'hi escriu (fins al màxim que diu l'estil).
function ajustaAlcada(camp) {
  camp.style.height = "auto";
  camp.style.height = `${camp.scrollHeight}px`;
}

// El text es queda al camp fins que el servidor l'ha desat: si falla, no es perd (encara que la llista s'hagi
// tornat a pintar mentrestant: el que hi ha escrit es conserva, vegeu pintaNotes). Revisió de Codex.
const enviantResposta = new Set();
async function respon(id, camp) {
  const text = camp.value.trim();
  if (!text || enviantResposta.has(id)) return;
  enviantResposta.add(id);
  try {
    respostaNotes(await api("/api/notes", { accio: "respon", id, text }));
  } catch (e) {
    avis(e.message, 5000);
    return;
  } finally {
    enviantResposta.delete(id);
  }
  esborranysResposta.delete(id);
  if (respostesObertes.delete(id)) pintaNotes();
  avis(claudeConnectat ? "Resposta enviada a Claude." : "Resposta desada: Claude la veurà quan miri les notes.");
}

async function treuNota(id) {
  try { respostaNotes(await api("/api/notes", { accio: "esborra", id })); } catch (e) { avis(e.message, 5000); }
}

async function enviaNotes() {
  try { respostaNotes(await api("/api/notes", { accio: "envia" })); } catch (e) { avis(e.message, 5000); return; }
  avis(claudeConnectat ? "Enviades a Claude." : "Enviades. Ara escriu-li al xat: «mira les meves notes».", 5000);
}

// Si Claude hi és connectat (espera les notes), si hi treballa o si no hi és. Sense notes i sense Claude, no
// cal dir res. Si s'han enviat notes i Claude no hi és (ni hi treballa), què li has de dir al xat.
function pintaConnexio() {
  const totes = notesDelProjecte();
  const treballa = totes.some((n) => n.estat === "treballant");
  const espera = !treballa && totes.some((n) => n.estat === "enviada");
  for (const el of $$("[data-connexio]")) {  // sota el vídeo, i a Revisa
    el.hidden = !claudeConnectat && !totes.length;
    el.classList.toggle("connectat", claudeConnectat);
    el.classList.toggle("treballa", !claudeConnectat && treballa);
    el.querySelector(".text-connexio").textContent = claudeConnectat ? "Connectat amb Claude"
      : treballa ? "Claude hi treballa" : "No connectat";
  }
  for (const el of $$("[data-avis-connexio]")) el.hidden = claudeConnectat || !espera;
}

function pintaMarquesNotes() {
  const cont = $("#marques-notes");
  cont.textContent = "";
  const d = durada();
  const amb = vista === "directe" && d ? notesVisibles().filter((n) => n.inici != null) : [];
  cont.hidden = !amb.length;
  for (const n of amb) {
    const m = muntatgeDe(n.inici);
    const b = document.createElement("button");
    b.className = `marca-nota estat-${n.estat}`;
    b.textContent = numNota(n);
    b.style.left = `${limita(m / d, 0, 1) * 100}%`;
    b.title = n.fil[0]?.text || "";
    b.setAttribute("aria-label", `Nota ${b.textContent}, al ${fmt(m)}`);
    b.addEventListener("click", () => vesANota(n));
    cont.append(b);
  }
}

// Des del número de la línia de temps (o del temps d'una nota): el vídeo hi va i la nota s'obre.
function vesANota(n) {
  if (n.inici != null) {
    if (vista !== "directe") canviaVista("directe");
    vesAOriginal(n.inici);
  }
  mostraNota(n.id, { obre: true });
  const el = $(`#llista-notes [data-id="${n.id}"]`);
  if (!el) return;
  el.classList.remove("llum");
  void el.offsetWidth;  // perquè l'animació torni a començar
  el.classList.add("llum");
}

// En començar a escriure, la nota es queda al moment on era el vídeo (i el vídeo s'atura). Sempre on és el
// vídeo, no a la paraula marcada: una paraula marcada fa estona deixava la nota lluny d'on es mirava (Codex).
function fixaMomentNota() {
  if (momentNota) return;
  if (sona()) atura();
  const t = tempsOriginalAra();
  const paraula = t == null || !P.paraules.length ? null : Math.max(0, paraulaAbans(t));
  momentNota = paraula == null ? { tot: true } : { paraula, m: muntatgeDe(P.paraules[paraula].inici) };
  pintaMomentNota();
}

function pintaMomentNota() {
  const b = $("#temps-nota");
  const tot = !!momentNota?.tot;
  b.classList.toggle("tot", tot);
  b.textContent = tot ? "Tot el vídeo" : fmt(momentNota ? momentNota.m : tempsMuntatge());
  b.title = tot ? "Toca-ho per fer-la en aquest moment del vídeo" : "Toca-ho per fer una nota per a tot el vídeo";
  $("#text-nota").setAttribute("aria-label", tot ? "Nota per a Claude per a tot el vídeo"
    : `Nota per a Claude al ${b.textContent} del vídeo`);
}

function obreNota() {
  if (vestint) mostraDreta("notes");
  if (document.body.classList.contains("sense-reproductor")) mostraColumna("reproductor", true);
  $("#text-nota").focus();
}

async function desaNota() {
  const camp = $("#text-nota");
  const text = camp.value.trim();
  if (!text || camp.readOnly) return;  // mentre es desa, un altre ↩ no en fa una de repetida (Codex)
  fixaMomentNota();
  const paraula = momentNota.tot ? null : momentNota.paraula;
  camp.readOnly = true;
  try {
    respostaNotes(await api("/api/notes", { accio: "afegeix", text, paraula }));
  } catch (e) {
    avis(e.message, 5000);
    return;
  } finally {
    camp.readOnly = false;
  }
  camp.value = "";
  ajustaAlcada(camp);
  momentNota = null;
  pintaMomentNota();
  camp.blur();
  if (!llegeix("tallat.nota-desada", false)) {
    desa("tallat.nota-desada", true);
    avis("Nota desada. Quan acabis, toca «Envia a Claude».", 5000);
  } else avis("Nota desada.");
}

function instalaNotes() {
  const camp = $("#text-nota");
  camp.addEventListener("focus", fixaMomentNota);
  camp.addEventListener("input", () => ajustaAlcada(camp));
  camp.addEventListener("blur", () => {
    if (camp.value.trim()) return;  // el que s'ha començat a escriure es queda al seu moment
    momentNota = null;
    pintaMomentNota();
  });
  camp.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); desaNota(); }
    else if (e.key === "Escape") { e.stopPropagation(); camp.blur(); }
  });
  $("#nova-nota").addEventListener("submit", (e) => { e.preventDefault(); desaNota(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) notesTornenASortir(); });
  const moment = $("#temps-nota");
  moment.addEventListener("pointerdown", (e) => e.preventDefault());  // que no es perdi el focus del text
  moment.addEventListener("click", () => {
    if (momentNota?.tot) { momentNota = null; fixaMomentNota(); }
    else { if (sona()) atura(); momentNota = { tot: true }; pintaMomentNota(); }
    camp.focus();
  });
  for (const b of $$("[data-copia-frase]")) b.addEventListener("click", async () => {
    const frase = $("#frase-connexio").textContent;
    try {
      await navigator.clipboard.writeText(frase);
      avis("Copiat. Enganxa-ho al xat de Claude.");
    } catch { avis(`Escriu-li al xat: «${frase}»`, 5000); }
  });
}

// --- Revisa ----------------------------------------------------------------------------------
// L'estació de les revisions finals: l'esborrany exportat (una versió) gran, com el veurà la gent, i a la dreta les
// notes d'aquella versió, cada una amb la miniatura del seu moment. Claude les fa i en treu una versió nova: les
// notes de cada versió no es barregen amb les de la següent. Les notes són les mateixes que les d'editar
// (notes.json), però porten `versio` i `t_versio` (el segon d'aquell vídeo).

let revisant = false;
let versionsRevisa = [];   // els esborranys, del més antic al més nou: [{nom, n, data}]
let versioRevisa = null;   // el nom del que es mira
let darrerExport = null;
let momentRevisa = null;   // on va la nota que s'escriu: {versio, t} (el vídeo s'hi atura)
const esborranysRevisa = new Map();  // la nota a mig escriure de cada versió, si se'n canvia: {text, moment}
let versioNovaEsperant = false;      // n'ha arribat una de nova mentre s'escrivia: s'hi va en acabar
let temporitzadorVistesRevisa = null;
const FOTOGRAMA = 1 / 30;
const vRevisa = () => $("#video-revisa");
const fmtDecima = (t) => {
  t = Math.max(0, t || 0);
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${m}:${s < 10 ? "0" : ""}${s.toFixed(1).replace(".", ",")}`;
};

function canviaEstacio(nom, { enfoca = true } = {}) {
  const abans = revisant ? "revisa" : vestint ? "vesteix" : "edita";
  revisant = nom === "revisa";
  vestint = nom === "vesteix";
  document.body.classList.toggle("revisant", revisant);
  document.body.classList.toggle("vestint", vestint);
  $("#revisa").hidden = !revisant;
  $("#vesteix-dreta").hidden = !vestint;
  for (const b of $$(".estacions button")) b.setAttribute("aria-checked", String(b.dataset.estacio === nom));
  // Les notes per a Claude: a Vesteix, a la columna de la dreta; a Edita, sota el vídeo.
  (vestint ? $("#vesteix-dreta") : $(".reproductor")).append($("#notes"));
  document.body.classList.remove("calaix-obert");
  if (ambCalaix()) obreCalaix(false);
  if (abans === "edita" && nom !== "edita") deixaSeleccio();
  if (abans === "vesteix" && nom !== "vesteix") {
    deixaCapa(); pecaTriada = null; tancaElQueHiHagi();
    aturaCarta();
    $("#tauler").hidden = true;
    document.body.classList.remove("amb-tauler");
  }
  if (vestint) pintaVesteix();
  if (revisant) { atura(); pintaRevisa(); requestAnimationFrame(ajustaBarraRevisa); }
  else vRevisa().pause();
  if (P) desa(`tallat.estacio.${P.clau_projecte}`, nom);
  if (enfoca) visible(`.estacions [data-estacio="${nom}"]`)?.focus({ preventScroll: true, focusVisible: false });
}

// Els esborranys d'aquest projecte són les versions. Si n'arriba un de nou, és el que es mira.
function actualitzaVersions(exports) {
  const abans = versionsRevisa.length;
  // Només les acabades: mentre s'exporta, el fitxer encara no és sencer (Codex).
  versionsRevisa = exports.filter((x) => x.qualitat === "esborrany" && x.complet !== false).reverse()
    .map((x, i) => ({ ...x, n: i + 1 }));
  const nou = versionsRevisa.length > abans && abans > 0;
  const escrivint = !!$("#text-nota-revisa").value.trim();
  if (!versionsRevisa.some((v) => v.nom === versioRevisa)) triaVersio(versionsRevisa.at(-1)?.nom ?? null);
  else if (nou && escrivint) {
    versioNovaEsperant = true;  // no es canvia sota la nota que s'escriu (Codex): s'hi va en desar-la
    if (revisant) avis(`Ja tens la versió ${versionsRevisa.length}: la veuràs quan desis aquesta nota.`, 5000);
  } else if (nou) {
    triaVersio(versionsRevisa.at(-1).nom);
    if (revisant) avis(`Ja tens la versió ${versionsRevisa.length}. Mira-la i deixa-hi notes.`, 5000);
  }
  pintaRevisa();
}

// Canviar de versió: la nota que s'estigués escrivint es queda amb la seva versió (i hi torna quan s'hi torna).
function triaVersio(nom) {
  if (nom === versioRevisa) return;
  const camp = $("#text-nota-revisa");
  if (versioRevisa && camp.value.trim()) esborranysRevisa.set(versioRevisa, { text: camp.value, moment: momentRevisa });
  versioRevisa = nom;
  const desat = esborranysRevisa.get(nom);
  esborranysRevisa.delete(nom);
  camp.value = desat?.text || "";
  ajustaAlcada(camp);
  momentRevisa = desat?.moment || null;
  if (momentRevisa) {
    const v = vRevisa();
    v.addEventListener("loadedmetadata", () => { v.currentTime = momentRevisa?.t ?? 0; }, { once: true });
  }
}

function pintaRevisa() {
  if (!revisant) return;
  const hiHa = versionsRevisa.length > 0;
  $("#revisa-buit").hidden = hiHa;
  $("#revisa-cos").hidden = !hiHa;
  $("#nova-versio").hidden = !hiHa;
  const pills = $("#versions-revisa");
  pills.textContent = "";
  for (const v of versionsRevisa) {
    const b = document.createElement("button");
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(v.nom === versioRevisa));
    b.textContent = `Versió ${v.n}`;
    b.title = v.data;
    b.addEventListener("click", () => { triaVersio(v.nom); pintaRevisa(); });
    pills.append(b);
  }
  if (!hiHa) return;
  const v = vRevisa();
  const src = `/exports/${encodeURIComponent(versioRevisa)}`;
  if (v.getAttribute("src") !== src) { v.setAttribute("src", src); pintaTempsRevisa(); }
  pintaNotesRevisa();
}

const notesDeRevisa = () => notesDelProjecte().filter((n) => n.versio === versioRevisa)
  .sort((a, b) => (a.t_versio ?? 0) - (b.t_versio ?? 0) || a.id - b.id);

function pintaNotesRevisa() {
  const llista = $("#llista-revisa");
  const actiu = document.activeElement;
  const focus = actiu?.closest?.("#llista-revisa") ? actiu.dataset.focus : null;
  const notes = notesDeRevisa();
  llista.textContent = "";
  for (const n of notes) llista.append(targetaRevisa(n));
  if (focus) llista.querySelector(`[data-focus="${focus}"]`)?.focus({ preventScroll: true });
  $("#buit-notes-revisa").hidden = notes.length > 0;
  const perEnviar = notes.filter((n) => n.estat === "esborrany").length;
  const pendents = notes.filter((n) => !["feta", "esborrany"].includes(n.estat)).length;
  $("#compte-notes-revisa").textContent = notes.length
    ? [`${notes.length}`, perEnviar && `${perEnviar} per enviar`, pendents && `${pendents} a Claude`].filter(Boolean).join(" · ") : "";
  const noves = notes.filter(esNova);
  $("#noves-notes-revisa").textContent = noves.length ? `· ${noves.length === 1 ? "1 nova" : `${noves.length} noves`}` : "";
  // Les targetes es veuen senceres: si la pàgina es veu, la resposta ja s'ha vist. El punt es queda un moment
  // (perquè es vegi quina és la nova) i després marxa.
  clearTimeout(temporitzadorVistesRevisa);
  if (noves.length && !document.hidden) {
    temporitzadorVistesRevisa = setTimeout(() => {
      if (!revisant || document.hidden) return;
      noves.forEach(marcaVista);
      pintaNotesRevisa();
    }, 2500);
  }
  const envia = $("#envia-revisa");
  envia.hidden = !perEnviar;
  envia.textContent = `Envia a Claude (${perEnviar})`;
  pintaConnexio();
  const marques = $("#marques-revisa");
  marques.textContent = "";
  const d = vRevisa().duration;
  for (const n of notes) {
    if (!(d > 0)) break;
    const b = document.createElement("button");
    b.className = `marca-nota estat-${n.estat}`;
    b.textContent = numNota(n);
    b.style.left = `${limita((n.t_versio ?? 0) / d, 0, 1) * 100}%`;
    b.title = n.fil[0]?.text || "";
    b.setAttribute("aria-label", `Nota ${b.textContent}, al ${fmtDecima(n.t_versio)}`);
    b.addEventListener("click", () => vesANotaRevisa(n));
    marques.append(b);
  }
}

function targetaRevisa(n) {
  const el = document.createElement("div");
  el.className = `targeta-nota estat-${n.estat}`;
  el.dataset.id = n.id;
  const mini = document.createElement("button");
  mini.className = "mini-nota";
  mini.dataset.focus = `mini-${n.id}`;
  mini.setAttribute("aria-label", `Ves al ${fmtDecima(n.t_versio)}`);
  if (n.miniatura) {
    const img = document.createElement("img");
    img.src = `/notes-miniatures/${encodeURIComponent(n.miniatura)}`;
    img.alt = "";
    mini.append(img);
  }
  mini.addEventListener("click", () => vesANotaRevisa(n));
  const cos = document.createElement("div");
  cos.className = "cos-targeta";
  const meta = document.createElement("div");
  meta.className = "meta-targeta";
  const num = document.createElement("span");
  num.className = "num-nota";
  num.textContent = numNota(n);
  const temps = document.createElement("button");
  temps.className = "temps-revisa";
  temps.dataset.focus = `temps-${n.id}`;
  temps.textContent = fmtDecima(n.t_versio);
  temps.title = "Ves a aquest moment";
  temps.addEventListener("click", () => vesANotaRevisa(n));
  const xip = document.createElement("span");
  xip.className = "xip-nota";
  xip.textContent = etiquetaEstat(n);
  meta.append(num, temps, xip);
  if (esNova(n)) {
    const punt = document.createElement("span");
    punt.className = "punt-nou";
    punt.setAttribute("aria-label", "resposta nova");
    meta.append(punt);
  }
  cos.append(meta);
  for (const m of n.fil) {
    const p = document.createElement("p");
    if (m.de === "claude") {
      p.className = "nota-claude";
      const qui = document.createElement("b");
      qui.textContent = "Claude";
      p.append(qui, document.createTextNode(m.text));
    } else {
      p.className = "nota-text";
      p.textContent = m.text;
    }
    cos.append(p);
  }
  if (n.estat === "pregunta" && n.al_xat) {
    const p = document.createElement("p");
    p.className = "nota-al-xat";
    p.textContent = "Aquesta pregunta respon-la al xat de Claude, no aquí: és un permís (per exemple, baixar un fitxer d'internet).";
    cos.append(p);
  } else if (n.estat === "pregunta" || (n.estat === "feta" && respostesObertes.has(n.id))) {
    cos.append(formResposta(n, esborranysResposta.get(n.id) || ""));
  }
  const peu = document.createElement("div");
  peu.className = "nota-peu";
  const enllac = (text, fn) => {
    const b = document.createElement("button");
    b.className = "enllac";
    b.dataset.focus = `${text}-${n.id}`;
    b.textContent = text;
    b.addEventListener("click", fn);
    peu.append(b);
  };
  if (n.estat === "esborrany") enllac("Treu", () => treuNota(n.id));
  if (n.estat === "feta" && !respostesObertes.has(n.id)) enllac("Respon", () => {
    respostesObertes.add(n.id);
    pintaNotesRevisa();
    $(`#llista-revisa .respon-nota textarea[data-id="${n.id}"]`)?.focus();
  });
  if (peu.children.length) cos.append(peu);
  el.append(mini, cos);
  return el;
}

function vesANotaRevisa(n) {
  const v = vRevisa();
  v.pause();
  v.currentTime = n.t_versio ?? 0;
  const el = $(`#llista-revisa [data-id="${n.id}"]`);
  if (!el) return;
  el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  el.classList.remove("llum");
  void el.offsetWidth;
  el.classList.add("llum");
}

function pintaTempsRevisa() {
  const v = vRevisa();
  const t = v.currentTime || 0, d = v.duration || 0;
  $("#tc-revisa").textContent = fmtDecima(t);
  $("#durada-revisa").textContent = fmt(d);
  const f = d ? limita(t / d, 0, 1) : 0;
  $("#ple-revisa").style.width = `${f * 100}%`;
  $("#capcal-revisa").style.left = `${f * 100}%`;
  $("#rv-play").classList.toggle("sona", !v.paused);
  $("#rv-play").setAttribute("aria-label", v.paused ? "Reprodueix" : "Atura");
  $("#temps-nota-revisa").textContent = fmtDecima(momentRevisa ? momentRevisa.t : t);
}

// La barra i els números, de l'amplada del vídeo que es veu (canvia amb la finestra).
function ajustaBarraRevisa() {
  const ample = vRevisa().getBoundingClientRect().width;
  if (ample > 0) $("#revisa-barra").style.maxWidth = `${Math.max(280, ample)}px`;
}

// La miniatura del fotograma que es veu (petita: només ha de recordar de quin moment parla la nota).
function miniaturaRevisa() {
  const v = vRevisa();
  try {
    const alt = 240, ample = Math.round(alt * ((v.videoWidth / v.videoHeight) || 9 / 16));
    const c = document.createElement("canvas");
    c.width = ample;
    c.height = alt;
    c.getContext("2d").drawImage(v, 0, 0, ample, alt);
    return c.toDataURL("image/jpeg", 0.72);
  } catch { return null; }
}

async function desaNotaRevisa() {
  const camp = $("#text-nota-revisa");
  const text = camp.value.trim();
  if (!text || camp.readOnly || !versioRevisa) return;
  const v = vRevisa();
  v.pause();
  const { versio, t } = momentRevisa?.versio === versioRevisa ? momentRevisa : { versio: versioRevisa, t: v.currentTime || 0 };
  camp.readOnly = true;
  try {
    // La miniatura ha de ser del moment de la nota: si el vídeo s'ha mogut, s'hi torna i s'espera que hi sigui (Codex).
    if (Math.abs(v.currentTime - t) > 0.04) {
      await new Promise((fet) => {
        v.addEventListener("seeked", fet, { once: true });
        setTimeout(fet, 1500);
        v.currentTime = t;
      });
    }
    respostaNotes(await api("/api/notes", { accio: "afegeix", text, versio, t, miniatura: miniaturaRevisa() }));
  } catch (e) {
    avis(e.message, 5000);
    return;
  } finally {
    camp.readOnly = false;
  }
  // Mentre es desava s'ha pogut triar una altra versió: el camp ja és el d'aquella (amb la seva nota a mig
  // escriure), i no s'ha de buidar. La nota desada, que s'havia guardat com a esborrany de la seva versió, fora (Codex).
  if (versioRevisa !== versio || camp.value.trim() !== text) {
    if (esborranysRevisa.get(versio)?.text.trim() === text) esborranysRevisa.delete(versio);
    avis("Nota desada.", 3000);
    return;
  }
  camp.value = "";
  ajustaAlcada(camp);
  momentRevisa = null;
  pintaTempsRevisa();
  camp.blur();
  if (versioNovaEsperant) {
    versioNovaEsperant = false;
    triaVersio(versionsRevisa.at(-1)?.nom ?? versioRevisa);
    pintaRevisa();
    avis(`Nota desada. Ara mires la versió ${versionsRevisa.length}, la nova.`, 4500);
  } else avis("Nota desada. Quan acabis de mirar la versió, toca «Envia a Claude».", 4000);
}

async function enviaRevisa() {
  try { respostaNotes(await api("/api/notes", { accio: "envia", versio: versioRevisa })); } catch (e) { avis(e.message, 5000); return; }
  avis(claudeConnectat ? "Enviades a Claude. Quan les acabi, en farà una versió nova."
    : "Enviades. Ara escriu-li al xat: «mira les meves notes».", 5000);
}

function teclaRevisa(e) {
  const v = vRevisa();
  if (e.metaKey || e.ctrlKey || e.altKey || !versioRevisa) return;
  if (e.key === " " && e.target.closest?.("button") && e.target.matches(":focus-visible")) return;
  if (e.key === " ") { e.preventDefault(); v.paused ? v.play().catch(() => {}) : v.pause(); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); v.currentTime = Math.max(0, v.currentTime - 1); }
  else if (e.key === "ArrowRight") { e.preventDefault(); v.currentTime = Math.min(v.duration || 0, v.currentTime + 1); }
  else if (e.key === ",") { e.preventDefault(); v.pause(); v.currentTime = Math.max(0, v.currentTime - FOTOGRAMA); }
  else if (e.key === ".") { e.preventDefault(); v.pause(); v.currentTime = Math.min(v.duration || 0, v.currentTime + FOTOGRAMA); }
  else if (e.code === "KeyN" && !e.shiftKey) { e.preventDefault(); $("#text-nota-revisa").focus(); }
}

function instalaRevisa() {
  for (const b of $$(".estacions button")) b.addEventListener("click", () => canviaEstacio(b.dataset.estacio));
  const v = vRevisa();
  for (const nom of ["timeupdate", "seeked", "loadedmetadata", "play", "pause"]) v.addEventListener(nom, pintaTempsRevisa);
  v.addEventListener("loadedmetadata", () => { pintaNotesRevisa(); ajustaBarraRevisa(); });  // els números necessiten la durada
  const bucle = () => { if (!v.paused) { pintaTempsRevisa(); requestAnimationFrame(bucle); } };
  let esperaCarrega = null;
  const carregant = (si) => {
    clearTimeout(esperaCarrega);
    if (si) esperaCarrega = setTimeout(() => { $("#carregant-revisa").hidden = false; }, 300);
    else $("#carregant-revisa").hidden = true;
  };
  v.addEventListener("waiting", () => carregant(!v.paused));
  v.addEventListener("seeking", () => carregant(!v.paused));
  for (const nom of ["playing", "seeked", "pause", "canplay", "emptied"]) v.addEventListener(nom, () => carregant(false));
  v.addEventListener("play", () => requestAnimationFrame(bucle));
  const commuta = () => { v.paused ? v.play().catch(() => {}) : v.pause(); };
  v.addEventListener("click", commuta);
  $("#rv-play").addEventListener("click", commuta);
  addEventListener("resize", () => { if (revisant) ajustaBarraRevisa(); });
  const linia = $("#linia-revisa");
  let arrossega = false;
  const posa = (e) => {
    const r = linia.getBoundingClientRect();
    if (v.duration) v.currentTime = limita((e.clientX - r.left) / r.width, 0, 1) * v.duration;
  };
  linia.addEventListener("pointerdown", (e) => { linia.setPointerCapture(e.pointerId); arrossega = true; v.pause(); posa(e); });
  linia.addEventListener("pointermove", (e) => { if (arrossega) posa(e); });
  linia.addEventListener("pointerup", () => { arrossega = false; });
  const salta = (dt, atura_ = false) => () => {
    if (atura_) v.pause();
    v.currentTime = limita(v.currentTime + dt, 0, v.duration || 0);
  };
  $("#rv-enrere").addEventListener("click", salta(-1));
  $("#rv-endavant").addEventListener("click", salta(1));
  $("#rv-fotograma-enrere").addEventListener("click", salta(-FOTOGRAMA, true));
  $("#rv-fotograma-endavant").addEventListener("click", salta(FOTOGRAMA, true));
  const camp = $("#text-nota-revisa");
  camp.addEventListener("focus", () => {
    v.pause();
    if (!momentRevisa) momentRevisa = { versio: versioRevisa, t: v.currentTime || 0 };
    pintaTempsRevisa();
  });
  camp.addEventListener("blur", () => { if (!camp.value.trim()) { momentRevisa = null; pintaTempsRevisa(); } });
  camp.addEventListener("input", () => ajustaAlcada(camp));
  camp.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); desaNotaRevisa(); }
    else if (e.key === "Escape") { e.stopPropagation(); camp.blur(); }
  });
  $("#nova-nota-revisa").addEventListener("submit", (e) => { e.preventDefault(); desaNotaRevisa(); });
  $("#envia-revisa").addEventListener("click", enviaRevisa);
  for (const b of [$("#nova-versio"), $("#primera-versio")]) b.addEventListener("click", () => comencaRender("esborrany"));
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

const RITMES = [0, 0.5, 0.35, 0.25];  // el silenci més llarg que es deixa: del més tranquil (tots) al més àgil
const NOTES_RITME = ["Deixa els silencis tal com són.", "Escurça els silencis de més de mig segon.",
  "Escurça els silencis de més de 0,35 s.", "Escurça els silencis de més de 0,25 s."];

function instalaControls() {
  for (const b of $$("#ritme button")) b.addEventListener("click", () => {
    const v = RITMES[Number(b.dataset.valor)];
    canvia((e) => { e.pausa_maxima = v > 0 ? v : null; }, { repinta: true });
    marcaPausa();
  });
  $("#accepta-instruccions").addEventListener("click", acceptaInstruccions);
  for (const b of $$("#vista button")) b.addEventListener("click", () => {
    if (b.dataset.vista === "esborrany" && !esborrany) {
      const darrer = $$("#versions .item")[0];
      if (darrer) darrer.click();
      return;
    }
    canviaVista(b.dataset.vista);
  });
  $("#fitxer-grafic").addEventListener("change", (e) => {
    const fitxers = [...e.target.files];
    e.target.value = "";
    if (graficPerPujar) pujaImatgesGrafic(graficPerPujar, fitxers);
  });
  $("#fitxer-broll").addEventListener("change", (e) => {
    const fitxer = e.target.files[0];
    if (fitxer && instruccioPerPujar) pujaBroll(instruccioPerPujar, fitxer);
    else if (fitxer && paraulaBrollNou != null) pujaBrollNou(fitxer);
    e.target.value = "";
  });
  instalaTecles();
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
  instalaColumna();
  instalaNotes();
  instalaRevisa();
  instalaVesteix();
  setInterval(miraNovetats, 3000);
  const subtitolsBoto = $("#subtitols");
  subtitolsBoto.addEventListener("click", () => {
    canvia((e) => { e.subtitols = e.subtitols === false; });
    marcaSubtitols();
    avis(estat.subtitols ? "Els renders portaran subtítols." : "Els renders sortiran sense subtítols.");
  });
  $("#desfes").addEventListener("click", desfes);
  $("#refes").addEventListener("click", refes);
  $("#exporta-esborrany").addEventListener("click", () => { tancaFinal(); comencaRender("esborrany"); });
  $("#final").addEventListener("click", obreFinal);
  $("#cancella-final").addEventListener("click", tancaFinal);
  $("#canvia-carpeta").addEventListener("click", () => triaCarpeta("tria"));
  $("#carpeta-projecte").addEventListener("click", () => triaCarpeta("projecte"));
  $("#fet-mostra").addEventListener("click", () => darrerFet && mostraAlFinder(darrerFet));
  $("#fet-tanca").addEventListener("click", () => { $("#fet-export").hidden = true; });
  $("#velo").addEventListener("click", () => {
    tancaFinal();
    if (!$("#full-estil").hidden) tancaEstilVideo();
    if (!$("#full-afegeix").hidden) tancaAfegeix();
  });
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
    if (e.target.matches?.("input, textarea, select")) return;
    if (revisant) { teclaRevisa(e); return; }
    // A Vesteix, la peça triada es treu amb ⌫ (com a Keynote) i es deixa amb Esc.
    if (vestint && pecaTriada && pestanyaDreta === "peces" && !e.metaKey && !e.ctrlKey && (e.key === "Backspace" || e.key === "Delete")
        && $("#full-final").hidden && !$(".barra").classList.contains("editant-estil")) {
      e.preventDefault();
      treuPecaTriada();
      return;
    }
    if (capaTriada && e.key === "Escape") { deixaCapa(); if (pecaTriada) deixaPeca(); return; }
    if (!$("#full-final").hidden) { if (e.key === "Escape") tancaFinal(); return; }
    if (e.key === "Escape" && tornaEnrere()) return;
    if (e.key === "Escape" && vestint && pecaTriada) { deixaPeca(); return; }
    if (ES_MAC ? e.ctrlKey && e.metaKey && e.code === "KeyS"  // ⌃⌘S, com al Finder
      : e.ctrlKey && e.shiftKey && !e.altKey && !ambAltGr(e) && e.code === "KeyE") {  // Ctrl+Maj+E
      e.preventDefault();
      mostraColumna("barra", document.body.classList.contains("sense-barra"));
      return;
    }
    if (ES_MAC ? e.altKey && e.metaKey && e.code === "KeyV"  // ⌥⌘V
      : e.ctrlKey && e.shiftKey && !e.altKey && !ambAltGr(e) && e.code === "KeyV") {  // Ctrl+Maj+V
      e.preventDefault();
      mostraColumna("reproductor", document.body.classList.contains("sense-reproductor"));
      return;
    }
    // Al tauler no hi ha el vídeo gran: l'espai, les fletxes i la N no hi fan res (cada targeta té el seu).
    if (vestint && !$("#tauler").hidden && (["ArrowLeft", "ArrowRight", " "].includes(e.key) || e.code === "KeyN")) return;
    // Amb el teclat, l'espai prem el botó que té el focus (Mantén, Treu…); si no, reprodueix o atura.
    if (e.key === " " && e.target.closest?.("button") && e.target.matches(":focus-visible")) return;
    if (e.key === " ") { e.preventDefault(); R.aturaA = null; sona() ? atura() : reprodueix(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); vesA(tempsMuntatge() - 5); }
    else if (e.key === "ArrowRight") { e.preventDefault(); vesA(tempsMuntatge() + 5); }
    else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? refes() : desfes(); }
    else if (e.code === "KeyN" && !e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey) { e.preventDefault(); obreNota(); }
  });
}

function marcaSubtitols() {
  $("#subtitols").setAttribute("aria-checked", String(estat.subtitols !== false));
  pintaResumSub();
}

function marcaPausa() {
  // Si el kit en diu un altre (0,6 s, per exemple), el control es posa al més semblant.
  const actual = estat.pausa_maxima || 0;
  let k = 0;
  if (actual > 0) k = [1, 2, 3].reduce((millor, j) => (Math.abs(RITMES[j] - actual) < Math.abs(RITMES[millor] - actual) ? j : millor), 1);
  marcaSegmentat("ritme", String(k));
  const aMida = actual > 0 && !RITMES.includes(actual);  // el teu estil en diu un altre (0,6 s…): es diu
  $("#nota-ritme").textContent = aMida
    ? `El teu estil escurça els silencis de més de ${String(actual).replace(".", ",")} s.` : NOTES_RITME[k];
}

async function inicia() {
  instalaControls();
  instalaText();
  instalaBarreta();
  instalaReels();
  instalaGrupsOpcions();
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
  estilsVideo = P.estils_video || [];
  kitEstil.titol = P.estil_titol;
  aplicaMarca(P);
  aplicaBroll(P);
  aplicaSo(P);
  kits = P.kits || [];
  kitActual = P.kit;
  pintaKits();
  bibliotecaLletres = P.biblioteca_lletres || bibliotecaLletres;
  versioEstil = P.versio_estil;
  carregaFontsKit(P.fonts_kit || []);
  kitEstil.subtitols = P.estil_subtitols;
  recalculaEstils();
  pintaPanellEstil();
  pintaVersions(P.exports || []);
  pintaCarpeta(P);
  pintaReels();
  try { biblioteca = await api("/api/biblioteca"); } catch { biblioteca = { broll: [], sticker: [] }; }
  pintaInstruccions();
  darrerExport = P.exports?.[0]?.nom ?? null;
  actualitzaVersions(P.exports || []);
  carregaNotes();
  if (P.feina?.estat === "treballant") seguimentFeina(P.feina);
  consultaFeina.darrer = P.feina?.fitxer;
  // Si recarregues la pàgina, tornes a l'estació on eres.
  const estacio = llegeix(`tallat.estacio.${P.clau_projecte}`, "edita");
  if (estacio !== "edita" && ["vesteix", "revisa"].includes(estacio)) canviaEstacio(estacio, { enfoca: false });
  // El primer cop (i un cop més si la pàgina ha canviat: abans s'hi desava «true»), la visita guiada.
  if (Number(llegeix("tallat.guia-vista", 0)) < VERSIO_GUIA) setTimeout(obreGuia, 600);
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
  if (mostresEnCurs) return;
  if (mostresSo && mostraNivell === nivell) return;
  $("#s-preparant").hidden = false;
  mostresEnCurs = (async () => {
    try {
      await esperaDesats();
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

function pintaResumSo() {
  if (!estilSo) return;
  const efectes = { cap: "sense efectes", pocs: "pocs efectes", molts: "molts efectes" }[estilSo.efectes || "pocs"];
  $("#nom-so").textContent = `${estilSo.neteja !== false ? "Veu neta" : "Veu sense netejar"} · ${efectes}`;
}

function pintaSo() {
  pintaResumSo();
  if (!estilSo || $("#panell-so").hidden) return;
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
  // Abans i neta: un toc la fa sonar (i atura l'altra); un altre toc l'atura.
  for (const boto of $$(".mostra-so")) {
    const audio = $(`#${boto.dataset.audio}`);
    boto.addEventListener("click", () => {
      if (sona()) atura();  // que no soni alhora que el vídeo
      for (const altre of $$(".abans-despres audio")) if (altre !== audio) altre.pause();
      if (audio.paused) audio.play().catch(() => avis("Encara s'està preparant la mostra.")); else audio.pause();
    });
    for (const ev of ["play", "pause", "ended"]) {
      audio.addEventListener(ev, () => boto.setAttribute("aria-pressed", String(!audio.paused)));
    }
  }
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
// La crida, l'estil dels gràfics, la lletra de mà i els colors prohibits no són a la pàgina (cadascú tria l'estil de cada
// gràfic, i la resta són casos concrets): si un kit els té, es fan servir igual; es posen al xat.
const LLETRES_MARCA = [["m-lletra-titols", "lletra_titols"], ["m-lletra-text", "lletra_text"],
  ["m-lletra-accent", "lletra_accent"]];

function aplicaMarca(r) {
  if (r.paleta_grafics) { paletaGrafics = r.paleta_grafics; previaBruta = true; }
  if (r.mostres_grafics) mostresGrafics = r.mostres_grafics;
  if (!r.estil_marca) return;
  estilMarca = { ...r.estil_marca, ...pendents.marca };
  pintaVesteix();
  pintaResumMarca();
  pintaPanellMarca();
}

function pintaResumMarca() {
  const m = estilMarca;
  if (!m) return;
  pintaOfertaMarca();
  const colors = COLORS_MARCA.map(([, clau]) => m[clau]).filter(Boolean);
  for (const mostra of $$("#mostra-marca, #llista-kits .mostra-actual")) {
    mostra.querySelectorAll("i").forEach((el, k) => { el.style.background = colors[k] || ""; });
  }
  const nom = kits.find((k) => k.id === kitActual)?.nom || "El teu estil";
  const lletres = [...new Set([m.lletra_titols, m.lletra_text].filter(Boolean))].join(" · ");
  $("#nom-marca").textContent = colors.length ? lletres || "Els teus colors" : "Encara no els has triat";
  $("#nom-kit-guardat").textContent = kits.length > 1 ? `Ara: ${nom} (en tens ${kits.length})` : nom;
}

function pintaPanellMarca() {
  const m = estilMarca;
  if (!m || $("#panell-marca").hidden) return;
  for (const [id, clau] of COLORS_MARCA) $(`#${id}`).value = (m[clau] || "#8E8E93").toLowerCase();
  for (const [id, clau] of LLETRES_MARCA) {
    if (document.activeElement !== $(`#${id}`)) ompleLletres($(`#${id}`), m[clau], { buit: "Sense triar" });
  }
  marcaSegmentat("m-grafics", m.grafics || "normal");
}

function canviaMarca(canvis) {
  estilMarca = { ...estilMarca, ...canvis };
  pintaResumMarca();
  apunta("marca", canvis);
}

function obreMarca() {
  tancaElQueHiHagi();
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
}

function instalaMarca() {
  $("#tanca-marca").addEventListener("click", tornaEnrere);
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
  for (const b of $$("#m-grafics button")) b.addEventListener("click", () => { canviaMarca({ grafics: b.dataset.valor }); pintaPanellMarca(); });
}

inicia();
