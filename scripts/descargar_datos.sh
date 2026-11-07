#!/usr/bin/env bash
# Descarga todos los datos de partida en raw/ desde los servicios oficiales.
# Se puede relanzar: salta lo que ya está descargado y completo.
# Los servidores del IGN fallan a menudo (502, respuestas cortadas): el script reintenta.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p raw/{mdt25,rios,ngbe,carreteras,aguas_api,comarcas,historico}

UA="Mozilla/5.0 (compatible; leon3d-datos/1.0)"
BBOX_LATLON="41.95,-7.15,43.30,-4.65,urn:ogc:def:crs:EPSG::4258"   # WFS 2.0 en EPSG:4258 (lat,lon)

completo() {  # fichero GML/XML que termina bien
  [ -s "$1" ] && tail -c 64 "$1" | grep -q "FeatureCollection>"
}
bajar() {     # bajar URL fichero [comprobación]
  local url="$1" out="$2" check="${3:-}"
  for i in 1 2 3 4 5 6; do
    if curl -s -m 600 -A "$UA" "$url" -o "$out"; then
      if [ -z "$check" ] || $check "$out"; then echo "  ok $out"; return 0; fi
    fi
    echo "  reintento $i: $out"; sleep $((i * 6))
  done
  echo "  FALLO: $out" >&2; return 1
}
wfs_filtro() {  # servicio tipo filtro_xml salida
  local url="$1" tipo="$2" filtro="$3" out="$4"
  completo "$out" && { echo "  ya está $out"; return 0; }
  for i in 1 2 3 4 5 6; do
    curl -s -m 600 -A "$UA" -G "$url" --data-urlencode "service=WFS" --data-urlencode "version=2.0.0" \
      --data-urlencode "request=GetFeature" --data-urlencode "typeNames=$tipo" --data-urlencode "count=20000" \
      --data-urlencode "filter=$filtro" -o "$out" && completo "$out" && { echo "  ok $out"; return 0; }
    echo "  reintento $i: $out"; sleep $((i * 6))
  done
  echo "  FALLO: $out" >&2; return 1
}

echo "1/9 Límites administrativos (IGN, unidades administrativas INSPIRE)"
completo raw/au_units.gml || bajar "https://www.ign.es/wfs-inspire/unidades-administrativas?service=WFS&version=2.0.0&request=GetFeature&typeNames=au:AdministrativeUnit&bbox=$BBOX_LATLON&count=5000" raw/au_units.gml completo

echo "2/9 Relieve: MDT25 del IGN (WCS), 12 mosaicos en ETRS89 / UTM 30N"
X0=164000; Y0=4655000; W=49000; H=45000
for cx in 0 1 2 3; do for cy in 0 1 2; do
  f=raw/mdt25/t_${cx}_${cy}.tif; [ -s "$f" ] && continue
  x1=$((X0 + cx * W)); y1=$((Y0 + cy * H))
  bajar "https://servicios.idee.es/wcs-inspire/mdt?service=WCS&version=2.0.1&request=GetCoverage&CoverageId=Elevacion25830_25&subset=x($x1,$((x1 + W)))&subset=y($y1,$((y1 + H)))&format=image/tiff" "$f"
done; done

echo "3/9 Ríos con nombre (IGN, hidrografía INSPIRE)"
FRIOS='<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" xmlns:hy-p="http://inspire.ec.europa.eu/schemas/hy-p/4.0" xmlns:gn="http://inspire.ec.europa.eu/schemas/gn/4.0" xmlns:gml="http://www.opengis.net/gml/3.2"><fes:And><fes:BBOX><fes:ValueReference>hy-p:geometry</fes:ValueReference><gml:Envelope srsName="urn:ogc:def:crs:EPSG::4258"><gml:lowerCorner>41.95 -7.15</gml:lowerCorner><gml:upperCorner>43.30 -4.65</gml:upperCorner></gml:Envelope></fes:BBOX><fes:PropertyIsLike wildCard="*" singleChar="." escapeChar="!"><fes:ValueReference>hy-p:geographicalName/gn:GeographicalName/gn:spelling/gn:SpellingOfName/gn:text</fes:ValueReference><fes:Literal>Río *</fes:Literal></fes:PropertyIsLike></fes:And></fes:Filter>'
for s in 0 1500 3000 4500 6000 7500 9000; do
  f=raw/rios/q_$s.gml; completo "$f" && continue
  for i in 1 2 3 4 5 6; do
    curl -s -m 600 -A "$UA" -G "https://servicios.idee.es/wfs-inspire/hidrografia" --data-urlencode "service=WFS" \
      --data-urlencode "version=2.0.0" --data-urlencode "request=GetFeature" --data-urlencode "typeNames=hy-p:Watercourse" \
      --data-urlencode "count=1500" --data-urlencode "startIndex=$s" --data-urlencode "filter=$FRIOS" -o "$f" && completo "$f" && break
    echo "  reintento $i: $f"; sleep $((i * 6))
  done
done

echo "4/9 Nomenclátor Geográfico Básico (IGN): poblaciones y orografía"
for T in "Capital de provincia" "Capital de municipio" "Entidad singular" "Montaña" "Alineación montañosa" "Depresión" "Paso de montaña" "Comarca geográfica"; do
  F="<fes:Filter xmlns:fes=\"http://www.opengis.net/fes/2.0\" xmlns:gn=\"http://inspire.ec.europa.eu/schemas/gn/4.0\" xmlns:gmd=\"http://www.isotc211.org/2005/gmd\" xmlns:gml=\"http://www.opengis.net/gml/3.2\"><fes:And><fes:BBOX><fes:ValueReference>gn:geometry</fes:ValueReference><gml:Envelope srsName=\"urn:ogc:def:crs:EPSG::4258\"><gml:lowerCorner>41.95 -7.15</gml:lowerCorner><gml:upperCorner>43.30 -4.65</gml:upperCorner></gml:Envelope></fes:BBOX><fes:PropertyIsEqualTo><fes:ValueReference>gn:localType/gmd:LocalisedCharacterString</fes:ValueReference><fes:Literal>$T</fes:Literal></fes:PropertyIsEqualTo></fes:And></fes:Filter>"
  wfs_filtro "https://www.ign.es/wfs-inspire/ngbe" "gn:NamedPlace" "$F" "raw/ngbe/$(echo "$T" | tr ' ' '_').gml"
done

echo "5/9 Embalses y lagos (IGN, OGC API Features de la IDEE)"
[ -s raw/aguas_api/standingwater.geojson ] || python3 -I scripts/fetch_ogcapi.py standingwater raw/aguas_api/standingwater.geojson

echo "6/9 Carreteras por clase funcional (IGN, OGC API Features de la IDEE)"
for c in mainRoad firstClass secondClass; do
  [ -s raw/carreteras/$c.geojson ] || python3 -I scripts/fetch_ogcapi.py roadlink raw/carreteras/$c.geojson functionalclass=$c
done

echo "7/9 Población (INE, Padrón municipal)"
[ -s raw/poblacion_ine_2025.csv ] || python3 -I scripts/ine_poblacion.py raw/poblacion_ine_2025.csv

echo "8/9 Comarcas tradicionales (Wikidata + Wikipedia, no oficiales)"
[ -s raw/comarcas/comarca_wikipedia.json ] || python3 -I scripts/comarcas_wikipedia.py raw/comarcas/comarca_wikipedia.json

echo "9/9 Población histórica (INE, censos desde 1900; tarda unos minutos)"
[ -s raw/historico/censos.json ] || python3 -I scripts/ine_censos.py raw/poblacion_ine_2025.csv raw/historico/censos.json

echo "Hecho. Siguiente paso: Rscript R/03_admin.R && Rscript R/10_preparar_web.R"
