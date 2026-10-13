"use strict";
// tallat · pàgina de revisió. Tot passa en aquest ordinador: el servidor local desa cada canvi.

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

async function api(ruta, dades) {
  const opcions = dades === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dades),
  };
  const r = await fetch(ruta, opcions);
  const json = await r.json().catch(() => ({}));
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
  fetch("/api/registre", { method: "POST", headers: { "Content-Type": "application/json" },
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
let instruccions = [];     // instruccions de veu «Claude, …»
let zoomsTram = [];        // quins trossos porten zoom
let notes = [];
let darrerDesplacamentManual = 0;

// --- Desar ----------------------------------------------------------------------------

let cua = Promise.resolve();
let pendent = false;
function sincronitza() {
  if (pendent) return;     // diversos canvis seguits viatgen en una sola petició
  pendent = true;
  cua = cua.then(async () => {
    pendent = false;
    try {
      const r = await api("/api/estat", estat);
      estat.revisio = r.estat.revisio;
      aplicaTrams(r);
      if (!pendent && escoltaPendent != null) { escoltaTall(escoltaPendent); escoltaPendent = null; }
    } catch (e) {
      if (e.codi !== 409) throw e;
      // La pàgina també és oberta en una altra pestanya i allà s'ha desat després.
      estat = e.dades.estat;
      desfer.length = 0;
      refer.length = 0;
      aplicaTrams(e.dades);
      refresca(true);
      marcaPausa();
      avis("Aquesta pàgina també és oberta en una altra pestanya. He carregat els canvis més nous.", 6000);
    }
  }).catch((e) => avis("No s'ha pogut desar: " + e.message));
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
  if (r.subtitols) { liniesSub = r.subtitols; liniaPintada = null; }
  if (r.zooms) zoomsTram = r.zooms;
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
  for (const ids of P.paragrafs) {
    const par = document.createElement("p");
    par.className = "paragraf";
    paragrafsEl.push({ el: par, ids });
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
  }
  actualitzaParaules();
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

function pintaSeleccio() {
  for (const id of marcades) spans.get(id)?.classList.remove("seleccio");
  marcades.clear();
  if (!seleccio) return;
  const [a, b] = [Math.min(seleccio.inici, seleccio.fi), Math.max(seleccio.inici, seleccio.fi)];
  for (let id = a; id <= b; id++) { spans.get(id)?.classList.add("seleccio"); marcades.add(id); }
}

function instalaText() {
  const cont = $("#transcripcio");
  cont.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
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
    if (!s) return;
    const id = +s.dataset.id;
    if (e.altKey) { e.preventDefault(); reprodueixDes(id); return; }
    if (mode === "corregeix") { e.preventDefault(); editaParaula(s, id); return; }
    e.preventDefault();
    seleccio = { inici: id, fi: id };
    pintaSeleccio();
  });
  document.addEventListener("pointermove", (e) => {
    if (!seleccio) return;
    const s = document.elementFromPoint(e.clientX, e.clientY)?.closest?.(".p");
    if (s && +s.dataset.id !== seleccio.fi) { seleccio.fi = +s.dataset.id; pintaSeleccio(); }
  });
  document.addEventListener("pointerup", () => {
    if (!seleccio) return;
    const [a, b] = [Math.min(seleccio.inici, seleccio.fi), Math.max(seleccio.inici, seleccio.fi)];
    seleccio = null;
    pintaSeleccio();
    const ids = Array.from({ length: b - a + 1 }, (_, i) => a + i);
    commuta(ids, ids.some((id) => !esFora(id)));
  });
  $(".text").addEventListener("wheel", () => { darrerDesplacamentManual = performance.now(); }, { passive: true });
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
const R = { v: $("#video-a"), k: 0, reproduint: false, aturaA: null, vigila: { t: -1, des: 0 } };

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
  return acum[k] + limita(R.v.currentTime - a, 0, b - a);
}

function durada() { return vista === "esborrany" ? (esborrany?.durada || vE.duration || 0) : duradaFinal; }

function vesA(m) {
  m = limita(m, 0, durada());
  if (vista === "esborrany") { vE.currentTime = m; return; }
  if (!trams.length) return;
  let k = 0;
  while (k + 1 < trams.length && acum[k + 1] <= m + 1e-6) k++;
  R.k = k;
  R.v.currentTime = trams[k][0] + (m - acum[k]);
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
  const t = R.v.currentTime;
  const k = indexTram(t);
  registre("recolloca", { t: +t.toFixed(3), k, kAbans: R.k });
  if (k >= trams.length) { R.k = trams.length - 1; if (R.reproduint) atura(); return; }
  R.k = k;
  if (t < trams[k][0] - 0.01 && R.reproduint) R.v.currentTime = trams[k][0];
}

function salta() {
  const k = R.k + 1;
  if (k >= trams.length) { atura(); return; }
  registre("salta", { k, cap: trams[k][0], video: ev(R.v) });
  R.k = k;
  R.v.currentTime = trams[k][0];
}

function reprodueix() {
  if (vista === "esborrany") { vE.play(); return; }
  if (!trams.length) return;
  if (tempsMuntatge() >= duradaFinal - 0.05) vesA(0);
  const t = R.v.currentTime;
  const k = indexTram(t);
  if (k >= trams.length) vesA(0);
  else { R.k = k; if (t < trams[k][0]) R.v.currentTime = trams[k][0]; }
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
  R.aturaA = null;
  R.reproduint = false;
  R.v.pause(); vE.pause();
  document.body.classList.remove("reproduint");
}

// Vigilant: si el vídeo diu que sona però el seu temps no avança, el despertem.
function vigila() {
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
  R.v.classList.toggle("zoom", vista === "directe" && !!zoomsTram[Math.min(R.k, trams.length - 1)]);
}

// --- Subtítols en directe ------------------------------------------------------------------------

let liniaPintada = null;
function pintaSubtitols() {
  const capa = $("#capa-subtitols");
  const visible = vista === "directe" && estat?.subtitols !== false && liniesSub.length > 0;
  capa.hidden = !visible;
  if (!visible) return;
  const m = tempsMuntatge();
  const linia = liniesSub.find((l) => m >= l.inici - 0.01 && m < l.final) || null;
  const text = $("#sub-text");
  if (linia !== liniaPintada) {
    liniaPintada = linia;
    text.textContent = "";
    for (const w of linia?.paraules || []) {
      const span = document.createElement("span");
      span.textContent = w.text;
      text.append(span, " ");
    }
  }
  if (!linia) return;
  const spans = text.querySelectorAll("span");
  linia.paraules.forEach((w, i) => {
    const fi = linia.paraules[i + 1]?.inici ?? linia.final;
    spans[i].classList.toggle("vista", m >= w.inici - 0.01);
    spans[i].classList.toggle("actiu", m >= w.inici - 0.01 && m < fi);
  });
}

function aplicaEstilSubtitols(e) {
  if (!e) return;
  const capa = $("#capa-subtitols").style;
  const posa = (k, v) => capa.setProperty(k, v);
  const escapa = (f) => (/^[\w-]+$/.test(f) ? f : `"${f.replace(/"/g, "")}"`);
  posa("--sub-y", `${e.posicio_y * 100}%`);
  posa("--sub-amplada", `${e.amplada_maxima * 100}%`);
  posa("--sub-font", e.font_fitxer ? "system-ui" : escapa(e.font));
  posa("--sub-pes", e.pes);
  posa("--sub-mida", `${e.mida * 100}cqw`);
  posa("--sub-color", e.color);
  posa("--sub-actiu", e.color_actiu);
  posa("--sub-contorn", e.contorn);
  posa("--sub-gruix", `${(e.gruix_contorn || 0) * 2}em`);
  posa("--sub-majuscules", e.majuscules ? "uppercase" : "none");
  posa("--sub-ombra", e.ombra ? "0 0.06em 0.2em rgba(0, 0, 0, 0.45)" : "none");
}

// Salta el que s'ha tret. Es crida a cada fotograma i també quan el vídeo avisa que
// ha avançat (per si el navegador alenteix el bucle de fotogrames).
function comprovaTall() {
  if (R.aturaA != null && R.reproduint && tempsMuntatge() >= R.aturaA) { atura(); }
  if (vista === "directe" && R.reproduint && trams.length) {
    const t = R.v.currentTime;
    const [a, b] = trams[Math.min(R.k, trams.length - 1)];
    if (t < a - 0.3 || t > b + 0.3) recolloca();
    else if (t >= b - 0.03) salta();
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
  R.v.addEventListener("loadedmetadata", () => { vesA(0); pintaTemps(); }, { once: true });

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
      <button class="mini" title="Esborra la nota" aria-label="Esborra la nota">${ICONES.esborra}</button>`;
    item.querySelector(".context").textContent = n.text;
    item.querySelector(".mini").addEventListener("click", (e) => {
      e.stopPropagation();
      notes = notes.filter((x) => x.id !== n.id);
      desaNotes();
    });
    item.addEventListener("click", () => {
      if (esborrany?.nom === n.versio) { canviaVista("esborrany"); vE.currentTime = n.temps; }
      else carregaVersio(n.versio, n.temps);
    });
    cont.append(item);
  }
}

async function desaNotes() {
  pintaNotes();
  try { notes = (await api("/api/notes", { notes })).notes; } catch (e) { avis("No s'ha pogut desar la nota: " + e.message); }
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
  notes.push({ id: Date.now(), versio: esborrany.nom, temps: arrodoneix(m), temps_original: original,
               text, creada: new Date().toISOString() });
  notes.sort((a, b) => (a.versio === b.versio ? a.temps - b.temps : a.id - b.id));
  desaNotes();
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
    const nom = feina.qualitat === "esborrany" ? "Construint l'esborrany" : `Exportant en ${QUALITATS[feina.qualitat]}`;
    if (feina.fase === "subtitols") {
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
      if (feina.qualitat === "esborrany") {
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

// --- Instruccions de veu -------------------------------------------------------------------

const TIPUS_INSTRUCCIO = {
  talla: ["Torna a començar", "En acceptar-la, es treu el primer intent."],
  zoom: ["Zoom", "En acceptar-la, el tros que ve s'apropa."],
  broll: ["B-roll / imatges", "Queda apuntada: el b-roll arriba a la fase 4."],
  sticker: ["Sticker", "Queda apuntada: els stickers arriben a la fase 4."],
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
      ins.estat === "acceptada" ? `Acceptada. ${ajuda.replace(/^En acceptar-la, /, "")}` : ins.estat === "descartada" ? "Descartada" : "";
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

function instalaControls() {
  for (const b of $$("#mode button")) {
    b.addEventListener("click", () => {
      mode = b.dataset.mode;
      for (const x of $$("#mode button")) x.setAttribute("aria-checked", String(x === b));
      document.body.classList.toggle("mode-corregeix", mode === "corregeix");
      $("#ajuda").innerHTML = mode === "talla"
        ? "Toca una paraula per treure-la o recuperar-la. Arrossega per triar-ne unes quantes. <kbd>⌥</kbd> + clic per escoltar des d'allà."
        : "Toca una paraula per corregir com s'escriu als subtítols. <kbd>↩</kbd> per desar, <kbd>esc</kbd> per deixar-ho.";
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

  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea")) return;
    if (!$("#full-final").hidden) { if (e.key === "Escape") tancaFinal(); return; }
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
  aplicaEstilSubtitols(P.estil_subtitols);
  $("#fitxer-estil").textContent = `Estil: ${(P.fitxer_estil || "").replace(/^\/Users\/[^/]+/, "~")}`;
  pintaNotes();
  pintaVersions(P.exports || []);
  pintaReels();
  pintaInstruccions();
  if (P.feina?.estat === "treballant") seguimentFeina(P.feina);
  consultaFeina.darrer = P.feina?.fitxer;
}

inicia();
