#!/usr/bin/env python3
"""Prepara el visor para un alojamiento estático (Cloudflare Pages): carpeta publicar/ y publicar.zip.

- index.html envuelto en servidor/app/cabecera.html (app instalable en la pantalla de inicio)
- manifiesto e iconos de servidor/app/
- web/zonas.json y web/data/<zona>/ de cada zona con datos, SIN destacados.json (es la lista privada; en el alojamiento estático los destacados
  son efímeros: cada visitante puede marcar los suyos, pero solo duran la visita)
- version.json con la huella de todo lo publicado, para el botón ↻ del visor
- _headers con cabeceras de seguridad y de caché para Cloudflare Pages

Subida: arrastrar la carpeta publicar/ en el panel de Cloudflare Pages, o
        npx wrangler pages deploy publicar --project-name leon3d
"""
import hashlib
import json
import shutil
import time
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WEB, APP = RAIZ / "web", RAIZ / "servidor" / "app"
OUT = RAIZ / "publicar"
PRIVADOS = {"destacados.json"}
APP_FICHEROS = ["manifest.webmanifest", "icono-180.png", "icono-192.png", "icono-512.png"]
CABECERAS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: same-origin
  X-Frame-Options: SAMEORIGIN
  Permissions-Policy: geolocation=(self), camera=(), microphone=()
/
  Cache-Control: no-cache
/index.html
  Cache-Control: no-cache
/version.json
  Cache-Control: no-store
/data/*
  Cache-Control: public, max-age=3600, must-revalidate
"""


def main():
    zonas = [p.name for p in sorted((WEB / "data").iterdir()) if (p / "zona.json").is_file()]
    if not zonas:
        raise SystemExit("Faltan los datos en web/data/<zona>/: genéralos antes con los scripts (ver README)")
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)
    shutil.copy2(WEB / "zonas.json", OUT / "zonas.json")
    (OUT / "index.html").write_bytes((APP / "cabecera.html").read_bytes() + (WEB / "index.html").read_bytes() + b"\n</body>\n</html>\n")
    for n in APP_FICHEROS:
        shutil.copy2(APP / n, OUT / n)
    for z in zonas:                        # todas las zonas con datos: data/leon/, data/picos/…
        (OUT / "data" / z).mkdir()
        for p in sorted((WEB / "data" / z).iterdir()):
            if p.is_file() and not p.name.startswith(".") and p.name not in PRIVADOS:
                shutil.copy2(p, OUT / "data" / z / p.name)
    print("zonas:", ", ".join(zonas))
    (OUT / "_headers").write_text(CABECERAS, encoding="utf-8")
    h = hashlib.sha1()
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(OUT).as_posix().encode() + b"\0" + hashlib.sha1(p.read_bytes()).digest())
    (OUT / "version.json").write_text(json.dumps({"version": h.hexdigest()[:12], "modificado": int(time.time())}), encoding="utf-8")
    zp = RAIZ / "publicar.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(OUT).as_posix())
    ficheros = [p for p in OUT.rglob("*") if p.is_file()]
    mayor = max(ficheros, key=lambda p: p.stat().st_size)
    print(f"publicar/: {len(ficheros)} ficheros, {sum(p.stat().st_size for p in ficheros) / 1e6:.1f} MB "
          f"(el mayor, {mayor.name}: {mayor.stat().st_size / 1e6:.1f} MB; límite de Pages: 25 MB por fichero)")
    print(f"publicar.zip: {zp.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
