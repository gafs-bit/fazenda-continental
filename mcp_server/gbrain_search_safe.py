"""MCP server wrapping gbrain keyword search with a "no match" fallback.

Testing on 2026-07-08 found that the gbrain MCP search tool, as wired into
this session, returns confident-looking "keyword_exact" scored results for
IDs that do not exist anywhere in the data (e.g. "Romaneio 99999", "placa
ZZZ9999") with no signal that nothing actually matched. `gbrain call search`
(the same underlying tool, invoked locally via the CLI) does not reproduce
this — it correctly returns an empty list for the same queries. This wrapper
routes through that reliable local path and turns an empty result into an
explicit "no match" message, so a caller can't mistake silence (or a
plausible-but-wrong top hit) for a real answer.
"""

import json
import subprocess
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gbrain-search-safe")


@mcp.tool()
def search_with_fallback(query: str, limit: int = 10, mode: Optional[str] = None) -> dict:
    """Keyword search over gbrain via the local CLI path, not the raw MCP
    search tool (which was found to fabricate "keyword_exact" matches for
    Romaneio/placa/Talhão values that don't exist in the data). Returns
    {"match_found": false, "message": ...} when nothing actually matches,
    instead of an empty or misleadingly-scored result. Use this for any
    exact-ID lookup where you need to know for certain whether a record
    exists before answering."""
    payload = {"query": query, "limit": limit}
    if mode:
        payload["mode"] = mode
    proc = subprocess.run(
        ["gbrain", "call", "search", json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return {"match_found": False, "message": f"gbrain search failed: {proc.stderr.strip()}"}
    results = json.loads(proc.stdout)
    if not results:
        return {"match_found": False, "message": f'No match found for "{query}".'}
    return {"match_found": True, "results": results}


if __name__ == "__main__":
    mcp.run()
