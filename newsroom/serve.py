"""Tiny local preview server that serves _site/ under the configured base path (e.g. /times/)."""

from __future__ import annotations

import functools
import http.server
from pathlib import Path


class _BasePathHandler(http.server.SimpleHTTPRequestHandler):
    base_path = "/"

    def do_GET(self):  # noqa: N802 (stdlib naming)
        if self.path == "/" and self.base_path != "/":
            self.send_response(302)
            self.send_header("Location", self.base_path)
            self.end_headers()
            return
        if self.path.startswith(self.base_path):
            self.path = "/" + self.path[len(self.base_path):]
        else:
            self.path = "/404.html"
        super().do_GET()

    def send_error(self, code, message=None, explain=None):
        # Mimic GitHub Pages: serve the site's own 404 page.
        if code == 404 and (Path(self.directory) / "404.html").exists():
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write((Path(self.directory) / "404.html").read_bytes())
            return
        super().send_error(code, message, explain)

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet


def serve(out_dir: Path, base_path: str, port: int) -> None:
    handler = functools.partial(
        type("Handler", (_BasePathHandler,), {"base_path": base_path}),
        directory=str(out_dir),
    )
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Serving {out_dir} at http://127.0.0.1:{port}{base_path}  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
