#!/usr/bin/env python3
"""Descarga la red hidrográfica del IGN (INSPIRE HY-N) para la zona del visor, desde la OGC API Features de la IDEE.

- watercourselink: tramos con nodo de inicio y fin y sentido del agua (topología de la red)
- watercourselinksequence: cursos (ríos) con su nombre y longitud (sin geometría)
- drainagebasin: cuencas de captación de la Dirección General del Agua con su orden Pfafstetter y superficie (sin geometría)
Además sigue aguas abajo, fuera de la zona, los ríos que salen de ella (Esla hasta el Duero, Sil hasta el Miño…),
para poder decir dónde desemboca cada uno.

Los identificadores de nodo solo son únicos dentro de cada demarcación: la clave es (demarcación, nodo).
Además descarga el Anuario de Aforos del MITECO (CSV de las confederaciones del Duero, Miño-Sil y Cantábrico)
y los listados de situación de las estaciones, que usa scripts/rios_red.py para caudales y embalses.

Salida: raw/rios_red/*.jsonl y raw/rios_mapa/ (caché; se puede relanzar).
"""
import json
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from zona import ZONA  # noqa: E402  (variable de entorno ZONA; por defecto «leon»)
OUT = RAIZ / "raw" / ZONA / "rios_red"
API = "https://api-features.idee.es/collections"
UA = "Mozilla/5.0 (compatible; leon3d-datos/1.0)"
from zona import FICHA  # noqa: E402
_b = FICHA["bbox"]                  # la misma caja que el resto de descargas de la zona (lat_min, lon_min, lat_max, lon_max)
BBOX = f"{_b[1]},{_b[0]},{_b[3]},{_b[2]}"
AFOROS = "https://www.miteco.gob.es/content/dam/miteco/es/agua/temas/evaluacion-de-los-recursos-hidricos/sistema-informacion-anuario-aforos/"
AFOROS_ZIP = "Anuario-21-22-csv.zip"      # último anuario publicado; al salir uno nuevo, cambiar aquí el nombre
CUENCAS_AFOROS = ("DUERO/", "MIÑO-SIL/", "CANTABRICO/")


def get(url, intentos=5):
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"  reintento {i + 1}: {e}")
            time.sleep(5 * (i + 1))
    raise SystemExit("No se pudo descargar " + url)


def paginar(coleccion, params, limite=5000):
    url = f"{API}/{coleccion}/items?" + urllib.parse.urlencode(dict(params, f="json", limit=limite))
    n = 0
    while url:
        d = get(url)
        for f in d.get("features", []):
            yield f
            n += 1
        url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
        print(f"  {coleccion}: {n} de {d.get('numberMatched')}", flush=True)


def por_teselas(coleccion, extra=None, caja=(-7.15, 41.95, -4.65, 43.30), paso=0.25, limite=2500):
    """Descarga por teselas pequeñas (una página cada una): la paginación por desplazamiento de esta API repite
    y salta elementos, y su numberMatched viene duplicado. Si una tesela se llena, se divide en cuatro."""
    vistos = set()
    pend = [(x, y, min(x + paso, caja[2]), min(y + paso, caja[3]))
            for x in np.arange(caja[0], caja[2], paso) for y in np.arange(caja[1], caja[3], paso)]
    hechas = 0
    while pend:
        x0, y0, x1, y1 = pend.pop()
        q = dict(extra or {}, f="json", limit=limite, bbox=f"{x0:.4f},{y0:.4f},{x1:.4f},{y1:.4f}")
        d = get(f"{API}/{coleccion}/items?" + urllib.parse.urlencode(q))
        fs = d.get("features", [])
        if len(fs) >= limite:
            xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
            pend += [(x0, y0, xm, ym), (xm, y0, x1, ym), (x0, ym, xm, y1), (xm, ym, x1, y1)]
            continue
        for f in fs:
            k = f.get("id") or json.dumps(f["properties"], sort_keys=True)
            if k not in vistos:
                vistos.add(k); yield f
        hechas += 1
        if hechas % 10 == 0:
            print(f"  {coleccion}: {hechas} teselas, {len(vistos)} elementos, quedan {len(pend)}", flush=True)


def nodo(s):
    return s.rsplit("_", 1)[-1] if s else None


def tramo(f):
    p = f["properties"]; g = f["geometry"]
    cs = g["coordinates"] if g["type"] == "LineString" else [c for parte in g["coordinates"] for c in parte]
    if p.get("dir_flujo") == "27002":          # digitalizado contra corriente: se da la vuelta
        cs = cs[::-1]; ini, fin = nodo(p["nodo_fin"]), nodo(p["nodo_ini"])
    else:
        ini, fin = nodo(p["nodo_ini"]), nodo(p["nodo_fin"])
    return {"dm": p["id_demarc"], "t": p["id_tramo"], "c": p["id_curso"], "i": ini, "f": fin, "l": float(p["longitud"] or 0),
            "x": p.get("ficticio") == "True", "g": [[round(c[0], 5), round(c[1], 5)] for c in cs]}


def guardar(nombre, filas):
    with open(OUT / nombre, "w", encoding="utf-8") as fh:
        for r in filas:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def leer(nombre):
    p = OUT / nombre
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else None


def anuario_aforos():
    import zipfile
    dest = RAIZ / "raw" / ZONA / "rios_mapa"; dest.mkdir(parents=True, exist_ok=True)
    for nombre, solo in ((AFOROS_ZIP, CUENCAS_AFOROS), ("listado-estaciones-aforo.zip", None)):
        z = dest / nombre
        if not z.exists() or not zipfile.is_zipfile(z):
            print("Descargando", nombre, "…", flush=True)
            req = urllib.request.Request(AFOROS + nombre, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=1800) as r, open(str(z) + ".part", "wb") as fh:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    fh.write(b)
            Path(str(z) + ".part").rename(z)
        with zipfile.ZipFile(z) as zf:
            for m in zf.namelist():
                if not m.endswith("/") and (solo is None or m.startswith(solo)) and not (dest / m).exists():
                    zf.extract(m, dest)
    print("Anuario de Aforos en", dest)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    anuario_aforos()
    tramos = leer("tramos.jsonl")
    if tramos is None:
        print("Tramos de la red (watercourselink)…")
        tramos = [tramo(f) for f in por_teselas("watercourselink")]
        guardar("tramos.jsonl", tramos)
    if leer("cursos.jsonl") is None:
        print("Cursos con nombre (watercourselinksequence)…")
        guardar("cursos.jsonl", [{"dm": f["properties"]["id_demarc"], "c": f["properties"]["id_curso"], "n": f["properties"]["nombre"],
                                  "l": float(f["properties"]["longitud"] or 0)}
                                 for f in por_teselas("watercourselinksequence", {"skipGeometry": "true"}, paso=0.5)])
    if leer("cuencas.jsonl") is None:
        print("Cuencas de la DGA (drainagebasin, solo atributos)…")
        guardar("cuencas.jsonl", [{"dm": f["properties"]["id_demarc"], "n": f["properties"]["nombre"], "o": int(f["properties"]["orden"] or 0),
                                   "a": float(f["properties"]["area"] or 0)}
                                  for f in por_teselas("drainagebasin", {"skipGeometry": "true"}, paso=0.5)])

    # seguir aguas abajo lo que sale de la zona
    extra = leer("aguas_abajo.jsonl") or []
    vistos_c = {tuple(x) for x in (leer("cursos_completos.jsonl") or [])}   # cursos descargados enteros
    cursos = {(c["dm"], c["c"]): c for c in leer("cursos.jsonl")}
    for ronda in range(12):
        todos = tramos + extra
        salen = {(t["dm"], t["i"]) for t in todos}
        largos = {k for k, c in cursos.items() if c["n"] and c["l"] > 8000}
        candidatos = [t for t in tramos if (t["dm"], t["c"]) in largos] + extra   # ríos con nombre largos y lo ya seguido
        finales = {(t["dm"], t["f"]) for t in candidatos if (t["dm"], t["f"]) not in salen}
        hechos = {tuple(x) for x in (leer("nodos_finales.jsonl") or [])}
        pendientes = sorted(finales - hechos)
        if not pendientes:
            break
        print(f"Ronda {ronda + 1}: {len(pendientes)} desembocaduras por seguir")
        nuevos = []
        for dm, nd in pendientes:
            d = get(f"{API}/watercourselink/items?" + urllib.parse.urlencode({"f": "json", "limit": 20, "id_demarc": dm, "nodo_ini": f"#HY-N_HYDRONODE_{nd}"}))
            for f in d.get("features", []):
                c = f["properties"]["id_curso"]
                if (dm, c) in vistos_c:
                    continue
                vistos_c.add((dm, c))
                print(f"  {dm} nodo {nd} → curso {c}")
                nuevos += [tramo(g) for g in paginar("watercourselink", {"id_demarc": dm, "id_curso": c})]
                if (dm, c) not in cursos:
                    for s in get(f"{API}/watercourselinksequence/items?" + urllib.parse.urlencode({"f": "json", "limit": 5, "skipGeometry": "true", "id_demarc": dm, "id_curso": c})).get("features", []):
                        p = s["properties"]; cursos[(dm, c)] = {"dm": dm, "c": c, "n": p["nombre"], "l": float(p["longitud"] or 0)}
            hechos.add((dm, nd))
        extra += nuevos
        guardar("aguas_abajo.jsonl", extra)
        guardar("nodos_finales.jsonl", [list(x) for x in sorted(hechos)])
        guardar("cursos_completos.jsonl", [list(x) for x in sorted(vistos_c)])
        guardar("cursos.jsonl", list(cursos.values()))
    print(f"Listo: {len(tramos)} tramos en la zona, {len(extra)} aguas abajo, {len(cursos)} cursos")


if __name__ == "__main__":
    main()
