# MCP server

Core Odoo exposes its agent tools over the Model Context Protocol:

```bash
core-odoo mcp serve
```

Tools:

| Tool | Purpose |
|---|---|
| `project_list` | List registered projects/environments |
| `catalog_models` | Models, fields and ACL from a running environment |
| `generate_module` | Odoo 20 module scaffold |
| `generate_resource` | Add/replace a `backend.yaml` resource |
| `generate_sdk` | Typed TypeScript client |
| `generate_frontend` | Login + generic CRUD frontend |
| `check_project` | Contract/module/ACL/frontend validation |
| `deploy_project` | Deploy through the orchestrator |
| `environment_logs` | Tail environment logs |

## OpenCode

`opencode.json` in the repository root enables the server automatically. After
changing it, restart OpenCode. Tools appear prefixed with `core-odoo_`.

## Claude Code

`.mcp.json` provides the same local server. Claude Code loads project MCP servers
from that file.

## Cursor

`.cursor/mcp.json` provides the same configuration.

## Requirements

The MCP server runs the CLI from the repository, so `uv` and the CLI dependencies
must be installed. It uses the same `.env` (`CORE_API_URL`, `CORE_API_TOKEN`) and
Docker access as the CLI.
