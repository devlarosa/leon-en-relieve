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

FEEDS = {}
def feed(prov):
    if prov not in FEEDS:   # el feed viene en Latin-1 (CABAÑAS RARAS)
        FEEDS[prov] = urllib.request.urlopen(ATOM.format(p=prov), timeout=60).read().decode("latin-1")
    return FEEDS[prov]

def todos(prov):
    """Todos los municipios que publica el Catastro en la provincia: {código: nombre}."""
    return dict(re.findall(r'<title>\s*(%s\d{3})-([^<]+?) buildings</title>' % prov, feed(prov)))

def descargar(cod):
    dest = os.path.join(RAW, "edificios", cod + ".zip")
    if os.path.exists(dest): return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    m = re.search(r'href="([^"]*/%s-[^"]*\.zip)"' % cod, feed(cod[:2]))
    if not m: raise SystemExit("El Catastro no publica el municipio " + cod)
    url = urllib.parse.quote(m.group(1), safe=":/")
    print("descargando", m.group(1))
    datos = urllib.request.urlopen(url, timeout=600).read()
    with open(dest + ".tmp", "wb") as f: f.write(datos)
    os.replace(dest + ".tmp", dest)
    return dest

# El Catastro publica cada municipio en su huso UTM: los del oeste de León (el Bierzo, Astorga…) vienen en el 29
# (EPSG:25829) y el mapa está en el 30 (EPSG:25830). Paso de huso por latitud y longitud (GRS80, series de Krüger
# truncadas: error muy por debajo del metro a menos de 5° del meridiano central).
_A, _F, _K0 = 6378137.0, 1 / 298.257222101, 0.9996
_E2 = _F * (2 - _F); _EP2 = _E2 / (1 - _E2)
def _tm_inv(E, N, lon0):
    import math
    e2 = _E2; x = E - 500000; m = N / _K0
    mu = m / (_A * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    C1 = _EP2 * math.cos(p1) ** 2; T1 = math.tan(p1) ** 2; N1 = _A / math.sqrt(1 - e2 * math.sin(p1) ** 2)
    R1 = _A * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5; D = x / (N1 * _K0)
    lat = p1 - (N1 * math.tan(p1) / R1) * (D ** 2 / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * _EP2) * D ** 4 / 24
                                           + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * _EP2 - 3 * C1 ** 2) * D ** 6 / 720)
    lon = lon0 + (D - (1 + 2 * T1 + C1) * D ** 3 / 6 + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * _EP2 + 24 * T1 ** 2) * D ** 5 / 120) / math.cos(p1)
    return lat, lon
def _tm_fwd(lat, lon, lon0):
    import math
    e2 = _E2; N = _A / math.sqrt(1 - e2 * math.sin(lat) ** 2); T = math.tan(lat) ** 2; C = _EP2 * math.cos(lat) ** 2
    A = math.cos(lat) * (lon - lon0)
    M = _A * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * lat - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * lat)
              + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * lat) - (35 * e2 ** 3 / 3072) * math.sin(6 * lat))
    E = 500000 + _K0 * N * (A + (1 - T + C) * A ** 3 / 6 + (5 - 18 * T + T ** 2 + 72 * C - 58 * _EP2) * A ** 5 / 120)
    Nn = _K0 * (M + N * math.tan(lat) * (A ** 2 / 2 + (5 - T + 9 * C + 4 * C ** 2) * A ** 4 / 24 + (61 - 58 * T + T ** 2 + 600 * C - 330 * _EP2) * A ** 6 / 720))
    return E, Nn
def huso29a30(E, N):
    import math
    lat, lon = _tm_inv(E, N, math.radians(-9))
    return _tm_fwd(lat, lon, math.radians(-3))

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
RE_SRS = re.compile(r'srsName="urn:ogc:def:crs:EPSG::(\d+)"')
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
    gml = z.read(nombre(".buildingpart.gml")).decode("utf-8")
    srs = RE_SRS.search(gml).group(1)
    if srs not in ("25829", "25830"): raise SystemExit(f"{cod}: sistema de referencia no previsto (EPSG:{srs})")
    for m in RE_FEAT.finditer(gml):
        t = m.group(3)
        pl = re.search(r"<bu-ext2d:numberOfFloorsAboveGround>(\d+)<", t)
        pl = int(pl.group(1)) if pl else 0
        if pl <= 0: continue                     # solo bajo rasante (sótanos, garajes) o sin dato
        anillos = []
        for k, (tipo, txt) in enumerate(RE_RING.findall(t)):
            v = list(map(float, txt.split()))
            xy = [(v[i], v[i + 1]) for i in range(0, len(v) - 2, 2)]           # sin el punto de cierre
            if srs == "25829": xy = [huso29a30(x, y) for x, y in xy]
            r = [(x - X0, Y1 - y) for x, y in xy]
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
    return {"c": cod, "partes": len(partes), "bb": [round(ox), round(oy), round(max(xs)), round(max(ys))], "kb": round(b.tell() / 1024)}

if __name__ == "__main__":
    fe = FICHA.get("edificios") or {}
    nombres = dict(fe.get("municipios", {}))
    if fe.get("todos"):   # toda la zona: los municipios que publica el Catastro en sus provincias
        from zona import PROVINCIAS
        for prov in PROVINCIAS:
            for c, n in todos(prov).items(): nombres.setdefault(c, n.title())
    cods = sys.argv[1:] or sorted(nombres)
    if not cods: raise SystemExit(f"La ficha de {ZONA} no tiene «edificios»")
    ruta = os.path.join(DATA, "edificios", "indice.json")
    indice = {}
    if os.path.exists(ruta): indice = {m["c"]: m for m in json.load(open(ruta))["municipios"]}
    for c in cods:
        try: m = convertir(c)
        except (SystemExit, Exception) as e: print("  ", c, "omitido:", e); continue
        m["n"] = nombres.get(c, c); indice[c] = m
    # índice para el visor: la caja de cada municipio (metros del visor) para cargarlo solo al acercarse
    indice = {c: m for c, m in indice.items() if c in nombres or not nombres}
    with open(ruta, "w") as f:
        json.dump({"fuente": "Dirección General del Catastro · INSPIRE Buildings", "municipios": sorted(indice.values(), key=lambda m: m["c"])}, f, ensure_ascii=False)
    print(len(indice), "municipios en", ruta)
