"""Comarca tradicional de cada municipio de León según su ficha en es.wikipedia.org.

No es una división oficial: León no tiene comarcalización oficial salvo El Bierzo
(Ley 1/1991 de Castilla y León), que se trata aparte en R/10_preparar_web.R.

1. Wikidata: código INE (P772) -> artículo de es.wikipedia.
2. Wikipedia: campo de comarca de la ficha de cada artículo.

Uso: python3 scripts/comarcas_wikipedia.py raw/comarcas/comarca_wikipedia.json
"""
import collections
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "leon3d-datos/1.0 (mapa educativo)"}
SPARQL = """SELECT ?ine ?article WHERE {
  ?item wdt:P772 ?ine . FILTER(STRSTARTS(?ine, "24") && STRLEN(?ine) = 5)
  ?article schema:about ?item ; schema:isPartOf <https://es.wikipedia.org/> . }"""
SINONIMOS = {"Cabrera": "La Cabrera"}


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
        return json.load(r)


def comarca_de(texto):
    m = None
    for pat in (r"tipo_superior_\d+\s*=\s*\[?\[?Comarca[^\n]*\n\s*\|\s*superior_\d+\s*=\s*([^\n]+)",
                r"\|\s*comarca\s*=\s*([^\n]+)",
                r"Comarca\]?\]?\s*\|\s*superior_\d+\s*=\s*([^\n]+)"):
        m = re.search(pat, texto, re.I)
        if m:
            break
    if not m:
        return ""
    raw = re.sub(r"\[\[(?:Archivo|File|Imagen|Image):[^\]]*\]\]", "", m.group(1))
    raw = re.split(r"\{\{|<ref", raw)[0]
    links = re.findall(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", raw)
    val = (links[0][1] or links[0][0]) if links else re.sub(r"<.*?>", "", raw).strip(" '")
    val = val.strip()
    return SINONIMOS.get(val, val)


def main(out):
    q = urllib.parse.urlencode({"query": SPARQL, "format": "json"})
    filas = get_json("https://query.wikidata.org/sparql?" + q)["results"]["bindings"]
    mun = {f["ine"]["value"]: urllib.parse.unquote(f["article"]["value"].split("/wiki/")[1]).replace("_", " ") for f in filas}
    titulos, textos = list(mun.values()), {}
    for i in range(0, len(titulos), 50):
        q = urllib.parse.urlencode({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                                    "format": "json", "redirects": 1, "titles": "|".join(titulos[i:i + 50])})
        r = get_json("https://es.wikipedia.org/w/api.php?" + q)
        for p in r["query"]["pages"].values():
            textos[p["title"]] = p["revisions"][0]["slots"]["main"]["*"]
        time.sleep(1)
    res = {ine: {"articulo": t, "comarca": comarca_de(textos.get(t, ""))} for ine, t in sorted(mun.items())}
    vacias = [v["articulo"] for v in res.values() if not v["comarca"]]
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"OK {out}: {len(res)} municipios, {len(vacias)} sin comarca {vacias}")
    print(collections.Counter(v["comarca"] for v in res.values()).most_common(10))


if __name__ == "__main__":
    main(sys.argv[1])
