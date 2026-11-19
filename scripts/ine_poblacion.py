"""Población de los municipios de la zona (INE, Padrón a 1 de enero; tablas por provincia en scripts/zona.py).

Uso: python3 scripts/ine_poblacion.py raw/poblacion_ine_2025.csv
"""
import csv
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zona import PROVINCIAS, PROVINCIAS_INE, MUNICIPIOS, es_de_la_zona  # noqa: E402

URL = "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{}?nult=1&tip=AM"


def main(out):
    series = []
    for pr in PROVINCIAS:
        tabla = PROVINCIAS_INE[pr][1]
        with urllib.request.urlopen(URL.format(tabla), timeout=180) as r:
            series += json.load(r)
    filas = []
    for s in series:
        md = s["MetaData"]
        mun = [m for m in md if m.get("T3_Variable") == "Municipios"]
        sexo = [m for m in md if m.get("T3_Variable") == "Sexo"]
        if mun and sexo and sexo[0]["Nombre"] == "Total" and len(mun[0].get("Codigo", "")) == 5 and es_de_la_zona(mun[0]["Codigo"]):
            d = s["Data"][0]
            filas.append((mun[0]["Codigo"], mun[0]["Nombre"], int(d["Valor"]), d["Anyo"]))
    esperados = len(MUNICIPIOS) if MUNICIPIOS else 211 if PROVINCIAS == ["24"] else None
    if (esperados and len(filas) != esperados) or not filas:
        sys.exit(f"Se esperaban {esperados} municipios y llegaron {len(filas)}")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "nombre_ine", "pob2025", "anyo"])
        w.writerows(sorted(filas))
    print(f"OK {out}: {len(filas)} municipios, año {filas[0][3]}, total {sum(x[2] for x in filas)}")


if __name__ == "__main__":
    main(sys.argv[1])
