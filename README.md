# dashy-mcp

MCP server exposing [Dashy](https://github.com/lissy93/dashy)'s [REST API](https://dashy.to/docs/api)
as tools, so an LLM can read and edit your dashboard config: sections, items (tiles),
and top-level config keys.

Built with [FastMCP](https://gofastmcp.com).

## Enabling the API on your Dashy server

Dashy's API is opt-in and disabled by default. Enabling and securing it (via
`ENABLE_API`, `API_TOKEN`, and/or Dashy's existing user auth) is server-side
configuration specific to how you run Dashy, and out of scope for this project -
see Dashy's own docs: [Enabling the API](https://dashy.to/docs/api#enabling-the-api).

## Install

Download a wheel from the [latest release](https://github.com/SavageCore/dashy-mcp/releases/latest)
and install it as a `uv` tool (no repo checkout needed):

```bash
uv tool install dashy_mcp-*.whl
```

This puts a `dashy-mcp` command on your PATH. Register it with Claude Code:

```bash
claude mcp add dashy \
  --env DASHY_URL=https://your-dashy-host \
  --env DASHY_TOKEN=<token> \
  -- dashy-mcp
```

### From source

```bash
uv sync
cp .env.example .env   # fill in DASHY_URL and DASHY_TOKEN
```

```bash
claude mcp add dashy \
  --env DASHY_URL=https://your-dashy-host \
  --env DASHY_TOKEN=<token> \
  -- uv run --directory /path/to/dashy-mcp dashy-mcp
```

## Config

| Env var | Required | Default |
|---|---|---|
| `DASHY_URL` | yes | - |
| `DASHY_TOKEN` | no | none (no auth header sent) |
| `DASHY_CONFIG_FILE` | no | `conf.yml` |

## Tools

**4 resource-scoped tools**, each covering multiple Dashy API endpoints (14
total) via an `operation` parameter. Call a tool with `operation` set to one
of its listed operations and an `arguments` dict matching that operation's
parameters — the tool's own description (visible to your MCP client) lists
every operation, its signature, and a one-line doc.

| Tool | Operations | Covers |
|---|---|---|
| `dashy_item` | 5 | List/add/get/update/delete items (tiles) |
| `dashy_section` | 4 | Add/get/update/delete sections |
| `dashy_config` | 3 | List config files, get/replace a config file |
| `dashy_key` | 2 | Get/set a top-level config key |

Example: `dashy_section(operation="dashy_get_section", arguments={"sid": "Media"})`.
Endpoint-level naming is preserved as the `operation` value:

| Operation | Endpoint |
|---|---|
| `dashy_list_config_files` | `GET /api/config` |
| `dashy_get_config` | `GET /api/config/:file` |
| `dashy_replace_config` | `PUT /api/config/:file` |
| `dashy_get_key` | `GET /api/config/:file/:key` |
| `dashy_set_key` | `PUT /api/config/:file/:key` |
| `dashy_add_section` | `POST /api/config/:file/sections` |
| `dashy_get_section` | `GET /api/config/:file/sections/:sid` |
| `dashy_update_section` | `PATCH /api/config/:file/sections/:sid` |
| `dashy_delete_section` | `DELETE /api/config/:file/sections/:sid` |
| `dashy_list_items` | `GET /api/config/:file/sections/:sid/items` |
| `dashy_add_item` | `POST /api/config/:file/sections/:sid/items` |
| `dashy_get_item` | `GET /api/config/:file/sections/:sid/items/:iid` |
| `dashy_update_item` | `PATCH /api/config/:file/sections/:sid/items/:iid` |
| `dashy_delete_item` | `DELETE /api/config/:file/sections/:sid/items/:iid` |

`sid`/`iid` accept either a zero-based index or an exact section name / item title.
`filename` defaults to `conf.yml` (or `DASHY_CONFIG_FILE`) on every operation.
`PATCH`-based updates are a shallow merge: only given fields change, and a nested
array included in the patch replaces the existing one wholesale.

## Development

```bash
make help  # list all commands
```

| Command | Does |
|---|---|
| `make sync` | `uv sync` |
| `make test` | Offline tests - one per endpoint, mocked HTTP |
| `make test-integration` | Tests against the live instance (needs `DASHY_URL`/`DASHY_TOKEN`) |
| `make build` | Build wheel + sdist into `dist/` |
| `make bump-patch` / `bump-minor` / `bump-major` | Bump the version in `pyproject.toml` + `uv.lock` |
| `make clean` | Remove build artifacts |

The release workflow (`.github/workflows/release.yml`) builds and publishes to
[Releases](https://github.com/SavageCore/dashy-mcp/releases) whenever a `v*` tag is
pushed - so the usual flow is `make bump-patch`, commit, then tag and push.

The integration suite reads real config and, for the write lifecycle test, creates and
then deletes a scratch section named `mcp-test-<uuid>` - never touches your real
sections. Dashy also auto-backs up every write to `user-data/config-backups/` as a
second safety net.
