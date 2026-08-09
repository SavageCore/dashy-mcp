"""MCP server exposing Dashy's REST API (https://dashy.to/docs/api) as tools.

One tool per API endpoint (see README for the full list). Auth is a bearer
DASHY_TOKEN sent as `Authorization: Bearer <token>` -- the only auth mode this
Dashy instance is configured for.

ponytail: no Basic-auth/OIDC support -- this instance has no Dashy `auth:`
block configured, only API_TOKEN. Add if the instance grows real user auth.
"""

import os
import sys
from typing import Any
from urllib.parse import quote

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

DESTRUCTIVE = ToolAnnotations(destructiveHint=True)

# Dashy responses are plain JSON. `dict[str, Any]` (not bare `Any`) matters here:
# FastMCP needs a concrete schema to build MCP structured content, and skips that
# step entirely for an `Any` return type -- which silently makes Client.call_tool's
# `.data` come back None for any tool returning a JSON array (dashy_list_items,
# dashy_get_key on sections/pages). Verified against fastmcp 3.4.6.
JSONObj = dict[str, Any]
JSONVal = JSONObj | list[Any]

mcp = FastMCP("dashy-mcp")

_client: httpx.AsyncClient | None = None
CONFIG_FILE = "conf.yml"


def build_client(base_url: str, token: str | None, transport: httpx.BaseTransport | None = None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(base_url=f"{base_url.rstrip('/')}/api", headers=headers, transport=transport)


async def _req(method: str, path: str, json: Any = None) -> JSONVal:
    assert _client is not None, "client not configured"
    r = await _client.request(method, path, json=json)
    if r.status_code >= 400:
        try:
            msg = r.json().get("message", r.text)
        except ValueError:
            msg = r.text
        raise ToolError(f"Dashy API {r.status_code}: {msg}")
    return r.json()


def _f(filename: str) -> str:
    return quote(filename or CONFIG_FILE)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def dashy_list_config_files() -> JSONObj:
    """List the YAML config files available on the Dashy instance."""
    return await _req("GET", "/config")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def dashy_get_config(filename: str = "") -> JSONObj:
    """Get a full Dashy config file as JSON. Defaults to conf.yml."""
    return await _req("GET", f"/config/{_f(filename)}")


@mcp.tool(annotations=DESTRUCTIVE)
async def dashy_replace_config(config: dict, filename: str = "") -> JSONObj:
    """Replace an entire Dashy config file. `config` must be a full config object
    (pageInfo, appConfig, sections, pages) -- this is a complete overwrite, not a merge."""
    return await _req("PUT", f"/config/{_f(filename)}", config)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def dashy_get_key(key: str, filename: str = "") -> JSONVal:
    """Get one top-level config key: pageInfo, appConfig, sections, or pages."""
    return await _req("GET", f"/config/{_f(filename)}/{quote(key)}")


@mcp.tool(annotations=DESTRUCTIVE)
async def dashy_set_key(key: str, value: Any, filename: str = "") -> JSONObj:
    """Replace one top-level config key (pageInfo, appConfig, sections, or pages)
    with `value`. This is a complete replacement of that key, not a merge."""
    return await _req("PUT", f"/config/{_f(filename)}/{quote(key)}", value)


@mcp.tool
async def dashy_add_section(section: dict, filename: str = "") -> JSONObj:
    """Add a new section (a group of tiles) to the dashboard. `section` requires
    a `name`; common keys: name, icon, items, displayData."""
    return await _req("POST", f"/config/{_f(filename)}/sections", section)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def dashy_get_section(sid: str, filename: str = "") -> JSONObj:
    """Get one section by zero-based index or exact section name."""
    return await _req("GET", f"/config/{_f(filename)}/sections/{quote(sid)}")


@mcp.tool
async def dashy_update_section(sid: str, patch: dict, filename: str = "") -> JSONObj:
    """Shallow-merge `patch` into a section (by index or exact name). Only the
    given fields change; a nested array in `patch` replaces the existing one wholesale."""
    return await _req("PATCH", f"/config/{_f(filename)}/sections/{quote(sid)}", patch)


@mcp.tool(annotations=DESTRUCTIVE)
async def dashy_delete_section(sid: str, filename: str = "") -> JSONObj:
    """Delete a section (by index or exact name), including all its items."""
    return await _req("DELETE", f"/config/{_f(filename)}/sections/{quote(sid)}")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def dashy_list_items(sid: str, filename: str = "") -> list[Any]:
    """List the items (tiles) in a section, by section index or exact name."""
    return await _req("GET", f"/config/{_f(filename)}/sections/{quote(sid)}/items")


@mcp.tool
async def dashy_add_item(sid: str, item: dict, filename: str = "") -> JSONObj:
    """Add a new item (tile) to a section (by index or exact name). `item` requires
    a `title`; common keys: title, url, icon, description, target."""
    return await _req("POST", f"/config/{_f(filename)}/sections/{quote(sid)}/items", item)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def dashy_get_item(sid: str, iid: str, filename: str = "") -> JSONObj:
    """Get one item (tile) by index or exact title, within a section by index or exact name."""
    return await _req("GET", f"/config/{_f(filename)}/sections/{quote(sid)}/items/{quote(iid)}")


@mcp.tool
async def dashy_update_item(sid: str, iid: str, patch: dict, filename: str = "") -> JSONObj:
    """Shallow-merge `patch` into an item (by index or exact title), within a section
    (by index or exact name). Only the given fields change."""
    return await _req("PATCH", f"/config/{_f(filename)}/sections/{quote(sid)}/items/{quote(iid)}", patch)


@mcp.tool(annotations=DESTRUCTIVE)
async def dashy_delete_item(sid: str, iid: str, filename: str = "") -> JSONObj:
    """Delete an item (tile) by index or exact title, within a section by index or exact name."""
    return await _req("DELETE", f"/config/{_f(filename)}/sections/{quote(sid)}/items/{quote(iid)}")


def main() -> None:
    global _client, CONFIG_FILE
    url = os.environ.get("DASHY_URL")
    if not url:
        print("DASHY_URL environment variable is required (e.g. https://dashy.example.com)", file=sys.stderr)
        raise SystemExit(1)
    CONFIG_FILE = os.environ.get("DASHY_CONFIG_FILE", "conf.yml")
    _client = build_client(url, os.environ.get("DASHY_TOKEN"))
    mcp.run()


if __name__ == "__main__":
    main()
