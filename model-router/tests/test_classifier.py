"""The local-LLM tiebreaker: consulted rarely, clamped, and never load-bearing."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ccrouter import classifier, config, rules, signals
from ccrouter.config import OPUS, SONNET

SYSTEM = "You are Claude Code, Anthropic's official CLI for Claude."
TOOLS = [{"name": n} for n in ("Task", "Read", "Edit", "Bash")]


class _FakeLocalLLM(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    answer = "opus"
    prompts: list[str] = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)))
        _FakeLocalLLM.prompts.append(body["messages"][0]["content"])
        out = json.dumps({"choices": [{"message": {"content": _FakeLocalLLM.answer}}]}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def verdict_for(prompt, cfg, **body):
    payload = {"model": "claude-sonnet-5", "system": SYSTEM, "tools": TOOLS,
               "messages": [{"role": "user", "content": prompt}], **body}
    s = signals.extract(payload, cfg)
    return classifier.refine(rules.evaluate(s, cfg), s, cfg)


class ClassifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeLocalLLM)
        cls.server.daemon_threads = True
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        host, port = cls.server.server_address[:2]
        cls.endpoint = f"http://{host}:{port}/v1/chat/completions"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        classifier._cache = None
        _FakeLocalLLM.prompts.clear()
        _FakeLocalLLM.answer = "opus"

    def cfg(self, **llm):
        base = config.load()
        return config.replace(base, llm=config.replace(
            base.llm, enabled=True, endpoint=self.endpoint, timeout_s=5, **llm))

    def test_a_confident_rule_verdict_never_calls_the_model(self):
        verdict_for("why does the scheduler intermittently deadlock?", self.cfg())
        self.assertEqual(_FakeLocalLLM.prompts, [])

    def test_a_borderline_verdict_is_handed_to_the_local_model(self):
        # "add a comment" is cheap, "migration" is not: the score lands mid-band.
        verdict = verdict_for("add a comment explaining the migration", self.cfg(dead_band=1.0))
        self.assertEqual(len(_FakeLocalLLM.prompts), 1)
        self.assertEqual(verdict.source, "llm")
        self.assertEqual(verdict.tier, OPUS)

    def test_the_prompt_template_is_rendered_with_real_signals(self):
        verdict_for("add a comment explaining the migration", self.cfg(dead_band=1.0))
        sent = _FakeLocalLLM.prompts[0]
        self.assertIn("add a comment explaining the migration", sent)
        self.assertIn("phase=user_turn", sent)
        self.assertNotIn("{{", sent)

    def test_the_model_cannot_undercut_a_floor(self):
        _FakeLocalLLM.answer = "haiku"
        verdict = verdict_for("add a comment explaining the migration", self.cfg(dead_band=1.0),
                              thinking={"type": "enabled", "budget_tokens": 30000})
        self.assertEqual(verdict.tier, OPUS)
        self.assertIn("clamped", " ".join(verdict.reasons))

    def test_identical_requests_are_answered_from_cache(self):
        cfg = self.cfg(dead_band=1.0)
        for _ in range(3):
            verdict_for("add a comment explaining the migration", cfg)
        self.assertEqual(len(_FakeLocalLLM.prompts), 1)

    def test_an_unreachable_model_leaves_the_rule_verdict_standing(self):
        base = config.load()
        cfg = config.replace(base, llm=config.replace(
            base.llm, enabled=True, endpoint="http://127.0.0.1:1/v1/chat/completions",
            timeout_s=1, dead_band=1.0))
        verdict = verdict_for("add a comment explaining the migration", cfg)
        self.assertEqual(verdict.source, "rules")
        self.assertEqual(verdict.tier, SONNET)
        self.assertIn("unavailable", " ".join(verdict.reasons))

    def test_a_nonsense_answer_leaves_the_rule_verdict_standing(self):
        _FakeLocalLLM.answer = "I think probably the medium one?"
        verdict = verdict_for("add a comment explaining the migration", self.cfg(dead_band=1.0))
        self.assertEqual(verdict.source, "rules")
        self.assertIn("unparseable", " ".join(verdict.reasons))

    def test_the_model_is_not_consulted_mid_loop(self):
        cfg = self.cfg(dead_band=1.0)
        payload = {"model": "claude-sonnet-5", "system": SYSTEM, "tools": TOOLS, "messages": [
            {"role": "user", "content": "add a comment explaining the migration"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "1", "name": "Read", "input": {"file_path": "a.py"}}]},
            {"role": "user", "content": [{"type": "tool_result", "content": "..."}]}]}
        s = signals.extract(payload, cfg)
        classifier.refine(rules.evaluate(s, cfg), s, cfg)
        self.assertEqual(_FakeLocalLLM.prompts, [])


if __name__ == "__main__":
    unittest.main()
