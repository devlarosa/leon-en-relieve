#!/usr/bin/env python3
"""Prepara para el visor la red de ríos con sus afluentes, caudales, estaciones de aforo, embalses y cuencas.

Entradas
  raw/rios_red/*.jsonl          red hidrográfica del IGN (scripts/rios_red_descargar.py)
  raw/rios_mapa/                Anuario de Aforos del MITECO 2021-22 (CSV) y listados de situación de estaciones
Salidas
  web/data/rios.json            ríos con nombre (árbol de afluentes), tramos dibujables con caudal, estaciones y embalses
  web/data/cuencas.png          a 100 m, el río de destino de cada celda (16 bits en R y G): sirve para pintar cuencas

Método
  · Árbol: cada tramo del IGN sabe su nodo final; el río de destino de un río es el primer río con nombre que se
    encuentra aguas abajo de su último tramo. Si la red acaba (frontera o mar) se indica el destino por demarcación.
  · Caudal medio por tramo (estimación): Q = a·Lᵇ, con L la longitud de red aguas arriba (todos los cauces del IGN),
    ajustado con las estaciones de aforo; cada tramo se corrige con el cociente observado/estimado de la primera
    estación aguas abajo (o aguas arriba por el cauce principal) y toma de ella el régimen mensual.
  · Cuencas (aproximadas): cada celda de 100 m se asigna al cauce del IGN más cercano y, siguiendo la red, al primer
    río con nombre aguas abajo. La cuenca de un río es la unión de las celdas de él y de todos sus afluentes.
"""
import csv
import io
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

RAIZ = Path(__file__).resolve().parent.parent
RED = RAIZ / "raw" / "rios_red"
AF = RAIZ / "raw" / "rios_mapa"
WEB = RAIZ / "web" / "data"
DESTINO = {"ES020": "el Atlántico (por Portugal)", "ES010": "el océano Atlántico", "ES018": "el mar Cantábrico", "ES017": "el mar Cantábrico"}
CUENCA_AF = {"ES020": "DUERO", "ES010": "MIÑO-SIL", "ES018": "CANTABRICO"}
MESES_HIDRO = ["moct", "mnov", "mdic", "mene", "mfeb", "mmar", "mabr", "mmay", "mjun", "mjul", "mago", "msep"]


def norm(t):
    t = unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def latlon_a_utm30(lat, lon):
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    e2 = f * (2 - f); ep2 = e2 / (1 - e2)
    p = np.radians(lat); l = np.radians(lon + 3)
    N = a / np.sqrt(1 - e2 * np.sin(p) ** 2); T = np.tan(p) ** 2; C = ep2 * np.cos(p) ** 2; A = np.cos(p) * l
    M = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * p - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * np.sin(2 * p)
             + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * np.sin(4 * p) - (35 * e2 ** 3 / 3072) * np.sin(6 * p))
    E = 500000 + k0 * N * (A + (1 - T + C) * A ** 3 / 6 + (5 - 18 * T + T * T + 72 * C - 58 * ep2) * A ** 5 / 120)
    Nn = k0 * (M + N * np.tan(p) * (A * A / 2 + (5 - T + 9 * C + 4 * C * C) * A ** 4 / 24 + (61 - 58 * T + T * T + 600 * C - 330 * ep2) * A ** 6 / 720))
    return E, Nn


def simplificar(pts, tol):
    """Douglas-Peucker sobre una lista de (x, y)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True; pila = [(0, len(pts) - 1)]
    while pila:
        i, j = pila.pop(); (x1, y1), (x2, y2) = pts[i], pts[j]; dx, dy = x2 - x1, y2 - y1; L = math.hypot(dx, dy) or 1e-9
        mejor, k = -1, -1
        for m in range(i + 1, j):
            d = abs(dy * (pts[m][0] - x1) - dx * (pts[m][1] - y1)) / L
            if d > mejor:
                mejor, k = d, m
        if mejor > tol:
            keep[k] = True; pila += [(i, k), (k, j)]
    return [p for p, q in zip(pts, keep) if q]


def titulo(t):
    """«BARRIOS DE LUNA» -> «Barrios de Luna»: mayúscula inicial salvo artículos y preposiciones."""
    menores = {"de", "del", "la", "las", "los", "el", "y", "o", "en", "a"}
    pal = t.strip().lower().split()
    return " ".join(w if (i and w in menores) else w[:1].upper() + w[1:] for i, w in enumerate(pal))


def jsonl(n):
    return [json.loads(l) for l in open(RED / n, encoding="utf-8")]


def csv_latin(p):
    return list(csv.DictReader(io.StringIO(Path(p).read_text(encoding="latin1")), delimiter=";"))


def num(s):
    try:
        return float(str(s).replace(",", "."))
    except (TypeError, ValueError):
        return None


def main():
    M = json.loads((WEB / "leon.json").read_text())["meta"]
    x0, y1, ancho, alto, celda = M["x0"], M["y1"], M["ancho"], M["alto"], M["celda"]

    # ---------------------------------------------------------------- red
    vistos, links = set(), []
    for t in jsonl("tramos.jsonl") + (jsonl("aguas_abajo.jsonl") if (RED / "aguas_abajo.jsonl").exists() else []):
        k = (t["dm"], t["t"])
        if k in vistos or len(t["g"]) < 2:
            continue
        vistos.add(k); links.append(t)
    n = len(links)
    print("Tramos:", n)
    allc = np.array([c for t in links for c in t["g"]], dtype=np.float64)
    E, Nn = latlon_a_utm30(allc[:, 1], allc[:, 0])
    pos = 0
    for t in links:
        k = len(t["g"]); t["xy"] = list(zip((E[pos:pos + k] - x0).tolist(), (y1 - Nn[pos:pos + k]).tolist())); pos += k
    cursos = {(c["dm"], c["c"]): c for c in jsonl("cursos.jsonl")}

    # aguas abajo: un único sucesor por tramo (el del mismo curso si hay varios; si no, el no ficticio)
    salida = defaultdict(list)
    for i, t in enumerate(links):
        salida[(t["dm"], t["i"])].append(i)
    abajo = np.full(n, -1)
    for i, t in enumerate(links):
        cand = [j for j in salida.get((t["dm"], t["f"]), []) if j != i]
        if cand:
            cand.sort(key=lambda j: (links[j]["c"] != t["c"], links[j]["x"]))
            abajo[i] = cand[0]
    # orden topológico (de cabecera a desembocadura) y longitud de red aguas arriba
    entra = np.zeros(n, int)
    for j in abajo[abajo >= 0]:
        entra[j] += 1
    cola = [i for i in range(n) if entra[i] == 0]; orden = []
    while cola:
        i = cola.pop(); orden.append(i); j = abajo[i]
        if j >= 0:
            entra[j] -= 1
            if entra[j] == 0:
                cola.append(j)
    if len(orden) < n:      # bucles (cauces trenzados): se rompen
        resto = [i for i in range(n) if entra[i] > 0]; print("  tramos en bucle:", len(resto))
        for i in resto:
            abajo[i] = -1
        orden += resto
    Lup = np.array([t["l"] / 1000 for t in links])
    for i in orden:
        if abajo[i] >= 0:
            Lup[abajo[i]] += Lup[i]

    dentro = np.array([any(-2000 <= x <= ancho + 2000 and -2000 <= y <= alto + 2000 for x, y in t["xy"]) for t in links])
    nombre = [cursos.get((t["dm"], t["c"]), {}).get("n") for t in links]

    # ---------------------------------------------------------------- ríos con nombre
    por_curso = defaultdict(list)
    for i, t in enumerate(links):
        if nombre[i]:
            por_curso[(t["dm"], t["c"])].append(i)
    rios = {}
    for k, idx in por_curso.items():
        boca = max(idx, key=lambda i: Lup[i])                     # el tramo con más red aguas arriba
        dentro_idx = [i for i in idx if dentro[i]]
        rios[k] = {"k": k, "n": cursos[k]["n"], "dm": k[0], "L": round(cursos[k]["l"] / 1000, 1), "idx": idx, "boca": boca,
                   "Lmax": float(Lup[boca]), "en_mapa": bool(dentro_idx),
                   "Lmapa": float(max(Lup[i] for i in dentro_idx)) if dentro_idx else 0}
    # río de destino: primer río con nombre distinto aguas abajo de la boca
    for r in rios.values():
        j, pasos, padre = abajo[r["boca"]], 0, None
        while j >= 0 and pasos < 100000:
            kk = (links[j]["dm"], links[j]["c"])
            if kk != r["k"] and nombre[j]:
                padre = kk; break
            j = abajo[j]; pasos += 1
        r["padre"] = padre
    # se dibujan los ríos con nombre del mapa con red suficiente aguas arriba; se guardan también sus antepasados
    dibujar = {k for k, r in rios.items() if r["en_mapa"] and (r["Lmapa"] >= 12 or (norm(r["n"]).startswith("rio") and r["Lmapa"] >= 4))}
    guardar = set(dibujar)
    for k in list(dibujar):
        p = rios[k]["padre"]
        while p and p not in guardar:
            guardar.add(p); p = rios[p]["padre"]
    lista = sorted(guardar, key=lambda k: -rios[k]["Lmax"])
    rid = {k: i for i, k in enumerate(lista)}
    print("Ríos con nombre:", len(rios), "· dibujados:", len(dibujar), "· guardados con antepasados:", len(lista))

    # ---------------------------------------------------------------- estaciones de aforo
    def en_zona(x, y):
        return 0 <= x <= ancho and 0 <= y <= alto
    situ = {r["COD_HIDRO"].strip(): r for r in csv_latin(AF / "Situac 4_Rio.csv")}
    estaciones = []
    for dm, carpeta in CUENCA_AF.items():
        if not (AF / carpeta / "estadis_a.csv").exists():
            continue
        stats = {r["indroea"]: r for r in csv_latin(AF / carpeta / "estadis_a.csv")}
        serie = defaultdict(list)
        for r in csv_latin(AF / carpeta / "anual_a.csv"):
            q = num(r["qmedano"])
            if q is not None:
                serie[r["indroea"]].append([int(r["ano_hidr"]), round(q, 2)])
        for r in csv_latin(AF / carpeta / "estaf.csv"):
            c = r["indroea"].strip(); s = stats.get(c); si = situ.get(c, {})
            xs, ys = num(si.get("COORD_UTMX_H30_ETRS89")) or num(r["xetrs89"]), num(si.get("COORD_UTMY_H30_ETRS89")) or num(r["yetrs89"])
            if not s or xs is None or num(s["medano"]) is None:
                continue
            mx, my = xs - x0, y1 - ys
            if not en_zona(mx, my):
                continue
            med = num(s["medano"]); meses = [num(s[m]) or 0 for m in MESES_HIDRO]
            enero_dic = meses[3:] + meses[:3]
            estaciones.append({"c": c, "n": titulo(si.get("NOM_ANUARIO") or r["lugar"]), "rio": (si.get("RIO") or "").strip(), "dm": dm,
                               "xy": [round(mx), round(my)], "q": round(med, 2), "m": [round(v, 2) for v in enero_dic],
                               "q5": num(s["q5"]), "q50": num(s["q50"]), "q95": num(s["q95"]), "a0": int(s["anoini"]), "a1": int(s["anofin"]),
                               "anos": int(s["totanos"]), "A": num(r["suprest"]), "serie": sorted(serie[c]),
                               "emb": "EMBALSE" in r["lugar"].upper()})
    print("Estaciones de aforo en el mapa:", len(estaciones))

    # enganche de cada estación a un tramo: del río con su nombre si está cerca; si no, el tramo con nombre más próximo
    mid = np.array([t["xy"][len(t["xy"]) // 2] for t in links])
    for e in estaciones:
        d = np.hypot(mid[:, 0] - e["xy"][0], mid[:, 1] - e["xy"][1])
        cerca = np.where((d < 2500) & dentro)[0]
        nr = norm(e["rio"])
        mismo = [i for i in cerca if nombre[i] and nr and nr in norm(nombre[i])]
        conn = [i for i in cerca if nombre[i]]
        pool = mismo or [i for i in conn if d[i] < 800] or list(cerca)
        if not pool:
            e["t"] = -1; continue
        # más cerca y, a igualdad, con más cuenca (no un arroyo lateral)
        e["t"] = int(min(pool, key=lambda i: d[i] - min(Lup[i], 400) * 2))
    utiles = [e for e in estaciones if e["t"] >= 0 and e["anos"] >= 6 and e["a1"] >= 1985 and e["q"] > 0]

    # ---------------------------------------------------------------- modelo de caudal Q = a·L^b
    X = np.log([Lup[e["t"]] for e in utiles]); Y = np.log([e["q"] for e in utiles])
    b, a = np.polyfit(X, Y, 1)
    print(f"Caudal ≈ {math.exp(a):.4f}·L^{b:.3f} (L en km de red aguas arriba), {len(utiles)} estaciones")
    qfit = lambda L: math.exp(a) * max(L, 0.1) ** b
    st_en = defaultdict(list)
    for k, e in enumerate(estaciones):
        if e in utiles:
            st_en[e["t"]].append(k)
    # estación de referencia aguas abajo (de la desembocadura hacia la cabecera, en orden topológico inverso)
    ref = np.full(n, -1)
    for i in reversed(orden):
        if st_en.get(i):
            ref[i] = max(st_en[i], key=lambda k: estaciones[k]["anos"])
        elif abajo[i] >= 0 and ref[abajo[i]] >= 0:
            # solo si la estación de abajo no está demasiado lejos en cuenca (factor 6)
            if Lup[estaciones[ref[abajo[i]]]["t"]] <= Lup[i] * 6:
                ref[i] = ref[abajo[i]]
    # también la primera estación aguas arriba por el cauce principal; se queda la más parecida en tamaño de cuenca
    arriba_principal = {}
    for i in orden:
        j = abajo[i]
        if j >= 0 and (j not in arriba_principal or Lup[i] > Lup[arriba_principal[j]]):
            arriba_principal[j] = i
    ref_arriba = np.full(n, -1)
    for i in orden:                      # de cabecera a desembocadura: hereda la del afluente principal
        if st_en.get(i):
            ref_arriba[i] = max(st_en[i], key=lambda k: estaciones[k]["anos"])
        elif i in arriba_principal and ref_arriba[arriba_principal[i]] >= 0:
            ref_arriba[i] = ref_arriba[arriba_principal[i]]
    for i in range(n):
        cands = [k for k in (ref[i], ref_arriba[i]) if k >= 0]
        cands = [k for k in cands if 0.25 <= Lup[estaciones[k]["t"]] / max(Lup[i], 0.1) <= 6]
        ref[i] = min(cands, key=lambda k: abs(math.log(Lup[estaciones[k]["t"]] / max(Lup[i], 0.1)))) if cands else -1
    regimen_dm = {}
    for dm in CUENCA_AF:
        rs = [np.array(e["m"]) / e["q"] for e in utiles if e["dm"] == dm and not e["emb"]]
        regimen_dm[dm] = np.median(rs, axis=0).round(3).tolist() if rs else [1] * 12

    def caudal(i):
        q = qfit(Lup[i])
        if ref[i] >= 0:
            e = estaciones[ref[i]]
            q *= min(3, max(1 / 3, e["q"] / qfit(Lup[e["t"]])))
        return q

    # ---------------------------------------------------------------- tramos dibujables: cadenas del mismo río entre confluencias
    tramos = []
    for k in dibujar:
        r = rios[k]; idx = set(i for i in r["idx"] if dentro[i])
        siguiente = {i: abajo[i] for i in idx if abajo[i] in idx}
        previos = defaultdict(list)
        for i, j in siguiente.items():
            previos[j].append(i)
        cabezas = [i for i in idx if not previos.get(i)]
        hecho = set()
        for h in cabezas:
            cadena, i = [], h
            while i in idx and i not in hecho:
                cadena.append(i); hecho.add(i)
                j = siguiente.get(i)
                # se corta donde entra otro cauce importante (sube mucho la red aguas arriba) para cambiar el grosor
                if j is None or Lup[j] > Lup[i] * 1.25 + 2:
                    if cadena:
                        tramos.append((rid[k], cadena)); cadena = []
                i = j if j is not None else -1
            if cadena:
                tramos.append((rid[k], cadena))
    de_tramo = {i: ti for ti, (_, cadena) in enumerate(tramos) for i in cadena}
    salida_tramos = []
    for r, cadena in tramos:
        pts = []
        for i in cadena:
            g = links[i]["xy"]
            pts += g if not pts else g[1:]
        pts = simplificar(pts, 20.0)
        fin = cadena[-1]
        j, pasos = abajo[fin], 0          # siguiente tramo dibujable aguas abajo (para el recorrido de la gota)
        while j >= 0 and j not in de_tramo and pasos < 5000:
            j = abajo[j]; pasos += 1
        salida_tramos.append({"r": r, "q": round(caudal(fin), 3), "s": int(ref[fin]), "L": round(float(Lup[fin]), 1), "a": de_tramo.get(j, -1) if j >= 0 else -1,
                              "g": [round(v) for p in pts for v in p]})
    print("Tramos dibujables:", len(salida_tramos))

    # caudal de cada río en su punto más bajo dentro del mapa, y estaciones de cada río
    for k in lista:
        r = rios[k]; dentro_idx = [i for i in r["idx"] if dentro[i]]
        r["q"] = round(caudal(max(dentro_idx, key=lambda i: Lup[i])), 2) if dentro_idx else None
    curso_de_tramo = {i: (links[i]["dm"], links[i]["c"]) for i in range(n)}
    for e in estaciones:
        kk = curso_de_tramo.get(e["t"]) if e["t"] >= 0 else None
        # una estación en un arroyo sin nombre cuenta para el primer río con nombre aguas abajo
        j = e["t"]
        while j >= 0 and (curso_de_tramo[j] not in rid):
            j = abajo[j]
        e["r"] = rid.get(curso_de_tramo[j]) if j >= 0 else -1

    # ---------------------------------------------------------------- cuencas: celda → río con nombre de destino
    W, R = ancho // celda, alto // celda
    destino = np.full(n, -1)
    for i in reversed(orden):            # de la desembocadura a la cabecera
        kk = curso_de_tramo[i]
        destino[i] = rid[kk] if kk in rid else (destino[abajo[i]] if abajo[i] >= 0 else -1)
    sem = np.full((R, W), -1, dtype=np.int64)
    for i, t in enumerate(links):
        if not dentro[i] or destino[i] < 0:
            continue
        g = np.array(t["xy"])
        for p0, p1 in zip(g[:-1], g[1:]):
            m = max(2, int(np.hypot(*(p1 - p0)) / 40))
            s = np.linspace(0, 1, m)[:, None] * (p1 - p0) + p0
            cx, cy = (s[:, 0] / celda).astype(int), (s[:, 1] / celda).astype(int)
            ok = (cx >= 0) & (cx < W) & (cy >= 0) & (cy < R)
            sem[cy[ok], cx[ok]] = destino[i]
    _, (iy, ix) = distance_transform_edt(sem < 0, return_indices=True)
    cuenca = sem[iy, ix] + 1                       # 0 = sin río
    rgb = np.zeros((R, W, 3), np.uint8); rgb[..., 0] = cuenca >> 8; rgb[..., 1] = cuenca & 255
    Image.fromarray(rgb, "RGB").save(WEB / "cuencas.png", optimize=True)
    area_mapa = np.bincount(cuenca.ravel(), minlength=len(lista) + 1)[1:] * (celda / 1000) ** 2

    # superficie oficial de la DGA: cuenca con el mismo nombre en la misma demarcación, la de tamaño más parecido
    dga = defaultdict(list)
    for c in jsonl("cuencas.jsonl"):
        if c["n"]:
            dga[(c["dm"], norm(c["n"]))].append(c)
    hijos = defaultdict(list)
    for k in lista:
        if rios[k]["padre"] in rid:
            hijos[rid[rios[k]["padre"]]].append(rid[k])
    area_total = area_mapa.copy()          # superficie en el mapa incluyendo afluentes
    for k in reversed(lista):              # de menor a mayor
        i = rid[k]
        area_total[i] = area_mapa[i] + sum(area_total[h] for h in hijos[i])

    salida_rios = []
    for k in lista:
        r = rios[k]; i = rid[k]
        cand = dga.get((r["dm"], norm(r["n"])), [])
        A = None
        if cand:
            c = min(cand, key=lambda c: abs(math.log(max(c["a"] / 1e6, 0.01) / max(area_total[i], 0.5))))
            if c["a"] / 1e6 >= area_total[i] * 0.6:
                A = round(c["a"] / 1e6, 1)
        salida_rios.append({"n": r["n"], "dm": r["dm"], "p": rid.get(r["padre"], -1),
                            "fin": None if r["padre"] else DESTINO.get(r["dm"], "el mar"),
                            "L": r["L"], "A": A, "Am": round(float(area_total[i]), 1), "q": r["q"], "d": k in dibujar})
    # embalses
    capac = {r["COD_HIDRO"].strip(): r for r in csv_latin(AF / "Situac 2_Embalse.csv")}
    embalses = []
    for dm, carpeta in CUENCA_AF.items():
        if not (AF / carpeta / "embalse.csv").exists():
            continue
        res = defaultdict(lambda: defaultdict(list)); todo = defaultdict(list)
        for r in csv_latin(AF / carpeta / "mensual_e.csv"):
            v = num(r["resmes"]); am = r["anomes"]
            if v is not None and len(am) == 6:
                todo[r["ref_ceh"]].append((int(am), v, num(r["entmes"]), num(r["salmes"])))
                if int(am[:4]) >= 1991:
                    res[r["ref_ceh"]][int(am[4:]) - 1].append(v)
        est_en = {r["ref_ceh"]: r for r in csv_latin(AF / carpeta / "estadis_en.csv")} if (AF / carpeta / "estadis_en.csv").exists() else {}
        est_sa = {r["ref_ceh"]: r for r in csv_latin(AF / carpeta / "estadis_sa.csv")} if (AF / carpeta / "estadis_sa.csv").exists() else {}

        def meses_de(st):          # medias mensuales de la tabla de estadísticas, de octubre-septiembre a enero-diciembre
            if not st:
                return None
            v = [num(st[m]) for m in MESES_HIDRO]
            return [None if x is None else round(x, 1) for x in v[3:] + v[:3]]
        for r in csv_latin(AF / carpeta / "embalse.csv"):
            c = r["ref_ceh"].strip(); si = capac.get(c, {})
            xs, ys = num(si.get("COORD_UTMX_H30_ETRS89")) or num(r["xetrs89"]), num(si.get("COORD_UTMY_H30_ETRS89")) or num(r["yetrs89"])
            if xs is None:
                continue
            mx, my = xs - x0, y1 - ys
            if not en_zona(mx, my):
                continue
            cap = num(si.get("VOLUMEN_E")); medias = [round(float(np.mean(res[c][m])), 1) if res[c][m] else None for m in range(12)]
            serie = sorted(todo[c])
            # reserva media de cada año hidrológico (octubre-septiembre), solo años completos
            por_ano = defaultdict(list)
            for am, v, _, _ in serie:
                y, mth = divmod(am, 100); por_ano[y + 1 if mth >= 10 else y].append(v)
            anual = [[y, round(float(np.mean(v)), 1)] for y, v in sorted(por_ano.items()) if len(v) == 12]
            # el mínimo se busca desde que el embalse supera por primera vez la mitad de su capacidad (se excluye el primer llenado)
            arranque = next((i for i, x in enumerate(serie) if cap and x[1] >= cap / 2), 0)
            mn = min(serie[arranque:], key=lambda x: x[1]) if serie else None; mxr = max(serie, key=lambda x: x[1]) if serie else None
            ultimo = serie[-12:] if len(serie) >= 12 else []
            embalses.append({"c": c, "n": titulo(r["nom_embalse"]), "rio": (si.get("RIO") or "").strip(), "xy": [round(mx), round(my)],
                             "cap": cap, "m": medias, "anos": max((len(v) for v in res[c].values()), default=0),
                             "ent": meses_de(est_en.get(c)), "sal": meses_de(est_sa.get(c)),
                             "entA": num(est_en[c]["medano"]) if c in est_en else None, "salA": num(est_sa[c]["medano"]) if c in est_sa else None,
                             "a0": serie[0][0] // 100 if serie else None, "anual": anual,
                             "min": [mn[1], mn[0]] if mn else None, "max": [mxr[1], mxr[0]] if mxr else None,
                             "ult": [[am, round(v, 1)] for am, v, _, _ in ultimo]})
    print("Embalses:", len(embalses))
    for e in embalses[:25]:
        pm = [round(v / e["cap"] * 100) if v and e["cap"] else None for v in e["m"]]
        print(f"  {e['n']:<32} {e['cap']} hm³ · llenado medio ene {pm[0]} % may {pm[4]} % sep {pm[8]} % · entradas {e['entA']} hm³/año · desde {e['a0']}")

    out = {"fuente": "IGN, red hidrográfica INSPIRE (HY-N) de la IDEE; Dirección General del Agua, cuencas Pfafstetter; "
                     "MITECO, Anuario de Aforos 2021-22 (estaciones de aforo y embalses de las confederaciones del Duero, Miño-Sil y Cantábrico)",
           "modelo": {"a": round(math.exp(a), 5), "b": round(b, 4), "n": len(utiles)},
           "regimen": regimen_dm, "rios": salida_rios, "tramos": salida_tramos,
           "estaciones": [{k: v for k, v in e.items() if k not in ("t", "dm")} for e in estaciones], "embalses": embalses}
    (WEB / "rios.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("Escrito rios.json", round((WEB / "rios.json").stat().st_size / 1e6, 2), "MB y cuencas.png")
    for nom in ["Río Esla", "Río Bernesga", "Río Sil", "Río Porma", "Río Órbigo", "Río Cea"]:
        for r in salida_rios:
            if r["n"] == nom:
                hij = sorted((salida_rios[h]["n"] for h in hijos[salida_rios.index(r)]))[:12]
                print(f"  {nom}: desemboca en {salida_rios[r['p']]['n'] if r['p'] >= 0 else r['fin']}; Q≈{r['q']} m³/s; "
                      f"cuenca DGA {r['A']} km², en mapa {r['Am']} km²; afluentes: {', '.join(hij)}")
                break


if __name__ == "__main__":
    main()
