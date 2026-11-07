"""Población municipal de la provincia de León (INE, Padrón a 1 de enero, tabla 2877).

Uso: python3 scripts/ine_poblacion.py raw/poblacion_ine_2025.csv
"""
import csv
import json
import sys
import urllib.request

URL = "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/2877?nult=1&tip=AM"


def main(out):
    with urllib.request.urlopen(URL, timeout=180) as r:
        series = json.load(r)
    filas = []
    for s in series:
        md = s["MetaData"]
        mun = [m for m in md if m.get("T3_Variable") == "Municipios"]
        sexo = [m for m in md if m.get("T3_Variable") == "Sexo"]
        if mun and sexo and sexo[0]["Nombre"] == "Total" and len(mun[0].get("Codigo", "")) == 5:
            d = s["Data"][0]
            filas.append((mun[0]["Codigo"], mun[0]["Nombre"], int(d["Valor"]), d["Anyo"]))
    if len(filas) != 211:
        sys.exit(f"Se esperaban 211 municipios y llegaron {len(filas)}")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "nombre_ine", "pob2025", "anyo"])
        w.writerows(sorted(filas))
    print(f"OK {out}: {len(filas)} municipios, año {filas[0][3]}, total {sum(x[2] for x in filas)}")


if __name__ == "__main__":
    main(sys.argv[1])
