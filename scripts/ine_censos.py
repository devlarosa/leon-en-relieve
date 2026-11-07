"""Población histórica de los municipios de León (INE, Alteraciones de los municipios en los Censos desde 1842).

Para cada municipio actual descarga su ficha censal y la de los municipios que absorbió
(siguiendo las notas "incorpora a 24xxx" de forma recursiva) y suma la población de derecho
censo a censo, para comparar siempre el mismo territorio. Añade la cifra del Padrón 2025.

Uso: python3 scripts/ine_censos.py raw/poblacion_ine_2025.csv raw/historico/censos.json
"""
import csv
import http.cookiejar
import json
import re
import sys
import time
import urllib.request

BASE = "https://www.ine.es/intercensal/"
UA = {"User-Agent": "Mozilla/5.0 (compatible; leon3d-datos/1.0)"}
AÑOS = [1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1981, 1991, 2001, 2011, 2021]

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(url):
    for intento in range(6):
        try:
            with opener.open(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            print("  reintento", intento, e, flush=True)
            time.sleep(4 * (intento + 1))
    raise RuntimeError("no se pudo descargar " + url)


def ficha(code):
    html = get(f"{BASE}intercensal.do?search=3&codigoProvincia=24&codigoMunicipio={code[2:]}&btnBuscarCod=Consultar")
    filas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        celdas = [re.sub(r"\s+", " ", re.sub(r"<[^>]*>|&nbsp;", " ", c)).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        if any(celdas):
            filas.append(celdas)
    años = next((f for f in filas if f and f[0].startswith("1842")), None)
    derecho = next((f[1:] for f in filas if f and f[0].startswith("Población de Derecho")), None)
    if not años or not derecho:
        return None
    pob = {}
    for a, v in zip(años, derecho):
        ma, v = re.match(r"(\d{4})", a), v.split("[")[0].strip().replace(".", "")
        if ma and v.isdigit():
            pob[int(ma.group(1))] = int(v)
    incorpora = []
    for f in filas:
        texto = " ".join(f)
        # "porque incorpora a 24500 (Armunia)" = absorbe; "se incorpora a ..." = cede territorio (no se suma)
        for m in re.finditer(r"(?<!se )incorpora a ((?:\s*(?:,|y)?\s*24\d{3} \([^)]*\))+)", texto):
            incorpora += re.findall(r"\b(24\d{3})\b", m.group(1))
        if "aparece este municipio porque" in texto:   # creado por fusión o por cambio de nombre de otro
            incorpora += re.findall(r"\b(24\d{3})\b", texto.split("aparece este municipio porque", 1)[1])
    nombre = re.search(r"Municipio:\s*\d+\s+(.+)", " ".join(filas[0])) if filas else None
    return {"nombre": nombre.group(1).strip() if nombre else code, "pob": pob, "incorpora": sorted(set(incorpora))}


def main(padron_csv, out):
    get(BASE)  # abre sesión
    actuales = {r["code"]: int(r["pob2025"]) for r in csv.DictReader(open(padron_csv))}
    cache_f = out.rsplit("/", 1)[0] + "/fichas_cache.json"
    try:
        cache = json.load(open(cache_f))
    except (OSError, ValueError):
        cache = {}
    res = {}

    def cargar(code):
        if code not in cache:
            cache[code] = ficha(code)
            time.sleep(0.3)
        return cache[code]

    for n, code in enumerate(sorted(actuales), 1):
        pendientes, vistos, total, absorbidos = [code], set(), {a: 0 for a in AÑOS}, []
        while pendientes:
            c = pendientes.pop()
            if c in vistos:
                continue
            vistos.add(c)
            f = cargar(c)
            if not f:
                print("  sin ficha", c, flush=True)
                continue
            if c != code:
                absorbidos.append(f"{c} {f['nombre']}")
            for a in AÑOS:
                total[a] += f["pob"].get(a, f["pob"].get(str(a), 0))
            pendientes += [x for x in f["incorpora"] if x not in actuales]   # un municipio que existe hoy nunca se suma a otro
        total[2025] = actuales[code]
        res[code] = {"nombre": cache[code]["nombre"] if cache.get(code) else code, "pob": total, "absorbidos": absorbidos}
        if n % 20 == 0:
            print(f"{n}/{len(actuales)}", flush=True)
    json.dump(cache, open(cache_f, "w"), ensure_ascii=False)
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    for a in AÑOS + [2025]:
        print(a, sum(r["pob"][a] for r in res.values()))


if __name__ == "__main__":
    main(*sys.argv[1:])
