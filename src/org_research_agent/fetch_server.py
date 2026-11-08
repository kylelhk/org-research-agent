"""MCP server that gives the agent one tool: fetch_page.

Claude Code starts this server for each organisation, with that
organisation's website, the page cap, and where to write the fetch log.
"""

from __future__ import annotations

import argparse

from mcp.server.mcpserver import MCPServer

from org_research_agent.fetcher import PageFetcher

SERVER_NAME = "fetcher"
TOOL_NAME = "fetch_page"
# How Claude Code names the tool: mcp__<server>__<tool>.
QUALIFIED_TOOL_NAME = f"mcp__{SERVER_NAME}__{TOOL_NAME}"


def build_server(fetcher: PageFetcher) -> MCPServer:
    server = MCPServer(SERVER_NAME)

    @server.tool(name=TOOL_NAME)
    def fetch_page(url: str) -> str:
        """Read one page from the organisation's own website.

        Returns the page's visible text and its same-site links. Pages on
        other websites, staff profile pages, pages blocked by robots.txt, and
        anything past the page limit are refused.
        """
        return fetcher.fetch(url)

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="The organisation's website host.")
    parser.add_argument("--max-pages", type=int, required=True)
    parser.add_argument("--log", required=True, help="Where to append the fetch log.")
    args = parser.parse_args(argv)

    fetcher = PageFetcher(args.host, args.max_pages, args.log)
    build_server(fetcher).run()


if __name__ == "__main__":
    main()
