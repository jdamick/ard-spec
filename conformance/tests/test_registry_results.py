#!/usr/bin/env python3
"""Registry mode checks that Search results and List items are AI Catalog entries (§5.3.2, §5.3.4)."""

import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFORMANCE_TOOL = REPO_ROOT / "conformance" / "bin" / "conformance-test"
ENTRY = {
    "identifier": "urn:air:registry.test:agent",
    "displayName": "Fixture",
    "type": "application/a2a-agent-card+json",
    "url": "https://registry.test/agent.json",
}


def _serve(items, results):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, body):
            data = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send({"items": items})

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path.endswith("/explore"):
                self._send({"resultType": "facets", "facets": {"type": {"buckets": []}}})
            else:
                self._send({"results": results})

    server = HTTPServer(("127.0.0.1", 0), Handler)  # loopback only
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _probe(items, results):
    server = _serve(items, results)
    try:
        return subprocess.run(
            [sys.executable, "-S", str(CONFORMANCE_TOOL), "registry", f"http://127.0.0.1:{server.server_port}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False,
        )
    finally:
        server.shutdown()
        server.server_close()


def _result(**members):
    result = dict(ENTRY, score=90, source="https://registry.test/")
    result.update(members)
    return {k: v for k, v in result.items() if v is not None}


class RegistryResultTests(unittest.TestCase):
    def test_complete_entries_pass(self):
        inline = _result(url=None, data={"name": "inline"})
        result = _probe([ENTRY, dict(ENTRY, version="2.0.0")], [_result(), inline])
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Catalog Entry requires", result.stdout)

    def test_identifier_only_result_fails(self):
        result = _probe([ENTRY], [{"identifier": ENTRY["identifier"], "score": 90, "source": "https://registry.test/"}])
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("[Result #0] Missing 'type'", result.stdout)
        self.assertIn("[Result #0] Carries neither of 'url' and 'data'", result.stdout)

    def test_result_with_url_and_data_fails(self):
        result = _probe([ENTRY], [_result(data={"name": "inline"})])
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("[Result #0] Carries both of 'url' and 'data'", result.stdout)

    def test_null_url_counts_as_carried(self):
        with_data = dict(ENTRY, url=None, data={"name": "inline"}, score=90, source="https://registry.test/")
        self.assertIn("[Result #0] Carries both of 'url' and 'data'", _probe([ENTRY], [with_data]).stdout)
        null_only = dict(ENTRY, url=None, score=90, source="https://registry.test/")
        self.assertIn("[Result #0] 'url' must be a non-empty string", _probe([ENTRY], [null_only]).stdout)

    def test_member_types(self):
        result = _probe([ENTRY], [_result(identifier=123), _result(url=None, data="inline")])
        self.assertIn("[Result #0] 'identifier' must be a string", result.stdout)
        self.assertIn("[Result #1] 'data' must be a JSON object", result.stdout)

    def test_list_item_with_score_warns(self):
        result = _probe([dict(ENTRY, score=90)], [_result()])
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("[Item #0] Carries 'score' or 'source'", result.stdout)

    def test_empty_url_fails(self):
        result = _probe([ENTRY], [_result(url="")])
        self.assertIn("[Result #0] 'url' must be a non-empty string", result.stdout)

    def test_incomplete_list_item_fails(self):
        result = _probe([{"identifier": ENTRY["identifier"]}], [_result()])
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("[Item #0] Missing 'type'", result.stdout)


if __name__ == "__main__":
    unittest.main()
