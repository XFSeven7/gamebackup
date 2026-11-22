"""本地起一个小服务，给 README 截图用。"""

from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from runpy import run_path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui"
ACHIEVEMENTS = run_path(str(ROOT / "src/bundled_support/onimusha/achievements.py"))["ACHIEVEMENTS_ZH"]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print(fmt % args)

    def do_GET(self):
        if self.path.split("?", 1)[0] in ("/", "/index.html"):
            self._send_demo_html()
            return
        if self.path == "/demo-achievements.js":
            self._send_content(
                "window.DEMO_ACHIEVEMENTS = " + json.dumps(ACHIEVEMENTS, ensure_ascii=False) + ";",
                "text/javascript; charset=utf-8",
            )
            return
        super().do_GET()

    def _send_demo_html(self):
        html = (UI / "index.html").read_text(encoding="utf-8")
        inject = (
            '  <script src="/docs/readme-demo/demo-data.js"></script>\n'
            '  <script src="/demo-achievements.js"></script>\n'
            '  <script src="/docs/readme-demo/demo-onimusha.js"></script>\n'
            '  <script src="/docs/readme-demo/demo-bridge.js"></script>\n'
        )
        html = html.replace('<script src="app.js"></script>', inject + '  <script src="/ui/app.js"></script>')
        html = html.replace('href="style.css"', 'href="/ui/style.css"')
        self._send_content(html, "text/html; charset=utf-8")

    def _send_content(self, content, content_type):
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    port = 8765
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"http://127.0.0.1:{port}/")
    print(f"http://127.0.0.1:{port}/?empty=1")
    print(f"http://127.0.0.1:{port}/?game=onimusha")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
