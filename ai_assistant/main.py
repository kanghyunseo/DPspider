"""Telegram bot entry point."""
from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import pathlib
    import sys

    _pkg_dir = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(_pkg_dir.parent))
    __package__ = _pkg_dir.name

import asyncio
import logging
import uuid
from datetime import datetime
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import (
    attachment_parser,
    config,
    daily_briefing,
    knowledge,
    monitors,
    recurring_tasks,
    storage,
    trends_report,
    weekly_report,
)
from .agent import Assistant
from .airwallex_client import Airwallex
from .gcal import Calendar, get_service as get_calendar_service
from .gdrive import Drive, get_service as get_drive_service
from .gtasks import Tasks, get_service as get_tasks_service

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    level=logging.INFO,
)
# httpx logs the full request URL at INFO level, which leaks the bot
# token in api.telegram.org/bot<TOKEN>/... entries. Demote to WARNING
# so tokens never appear in logs/screenshots.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
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
        "💬 자연어로 일정·업무를 말씀해주세요.\n"
        "예) 내일 오후 3시에 싱가포르 매장 리뷰 미팅 1시간 잡아줘\n"
        "예) 베트남 2호점 인테리어 견적 검토 — 4/30까지 할 일로 추가\n"
        "예) 이번주 진행중 업무 보여줘\n"
        "예) 싱가포르 카드결제 정산 이슈 완료 처리\n\n"
        "📎 항공권/호텔 바우처/회의 문서 사진이나 PDF를 보내시면\n"
        "   자동으로 일정 등록 (확인 버튼 후)\n\n"
        "☀️ /today — 오늘 일정 + 마감 업무 브리핑 (매일 9시 자동)\n"
        "📋 /report — 지난주 주간 리포트 즉시 생성 (월 9시 자동)\n"
        "📌 /tasks — 진행중 업무 목록\n"
        "🌏 /trends — F&B 트렌드 브리프 즉시 생성 (월 9시 자동)\n"
        "🧹 /clear — 대화 기록 초기화\n"
        "❓ /help — 도움말"
    )


async def help_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "명령어:\n"
        "/start - 시작 안내\n"
        "/clear - 대화 기록 초기화\n"
        "/today - 오늘 일정 + 마감 업무 브리핑\n"
        "/report - 지난주 주간 리포트 즉시 생성 (일정+업무+자금)\n"
        "/tasks - 진행중 업무 목록 (마감 임박순)\n"
        "/trends - 국가별 F&B 트렌드 브리프 즉시 생성\n"
        "          (사용예: /trends 싱가포르 베트남)\n"
        "/help - 이 도움말\n\n"
        "그 외 모든 메시지는 업무 지시로 처리됩니다.\n"
        "사진/PDF를 보내면 일정 자동 등록 (확인 후)."
    )


async def today_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    calendar: Calendar = context.application.bot_data["calendar"]
    tasks: Tasks = context.application.bot_data["tasks"]
    loop = asyncio.get_running_loop()
    try:
        msg = await loop.run_in_executor(
            None, daily_briefing.build_briefing, calendar, tasks
        )
    except Exception as e:
        await update.message.reply_text(f"❌ 브리핑 생성 실패: {e}")
        return
    if len(msg) > 3900:
        msg = msg[:3900] + "\n…(이하 생략)"
    await update.message.reply_text(msg)


async def tasks_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return
    tasks: Tasks = context.application.bot_data["tasks"]
    loop = asyncio.get_running_loop()
    try:
        items = await loop.run_in_executor(None, tasks.list_tasks)
    except Exception as e:
        await update.message.reply_text(f"❌ 업무 조회 실패: {e}")
        return

    if not items:
        await update.message.reply_text("✨ 진행중인 업무가 없습니다.")
        return

    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _Z

    now = _dt.now(_Z(config.DEFAULT_TIMEZONE))

    def _due_sort_key(t: dict):
        d = t.get("due")
        if not d:
            return (1, "")  # no due → bottom
        return (0, d)

    items.sort(key=_due_sort_key)
    lines = [f"📌 진행중 업무 ({len(items)}건)\n"]
    for t in items:
        due = t.get("due")
        if due:
            try:
                d = _dt.fromisoformat(due.replace("Z", "+00:00"))
                days = (d.date() - now.date()).days
                if days < 0:
                    tag = f"🚧 {-days}일 지연"
                elif days == 0:
                    tag = "🔥 오늘"
                elif days <= 3:
                    tag = f"⏰ D-{days}"
                else:
                    tag = f"D-{days}"
                due_str = f"  [{tag}, {d.strftime('%m/%d')}]"
            except ValueError:
                due_str = ""
        else:
            due_str = ""
        title = t.get("title", "(제목 없음)")
        lines.append(f"• {title}{due_str}")
    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n…(이하 생략)"
    await update.message.reply_text(msg)


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


async def trends_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return
    # Allow override: "/trends 싱가포르 베트남 일본"
    override = context.args
    countries = override if override else config.TREND_COUNTRIES
    if not countries:
        await update.message.reply_text(
            "❌ 조사할 국가를 지정하세요.\n"
            "예) /trends 싱가포르 베트남\n"
            "또는 TREND_COUNTRIES 환경변수 설정"
        )
        return
    await update.message.reply_text(
        f"🌏 F&B 트렌드 조사 중... (30초~2분 소요)\n대상: {', '.join(countries)}"
    )
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        await _deliver_trends_report(
            context.application,
            countries=countries,
            chat_id=update.effective_chat.id,
        )
    except Exception as e:
        logger.exception("Manual /trends failed")
        await update.message.reply_text(f"❌ 트렌드 리포트 실패: {e}")


async def _process_message(
    application: Application,
    user_id: int,
    chat_id: int,
    text: str,
    attachments: list[dict] | None = None,
) -> None:
    assistant: Assistant = application.bot_data["assistant"]
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        partial(assistant.process_message, user_id, text, attachments=attachments),
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
        await _process_message(
            context.application, user.id, update.effective_chat.id, update.message.text
        )
    except Exception as e:
        logger.exception("Failed to process text from user_id=%s", user.id)
        await update.message.reply_text(f"❌ 오류 발생: {e}")


_MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024  # Anthropic API limit
_SUPPORTED_DOC_MIMES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}
# Pending attachment proposals awaiting user confirm/cancel.
# Stored in application.bot_data["pending_attachments"][token] = {events, user_id}
_PENDING_KEY = "pending_attachments"


async def _download_attachment(file) -> bytes:
    return bytes(await file.download_as_bytearray())


async def _extract_and_propose(
    application: Application,
    user_id: int,
    chat_id: int,
    data: bytes,
    mime: str,
    caption: str | None,
) -> None:
    """Run extraction in executor, then send preview + confirm/cancel buttons."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        partial(attachment_parser.extract_events, data, mime, caption),
    )

    if not result.events:
        msg = "⚠️ 첨부에서 일정 정보를 추출하지 못했습니다."
        if result.notes:
            msg += f"\n\n{result.notes}"
        await application.bot.send_message(chat_id=chat_id, text=msg)
        return

    token = uuid.uuid4().hex[:8]
    pending = application.bot_data.setdefault(_PENDING_KEY, {})
    pending[token] = {"events": result.events, "user_id": user_id}

    preview = (
        f"📎 첨부에서 일정 {len(result.events)}건 추출됨 — 등록할까요?\n\n"
        + attachment_parser.format_events_preview(result.events)
    )
    if result.notes:
        preview += f"\n\n💬 {result.notes}"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ 모두 등록", callback_data=f"att:confirm:{token}"
                ),
                InlineKeyboardButton(
                    "❌ 취소", callback_data=f"att:cancel:{token}"
                ),
            ]
        ]
    )
    # Telegram message limit: 4096. Truncate preview if needed.
    if len(preview) > 3900:
        preview = preview[:3900] + "\n…(이하 생략)"
    await application.bot.send_message(
        chat_id=chat_id, text=preview, reply_markup=keyboard
    )


async def handle_photo(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text(f"⛔ 권한 없음 (user id: {user.id})")
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        photo = update.message.photo[-1]  # largest size
        file = await photo.get_file()
        data = await _download_attachment(file)
        if len(data) > _MAX_ATTACHMENT_BYTES:
            await update.message.reply_text("❌ 파일이 너무 큽니다 (20MB 초과).")
            return

        await _extract_and_propose(
            context.application,
            user.id,
            update.effective_chat.id,
            data,
            "image/jpeg",
            update.message.caption,
        )
    except Exception as e:
        logger.exception("Failed to process photo from user_id=%s", user.id)
        await update.message.reply_text(f"❌ 사진 처리 실패: {e}")


async def handle_document(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text(f"⛔ 권한 없음 (user id: {user.id})")
        return

    doc = update.message.document
    mime = (doc.mime_type or "").lower()
    if mime not in _SUPPORTED_DOC_MIMES:
        await update.message.reply_text(
            f"❌ 지원하지 않는 파일 형식: {mime or '(unknown)'}\n"
            "지원: PDF, JPEG, PNG, GIF, WEBP"
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        file = await doc.get_file()
        data = await _download_attachment(file)
        if len(data) > _MAX_ATTACHMENT_BYTES:
            await update.message.reply_text("❌ 파일이 너무 큽니다 (20MB 초과).")
            return

        await _extract_and_propose(
            context.application,
            user.id,
            update.effective_chat.id,
            data,
            mime,
            update.message.caption,
        )
    except Exception as e:
        logger.exception("Failed to process document from user_id=%s", user.id)
        await update.message.reply_text(f"❌ 파일 처리 실패: {e}")


async def handle_attachment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    try:
        prefix, action, token = query.data.split(":", 2)
    except ValueError:
        await query.edit_message_text("⚠️ 잘못된 요청입니다.")
        return

    pending: dict = context.application.bot_data.get(_PENDING_KEY, {})
    entry = pending.pop(token, None)
    if entry is None:
        await query.edit_message_text(
            "⚠️ 만료되었거나 이미 처리된 요청입니다 (봇 재시작 시 보류 항목 소실)."
        )
        return

    if entry["user_id"] != user_id:
        # restore and reject
        pending[token] = entry
        await query.answer("권한 없음", show_alert=True)
        return

    if action == "cancel":
        await query.edit_message_text("❌ 등록 취소됨")
        return

    if action != "confirm":
        await query.edit_message_text(f"⚠️ 알 수 없는 액션: {action}")
        return

    calendar: Calendar = context.application.bot_data["calendar"]
    loop = asyncio.get_running_loop()
    results: list[str] = []
    for ev in entry["events"]:
        try:
            created = await loop.run_in_executor(
                None, partial(calendar.create_event, **ev.to_calendar_kwargs())
            )
            results.append(f"✅ {created.get('summary', ev.summary)}")
        except Exception as exc:
            logger.exception("Failed to create event %r", ev.summary)
            results.append(f"❌ {ev.summary} — {type(exc).__name__}: {exc}")

    await query.edit_message_text(
        "📅 등록 결과\n\n" + "\n".join(results)
    )


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
    tasks: Tasks = application.bot_data["tasks"]
    airwallex: Airwallex | None = application.bot_data.get("airwallex")

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            partial(weekly_report.generate, calendar, drive, tasks, airwallex),
        )
    except Exception as e:
        logger.exception("Weekly report generation failed")
        await application.bot.send_message(
            chat_id=target_chat_id, text=f"❌ 주간 리포트 생성 실패: {e}"
        )
        return

    finance_tag = " + 💰자금" if airwallex else ""
    msg = (
        f"📋 지난주 리포트 업로드 완료{finance_tag}\n\n"
        f"📅 {result.week_label}\n"
        f"📝 일정 {result.event_count}건  |  "
        f"✅ 완료 업무 {result.completed_task_count}건  |  "
        f"🔄 진행중 {result.open_task_count}건\n"
        f"🔗 {result.doc_link}\n\n"
        f"— 미리보기 —\n{result.summary_preview}"
    )
    await application.bot.send_message(chat_id=target_chat_id, text=msg)


async def _deliver_trends_report(
    application: Application,
    countries: list[str],
    chat_id: int | None = None,
) -> None:
    target_chat_id = chat_id or config.WEEKLY_REPORT_CHAT_ID
    if not target_chat_id:
        logger.error("No chat id for trends report.")
        return

    drive: Drive = application.bot_data["drive"]

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None, trends_report.generate, drive, countries
        )
    except Exception as e:
        logger.exception("Trends report generation failed")
        await application.bot.send_message(
            chat_id=target_chat_id, text=f"❌ 트렌드 리포트 실패: {e}"
        )
        return

    msg = (
        f"🌏 F&B 트렌드 브리프 업로드 완료\n\n"
        f"📅 {result.period_label}\n"
        f"🗺️  대상국가: {', '.join(result.countries)}\n"
        f"🔗 {result.doc_link}\n\n"
        f"— 미리보기 —\n{result.summary_preview}"
    )
    await application.bot.send_message(chat_id=target_chat_id, text=msg)


async def _notify_scheduled_failure(
    application: Application, job_label: str, exc: BaseException
) -> None:
    """Send a Telegram alert when a scheduled job crashes outside its
    own try/except. Falls back to log-only if no chat is configured."""
    chat_id = config.WEEKLY_REPORT_CHAT_ID
    if not chat_id:
        return
    try:
        await application.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🚨 자동 {job_label} 실패\n"
                f"{type(exc).__name__}: {str(exc)[:500]}\n\n"
                "로그를 확인해주세요."
            ),
        )
    except Exception:
        logger.exception("Failed to send scheduled-failure notification")


async def _scheduled_weekly_report(application: Application) -> None:
    logger.info("Running scheduled weekly report")
    try:
        await _deliver_weekly_report(application)
    except Exception as e:
        logger.exception("Scheduled weekly report crashed")
        await _notify_scheduled_failure(application, "주간 리포트", e)


async def _scheduled_trends_report(application: Application) -> None:
    logger.info("Running scheduled trends report")
    try:
        await _deliver_trends_report(application, countries=config.TREND_COUNTRIES)
    except Exception as e:
        logger.exception("Scheduled trends report crashed")
        await _notify_scheduled_failure(application, "트렌드 리포트", e)


async def _scheduled_daily_briefing(application: Application) -> None:
    logger.info("Running scheduled daily briefing")
    chat_id = config.WEEKLY_REPORT_CHAT_ID
    if not chat_id:
        logger.error("Daily briefing: no chat_id configured")
        return
    try:
        calendar: Calendar = application.bot_data["calendar"]
        tasks: Tasks = application.bot_data["tasks"]
        loop = asyncio.get_running_loop()
        msg = await loop.run_in_executor(
            None, daily_briefing.build_briefing, calendar, tasks
        )
        await application.bot.send_message(chat_id=chat_id, text=msg)
    except Exception as e:
        logger.exception("Scheduled daily briefing crashed")
        await _notify_scheduled_failure(application, "데일리 브리핑", e)


async def _scheduled_meeting_reminders(application: Application) -> None:
    if config.MEETING_REMINDER_LEAD_MINUTES <= 0:
        return
    chat_id = config.WEEKLY_REPORT_CHAT_ID
    if not chat_id:
        return
    try:
        calendar: Calendar = application.bot_data["calendar"]
        loop = asyncio.get_running_loop()
        events = await loop.run_in_executor(
            None,
            monitors.upcoming_events_to_remind,
            calendar,
            config.MEETING_REMINDER_LEAD_MINUTES,
            config.MEETING_REMINDER_CHECK_INTERVAL_MINUTES,
        )
        for ev in events:
            text = monitors.format_reminder(
                ev, config.MEETING_REMINDER_LEAD_MINUTES
            )
            await application.bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        # Silent — reminders failing once shouldn't spam the user;
        # we'll just try again next interval.
        logger.exception("Meeting reminder check failed")


async def _scheduled_healthcheck_ping(_: Application) -> None:
    if not config.HEALTHCHECK_URL:
        return
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, monitors.ping_healthcheck)


async def _scheduled_recurring_tasks(application: Application) -> None:
    """Materialize recurring task templates into Google Tasks for today."""
    try:
        tasks: Tasks = application.bot_data["tasks"]
        loop = asyncio.get_running_loop()
        created = await loop.run_in_executor(
            None, recurring_tasks.materialize_due_today, tasks
        )
        if created:
            logger.info(
                "Recurring tasks materialized: %d", len(created)
            )
    except Exception as e:
        logger.exception("Recurring tasks job crashed")
        await _notify_scheduled_failure(application, "반복 업무 생성", e)


async def _scheduled_backup(application: Application) -> None:
    logger.info("Running scheduled backup")
    try:
        drive: Drive = application.bot_data.get("drive")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, partial(monitors.run_backup, drive=drive)
        )
    except Exception as e:
        logger.exception("Scheduled backup crashed")
        await _notify_scheduled_failure(application, "백업", e)


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
    if config.TREND_COUNTRIES:
        scheduler.add_job(
            _scheduled_trends_report,
            CronTrigger(
                day_of_week=config.TRENDS_REPORT_DAY,
                hour=config.TRENDS_REPORT_HOUR,
                minute=config.TRENDS_REPORT_MINUTE,
            ),
            args=[application],
            id="trends_report",
            replace_existing=True,
            misfire_grace_time=60 * 60 * 12,
            coalesce=True,
        )

    if config.DAILY_BRIEFING_ENABLED:
        scheduler.add_job(
            _scheduled_daily_briefing,
            CronTrigger(
                hour=config.DAILY_BRIEFING_HOUR,
                minute=config.DAILY_BRIEFING_MINUTE,
            ),
            args=[application],
            id="daily_briefing",
            replace_existing=True,
            misfire_grace_time=60 * 60 * 6,
            coalesce=True,
        )

    if config.MEETING_REMINDER_LEAD_MINUTES > 0:
        scheduler.add_job(
            _scheduled_meeting_reminders,
            "interval",
            minutes=config.MEETING_REMINDER_CHECK_INTERVAL_MINUTES,
            args=[application],
            id="meeting_reminders",
            replace_existing=True,
        )

    if config.HEALTHCHECK_URL:
        scheduler.add_job(
            _scheduled_healthcheck_ping,
            "interval",
            minutes=config.HEALTHCHECK_INTERVAL_MINUTES,
            args=[application],
            id="healthcheck_ping",
            replace_existing=True,
            # Ping immediately on startup so external monitor sees life
            next_run_time=datetime.now(ZoneInfo(config.DEFAULT_TIMEZONE)),
        )

    scheduler.add_job(
        _scheduled_backup,
        CronTrigger(hour=config.BACKUP_HOUR, minute=config.BACKUP_MINUTE),
        args=[application],
        id="backup",
        replace_existing=True,
        misfire_grace_time=60 * 60 * 12,
        coalesce=True,
    )

    # Materialize recurring task templates: every day at 01:00 KST
    scheduler.add_job(
        _scheduled_recurring_tasks,
        CronTrigger(hour=1, minute=0),
        args=[application],
        id="recurring_tasks",
        replace_existing=True,
        misfire_grace_time=60 * 60 * 12,
        coalesce=True,
    )

    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    logger.info(
        "Scheduled weekly report: %s %02d:%02d %s (chat_id=%s)",
        config.WEEKLY_REPORT_DAY,
        config.WEEKLY_REPORT_HOUR,
        config.WEEKLY_REPORT_MINUTE,
        config.DEFAULT_TIMEZONE,
        config.WEEKLY_REPORT_CHAT_ID,
    )
    if config.TREND_COUNTRIES:
        logger.info(
            "Scheduled trends report: %s %02d:%02d %s, countries=%s",
            config.TRENDS_REPORT_DAY,
            config.TRENDS_REPORT_HOUR,
            config.TRENDS_REPORT_MINUTE,
            config.DEFAULT_TIMEZONE,
            ", ".join(config.TREND_COUNTRIES),
        )

    if config.WEEKLY_REPORT_CHAT_ID:
        try:
            schedule_lines = [
                f"• 주간 리포트: {config.WEEKLY_REPORT_DAY} "
                f"{config.WEEKLY_REPORT_HOUR:02d}:{config.WEEKLY_REPORT_MINUTE:02d}",
                f"• 트렌드 리포트: {config.TRENDS_REPORT_DAY} "
                f"{config.TRENDS_REPORT_HOUR:02d}:{config.TRENDS_REPORT_MINUTE:02d}",
            ]
            if config.DAILY_BRIEFING_ENABLED:
                schedule_lines.append(
                    f"• 데일리 브리핑: 매일 "
                    f"{config.DAILY_BRIEFING_HOUR:02d}:{config.DAILY_BRIEFING_MINUTE:02d}"
                )
            if config.MEETING_REMINDER_LEAD_MINUTES > 0:
                schedule_lines.append(
                    f"• 미팅 알림: {config.MEETING_REMINDER_LEAD_MINUTES}분 전"
                )
            schedule_lines.append(
                f"• 백업: 매일 "
                f"{config.BACKUP_HOUR:02d}:{config.BACKUP_MINUTE:02d} "
                f"→ Google Drive (보관 {config.BACKUP_RETENTION_DAYS}일)"
            )
            if config.HEALTHCHECK_URL:
                schedule_lines.append("• 헬스체크 ping: 활성")
            await application.bot.send_message(
                chat_id=config.WEEKLY_REPORT_CHAT_ID,
                text=(
                    "🤖 봇 시작됨\n"
                    f"• model: {config.CLAUDE_MODEL}\n"
                    + "\n".join(schedule_lines)
                    + "\n\n업무 지시를 메시지로 보내주세요."
                ),
            )
        except Exception:
            logger.exception("Failed to send startup notification")


def main() -> None:
    _materialize_secrets()
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    storage.init_db(config.DB_PATH)
    recurring_tasks.init_db()
    knowledge.init_db()

    cal_service = get_calendar_service(
        config.GOOGLE_CREDENTIALS_PATH, config.GOOGLE_TOKEN_PATH
    )
    drive_service = get_drive_service(
        config.GOOGLE_CREDENTIALS_PATH, config.GOOGLE_TOKEN_PATH
    )
    tasks_service = get_tasks_service(
        config.GOOGLE_CREDENTIALS_PATH, config.GOOGLE_TOKEN_PATH
    )
    calendar = Calendar(cal_service, config.CALENDAR_ID, config.DEFAULT_TIMEZONE)
    drive = Drive(drive_service, config.DRIVE_FOLDER_ID)
    tasks = Tasks(tasks_service)
    assistant = Assistant(calendar, tasks)

    airwallex = None
    if config.AIRWALLEX_CLIENT_ID and config.AIRWALLEX_API_KEY:
        airwallex = Airwallex(
            client_id=config.AIRWALLEX_CLIENT_ID,
            api_key=config.AIRWALLEX_API_KEY,
            base_url=config.AIRWALLEX_BASE_URL,
        )

    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.bot_data["assistant"] = assistant
    app.bot_data["calendar"] = calendar
    app.bot_data["drive"] = drive
    app.bot_data["tasks"] = tasks
    app.bot_data["airwallex"] = airwallex

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("tasks", tasks_cmd))
    app.add_handler(CommandHandler("today", today_cmd))
    app.add_handler(CommandHandler("trends", trends_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(
        CallbackQueryHandler(handle_attachment_callback, pattern=r"^att:")
    )

    logger.info(
        "Bot starting (model=%s, calendar=%s, tz=%s, drive_folder=%s, "
        "airwallex=%s, trends=%s)",
        config.CLAUDE_MODEL,
        config.CALENDAR_ID,
        config.DEFAULT_TIMEZONE,
        config.DRIVE_FOLDER_ID or "(My Drive root)",
        "enabled" if airwallex else "disabled",
        "enabled" if config.TREND_COUNTRIES else "disabled",
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
