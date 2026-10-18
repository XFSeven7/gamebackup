"""本地起一个小服务，给 README 截图用。"""

from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui"
DEMO = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print(fmt % args)

    def do_GET(self):
        if self.path.split("?", 1)[0] in ("/", "/index.html"):
            self._send_demo_html()
            return
        super().do_GET()

    def _send_demo_html(self):
        html = (UI / "index.html").read_text(encoding="utf-8")
        inject = (
            '  <script src="/docs/readme-demo/demo-data.js"></script>\n'
            '  <script src="/docs/readme-demo/demo-bridge.js"></script>\n'
        )
        html = html.replace('<script src="app.js"></script>', inject + '  <script src="/ui/app.js"></script>')
        html = html.replace('href="style.css"', 'href="/ui/style.css"')
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    port = 8765
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"http://127.0.0.1:{port}/")
    print(f"http://127.0.0.1:{port}/?empty=1")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
