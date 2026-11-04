// Sonda que s'injecta a la pàgina de tallat per mesurar-la: no en canvia res, només hi escolta.
// Apunta què fan els dos vídeos i, quan se li demana, enregistra el que surt de debò pels altaveus.
(() => {
  if (window.__sonda) return;
  const S = (window.__sonda = { ev: [], ticks: [], parts: [], primerFrame: null, marques: {} });
  const ara = () => performance.now();
  S.marca = (tipus, d = {}) => S.ev.push({ t: +ara().toFixed(1), tipus, ...d });
  try { localStorage.setItem("tallat.guia-vista", "99"); } catch {}  // sense la visita guiada

  window.addEventListener("error", (e) => S.marca("error-js", { msg: String(e.message).slice(0, 200) }));
  window.addEventListener("unhandledrejection", (e) => S.marca("promesa-rebutjada", { msg: String(e.reason).slice(0, 200) }));

  const EVENTS = ["loadstart", "loadedmetadata", "loadeddata", "canplay", "canplaythrough", "play", "playing", "pause", "waiting", "stalled",
    "seeking", "seeked", "ended", "error", "emptied"];
  const enganxats = new WeakSet();
  function enganxa(v) {
    if (enganxats.has(v)) return;
    enganxats.add(v);
    for (const n of EVENTS) {
      v.addEventListener(n, () => S.marca("v:" + n, { id: v.id, ct: +v.currentTime.toFixed(3), rs: v.readyState, vol: +v.volume.toFixed(2), muted: v.muted }));
    }
  }
  const estatVideo = (v) => v && [+v.currentTime.toFixed(3), v.paused ? 1 : 0, v.seeking ? 1 : 0, v.readyState, +v.volume.toFixed(2), v.muted ? 1 : 0];
  function tick() {
    const a = document.getElementById("video-a"), m = document.getElementById("video-m");
    if (a) enganxa(a);
    if (m) enganxa(m);
    if (a && !S.marques.video && a.readyState >= 2) S.marques.video = ara();
    if (!S.marques.text && document.querySelector("#transcripcio .p")) S.marques.text = ara();
    let munt = null, sonant = null, aPunt = null;
    try { munt = +tempsMuntatge().toFixed(3); sonant = R.reproduint; aPunt = previaAPunt(); } catch {}
    if (aPunt && !S.marques.continu) S.marques.continu = ara();
    const preparant = document.getElementById("preparant"), carregant = document.getElementById("carregant");
    S.ticks.push([+ara().toFixed(1), munt, sonant ? 1 : 0, estatVideo(a), estatVideo(m), preparant && !preparant.hidden ? 1 : 0, carregant && !carregant.hidden ? 1 : 0]);
    if (S.ticks.length > 60000) S.ticks.shift();
  }
  setInterval(tick, 40);

  // Els fotogrames que no es dibuixen a temps
  let darrer = ara();
  const mira = () => {
    const t = ara();
    if (t - darrer > 250) S.marca("fil-ocupat", { ms: Math.round(t - darrer) });
    darrer = t;
    requestAnimationFrame(mira);
  };
  requestAnimationFrame(mira);

  document.addEventListener("click", (e) => {
    S.marca("clic", { id: e.target?.closest?.("button")?.id || e.target?.id || "", audio: S.ctx ? S.ctx.currentTime : null });
  }, true);

  const CODI = `class Enregistra extends AudioWorkletProcessor {
    constructor() { super(); this.b = new Float32Array(9600); this.n = 0; this.primer = null; }
    process(entrades, sortides) {
      if (this.primer === null) { this.primer = currentFrame; this.port.postMessage({ primer: currentFrame }); }
      const x = entrades[0] && entrades[0][0];
      const q = x ? x.length : 128;
      for (let i = 0; i < q; i++) {
        this.b[this.n++] = x ? x[i] : 0;
        if (this.n === this.b.length) { this.port.postMessage(this.b.slice(0)); this.n = 0; }
      }
      const s = sortides[0];
      if (x) for (const c of s) c.set(x);
      return true;
    }
  }
  registerProcessor("enregistra", Enregistra);`;

  S.capta = async () => {
    const ctx = (S.ctx = new AudioContext({ sampleRate: 48000 }));
    await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([CODI], { type: "text/javascript" })));
    const node = new AudioWorkletNode(ctx, "enregistra", { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1, channelCountMode: "explicit", channelInterpretation: "speakers" });
    node.port.onmessage = (e) => {
      if (e.data.primer !== undefined) S.primerFrame = e.data.primer;
      else S.parts.push(e.data);
    };
    for (const id of ["video-a", "video-m"]) ctx.createMediaElementSource(document.getElementById(id)).connect(node);
    node.connect(ctx.destination);
    await ctx.resume();
    S.mostreig = ctx.sampleRate;
    return ctx.state;
  };

  // El so enregistrat, a trossos (en base64), perquè no passi tot de cop pel canal de control
  S.treu = (i) => {
    const p = S.parts[i];
    if (!p) return null;
    const bytes = new Uint8Array(p.buffer);
    let text = "";
    for (let k = 0; k < bytes.length; k += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(k, k + 0x8000));
    return btoa(text);
  };

  S.resum = () => {
    const pinta = performance.getEntriesByType("paint").find((p) => p.name === "first-contentful-paint");
    const nav = performance.getEntriesByType("navigation")[0];
    const q = (id) => { const v = document.getElementById(id); return v?.getVideoPlaybackQuality ? (({ totalVideoFrames, droppedVideoFrames }) => ({ totalVideoFrames, droppedVideoFrames }))(v.getVideoPlaybackQuality()) : null; };
    let t = null, durada = null;
    try { t = trams; durada = duradaFinal; } catch {}
    const recursos = performance.getEntriesByType("resource").map((r) => ({ nom: r.name.replace(location.origin, "").slice(0, 70), inici: Math.round(r.startTime), ms: Math.round(r.duration), kb: Math.round((r.transferSize || 0) / 1024), tipus: r.initiatorType }))
      .sort((a, b) => (b.inici + b.ms) - (a.inici + a.ms)).slice(0, 14);
    return { recursos, fcp: pinta?.startTime ?? null, dom: nav?.domContentLoadedEventEnd ?? null, load: nav?.loadEventEnd ?? null, marques: S.marques, ev: S.ev, ticks: S.ticks,
      primerFrame: S.primerFrame, mostreig: S.mostreig ?? null, nParts: S.parts.length, qualitat: { a: q("video-a"), m: q("video-m") }, trams: t, duradaFinal: durada,
      memoriaJS: performance.memory ? performance.memory.usedJSHeapSize : null, paraules: document.querySelectorAll("#transcripcio .p").length };
  };
})();
