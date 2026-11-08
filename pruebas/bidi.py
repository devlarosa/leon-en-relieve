"""Cliente mínimo de WebDriver BiDi para Firefox (solo biblioteca estándar).
Uso: python3 bidi.py URL salida.png [espera_s] [ancho] [alto] [js_extra]
Abre la URL, espera, imprime errores y avisos de consola, evalúa js_extra (si se da) y guarda una captura.
"""
import base64, json, os, socket, struct, subprocess, sys, tempfile, time, shutil

url, out = sys.argv[1], sys.argv[2]
wait = float(sys.argv[3]) if len(sys.argv) > 3 else 25
w, h = (int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 5 else (1400, 850)
extra = sys.argv[6] if len(sys.argv) > 6 else None
PORT = 9333

prof = tempfile.mkdtemp(prefix="ffbidi_")
with open(os.path.join(prof, "user.js"), "w") as f:
    f.write('user_pref("remote.active-protocols", 1);\n')
    if os.environ.get("SOFT"): f.write('user_pref("webgl.force-enabled", true);\nuser_pref("webgl.disable-fail-if-major-performance-caveat", true);\n')
env = dict(os.environ, DISPLAY=":0", XAUTHORITY=os.path.expanduser("~/.Xauthority"))
if os.environ.get("SOFT"): env["LIBGL_ALWAYS_SOFTWARE"] = "1"
env.pop("MOZ_HEADLESS", None)
ff = subprocess.Popen(["firefox", "--no-remote", "--new-instance", "--profile", prof, f"--remote-debugging-port={PORT}",
                       f"--window-size={w},{h}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)


class WS:
    def __init__(self, host, port, path):
        for _ in range(60):
            try:
                self.s = socket.create_connection((host, port), timeout=5); break
            except OSError:
                time.sleep(0.5)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.s.recv(4096)
        if b" 101 " not in resp.split(b"\r\n")[0]:
            raise RuntimeError(resp[:200])
        self.buf = resp.split(b"\r\n\r\n", 1)[1]
        self.s.settimeout(None)

    def send(self, obj):
        data = json.dumps(obj).encode()
        hdr = bytearray([0x81]); n = len(data); mask = os.urandom(4)
        if n < 126: hdr.append(0x80 | n)
        elif n < 65536: hdr.append(0x80 | 126); hdr += struct.pack(">H", n)
        else: hdr.append(0x80 | 127); hdr += struct.pack(">Q", n)
        self.s.sendall(bytes(hdr) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(1 << 20)
            if not chunk: raise EOFError
            self.buf += chunk
        d, self.buf = self.buf[:n], self.buf[n:]
        return d

    def recv(self):
        msg = b""
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7F
            if n == 126: n = struct.unpack(">H", self._read(2))[0]
            elif n == 127: n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            msg += payload
            if b0 & 0x80: break
        return json.loads(msg)


ws = WS("127.0.0.1", PORT, "/session")
mid = 0
logs = []
def call(method, params):
    global mid
    mid += 1; ws.send({"id": mid, "method": method, "params": params})
    while True:
        m = ws.recv()
        if m.get("method") == "log.entryAdded":
            e = m["params"]; logs.append(f"[{e.get('level')}] {e.get('text') or ''}"[:400]); continue
        if m.get("id") == mid:
            if m.get("type") == "error": raise RuntimeError(m)
            return m.get("result")

try:
    call("session.new", {"capabilities": {}})
    call("session.subscribe", {"events": ["log.entryAdded"]})
    ctx = call("browsingContext.getTree", {})["contexts"][0]["context"]
    call("browsingContext.setViewport", {"context": ctx, "viewport": {"width": w, "height": h}})
    t0 = time.time()
    call("browsingContext.navigate", {"context": ctx, "url": url, "wait": "complete"})
    # esperar procesando mensajes de consola
    ws.s.settimeout(0.5)
    while time.time() - t0 < wait:
        try:
            m = ws.recv()
            if m.get("method") == "log.entryAdded":
                e = m["params"]; logs.append(f"[{e.get('level')}] {e.get('text') or ''}"[:400])
        except (socket.timeout, TimeoutError):
            pass
    ws.s.settimeout(None)
    estado = call("script.evaluate", {"expression": "JSON.stringify({carga: document.getElementById('loading')?.className, msg: document.getElementById('loading-msg')?.textContent, box: document.querySelector('#loading .box')?.innerText?.slice(0,300), lectura: document.getElementById('readout')?.innerText})", "target": {"context": ctx}, "awaitPromise": False})
    print("ESTADO", estado["result"].get("value"))
    if extra:
        r = call("script.evaluate", {"expression": extra, "target": {"context": ctx}, "awaitPromise": True})
        print("EXTRA", json.dumps(r.get("result"), ensure_ascii=False)[:1500])
        time.sleep(3)
    # memoria: suma del RSS de los procesos de este perfil
    rss = 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit(): continue
        try:
            if prof.encode() in open(f"/proc/{pid}/cmdline", "rb").read() or str(ff.pid) == pid or open(f"/proc/{pid}/stat").read().split()[3] == str(ff.pid):
                rss += int([l for l in open(f"/proc/{pid}/status") if l.startswith("VmRSS")][0].split()[1])
        except Exception: pass
    print("MEMORIA_MB", round(rss / 1024))
    shot = call("browsingContext.captureScreenshot", {"context": ctx})
    open(out, "wb").write(base64.b64decode(shot["data"]))
    print("captura", out, "tiempo", round(time.time() - t0, 1), "s")
finally:
    for l in logs[:40]: print(l)
    try: call("session.end", {})
    except Exception: pass
    ff.terminate()
    try: ff.wait(10)
    except Exception: ff.kill()
    shutil.rmtree(prof, ignore_errors=True)
