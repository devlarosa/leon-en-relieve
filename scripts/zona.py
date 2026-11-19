"""Zona con la que trabajan los scripts de datos: la variable de entorno ZONA (por defecto «leon»).

Su ficha está en web/zonas.json; sus datos de partida en raw/<zona>/ y los generados en web/data/<zona>/.
    ZONA=picos python3 scripts/ine_poblacion.py raw/picos/poblacion_ine_2025.csv
"""
import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_FICHAS = json.loads((RAIZ / "web" / "zonas.json").read_text(encoding="utf-8"))
ZONA = os.environ.get("ZONA", "leon")
if ZONA not in _FICHAS or ZONA.startswith("_"):
    raise SystemExit(f"Zona desconocida: {ZONA!r} (están {', '.join(k for k in _FICHAS if not k.startswith('_'))})")
FICHA = _FICHAS[ZONA]
RAW = RAIZ / "raw" / ZONA
DATA = RAIZ / "web" / "data" / ZONA
# provincias del INE: código -> (comunidad autónoma en el Nomenclátor, tabla del Padrón por municipios y sexo, nombre)
PROVINCIAS_INE = {"24": ("7", 2877, "León"), "33": ("3", 2886, "Asturias"), "39": ("6", 2893, "Cantabria")}
_m = FICHA.get("municipios", {})
MUNICIPIOS = _m.get("lista")                    # {código INE: nombre} o None si es una provincia entera
PROVINCIAS = sorted({c[:2] for c in MUNICIPIOS}) if MUNICIPIOS else [_m["provincia"]]


def es_de_la_zona(codigo):
    """¿El municipio (código INE de 5 cifras) entra en la zona?"""
    return codigo in MUNICIPIOS if MUNICIPIOS else codigo[:2] in PROVINCIAS
