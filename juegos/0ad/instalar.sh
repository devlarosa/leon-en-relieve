#!/bin/bash
# Copia el mapa de León a la carpeta de usuario de 0 A.D. (Flatpak o instalación normal).
# El juego carga esa carpeta siempre, sin activar ningún mod.
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
for base in "$HOME/.var/app/com.play0ad.zeroad/data/0ad/mods/user" "${XDG_DATA_HOME:-$HOME/.local/share}/0ad/mods/user"; do
    if [ -d "$(dirname "$base")" ] || [[ "$base" == *com.play0ad.zeroad* && -d "$HOME/.var/app/com.play0ad.zeroad" ]]; then
        mkdir -p "$base" && cp -r "$DIR/user/." "$base/" && echo "Instalado en $base"
    fi
done
