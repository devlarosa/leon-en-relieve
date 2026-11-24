#!/usr/bin/env python3
"""Edificios en 3D a partir del Catastro (Dirección General del Catastro, servicio INSPIRE de edificios).

Para cada municipio de la lista «edificios» de la ficha de la zona (web/zonas.json), descarga el paquete INSPIRE
(huellas de las partes de cada edificio con su número de plantas sobre rasante; uso y año de construcción del
edificio) y lo convierte en un binario compacto que el visor extruye: web/data/<zona>/edificios/<código>.bin

Formato (little endian):
  cabecera  "EDF1", uint32 n.º de partes, float32 x0, float32 y0 (origen en metros del visor: x desde el oeste
            de la zona, y desde el norte), float32 paso (m por unidad de las coordenadas)
  por parte uint8 plantas, uint8 uso, uint16 año (0 = desconocido), uint8 n.º de anillos,
            por anillo: uint16 n.º de vértices y n × (uint16 x, uint16 y)   (el primero, exterior; el resto, patios)
Usos: 0 desconocido, 1 residencial, 2 agrario, 3 industrial, 4 oficinas, 5 comercio, 6 servicios públicos.

Uso: ZONA=leon python3 scripts/edificios.py [código_catastro ...]
"""
import io, json, os, re, struct, sys, urllib.parse, urllib.request, zipfile
sys.path.insert(0, os.path.dirname(__file__))
from zona import ZONA, FICHA, RAW, DATA

ATOM = "https://www.catastro.hacienda.gob.es/INSPIRE/buildings/{p}/ES.SDGC.bu.atom_{p}.xml"
USOS = {"1_residential": 1, "2_agriculture": 2, "3_industrial": 3, "4_1_office": 4, "4_2_retail": 5, "4_3_publicServices": 6}
X0, Y1 = FICHA["extension"][0], FICHA["extension"][3]
PASO = 0.5          # m por unidad: rango de 32 km con uint16, de sobra para un municipio
TOL = 0.35          # simplificación (Douglas-Peucker), m
MIN_AREA = 6.0      # m²: se descartan casetas diminutas

def descargar(cod):
    dest = os.path.join(RAW, "edificios", cod + ".zip")
    if os.path.exists(dest): return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    feed = urllib.request.urlopen(ATOM.format(p=cod[:2]), timeout=60).read().decode("utf-8", "replace")
    m = re.search(r'href="([^"]*/%s-[^"]*\.zip)"' % cod, feed)
    if not m: raise SystemExit("El Catastro no publica el municipio " + cod)
    url = urllib.parse.quote(m.group(1), safe=":/")
    print("descargando", m.group(1))
    datos = urllib.request.urlopen(url, timeout=600).read()
    with open(dest + ".tmp", "wb") as f: f.write(datos)
    os.replace(dest + ".tmp", dest)
    return dest

def dp(pts, tol):
    """Douglas-Peucker sobre un anillo abierto (lista de (x, y))."""
    if len(pts) < 4: return pts
    P = pts + [pts[0]]
    def rec(a, b):
        (x1, y1), (x2, y2) = P[a], P[b]
        dx, dy = x2 - x1, y2 - y1; L = (dx * dx + dy * dy) ** 0.5 or 1e-9
        imax, dmax = -1, tol
        for i in range(a + 1, b):
            d = abs((P[i][0] - x1) * dy - (P[i][1] - y1) * dx) / L
            if d > dmax: imax, dmax = i, d
        return rec(a, imax)[:-1] + rec(imax, b) if imax >= 0 else [P[a], P[b]]
    # se parte por el vértice más lejano al primero para no perder esquinas
    far = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
    return rec(0, far)[:-1] + rec(far, len(P) - 1)[:-1] if far > 0 else pts

def area(r):
    return abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2

RE_FEAT = re.compile(r"<bu-ext2d:(Building|BuildingPart) gml:id=\"ES\.SDGC\.BU\.([^\"]+)\">(.*?)</bu-ext2d:\1>", re.S)
RE_RING = re.compile(r"<gml:(exterior|interior)>.*?<gml:posList[^>]*>([^<]+)</gml:posList>", re.S)

def convertir(cod):
    z = zipfile.ZipFile(descargar(cod))
    nombre = lambda suf: next(n for n in z.namelist() if n.endswith(suf))
    edif = {}
    for m in RE_FEAT.finditer(z.read(nombre(".building.gml")).decode("utf-8")):
        if m.group(1) != "Building": continue
        t = m.group(3)
        uso = re.search(r"<bu-ext2d:currentUse>([^<]+)<", t)
        anio = re.search(r"<bu-core2d:beginning>(\d{4})", t)
        edif[m.group(2)] = (USOS.get(uso.group(1), 0) if uso else 0, int(anio.group(1)) if anio else 0)
    partes = []
    for m in RE_FEAT.finditer(z.read(nombre(".buildingpart.gml")).decode("utf-8")):
        t = m.group(3)
        pl = re.search(r"<bu-ext2d:numberOfFloorsAboveGround>(\d+)<", t)
        pl = int(pl.group(1)) if pl else 0
        if pl <= 0: continue                     # solo bajo rasante (sótanos, garajes) o sin dato
        anillos = []
        for k, (tipo, txt) in enumerate(RE_RING.findall(t)):
            v = list(map(float, txt.split()))
            r = [(v[i] - X0, Y1 - v[i + 1]) for i in range(0, len(v) - 2, 2)]   # sin el punto de cierre
            r = dp(r, TOL)
            if len(r) >= 3 and area(r) >= (MIN_AREA if tipo == "exterior" else 2.0): anillos.append((tipo, r))
        if not anillos or anillos[0][0] != "exterior": continue
        uso, anio = edif.get(m.group(2).split("_part")[0], (0, 0))
        partes.append((min(pl, 255), uso, anio, [r for _, r in anillos]))
    if not partes: raise SystemExit("sin edificios en " + cod)
    xs = [p[0] for q in partes for r in q[3] for p in r]; ys = [p[1] for q in partes for r in q[3] for p in r]
    ox, oy = min(xs), min(ys)
    if (max(xs) - ox) / PASO > 65535 or (max(ys) - oy) / PASO > 65535: raise SystemExit("municipio demasiado grande para uint16")
    b = io.BytesIO()
    b.write(b"EDF1"); b.write(struct.pack("<Ifff", len(partes), ox, oy, PASO))
    for pl, uso, anio, rings in partes:
        b.write(struct.pack("<BBHB", pl, uso, anio, len(rings)))
        for r in rings:
            b.write(struct.pack("<H", len(r)))
            b.write(struct.pack("<%dH" % (2 * len(r)), *[round((c - o) / PASO) for p in r for c, o in ((p[0], ox), (p[1], oy))]))
    os.makedirs(os.path.join(DATA, "edificios"), exist_ok=True)
    out = os.path.join(DATA, "edificios", cod + ".bin")
    with open(out, "wb") as f: f.write(b.getvalue())
    print(f"{cod}: {len(partes)} partes de edificio, {len(edif)} edificios, {b.tell() / 1e6:.2f} MB -> {out}")

if __name__ == "__main__":
    cods = sys.argv[1:] or list((FICHA.get("edificios") or {}).get("municipios", {}))
    if not cods: raise SystemExit(f"La ficha de {ZONA} no tiene «edificios.municipios»")
    for c in cods: convertir(c)
