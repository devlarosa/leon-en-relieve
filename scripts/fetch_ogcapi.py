"""Descarga paginada desde la OGC API Features de la IDEE (IGN). Uso: fetch_ogcapi.py coleccion salida.geojson [filtro=valor ...]"""
import json, sys, time, urllib.request, urllib.parse
UA = {"User-Agent": "Mozilla/5.0 (compatible; leon3d-datos/1.0)"}
col, out, *filters = sys.argv[1:]
params = {"f": "json", "limit": "2000", "bbox": "-7.1,42.0,-4.7,43.25"}
for f in filters:
    k, v = f.split("=", 1); params[k] = v
url = f"https://api-features.idee.es/collections/{col}/items?" + urllib.parse.urlencode(params)
feats = []
while url:
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                d = json.load(r); break
        except Exception as e:
            print("reintento", attempt, e, flush=True); time.sleep(5 * (attempt + 1))
    else:
        sys.exit("fallo definitivo en " + url)
    feats += d["features"]
    print(col, filters, len(feats), "/", d.get("numberMatched"), flush=True)
    url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
print("OK", out, len(feats))
