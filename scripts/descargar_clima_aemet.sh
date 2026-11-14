#!/bin/bash
# Descarga la rejilla diaria de 5 km de AEMET (ROCIO_IBEB) para 1991-2020: precipitación (v2), temperatura máxima y mínima (v1).
# Fuente: https://www.aemet.es/es/serviciosclimaticos/cambio_climat/datos_diarios?w=1  (unos 800 MB; se descarga una vez)
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)/raw/clima_aemet"
B="https://www.aemet.es/documentos/es/serviciosclimaticos/cambio_climat/datos_diarios/dato_observacional/rejilla_5km"
UA="Mozilla/5.0 (compatible; leon3d-datos/1.0)"
mkdir -p "$DIR"
ficheros=()
for p in 1990a1999 2000a2009 2010a2019 2020; do
  ficheros+=("v2/Serie_AEMET_v2_pcp_${p}_netcdf.tar.gz")
  for v in tmax tmin; do ficheros+=("temperatura/v1/$v/Serie_AEMET_v1_${v}_${p}_netcdf.tar.gz"); done
done
for f in "${ficheros[@]}"; do
  out="$DIR/$(basename "$f")"
  if [ -s "$out" ] && gzip -t "$out" 2>/dev/null; then echo "ya está: $(basename "$f")"; continue; fi
  echo "descargando $(basename "$f")"
  curl -fsSL --retry 4 --retry-delay 5 -A "$UA" -o "$out.part" "$B/$f" && mv "$out.part" "$out"
done
# no se descomprimen: scripts/clima_aemet.py lee los .nc directamente de los .tar.gz (descomprimidos ocupan unos 9 GB)
echo "Listo en $DIR"
