#!/usr/bin/env bash
# Descarga los datos de partida de una zona en raw/<zona>/ desde los servicios oficiales (IGN e INE).
#   ZONA=picos scripts/descargar_datos.sh      (por defecto, ZONA=leon; las zonas están en web/zonas.json)
# Se puede relanzar: salta lo que ya está descargado y completo.
# Los servidores del IGN fallan a menudo (502, respuestas cortadas): el script reintenta.
set -uo pipefail
cd "$(dirname "$0")/.."
export ZONA="${ZONA:-leon}"
ficha() { python3 -c "import json,sys; f=json.load(open('web/zonas.json'))['$ZONA']; v=eval(sys.argv[1]); print(v if not isinstance(v, list) else ' '.join(map(str, v)))" "$1"; }
ficha "f['nombre']" > /dev/null || { echo "Zona desconocida: $ZONA" >&2; exit 1; }
R="raw/$ZONA"
mkdir -p $R/{mdt25,rios,ngbe,carreteras,aguas_api,historico,rejilla,nomenclator}
UA="Mozilla/5.0 (compatible; leon3d-datos/1.0)"
read X0 Y0 X1 Y1 <<< "$(ficha "f['extension']")"
read LA0 LO0 LA1 LO1 <<< "$(ficha "f['bbox']")"
ENV="<gml:Envelope srsName=\"urn:ogc:def:crs:EPSG::4258\"><gml:lowerCorner>$LA0 $LO0</gml:lowerCorner><gml:upperCorner>$LA1 $LO1</gml:upperCorner></gml:Envelope>"
echo "Zona: $(ficha "f['nombre']") ($ZONA) · mapa $X0 $Y0 $X1 $Y1 (EPSG:25830)"

completo() {  # fichero GML/XML que termina bien
  [ -s "$1" ] && tail -c 64 "$1" | grep -q "FeatureCollection>"
}
bajar() {     # bajar URL fichero [comprobación]
  local url="$1" out="$2" check="${3:-}"
  for i in 1 2 3 4 5 6; do
    if curl -sfL -m 600 -A "$UA" "$url" -o "$out" && [ -s "$out" ]; then   # -L: sigue redirecciones (GitHub); -f: falla con errores HTTP
      if [ -z "$check" ] || $check "$out"; then echo "  ok $out"; return 0; fi
    fi
    echo "  reintento $i: $out"; sleep $((i * 6))
  done
  echo "  FALLO: $out" >&2; return 1
}
wfs_filtro() {  # servicio tipo filtro_xml salida [count] [startIndex]
  local url="$1" tipo="$2" filtro="$3" out="$4" n="${5:-20000}" s="${6:-0}"
  completo "$out" && { echo "  ya está $out"; return 0; }
  for i in 1 2 3 4 5 6; do
    curl -s -m 600 -A "$UA" -G "$url" --data-urlencode "service=WFS" --data-urlencode "version=2.0.0" \
      --data-urlencode "request=GetFeature" --data-urlencode "typeNames=$tipo" --data-urlencode "count=$n" --data-urlencode "startIndex=$s" \
      --data-urlencode "filter=$filtro" -o "$out" && completo "$out" && { echo "  ok $out"; return 0; }
    echo "  reintento $i: $out"; sleep $((i * 6))
  done
  echo "  FALLO: $out" >&2; return 1
}

echo "1/9 Límites administrativos (IGN, unidades administrativas INSPIRE) y contorno de la zona"
completo $R/au_units.gml || bajar "https://www.ign.es/wfs-inspire/unidades-administrativas?service=WFS&version=2.0.0&request=GetFeature&typeNames=au:AdministrativeUnit&bbox=$LA0,$LO0,$LA1,$LO1,urn:ogc:def:crs:EPSG::4258&count=5000" $R/au_units.gml completo
[ -s $R/municipios.gpkg ] || Rscript R/03_admin.R || exit 1

echo "2/9 Relieve: MDT25 del IGN (WCS), en mosaicos de hasta 32 km"
if ls $R/mdt25/*.tif > /dev/null 2>&1; then echo "  ya está $R/mdt25"; else
  for ((x = X0; x < X1; x += 32000)); do for ((y = Y0; y < Y1; y += 32000)); do
    xe=$((x + 32000 > X1 ? X1 : x + 32000)); ye=$((y + 32000 > Y1 ? Y1 : y + 32000))
    bajar "https://servicios.idee.es/wcs-inspire/mdt?service=WCS&version=2.0.1&request=GetCoverage&CoverageId=Elevacion25830_25&subset=x($x,$xe)&subset=y($y,$ye)&format=image/tiff" "$R/mdt25/t_${x}_${y}.tif"
  done; done
fi

echo "3/9 Ríos con nombre (IGN, hidrografía INSPIRE), por páginas de 1.500"
FRIOS="<fes:Filter xmlns:fes=\"http://www.opengis.net/fes/2.0\" xmlns:hy-p=\"http://inspire.ec.europa.eu/schemas/hy-p/4.0\" xmlns:gn=\"http://inspire.ec.europa.eu/schemas/gn/4.0\" xmlns:gml=\"http://www.opengis.net/gml/3.2\"><fes:And><fes:BBOX><fes:ValueReference>hy-p:geometry</fes:ValueReference>$ENV</fes:BBOX><fes:PropertyIsLike wildCard=\"*\" singleChar=\".\" escapeChar=\"!\"><fes:ValueReference>hy-p:geographicalName/gn:GeographicalName/gn:spelling/gn:SpellingOfName/gn:text</fes:ValueReference><fes:Literal>Río *</fes:Literal></fes:PropertyIsLike></fes:And></fes:Filter>"
for ((s = 0; s <= 30000; s += 1500)); do
  f=$R/rios/q_$s.gml
  wfs_filtro "https://servicios.idee.es/wfs-inspire/hidrografia" "hy-p:Watercourse" "$FRIOS" "$f" 1500 "$s" || break
  [ "$(grep -c "<wfs:member>" "$f")" -lt 1500 ] && break      # última página
done

echo "4/9 Nomenclátor Geográfico Básico (IGN): poblaciones y orografía"
for T in "Capital de provincia" "Capital de municipio" "Entidad singular" "Núcleos de población" "Capital de EATIM" "Entidad menor de población" "Montaña" "Alineación montañosa" "Depresión" "Paso de montaña" "Comarca geográfica"; do
  F="<fes:Filter xmlns:fes=\"http://www.opengis.net/fes/2.0\" xmlns:gn=\"http://inspire.ec.europa.eu/schemas/gn/4.0\" xmlns:gmd=\"http://www.isotc211.org/2005/gmd\" xmlns:gml=\"http://www.opengis.net/gml/3.2\"><fes:And><fes:BBOX><fes:ValueReference>gn:geometry</fes:ValueReference>$ENV</fes:BBOX><fes:PropertyIsEqualTo><fes:ValueReference>gn:localType/gmd:LocalisedCharacterString</fes:ValueReference><fes:Literal>$T</fes:Literal></fes:PropertyIsEqualTo></fes:And></fes:Filter>"
  wfs_filtro "https://www.ign.es/wfs-inspire/ngbe" "gn:NamedPlace" "$F" "$R/ngbe/$(echo "$T" | tr ' ' '_').gml"
done

echo "5/9 Lagos y embalses, carreteras por clase funcional (IGN, OGC API Features de la IDEE)"
[ -s $R/aguas_api/standingwater.geojson ] || python3 -I scripts/fetch_ogcapi.py standingwater $R/aguas_api/standingwater.geojson
for c in $(ficha "f.get('procesado', {}).get('carreteras', ['mainRoad', 'firstClass', 'secondClass'])"); do
  [ -s $R/carreteras/$c.geojson ] || python3 -I scripts/fetch_ogcapi.py roadlink $R/carreteras/$c.geojson functionalclass=$c
done

echo "6/9 Población (INE): Padrón municipal y Nomenclátor de cada pueblo"
[ -s $R/poblacion_ine_2025.csv ] || python3 -I scripts/ine_poblacion.py $R/poblacion_ine_2025.csv
[ -s $R/nomenclator/entidades_ine.csv ] || python3 -I scripts/ine_nomenclator.py 2025 $R/nomenclator/entidades_ine.csv

if [ "$(ficha "f.get('procesado', {}).get('comarcas', 'agrarias')")" = "agrarias" ]; then
  echo "7/9 Comarcas: agrarias (MAPA, copia del shapefile oficial en rOpenSpain/mapSpain) y tradicionales (Wikidata + Wikipedia, no oficiales)"
  mkdir -p $R/comarcas $R/comarcas_agrarias
  [ -s $R/comarcas/comarca_wikipedia.json ] || python3 -I scripts/comarcas_wikipedia.py $R/comarcas/comarca_wikipedia.json
  [ -s $R/comarcas_agrarias/comarcas_agrarias.gpkg ] || bajar "https://github.com/rOpenSpain/mapSpain/raw/sianedata/MITECO/dist/comarcas_agrarias.gpkg" $R/comarcas_agrarias/comarcas_agrarias.gpkg
else
  echo "7/9 Comarcas: las provincias (no hace falta descargar nada más)"
fi

echo "8/9 Población del Censo 2021 en celdas de 1 km² (INE, rejilla europea)"
[ -s $R/rejilla/Poblacion_Rejilla_Europea.csv ] || bajar "https://www.ine.es/censos2021/Poblacion_Rejilla_Europea.csv" $R/rejilla/Poblacion_Rejilla_Europea.csv

echo "9/9 Población histórica (INE, censos desde 1900; tarda unos minutos)"
[ -s $R/historico/censos.json ] || python3 -I scripts/ine_censos.py $R/poblacion_ine_2025.csv $R/historico/censos.json

echo "Hecho. Siguiente paso (con ZONA=$ZONA): Rscript R/10_preparar_web.R && Rscript R/11_rejilla_poblacion.R && Rscript R/12_cobertura_copernicus.R && Rscript scripts/cumbres.R"
