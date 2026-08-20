"""Milestone 6 -- MCP client wrapper for the mock EHR/scheduling MCP server.

Opens ONE stdio session per `McpToolSession` (i.e. per agent tool-calling
loop, not per tool call) -- spawning the server subprocess and doing the MCP
handshake on every single tool call would be wasteful inside a multi-turn
tool loop. See app/agents/referral_agent.py for the intended usage: one
`async with McpToolSession() as session:` wraps the whole loop.
"""

import json
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult

_SERVER_PARAMS = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server.server"])


def _parse_tool_result(result: CallToolResult) -> dict | list:
    if result.isError:
        text = result.content[0].text if result.content else "MCP tool call failed."
        return {"success": False, "error": text}
    if result.structuredContent is not None:
        return result.structuredContent.get("result", result.structuredContent)
    if len(result.content) == 1:
        return json.loads(result.content[0].text)
    return [json.loads(item.text) for item in result.content]


class McpToolSession:
    """Async context manager wrapping one MCP ClientSession over stdio."""

    def __init__(self):
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "McpToolSession":
        read, write = await self._stack.enter_async_context(stdio_client(_SERVER_PARAMS))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._stack.aclose()

    async def call_tool(self, name: str, arguments: dict) -> dict | list:
        assert self._session is not None, "McpToolSession used outside its `async with` block."
        result = await self._session.call_tool(name, arguments)
        return _parse_tool_result(result)
