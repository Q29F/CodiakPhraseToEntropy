"""Application integration through the actual fixed loopback routes."""

import http.client
import json
import math
import threading
import unittest

from web import create_app


class WebTests(unittest.TestCase):
    def setUp(self):
        self.server = create_app(port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.server_close()
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())

    def request(self, path, payload=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            if payload is None:
                connection.request("GET", path)
            else:
                connection.request("POST", path, json.dumps(payload).encode("utf-8"), {
                    "Content-Type": "application/json",
                    "Origin": self.server.origin,
                    "X-CSRF-Token": self.server.session_token,
                })
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_public_assets_and_health_are_served_without_caching(self):
        for path, mime in (("/", "text/html"), ("/app.js", "text/javascript"), ("/style.css", "text/css"), ("/icon.svg", "image/svg+xml")):
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertTrue(headers["Content-Type"].startswith(mime))
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertGreater(len(body), 0)
        status, _, body = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ok", "application": "codiak-workbench"})

    def test_phrase_calculation_round_trips_through_json(self):
        status, _, body = self.request("/api/calculate", {
            "mode": "phrase", "phrase": "abab", "u": 3, "v": 4, "y": 1, "t": 0,
        })
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertAlmostEqual(result["phase"], math.pi / 2, places=12)
        self.assertEqual(len(result["samples"]), 129)
        self.assertAlmostEqual(result["samples"][64]["value"], 5, places=12)
        self.assertNotIn(b"abab", body)

    def test_invalid_semantic_payload_returns_a_bounded_client_error(self):
        status, headers, body = self.request("/api/calculate", {
            "mode": "phase", "phase": 0, "u": True, "v": 1, "y": 1, "t": 0,
        })
        self.assertEqual(status, 400)
        self.assertEqual(headers["Cache-Control"], "no-store")
        error = json.loads(body)
        self.assertEqual(set(error), {"error"})
        self.assertLessEqual(len(error["error"]), 160)
        self.assertNotIn("Traceback", error["error"])

    def test_source_and_configuration_files_are_not_public_routes(self):
        for path in ("/entropy.py", "/web.py", "/requirements.txt", "/CodiakPhraseToEntropySimulationV2.ipynb", "/.git/config"):
            with self.subTest(path=path):
                status, _, body = self.request(path)
                self.assertEqual(status, 404)
                self.assertEqual(json.loads(body), {"error": "Not found."})


if __name__ == "__main__":
    unittest.main()
