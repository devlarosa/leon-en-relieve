"""Población de cada entidad singular (pueblo) de la provincia de León (INE, Nomenclátor a 1 de enero).

Uso: python3 scripts/ine_nomenclator.py 2025 raw/nomenclator/entidades_ine.csv
"""
import csv
import html
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; leon3d-datos/1.0)"}


def leer(t):
    """Filas de la tabla: provincia | municipio "1 Acebedo" | código "00 02 00" | nombre | ES | total | hombres | mujeres"""
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        c = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", x))).strip() for x in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        if len(c) >= 8 and re.fullmatch(r"\d\d \d\d \d\d", c[-6]) and c[-4] == "ES":
            mun = re.match(r"(\d{1,3})\s+(.*)", c[-7])
            if not mun:
                continue
            col, sing, _ = c[-6].split()
            cm = mun.group(1).zfill(3)
            out.append(("24" + cm + col + sing, "24" + cm, mun.group(2), c[-5], int(c[-3].replace(".", "") or 0)))
    return out


def main(anio, out):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.open(urllib.request.Request("https://www.ine.es/nomen2/index.do", headers=UA), timeout=120).read()
    base = {"accion": "busquedaAvanzada", "entidad_amb": "ES", "comunidad": "7", "provincias": "24", "anios": anio,
            "poblacion_amb": "T", "desagregacion": "S", "poblacion_op": "MA", "poblacion_txt": "", "L": "0"}
    filas, pag, npag = [], 1, 1
    while pag <= npag:
        datos = urllib.parse.urlencode(dict(base, **({"numPag": str(pag)} if pag > 1 else {}))).encode()
        t = op.open(urllib.request.Request("https://www.ine.es/nomen2/tabla.do", data=datos, headers=UA), timeout=300).read().decode("utf-8", "replace")
        m = re.search(r"Página\s+\d+\s+de\s+(\d+)", t)
        npag = int(m.group(1)) if m else 1
        filas += leer(t)
        print(f"  página {pag} de {npag}: {len(filas)} entidades", flush=True)
        pag += 1
    filas = list(dict.fromkeys(filas))   # por si una página se repite
    if len(filas) < 1000:
        sys.exit(f"Solo se leyeron {len(filas)} entidades: revisa el formato de la tabla del INE")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["codigo", "municipio_ine", "municipio", "nombre_ine", f"pob{anio}"])
        w.writerows(filas)
    print(f"OK {out}: {len(filas)} entidades singulares, {sum(x[4] for x in filas)} habitantes")


if __name__ == "__main__":
    main(*sys.argv[1:])
