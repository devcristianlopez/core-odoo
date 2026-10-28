# MCP server

Core Odoo exposes its agent tools over the Model Context Protocol:

```bash
core-odoo mcp serve
```

Tools:

| Tool | Purpose |
|---|---|
| `project_list` | List registered projects/environments |
| `list_iterations` | Versioned project iterations |
| `create_iteration` | Snapshot the project source |
| `restore_iteration` | Restore source from a snapshot |
| `iteration_diff` | Compare two iterations |
| `backup_iteration` | Create a DB dump linked to an iteration |
| `catalog_models` | Models, fields and ACL from a running environment |
| `generate_module` | Odoo 20 module scaffold |
| `generate_resource` | Add/replace a `backend.yaml` resource |
| `generate_sdk` | Typed TypeScript client |
| `generate_frontend` | Login + generic CRUD frontend |
| `check_project` | Contract/module/ACL/frontend validation |
| `deploy_project` | Deploy through the orchestrator (`modules` to install Odoo apps, `confirm` required for prod) |
| `rollback_environment` | Roll back to the last successful iteration (`confirm` required for prod) |
| `restore_iteration_db` | Load an iteration dump into an environment (`confirm` required for prod) |
| `promote_environment` | Clone a source environment into production (`iteration`, `neutralize`, `skip_smoke`) |
| `list_deploy_requests` | List production requests |
| `request_deploy` | Request production approval |
| `approve_deploy` / `reject_deploy` | Admin decision |
| `environment_logs` | Tail environment logs |

The CLI also exposes `core-odoo env credentials <project> --stage <stage>` for the
generated Odoo admin password; there is no MCP tool for it (it is a human
operation).

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
