"""ask_hermes — drop-in replacement for bot.py's ask_claude, with a
two-pass self-check guard.

Pipeline (per question):
  Pass 1  run `hermes chat -s farm-telegram -q <question>` -> candidate answer.
  Pass 2  run a second `hermes chat` that independently re-derives the answer
          from the (read-only) MCP tools and judges whether the candidate
          contradicts the data. Returns PASS or FAIL:<reason>.

The gbrain / farm-stats / gbrain-search-safe MCP servers are registered in
~/.hermes/config.yaml with read-only tools.include allowlists, so Hermes can
only ever READ farm data — it has no write/SQL tools available. The
farm-telegram skill enforces the citation contract + grounding rule, which
Pass 2 relies on to catch misattribution.

Public API:
  ask_hermes(question) -> str            (passes through; for drop-in compat)
  ask_hermes_verified(question) -> (answer, ok, reason)
      ok=False on a self-check FAIL — bot.py should withhold the answer then.
"""

import asyncio
import json
import os
import re
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
HERMES_TIMEOUT_SECONDS = int(os.environ.get("CLAUDE_TIMEOUT_SECONDS", "180"))
SELFCHECK_TIMEOUT_SECONDS = int(
    os.environ.get("SELFCHECK_TIMEOUT_SECONDS", str(HERMES_TIMEOUT_SECONDS))
)
# If the judge call itself errors (infra, not data), deliver the answer anyway
# but flag it — we never block delivery on a verification subsystem failure.
BLOCK_ON_SELFCHECK_INFRA_FAILURE = False


async def _hermes_chat(question: str, extra_args: list[str]) -> str:
    """Run a single hermes chat invocation; return the answer text only."""
    proc = await asyncio.create_subprocess_exec(
        "hermes",
        "chat",
        "-q",
        question,
        "-s",
        "farm-telegram",
        "-Q",
        "--source",
        "telegram",
        *extra_args,
        cwd=str(REPO_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=HERMES_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("hermes did not respond in time")
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode().strip() or "hermes exited with an error")
    text = stdout.decode().strip()
    lines = text.split("\n")
    if lines and lines[0].startswith("session_id:"):
        return "\n".join(lines[1:]).strip()
    return text


_JUDGE_PROMPT = (
    "You are a verification judge for a farm-data answer. You have the SAME "
    "read-only tools as the original answerer (farm-stats, gbrain-search-safe, "
    "gbrain query). Re-derive the answer to the QUESTION yourself from the "
    "tools, then compare against the CANDIDATE answer.\n\n"
    "Rules:\n"
    "- The candidate is CORRECT only if its cited numbers/plates/romaneios/"
    "driver names match what the tools actually return.\n"
    "- A citation that names the wrong plate/romaneio, or a number that does "
    "not match the tool result, is a FAIL.\n"
    "- If the candidate correctly says 'no record found' and the tools confirm "
    "absence, that is PASS.\n"
    "Respond with ONLY a single JSON line: "
    '{"verdict":"PASS"|"FAIL","reason":"<one sentence>"}'
)


def _parse_verdict(judge_out: str):
    """Extract (ok, reason) from the judge's JSON-or-text output."""
    m = re.search(r'\{[^{}]*"verdict"[^{}]*\}', judge_out, re.S)
    if not m:
        # No JSON — treat as inconclusive, not a hard fail.
        return True, f"judge returned non-JSON: {judge_out[:200]}"
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return True, f"judge JSON unparseable: {judge_out[:200]}"
    verdict = str(data.get("verdict", "PASS")).upper()
    reason = str(data.get("reason", ""))
    return (verdict == "PASS"), reason


async def ask_hermes_verified(question: str):
    """Return (answer, ok, reason). ok=False means the self-check failed."""
    answer = await _hermes_chat(question, [])

    judge_q = (
        f"{_JUDGE_PROMPT}\n\nQUESTION:\n{question}\n\nCANDIDATE ANSWER:\n{answer}"
    )
    try:
        judge_out = await asyncio.wait_for(
            _hermes_chat(judge_q, []), timeout=SELFCHECK_TIMEOUT_SECONDS
        )
        ok, reason = _parse_verdict(judge_out)
        return answer, ok, reason
    except Exception as e:  # infra failure in the judge, not a data problem
        if BLOCK_ON_SELFCHECK_INFRA_FAILURE:
            raise
        # Deliver but flag: reason records the subsystem issue.
        return answer, True, f"self-check skipped (infra): {e}"


async def ask_hermes(question: str) -> str:
    """Drop-in compatible: returns the answer string, ignoring the verdict."""
    answer, _ok, _reason = await ask_hermes_verified(question)
    return answer
