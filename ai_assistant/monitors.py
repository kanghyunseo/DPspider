"""Background monitors: meeting reminders, healthcheck pings, backups."""
from __future__ import annotations

import logging
import shutil
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import config
from .gcal import Calendar
from .gdrive import Drive

logger = logging.getLogger(__name__)


# ---------- meeting reminders ----------

# In-memory set of (event_id, reminder_marker) we've already sent.
# Reset on bot restart — small risk of duplicate notifications after
# restart for events about to start, acceptable for this volume.
_REMINDED: set[tuple[str, str]] = set()


def upcoming_events_to_remind(
    calendar: Calendar, lead_minutes: int, check_interval_minutes: int
) -> list[dict]:
    """Return events that start in [lead, lead - check_interval] minutes.

    The check window matches the scheduler interval, so each event
    triggers exactly one reminder per (event_id, lead) pair.
    """
    if lead_minutes <= 0:
        return []
    tz = ZoneInfo(config.DEFAULT_TIMEZONE)
    now = datetime.now(tz)
    window_start = now + timedelta(minutes=lead_minutes - check_interval_minutes)
    window_end = now + timedelta(minutes=lead_minutes)

    events = calendar.list_events(
        time_min=window_start.isoformat(),
        time_max=window_end.isoformat(),
        max_results=20,
    )
    marker = f"lead-{lead_minutes}"
    fresh = []
    for ev in events:
        eid = ev.get("id")
        if not eid:
            continue
        # Skip all-day events (no time)
        start = ev.get("start", "")
        if "T" not in start:
            continue
        key = (eid, marker)
        if key in _REMINDED:
            continue
        _REMINDED.add(key)
        fresh.append(ev)
    return fresh


def format_reminder(ev: dict, lead_minutes: int) -> str:
    tz = ZoneInfo(config.DEFAULT_TIMEZONE)
    summary = ev.get("summary", "(제목 없음)")
    start = ev.get("start", "")
    try:
        dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(tz)
        time_str = dt.strftime("%H:%M")
    except ValueError:
        time_str = start[:16]

    lines = [f"⏰ {lead_minutes}분 후 미팅", "", f"📅 {time_str}  {summary}"]
    if ev.get("location"):
        lines.append(f"📍 {ev['location']}")
    if ev.get("description"):
        d = ev["description"]
        short = d if len(d) <= 200 else d[:200] + "…"
        lines.append(f"📝 {short}")
    if ev.get("htmlLink"):
        lines.append(f"🔗 {ev['htmlLink']}")
    return "\n".join(lines)


# ---------- healthcheck ----------

def ping_healthcheck(url: str | None = None) -> None:
    """Best-effort GET to the healthcheck URL. Failures are logged, not raised."""
    target = url if url is not None else config.HEALTHCHECK_URL
    if not target:
        return
    try:
        r = requests.get(target, timeout=10)
        if r.status_code >= 400:
            logger.warning(
                "Healthcheck ping returned %s: %s", r.status_code, r.text[:200]
            )
    except Exception:
        logger.exception("Healthcheck ping failed")


# ---------- backups ----------

def run_backup(drive: Drive | None = None) -> Path:
    """Snapshot critical files into BACKUP_DIR/YYYYMMDD/. Prune local + Drive copies.

    If `drive` is provided, also tar.gz the snapshot and upload to a
    `ai_assistant_backups` folder in Drive (offsite copy survives if
    the fly.io machine is destroyed).
    """
    backup_root = Path(config.BACKUP_DIR)
    backup_root.mkdir(parents=True, exist_ok=True)

    tz = ZoneInfo(config.DEFAULT_TIMEZONE)
    today = datetime.now(tz).strftime("%Y%m%d")
    target_dir = backup_root / today
    target_dir.mkdir(exist_ok=True)

    pkg_dir = Path(config.PACKAGE_DIR)
    sources = [
        Path(config.DB_PATH) if Path(config.DB_PATH).is_absolute()
            else pkg_dir / config.DB_PATH,
        Path(config.GOOGLE_TOKEN_PATH) if Path(config.GOOGLE_TOKEN_PATH).is_absolute()
            else pkg_dir / config.GOOGLE_TOKEN_PATH,
        pkg_dir / ".env",
    ]
    copied = []
    for src in sources:
        if not src.exists():
            logger.warning("Backup: source missing %s", src)
            continue
        dst = target_dir / src.name
        shutil.copy2(src, dst)
        copied.append(dst.name)
    logger.info("Backup → %s : %s", target_dir, ", ".join(copied))

    # Offsite copy → Google Drive (best-effort)
    if drive is not None and copied:
        try:
            archive_path = backup_root / f"backup-{today}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                for fname in copied:
                    tar.add(target_dir / fname, arcname=fname)
            try:
                drive_folder = drive.find_or_create_folder("ai_assistant_backups")
                uploaded = drive.upload_file(
                    archive_path,
                    drive_filename=archive_path.name,
                    mime_type="application/gzip",
                    folder_id=drive_folder,
                )
                logger.info("Backup uploaded to Drive: %s", uploaded["link"])
                _prune_drive_backups(drive, drive_folder)
            finally:
                # Local tar.gz is redundant (we have unpacked dir + Drive copy)
                archive_path.unlink(missing_ok=True)
        except Exception:
            logger.exception("Backup: Drive upload failed (local copy still saved)")

    # Prune local backups
    cutoff = datetime.now(tz).date() - timedelta(days=config.BACKUP_RETENTION_DAYS)
    for entry in backup_root.iterdir():
        if not entry.is_dir():
            continue
        try:
            d = datetime.strptime(entry.name, "%Y%m%d").date()
        except ValueError:
            continue
        if d < cutoff:
            shutil.rmtree(entry, ignore_errors=True)
            logger.info("Backup: pruned old local snapshot %s", entry.name)

    return target_dir


def _prune_drive_backups(drive: Drive, folder_id: str) -> None:
    """Delete Drive backup files older than BACKUP_RETENTION_DAYS."""
    files = drive.list_files_in_folder(folder_id, name_prefix="backup-")
    cutoff = datetime.now().date() - timedelta(days=config.BACKUP_RETENTION_DAYS)
    for f in files:
        # Filenames look like "backup-20260423.tar.gz"
        name = f.get("name", "")
        try:
            date_str = name.replace("backup-", "").split(".")[0]
            d = datetime.strptime(date_str, "%Y%m%d").date()
        except ValueError:
            continue
        if d < cutoff:
            try:
                drive.delete_file(f["id"])
                logger.info("Backup: pruned old Drive snapshot %s", name)
            except Exception:
                logger.exception("Backup: failed to prune Drive file %s", name)
