import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_SERVER = PROJECT_ROOT / "mcp-server" / "server.py"

server_params = StdioServerParameters(
    command=sys.executable,
    args=["-u", str(MCP_SERVER)],
    cwd=str(PROJECT_ROOT),
)


def _decode_text_result(text: str) -> Any:
    """Decode JSON encoded MCP tool values, keeping ordinary text unchanged."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


async def call_mcp_tool(tool_name: str, arguments: dict | None = None) -> Any:
    """Start the local MCP server, call one tool, and return its decoded value."""
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments or {})

            if result.isError:
                raise RuntimeError(f"MCP tool '{tool_name}' returned an error.")

            structured = getattr(result, "structuredContent", None)
            if structured is not None:
                if isinstance(structured, dict) and set(structured) == {"result"}:
                    return structured["result"]
                return structured

            decoded = [
                _decode_text_result(item.text)
                for item in result.content
                if hasattr(item, "text")
            ]
            if len(decoded) == 1:
                return decoded[0]
            return decoded


async def list_project_files() -> list[str]:
    result = await call_mcp_tool("list_project_files")
    if not isinstance(result, list) or not all(isinstance(item, str) for item in result):
        raise RuntimeError("MCP returned an invalid project file list.")
    return result


async def read_project_file(path: str) -> str:
    result = await call_mcp_tool("read_file", {"path": path})
    if not isinstance(result, str):
        raise RuntimeError("MCP returned an invalid file content value.")
    return result


async def search_project(query: str) -> list[dict[str, Any]]:
    result = await call_mcp_tool("search_repository", {"query": query})
    if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
        raise RuntimeError("MCP returned invalid repository search results.")
    return result


async def main() -> None:
    files = await list_project_files()
    print("Project files:")
    print("\n".join(files[:30]))
    print("\nSearch results:")
    print(json.dumps(await search_project("syncodex.ai-service.url"), indent=2))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
