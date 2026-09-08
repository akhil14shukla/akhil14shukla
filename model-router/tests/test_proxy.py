"""End-to-end: a real proxy in front of a fake Anthropic, over real sockets."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ccrouter import config, proxy


class _FakeAnthropic(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    received: list[dict] = []

    def log_message(self, *args):  # keep the test output quiet
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length") or 0))
        payload = json.loads(body or b"{}")
        _FakeAnthropic.received.append({"path": self.path, "body": payload,
                                        "auth": self.headers.get("x-api-key"),
                                        "beta": self.headers.get("anthropic-beta")})

        if payload.get("stream"):
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("transfer-encoding", "chunked")
            self.end_headers()
            events = [
                ("message_start", {"type": "message_start", "message": {
                    "id": "msg_1", "model": payload["model"], "usage": {
                        "input_tokens": 120, "cache_read_input_tokens": 48_000,
                        "cache_creation_input_tokens": 2_400, "output_tokens": 1}}}),
                *[("delta", {"i": i, "model": payload["model"]}) for i in range(4)],
                ("message_delta", {"type": "message_delta",
                                   "usage": {"output_tokens": 777}}),
            ]
            for name, data in events:
                event = f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()
                self.wfile.write(b"%X\r\n%s\r\n" % (len(event), event))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            return

        out = json.dumps({"id": "msg_1", "model": payload.get("model"), "usage": {
            "input_tokens": 95, "output_tokens": 310,
            "cache_read_input_tokens": 30_000,
            "cache_creation_input_tokens": 1_100}}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


class ProxyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAnthropic)
        cls.upstream.daemon_threads = True
        threading.Thread(target=cls.upstream.serve_forever, daemon=True).start()

        cls.tmp = tempfile.TemporaryDirectory()
        host, port = cls.upstream.server_address[:2]
        cfg = config.replace(
            config.load(),
            listen="127.0.0.1:0",
            upstream=f"http://{host}:{port}",
            log_file=str(Path(cls.tmp.name) / "log.jsonl"),
        )
        cls.proxy = proxy.ProxyServer(cfg, verbose=False)
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        phost, pport = cls.proxy.server_address[:2]
        cls.base = f"http://{phost}:{pport}"

    @classmethod
    def tearDownClass(cls):
        cls.proxy.shutdown()
        cls.proxy.server_close()
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        _FakeAnthropic.received.clear()

    def post(self, path, payload, headers=None):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(),
            headers={"content-type": "application/json", **(headers or {})})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=10)

    def message(self, prompt, model="claude-opus-5", **extra):
        return {
            "model": model,
            "max_tokens": 1024,
            "system": "You are Claude Code, Anthropic's official CLI for Claude.",
            "tools": [{"name": n} for n in ("Task", "Read", "Edit", "Bash")],
            "messages": [{"role": "user", "content": prompt}],
            **extra,
        }

    # -- behaviour ---------------------------------------------------------
    def test_a_cheap_prompt_reaches_upstream_as_haiku(self):
        response = self.post("/v1/messages", self.message("rename parse in src/app.py"))
        self.assertEqual(response.status, 200)
        self.assertEqual(_FakeAnthropic.received[0]["body"]["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(response.headers["x-ccrouter-tier"], "haiku")
        self.assertEqual(response.headers["x-ccrouter-from"], "claude-opus-5")

    def test_a_hard_prompt_is_left_on_the_top_tier(self):
        self.post("/v1/messages", self.message("why does the scheduler intermittently deadlock?"))
        self.assertEqual(_FakeAnthropic.received[0]["body"]["model"], "claude-opus-5")

    def test_credentials_and_beta_headers_are_relayed_untouched(self):
        self.post("/v1/messages", self.message("read src/app.py"),
                  headers={"x-api-key": "sk-ant-test", "anthropic-beta": "fine-grained-tool-streaming-2025-05-14"})
        seen = _FakeAnthropic.received[0]
        self.assertEqual(seen["auth"], "sk-ant-test")
        self.assertEqual(seen["beta"], "fine-grained-tool-streaming-2025-05-14")

    def test_the_rest_of_the_body_survives_the_rewrite(self):
        self.post("/v1/messages", self.message("read src/app.py", metadata={"user_id": "u1"}))
        body = _FakeAnthropic.received[0]["body"]
        self.assertEqual(body["max_tokens"], 1024)
        self.assertEqual(body["metadata"], {"user_id": "u1"})
        self.assertEqual(len(body["tools"]), 4)

    def test_streaming_responses_pass_through_intact(self):
        response = self.post("/v1/messages", self.message("read src/app.py", stream=True))
        payload = response.read().decode()
        self.assertEqual(payload.count("event: delta"), 4)
        self.assertIn("claude-haiku-4-5-20251001", payload)

    def test_token_counting_is_never_rerouted(self):
        self.post("/v1/messages/count_tokens", self.message("rename parse in src/app.py"))
        self.assertEqual(_FakeAnthropic.received[0]["body"]["model"], "claude-opus-5")

    def test_an_unroutable_body_is_forwarded_unchanged(self):
        self.post("/v1/messages", {"not": "a message request"})
        self.assertEqual(_FakeAnthropic.received[0]["body"], {"not": "a message request"})

    def test_usage_is_captured_from_a_non_streaming_response(self):
        self.proxy.router.measured.clear()
        self.post("/v1/messages", self.message("rename parse in src/app.py"))
        measured = self.proxy.router.measured["haiku"]
        self.assertEqual(measured["cache_read"], 30_000)
        self.assertEqual(measured["cache_write"], 1_100)
        self.assertEqual(measured["output_tokens"], 310)

    def test_usage_is_captured_from_a_streamed_response(self):
        self.proxy.router.measured.clear()
        response = self.post("/v1/messages", self.message("read src/app.py", stream=True))
        payload = response.read().decode()
        self.assertEqual(payload.count("event: delta"), 4)      # body still intact
        measured = self.proxy.router.measured["haiku"]
        self.assertEqual(measured["cache_read"], 48_000)
        self.assertEqual(measured["cache_write"], 2_400)
        self.assertEqual(measured["output_tokens"], 777)        # from message_delta

    def test_the_savings_report_switches_to_measured_numbers(self):
        self.proxy.router.measured.clear()
        self.post("/v1/messages", self.message("rename parse in src/app.py"))
        report = self.proxy.router.savings()
        self.assertIn("measured", report["basis"])
        self.assertGreater(report["net_saving_usd"], 0)

    def test_health_and_stats_are_served_locally(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        health = json.loads(opener.open(self.base + "/__router/healthz", timeout=5).read())
        self.assertTrue(health["ok"])
        self.post("/v1/messages", self.message("read src/app.py"))
        stats = json.loads(opener.open(self.base + "/__router/stats", timeout=5).read())
        self.assertIn("haiku", stats["by_tier"])
        self.assertIn("cache_rewarm_usd", stats)

    def test_an_upstream_failure_surfaces_as_an_api_shaped_error(self):
        cfg = config.replace(self.proxy.cfg, upstream="http://127.0.0.1:1")
        broken = proxy.ProxyServer(cfg, verbose=False)
        threading.Thread(target=broken.serve_forever, daemon=True).start()
        try:
            host, port = broken.server_address[:2]
            request = urllib.request.Request(
                f"http://{host}:{port}/v1/messages",
                data=json.dumps(self.message("read src/app.py")).encode(),
                headers={"content-type": "application/json"})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with self.assertRaises(urllib.error.HTTPError) as caught:
                opener.open(request, timeout=10)
            self.assertEqual(caught.exception.code, 502)
            self.assertEqual(json.loads(caught.exception.read())["error"]["type"],
                             "ccrouter_upstream_error")
        finally:
            broken.shutdown()
            broken.server_close()


if __name__ == "__main__":
    unittest.main()
