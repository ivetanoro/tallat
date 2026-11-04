// Obre la pàgina de tallat en un navegador de debò, la fa sonar i guarda què ha passat.
//   node pagina.mjs URL CARPETA_SORTIDA --motor chrome|firefox|webkit --exe CAMI --cpu 4 --escenari fred|calent|edita --segons 60
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync, createWriteStream } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { mkdtempSync } from "node:fs";

const aqui = dirname(fileURLToPath(import.meta.url));
const require = createRequire(process.env.PLAYWRIGHT_CORE ? process.env.PLAYWRIGHT_CORE + "/" : import.meta.url);
const pw = require(process.env.PLAYWRIGHT_CORE ? process.env.PLAYWRIGHT_CORE : "playwright-core");

const args = process.argv.slice(2);
const [url, sortida] = args;
const opcio = (n, d) => { const i = args.indexOf("--" + n); return i >= 0 ? args[i + 1] : d; };
const motor = opcio("motor", "chrome"), exe = opcio("exe"), cpu = Number(opcio("cpu", "1")), escenari = opcio("escenari", "calent");
const segons = Number(opcio("segons", "60")), senseCaptura = args.includes("--sense-captura"), espereContinu = Number(opcio("espera-continu", "180"));
const paraulaEdita = Number(opcio("paraula-edita", "-1"));

const dorm = (ms) => new Promise((r) => setTimeout(r, ms));
mkdirSync(sortida, { recursive: true });

const opcions = { headless: !args.includes("--amb-finestra") };
if (exe) opcions.executablePath = exe;
if (opcio("canal")) opcions.channel = opcio("canal");
if (motor === "chrome") {
  // --use-mock-keychain i --password-store=basic: que el Mac no demani la contrasenya del clauer.
  opcions.args = ["--use-mock-keychain", "--password-store=basic", "--autoplay-policy=no-user-gesture-required", "--no-first-run", "--no-default-browser-check"];
  opcions.ignoreDefaultArgs = ["--mute-audio"];
}
if (motor === "firefox") opcions.firefoxUserPrefs = { "media.autoplay.default": 0, "media.autoplay.blocking_policy": 0 };

const tipus = { chrome: pw.chromium, firefox: pw.firefox, webkit: pw.webkit }[motor];
const inici = Date.now();
const navegador = await tipus.launch(opcions);
const context = await navegador.newContext({ viewport: { width: 1440, height: 900 } });
const pagina = await context.newPage();
const consola = [];
pagina.on("console", (m) => { if (["error", "warning"].includes(m.type())) consola.push({ tipus: m.type(), text: m.text().slice(0, 300) }); });
pagina.on("pageerror", (e) => consola.push({ tipus: "pageerror", text: String(e).slice(0, 300) }));
pagina.on("response", (r) => { if (r.status() >= 400) consola.push({ tipus: "http" + r.status(), text: r.url().replace(url, "/").slice(0, 200) }); });
await pagina.addInitScript({ content: readFileSync(join(aqui, "sonda.js"), "utf8") });
if (motor === "chrome" && cpu > 1) {
  const cdp = await context.newCDPSession(pagina);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: cpu });
}

const resultat = { motor, cpu, escenari, versio: navegador.version(), url };
try {
  const abans = Date.now();
  await pagina.goto(url, { waitUntil: "load", timeout: 180000 });
  resultat.goto_ms = Date.now() - abans;
  await pagina.waitForFunction(() => window.__sonda?.marques?.text, null, { timeout: 180000, polling: 100 });
  // El que el vídeo pot reproduir, en aquest navegador
  resultat.pot = await pagina.evaluate(() => {
    const v = document.createElement("video");
    return { h264: v.canPlayType('video/mp4; codecs="avc1.640028"'), aac: v.canPlayType('audio/mp4; codecs="mp4a.40.2"') };
  });
  // Sense altaveus (com a GitHub), alguns navegadors no engeguen mai el so: que no es quedi aquí per sempre.
  if (!senseCaptura) resultat.estat_captura = await Promise.race([pagina.evaluate(() => window.__sonda.capta()).catch((e) => "error: " + e), dorm(30000).then(() => "no respon")]);

  if (escenari !== "fred") {  // la còpia contínua ja a punt
    const t0 = Date.now();
    await pagina.waitForFunction(() => window.__sonda.marques.continu, null, { timeout: espereContinu * 1000, polling: 200 }).catch(() => { resultat.continu_no_arriba = true; });
    resultat.espera_continu_ms = Date.now() - t0;
  }
  await dorm(300);
  await pagina.evaluate(() => window.__sonda.marca("a-punt-de-clicar"));
  await pagina.locator("#play").click({ timeout: 60000 });
  const fi = Date.now() + segons * 1000;
  let editat = false;
  while (Date.now() < fi) {
    await dorm(500);
    if (escenari === "edita" && !editat) {
      const m = await pagina.evaluate(() => { try { return tempsMuntatge(); } catch { return 0; } });
      if (m >= 6) {  // Sona: es treu una paraula de més endavant, sense aturar el vídeo. Es tria amb el teclat del text, com una persona.
        const id = await pagina.evaluate((preferida) => {
          const t = tempsMuntatge();
          const dins = P.paraules.filter((p) => !p.esborrada && muntatgeDe(p.inici) > t + 3 && p.final - p.inici > 0.25);
          const p = dins.find((x) => x.id >= preferida) || dins[0];
          return p ? p.id : null;
        }, paraulaEdita).catch((e) => { resultat.error_tria = String(e); return null; });
        if (id != null) {
          resultat.paraula_treta = id;
          await pagina.locator(`#transcripcio .p[data-id="${id}"]`).click({ timeout: 8000 }).catch((e) => { resultat.error_clic = String(e).slice(0, 200); });
          await dorm(250);
          await pagina.keyboard.press("Backspace");
          await pagina.evaluate((x) => window.__sonda.marca("treta", { id: x, audio: window.__sonda.ctx ? window.__sonda.ctx.currentTime : null, munt: tempsMuntatge() }), id);
        }
        editat = true;
      }
    }
    const acabat = await pagina.evaluate(() => { try { return !R.reproduint && !R.espera && window.__sonda.ev.some((e) => e.tipus === "clic") && Date.now() > 0 && tempsMuntatge() > duradaFinal - 0.4; } catch { return false; } });
    if (acabat) { resultat.ha_arribat_al_final = true; break; }
  }
  await pagina.evaluate(() => window.__sonda.marca("fi"));
  const r = await pagina.evaluate(() => window.__sonda.resum());
  Object.assign(resultat, r);
  if (!senseCaptura && r.nParts) {
    const f = createWriteStream(join(sortida, "so.f32"));
    for (let i = 0; i < r.nParts; i++) {
      const b64 = await pagina.evaluate((k) => window.__sonda.treu(k), i);
      if (b64) f.write(Buffer.from(b64, "base64"));
    }
    await new Promise((res) => f.end(res));
  }
} catch (e) {
  resultat.error = String(e).slice(0, 1000);
  try { Object.assign(resultat, await pagina.evaluate(() => window.__sonda.resum())); } catch {}
  try { await pagina.screenshot({ path: join(sortida, "error.png") }); } catch {}
}
resultat.consola = consola.slice(-40);
resultat.total_ms = Date.now() - inici;
writeFileSync(join(sortida, "dades.json"), JSON.stringify(resultat));
try { await pagina.screenshot({ path: join(sortida, "final.png") }); } catch {}
await navegador.close();
console.log(JSON.stringify({ motor, cpu, escenari, error: resultat.error, total_ms: resultat.total_ms }));
