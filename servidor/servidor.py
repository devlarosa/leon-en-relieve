#!/usr/bin/env python3
"""Sirve el visor «León en relieve» como aplicación web instalable (pantalla de inicio del iPhone).

- web/index.html se entrega envuelto en app/cabecera.html (doctype, viewport, manifiesto e icono),
  así el mismo index.html sigue valiendo para el artefacto de claude.ai.
- /version.json resume las fechas y tamaños de los ficheros servidos: el botón ↻ del visor lo
  consulta para saber si hay cambios.
- Todo va con Cache-Control: no-cache y ETag: el navegador guarda copia pero pregunta antes de usarla
  (respuesta 304 si no ha cambiado). JSON, HTML y SVG se comprimen con gzip.

Uso: python3 servidor.py [--puerto 8800] [--host 0.0.0.0]
"""
import argparse
import gzip
import hashlib
import json
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

AQUI = Path(__file__).resolve().parent
WEB = AQUI.parent / "web"
APP = AQUI / "app"
APP_FICHEROS = {"manifest.webmanifest", "icono-180.png", "icono-192.png", "icono-512.png"}
COMPRIMIBLE = {".json", ".html", ".webmanifest", ".svg", ".js", ".css"}
mimetypes.add_type("application/manifest+json", ".webmanifest")

_cache_gz = {}   # (ruta, mtime_ns, tamaño) -> bytes comprimidos


def ficheros_servidos():
    out = [APP / "cabecera.html"] + [APP / n for n in sorted(APP_FICHEROS)]
    for raiz, dirs, nombres in os.walk(WEB):
        dirs.sort()
        out += [Path(raiz) / n for n in sorted(nombres) if not n.startswith(".")]
    return out


def version():
    h = hashlib.sha1()
    ultimo = 0
    for p in ficheros_servidos():
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        h.update(f"{p.relative_to(AQUI.parent)}:{st.st_mtime_ns}:{st.st_size}\n".encode())
        ultimo = max(ultimo, st.st_mtime)
    return {"version": h.hexdigest()[:12], "modificado": int(ultimo)}


class Visor(BaseHTTPRequestHandler):
    server_version = "leon3d"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def do_HEAD(self):
        self.responder(cuerpo=False)

    def do_GET(self):
        self.responder(cuerpo=True)

    # ---- lista de destacados editable desde el visor (botón «Destacar» de la ficha)
    def do_OPTIONS(self):
        if urlsplit(self.path).path != "/destacados":
            return self.enviar(404, b"", "text/plain", None, False)
        self.send_response(204)
        self.send_header("Allow", "OPTIONS, PUT")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PUT(self):
        if urlsplit(self.path).path != "/destacados":
            return self.enviar(404, b"No encontrado\n", "text/plain; charset=utf-8", None, True)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 20000:
                raise ValueError("demasiado grande")
            lista = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(lista, list) or len(lista) > 300 or not all(isinstance(x, str) and 0 < len(x.strip()) <= 120 for x in lista):
                raise ValueError("se espera una lista de nombres")
        except (ValueError, UnicodeDecodeError) as e:
            return self.enviar(400, f"{e}\n".encode(), "text/plain; charset=utf-8", None, True)
        vista, limpia = set(), []
        for x in (x.strip() for x in lista):
            if x.lower() not in vista:
                vista.add(x.lower()); limpia.append(x)
        destino = WEB / "data" / "destacados.json"
        tmp = destino.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(limpia, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, destino)
        self.log_message("destacados guardados: %d", len(limpia))
        self.enviar(200, json.dumps(limpia, ensure_ascii=False).encode(), "application/json; charset=utf-8", None, True)

    def enviar(self, estado, datos, tipo, etag=None, cuerpo=True, comprimir=False):
        if etag and self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        gz = comprimir and "gzip" in (self.headers.get("Accept-Encoding") or "")
        if gz:
            datos = datos() if callable(datos) else gzip.compress(datos, 6)
        elif callable(datos):
            datos = datos(crudo=True)
        self.send_response(estado)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-cache" if etag else "no-store")
        if etag:
            self.send_header("ETag", etag)
        if comprimir:
            self.send_header("Vary", "Accept-Encoding")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        if cuerpo:
            self.wfile.write(datos)

    def responder(self, cuerpo):
        ruta = unquote(urlsplit(self.path).path)
        if ruta in ("/", "/index.html"):
            cab, idx = APP / "cabecera.html", WEB / "index.html"
            sa, sb = cab.stat(), idx.stat()
            etag = f'"i-{sa.st_mtime_ns:x}-{sb.st_mtime_ns:x}-{sb.st_size:x}"'
            datos = cab.read_bytes() + idx.read_bytes() + b"\n</body>\n</html>\n"
            return self.enviar(200, datos, "text/html; charset=utf-8", etag, cuerpo, comprimir=True)
        if ruta == "/version.json":
            datos = json.dumps(version()).encode()
            return self.enviar(200, datos, "application/json", None, cuerpo)

        nombre = ruta.lstrip("/")
        if nombre in APP_FICHEROS:
            p = APP / nombre
        else:
            p = (WEB / nombre).resolve()
            if WEB not in p.parents or not p.is_file() or p.name.startswith("."):
                return self.enviar(404, b"No encontrado\n", "text/plain; charset=utf-8", None, cuerpo)
        st = p.stat()
        etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
        tipo = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo.endswith("json"):
            tipo += "; charset=utf-8"
        comp = p.suffix in COMPRIMIBLE

        def leer(crudo=False):
            if crudo:
                return p.read_bytes()
            k = (str(p), st.st_mtime_ns, st.st_size)
            if k not in _cache_gz:
                _cache_gz.clear() if len(_cache_gz) > 16 else None
                _cache_gz[k] = gzip.compress(p.read_bytes(), 6)
            return _cache_gz[k]

        self.enviar(200, leer if comp else p.read_bytes(), tipo, etag, cuerpo, comprimir=comp)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--puerto", type=int, default=int(os.environ.get("LEON3D_PUERTO", 8800)))
    ap.add_argument("--host", default=os.environ.get("LEON3D_HOST", "0.0.0.0"))
    a = ap.parse_args()
    if not (WEB / "index.html").is_file():
        sys.exit(f"No encuentro {WEB / 'index.html'}")
    srv = ThreadingHTTPServer((a.host, a.puerto), Visor)
    srv.daemon_threads = True
    print(f"León en relieve en http://{a.host}:{a.puerto}/  (versión {version()['version']})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
