"""Ensenya els resultats d'un o més JSON de cami.py en poques línies."""
import json, sys
for f in sys.argv[1:]:
    r = json.load(open(f, encoding="utf-8"))
    print(f"\n=== {r['video']}  {r['durada']:.0f} s, {r['talls']} talls, muntatge {r['durada_muntatge']} s")
    print(" pàgina 1a vegada:", r.get("pagina_primera_vegada"), "| 2a:", r.get("pagina_segona_vegada"))
    print(" referència (original):", r.get("referencia_original"))
    for p in r["passos"]:
        print("  pas:", p["ordre"][:48], f"{p['segons']} s", f"{p.get('memoria_mb','?')} MB", "OK" if p["ok"] else "ERROR " + p.get("error", "")[-300:])
    fitxers = dict(r.get("exports", {}))
    if "copia_continua" in r:
        fitxers["còpia contínua"] = r["copia_continua"]
    for q, e in fitxers.items():
        if "imatge" not in e:
            print(" ", q, e); continue
        i, s, c = e["imatge"], e["so"], e["sincronisme"]
        print(f" {q}: {e['mida']} {e['fps']}  v={e['durada_video']:.3f} a={e['durada_so']:.3f} munt={e['durada_muntatge']:.3f}")
        print(f"   imatge: vora max {i['error_vora_max_ms']} ms, mediana {i['error_vora_mediana_ms']}, qualsevol max {i['error_tots_max_ms']}, >1 foto {i['trams_amb_error_de_mes_d_un_fotograma']}, fora muntatge {i['fora_del_muntatge']}, salts {i['salts_dins_d_un_tram']}, sense codi {i['sense_codi']}, fotos {i['fotogrames']}")
        print(f"   so: {s['talls_mesurats']} vores, mediana {s['error_mediana_ms']} ms, p95 {s['error_p95_ms']}, max {s['error_max_ms']}, mitjana {s['error_mitjana_amb_signe_ms']}, sense coincid {s['sense_coincidencia']}, corr {s['corr_mediana']}, retallades {s['n_retallades']}/{s['paraules_de_vora_mirades']}, fuita {s['fuita_max_db']} dB, trets {len(s['trets_que_sonen'])}/{s['trets_buscats']} (pic {s['pic_max_trets']}), control {s['control_conservats_min']}")
        print(f"   sincro: {c.get('flaixos')} flaixos, principi {c.get('al_principi_ms')} ms, final {c.get('al_final_ms')} ms, max {c.get('max_abs_ms')}")
    print(" premiere:", {k: v for k, v in r.get("premiere", {}).items() if k != "url"}, "fcp:", r.get("fcpxml"))
    print(" capcut:", r.get("trossos_capcut"))
