#!/usr/bin/env python3
"""Sitúa en el mapa los lugares de interés de recursos/<zona>/lugares.json (ZONA=leon por defecto).

Para cada lugar busca coordenadas, por este orden:
  1. Nomenclátor Geográfico Básico de España (IGN, servicio WFS INSPIRE) por nombre
  2. Wikidata (propiedad P625, coordenadas)
  3. La localidad de referencia ('cerca'), marcada como posición aproximada
Un candidato solo vale si cae dentro del municipio indicado y a menos de 8 km de la localidad de referencia.
Salida: web/data/lugares.json. Las respuestas se guardan en raw/lugares/cache.json (se puede relanzar).
"""
import json
import math
import re
import sys
import time
import urllib.error
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from zona import ZONA, FICHA  # noqa: E402  (variable de entorno ZONA; por defecto «leon»)
# caja de la zona para buscar en el Nomenclátor (con dos decimales si los tiene justos: «43.30», como siempre en León)
BB = [f"{v:.2f}" if abs(v * 100 - round(v * 100)) < 1e-9 else f"{v}" for v in FICHA["bbox"]]
sys.path.insert(0, str(RAIZ / "scripts"))
from rios_red import latlon_a_utm30  # noqa: E402

UA = "Mozilla/5.0 (compatible; leon3d-datos/1.0)"
CACHE = RAIZ / "raw" / ZONA / "lugares" / "cache.json"
MAX_KM = 8


def norm(t):
    t = unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def get(url, cache):
    if url in cache:
        return cache[url]
    for i in range(6):           # Wikidata limita la frecuencia (429): pausa y reintento
        try:
            time.sleep(1.2 if "wikidata" in url else 0.2)
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120) as r:
                txt = r.read().decode("utf-8", "ignore")
            cache[url] = txt
            return txt
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == 5:
                raise
            time.sleep(10 * (i + 1))


def ngbe(texto, cache):
    F = ('<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" xmlns:gn="http://inspire.ec.europa.eu/schemas/gn/4.0" xmlns:gml="http://www.opengis.net/gml/3.2"><fes:And>'
         '<fes:BBOX><fes:ValueReference>gn:geometry</fes:ValueReference><gml:Envelope srsName="urn:ogc:def:crs:EPSG::4258">'
         f'<gml:lowerCorner>{BB[0]} {BB[1]}</gml:lowerCorner><gml:upperCorner>{BB[2]} {BB[3]}</gml:upperCorner></gml:Envelope></fes:BBOX><fes:PropertyIsLike wildCard="*" singleChar="." escapeChar="!" matchCase="false">'
         '<fes:ValueReference>gn:name/gn:GeographicalName/gn:spelling/gn:SpellingOfName/gn:text</fes:ValueReference>'
         f'<fes:Literal>*{texto}*</fes:Literal></fes:PropertyIsLike></fes:And></fes:Filter>')
    q = urllib.parse.urlencode({"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": "gn:NamedPlace", "count": "100", "filter": F})
    x = get("https://www.ign.es/wfs-inspire/ngbe?" + q, cache)
    out = []
    for m in re.finditer(r"<gn:NamedPlace.*?</gn:NamedPlace>", x, re.S):
        b = m.group(0)
        nom = re.search(r"<gn:text>([^<]+)</gn:text>", b)
        tipo = re.search(r"<gn:localType>.*?<gmd:LocalisedCharacterString[^>]*>([^<]+)<", b, re.S)
        pos = re.search(r"<gml:pos[^>]*>([^<]+)</gml:pos>", b) or re.search(r"<gml:posList[^>]*>([^<]+)</gml:posList>", b)
        if nom and pos:
            v = [float(t) for t in pos.group(1).split()]
            out.append({"n": nom.group(1), "tipo": tipo.group(1) if tipo else "", "lat": v[0], "lon": v[1]})
    return out


def wikidata(texto, cache):
    s = json.loads(get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbsearchentities", "search": texto, "language": "es", "limit": 6, "format": "json"}), cache))
    ids = [r["id"] for r in s.get("search", [])]
    if not ids:
        return []
    e = json.loads(get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbgetentities", "ids": "|".join(ids), "props": "claims|labels", "languages": "es", "format": "json"}), cache))
    out = []
    for q in ids:
        ent = e["entities"].get(q, {})
        for c in ent.get("claims", {}).get("P625", []):
            v = c["mainsnak"].get("datavalue", {}).get("value")
            if v:
                out.append({"n": ent.get("labels", {}).get("es", {}).get("value", q), "tipo": "Wikidata " + q, "lat": v["latitude"], "lon": v["longitude"], "qid": q})
    return out


def dentro(x, y, rings):
    ins = False
    for r in rings:
        for i in range(0, len(r), 2):
            j = (i - 2) % len(r)
            xi, yi, xj, yj = r[i], r[i + 1], r[j], r[j + 1]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                ins = not ins
    return ins


class Contexto:
    """Datos del visor necesarios para situar lugares (municipios, pueblos, malla)."""
    def __init__(self):
        L = json.loads((RAIZ / "web" / "data" / ZONA / "zona.json").read_text())
        self.L, self.M = L, L["meta"]
        self.munis = {m["n"]: m for m in L["municipios"]}
        self.pueblos = [(e["n"].split(" / ")[0], e.get("c"), e["xy"]) for e in L["capitales"] + L["entidades"]]
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        self.cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    def guardar(self):
        CACHE.write_text(json.dumps(self.cache, ensure_ascii=False))

    def local(self, lat, lon):
        E, N = latlon_a_utm30(np.array(lat), np.array(lon))
        return float(E) - self.M["x0"], self.M["y1"] - float(N)


def situar(l, cx, avisos):
    """Devuelve ((x, y), fuente, nombre encontrado, qid) o None. l: dict con n, mun y opcionalmente ngbe, wd, cerca."""
    mun = cx.munis.get(l["mun"])
    if not mun:
        avisos.append(f"{l['n']}: municipio desconocido {l['mun']}"); return None
    cerca = norm(l.get("cerca", ""))
    ref = next((xy for n, c, xy in cx.pueblos if norm(n) == cerca and c == mun["c"]), None) \
        or next((xy for n, c, xy in cx.pueblos if cerca and norm(n).startswith(cerca) and c == mun["c"]), None)
    refmun = next((c["xy"] for c in cx.L["capitales"] if c.get("c") == mun["c"]), None)   # capital del municipio, último recurso

    def vale(c):
        x, y = cx.local(c["lat"], c["lon"])
        ok = dentro(x, y, mun["g"]) and (ref is None or math.hypot(x - ref[0], y - ref[1]) <= MAX_KM * 1000)
        return (x, y) if ok else None

    def puntua(c):    # nombre más parecido primero; los cauces, al final
        n = norm(c["n"]); objetivo = {norm(l["n"]), norm(l.get("ngbe", "")), norm(l.get("wd", ""))} - {""}
        return (0 if n in objetivo else 1 if any(o in n or n in o for o in objetivo) else 2, "agua" in norm(c["tipo"]))

    for fuente, buscar, termino in (("IGN", ngbe, l.get("ngbe")), ("Wikidata", wikidata, l.get("wd")), ("Wikidata", wikidata, l["n"])):
        if not termino:
            continue
        try:
            cands = buscar(termino, cx.cache)
        except Exception as e:      # un servicio caído no detiene el resto
            avisos.append(f"{l['n']}: {fuente} falló ({e})"); continue
        for c in sorted(cands, key=puntua):
            xy = vale(c)
            if xy and puntua(c)[0] < 2:
                return xy, fuente, c["n"], c.get("qid")
    if ref or refmun:
        return tuple(ref or refmun), "aprox", l.get("cerca") if ref else "capital de " + l["mun"], None
    avisos.append(f"{l['n']}: sin posición")
    return None


def main():
    D = json.loads((RAIZ / "recursos" / ZONA / "lugares.json").read_text(encoding="utf-8"))
    cx = Contexto()
    salida, avisos = [], []
    for l in D["lugares"]:
        r = situar(l, cx, avisos)
        if not r:
            continue
        (x, y), fuente, encontrado, qid = r
        salida.append({"n": l["n"], "cat": l["cat"], "desc": l["desc"], "mun": l["mun"], "xy": [round(x), round(y)],
                       "fuente": fuente, "como": encontrado, **({"wd": qid} if qid else {})})
        print(f"  {fuente:8} {l['n']:42} ← {encontrado}")
    cx.guardar()
    out = {"fuente": "Lugares escogidos para el visor; posiciones del Nomenclátor Geográfico Básico de España (IGN) o, si no figuran, de Wikidata",
           "categorias": D["categorias"], "lugares": salida}
    (RAIZ / "web" / "data" / ZONA / "lugares.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    cuenta = {f: sum(1 for s in salida if s["fuente"] == f) for f in ("IGN", "Wikidata", "aprox")}
    print(f"{len(salida)} lugares: {cuenta}")
    for a in avisos:
        print("  aviso:", a)


if __name__ == "__main__":
    main()
