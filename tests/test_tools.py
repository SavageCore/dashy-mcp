"""Offline tests: one per Dashy API endpoint, plus error-path tests.

No network. Each tool call is checked against the exact HTTP request it should
produce (method, path incl. URL-encoding, JSON body) via httpx.MockTransport,
using FastMCP's in-memory Client (see https://gofastmcp.com/development/tests).
"""

import json

import httpx
import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.exceptions import ToolError

import dashy_mcp


class Recorder:
    """Captures the single request made during a test and replays a canned response."""

    def __init__(self):
        self.method = None
        self.url = None
        self.headers = None
        self.json = None
        self.response = httpx.Response(200, json={"success": True})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.method = request.method
        self.url = request.url
        self.headers = request.headers
        self.json = json.loads(request.content) if request.content else None
        return self.response


@pytest.fixture
def recorder():
    return Recorder()


@pytest_asyncio.fixture
async def server(recorder, monkeypatch):
    transport = httpx.MockTransport(recorder.handler)
    client = dashy_mcp.build_client("https://dashy.example.com", "test-token", transport=transport)
    monkeypatch.setattr(dashy_mcp, "_client", client)
    monkeypatch.setattr(dashy_mcp, "CONFIG_FILE", "conf.yml")
    yield dashy_mcp.mcp
    await client.aclose()


async def call(server, name, **kwargs):
    async with Client(server) as c:
        return await c.call_tool(name, kwargs)


# --- one test per endpoint --------------------------------------------------

async def test_1_list_config_files(server, recorder):
    recorder.response = httpx.Response(200, json={"success": True, "files": ["conf.yml"]})
    result = await call(server, "dashy_list_config_files")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/config"
    assert result.data == {"success": True, "files": ["conf.yml"]}


async def test_2_get_config(server, recorder):
    await call(server, "dashy_get_config")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/config/conf.yml"


async def test_3_replace_config(server, recorder):
    cfg = {"pageInfo": {"title": "X"}, "sections": []}
    await call(server, "dashy_replace_config", config=cfg)
    assert recorder.method == "PUT"
    assert recorder.url.path == "/api/config/conf.yml"
    assert recorder.json == cfg


async def test_4_get_key(server, recorder):
    await call(server, "dashy_get_key", key="pageInfo")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/config/conf.yml/pageInfo"


async def test_5_set_key(server, recorder):
    await call(server, "dashy_set_key", key="pageInfo", value={"title": "X"})
    assert recorder.method == "PUT"
    assert recorder.url.path == "/api/config/conf.yml/pageInfo"
    assert recorder.json == {"title": "X"}


async def test_6_add_section(server, recorder):
    section = {"name": "Infra", "items": []}
    recorder.response = httpx.Response(201, json={"success": True, "index": 0, "section": section})
    await call(server, "dashy_add_section", section=section)
    assert recorder.method == "POST"
    assert recorder.url.path == "/api/config/conf.yml/sections"
    assert recorder.json == section


async def test_7_get_section(server, recorder):
    await call(server, "dashy_get_section", sid="Media Center")
    assert recorder.method == "GET"
    assert recorder.url.raw_path == b"/api/config/conf.yml/sections/Media%20Center"


async def test_8_update_section(server, recorder):
    await call(server, "dashy_update_section", sid="0", patch={"name": "New"})
    assert recorder.method == "PATCH"
    assert recorder.url.path == "/api/config/conf.yml/sections/0"
    assert recorder.json == {"name": "New"}


async def test_9_delete_section(server, recorder):
    await call(server, "dashy_delete_section", sid="0")
    assert recorder.method == "DELETE"
    assert recorder.url.path == "/api/config/conf.yml/sections/0"


async def test_10_list_items(server, recorder):
    recorder.response = httpx.Response(200, json=[{"title": "Plex"}])
    result = await call(server, "dashy_list_items", sid="0")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/config/conf.yml/sections/0/items"
    assert result.data == [{"title": "Plex"}]


async def test_11_add_item(server, recorder):
    item = {"title": "Plex", "url": "https://plex.local"}
    recorder.response = httpx.Response(201, json={"success": True, "index": 0, "item": item})
    await call(server, "dashy_add_item", sid="0", item=item)
    assert recorder.method == "POST"
    assert recorder.url.path == "/api/config/conf.yml/sections/0/items"
    assert recorder.json == item


async def test_12_get_item(server, recorder):
    await call(server, "dashy_get_item", sid="0", iid="Plex")
    assert recorder.method == "GET"
    assert recorder.url.path == "/api/config/conf.yml/sections/0/items/Plex"


async def test_13_update_item(server, recorder):
    await call(server, "dashy_update_item", sid="Media Center", iid="Plex", patch={"url": "https://x"})
    assert recorder.method == "PATCH"
    assert recorder.url.raw_path == b"/api/config/conf.yml/sections/Media%20Center/items/Plex"
    assert recorder.json == {"url": "https://x"}


async def test_14_delete_item(server, recorder):
    await call(server, "dashy_delete_item", sid="0", iid="0")
    assert recorder.method == "DELETE"
    assert recorder.url.path == "/api/config/conf.yml/sections/0/items/0"


# --- filename override -------------------------------------------------------

async def test_filename_override_used_instead_of_default(server, recorder):
    await call(server, "dashy_get_config", filename="other.yml")
    assert recorder.url.path == "/api/config/other.yml"


# --- auth header --------------------------------------------------------------

async def test_token_sent_as_bearer_header(server, recorder):
    await call(server, "dashy_list_config_files")
    assert recorder.headers["authorization"] == "Bearer test-token"


async def test_no_token_means_no_authorization_header(recorder, monkeypatch):
    transport = httpx.MockTransport(recorder.handler)
    client = dashy_mcp.build_client("https://dashy.example.com", None, transport=transport)
    monkeypatch.setattr(dashy_mcp, "_client", client)
    monkeypatch.setattr(dashy_mcp, "CONFIG_FILE", "conf.yml")
    await call(dashy_mcp.mcp, "dashy_list_config_files")
    assert "authorization" not in recorder.headers
    await client.aclose()


# --- error paths ---------------------------------------------------------------

async def test_404_error_message_reaches_caller(server, recorder):
    recorder.response = httpx.Response(404, json={"success": False, "message": "Section 'x' not found"})
    with pytest.raises(ToolError, match="Section 'x' not found"):
        await call(server, "dashy_get_section", sid="x")


async def test_401_error_surfaces_status(server, recorder):
    recorder.response = httpx.Response(401, json={"success": False, "message": "Unauthorized"})
    with pytest.raises(ToolError, match="401"):
        await call(server, "dashy_list_config_files")


async def test_api_disabled_message_passthrough(server, recorder):
    recorder.response = httpx.Response(
        404, json={"success": False, "message": "API not enabled. Set ENABLE_API=true to use the REST API."}
    )
    with pytest.raises(ToolError, match="API not enabled"):
        await call(server, "dashy_list_config_files")


async def test_non_json_error_body_does_not_crash(server, recorder):
    recorder.response = httpx.Response(502, text="<html>Bad Gateway</html>")
    with pytest.raises(ToolError, match="502"):
        await call(server, "dashy_list_config_files")


# --- main() ----------------------------------------------------------------

def test_main_requires_dashy_url(monkeypatch):
    monkeypatch.delenv("DASHY_URL", raising=False)
    with pytest.raises(SystemExit):
        dashy_mcp.main()
