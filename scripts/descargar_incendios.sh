#!/usr/bin/env bash
# Superficies quemadas (perímetros de incendios) de EFFIS, el Sistema Europeo de Información sobre Incendios
# Forestales del programa Copernicus (JRC, Comisión Europea), para el entorno de la provincia de León.
# Capa modis.ba.poly del WFS de EFFIS: todos los incendios cartografiados desde 2016 (unas 30 ha o más),
# con fechas, municipio de origen, superficie y cubierta del suelo quemada. Salida: raw/incendios/effis_ba.json
# Se vuelve a descargar siempre: el año en curso se actualiza durante la campaña.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
D="$RAIZ/raw/incendios"; mkdir -p "$D"; cd "$D"
URL="https://maps.effis.emergency.copernicus.eu/effis?service=WFS&version=1.1.0&request=GetFeature&typename=ms:modis.ba.poly&srsName=EPSG:4326&bbox=41.9,-7.2,43.35,-4.5,EPSG:4326&outputformat=geojson"
curl -sfL --retry 3 --max-time 900 -o effis_ba.json.tmp "$URL"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d.get('features'), 'sin incendios'; print(len(d['features']), 'perímetros')" effis_ba.json.tmp
mv effis_ba.json.tmp effis_ba.json
echo "Listo. Siguiente paso: Rscript scripts/incendios.R"
