"""MCP server command."""

from __future__ import annotations


def serve() -> None:
    """Serve Core Odoo tools over the Model Context Protocol (stdio)."""
    from ..mcp_server import build_server

    build_server().run(transport="stdio")
