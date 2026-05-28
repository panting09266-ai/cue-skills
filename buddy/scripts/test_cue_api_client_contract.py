#!/usr/bin/env python3
"""Stdlib-only contract test for `cue_api.capabilities()` HTTP client.

Codex r3 finding: `test_capabilities_client.py` 和 `test_corporate_credit_coverage.py`
需要 cubemanus repo 在本地 + uvicorn + fastapi,CI 跑不到,capabilities
合约从未在 CI 真正被验证(只能 local dev 验)。

本 test 用 stdlib `http.server` + threading 起一个 mock server,fake
cubemanus tool_capabilities API 的 response shape,然后跑 cue_api
client 端到端,验证 client wire format 全套:
  - URL 拼接 (base + /tools/capabilities + query string)
  - Bearer auth header
  - 查询参数序列化 (q / category / fields / max_triggers)
  - ETag echo back as `_etag` in payload
  - If-None-Match → 304 → returns None
  - 4xx → CueAPIError with parsed detail dict

CI 友好 (stdlib only),不需要 cubemanus repo / uvicorn / fastapi。
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))


@contextlib.contextmanager
def mock_server(handler_fn):
    """Spin up a one-shot stdlib mock HTTP server for a single test.

    ``handler_fn(req)`` receives a BaseHTTPRequestHandler instance with
    both do_GET and do_POST dispatched to it.  The context manager yields
    the base URL (``http://127.0.0.1:<port>/api``) so callers can set
    ``CUE_API_BASE`` before exercising the client under test.

    The server is shut down when the ``with`` block exits.
    """
    # Find a free port.
    _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _sock.bind(("127.0.0.1", 0))
    port = _sock.getsockname()[1]
    _sock.close()

    class _DynamicHandler(BaseHTTPRequestHandler):
        def log_message(self, *args, **kwargs) -> None:  # noqa: D401
            return

        def do_GET(self) -> None:
            handler_fn(self)

        def do_POST(self) -> None:
            handler_fn(self)

    srv = ThreadingHTTPServer(("127.0.0.1", port), _DynamicHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}/api"
    finally:
        srv.shutdown()


# Canned capabilities payload (shape mirrors cubemanus
# tool_capabilities.py:build_researcher_capabilities()).
_CANNED_PAYLOAD = {
    "schema_version": 1,
    "api_version": "2026-05-20",
    "surface": "researcher",
    "environment": "test",
    "query": {
        "fields": "default",
        "include_tools": True,
        "include_triggers": True,
        "include_unavailable": True,
        "category": None,
        "q": None,
    },
    "source_counts": {"catalog_tools": 3, "runtime_available_catalog_tools": 3},
    "counts": {
        "returned_tools": 3,
        "runtime_available_tools": 3,
        "categories": 2,
        "presets": 0,
    },
    "categories": [
        {
            "category": "disclosure_cn",
            "label": "信息披露",
            "tool_count": 2,
            "runtime_available_count": 2,
            "sample_triggers": ["公告", "披露"],
        },
        {
            "category": "regulatory_cn",
            "label": "监管合规",
            "tool_count": 1,
            "runtime_available_count": 1,
            "sample_triggers": ["监管处罚"],
        },
    ],
    "presets": [],
    "tools": [
        {
            "name": "get_announcement_content",
            "category": "disclosure_cn",
            "triggers": ["公告", "披露"],
            "runtime_available": True,
        },
        {
            "name": "get_cninfo_announcement_list",
            "category": "disclosure_cn",
            "triggers": ["公告列表"],
            "runtime_available": True,
        },
        {
            "name": "get_cn_financial_penalties",
            "category": "regulatory_cn",
            "triggers": ["金融监管处罚", "银保监会"],
            "runtime_available": True,
        },
    ],
}

# Stable ETag for the canned payload (route layer would compute over normalized
# JSON; we just need any stable string for this mock).
_CANNED_ETAG = 'W/"mockcanned1234"'


# Track what server saw — for cross-checks.
_LAST_REQUEST: dict = {"path": None, "auth": None, "if_none_match": None, "query": None}


class _MockHandler(BaseHTTPRequestHandler):
    """Mock /api/tools/capabilities handler. Single-test scoped, not robust."""

    # Silence default access log spam.
    def log_message(self, *args, **kwargs) -> None:  # noqa: D401
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        _LAST_REQUEST["path"] = parsed.path
        _LAST_REQUEST["auth"] = self.headers.get("Authorization")
        _LAST_REQUEST["if_none_match"] = self.headers.get("If-None-Match")
        _LAST_REQUEST["query"] = query

        # Path mismatch
        if parsed.path != "/api/tools/capabilities":
            self.send_response(404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"detail":"not found"}')
            return

        # 400 simulation: fields=bogus
        if query.get("fields") == "bogus":
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            body = json.dumps(
                {
                    "detail": {
                        "error": "unsupported_fields",
                        "fields": "bogus",
                        "supported": ["summary", "default", "debug"],
                    }
                }
            )
            self.wfile.write(body.encode("utf-8"))
            return

        # If-None-Match → 304 short-circuit (strong + weak comparison)
        inm = (self.headers.get("If-None-Match") or "").strip()
        if inm:
            stripped = inm[2:] if inm.startswith("W/") else inm
            canon = _CANNED_ETAG[2:]  # strip W/
            if stripped == canon:
                self.send_response(304)
                self.send_header("ETag", _CANNED_ETAG)
                self.end_headers()
                return

        # 200 normal — return canned, customize query echo
        payload = dict(_CANNED_PAYLOAD)
        payload["query"] = dict(_CANNED_PAYLOAD["query"])
        for k in ("fields", "q", "category"):
            if k in query:
                payload["query"][k] = query[k]
        body = json.dumps(payload, ensure_ascii=False)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("ETag", _CANNED_ETAG)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


def _start_mock_server() -> tuple[str, ThreadingHTTPServer]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    srv = ThreadingHTTPServer(("127.0.0.1", port), _MockHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}/api", srv


# ---------------------------------------------------------------------------
# Boot mock + configure cue_api before importing capabilities()
# ---------------------------------------------------------------------------
_BASE, _SRV = _start_mock_server()
os.environ["CUE_API_BASE"] = _BASE
os.environ["CUE_API_KEY"] = "sk-mock-contract-test"

from cue_api import CueAPIError, capabilities  # noqa: E402


class Case1_BasicWireFormat(unittest.TestCase):
    def test_bare_get_returns_payload(self) -> None:
        body = capabilities()
        self.assertIsNotNone(body)
        self.assertEqual(body["schema_version"], 1)
        self.assertEqual(body["surface"], "researcher")
        self.assertIn("counts", body)
        # _etag injected by client from response header
        self.assertEqual(body.get("_etag"), _CANNED_ETAG)

    def test_url_path_and_bearer_header(self) -> None:
        capabilities()
        self.assertEqual(_LAST_REQUEST["path"], "/api/tools/capabilities")
        self.assertEqual(_LAST_REQUEST["auth"], "Bearer sk-mock-contract-test")


class Case2_QuerySerialization(unittest.TestCase):
    def test_q_param_sent(self) -> None:
        capabilities(q="公告")
        self.assertEqual(_LAST_REQUEST["query"].get("q"), "公告")

    def test_category_param_sent(self) -> None:
        capabilities(category="disclosure_cn")
        self.assertEqual(_LAST_REQUEST["query"].get("category"), "disclosure_cn")

    def test_fields_param_sent(self) -> None:
        capabilities(fields="default")
        self.assertEqual(_LAST_REQUEST["query"].get("fields"), "default")

    def test_max_triggers_param_sent_as_str(self) -> None:
        capabilities(max_triggers=3)
        self.assertEqual(_LAST_REQUEST["query"].get("max_triggers"), "3")


class Case3_ETagRoundTrip(unittest.TestCase):
    def test_etag_echo_returns_none_on_304(self) -> None:
        first = capabilities()
        etag = first.get("_etag")
        self.assertIsNotNone(etag)

        # Pass etag back via If-None-Match — should get 304 → None
        second = capabilities(if_none_match=etag)
        self.assertIsNone(second)
        self.assertEqual(_LAST_REQUEST["if_none_match"], etag)

    def test_etag_strong_token_form_also_matches(self) -> None:
        """Strong form (without W/ prefix) should also yield 304 (weak comparison)."""
        first = capabilities()
        etag = first["_etag"]
        strong = etag[2:] if etag.startswith("W/") else etag
        second = capabilities(if_none_match=strong)
        self.assertIsNone(second)


class Case4_ErrorPropagation(unittest.TestCase):
    def test_unsupported_fields_400_raises_with_detail(self) -> None:
        with self.assertRaises(CueAPIError) as cm:
            capabilities(fields="bogus")
        self.assertEqual(cm.exception.status, 400)
        # detail should include the structured payload (json-serialized when dict)
        self.assertIn("unsupported_fields", cm.exception.detail)

    def test_network_unreachable_wrapped_as_cue_api_error(self) -> None:
        """codex r6: URLError(transport-layer fail) 必须包装成 CueAPIError(status=0),
        否则 CLI 外层 except 兜不住 → user 看到 raw Python traceback。"""
        # 临时切到不可连的 base URL,再调一次 capabilities
        import urllib.request

        orig_base = os.environ.get("CUE_API_BASE")
        os.environ["CUE_API_BASE"] = "http://127.0.0.1:1"  # nothing listens
        try:
            with self.assertRaises(CueAPIError) as cm:
                capabilities()
            self.assertEqual(cm.exception.status, 0)
            self.assertIn("network unreachable", cm.exception.detail)
            # user_hint 给 actionable 提示而非 raw error
            hint = cm.exception.user_hint()
            self.assertIn("CUE_API_BASE", hint)
            self.assertIn("代理", hint)
        finally:
            if orig_base is not None:
                os.environ["CUE_API_BASE"] = orig_base


class Case5_NoRegressionOnRetry(unittest.TestCase):
    def test_calls_remain_idempotent(self) -> None:
        body1 = capabilities(q="公告")
        body2 = capabilities(q="公告")
        # Mock returns the same payload + same etag both times
        self.assertEqual(body1["_etag"], body2["_etag"])
        self.assertEqual(body1["counts"], body2["counts"])


import cue_api as _cue_api_module  # noqa: E402 — needed for search_templates tests


class Case6_SearchTemplates(unittest.TestCase):
    def test_search_templates_keyword_includes_system_and_pagination(self):
        """search_templates posts {keyword, include_system, page, page_size} and
        returns unwrapped items list (matching get_templates' unwrap convention)."""
        captured = {}

        def handler(req):
            captured["path"] = req.path
            captured["auth"] = req.headers.get("Authorization")
            length = int(req.headers.get("Content-Length", "0"))
            captured["body"] = json.loads(req.rfile.read(length))
            body = {
                "data": {
                    "items": [{"template_id": "t1", "title": "财报分析"}],
                    "total": 1,
                    "page": 1,
                    "page_size": 20,
                }
            }
            req.send_response(200)
            req.send_header("Content-Type", "application/json")
            req.end_headers()
            req.wfile.write(json.dumps(body).encode())

        with mock_server(handler) as base:
            os.environ["CUE_API_BASE"] = base
            os.environ["CUE_API_KEY"] = "sk-test"
            items = _cue_api_module.search_templates(keyword="财报", include_system=True)

        self.assertEqual(captured["path"], "/api/templates/search")
        self.assertEqual(captured["auth"], "Bearer sk-test")
        self.assertEqual(
            captured["body"],
            {"keyword": "财报", "include_system": True, "page": 1, "page_size": 20},
        )
        self.assertEqual(items, [{"template_id": "t1", "title": "财报分析"}])


class Case7_Rewrite(unittest.TestCase):
    def test_rewrite_posts_input_and_returns_mandate(self):
        """rewrite() posts {input} and returns the full dict with user_confirmation,
        rewritten_mandate, task_node, safety_flag. device_type is a Header (not body)."""
        captured = {}

        def handler(req):
            captured["path"] = req.path
            captured["auth"] = req.headers.get("Authorization")
            captured["device_type"] = req.headers.get("device_type")
            length = int(req.headers.get("Content-Length", "0"))
            captured["body"] = json.loads(req.rfile.read(length))
            body = {
                "_thinking": "...",
                "user_confirmation": "即将为您调研...",
                "task_node": {"intent_tag": "尽职调查", "agent_persona": "...",
                              "target_subject": "...", "search_methodology": "Triangulation"},
                "rewritten_mandate": "**【调研目标】**...",
                "safety_flag": {"pii_masked": [], "risk_category": "None"},
            }
            req.send_response(200)
            req.send_header("Content-Type", "application/json")
            req.end_headers()
            req.wfile.write(json.dumps(body).encode())

        with mock_server(handler) as base:
            os.environ["CUE_API_BASE"] = base
            os.environ["CUE_API_KEY"] = "sk-test"
            result = _cue_api_module.rewrite(input="帮我查一下宁德时代", device_type="cli")
        self.assertEqual(captured["path"], "/api/rewrite")
        self.assertEqual(captured["auth"], "Bearer sk-test")
        self.assertEqual(captured["device_type"], "cli")
        self.assertEqual(captured["body"]["input"], "帮我查一下宁德时代")
        self.assertTrue(result["user_confirmation"].startswith("即将为您调研"))
        self.assertTrue(result["rewritten_mandate"].startswith("**【调研目标】**"))


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        _SRV.shutdown()
