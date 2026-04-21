"""Telegram bot entry point."""
import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import config, storage
from .agent import Assistant
from .gcal import Calendar, get_service

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def is_authorized(user_id: int) -> bool:
    if not config.ALLOWED_TELEGRAM_USER_IDS:
        logger.warning(
            "No ALLOWED_TELEGRAM_USER_IDS set — bot is open to everyone. "
            "Set the env var in production."
        )
        return True
    return user_id in config.ALLOWED_TELEGRAM_USER_IDS


async def start_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info("start from user_id=%s (%s)", user.id, user.username)
    if not is_authorized(user.id):
        await update.message.reply_text(
            f"⛔ 이 봇을 사용할 권한이 없습니다.\n귀하의 Telegram user id: {user.id}"
        )
        return
    await update.message.reply_text(
        "안녕하세요 팀장님. 올에프인비 업무 비서입니다.\n\n"
        "💬 자연어로 일정을 말씀해주세요.\n"
        "예) 내일 오후 3시에 싱가포르 매장 리뷰 미팅 1시간 잡아줘\n"
        "예) 이번주 일정 다 보여줘\n"
        "예) 금요일 2시 회의를 3시로 미뤄줘\n\n"
        "/clear 대화 기록 초기화\n"
        "/help 도움말"
    )


async def help_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "명령어:\n"
        "/start - 시작 안내\n"
        "/clear - 대화 기록 초기화\n"
        "/help - 이 도움말\n\n"
        "그 외 모든 메시지는 업무 지시로 처리됩니다."
    )


async def clear_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return
    storage.clear_history(config.DB_PATH, user.id)
    await update.message.reply_text("🧹 대화 기록을 초기화했습니다.")


async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    text = update.message.text
    if not is_authorized(user.id):
        await update.message.reply_text(f"⛔ 권한 없음 (user id: {user.id})")
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    assistant: Assistant = context.application.bot_data["assistant"]
    loop = asyncio.get_running_loop()
    try:
        response = await loop.run_in_executor(
            None, assistant.process_message, user.id, text
        )
    except Exception as e:
        logger.exception("Failed to process message from user_id=%s", user.id)
        await update.message.reply_text(f"❌ 오류 발생: {e}")
        return

    for i in range(0, len(response), 4000):
        await update.message.reply_text(response[i : i + 4000])


def main() -> None:
    storage.init_db(config.DB_PATH)
    service = get_service(config.GOOGLE_CREDENTIALS_PATH, config.GOOGLE_TOKEN_PATH)
    calendar = Calendar(service, config.CALENDAR_ID, config.DEFAULT_TIMEZONE)
    assistant = Assistant(calendar)

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.bot_data["assistant"] = assistant

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(
        "Bot starting (model=%s, calendar=%s, tz=%s)",
        config.CLAUDE_MODEL,
        config.CALENDAR_ID,
        config.DEFAULT_TIMEZONE,
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
