# Servidor de pruebas: sirve web/ y una ruta /espera?s=N que tarda N segundos (retiene el evento load del arnés)
import http.server, time, sys, os, urllib.parse
raiz = sys.argv[1]
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=raiz, **k)
    def log_message(self, *a): pass
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/espera":
            time.sleep(float(urllib.parse.parse_qs(u.query).get("s", ["20"])[0]))
            self.send_response(200); self.send_header("Content-Type", "image/gif"); self.end_headers()
            self.wfile.write(b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")
            return
        if u.path == "/lento":
            n = float(urllib.parse.parse_qs(u.query).get("s", ["40"])[0])
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(b'<!doctype html><meta charset="utf-8"><style>html,body{margin:0;height:100%}iframe{border:0;width:100%;height:100%;display:block}</style><iframe src="/index.html"></iframe>')
            self.wfile.flush()
            for _ in range(int(n)):
                time.sleep(1); self.wfile.write(b" "); self.wfile.flush()
            self.wfile.write(b"</html>"); return
        super().do_GET()
http.server.ThreadingHTTPServer(("127.0.0.1", 8765), H).serve_forever()
