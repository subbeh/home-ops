#!/usr/bin/env python3
# Self-test for the hermes crawl4ai plugin: blocked reads retry through Tavily, others don't.
# Run with `just docs-test`.
import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest

# The plugin dir is copied to the vps as-is, so keep __pycache__ out of it.
sys.dont_write_bytecode = True


class HTTPStatusError(Exception):
    def __init__(self, response):
        self.response = response


class Response:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, str(body)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPStatusError(self)

    def json(self):
        return self._body


class Client:
    replies = {}

    def __init__(self, **_):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, endpoint, json, headers):
        assert endpoint.endswith("/crawl") and json["browser_config"]["params"]["enable_stealth"]
        return self.replies[json["urls"][0]]


class Tavily:
    calls = []

    def extract(self, urls):
        self.calls.extend(urls)
        if "raise" in urls[0]:
            raise ValueError("Tavily down")
        if "akamai" in urls[0]:
            return [{"url": urls[0], "title": "", "content": "", "error": "Error fetching content"}]
        return [{"url": urls[0], "title": "T", "content": "from tavily", "raw_content": "from tavily", "metadata": {}}]


def stub(name, **attrs):
    sys.modules[name] = types.SimpleNamespace(**attrs)


stub("httpx", AsyncClient=Client, HTTPStatusError=HTTPStatusError)
stub("agent.web_search_provider", WebSearchProvider=object)
stub("tools.url_safety", is_safe_url=lambda u: "internal" not in u)
stub("plugins.web.tavily.provider", TavilyWebSearchProvider=Tavily)

_path = pathlib.Path(__file__).resolve().parent.parent / "ansible/services/data/hermes/crawl4ai/provider.py"
_spec = importlib.util.spec_from_file_location("crawl4ai_provider", _path)
provider = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(provider)
provider._crawl4ai_url = lambda: "https://c4a"
provider._crawl4ai_token = lambda: "t"


def blocked(reason):
    return Response(200, {"success": True, "results": [{"success": False, "error_message": reason}]})


class Extract(unittest.TestCase):
    def test_retry_only_blocked(self):
        Client.replies = {
            "https://ok": Response(200, {"results": [{"success": True, "markdown": {"raw_markdown": "# Home\nhi"}}]}),
            "https://cf": blocked("Blocked by anti-bot protection: Cloudflare JS challenge"),
            "https://akamai": blocked("Blocked by anti-bot protection: Akamai challenge"),
            "https://down": Response(503, "no server"),
            "https://raise": Response(502, "bad gateway"),
            "https://token": Response(401, "bad token"),
        }
        Tavily.calls = []
        urls = ["https://ok", "https://cf", "https://akamai", "https://down", "https://raise", "https://token",
                "http://internal"]
        out = asyncio.run(provider.Crawl4aiWebExtractProvider().extract(urls))
        self.assertEqual([r["url"] for r in out], urls)
        self.assertEqual((out[0]["title"], out[0]["content"]), ("Home", "# Home\nhi"))
        self.assertEqual(out[1]["content"], "from tavily")
        self.assertEqual(out[2]["error"], "Crawl4ai: Blocked by anti-bot protection: Akamai challenge; "
                                          "Tavily retry: Error fetching content")
        self.assertEqual(out[3]["content"], "from tavily")
        self.assertEqual(out[4]["error"], "Crawl4ai HTTP 502: bad gateway; Tavily retry: Tavily down")
        self.assertEqual(out[5]["error"], "Crawl4ai HTTP 401: bad token")
        self.assertIn("Blocked", out[6]["error"])
        self.assertEqual(Tavily.calls, ["https://cf", "https://akamai", "https://down", "https://raise"])


if __name__ == "__main__":
    unittest.main()
