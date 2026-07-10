"""Telegram bot front-end for farm data Q&A.

Each incoming message is answered by `ask_hermes.py`, which runs the
`hermes` CLI with the `farm-telegram` skill (see
`~/.hermes/skills/farm-telegram/SKILL.md`, mirrored into this repo at
`agent/hermes-skill/farm-telegram/SKILL.md`). That skill carries the
plain-language presentation rules and the gbrain-vs-farm-stats tool-choice
rules that this file used to enforce itself via --append-system-prompt +
an ALLOWED_TOOLS list (see docs/PROJECT_LOG.md for the 2026-07-08 backend
swap this replaced).
"""

import logging
import os
import sys
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

TELEGRAM_MAX_MESSAGE_LENGTH = 4096

if REPO_DIR not in sys.path:
    sys.path.insert(0, str(REPO_DIR))
from telegram_bot.ask_hermes import ask_hermes_verified as _ask_hermes_verified  # noqa: E402


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
        answer, ok, reason = await _ask_hermes_verified(message.text)
    except RuntimeError as exc:
        logger.exception("Failed to answer question")
        await message.reply_text(f"Something went wrong answering that: {exc}")
        return

    # Two-pass self-check guard (B): withhold a contradicted answer rather
    # than deliver a plausible-but-wrong figure to a non-technical reader.
    if not ok:
        logger.error("Self-check FAILED for %r: %s", message.text, reason)
        await message.reply_text(
            "I'm not confident enough in that answer to send it — the data "
            "didn't check out on a second pass. Please rephrase or ask for a "
            "specific romaneio/placa and I'll look it up directly."
        )
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
