#!/usr/bin/env bash
# Figuras de protección: descarga en raw/proteccion/ (se puede relanzar: lo ya descargado no se repite).
#  - Junta de Castilla y León (datos abiertos / IDECyL):
#      Red de Espacios Naturales (REN), Red Natura 2000 (ZEC y ZEPA), Bienes de Interés Cultural inmuebles
#    (la REN ya incluye el Parque Nacional de Picos de Europa)
#  - MITECO, Banco de Datos de la Naturaleza: Reservas de la Biosfera (límites y zonificación, OAPN)
# opendata.jcyl.es no envía su certificado intermedio (Sectigo OV R36): se descarga de la dirección que
# indica el propio certificado (AIA), se comprueba con openssl contra las raíces del sistema y se usa
# como cadena adicional. La verificación TLS nunca se desactiva.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
D="$RAIZ/raw/${ZONA:-leon}/proteccion"; mkdir -p "$D"; cd "$D"

baja() {   # baja URL FICHERO [opciones de curl]
  local url="$1" f="$2"; shift 2
  if [ -s "$f" ]; then echo "  ya está: $f"; return; fi
  curl -sfL --retry 3 --max-time 600 "$@" -o "$f.tmp" "$url"
  [ -s "$f.tmp" ] || { echo "vacío: $url" >&2; exit 1; }
  mv "$f.tmp" "$f"; echo "  $f ($(du -h "$f" | cut -f1))"
}

# cadena de certificados para *.jcyl.es
if [ ! -s cadena.pem ]; then
  curl -sf --max-time 60 http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt -o ov_r36.crt
  openssl x509 -inform DER -in ov_r36.crt -out ov_r36.pem
  openssl verify ov_r36.pem >/dev/null || { echo "el intermedio de Sectigo no verifica contra las raíces del sistema" >&2; exit 1; }
  cat /etc/ssl/certs/ca-certificates.crt ov_r36.pem > cadena.pem
fi

M=https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/servicios/banco-datos-naturaleza
FUENTES=$(python3 -c "import json; print(json.load(open('$RAIZ/web/zonas.json'))['${ZONA:-leon}'].get('procesado', {}).get('proteccion', 'cyl'))")
if [ "$FUENTES" = "nacional" ]; then
  # zonas de varias comunidades: capas nacionales del MITECO (sin BIC)
  echo "MITECO (Espacios Naturales Protegidos y Red Natura 2000)"
  baja "$M/enp/Enp2025_geojson.zip" enp2025.zip
  for i in 1 2 3 4 5; do   # el servidor corta a veces la descarga de la Red Natura: se reanuda
    curl -sfL -C - --max-time 900 -o n2000_2025.zip "$M/3-rn2000/n2000_2025_GeoJson.zip" || true
    unzip -tq n2000_2025.zip > /dev/null 2>&1 && break
  done
else
J=https://opendata.jcyl.es/ficheros/carto
echo "Junta de Castilla y León"
baja "$J/medioambiente/espaciosnaturales/en_cyl_ren_limites_gpkg.zip" en_cyl_ren_limites_gpkg.zip --cacert cadena.pem
baja "$J/medioambiente/espaciosnaturales/en_cyl_rednatura2000_zec_gpkg.zip" en_cyl_rednatura2000_zec_gpkg.zip --cacert cadena.pem
baja "$J/medioambiente/espaciosnaturales/en_cyl_rednatura2000_zepa_gpkg.zip" en_cyl_rednatura2000_zepa_gpkg.zip --cacert cadena.pem
baja "$J/cultura/patrimoniocultural/pacu_cyl_bic_inmu_gpkg.zip" pacu_cyl_bic_inmu_gpkg.zip --cacert cadena.pem
fi

echo "MITECO (Reservas de la Biosfera)"
baja "$M/mab/Mab_Limites_OAPN_GeoJson.zip" mab_limites.zip
baja "$M/mab/Mab_Zonif_OAPN_GeoJson.zip" mab_zonif.zip

for z in *.zip; do [ -d "${z%.zip}" ] || unzip -oq "$z" -d "${z%.zip}"; done
echo "Listo. Siguiente paso: Rscript scripts/proteccion.R"
