/* nucli · la peça de votar de les rondes, la mateixa a tallat, personalitza i matcha.
 *
 * Tres vots, amb les mateixes paraules a tot arreu: Sí · Potser · No. Internament: "si", "potser", "no".
 * Cada eina pot desar-los amb els seus noms d'abans (personalitza: guarda/potser/fora; matcha:
 * aprovada/canvi/treta): li passa `interns` i la peça tradueix en les dues direccions.
 *
 *   const c = Rondes.control({ valor: "guarda", interns: Rondes.INTERNS.personalitza,
 *                              onTria: (intern) => desa(intern), desactivat: false });
 *   c.posa("fora");                      // quan el valor canvia per una altra banda
 *   Rondes.teclaVot(event)               // 1/2/3 → "si"/"potser"/"no" (o null)
 *
 * Sense dependències ni xarxa: també funciona dins d'un artifact de claude.ai (s'hi enganxa sencer).
 * L'estil és a rondes.css; els colors es poden canviar amb --rondes-si, --rondes-potser i --rondes-no.
 */
(function (arrel) {
  "use strict";
  const VOTS = ["si", "potser", "no"];
  const ETIQUETES = { si: "Sí", potser: "Potser", no: "No" };
  const INTERNS = {
    comu: { si: "si", potser: "potser", no: "no" },
    tallat: { si: "si", potser: "potser", no: "no" },
    personalitza: { si: "guarda", potser: "potser", no: "fora" },
    matcha: { si: "aprovada", potser: "canvi", no: "treta" },
  };

  /** El vot comú d'un valor de qualsevol eina ("guarda" → "si", "treta" → "no"…), o null. */
  function vot(valor) {
    if (VOTS.includes(valor)) return valor;
    for (const mapa of Object.values(INTERNS)) {
      const trobat = VOTS.find((v) => mapa[v] === valor);
      if (trobat) return trobat;
    }
    return null;
  }

  function teclaVot(e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return null;
    return { 1: "si", 2: "potser", 3: "no" }[e.key] || null;
  }

  function control({ valor = null, interns = INTERNS.comu, onTria = () => {}, desactivat = false,
                     etiqueta = "Valoració", permetBuit = true } = {}) {
    const caixa = document.createElement("div");
    caixa.className = "rondes-vot";
    caixa.setAttribute("role", "radiogroup");
    caixa.setAttribute("aria-label", etiqueta);
    const indicador = document.createElement("span");
    indicador.className = "rondes-indicador";
    indicador.setAttribute("aria-hidden", "true");
    caixa.append(indicador);
    const botons = {};
    for (const v of VOTS) {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.vot = v;
      b.textContent = ETIQUETES[v];
      b.setAttribute("role", "radio");
      b.disabled = desactivat;
      b.addEventListener("click", () => {
        const actual = vot(caixa.dataset.intern || null);
        const nou = actual === v && permetBuit ? null : v;
        posa(nou ? interns[nou] : null);
        onTria(nou ? interns[nou] : null, nou);
      });
      b.addEventListener("keydown", (e) => {  // fletxes dins del grup, com un radiogroup de debò
        const i = VOTS.indexOf(v);
        const salt = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
        if (!salt) return;
        e.preventDefault();
        e.stopPropagation();  // la pàgina pot fer servir les fletxes per a una altra cosa (passar d'opció)
        botons[VOTS[(i + salt + VOTS.length) % VOTS.length]].focus();
      });
      botons[v] = b;
      caixa.append(b);
    }
    function posa(intern) {
      const v = vot(intern);
      if (v) { caixa.dataset.vot = v; caixa.dataset.intern = intern; }
      else { delete caixa.dataset.vot; delete caixa.dataset.intern; }
      for (const w of VOTS) {
        botons[w].setAttribute("aria-checked", String(w === v));
        botons[w].tabIndex = (v ? w === v : w === "si") ? 0 : -1;
      }
    }
    function desactiva(si) { for (const w of VOTS) botons[w].disabled = Boolean(si); }
    posa(valor);
    caixa.posa = posa;
    caixa.desactiva = desactiva;
    return caixa;
  }

  arrel.Rondes = { VOTS, ETIQUETES, INTERNS, vot, teclaVot, control };
})(typeof window !== "undefined" ? window : globalThis);
