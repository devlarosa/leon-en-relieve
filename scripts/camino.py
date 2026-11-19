#!/usr/bin/env python3
"""Caminos de Santiago por la provincia, del IGN (Caminos de Santiago en Europa, nco.ign.es).

- Etapas de cada camino (nombre, longitud oficial) con su trazado
- Albergues (tipo, plazas, precio, servicios)
Para cada etapa se calcula el perfil de altitud con el MDT del visor (relieve.png, 100 m) y el desnivel acumulado.
Salida: web/data/camino.json. Descargas en raw/camino/ (se puede relanzar).
"""
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from zona import ZONA  # noqa: E402  (variable de entorno ZONA; por defecto «leon»)
sys.path.insert(0, str(RAIZ / "scripts"))
from rios_red import simplificar  # noqa: E402
from lugares import dentro  # noqa: E402

RAW = RAIZ / "raw" / ZONA / "camino"
UA = "Mozilla/5.0 (compatible; leon3d-datos/1.0)"
BASE = "https://nco.ign.es/server/rest/services/ccsseu"
COLORES = {"Camino Francés": "#c0392b", "Camino de El Salvador": "#2471a3", "Vía de la Plata de Zamora a Astorga": "#b9770e",
           "Camino Mozárabe - Vía de la Plata": "#ca6f1e", "Camino de Invierno": "#117a65", "Camino Olvidado": "#7d3c98",
           "Ruta Vadiniense": "#1f618d", "Camino de las Asturias": "#2e86c1", "Camino de Madrid": "#a04000",
           "Camino Primitivo": "#5b2c6f", "Camino del Sureste": "#935116"}


def descargar(nombre, servicio):
    f = RAW / f"{nombre}.json"
    if f.exists() and json.loads(f.read_text()).get("features"):
        return json.loads(f.read_text())
    RAW.mkdir(parents=True, exist_ok=True)
    q = {"geometry": "164000,4655000,360000,4790000", "geometryType": "esriGeometryEnvelope", "inSR": 25830, "outSR": 25830,
         "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "true", "f": "json"}
    with urllib.request.urlopen(urllib.request.Request(f"{BASE}/{servicio}/query?" + urllib.parse.urlencode(q), headers={"User-Agent": UA}), timeout=300) as r:
        d = json.loads(r.read().decode("utf-8"))
    if "error" in d or d.get("exceededTransferLimit"):
        raise SystemExit(f"{servicio}: {d.get('error') or 'demasiados elementos'}")
    f.write_text(json.dumps(d, ensure_ascii=False))
    return d


def campo(a, sufijo):
    return next((v for k, v in a.items() if k.endswith(sufijo)), None)


def main():
    L = json.loads((RAIZ / "web" / "data" / ZONA / "zona.json").read_text()); M = L["meta"]
    px = np.asarray(Image.open(RAIZ / "web" / "data" / ZONA / "relieve.png").convert("RGB"), dtype=np.float64)
    H = (px[..., 0] * 65536 + px[..., 1] * 256 + px[..., 2]) / 10 - 10000
    R, W = H.shape

    def altura(x, y):
        fx = min(max(x / M["celda"] - 0.5, 0), W - 1.001); fy = min(max(y / M["celda"] - 0.5, 0), R - 1.001)
        x0, y0 = int(fx), int(fy); tx, ty = fx - x0, fy - y0
        return (H[y0, x0] * (1 - tx) + H[y0, x0 + 1] * tx) * (1 - ty) + (H[y0 + 1, x0] * (1 - tx) + H[y0 + 1, x0 + 1] * tx) * ty

    etapas_raw = descargar("etapas", "CaminoSantiagoEuropa/MapServer/0")["features"]
    alb_raw = descargar("albergues", "CaminoSantiagoEuropa_alojamiento/MapServer/0")["features"]
    caminos, etapas = {}, []
    for f in etapas_raw:
        a = f["attributes"]; cam = (campo(a, "cst_camino.nombre") or "").strip()
        rings = f["geometry"].get("paths", [])
        partes = [[(x - M["x0"], M["y1"] - y) for x, y in p[:]] for p in rings]
        pts = [q for p in partes for q in p]
        if not pts or not any(dentro(x, y, L["provincia"]) for x, y in pts[::3]):
            continue                  # solo las etapas que pisan la provincia
        # perfil: cada 100 m a lo largo de la etapa
        perfil, dist, sube, baja = [], 0.0, 0.0, 0.0
        for p in partes:
            for (x0, y0), (x1, y1) in zip(p, p[1:]):
                seg = math.hypot(x1 - x0, y1 - y0); n = max(1, int(seg // 100))
                for k in range(n):
                    t = k / n; perfil.append(altura(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
                dist += seg
        perfil = [round(v) for v in perfil[::max(1, len(perfil) // 300)]]   # como mucho ~300 puntos
        # desnivel acumulado con umbral de 5 m (descarta el ruido del MDT en los llanos)
        ref = perfil[0] if perfil else 0
        for v in perfil[1:]:
            if v - ref >= 5: sube += v - ref; ref = v
            elif ref - v >= 5: baja += ref - v; ref = v
        nombre = (campo(a, "CST.nombre") or "").strip()
        geo = [[round(v) for q in simplificar(p, 12.0) for v in q] for p in partes]
        caminos.setdefault(cam, {"n": cam, "color": COLORES.get(cam, "#7b241c"), "km": 0, "etapas": []})
        etapas.append({"n": nombre, "c": cam, "km": round(campo(a, "CST.longitud") or dist / 1000, 1), "kmm": round(dist / 1000, 1),
                       "variante": nombre.lower().startswith("variante"), "id": campo(a, "CST.id_etapa"),
                       "sube": round(sube), "baja": round(baja), "zmin": min(perfil), "zmax": max(perfil), "perfil": perfil, "g": geo})
    # orden de marcha: se encadenan las etapas de cada camino (cada una empieza donde acaba otra); las variantes, al final
    def extremos(e):
        g = [p for p in e["g"] if len(p) >= 4]
        return (g[0][0], g[0][1]), (g[-1][-2], g[-1][-1])
    ordenadas = []
    for cam in sorted({e["c"] for e in etapas}):
        principales = [e for e in etapas if e["c"] == cam and not e["variante"]]
        resto = list(principales); cadena = []
        while resto:
            # empieza por la etapa cuyo inicio no es el final de ninguna otra
            cab = next((e for e in resto if not any(math.dist(extremos(e)[0], extremos(o)[1]) < 1500 for o in resto if o is not e)), resto[0])
            cadena.append(cab); resto.remove(cab)
            while True:
                fin = extremos(cadena[-1])[1]
                sig = min(resto, key=lambda o: math.dist(fin, extremos(o)[0]), default=None)
                if not sig or math.dist(fin, extremos(sig)[0]) > 3000:
                    break
                cadena.append(sig); resto.remove(sig)
        ordenadas += cadena + [e for e in etapas if e["c"] == cam and e["variante"]]
    etapas = ordenadas
    for i, e in enumerate(etapas):
        c = caminos[e["c"]]; c["etapas"].append(i)
        if not e["variante"]:
            c["km"] = round(c["km"] + e["km"], 1)
    albergues = []
    for f in alb_raw:
        a = f["attributes"]; g = f.get("geometry") or {}
        if "x" not in g:
            continue
        x, y = g["x"] - M["x0"], M["y1"] - g["y"]
        if not dentro(x, y, L["provincia"]):
            continue
        serv = [s for s, k in (("cocina", "cocina"), ("wifi", "wifi"), ("lavadora", "lavadora"), ("calefacción", "calef"), ("bicis", "bicis"),
                                ("animales", "animales"), ("comedor", "comedor"), ("reserva", "reserva")) if a.get(k)]
        albergues.append({"n": (a.get("albergue") or "").strip(), "t": (a.get("tipo") or "").strip(), "p": (a.get("poblacion") or "").strip(),
                          "c": (a.get("denocamino") or "").strip(), "pl": int(a["plazas"]) if a.get("plazas") else None,
                          "eur": a.get("pvpnoche"), "don": bool(a.get("donativo")), "ges": (a.get("gestion") or "").strip(), "s": serv,
                          "anual": bool(a.get("anual")), "xy": [round(x), round(y)]})
    out = {"fuente": "IGN, Caminos de Santiago en Europa (etapas y albergues, nco.ign.es); perfiles calculados con el MDT del IGN",
           "caminos": sorted(caminos.values(), key=lambda c: -c["km"]), "etapas": etapas, "albergues": albergues}
    (RAIZ / "web" / "data" / ZONA / "camino.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(out['caminos'])} caminos, {len(etapas)} etapas, {len(albergues)} albergues en la provincia;",
          round((RAIZ / "web" / "data" / ZONA / "camino.json").stat().st_size / 1e6, 2), "MB")
    for c in out["caminos"]:
        print(f"  {c['n']:40} {c['km']:6} km (etapas en la provincia) · {len(c['etapas'])} tramos")
    fr = [e for e in etapas if e["c"] == "Camino Francés" and not e["variante"]]
    for e in fr[:12]:
        print(f"    {e['n']:48} {e['km']:5} km  +{e['sube']} m / -{e['baja']} m  ({e['zmin']}–{e['zmax']} m)")


if __name__ == "__main__":
    main()
