#!/bin/bash
# Abre el visor "León en relieve" en local: sirve web/ en http://127.0.0.1:8800 (solo este equipo) y abre el navegador.
# Uso: ./abrir_visor.sh          abre el visor (arranca el servidor si hace falta)
#      ./abrir_visor.sh --parar  detiene el servidor local
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PUERTO=8800
URL="http://127.0.0.1:$PUERTO/index.html"
PIDF="${XDG_RUNTIME_DIR:-/tmp}/leon3d-visor.pid"

en_marcha() { curl -s -o /dev/null -m 1 "http://127.0.0.1:$PUERTO/index.html"; }

if [ "$1" = "--parar" ]; then
    [ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null && rm -f "$PIDF" && echo "Servidor detenido." || echo "No había servidor en marcha."
    exit 0
fi

if [ ! -s "$DIR/web/data/relieve.png" ]; then
    notify-send "León en relieve" "Faltan los datos en web/data. Ejecuta antes scripts/descargar_datos.sh y los scripts de R/." 2>/dev/null
    echo "Faltan los datos en $DIR/web/data"; exit 1
fi

if ! en_marcha; then
    setsid python3 -m http.server "$PUERTO" --bind 127.0.0.1 --directory "$DIR/web" > /dev/null 2>&1 < /dev/null &
    echo $! > "$PIDF"
    for _ in $(seq 1 30); do en_marcha && break; sleep 0.2; done
fi

xdg-open "$URL" > /dev/null 2>&1 || firefox "$URL" &
