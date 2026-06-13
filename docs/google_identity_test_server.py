from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import html
import os


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_ENV = ROOT_DIR / "backend" / ".env"
HOST = "127.0.0.1"
PORT = 5500


def load_google_client_id() -> str:
    if os.getenv("GOOGLE_CLIENT_ID"):
        return os.environ["GOOGLE_CLIENT_ID"].strip()

    if BACKEND_ENV.exists():
        for line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "GOOGLE_CLIENT_ID":
                return value.strip().strip('"').strip("'")

    return ""


def render_page(client_id: str) -> bytes:
    safe_client_id = html.escape(client_id, quote=True)
    body = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Google Identity Token Test</title>
    <script src="https://accounts.google.com/gsi/client" async defer></script>
    <style>
      body {{
        font-family: Arial, sans-serif;
        margin: 2rem;
        max-width: 900px;
      }}

      textarea {{
        box-sizing: border-box;
        font-family: Consolas, monospace;
        min-height: 220px;
        width: 100%;
      }}
    </style>
  </head>
  <body>
    <h1>Google Identity Token Test</h1>
    <p>This local page reads <code>GOOGLE_CLIENT_ID</code> from your environment or <code>backend/.env</code>.</p>

    <div
      id="g_id_onload"
      data-client_id="{safe_client_id}"
      data-callback="handleCredentialResponse"
    ></div>
    <div class="g_id_signin" data-type="standard"></div>

    <h2>response.credential</h2>
    <textarea id="credential" readonly spellcheck="false"></textarea>

    <script>
      function handleCredentialResponse(response) {{
        const credential = response.credential || "";
        console.log("Google response.credential:", credential);
        document.getElementById("credential").value = credential;
      }}
    </script>
  </body>
</html>
"""
    return body.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/", "/test-google-login"}:
            self.send_response(404)
            self.end_headers()
            return

        client_id = load_google_client_id()
        if not client_id:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"GOOGLE_CLIENT_ID is missing from environment or backend/.env")
            return

        page = render_page(client_id)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Open http://{HOST}:{PORT}/test-google-login")
    server.serve_forever()


if __name__ == "__main__":
    main()
