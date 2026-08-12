# AGENTS.md — dashy-mcp

MCP server exposing Dashy's REST API as tools so an LLM can read and edit dashboard config: sections, items (tiles), and top-level config keys. Uses FastMCP, `uv` for deps.

Exposed as **4 resource-scoped portmanteau tools** (`dashy_config`, `dashy_key`, `dashy_section`, `dashy_item`), not one tool per endpoint — see "Portmanteau registration" below. A prior version registered all 14 endpoints individually; already small, but ported to the same pattern as the rest of the fleet for consistency.

## Testing
- Offline suite: `make test` (or `uv run pytest`)
- Live integration (needs `DASHY_URL`/`DASHY_TOKEN`): `make test-integration`

## Release workflow
Always use the `make bump-*` targets to bump the version (`uv version --bump patch|minor|major`), which updates `pyproject.toml` and `uv.lock` together. Do NOT edit the version by hand.

- Bump: `make bump-patch` (or `bump-minor` / `bump-major`)
- Commit message is **just the version**, e.g. `0.1.2` — nothing else.
- Tag it `v<version>` (e.g. `v0.1.2`).
- Push main and the tag:
  ```
  git push origin main
  git push origin v<version>
  ```
- Then sync the project copy:
  ```
  cd /home/savagecore/Documents/christopfarr/mcp/dashy-mcp
  git fetch origin && git reset --hard origin/main
  ```
- Deploy to the Proxmox host (root SSH key): pull the repo and re-sync the venv:
  ```
  ssh root@192.168.50.3 -- 'cd /root/dashy-mcp && git fetch origin && git reset --hard origin/main && uv sync'
  ```
  **Correction (verified against the live host, this AGENTS.md previously had it backwards):** the opencode config
  (`/root/.config/opencode/opencode.jsonc`) runs `/root/dashy-mcp/.venv/bin/dashy-mcp` — i.e. the repo checkout's own
  venv, not a `uv tool install`. There is no `/root/.local/bin/dashy-mcp` symlink and no uv-tool install for this
  server. `uv tool install --force .` would create one but would NOT change what opencode actually executes, so it's
  a no-op for deployment purposes here — use `uv sync` in the checkout instead, as above.

## Env note
Dashy's API is opt-in. Access is keyed on `DASHY_TOKEN`; keep tokens out of code, logs, and commit messages.

## Portmanteau registration — **do not go back to one tool per endpoint**
- `_GROUPS` near the bottom of `dashy_mcp.py` buckets every endpoint function into one of 4 resource groups (`dashy_config`, `dashy_key`, `dashy_section`, `dashy_item`). `_register_tools()` registers exactly one MCP tool per group via `_register_group`, which wraps the group's functions in a single `dispatch(operation, arguments)` closure. The endpoint functions themselves are unchanged — they're plain callables looked up by name via `globals()`, not separately-registered tools.
- `operation` is typed `Literal[<the group's function names>]`, so FastMCP/pydantic validates it against the real operation list before `dispatch` ever runs — an invalid operation never reaches the group tool's body.
- Adding a new endpoint: write the function as before (no decorator), then add its name to exactly one group in `_GROUPS`. `tests/test_tools.py::test_all_operations_grouped` fails if a name doesn't resolve to a real module attribute.
- If you're tempted to add a per-endpoint `@mcp.tool` decorator back, don't — every endpoint must be reachable only via its group's `operation` enum.
- Annotations: a group tool is `readOnlyHint=True` (`READONLY` — a module constant added during the portmanteau refactor; the file previously only had `DESTRUCTIVE` and used inline `ToolAnnotations(readOnlyHint=True)` per read-only tool) only when *every* operation in it was originally read-only. None of the 4 groups end up all-read-only, since each mixes at least one write.