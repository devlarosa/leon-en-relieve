#!/usr/bin/env python3
"""Normales climáticas 1991-2020 para el visor, a partir de la rejilla diaria de 5 km de AEMET (ROCIO_IBEB).

Entrada: raw/clima_aemet/*.tar.gz (scripts/descargar_clima_aemet.sh); se leen sin descomprimir.
Salida:  web/data/clima.png  (atlas de rejillas a 1 km, valores de 16 bits en los canales R y G)
         web/data/clima.json (variables, escalas, gradiente con la altitud y rango en la provincia)

Ajuste con la altitud: la rejilla de 5 km promedia montaña y valle. Para cada mes y variable se ajusta por
mínimos cuadrados, sobre las celdas de la zona, v = a + b·altitud + c·x + d·y; con ese gradiente b se guarda el
valor «reducido a 0 m» de cada celda (v − b·altitud media de la celda) y el visor lo devuelve a la altitud real
del MDT: v = ref + b·altitud. En precipitación no se aplica (b = 0): depende demasiado de la orientación.

Uso: python3 scripts/clima_aemet.py
"""
import io
import json
import tarfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.io import netcdf_file

RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / "raw" / "clima_aemet"
WEB = RAIZ / "web" / "data"
ANIOS = range(1991, 2021)
PASO = 1000                      # m por píxel del atlas
POLO_LAT, LON0, ROT = 49.5, -6.0, 40.5   # polo rotado de la rejilla (comprobado con sus lat/lon)
NODATA = -9999.0


# ---------------------------------------------------------------- geometría
def utm_a_latlon(E, N):
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    e2 = f * (2 - f); ep2 = e2 / (1 - e2)
    x = E - 500000.0; m = N / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - np.sqrt(1 - e2)) / (1 + np.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * np.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * np.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * np.sin(6 * mu) + (1097 * e1 ** 4 / 512) * np.sin(8 * mu))
    C1 = ep2 * np.cos(p1) ** 2; T1 = np.tan(p1) ** 2; N1 = a / np.sqrt(1 - e2 * np.sin(p1) ** 2)
    R1 = a * (1 - e2) / (1 - e2 * np.sin(p1) ** 2) ** 1.5; D = x / (N1 * k0)
    lat = p1 - (N1 * np.tan(p1) / R1) * (D ** 2 / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * ep2) * D ** 4 / 24
                                        + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * ep2 - 3 * C1 ** 2) * D ** 6 / 720)
    lon = (D - (1 + 2 * T1 + C1) * D ** 3 / 6 + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * ep2 + 24 * T1 ** 2) * D ** 5 / 120) / np.cos(p1)
    return np.degrees(lat), -3.0 + np.degrees(lon)


def a_rotadas(lat, lon):
    p = np.radians(lat); l = np.radians(lon - LON0); t = np.radians(ROT)
    x, y, z = np.cos(p) * np.cos(l), np.cos(p) * np.sin(l), np.sin(p)
    x2 = np.cos(t) * x + np.sin(t) * z; z2 = -np.sin(t) * x + np.cos(t) * z
    return np.degrees(np.arcsin(z2)), np.degrees(np.arctan2(y, x2))


# ---------------------------------------------------------------- lectura
def ficheros(var):
    pref = "pcp" if var == "pcp" else var
    for t in sorted(RAW.glob(f"Serie_AEMET_v*_{pref}_*_netcdf.tar.gz")):
        with tarfile.open(t) as tf:
            for m in tf.getmembers():
                if not m.name.endswith(".nc"):
                    continue
                anio = int(Path(m.name).name[5:9])
                if anio in ANIOS:
                    yield anio, tf.extractfile(m).read()


def leer(var, ventana):
    """Media 1991-2020 por mes: valor medio (temperatura) o acumulado (precipitación) y días que cumplen umbrales."""
    j0, j1, i0, i1 = ventana
    nombre = {"pcp": "precipitation", "tmax": "maxtemp", "tmin": "mintemp"}[var]
    shape = (12, j1 - j0, i1 - i0)
    suma = np.zeros(shape); dias = np.zeros(shape); umbral = np.zeros(shape); visto = set()
    for anio, datos in ficheros(var):
        f = netcdf_file(io.BytesIO(datos), mmap=False)
        v = f.variables[nombre]
        d = np.array(v[:, 0, j0:j1, i0:i1], dtype=np.float64)
        d[d <= NODATA + 1] = np.nan
        meses = np.array([(date(anio, 1, 1) + timedelta(days=k)).month - 1 for k in range(d.shape[0])])
        for m in range(12):
            sel = d[meses == m]
            suma[m] += np.nansum(sel, axis=0); dias[m] += np.sum(np.isfinite(sel), axis=0)
            if var == "tmin":
                umbral[m] += np.sum(sel < 0, axis=0)
            elif var == "tmax":
                umbral[m] += np.sum(sel > 30, axis=0)
        visto.add(anio); f.close()
        print(f"  {var} {anio}", flush=True)
    faltan = sorted(set(ANIOS) - visto)
    if faltan:
        raise SystemExit(f"Faltan años de {var}: {faltan}")
    n = len(visto)
    with np.errstate(invalid="ignore", divide="ignore"):
        if var == "pcp":                                  # acumulado medio del mes
            media = suma / dias * (dias / n)
        else:
            media = suma / dias
        frac = umbral / n                                 # días por mes y año
    media[dias == 0] = np.nan; frac[dias == 0] = np.nan
    return media, frac


# ---------------------------------------------------------------- principal
def main():
    meta = json.loads((WEB / "leon.json").read_text())
    M = meta["meta"]
    x0, y1, ancho, alto, celda = M["x0"], M["y1"], M["ancho"], M["alto"], M["celda"]
    nx, ny = ancho // PASO, alto // PASO

    # relieve del visor (100 m) y altitud media de cada píxel de 1 km
    px = np.asarray(Image.open(WEB / "relieve.png").convert("RGB"), dtype=np.float64)
    H = (px[..., 0] * 65536 + px[..., 1] * 256 + px[..., 2]) / 10 - 10000
    f = PASO // celda
    H1 = H[: ny * f, : nx * f].reshape(ny, f, nx, f).mean(axis=(1, 3))

    # máscara de la provincia a 1 km
    im = Image.new("L", (nx, ny), 0); dr = ImageDraw.Draw(im)
    for r in meta["provincia"]:
        dr.polygon([(r[k] / PASO, r[k + 1] / PASO) for k in range(0, len(r), 2)], fill=255)
    prov = np.asarray(im) > 127

    # rejilla de AEMET: coordenadas rotadas y ventana que cubre el visor
    with tarfile.open(next(RAW.glob("Serie_AEMET_v2_pcp_*_netcdf.tar.gz"))) as tf:
        m = next(x for x in tf.getmembers() if x.name.endswith(".nc"))
        g = netcdf_file(io.BytesIO(tf.extractfile(m).read()), mmap=False)
        rlon = np.array(g.variables["rlon"][:]); rlat = np.array(g.variables["rlat"][:]); g.close()
    dl = rlon[1] - rlon[0]

    def indices(E, N):
        la, lo = utm_a_latlon(E, N)
        ra, ro = a_rotadas(la, lo)
        return (ro - rlon[0]) / dl, (ra - rlat[0]) / dl     # índices fraccionarios (columna, fila)

    Ec = x0 + PASO / 2 + np.arange(nx) * PASO; Nc = y1 - PASO / 2 - np.arange(ny) * PASO
    EE, NN = np.meshgrid(Ec, Nc)
    fi, fj = indices(EE, NN)
    i0, i1 = int(np.floor(fi.min())) - 2, int(np.ceil(fi.max())) + 3
    j0, j1 = int(np.floor(fj.min())) - 2, int(np.ceil(fj.max())) + 3
    ventana = (j0, j1, i0, i1)
    print(f"Ventana AEMET: filas {j0}-{j1}, columnas {i0}-{i1}")

    # altitud media de cada celda de 5 km según el MDT del visor (100 m)
    Eh = x0 + celda / 2 + np.arange(H.shape[1]) * celda; Nh = y1 - celda / 2 - np.arange(H.shape[0]) * celda
    hi, hj = indices(*np.meshgrid(Eh, Nh))
    ci = np.rint(hi).astype(int) - i0; cj = np.rint(hj).astype(int) - j0
    ok = (ci >= 0) & (ci < i1 - i0) & (cj >= 0) & (cj < j1 - j0)
    acc = np.zeros((j1 - j0, i1 - i0)); cnt = np.zeros_like(acc)
    np.add.at(acc, (cj[ok], ci[ok]), H[ok]); np.add.at(cnt, (cj[ok], ci[ok]), 1)
    Hc = np.where(cnt > 50, acc / np.maximum(cnt, 1), np.nan)   # solo celdas bien cubiertas por el MDT
    gj, gi = np.mgrid[0:j1 - j0, 0:i1 - i0]

    print("Leyendo precipitación…"); pcp, _ = leer("pcp", ventana)
    print("Leyendo temperatura máxima…"); tmax, calor = leer("tmax", ventana)
    print("Leyendo temperatura mínima…"); tmin, helada = leer("tmin", ventana)
    tmed = (tmax + tmin) / 2

    ndias = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
    VARS = [
        ("tmed", "Temperatura media", "°C", tmed, "media", True),
        ("tmax", "Temperatura máxima media", "°C", tmax, "media", True),
        ("tmin", "Temperatura mínima media", "°C", tmin, "media", True),
        ("prec", "Precipitación", "mm", pcp, "suma", False),
        ("helada", "Días de helada (mínima < 0 °C)", "días", helada, "suma", True),
        ("calor", "Días de calor (máxima > 30 °C)", "días", calor, "suma", True),
    ]

    def bilineal(campo):
        c = campo.copy()
        if np.isnan(c).any():                      # rellenar huecos con la celda válida más cercana
            from scipy.ndimage import distance_transform_edt
            idx = distance_transform_edt(np.isnan(c), return_distances=False, return_indices=True)
            c = c[tuple(idx)]
        x = np.clip(fi - i0, 0, c.shape[1] - 1.001); y = np.clip(fj - j0, 0, c.shape[0] - 1.001)
        xa, ya = np.floor(x).astype(int), np.floor(y).astype(int); tx, ty = x - xa, y - ya
        return ((c[ya, xa] * (1 - tx) + c[ya, xa + 1] * tx) * (1 - ty) + (c[ya + 1, xa] * (1 - tx) + c[ya + 1, xa + 1] * tx) * ty)

    atlas = np.zeros((len(VARS) * ny, 13 * nx), dtype=np.uint16)
    salida = {"fuente": "AEMET, rejilla diaria de 5 km ROCIO_IBEB (precipitación v2, temperaturas v1): normales 1991-2020 calculadas para el visor, "
                        "ajustadas a la altitud del MDT del IGN con el gradiente de cada mes",
              "periodo": "1991-2020", "paso": PASO, "nx": nx, "ny": ny, "variables": []}
    for fila, (vid, nombre, unidad, datos, agg, con_alt) in enumerate(VARS):
        rejillas = []
        for k in range(13):
            campo = (datos.mean(axis=0) if agg == "media" else datos.sum(axis=0)) if k == 12 else datos[k]
            b = 0.0
            if con_alt:
                sel = np.isfinite(campo) & np.isfinite(Hc)
                X = np.column_stack([np.ones(sel.sum()), Hc[sel], gi[sel], gj[sel]])
                b = float(np.linalg.lstsq(X, campo[sel], rcond=None)[0][1])
            ref = campo - b * np.nan_to_num(Hc, nan=np.nanmean(Hc))
            ref1 = bilineal(ref)
            v1 = ref1 + b * H1
            tope = (ndias.sum() if k == 12 else ndias[k]) if unidad == "días" else None
            if tope:
                v1 = np.clip(v1, 0, tope)
            if unidad == "mm":
                v1 = np.maximum(v1, 0)
            lo, hi = float(ref1.min()), float(ref1.max())
            if hi - lo < 1e-6:
                hi = lo + 1
            q = np.rint((ref1 - lo) / (hi - lo) * 65535).astype(np.uint16)
            atlas[fila * ny:(fila + 1) * ny, k * nx:(k + 1) * nx] = q
            pv = v1[prov]
            rejillas.append({"min": round(lo, 4), "max": round(hi, 4), "b": round(b, 7),
                             "pmin": round(float(np.percentile(pv, 0.5)), 2), "pmax": round(float(np.percentile(pv, 99.5)), 2),
                             "media": round(float(pv.mean()), 2), "tope": tope})
            if k in (0, 6, 12):
                print(f"  {vid} {'ene' if k == 0 else 'jul' if k == 6 else 'año'}: provincia {rejillas[-1]['pmin']}–{rejillas[-1]['pmax']} {unidad}, "
                      f"media {rejillas[-1]['media']}, gradiente {b * 100:.3f} {unidad}/100 m")
        salida["variables"].append({"id": vid, "nombre": nombre, "unidad": unidad, "agregado": agg, "rejillas": rejillas})

    rgb = np.zeros(atlas.shape + (3,), dtype=np.uint8)
    rgb[..., 0] = atlas >> 8; rgb[..., 1] = atlas & 255
    Image.fromarray(rgb, "RGB").save(WEB / "clima.png", optimize=True)
    (WEB / "clima.json").write_text(json.dumps(salida, ensure_ascii=False))
    print("Escrito", WEB / "clima.png", rgb.shape, "y clima.json")

    # comprobación en tres puntos conocidos
    for nom, E, N in [("León", 290000, 4719000), ("Riaño", 330400, 4761000), ("Ponferrada", 202000, 4718000)]:
        c, r = int((E - x0) / PASO), int((y1 - N) / PASO)
        vals = []
        for vid, *_ in VARS:
            v = next(x for x in salida["variables"] if x["id"] == vid)["rejillas"][12]
            q = atlas[[x["id"] for x in salida["variables"]].index(vid) * ny + r, 12 * nx + c]
            vals.append(f"{vid}={v['min'] + q / 65535 * (v['max'] - v['min']) + v['b'] * H1[r, c]:.1f}")
        print(f"  {nom} ({H1[r, c]:.0f} m): " + ", ".join(vals))


if __name__ == "__main__":
    main()
