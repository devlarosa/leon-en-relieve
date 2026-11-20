#!/usr/bin/env python3
"""Rutas de montaña, refugios y majadas de una zona (ZONA=picos) -> web/data/<zona>/camino.json

Usa el mismo formato que los Caminos de Santiago (scripts/camino.py), así la pestaña del Camino del visor
sirve también para las rutas («Rutas» en la ficha de la zona). Todo de fuentes oficiales del IGN:
  - red de transporte de la OGC API de la IDEE (roadlink): carreteras, pistas y sendas, sin nombres
  - cables (cablewaylink): teleféricos y funiculares
  - Nomenclátor Geográfico Básico: edificaciones con nombre (refugios, majadas) y los puntos de las rutas
Cada ruta de «rutas» en web/zonas.json va de un punto con nombre del Nomenclátor a otro (con paradas
opcionales) por el camino más corto de la red, prefiriendo sendas y pistas a carreteras. Su perfil se calcula
con el relieve del visor y el desnivel acumulado con un umbral de 5 m, como en camino.py.
Descargas en raw/<zona>/rutas/ (se reutilizan si ya están).
"""
import heapq
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from zona import ZONA, FICHA  # noqa: E402

RAW = RAIZ / "raw" / ZONA / "rutas"
WEB = RAIZ / "web" / "data" / ZONA
UA = {"User-Agent": "Mozilla/5.0 (compatible; leon3d-datos/1.0)"}
API = "https://api-features.idee.es/collections"
NGBE = "https://www.ign.es/wfs-inspire/ngbe"


def get(url, intentos=6):
    for i in range(intentos):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            print("  reintento", i, str(e)[:80], flush=True); time.sleep(4 * (i + 1))
    raise SystemExit("no se pudo descargar " + url[:120])


def ogc(coleccion, nombre, n=6):
    """Descarga por teselas (la paginación de la IDEE repite y salta elementos): se juntan y se quitan repetidos."""
    f = RAW / nombre
    if f.exists():
        return json.loads(f.read_text())
    la0, lo0, la1, lo1 = FICHA["bbox"]
    vistos, feats = set(), []
    for i in range(n):
        for j in range(n):
            x0, x1 = lo0 + (lo1 - lo0) * i / n, lo0 + (lo1 - lo0) * (i + 1) / n
            y0, y1 = la0 + (la1 - la0) * j / n, la0 + (la1 - la0) * (j + 1) / n
            url = f"{API}/{coleccion}/items?" + urllib.parse.urlencode({"f": "json", "limit": 1000, "bbox": f"{x0:.5f},{y0:.5f},{x1:.5f},{y1:.5f}"})
            while url:
                d = json.loads(get(url))
                for ft in d["features"]:
                    k = ft.get("id") or json.dumps(ft["geometry"])[:200]
                    if k not in vistos:
                        vistos.add(k); feats.append(ft)
                url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
            print(f"  {coleccion}: tesela {i * n + j + 1}/{n * n}, {len(feats)} elementos", flush=True)
    RAW.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(feats))
    return feats


def ngbe(tipo):
    """Lugares con nombre del Nomenclátor de un tipo (localType), en la caja de la zona: [(nombre, lon, lat)]."""
    f = RAW / f"ngbe_{tipo.replace(' ', '_').replace('/', '-')}.json"
    if f.exists():
        return json.loads(f.read_text())
    la0, lo0, la1, lo1 = FICHA["bbox"]
    filtro = (f'<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" xmlns:gn="http://inspire.ec.europa.eu/schemas/gn/4.0" '
              f'xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gml="http://www.opengis.net/gml/3.2"><fes:And><fes:BBOX>'
              f'<fes:ValueReference>gn:geometry</fes:ValueReference><gml:Envelope srsName="urn:ogc:def:crs:EPSG::4258">'
              f'<gml:lowerCorner>{la0} {lo0}</gml:lowerCorner><gml:upperCorner>{la1} {lo1}</gml:upperCorner></gml:Envelope></fes:BBOX>'
              f'<fes:PropertyIsEqualTo><fes:ValueReference>gn:localType/gmd:LocalisedCharacterString</fes:ValueReference>'
              f'<fes:Literal>{tipo}</fes:Literal></fes:PropertyIsEqualTo></fes:And></fes:Filter>')
    url = NGBE + "?" + urllib.parse.urlencode({"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": "gn:NamedPlace",
                                              "count": 20000, "filter": filtro})
    t = get(url).decode("utf-8")
    if not t.rstrip().endswith("FeatureCollection>"):
        raise SystemExit(f"Respuesta incompleta del Nomenclátor ({tipo})")
    out = []
    for m in t.split("<wfs:member>")[1:]:
        nm = re.findall(r"<gn:text>([^<]*)", m); pos = re.search(r"<gml:pos>([-\d.]+) ([-\d.]+)</gml:pos>", m)
        if nm and pos:
            out.append([" / ".join(dict.fromkeys(nm)), float(pos.group(2)), float(pos.group(1))])
    RAW.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, ensure_ascii=False))
    return out


# ---------------------------------------------------------------- proyección (ETRS89 geográficas -> UTM 30N)
def utm30(lon, lat):
    a, f = 6378137.0, 1 / 298.257222101; e2 = f * (2 - f); ep2 = e2 / (1 - e2); k0 = 0.9996
    lam0 = math.radians(-3); phi, lam = math.radians(lat), math.radians(lon)
    N = a / math.sqrt(1 - e2 * math.sin(phi) ** 2); T = math.tan(phi) ** 2; C = ep2 * math.cos(phi) ** 2; A = math.cos(phi) * (lam - lam0)
    e4, e6 = e2 * e2, e2 ** 3
    Mm = a * ((1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
              + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi) - (35 * e6 / 3072) * math.sin(6 * phi))
    x = k0 * N * (A + (1 - T + C) * A ** 3 / 6 + (5 - 18 * T + T * T + 72 * C - 58 * ep2) * A ** 5 / 120) + 500000
    y = k0 * (Mm + N * math.tan(phi) * (A * A / 2 + (5 - T + 9 * C + 4 * C * C) * A ** 4 / 24 + (61 - 58 * T + T * T + 600 * C - 330 * ep2) * A ** 6 / 720))
    return x, y


def norm(s):
    s = unicodedata.normalize("NFD", s.lower()); s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def main():
    M = json.loads((WEB / "zona.json").read_text())["meta"]
    x0, y1, celda = M["x0"], M["y1"], M["celda"]
    loc = lambda lon, lat: (lambda x, y: (x - x0, y1 - y))(*utm30(lon, lat))
    px = np.asarray(Image.open(WEB / "relieve.png").convert("RGB"), dtype=np.float64)
    H = (px[..., 0] * 65536 + px[..., 1] * 256 + px[..., 2]) / 10 - 10000; R, W = H.shape

    def altura(x, y):
        fx = min(max(x / celda - 0.5, 0), W - 1.001); fy = min(max(y / celda - 0.5, 0), R - 1.001)
        i, j = int(fx), int(fy); tx, ty = fx - i, fy - j
        return (H[j, i] * (1 - tx) + H[j, i + 1] * tx) * (1 - ty) + (H[j + 1, i] * (1 - tx) + H[j + 1, i + 1] * tx) * ty

    print("Red de transporte del IGN (carreteras, pistas y sendas)")
    red = ogc("roadlink", "roadlink.json")
    print("Cables (teleféricos y funiculares)")
    cables = ogc("cablewaylink", "cablewaylink.json", n=2)
    print("Nomenclátor: edificaciones, núcleos, montañas, pasos y aguas")
    lugares = {t: ngbe(t) for t in ["Edificación", "Entidad singular", "Núcleos de población", "Montaña", "Paso de montaña", "Masa de agua",
                                    "Construcción/instalación abierta", "Paraje", "Elemento puntual del paisaje"]}

    # ---- grafo de la red: nudos = extremos de los tramos (redondeados a 2 m)
    PESO = {None: 1.0, "ninthClass": 1.25, "fourthClass": 1.4, "thirdClass": 1.8, "secondClass": 2.5, "firstClass": 3.5, "mainRoad": 4.0}
    nudo, coords, ady = {}, [], []
    def id_nudo(p):
        k = (round(p[0] / 2), round(p[1] / 2))
        if k not in nudo:
            nudo[k] = len(coords); coords.append(p); ady.append([])
        return nudo[k]
    tramos = []
    for ft in red:
        g = ft["geometry"]; pr = ft["properties"]
        partes = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for parte in partes:
            pts = [loc(*c[:2]) for c in parte]
            if len(pts) < 2:
                continue
            L = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
            a, b = id_nudo(pts[0]), id_nudo(pts[-1])
            w = L * PESO.get(pr.get("functionalclass"), 1.5) * (1.0 if pr.get("surfacecategory", "").endswith("unpaved") else 1.15)
            t = len(tramos); tramos.append(pts)
            ady[a].append((b, w, t, False)); ady[b].append((a, w, t, True))
    print(f"  {len(tramos)} tramos, {len(coords)} nudos")
    XY = np.array(coords)

    todos = [(n, *loc(lo, la)) for lst in lugares.values() for n, lo, la in lst]
    def punto(ref):
        if isinstance(ref, list):              # [lon, lat]
            return loc(*ref), f"{ref}"
        q = norm(ref)
        cand = [c for c in todos if q in [norm(a) for a in c[0].split(" / ")]] or [c for c in todos if q in norm(c[0])]
        if not cand:
            raise SystemExit(f"No encuentro «{ref}» en el Nomenclátor: pon otro nombre o [lon, lat] en web/zonas.json")
        c = cand[0]
        return (c[1], c[2]), c[0]

    def dijkstra(s, t):
        dist = {s: 0.0}; prev = {}; pq = [(0.0, s)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == t:
                break
            if d > dist.get(u, 1e18):
                continue
            for v, w, ti, rev in ady[u]:
                nd = d + w
                if nd < dist.get(v, 1e18):
                    dist[v] = nd; prev[v] = (u, ti, rev); heapq.heappush(pq, (nd, v))
        if t not in prev and s != t:
            return None
        seq, u = [], t
        while u != s:
            p, ti, _ = prev[u]; seq.append((p, ti)); u = p
        camino = []
        for p, ti in reversed(seq):              # cada tramo, orientado para que empiece donde acabó el anterior
            seg = tramos[ti]
            if math.dist(seg[0], coords[p]) > math.dist(seg[-1], coords[p]):
                seg = seg[::-1]
            camino += seg if not camino else seg[1:]
        return camino

    def cercano(p):
        d = np.hypot(XY[:, 0] - p[0], XY[:, 1] - p[1]); k = int(d.argmin()); return k, float(d[k])

    def perfil_de(pts):
        perfil, dist = [], 0.0
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            seg = math.hypot(bx - ax, by - ay); n = max(1, int(seg // 50))
            for k in range(n):
                t = k / n; perfil.append(altura(ax + (bx - ax) * t, ay + (by - ay) * t))
            dist += seg
        perfil.append(altura(*pts[-1]))
        perfil = [round(v) for v in perfil[::max(1, len(perfil) // 300)]]
        sube = baja = 0.0; ref = perfil[0]
        for v in perfil[1:]:
            if v - ref >= 5: sube += v - ref; ref = v
            elif ref - v >= 5: baja += ref - v; ref = v
        return perfil, dist, sube, baja

    def simplificar(pts, tol):
        if len(pts) < 3:
            return pts
        a, b = np.array(pts[0]), np.array(pts[-1]); ab = b - a; L = np.hypot(*ab) or 1
        d = [abs(ab[0] * (p[1] - a[1]) - ab[1] * (p[0] - a[0])) / L for p in pts[1:-1]]
        i = int(np.argmax(d)) + 1
        return simplificar(pts[:i + 1], tol)[:-1] + simplificar(pts[i:], tol) if d[i - 1] > tol else [pts[0], pts[-1]]

    conf = FICHA.get("rutas", {})
    caminos, etapas, descartadas = [], [], []
    grupo = {"n": conf.get("grupo", "Rutas clásicas"), "color": conf.get("color", "#b5541b"), "km": 0, "etapas": []}
    for r in conf.get("lista", []):
        refs = [r["desde"]] + r.get("por", []) + [r["hasta"]]
        pts_ref = [punto(x) for x in refs]
        trazado = []
        for (pa, na), (pb, nb) in zip(pts_ref, pts_ref[1:]):
            (sa, da), (sb, db) = cercano(pa), cercano(pb)
            if max(da, db) > 400:
                print(f"  OJO {r['n']}: «{na if da > 400 else nb}» queda a {max(da, db):.0f} m de la red")
            c = dijkstra(sa, sb)
            if not c:
                raise SystemExit(f"No hay camino en la red entre «{na}» y «{nb}» ({r['n']})")
            trazado += c if not trazado else c[1:]
        perfil, dist, sube, baja = perfil_de(trazado)
        recta = sum(math.dist(a[0], b[0]) for a, b in zip(pts_ref, pts_ref[1:]))
        if dist > 3.0 * max(recta, 500):      # las sendas de alta montaña zigzaguean: hasta 3 veces la línea recta
            # la red del IGN no tiene la senda de esta ruta (solo carreteras y pistas): saldría un rodeo; mejor no dibujarla
            print(f"  FUERA {r['n']}: {dist / 1000:.1f} km por la red frente a {recta / 1000:.1f} km en línea recta (falta la senda en los datos)")
            descartadas.append(r["n"]); continue
        g = [[round(v) for q in simplificar(trazado, 6.0) for v in q]]
        grupo["etapas"].append(len(etapas))
        etapas.append({"n": r["n"], "c": grupo["n"], "km": round(dist / 1000, 1), "kmm": round(dist / 1000, 1), "variante": False, "id": len(etapas),
                       "sube": round(sube), "baja": round(baja), "zmin": min(perfil), "zmax": max(perfil), "perfil": perfil, "g": g,
                       "desc": r.get("desc"), "desde": pts_ref[0][1], "hasta": pts_ref[-1][1]})
        grupo["km"] = round(grupo["km"] + dist / 1000, 1)
        print(f"  {r['n']:52} {dist / 1000:5.1f} km  +{sube:.0f} / -{baja:.0f} m  ({min(perfil)}–{max(perfil)} m)")
    if grupo["etapas"]:
        caminos.append(grupo)
    # cables: teleféricos y funiculares, como otra «ruta»
    gc = {"n": "Teleféricos y funiculares", "color": "#2c3e50", "km": 0, "etapas": []}
    for ft in cables:
        g = ft["geometry"]; partes = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        pts = [loc(*c[:2]) for p in partes for c in p]
        if len(pts) < 2 or not all(0 <= x <= M["ancho"] and 0 <= y <= M["alto"] for x, y in pts):
            continue
        nombre = (ft["properties"].get("nombre") or "Cable").strip()
        nombre = ("Teleférico " + nombre if nombre.startswith("de ") else nombre).replace("Fuente De", "Fuente Dé")
        perfil, dist, sube, baja = perfil_de(pts)
        gc["etapas"].append(len(etapas)); gc["km"] = round(gc["km"] + dist / 1000, 1)
        etapas.append({"n": nombre, "c": gc["n"], "km": round(dist / 1000, 1), "kmm": round(dist / 1000, 1), "variante": True, "id": len(etapas),
                       "sube": round(sube), "baja": round(baja), "zmin": min(perfil), "zmax": max(perfil), "perfil": perfil,
                       "g": [[round(v) for q in pts for v in q]]})
        print(f"  {nombre:52} {dist / 1000:5.1f} km  ({min(perfil)}–{max(perfil)} m)")
    if gc["etapas"]:
        caminos.append(gc)

    # refugios y majadas (edificaciones con nombre del Nomenclátor)
    albergues = []
    for n, lo, la in lugares["Edificación"]:
        x, y = loc(lo, la)
        if not (0 <= x <= M["ancho"] and 0 <= y <= M["alto"]):
            continue
        tipo = "Refugio de montaña" if norm(n).startswith("refugio") else "Majada" if re.match(r"(majada|mayada|mayáu|mayau)\b", norm(n)) else None
        if tipo:
            albergues.append({"n": n.split(" / ")[0], "t": tipo, "p": "", "c": "", "pl": None, "eur": None, "don": False, "ges": "", "s": [],
                              "anual": False, "xy": [round(x), round(y)], "e": round(altura(x, y))})
    out = {"fuente": "IGN: red de transporte (carreteras, pistas y sendas) y cables de la OGC API de la IDEE; refugios, majadas y puntos "
                     "de las rutas del Nomenclátor Geográfico Básico. Trazados por el camino más corto de la red; perfiles con el MDT25",
           "caminos": caminos, "etapas": etapas, "albergues": albergues, "sinTrazado": descartadas}
    (WEB / "camino.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(etapas)} trazados, {sum(a['t'].startswith('Refugio') for a in albergues)} refugios y "
          f"{sum(a['t'] == 'Majada' for a in albergues)} majadas -> {WEB / 'camino.json'} ({(WEB / 'camino.json').stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
