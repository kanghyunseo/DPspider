"""Telegram bot entry point."""
if __name__ == "__main__" and __package__ in (None, ""):
    import pathlib
    import sys

    _pkg_dir = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(_pkg_dir.parent))
    __package__ = _pkg_dir.name

import asyncio
import logging
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import config, storage, weekly_report
from .agent import Assistant
from .gcal import Calendar, get_service as get_calendar_service
from .gdrive import Drive, get_service as get_drive_service

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
        "📋 /report — 주간 리포트 즉시 생성 (금요일 17시 자동)\n"
        "🧹 /clear — 대화 기록 초기화\n"
        "❓ /help — 도움말"
    )


async def help_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "명령어:\n"
        "/start - 시작 안내\n"
        "/clear - 대화 기록 초기화\n"
        "/report - 이번주 주간 리포트 즉시 생성\n"
        "/help - 이 도움말\n\n"
        "그 외 모든 메시지는 업무 지시로 처리됩니다."
    )


async def clear_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return
    storage.clear_history(config.DB_PATH, user.id)
    await update.message.reply_text("🧹 대화 기록을 초기화했습니다.")


async def report_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return
    await update.message.reply_text("📋 주간 리포트 생성 중... (10~30초 소요)")
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        await _deliver_weekly_report(context.application, chat_id=update.effective_chat.id)
    except Exception as e:
        logger.exception("Manual /report failed")
        await update.message.reply_text(f"❌ 리포트 생성 실패: {e}")


async def _process_text(
    application: Application, user_id: int, chat_id: int, text: str
) -> None:
    assistant: Assistant = application.bot_data["assistant"]
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None, assistant.process_message, user_id, text
    )
    for i in range(0, len(response), 4000):
        await application.bot.send_message(
            chat_id=chat_id, text=response[i : i + 4000]
        )


async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text(f"⛔ 권한 없음 (user id: {user.id})")
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        await _process_text(
            context.application, user.id, update.effective_chat.id, update.message.text
        )
    except Exception as e:
        logger.exception("Failed to process text from user_id=%s", user.id)
        await update.message.reply_text(f"❌ 오류 발생: {e}")


async def _deliver_weekly_report(
    application: Application, chat_id: int | None = None
) -> None:
    """Generate and deliver the weekly report to Telegram."""
    target_chat_id = chat_id or config.WEEKLY_REPORT_CHAT_ID
    if not target_chat_id:
        logger.error(
            "No chat id for weekly report. Set WEEKLY_REPORT_CHAT_ID "
            "or ALLOWED_TELEGRAM_USER_IDS."
        )
        return

    calendar: Calendar = application.bot_data["calendar"]
    drive: Drive = application.bot_data["drive"]

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None, weekly_report.generate, calendar, drive
        )
    except Exception as e:
        logger.exception("Weekly report generation failed")
        await application.bot.send_message(
            chat_id=target_chat_id, text=f"❌ 주간 리포트 생성 실패: {e}"
        )
        return

    msg = (
        f"📋 *주간 리포트 업로드 완료*\n\n"
        f"📅 {result.week_label}\n"
        f"📝 일정 {result.event_count}건\n"
        f"🔗 {result.doc_link}\n\n"
        f"— 미리보기 —\n{result.summary_preview}"
    )
    # Telegram markdown is fragile; send plain with link
    await application.bot.send_message(chat_id=target_chat_id, text=msg)


async def _scheduled_weekly_report(application: Application) -> None:
    logger.info("Running scheduled weekly report")
    await _deliver_weekly_report(application)


def _materialize_secrets() -> None:
    """Write JSON env-var secrets to file if set (for cloud deployments)."""
    for content, path in (
        (config.GOOGLE_TOKEN_JSON, config.GOOGLE_TOKEN_PATH),
        (config.GOOGLE_CREDENTIALS_JSON, config.GOOGLE_CREDENTIALS_PATH),
    ):
        if content and not Path(path).exists():
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content)
            logger.info("Materialized credential file at %s", path)


async def _post_init(application: Application) -> None:
    """Start the APScheduler weekly-report cron job after PTB's loop is ready."""
    scheduler = AsyncIOScheduler(timezone=config.DEFAULT_TIMEZONE)
    scheduler.add_job(
        _scheduled_weekly_report,
        CronTrigger(
            day_of_week=config.WEEKLY_REPORT_DAY,
            hour=config.WEEKLY_REPORT_HOUR,
            minute=config.WEEKLY_REPORT_MINUTE,
        ),
        args=[application],
        id="weekly_report",
        replace_existing=True,
        # If the machine was asleep / offline at the scheduled time,
        # run the report as soon as it wakes up — within 12 hours.
        misfire_grace_time=60 * 60 * 12,
        coalesce=True,
    )
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    logger.info(
        "Scheduled weekly report: every %s at %02d:%02d %s (chat_id=%s)",
        config.WEEKLY_REPORT_DAY,
        config.WEEKLY_REPORT_HOUR,
        config.WEEKLY_REPORT_MINUTE,
        config.DEFAULT_TIMEZONE,
        config.WEEKLY_REPORT_CHAT_ID,
    )


def main() -> None:
    _materialize_secrets()
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    storage.init_db(config.DB_PATH)

    cal_service = get_calendar_service(
        config.GOOGLE_CREDENTIALS_PATH, config.GOOGLE_TOKEN_PATH
    )
    drive_service = get_drive_service(
        config.GOOGLE_CREDENTIALS_PATH, config.GOOGLE_TOKEN_PATH
    )
    calendar = Calendar(cal_service, config.CALENDAR_ID, config.DEFAULT_TIMEZONE)
    drive = Drive(drive_service, config.DRIVE_FOLDER_ID)
    assistant = Assistant(calendar)

    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.bot_data["assistant"] = assistant
    app.bot_data["calendar"] = calendar
    app.bot_data["drive"] = drive

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(
        "Bot starting (model=%s, calendar=%s, tz=%s, drive_folder=%s)",
        config.CLAUDE_MODEL,
        config.CALENDAR_ID,
        config.DEFAULT_TIMEZONE,
        config.DRIVE_FOLDER_ID or "(My Drive root)",
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
