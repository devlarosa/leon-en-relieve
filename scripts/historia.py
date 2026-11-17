#!/usr/bin/env python3
"""Mapa histórico: reúne y sitúa los datos de las cuatro épocas (castros, Roma, Reino de León, minería del carbón).

Entradas
  recursos/historia.json                sitios escogidos, épocas, pueblos prerromanos y pueblos del Camino
  raw/historia/itinere_roads.geojson     calzadas romanas, Itiner-e 2024 (Zenodo 10.5281/zenodo.17122148, CC BY 4.0)
  raw/historia/wikidata.json             castros, yacimientos, castillos, monasterios… de Wikidata (consulta SPARQL)
  IGME-CSIC (BDMIN, se descarga aquí)    indicios de oro y de carbón; inventario de escombreras de 1989
Salida: web/data/historia.json
"""
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from lugares import Contexto, situar, norm, dentro  # noqa: E402
from rios_red import simplificar  # noqa: E402

RAW = RAIZ / "raw" / "historia"
UA = "Mozilla/5.0 (compatible; leon3d-datos/1.0)"
IGME = "https://mapas.igme.es/gis/rest/services/BasesDatos"
QUERY_WD = """SELECT ?item ?itemLabel ?itemDescription ?tipoLabel ?c ?inicio ?fin ?art WHERE {
  SERVICE wikibase:box { ?item wdt:P625 ?c . bd:serviceParam wikibase:cornerSouthWest "Point(-7.15 41.95)"^^geo:wktLiteral .
    bd:serviceParam wikibase:cornerNorthEast "Point(-4.65 43.30)"^^geo:wktLiteral . }
  ?item wdt:P31 ?tipo . ?tipo rdfs:label ?tl . FILTER(LANG(?tl) = "es")
  FILTER(REGEX(?tl, "castro|yacimiento|arqueol|romana|romano|campamento|dolmen|megal|monasterio|castillo|torre fortificada|muralla|mina|calzada|necrópolis|abadía|ciudad romana|Zona Arqueológica|villa romana", "i"))
  OPTIONAL { ?item wdt:P571 ?inicio . } OPTIONAL { ?item wdt:P576 ?fin . }
  OPTIONAL { ?art schema:about ?item ; schema:isPartOf <https://es.wikipedia.org/> . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". } }"""


def get_json(url, data=None, intentos=6, pausa=5):
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": "application/sparql-results+json, application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"  reintento {i + 1}: {e}", flush=True); time.sleep(pausa * (i + 1) if "429" not in str(e) else 70)
    raise SystemExit("No se pudo descargar " + url)


def descargar():
    RAW.mkdir(parents=True, exist_ok=True)
    f = RAW / "itinere_roads.geojson"
    if not f.exists():
        print("Calzadas romanas (Itiner-e)…")
        urllib.request.urlretrieve("https://zenodo.org/api/records/17122148/files/itinere_roads.geojson/content", f)
    f = RAW / "wikidata.json"
    if not f.exists() or not f.read_text()[:1] == "{":
        print("Wikidata…")
        d = get_json("https://query.wikidata.org/sparql", data=urllib.parse.urlencode({"query": QUERY_WD}).encode())
        f.write_text(json.dumps(d, ensure_ascii=False))
    # IGME: el servicio no admite filtros ni paginación; se pide por teselas (como mucho 1000 por consulta) y se filtra aquí
    for nombre, servicio, campos, quiero in (
            ("igme_oro", "IGME_BDMIN_Indicios", "ESRI_OID,Nombre_mina,Sustancia,Municipio,Morfologia", r"\boro\b"),
            ("igme_carbon", "IGME_BDMIN_Indicios", "ESRI_OID,Nombre_mina,Sustancia,Municipio,Morfologia", r"hulla|antracita"),
            ("igme_escombreras", "IGME_InventarioEscombreras", "ESRI_OID,NOMBRE,PARAJE,Sustancia,NOMBRE_MUN,VOLU", r"hulla|antracita")):
        f = RAW / f"{nombre}.json"
        if f.exists() and json.loads(f.read_text()):
            continue
        print("IGME", nombre, "…", flush=True)
        vistos, feats, pend = set(), [], [(x, y, x + 40000, y + 45000) for x in range(164000, 360000, 40000) for y in range(4655000, 4790000, 45000)]
        while pend:
            x0, y0, x1, y1 = pend.pop()
            q = {"geometry": f"{x0},{y0},{x1},{y1}", "geometryType": "esriGeometryEnvelope", "inSR": 25830, "outSR": 25830,
                 "spatialRel": "esriSpatialRelIntersects", "outFields": campos, "returnGeometry": "true", "f": "json"}
            d = get_json(f"{IGME}/{servicio}/MapServer/0/query?" + urllib.parse.urlencode(q))
            if "error" in d:
                raise SystemExit(f"IGME {servicio}: {d['error']}")
            if d.get("exceededTransferLimit"):
                xm, ym = (x0 + x1) // 2, (y0 + y1) // 2
                pend += [(x0, y0, xm, ym), (xm, y0, x1, ym), (x0, ym, xm, y1), (xm, ym, x1, y1)]
                continue
            for ft in d.get("features", []):
                k = ft["attributes"].get("ESRI_OID")
                if k not in vistos and re.search(quiero, (ft["attributes"].get("Sustancia") or "").lower()):
                    vistos.add(k); feats.append(ft)
        f.write_text(json.dumps(feats, ensure_ascii=False))


def main():
    descargar()
    H = json.loads((RAIZ / "recursos" / "historia.json").read_text(encoding="utf-8"))
    cx = Contexto(); M = cx.M; L = cx.L; avisos = []
    prov = L["provincia"]
    en_prov = lambda x, y: dentro(x, y, prov)
    pueblo = lambda n: next((xy for p, c, xy in cx.pueblos if norm(p) == norm(n)), None)

    # sitios escogidos
    sitios = []
    for s in H["sitios"]:
        r = situar(s, cx, avisos)
        if not r:
            continue
        (x, y), fuente, como, qid = r
        sitios.append({k: s[k] for k in ("n", "era", "ini", "fin", "fecha", "desc", "mun") if k in s} |
                      {"xy": [round(x), round(y)], "pos": fuente, "aprox": bool(s.get("aprox"))})
        print(f"  {fuente:8} {s['n']:40} ← {como}")
    cx.guardar()
    pueblos = []
    for p in H["pueblos"]:
        xy = pueblo(p["cerca"])
        if xy:
            pueblos.append({"n": p["n"], "era": p["era"], "xy": [xy[0] + p["dx"], xy[1] + p["dy"]]})
    camino = [pueblo(n) for n in H["camino"]["por"]]
    if None in camino:
        avisos.append("Camino: no se encuentran " + ", ".join(n for n, xy in zip(H["camino"]["por"], camino) if xy is None))
    camino = [xy for xy in camino if xy]

    # calzadas romanas de Itiner-e (Mercator elipsoidal EPSG:3395 → UTM 30 local)
    a, e = 6378137.0, 0.0818191908426
    def m3395(x, y):
        t = math.exp(-y / a); phi = math.pi / 2 - 2 * math.atan(t)
        for _ in range(8):
            phi = math.pi / 2 - 2 * math.atan(t * ((1 - e * math.sin(phi)) / (1 + e * math.sin(phi))) ** (e / 2))
        return math.degrees(phi), math.degrees(x / a)
    calzadas = []
    for f in json.load(open(RAW / "itinere_roads.geojson"))["features"]:
        g = f["geometry"]
        if not g:
            continue
        partes = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for parte in partes:
            pts = [cx.local(*m3395(c[0], c[1])) for c in parte]
            if not any(-3000 <= x <= M["ancho"] + 3000 and -3000 <= y <= M["alto"] + 3000 for x, y in pts):
                continue
            pts = simplificar(pts, 40.0)
            p = f["properties"]
            calzadas.append({"n": (p.get("Name") or "").strip(), "t": 1 if p.get("Type") == "Main Road" else 2, "g": [round(v) for q in pts for v in q]})
    print("Calzadas romanas:", len(calzadas))

    # IGME: oro (labores antiguas, en su mayoría romanas) y carbón
    def puntos(nombre, campo_n, campo_mun):
        out = []
        for f in json.load(open(RAW / f"{nombre}.json")):
            g = f.get("geometry") or {}
            if "x" not in g:
                continue
            x, y = g["x"] - M["x0"], M["y1"] - g["y"]
            if not en_prov(x, y):
                continue
            at = f["attributes"]
            out.append({"n": (at.get(campo_n) or "").strip().title(), "m": (at.get(campo_mun) or "").strip().title(),
                        "s": (at.get("Sustancia") or "").strip().title(), "xy": [round(x), round(y)]})
        return out
    oro = puntos("igme_oro", "Nombre_mina", "Municipio")
    carbon = puntos("igme_carbon", "Nombre_mina", "Municipio")
    escombreras = puntos("igme_escombreras", "NOMBRE", "NOMBRE_MUN")
    print("IGME en la provincia: oro", len(oro), "· carbón", len(carbon), "· escombreras de carbón", len(escombreras))

    # Wikidata: más sitios, con época deducida del tipo (se quitan fragmentos, repetidos y lo de fuera de la provincia)
    wd = json.load(open(RAW / "wikidata.json"))["results"]["bindings"]
    items = {}
    for b in wd:
        q = b["item"]["value"].rsplit("/", 1)[1]
        it = items.setdefault(q, {"n": b["itemLabel"]["value"], "d": b.get("itemDescription", {}).get("value", ""), "c": b["c"]["value"],
                                  "tipos": set(), "art": b.get("art", {}).get("value")})
        it["tipos"].add(b["tipoLabel"]["value"].lower())
    era_de = [("hierro", ["castro", "dolmen"]), ("roma", ["romana", "romano", "ciudad romana", "calzada"]),
              ("reino", ["monasterio", "castillo", "torre fortificada", "muralla", "abadía"]), ("mineria", ["mina"])]
    extra = []
    for q, it in items.items():
        if re.match(r"^(Q\d+|Habitaci|Galer|Delimitaci)", it["n"]) or "mosaico" in it["n"].lower():
            continue
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", it["c"])
        if not m:
            continue
        x, y = cx.local(float(m.group(2)), float(m.group(1)))
        if not en_prov(x, y):
            continue
        era = next((e for e, ks in era_de if any(k in t for t in it["tipos"] for k in ks)), None)
        if not era or any(math.hypot(x - s["xy"][0], y - s["xy"][1]) < 1500 and norm(s["n"])[:6] == norm(it["n"])[:6] for s in sitios):
            continue
        if era == "mineria" and not re.search(r"carb|hulla|antrac|pozo", (it["n"] + it["d"]).lower()):
            era = "roma" if "roman" in (it["n"] + it["d"]).lower() else None
            if not era:
                continue
        extra.append({"n": it["n"], "era": era, "d": it["d"], "xy": [round(x), round(y)], "wd": q, **({"w": it["art"]} if it["art"] else {})})
    print("Wikidata en la provincia:", len(extra), {e: sum(1 for s in extra if s["era"] == e) for e, _ in era_de})

    # población de los municipios mineros (censos, para la ficha de la época)
    mun = {m["n"]: m for m in L["municipios"]}
    mineros = [{"n": n, "ph": mun[n]["ph"]} for n in H["mineros"] if n in mun and mun[n].get("ph")]

    out = {"fuente": "Selección divulgativa de sitios (posiciones del IGN, Wikidata o su pueblo); calzadas romanas: Itiner-e 2024 (CC BY 4.0); "
                     "oro y carbón: IGME-CSIC (BDMIN e inventario de escombreras de 1989); más sitios: Wikidata",
           "epocas": H["epocas"], "sitios": sitios, "pueblos": pueblos, "camino": {k: v for k, v in H["camino"].items() if k != "por"} | {"g": [v for xy in camino for v in xy]},
           "calzadas": calzadas, "oro": oro, "carbon": carbon, "escombreras": escombreras, "extra": extra, "mineros": mineros}
    (RAIZ / "web" / "data" / "historia.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("Escrito historia.json", round((RAIZ / "web" / "data" / "historia.json").stat().st_size / 1e6, 2), "MB")
    for a_ in avisos:
        print("  aviso:", a_)


if __name__ == "__main__":
    main()
