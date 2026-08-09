"""Integration tests against a real Dashy instance.

Skipped unless DASHY_URL and DASHY_TOKEN are set. Run with:
    uv run pytest -m integration

Write tests only ever touch a scratch section named "mcp-test-<uuid>",
cleaned up in a finally block so a failing assertion can't leave litter
in the real conf.yml (Dashy also auto-backs up every write, as a second net).
"""

import os
import uuid

import pytest
from fastmcp import Client

import dashy_mcp

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.environ.get("DASHY_URL") and os.environ.get("DASHY_TOKEN")),
        reason="requires DASHY_URL and DASHY_TOKEN",
    ),
]


@pytest.fixture(autouse=True)
def configure_client():
    dashy_mcp._client = dashy_mcp.build_client(os.environ["DASHY_URL"], os.environ["DASHY_TOKEN"])
    dashy_mcp.CONFIG_FILE = os.environ.get("DASHY_CONFIG_FILE", "conf.yml")
    yield


async def call(name, **kwargs):
    async with Client(dashy_mcp.mcp) as c:
        return await c.call_tool(name, kwargs)


async def test_list_config_files_includes_conf_yml():
    result = await call("dashy_list_config_files")
    assert "conf.yml" in result.data["files"]


async def test_get_config_returns_full_config():
    result = await call("dashy_get_config")
    assert "sections" in result.data


async def test_get_key_pageinfo():
    result = await call("dashy_get_key", key="pageInfo")
    assert isinstance(result.data, dict)


async def test_section_and_item_lifecycle():
    name = f"mcp-test-{uuid.uuid4().hex[:8]}"
    try:
        added = await call("dashy_add_section", section={"name": name, "items": []})
        sid = str(added.data["index"])

        fetched = await call("dashy_get_section", sid=name)
        assert fetched.data["name"] == name

        patched = await call("dashy_update_section", sid=name, patch={"icon": "fas fa-flask"})
        assert patched.data["section"]["icon"] == "fas fa-flask"

        item = {"title": "mcp-test-item", "url": "https://example.com"}
        added_item = await call("dashy_add_item", sid=name, item=item)
        iid = str(added_item.data["index"])

        fetched_item = await call("dashy_get_item", sid=name, iid="mcp-test-item")
        assert fetched_item.data["url"] == "https://example.com"

        patched_item = await call(
            "dashy_update_item", sid=name, iid="mcp-test-item", patch={"url": "https://example.org"}
        )
        assert patched_item.data["item"]["url"] == "https://example.org"

        items = await call("dashy_list_items", sid=name)
        assert any(i["title"] == "mcp-test-item" for i in items.data)

        await call("dashy_delete_item", sid=name, iid="mcp-test-item")
    finally:
        await call("dashy_delete_section", sid=name)

    # confirm cleanup
    remaining = await call("dashy_get_key", key="sections")
    assert not any(s.get("name") == name for s in remaining.data)
