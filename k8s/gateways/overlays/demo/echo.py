"""Fixed demo destinations with an explicit response-field allowlist."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class Echo(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.connection.settimeout(5)
        path = urlsplit(self.path)
        try:
            size = int(self.headers.get('Content-Length', 0))
        except ValueError:
            size = -1
        if self.headers.get('Transfer-Encoding') or size < 0:
            self.send_error(400)
            return
        if size > 65536:
            self.send_error(413)
            return
        body = self.rfile.read(size)
        if path.path == '/apis/demo/meteo':
            value = {'fictional': True, 'forecast': 'sunny', 'temperature_c': 22}
        elif path.path == '/apis/demo/echo' or path.path.startswith('/apis/demo/echo/'):
            value = {'method': self.command, 'path': path.path, 'query': path.query,
                     'content_type': self.headers.get('Content-Type', ''),
                     'user_agent': self.headers.get('User-Agent', ''),
                     'body': body.decode('utf-8', errors='replace')}
        else:
            self.send_error(404)
            return
        raw = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(raw)

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = do_GET


if __name__ == '__main__':
    ThreadingHTTPServer(('', 8080), Echo).serve_forever()
