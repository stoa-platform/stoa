"""Local HTTP boundary tests; no cluster access."""
import http.client
import importlib.util
import json
import threading
import unittest
from pathlib import Path


class EchoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name('echo.py')
        spec = importlib.util.spec_from_file_location('echo', path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.server = cls.module.ThreadingHTTPServer(('localhost', 0), cls.module.Echo)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path, body=b'', headers=None):
        conn = http.client.HTTPConnection('localhost', self.server.server_port)
        conn.request('POST', path, body, headers or {})
        res = conn.getresponse()
        return res.status, res.read()

    def test_allowlisted_headers_and_body(self):
        forbidden = ['Authorization', 'Cookie', 'X-Forwarded-For', 'CF-Ray', 'X-Internal']
        headers = {name: name for name in forbidden}
        headers.update({'Content-Type': 'text/plain', 'User-Agent': 'probe'})
        status, raw = self.request('/apis/demo/echo?q=hello', b'payload', headers)
        value = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(set(value), {'method', 'path', 'query', 'content_type', 'user_agent', 'body'})
        self.assertEqual(value['method'], 'POST')
        self.assertEqual(value['path'], '/apis/demo/echo')
        self.assertEqual(value['query'], 'q=hello')
        self.assertEqual(value['body'], 'payload')
        self.assertEqual(value['content_type'], 'text/plain')
        self.assertEqual(value['user_agent'], 'probe')
        for name in forbidden:
            self.assertNotIn(name.encode(), raw)

    def test_body_limit_and_fake_weather(self):
        self.assertEqual(self.request('/apis/demo/echo', b'x' * 65536)[0], 200)
        self.assertEqual(self.request('/apis/demo/echo', b'x' * 65537)[0], 413)
        status, raw = self.request('/apis/demo/meteo?url=ignored')
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)['fictional'])
        self.assertEqual(self.request('/admin')[0], 404)


if __name__ == '__main__':
    unittest.main()
