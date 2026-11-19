#!/usr/bin/env python3
"""Geología para el visor a partir de los mapas del IGME-CSIC (scripts/geologia_descargar.py).

Salidas
  web/data/geologia.png   a 100 m, alineada con relieve.png: R y G = unidad del MAGNA 1:50.000 (16 bits),
                          B = unidad del Mapa Geológico 1:1.000.000 (+1; 0 = sin dato)
  web/data/permeab.png    a 100 m: R = clase de permeabilidad del Mapa Hidrogeológico 1:200.000 (+1)
  web/data/geologia.json  descripciones, tipo de roca, edades con los colores de la tabla cronoestratigráfica
                          internacional (ICS), clases de permeabilidad y lugares de interés geológico

Tipo de roca: la descripción de cada unidad del MAGNA se clasifica por la primera roca que nombra (las hojas
describen primero la roca dominante); los depósitos cuaternarios se reconocen por sus palabras propias.
"""
import json
import sys
import re
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from zona import ZONA  # noqa: E402  (variable de entorno ZONA; por defecto «leon»)
RAW = RAIZ / "raw" / ZONA / "geologia"
WEB = RAIZ / "web" / "data" / ZONA

# colores oficiales de la Comisión Internacional de Estratigrafía (carta cronoestratigráfica)
ICS = {"RIFEENSE": "#f4a67a", "VENDIENSE": "#feb342", "PROTEROZOICO": "#f73563", "PRECAMBRICO": "#f74370",
       "CAMBRICO": "#7fa056", "ORDOVICICO": "#009270", "ORODVICICO": "#009270", "SILURICO": "#b3e1b6", "DEVONICO": "#cb8c37",
       "CARBONIFERO": "#67a599", "PERMICO": "#f04028", "TRIASICO": "#812b92", "JURASICO": "#34b2c9", "CRETACICO": "#7fc64e",
       "PALEOGENO": "#fd9a52", "NEOGENO": "#ffe619", "CUATERNARIO": "#f9f97f"}
ORDEN_EDAD = list(ICS)
NOMBRE_EDAD = {"RIFEENSE": "Rifeense", "VENDIENSE": "Vendiense", "PROTEROZOICO": "Proterozoico", "PRECAMBRICO": "Precámbrico",
               "CAMBRICO": "Cámbrico", "ORDOVICICO": "Ordovícico", "ORODVICICO": "Ordovícico", "SILURICO": "Silúrico",
               "DEVONICO": "Devónico", "CARBONIFERO": "Carbonífero", "PERMICO": "Pérmico", "TRIASICO": "Triásico",
               "JURASICO": "Jurásico", "CRETACICO": "Cretácico", "PALEOGENO": "Paleógeno", "NEOGENO": "Neógeno", "CUATERNARIO": "Cuaternario"}
MA = {"RIFEENSE": 1000, "VENDIENSE": 635, "PROTEROZOICO": 1000, "PRECAMBRICO": 1000, "CAMBRICO": 539, "ORDOVICICO": 485, "ORODVICICO": 485,
      "SILURICO": 444, "DEVONICO": 419, "CARBONIFERO": 359, "PERMICO": 299, "TRIASICO": 252, "JURASICO": 201, "CRETACICO": 145,
      "PALEOGENO": 66, "NEOGENO": 23, "CUATERNARIO": 2.6}

ROCAS = [  # (id, nombre, color, palabras); el orden decide los empates
    ("cuat", "Depósitos cuaternarios (aluviales, terrazas, glaciares…)", "#e9dcae",
     ["terraza", "aluvia", "aluvion", "coluvi", "glaciar", "morren", "derrubio", "canchal", "deyecc", "fondo de valle", "fondos de valle",
      "llanura de inundacion", "turba", "eluvi", "abanico", "cono", "glacis", "rana", "lacustre", "torrencial", "periglaciar", "till", "bloques y cantos",
      "cuaternario", "holoceno", "pleistoceno", "escombr", "vertedero", "dolina", "descalcificacion", "formas carsticas", "rellenos de",
      "deslizamiento", "solifluxi"]),
    ("gran", "Granitos y rocas plutónicas", "#e58a8a", ["granit", "granod", "tonalit", "diorit", "gabro", "pluton", "leucogran", "monzogran", "sienit", "aplit", "pegmatit"]),
    ("volc", "Rocas volcánicas y filones", "#c062a8", ["volcan", "basalt", "riolit", "porfid", "andesit", "dique", "filon", "ofit", "diabas", "lamprof", "tob", "ignimbrit", "vulcanit"]),
    ("meta", "Esquistos, gneises y mármoles", "#9c7fc4", ["esquist", "gneis", "neis", "migmatit", "marmol", "corneana", "anfibolit", "metamorf"]),
    ("carb", "Capas de carbón", "#3d3d46", ["carbon", "hulla", "antracit"]),
    ("cuar", "Cuarcitas", "#f1ece0", ["cuarcita", "cuarzoarenit"]),
    ("cali", "Calizas y dolomías", "#86b9e0", ["caliz", "dolom", "carbonat", "olistolitos calc", "calcare"]),
    ("cong", "Conglomerados y areniscas", "#d6a05c", ["conglomer", "arenisc", "grauvac", "grauwac", "microconglomer", "brecha", "olistolit"]),
    ("piza", "Pizarras y lutitas", "#7b8794", ["pizarr", "lutit", "filit", "ampelit", "argilit", "limolit"]),
    ("arci", "Arcillas, arenas y margas (cuencas terciarias)", "#d9b38c", ["arcill", "arena", "marga", "limo", "grava", "fangos", "yeso", "evapor"]),
]
PERM = [  # las siete clases oficiales del Mapa Hidrogeológico 1:200.000, de más a menos permeable (patrón, nombre corto, color)
    ("carbonatadas de permeabilidad alta", "Calizas muy permeables (acuíferos kársticos)", "#1f5f9e"),
    ("detriticas y cuaternarias de permeabilidad alta", "Gravas y arenas muy permeables", "#3f86c2"),
    ("carbonatadas y volcanicas de permeabilidad media", "Calizas de permeabilidad media", "#6aa6d6"),
    ("detriticas y cuaternarias de permeabilidad media", "Gravas y arenas de permeabilidad media", "#9cc6e4"),
    ("evaporiticas, igneas y metadetriticas de alta", "Mixta: alta en rocas ígneas y metamórficas, baja en detríticas", "#bcd3d6"),
    ("impermeables o de muy baja", "Impermeables o de permeabilidad baja (pizarras, granitos…)", "#efe5cf"),
    ("masa de agua", "Embalses y lagos", "#6cc6cf")]


def norm(t):
    return unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().lower()


def _patron(p):
    """Palabra clave como inicio de palabra; «carbon» no vale para «carbonatado» (eso es caliza)."""
    if p == "carbon":
        return re.compile(r"\bcarbon(?!at)")
    return re.compile(r"\b" + re.escape(p))


PATRONES = [[_patron(p) for p in pals] for (_, _, _, pals) in ROCAS]


def tipo_roca(desc):
    d = norm(desc)
    if any(rx.search(d) for rx in PATRONES[0]):
        return 0
    mejor, pos = None, 10 ** 9
    for i, pats in enumerate(PATRONES[1:], start=1):
        for rx in pats:
            m = rx.search(d)
            if m and m.start() < pos:
                mejor, pos = i, m.start()
    return mejor


def clase_perm(t):
    t = norm(t)
    return next((k for k, (pat, _, _) in enumerate(PERM) if pat in t), None)


TILDES = {"cambrico": "cámbrico", "ordovicico": "ordovícico", "silurico": "silúrico", "devonico": "devónico", "carbonifero": "carbonífero",
          "permico": "pérmico", "triasico": "triásico", "jurasico": "jurásico", "cretacico": "cretácico"}


def tildes(t):
    return re.sub(r"[A-Za-z]+", lambda m: (TILDES[m.group(0).lower()].capitalize() if m.group(0)[0].isupper() else TILDES[m.group(0).lower()])
                  if m.group(0).lower() in TILDES else m.group(0), t)


def mezcla(hexes):
    c = np.mean([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in hexes], axis=0)
    return "#" + "".join(f"{int(round(v)):02x}" for v in c)


def leer(n):
    return [json.loads(l) for l in open(RAW / f"{n}.jsonl", encoding="utf-8")]


def rasterizar(feats, valor, W, R, x0, y1, celda):
    """Pinta polígonos (ETRS89 UTM 30) en una rejilla de celdas de `celda` m; los grandes primero."""
    def area(f):
        return sum(abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(r, r[1:] + r[:1]))) for r in (f["r"] or [])) / 2
    im = Image.new("I", (W, R), 0); dr = ImageDraw.Draw(im)
    for f in sorted(feats, key=area, reverse=True):
        v = valor(f)
        if not v or not f["r"]:
            continue
        for ring in f["r"]:
            if len(ring) >= 3:
                dr.polygon([((x - x0) / celda, (y1 - y) / celda) for x, y in ring], fill=int(v))
    return np.asarray(im, dtype=np.int64)


def main():
    M = json.loads((WEB / "zona.json").read_text())["meta"]
    x0, y1, celda = M["x0"], M["y1"], M["celda"]; W, R = M["ancho"] // celda, M["alto"] // celda

    # --- 1:1.000.000: edad
    g1m = leer("g1m")
    unidades, uid = [], {}
    for f in g1m:
        a = f["a"]; k = a.get("ID")
        if k not in uid:
            sis = (a.get("SISTEMA") or "").strip() or (a.get("EON_ERA") or "").strip()
            partes = [p for p in re.split(r"[-\s]+", norm(sis).upper()) if p in ICS]
            uid[k] = len(unidades)
            unidades.append({"lit": (a.get("LITOGENER") or "").strip(), "dlo": (a.get("DLO") or "").strip(), "era": (a.get("EON_ERA") or "").strip().title(),
                             "sis": " – ".join(NOMBRE_EDAD[p] for p in partes) or sis.title(), "serie": tildes((a.get("SERIE") or "").strip().replace("ORODVICICO", "ORDOVICICO").capitalize()),
                             "color": mezcla([ICS[p] for p in partes]) if partes else "#cccccc", "ma": max((MA[p] for p in partes), default=None),
                             "edad": partes[0] if partes else None})
    g1 = rasterizar(g1m, lambda f: uid[f["a"].get("ID")] + 1, W, R, x0, y1, celda)
    # --- MAGNA 1:50.000: descripción y tipo de roca
    magna = leer("magna")
    descs, did = [], {}
    for f in magna:
        a = f["a"]; k = (a.get("HOJA"), a.get("ID"))
        if k not in did:
            did[k] = len(descs); d = (a.get("DLO") or "").strip()
            descs.append({"d": d[:1].upper() + d[1:].lower() if d.isupper() else d, "h": a.get("HOJA"), "t": tipo_roca(d)})
    mg = rasterizar(magna, lambda f: did[(f["a"].get("HOJA"), f["a"].get("ID"))] + 1, W, R, x0, y1, celda)
    # --- permeabilidad
    hid = leer("hidro")
    pm = rasterizar(hid, lambda f: (clase_perm(f["a"].get("HIDPERM")) + 1) if clase_perm(f["a"].get("HIDPERM")) is not None else 0, W, R, x0, y1, celda)
    # --- lugares de interés geológico
    ligs = []
    for f in leer("lig"):
        a = f["a"]
        if f["p"]:
            x, y = f["p"]
        elif f["r"]:
            pts = np.array([p for r in f["r"] for p in r]); x, y = pts.mean(axis=0)
        else:
            continue
        mx, my = x - x0, y1 - y
        if not (0 <= mx <= M["ancho"] and 0 <= my <= M["alto"]):
            continue
        edad = " – ".join(e for e in [a.get("EdadRasgoInferior"), a.get("EdadRasgoSuperior")] if e and e != "None")
        ligs.append({"c": a.get("CODIGO"), "n": a.get("Denominacion"), "xy": [round(mx), round(my)], "d": a.get("Descripcion"),
                     "i": ", ".join(e.strip(" .") for e in [a.get("InteresPrincipal"), a.get("InteresSecundario")] if e and e != "None"),
                     "u": a.get("UnidadGeotectonica"), "e": edad, "geo": a.get("CodigoGeosite") if a.get("CodigoGeosite") not in (None, "None") else None})

    rgb = np.zeros((R, W, 3), np.uint8)
    rgb[..., 0] = (mg >> 8) & 255; rgb[..., 1] = mg & 255; rgb[..., 2] = np.clip(g1, 0, 255)
    Image.fromarray(rgb, "RGB").save(WEB / "geologia.png", optimize=True)
    p8 = np.zeros((R, W, 3), np.uint8); p8[..., 0] = pm
    Image.fromarray(p8, "RGB").save(WEB / "permeab.png", optimize=True)

    # superficies en la provincia para las leyendas
    prov = Image.new("L", (W, R), 0); dr = ImageDraw.Draw(prov)
    for r in json.loads((WEB / "zona.json").read_text())["provincia"]:
        dr.polygon([(r[k] / celda, r[k + 1] / celda) for k in range(0, len(r), 2)], fill=255)
    pv = np.asarray(prov) > 127; km2 = (celda / 1000) ** 2
    tipos = np.array([d["t"] if d["t"] is not None else -1 for d in descs])
    t_cel = np.where(mg > 0, tipos[np.maximum(mg - 1, 0)], -1)
    area_roca = Counter(t_cel[pv].tolist()); area_edad = Counter(g1[pv].tolist()); area_perm = Counter(pm[pv].tolist())
    # edades para la leyenda: se agrupan las unidades con el mismo periodo y serie
    edades, eid = [], {}
    for k, u in enumerate(unidades):
        nombre = (u["sis"] or "Sin edad asignada") + (" · " + u["serie"] if u["serie"] and len(u["serie"]) < 32 else "")
        if nombre not in eid:
            eid[nombre] = len(edades); edades.append({"n": nombre, "color": u["color"], "ma": u["ma"], "km2": 0})
        u["e"] = eid[nombre]; edades[eid[nombre]]["km2"] += round(area_edad.get(k + 1, 0) * km2)
    out = {"fuente": "IGME-CSIC: Mapa Geológico de España 1:1.000.000, MAGNA 1:50.000, Mapa Hidrogeológico 1:200.000 e "
                     "Inventario Español de Lugares de Interés Geológico (servicios de mapas.igme.es); edades con los colores de la "
                     "Comisión Internacional de Estratigrafía",
           "rocas": [{"id": i, "n": n, "color": c, "km2": round(area_roca.get(k, 0) * km2)} for k, (i, n, c, _) in enumerate(ROCAS)],
           "unidades": [dict(u, km2=round(area_edad.get(k + 1, 0) * km2)) for k, u in enumerate(unidades)], "edades": edades,
           "perm": [{"n": n, "color": c, "km2": round(area_perm.get(k + 1, 0) * km2)} for k, (_, n, c) in enumerate(PERM)],
           "descs": [[d["d"], d["t"] if d["t"] is not None else -1, d["h"]] for d in descs], "ligs": ligs}
    (WEB / "geologia.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    sin = sum(1 for d in descs if d["t"] is None)
    print(f"Unidades 1:1M: {len(unidades)} · descripciones MAGNA: {len(descs)} (sin clasificar: {sin}) · LIG: {len(ligs)}")
    print("Rocas en la provincia (km²):", {ROCAS[k][0]: round(v * km2) for k, v in sorted(area_roca.items()) if k >= 0}, "sin dato:", round(area_roca.get(-1, 0) * km2))
    print("Edades:", sorted(((u["sis"], round(area_edad.get(k + 1, 0) * km2)) for k, u in enumerate(unidades)), key=lambda x: -x[1])[:12])
    print("Permeabilidad:", {PERM[k - 1][1]: round(v * km2) for k, v in sorted(area_perm.items()) if k > 0}, "sin dato:", round(area_perm.get(0, 0) * km2))
    if sin:
        print("Ejemplos sin clasificar:", [d["d"] for d in descs if d["t"] is None][:8])
    print("Escrito geologia.png, permeab.png y geologia.json", round((WEB / "geologia.json").stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
