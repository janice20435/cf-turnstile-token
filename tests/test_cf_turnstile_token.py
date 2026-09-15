"""Unit tests for cf_turnstile_token - standard library only, no network."""

import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cf_turnstile_token as mod  # noqa: E402


SAMPLE_PAGE = """
<html><body>
  <div class="cf-turnstile" data-sitekey="0x4AAAAAAAfirst"></div>
  <script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>
  <div data-sitekey='0x4AAAAAAAsecond'></div>
</body></html>
"""


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestSitekeyExtraction(unittest.TestCase):
    def test_first_sitekey(self):
        self.assertEqual(mod.extract_sitekey(SAMPLE_PAGE), "0x4AAAAAAAfirst")

    def test_all_sitekeys_unique_and_ordered(self):
        html = SAMPLE_PAGE + '<div data-sitekey="0x4AAAAAAAfirst"></div>'
        self.assertEqual(
            mod.extract_sitekeys(html),
            ["0x4AAAAAAAfirst", "0x4AAAAAAAsecond"],
        )

    def test_js_style_sitekey(self):
        html = "<script>window.cfg = {sitekey: '0x4AAAAAAAjs'};</script>"
        self.assertEqual(mod.extract_sitekey(html), "0x4AAAAAAAjs")

    def test_missing_sitekey_returns_none(self):
        self.assertIsNone(mod.extract_sitekey("<html>no widget here</html>"))

    def test_empty_html(self):
        self.assertIsNone(mod.extract_sitekey(""))


class TestBuildPayload(unittest.TestCase):
    def test_minimal_payload(self):
        payload = mod.build_payload("0xKEY", "https://example.com/")
        self.assertEqual(payload["task_type"], "turnstiletask")
        self.assertEqual(payload["sitekey"], "0xKEY")
        self.assertEqual(payload["url"], "https://example.com/")
        self.assertNotIn("proxy", payload)

    def test_optional_fields(self):
        payload = mod.build_payload(
            "0xKEY", "https://example.com/",
            proxy="http://u:p@1.2.3.4:8080", action="login", cdata="abc",
        )
        self.assertEqual(payload["proxy"], "http://u:p@1.2.3.4:8080")
        self.assertEqual(payload["action"], "login")
        self.assertEqual(payload["cdata"], "abc")


class TestSolve(unittest.TestCase):
    def test_missing_api_key_raises(self):
        with self.assertRaises(mod.PeakError):
            mod.solve("", "0xKEY", "https://example.com/")

    def test_successful_solve(self):
        payload = {"success": True, "data": {"token": "0.TOKEN"}}
        with mock.patch.object(mod, "urlopen", return_value=FakeResponse(payload)):
            result = mod.solve("pk_test", "0xKEY", "https://example.com/")
        self.assertEqual(result.token, "0.TOKEN")
        self.assertTrue(result.raw["success"])

    def test_api_error_raises(self):
        payload = {"success": False, "error": "unsupported sitekey"}
        with mock.patch.object(mod, "urlopen", return_value=FakeResponse(payload)):
            with self.assertRaises(mod.PeakError):
                mod.solve("pk_test", "0xKEY", "https://example.com/")

    def test_missing_token_raises(self):
        payload = {"success": True, "data": {}}
        with mock.patch.object(mod, "urlopen", return_value=FakeResponse(payload)):
            with self.assertRaises(mod.PeakError):
                mod.solve("pk_test", "0xKEY", "https://example.com/")

    def test_retry_then_success(self):
        payload = {"success": True, "data": {"token": "0.RETRY"}}
        side = [OSError("temporary"), FakeResponse(payload)]

        def flaky(*a, **kw):
            item = side.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with mock.patch.object(mod, "urlopen", side_effect=flaky), \
                mock.patch.object(mod.time, "sleep", return_value=None):
            result = mod.solve("pk_test", "0xKEY", "https://example.com/", retries=2)
        self.assertEqual(result.token, "0.RETRY")


class TestSolveMany(unittest.TestCase):
    def test_one_bad_job_does_not_kill_batch(self):
        good = {"success": True, "data": {"token": "0.GOOD"}}
        bad = {"success": False, "error": "nope"}
        responses = [FakeResponse(good), FakeResponse(bad)]

        def seq(*a, **kw):
            return responses.pop(0)

        jobs = [
            {"sitekey": "0xA", "url": "https://example.com/"},
            {"sitekey": "0xB", "url": "https://example.com/"},
        ]
        with mock.patch.object(mod, "urlopen", side_effect=seq):
            results = mod.solve_many("pk_test", jobs, retries=1)
        self.assertEqual(results[0]["token"], "0.GOOD")
        self.assertIn("error", results[1])


class TestCliSurface(unittest.TestCase):
    def test_parser_version(self):
        with self.assertRaises(SystemExit) as ctx:
            mod.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)

    def test_requires_sitekey_or_page(self):
        with self.assertRaises(SystemExit) as ctx:
            mod.main(["--url", "https://example.com/"])
        self.assertEqual(ctx.exception.code, 2)

    def test_requires_url(self):
        with self.assertRaises(SystemExit) as ctx:
            mod.main(["--sitekey", "0xKEY"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
