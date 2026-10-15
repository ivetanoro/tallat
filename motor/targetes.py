"""On va el b-roll a la pantalla: sencer, en una targeta, en pantalla partida o en tres targetes.

La geometria es calcula aquí, en píxels d'un vídeo de 1080 × 1920, i la fan servir igual la vista
prèvia de la pàgina (pagina/app.js, que la rep del servidor) i l'export (motor/exporta.py).
L'animació d'entrada també és la mateixa a tots dos llocs: si en canvies una fórmula aquí,
canvia-la també a `animacioBroll()` de pagina/app.js.

  pantalla   tapa tota la imatge (tall sec), com sempre
  targeta    una targeta arrodonida, amb vora i ombra si en vols; la persona es veu al voltant
  partida    el b-roll a la meitat de dalt i la persona, a la de baix
  carrusel   b-rolls seguits (a menys d'un segon l'un de l'altre, fins a tres) entren d'un en un
             en targetes una al costat de l'altra, i s'hi queden fins que s'acaba l'últim
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

AMPLADA, ALCADA = 1080, 1920
ENTRADA = 0.4            # segons que dura l'animació d'entrada
GRUP_CARRUSEL = 1.0      # b-rolls a menys d'aquests segons l'un de l'altre van al mateix carrusel
MAXIM_CARRUSEL = 3
PROPORCIONS = {"9:16": 16 / 9, "3:4": 4 / 3, "4:5": 5 / 4, "1:1": 1.0, "16:9": 9 / 16}  # alçada / amplada
# L'ombra de les targetes (com un box-shadow: desplaçament avall, difuminat i opacitat).
OMBRA_Y, OMBRA_DIFUMINAT, OMBRA_OPACITAT = 14, 48, 0.45
CARRUSEL_AMPLADA = 0.36  # amplada de cada targeta del carrusel, en proporció a l'amplada del vídeo
CARRUSEL = {1: ([0.5], [0]), 2: ([0.32, 0.68], [-4, 4]), 3: ([0.19, 0.5, 0.81], [-6, 0, 6])}
SALT_POP = 1.70158       # quant «salta» l'animació pop (corba «back»)


def _caixa(x: float, y: float, w: float, h: float, radi=0.0, vora=0.0, color="#FFFFFF",
           ombra=False, rotacio=0.0) -> dict:
    radi = min(radi, w / 2, h / 2)  # com fa el navegador: mai més de mig costat curt
    return {"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2), "radi": round(radi, 2),
            "vora": round(vora, 2), "vora_color": color, "ombra": bool(ombra), "rotacio": rotacio}


def _grups(brolls: list[dict]) -> list[list[dict]]:
    """Els b-rolls seguits del carrusel, en grups de fins a tres."""
    grups: list[list[dict]] = []
    for b in sorted(brolls, key=lambda b: b["inici"]):
        if grups and len(grups[-1]) < MAXIM_CARRUSEL:
            anterior = grups[-1][-1]
            if b["inici"] - (anterior["inici"] + anterior["durada"]) <= GRUP_CARRUSEL:
                grups[-1].append(b)
                continue
        grups.append([b])
    return grups


def disposa(brolls: list[dict], estil: dict, accent: str = "#FFFFFF") -> list[dict]:
    """Afegeix a cada b-roll on va i com entra.

    Cada b-roll ({id, inici, durada, …}) torna amb:
      caixa      {x, y, w, h, radi, vora, vora_color, ombra, rotacio}: el rectangle de fora (vora
                 inclosa) abans de girar-lo, en píxels de 1080 × 1920; gira pel seu centre
      fins       quan desapareix (al carrusel, quan s'acaba l'últim del grup)
      animacio   pop, puja, llisca, fos o cap (i entrada: quants segons dura)
      direccio   d'on ve si llisca (-1 esquerra, 1 dreta)
      partida    si la persona baixa a la meitat de sota mentre surt
    L'ordre de la llista és l'ordre de les capes (el darrer, a sobre)."""
    disposicio = estil.get("disposicio", "pantalla")
    animacio = estil.get("animacio", "cap")
    color = estil.get("vora_color") or accent
    vora = float(estil.get("vora", 0)) * AMPLADA
    ombra = bool(estil.get("ombra", False))
    proporcio = PROPORCIONS.get(estil.get("proporcio", "4:5"), 1.25)

    def amb(b, caixa, fins=None, **altres):
        cx = caixa["x"] + caixa["w"] / 2
        return {**b, "caixa": caixa, "fins": round(fins if fins is not None else b["inici"] + b["durada"], 4),
                "animacio": animacio, "entrada": ENTRADA, "direccio": -1 if cx <= AMPLADA / 2 else 1,
                "partida": False, **altres}

    if disposicio == "carrusel":
        resultat = []
        w = CARRUSEL_AMPLADA * AMPLADA
        h = min(w * proporcio, 0.6 * ALCADA)
        cy = float(estil.get("posicio_y", 0.38)) * ALCADA
        for grup in _grups(brolls):
            xs, angles = CARRUSEL[len(grup)]
            fins = max(b["inici"] + b["durada"] for b in grup)
            for k, b in enumerate(grup):
                baixa = 0.012 * ALCADA if angles[k] else 0.0  # les de banda, una mica més avall
                caixa = _caixa(xs[k] * AMPLADA - w / 2, cy + baixa - h / 2, w, h,
                               float(estil.get("radi", 0.08)) * w, vora, color, ombra, angles[k])
                resultat.append(amb(b, caixa, fins))
        return resultat

    resultat = []
    for b in brolls:
        if disposicio == "targeta":
            w = float(estil.get("mida", 0.82)) * AMPLADA
            h = w * proporcio
            if h > 0.92 * ALCADA:  # massa alta: s'encongeix fins que hi cap
                h = 0.92 * ALCADA
                w = h / proporcio
            cx = min(AMPLADA - w / 2, max(w / 2, float(estil.get("posicio_x", 0.5)) * AMPLADA))
            cy = min(ALCADA - h / 2, max(h / 2, float(estil.get("posicio_y", 0.38)) * ALCADA))
            caixa = _caixa(cx - w / 2, cy - h / 2, w, h, float(estil.get("radi", 0.06)) * w, vora, color,
                           ombra, float(estil.get("rotacio", 0)))
            resultat.append(amb(b, caixa))
        elif disposicio == "partida":
            resultat.append(amb(b, _caixa(0, 0, AMPLADA, ALCADA / 2), partida=True))
        else:
            resultat.append(amb(b, _caixa(0, 0, AMPLADA, ALCADA)))
    return resultat


def mostra(estil: dict, accent: str = "#FFFFFF") -> list[dict]:
    """Com queda un estil, per dibuixar-ne una miniatura (al carrusel, un grup de tres)."""
    n = 3 if estil.get("disposicio") == "carrusel" else 1
    return [{k: b[k] for k in ("caixa", "partida")}
            for b in disposa([{"id": str(i), "inici": i * 1.6, "durada": 1.5} for i in range(n)], estil, accent)]


# --- L'animació d'entrada (la mateixa fórmula que pagina/app.js) -----------------------------------
# p va de 0 a 1 durant ENTRADA segons. Opacitat: lineal (com el «fade» d'ffmpeg).
#   pop     mida 0,8 → 1 amb un petit salt (corba «back»); opacitat en el primer 40 %
#   puja    puja 96 px (corba de sortida cúbica); opacitat lineal
#   llisca  ve 380 px de banda (cúbica); opacitat lineal
#   fos     només l'opacitat

def _p(t: str) -> str:
    return f"min(1,max(0,({t})/{ENTRADA}))"


def _cubica(t: str) -> str:
    return f"(1-pow(1-{_p(t)},3))"


def _salt(t: str) -> str:
    q = f"({_p(t)}-1)"
    return f"(1+{SALT_POP + 1}*pow({q},3)+{SALT_POP}*pow({q},2))"


# --- Les peces per a l'export -------------------------------------------------------------------

def _parell(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def _arrodonit(cx: float, cy: float, mw: float, mh: float, r: float) -> str:
    """Expressió de geq: 1 dins d'un rectangle arrodonit (amb les vores suavitzades), 0 fora."""
    r = max(r, 1.0)
    e = (f"clip({r:.3f}+0.5-hypot(max(0,abs(X+0.5-{cx:.3f})-{mw / 2 - r:.3f}),"
         f"max(0,abs(Y+0.5-{cy:.3f})-{mh / 2 - r:.3f})),0,1)")
    return e.replace(",", "\\,")


def mides(caixa: dict, factor: float) -> dict:
    """Les mides de la targeta en píxels del vídeo que s'exporta (factor = amplada / 1080)."""
    w, h = _parell(caixa["w"] * factor), _parell(caixa["h"] * factor)
    vora = int(round(caixa["vora"] * factor)) if caixa["vora"] else 0
    vora = min(vora, w // 4, h // 4)
    marge = int(math.ceil((OMBRA_DIFUMINAT * 1.5 + OMBRA_Y) * factor)) if caixa["ombra"] else 0
    return {"w": w, "h": h, "vora": vora, "dins_w": w - 2 * vora, "dins_h": h - 2 * vora,
            "radi": caixa["radi"] * factor, "radi_dins": max(0.0, caixa["radi"] - caixa["vora"]) * factor,
            "marge": marge}


def cal_marc(caixa: dict) -> bool:
    return bool(caixa["vora"] or caixa["ombra"])


def fes_mascara(m: dict, desti: Path) -> Path:
    """La forma arrodonida del vídeo de dins (gris: blanc es veu, negre no)."""
    w, h = m["dins_w"], m["dins_h"]
    expr = _arrodonit(w / 2, h / 2, w, h, m["radi_dins"])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={w}x{h}:d=1",
                    "-vf", f"format=gray,geq=lum='255*{expr}'", "-frames:v", "1", str(desti)],
                   check=True, capture_output=True)
    return desti


def fes_marc(m: dict, caixa: dict, factor: float, desti: Path) -> Path:
    """L'ombra i la vora de la targeta (amb transparència), on després es posa el vídeo."""
    fw, fh = m["w"] + 2 * m["marge"], m["h"] + 2 * m["marge"]
    cx, cy = fw / 2, fh / 2
    parts = [f"color=c=black@0:s={fw}x{fh}:d=1,format=rgba[fons]"]
    actual = "fons"
    if caixa["ombra"]:
        ombra = _arrodonit(cx, cy + OMBRA_Y * factor, m["w"], m["h"], m["radi"])
        sigma = OMBRA_DIFUMINAT * factor / 2  # el difuminat d'un box-shadow és el doble de la sigma
        parts += [f"color=black:s={fw}x{fh}:d=1,format=gray,geq=lum='255*{OMBRA_OPACITAT}*{ombra}',"
                  f"gblur=sigma={sigma:.2f}[oa]",
                  f"color=black:s={fw}x{fh}:d=1,format=rgba[ob]", "[ob][oa]alphamerge[om]",
                  f"[{actual}][om]overlay=0:0:format=auto[a1]"]
        actual = "a1"
    if m["vora"]:
        placa = _arrodonit(cx, cy, m["w"], m["h"], m["radi"])
        parts += [f"color=black:s={fw}x{fh}:d=1,format=gray,geq=lum='255*{placa}'[pa]",
                  f"color=c=0x{caixa['vora_color'].lstrip('#')}:s={fw}x{fh}:d=1,format=rgba[pc]",
                  "[pc][pa]alphamerge[pl]", f"[{actual}][pl]overlay=0:0:format=auto[a2]"]
        actual = "a2"
    parts.append(f"[{actual}]format=rgba[sortida]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-filter_complex", ";".join(parts), "-map", "[sortida]",
                    "-frames:v", "1", str(desti)], check=True, capture_output=True)
    return desti


def prepara_peces(brolls: list[dict], factor: float, carpeta: Path) -> list[dict]:
    """Fa les imatges de la forma i del marc de cada targeta (les iguals, un sol cop).
    Torna, per a cada b-roll, {"mascara": Path | None, "marc": Path | None}."""
    fetes: dict[tuple, Path] = {}
    peces = []
    for i, b in enumerate(brolls):
        caixa = b["caixa"]
        m = mides(caixa, factor)
        mascara = marc = None
        if m["radi_dins"] >= 1:
            clau = ("m", m["dins_w"], m["dins_h"], round(m["radi_dins"], 1))
            if clau not in fetes:
                fetes[clau] = fes_mascara(m, carpeta / f"mascara-{len(fetes)}.png")
            mascara = fetes[clau]
        if cal_marc(caixa):
            clau = ("c", m["w"], m["h"], round(m["radi"], 1), m["vora"], caixa["vora_color"], caixa["ombra"])
            if clau not in fetes:
                fetes[clau] = fes_marc(m, caixa, factor, carpeta / f"marc-{len(fetes)}.png")
            marc = fetes[clau]
        peces.append({"mascara": mascara, "marc": marc})
    return peces


def filtre(brolls: list[dict], peces: list[dict], entrada_broll: int, entrada_peces: dict,
           actual: str, mida: tuple[int, int]) -> tuple[list[str], str]:
    """Les línies del filtre d'ffmpeg que posen els b-rolls (ja disposats) damunt de `actual`.

    `entrada_broll`: l'índex de l'entrada del primer b-roll (un per b-roll, en ordre).
    `entrada_peces`: {(k, "mascara"|"marc"): índex de l'entrada} de les imatges fixes.
    Torna (línies, nom de la sortida)."""
    ow, oh = mida
    factor = ow / AMPLADA
    parts = []
    partides = [b for b in brolls if b["partida"]]
    if partides:
        # Pantalla partida: mentre surt, la franja del mig de la persona baixa a la meitat de sota
        # i la de dalt queda negra (el b-roll hi entra a sobre).
        quan = "+".join(f"between(t,{b['inici']:.4f},{b['fins']:.4f})" for b in partides)
        parts += [f"[{actual}]split[pp0][pp1];",
                  f"[pp1]crop={ow}:{oh // 2}:0:{oh // 4}[pmig];",
                  f"[pp0][pmig]overlay=0:{oh // 2}:enable='{quan}',"
                  f"drawbox=x=0:y=0:w={ow}:h={oh // 2}:color=black:t=fill:enable='{quan}'[pbase];"]
        actual = "pbase"
    for k, b in enumerate(brolls):
        caixa, m, peca = b["caixa"], mides(b["caixa"], factor), peces[k]
        visible = b["fins"] - b["inici"]
        # Si el clip s'acaba abans (al carrusel, o un vídeo més curt que la durada), es queda quiet a
        # l'últim fotograma fins que la targeta se'n va: com a la vista prèvia.
        cadena = (f"[{entrada_broll + k}:v]setpts=PTS-STARTPTS,"
                  f"scale={m['dins_w']}:{m['dins_h']}:force_original_aspect_ratio=increase:flags=lanczos,"
                  f"crop={m['dins_w']}:{m['dins_h']},setsar=1,"
                  f"tpad=stop_mode=clone:stop_duration={visible:.4f},trim=duration={visible:.4f},"
                  f"format=yuva444p[bc{k}];")
        parts.append(cadena)
        ara = f"bc{k}"
        if peca["mascara"]:
            parts.append(f"[{entrada_peces[(k, 'mascara')]}:v]format=gray[bm{k}];[{ara}][bm{k}]alphamerge[ba{k}];")
            ara = f"ba{k}"
        if peca["marc"]:
            desp = m["marge"] + m["vora"]
            parts.append(f"[{entrada_peces[(k, 'marc')]}:v]format=yuva444p[bf{k}];"
                         f"[bf{k}][{ara}]overlay={desp}:{desp}:format=auto:shortest=1[bk{k}];")
            ara = f"bk{k}"
        efectes = []
        if caixa["rotacio"]:
            a = f"{caixa['rotacio']}*PI/180"
            efectes.append(f"rotate={a}:c=none:ow=rotw({a}):oh=roth({a})")
        if b["animacio"] == "pop":
            amplada = m["w"] + 2 * m["marge"]
            if caixa["rotacio"]:
                rad = math.radians(abs(caixa["rotacio"]))
                amplada = (m["w"] + 2 * m["marge"]) * math.cos(rad) + (m["h"] + 2 * m["marge"]) * math.sin(rad)
            efectes.append(f"scale=w='trunc({amplada:.2f}*(0.8+0.2*{_salt('t')})/2)*2':h=-2:eval=frame")
            efectes.append(f"fade=t=in:st=0:d={ENTRADA * 0.4:.3f}:alpha=1")
        elif b["animacio"] in ("puja", "llisca", "fos"):
            efectes.append(f"fade=t=in:st=0:d={ENTRADA}:alpha=1")
        efectes.append(f"setpts=PTS+{b['inici']:.4f}/TB")
        parts.append(f"[{ara}]{','.join(efectes)}[bt{k}];")
        cx = (caixa["x"] + caixa["w"] / 2) * factor
        cy = (caixa["y"] + caixa["h"] / 2) * factor
        t = f"t-{b['inici']:.4f}"
        x, y = f"{cx:.2f}-overlay_w/2", f"{cy:.2f}-overlay_h/2"
        if b["animacio"] == "puja":
            y += f"+{96 * factor:.2f}*(1-{_cubica(t)})"
        elif b["animacio"] == "llisca":
            x += f"+{380 * factor * b['direccio']:.2f}*(1-{_cubica(t)})"
        parts.append(f"[{actual}][bt{k}]overlay=x='{x}':y='{y}':eval=frame:eof_action=pass:"
                     f"enable='between(t,{b['inici']:.4f},{b['fins']:.4f})'[bv{k}];")
        actual = f"bv{k}"
    return parts, actual
