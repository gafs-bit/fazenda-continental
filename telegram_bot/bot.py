"""Telegram bot front-end for farm data Q&A.

Each incoming message is answered by running `claude -p` from this repo's
root, so it automatically picks up CLAUDE.md's rules and the farm-stats /
gbrain / gbrain-search-safe MCP tools registered in .mcp.json — no
query-routing logic is duplicated here. Access is restricted to an
allowlist of Telegram user IDs since the underlying data contains driver
names, plates, and client document numbers (see CLAUDE.md).
"""

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logger = logging.getLogger("farm-telegram-bot")

BOT_DIR = Path(__file__).resolve().parent
REPO_DIR = BOT_DIR.parent

load_dotenv(BOT_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_IDS = {
    int(uid.strip())
    for uid in os.environ.get("ALLOWED_TELEGRAM_USER_IDS", "").split(",")
    if uid.strip()
}
CLAUDE_TIMEOUT_SECONDS = int(os.environ.get("CLAUDE_TIMEOUT_SECONDS", "180"))

# Mirrors CLAUDE.md: gbrain-search-safe (not raw gbrain search) for exact-ID
# lookups, gbrain query for fuzzy questions, farm-stats for aggregates. No
# Bash/Edit/Write/etc — this bot can only ever read farm data, nothing else.
ALLOWED_TOOLS = ",".join(
    [
        "mcp__gbrain-search-safe__search_with_fallback",
        "mcp__gbrain__query",
        "mcp__farm-stats__pesagens_count",
        "mcp__farm-stats__pesagens_aggregate",
        "mcp__farm-stats__pesagens_extremes",
        "mcp__farm-stats__pesagens_date_range",
        "mcp__farm-stats__pesagens_group_counts",
        "mcp__farm-stats__pesagens_distinct_count",
        "mcp__farm-stats__fretes_aggregate",
    ]
)

TELEGRAM_MAX_MESSAGE_LENGTH = 4096

# This is a one-shot message to a non-technical farm employee, not an
# interactive dev session: they cannot reply mid-turn, and they should never
# see tool names, file paths, code, or CLAUDE.md referenced directly.
TELEGRAM_SYSTEM_PROMPT = """You are answering a single Telegram message from \
a Fazenda Continental farm employee who is not a programmer. This is your \
only chance to respond -- they cannot reply to a follow-up question, so \
always give a final, direct answer instead of asking one.

Never mention tool names, function names, file paths, line numbers, \
CLAUDE.md, MCP, or any other implementation detail -- the reader has no \
context for any of that and does not need it.

If the current tools genuinely cannot answer the question, say so in one or \
two plain sentences describing what you *can* look up instead (e.g. totals/\
averages by driver, plate, or date; specific romaneio/placa/talhão lookups) \
-- do not explain why in technical terms, and do not propose a code change.

Answer in the same language the question was asked in."""


async def ask_claude(question: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "claude",
        "-p",
        question,
        "--allowedTools",
        ALLOWED_TOOLS,
        "--append-system-prompt",
        TELEGRAM_SYSTEM_PROMPT,
        "--no-session-persistence",
        cwd=str(REPO_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=CLAUDE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"claude did not respond within {CLAUDE_TIMEOUT_SECONDS}s")

    if proc.returncode != 0:
        raise RuntimeError(stderr.decode().strip() or "claude exited with an error")

    return stdout.decode().strip()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None or not message.text:
        return

    if user.id not in ALLOWED_USER_IDS:
        logger.warning(
            "Rejected message from unauthorized user id=%s username=%s",
            user.id,
            user.username,
        )
        await message.reply_text(
            "You're not authorized to use this bot. Ask the project owner to "
            f"add your Telegram user id ({user.id}) to the allowlist."
        )
        return

    logger.info("Question from user id=%s username=%s: %s", user.id, user.username, message.text)
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    try:
        answer = await ask_claude(message.text)
    except RuntimeError as exc:
        logger.exception("Failed to answer question")
        await message.reply_text(f"Something went wrong answering that: {exc}")
        return

    if not answer:
        answer = "No answer was returned."

    for i in range(0, len(answer), TELEGRAM_MAX_MESSAGE_LENGTH):
        await message.reply_text(answer[i : i + TELEGRAM_MAX_MESSAGE_LENGTH])


def main() -> None:
    if not ALLOWED_USER_IDS:
        logger.warning(
            "ALLOWED_TELEGRAM_USER_IDS is empty -- every message will be rejected "
            "with a reply that includes the sender's user id. Message the bot, "
            "copy that id into .env, and restart."
        )
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot starting (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
