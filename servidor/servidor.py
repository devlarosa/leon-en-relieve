#!/usr/bin/env python3
"""Sirve el visor «León en relieve» como aplicación web instalable (pantalla de inicio del iPhone).

- web/index.html se entrega envuelto en app/cabecera.html (doctype, viewport, manifiesto e icono),
  así el mismo index.html sigue valiendo para el artefacto de claude.ai.
- /version.json resume las fechas y tamaños de los ficheros servidos: el botón ↻ del visor lo
  consulta para saber si hay cambios.
- Todo va con Cache-Control: no-cache y ETag: el navegador guarda copia pero pregunta antes de usarla
  (respuesta 304 si no ha cambiado). JSON, HTML y SVG se comprimen con gzip.

- Acceso con usuario y contraseña (opcional): si existe ~/.config/leon3d-visor/acceso.json, todo pide
  entrar por /entrar, que deja una cookie firmada válida un año (las apps de la pantalla de inicio del
  iPhone llevan mal la autenticación básica del navegador). Sin ese fichero, el visor queda abierto.
  La contraseña se guarda como hash PBKDF2, nunca en claro, y fuera del repositorio.

Uso: python3 servidor.py [--puerto 8800] [--host 0.0.0.0]
     python3 servidor.py --acceso USUARIO [CONTRASEÑA]   crea o cambia el acceso (cierra las sesiones abiertas)
     python3 servidor.py --sin-acceso                    lo quita: el visor vuelve a quedar abierto
"""
import argparse
import getpass
import gzip
import hashlib
import hmac
import html
import json
import secrets
import time
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

AQUI = Path(__file__).resolve().parent
WEB = AQUI.parent / "web"
APP = AQUI / "app"
APP_FICHEROS = {"manifest.webmanifest", "icono-180.png", "icono-192.png", "icono-512.png"}
COMPRIMIBLE = {".json", ".html", ".webmanifest", ".svg", ".js", ".css"}
mimetypes.add_type("application/manifest+json", ".webmanifest")

_cache_gz = {}   # (ruta, mtime_ns, tamaño) -> bytes comprimidos

# ---------------------------------------------------------------- acceso con usuario y contraseña
ACCESO = Path(os.environ.get("LEON3D_ACCESO", Path.home() / ".config" / "leon3d-visor" / "acceso.json"))
COOKIE = "leon3d"
LIBRES = {"/entrar", "/manifest.webmanifest", "/icono-180.png", "/icono-192.png", "/icono-512.png"}   # sin sesión


def hash_clave(clave, sal):
    return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), bytes.fromhex(sal), 200_000).hex()


def leer_acceso():
    try:
        a = json.loads(ACCESO.read_text(encoding="utf-8"))
        return a if a.get("usuario") and a.get("hash") and a.get("sal") and a.get("secreto") else None
    except (FileNotFoundError, ValueError):
        return None


def ficha_sesion(a):
    # firma del usuario con el secreto; cambiar la contraseña genera otro secreto y cierra todas las sesiones
    return a["usuario"] + "." + hmac.new(bytes.fromhex(a["secreto"]), a["usuario"].encode(), "sha256").hexdigest()


def pagina_entrar(error=""):
    aviso = f'<p class="err">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="León 3D">
<link rel="manifest" href="manifest.webmanifest"><link rel="apple-touch-icon" href="icono-180.png">
<title>León en relieve · Entrar</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 16px;
    font: 16px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; color: #3b2714;
    background: radial-gradient(ellipse at center, #f4ead6 0%, #e6d6b0 70%, #d4bf92 100%); }}
  form {{ width: 100%; max-width: 340px; background: rgba(255, 252, 244, .9); border: 1px solid #c9b38a; border-radius: 16px;
    padding: 26px 22px; box-shadow: 0 10px 30px rgba(80, 52, 22, .18); display: grid; gap: 12px; }}
  h1 {{ margin: 0; font: 600 26px/1.15 Georgia, "Times New Roman", serif; text-align: center; }}
  p {{ margin: 0; text-align: center; font-size: 14px; color: #6b5536; }}
  label {{ display: grid; gap: 4px; font-size: 13px; font-weight: 600; }}
  input {{ font: inherit; padding: 11px 12px; border: 1px solid #c9b38a; border-radius: 10px; background: #fff; color: #3b2714; }}
  input:focus {{ outline: 2px solid #7a2a6f; outline-offset: 1px; }}
  button {{ font: inherit; font-weight: 600; padding: 12px; border: 0; border-radius: 10px; background: #7a2a6f; color: #fff; cursor: pointer; margin-top: 4px; }}
  .err {{ color: #9c2f2f; font-weight: 600; }}
</style></head><body>
<form method="post" action="entrar">
  <h1>León en relieve</h1>
  <p>La provincia en 3D. Entra con el usuario y la contraseña que te han dado.</p>
  {aviso}
  <label>Usuario<input name="usuario" autocomplete="username" autocapitalize="none" autocorrect="off" required autofocus></label>
  <label>Contraseña<input name="clave" type="password" autocomplete="current-password" required></label>
  <button type="submit">Entrar</button>
</form></body></html>""".encode("utf-8")


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
        quien = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip() if getattr(self, "headers", None) else ""
        sys.stderr.write("%s %s\n" % (quien or self.address_string(), fmt % args))

    # ---- acceso
    def cookie_sesion(self):
        for trozo in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = trozo.strip().partition("=")
            if k == COOKIE:
                return v
        return ""

    def autorizado(self):
        a = leer_acceso()
        if not a:
            return True                                   # sin fichero de acceso: visor abierto
        if self.client_address[0] in ("127.0.0.1", "::1") and not self.headers.get("X-Forwarded-For"):
            return True                                   # desde el propio gravity (pruebas)
        return hmac.compare_digest(self.cookie_sesion(), ficha_sesion(a))

    def exigir_acceso(self, cuerpo):
        """True si la petición puede seguir; si no, responde (a la entrada si es la página, 401 si es un dato)."""
        ruta = urlsplit(self.path).path
        if ruta in LIBRES or self.autorizado():
            return True
        if ruta in ("/", "/index.html"):
            self.send_response(303)
            self.send_header("Location", "entrar")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.enviar(401, b"Hay que entrar con usuario y contrasena\n", "text/plain; charset=utf-8", None, cuerpo)
        return False

    def do_POST(self):
        if urlsplit(self.path).path != "/entrar":
            return self.enviar(404, b"No encontrado\n", "text/plain; charset=utf-8", None, True)
        a = leer_acceso()
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 4000)
            f = parse_qs(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            f = {}
        usuario, clave = (f.get("usuario") or [""])[0].strip(), (f.get("clave") or [""])[0]
        ok = bool(a) and hmac.compare_digest(usuario.lower(), a["usuario"].lower()) and \
            hmac.compare_digest(hash_clave(clave, a["sal"]), a["hash"])
        if not ok:
            time.sleep(1.5)                               # frena los intentos a ciegas
            self.log_message("entrada fallida (usuario %r)", usuario[:40])
            return self.enviar(401, pagina_entrar("Usuario o contraseña incorrectos."), "text/html; charset=utf-8", None, True)
        segura = "; Secure" if (self.headers.get("X-Forwarded-Proto") == "https" or ".devlarosa.es" in (self.headers.get("Host") or "")) else ""
        self.log_message("entrada correcta")
        self.send_response(303)
        self.send_header("Set-Cookie", f"{COOKIE}={ficha_sesion(a)}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax{segura}")
        self.send_header("Location", "./")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        if self.exigir_acceso(False):
            self.responder(cuerpo=False)

    def do_GET(self):
        ruta = urlsplit(self.path).path
        if ruta == "/entrar":
            if not leer_acceso() or self.autorizado():
                self.send_response(303); self.send_header("Location", "./"); self.send_header("Content-Length", "0"); self.end_headers()
                return
            return self.enviar(200, pagina_entrar(), "text/html; charset=utf-8", None, True)
        if ruta == "/salir":
            self.send_response(303)
            self.send_header("Set-Cookie", f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
            self.send_header("Location", "entrar")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.exigir_acceso(True):
            self.responder(cuerpo=True)

    # ---- lista de destacados editable desde el visor (botón «Destacar» de la ficha)
    def do_OPTIONS(self):
        if not self.exigir_acceso(False):
            return
        if urlsplit(self.path).path != "/destacados":
            return self.enviar(404, b"", "text/plain", None, False)
        self.send_response(204)
        self.send_header("Allow", "OPTIONS, PUT")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PUT(self):
        if not self.exigir_acceso(True):
            return
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
    ap.add_argument("--acceso", nargs="+", metavar=("USUARIO", "CONTRASEÑA"), help="crea o cambia el usuario y la contraseña")
    ap.add_argument("--sin-acceso", action="store_true", help="quita el usuario y la contraseña")
    a = ap.parse_args()
    if a.sin_acceso:
        ACCESO.unlink(missing_ok=True); print("Acceso quitado: el visor queda abierto."); return
    if a.acceso:
        usuario = a.acceso[0].strip()
        clave = a.acceso[1] if len(a.acceso) > 1 else getpass.getpass(f"Contraseña para {usuario}: ")
        if not usuario or len(clave) < 6:
            sys.exit("Hace falta un usuario y una contraseña de al menos 6 caracteres.")
        sal = secrets.token_hex(16)
        ACCESO.parent.mkdir(parents=True, exist_ok=True)
        tmp = ACCESO.with_suffix(".tmp")
        tmp.write_text(json.dumps({"usuario": usuario, "sal": sal, "hash": hash_clave(clave, sal), "secreto": secrets.token_hex(32)}), encoding="utf-8")
        os.chmod(tmp, 0o600); os.replace(tmp, ACCESO)
        print(f"Acceso guardado en {ACCESO} (usuario «{usuario}»). Las sesiones anteriores quedan cerradas."); return
    if not (WEB / "index.html").is_file():
        sys.exit(f"No encuentro {WEB / 'index.html'}")
    srv = ThreadingHTTPServer((a.host, a.puerto), Visor)
    srv.daemon_threads = True
    print(f"León en relieve en http://{a.host}:{a.puerto}/  (versión {version()['version']}; "
          f"{'con usuario y contraseña' if leer_acceso() else 'ABIERTO, sin usuario ni contraseña'})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
