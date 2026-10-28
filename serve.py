"""Serves the node interface on localhost and, with --sim, bridges it to the mesh-network simulator console."""
import argparse
import json
import queue
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_EXE = HERE.parent / "mesh-network" / "build" / ("lmesh_console.exe" if sys.platform == "win32" else "lmesh_console")
TICK_S = 0.05


class Sim:
    def __init__(self, exe, args, speed):
        self.proc = subprocess.Popen([str(exe), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1)
        self.speed = speed
        self.lock = threading.Lock()
        self.clients = set()
        self.clients_lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._tick, daemon=True).start()

    def write(self, line):
        with self.lock:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()

    def subscribe(self):
        q = queue.Queue(maxsize=5000)
        with self.clients_lock:
            self.clients.add(q)
        return q

    def unsubscribe(self, q):
        with self.clients_lock:
            self.clients.discard(q)

    def _read(self):
        for line in self.proc.stdout:
            line = line.rstrip("\r\n")
            with self.clients_lock:
                for q in self.clients:
                    try:
                        q.put_nowait(line)
                    except queue.Full:
                        pass
        print("simulator exited", file=sys.stderr)

    def _tick(self):
        last = time.monotonic()
        carry = 0.0
        while self.proc.poll() is None:
            time.sleep(TICK_S)
            now = time.monotonic()
            carry += (now - last) * 1000.0 * self.speed
            last = now
            ms = int(carry)
            if ms > 0:
                carry -= ms
                try:
                    self.write(f"@t {ms}")
                except OSError:
                    return


def make_handler(sim):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(HERE), **kw)

        def log_message(self, fmt, *args):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/sim/info":
                if sim is None:
                    self._json(404, {"sim": False})
                else:
                    self._json(200, {"sim": True, "speed": sim.speed})
                return
            if self.path == "/sim/events" and sim is not None:
                self._events()
                return
            super().do_GET()

        def do_POST(self):
            if self.path != "/sim/send" or sim is None:
                self._json(404, {"ok": False})
                return
            length = int(self.headers.get("Content-Length", 0))
            text = self.rfile.read(length).decode("utf-8", "replace")
            for line in text.splitlines():
                if line.strip():
                    sim.write(line)
            self._json(200, {"ok": True})

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q = sim.subscribe()
            try:
                while True:
                    try:
                        line = q.get(timeout=10)
                        self.wfile.write(f"data: {line}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            finally:
                sim.unsubscribe(q)

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--sim", action="store_true", help="run the simulator console and offer it to the page")
    p.add_argument("--exe", type=Path, default=DEFAULT_EXE, help="path to lmesh_console")
    p.add_argument("--topo", default="random", choices=["line", "ring", "diamond", "random"])
    p.add_argument("--nodes", type=int, default=8)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--loss", type=int, default=0, help="loss percent on every link")
    p.add_argument("--speed", type=float, default=1.0, help="simulated seconds per real second")
    a = p.parse_args()

    sim = None
    if a.sim:
        if not a.exe.exists():
            sys.exit(f"{a.exe} not found; build it with: cmake --build ../mesh-network/build")
        sim = Sim(a.exe, [a.topo, str(a.nodes), str(a.seed), str(a.loss)], a.speed)

    server = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(sim))
    server.daemon_threads = True
    mode = f"simulator: {a.topo} of {a.nodes}, seed {a.seed}, {a.loss} % loss, x{a.speed:g}" if sim else "USB only"
    print(f"interface at http://localhost:{a.port}/  ({mode}); Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if sim:
            sim.proc.terminate()


if __name__ == "__main__":
    main()
