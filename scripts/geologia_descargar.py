#!/usr/bin/env python3
"""Descarga la geología oficial del IGME-CSIC para la zona del visor (servicios ArcGIS de mapas.igme.es).

- Mapa Geológico de España 1:1.000.000 (litologías color): unidad, litología general, era, sistema y serie
- MAGNA 1:50.000 (litologías color): descripción de cada unidad cartográfica por hoja
- Mapa Hidrogeológico 1:200.000: permeabilidad
- Inventario Español de Lugares de Interés Geológico (IELIG)

Se pide por teselas (cada servicio devuelve como mucho 1000 elementos por consulta) en ETRS89 / UTM 30N,
con la geometría ya simplificada a 20 m en el servidor (que además la recorta a cada tesela). Salida: raw/geologia/*.jsonl (caché; se puede relanzar).
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
OUT = RAIZ / "raw" / "geologia"
BASE = "https://mapas.igme.es/gis/rest/services"
UA = "Mozilla/5.0 (compatible; leon3d-datos/1.0)"
CAJA = (164000, 4655000, 360000, 4790000)          # la del visor, en metros UTM 30
CAPAS = {
    "g1m": ("Cartografia_Geologica/IGME_Geologico_1M", 4, "OBJECTID,ID,SIGLA,LITOGENER,DLO,EON_ERA,SUBERA,SISTEMA,SERIE,PISO", 40000),
    "magna": ("Cartografia_Geologica/IGME_MAGNA_50", 11, "OBJECTID,HOJA,ID,DLO", 10000),
    "hidro": ("Cartografia_Tematica/IGME_Hidrogeologico_200", 0, "OBJECTID,COD_HIDR_1,CLHID,HIDPERM", 20000),
    "lig": ("BasesDatos/IGME_IELIG", 0, "*", 70000),
}


def get(url, intentos=6):
    for i in range(intentos):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300) as r:
                d = json.loads(r.read().decode("utf-8"))
            if "error" in d:
                raise RuntimeError(d["error"])
            return d
        except Exception as e:
            print(f"  reintento {i + 1}: {e}", flush=True)
            time.sleep(5 * (i + 1))
    raise SystemExit("No se pudo descargar " + url)


def consulta(servicio, capa, campos, x0, y0, x1, y1):
    q = {"geometry": f"{x0},{y0},{x1},{y1}", "geometryType": "esriGeometryEnvelope", "inSR": 25830, "outSR": 25830,
         "spatialRel": "esriSpatialRelIntersects", "outFields": campos, "returnGeometry": "true",
         "maxAllowableOffset": 20, "geometryPrecision": 0, "f": "json"}
    return get(f"{BASE}/{servicio}/MapServer/{capa}/query?" + urllib.parse.urlencode(q))


def descargar(nombre, servicio, capa, campos, paso):
    destino = OUT / f"{nombre}.jsonl"
    if destino.exists():
        print("ya está", destino.name); return
    vistos, n = set(), 0
    pend = [(x, y, min(x + paso, CAJA[2]), min(y + paso, CAJA[3])) for x in range(CAJA[0], CAJA[2], paso) for y in range(CAJA[1], CAJA[3], paso)]
    with open(str(destino) + ".part", "w", encoding="utf-8") as fh:
        while pend:
            x0, y0, x1, y1 = pend.pop()
            d = consulta(servicio, capa, campos, x0, y0, x1, y1)
            fs = d.get("features", [])
            if d.get("exceededTransferLimit") or len(fs) >= 1000:      # tesela llena: se divide en cuatro
                xm, ym = (x0 + x1) // 2, (y0 + y1) // 2
                pend += [(x0, y0, xm, ym), (xm, y0, x1, ym), (x0, ym, xm, y1), (xm, ym, x1, y1)]
                continue
            for f in fs:
                # el servidor recorta cada polígono a la tesela pedida: se guardan los trozos de todas las teselas
                # (encajan entre sí); solo los puntos (lugares de interés) se descartan si se repiten
                a = f["attributes"]; k = a.get("OBJECTID", a.get("ESRI_OID"))   # identificador único: hay que pedirlo en outFields
                assert k is not None, "falta OBJECTID en la respuesta"
                if "rings" in (f.get("geometry") or {}):
                    k = (k, x0, y0)
                if k in vistos:
                    continue
                vistos.add(k); n += 1
                g = f.get("geometry") or {}
                fh.write(json.dumps({"a": a, "r": g.get("rings"), "p": [g["x"], g["y"]] if "x" in g else None}, ensure_ascii=False) + "\n")
            print(f"  {nombre}: {n} elementos, quedan {len(pend)} teselas", flush=True)
    Path(str(destino) + ".part").rename(destino)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for nombre, (servicio, capa, campos, paso) in CAPAS.items():
        print("Descargando", nombre, "…", flush=True)
        descargar(nombre, servicio, capa, campos, paso)
    print("Listo en", OUT)


if __name__ == "__main__":
    main()
