"""
Tính toán lịch đăng bài.
- Khoảng cách và số lượng bài được cài per-destination
- Mỗi trang đích có hàng đợi riêng, bài mới nối tiếp sau slot cuối

Không ghi DB — việc đăng và lưu dedup do main_scrape.py thực hiện.
"""
import logging
from datetime import datetime, timedelta, timezone
from dateutil.parser import isoparse

from src.config import (
    DB_BACKEND,
    DEFAULT_MAX_POSTS_PER_RUN,
    DEFAULT_POST_INTERVAL_HOURS,
)

if DB_BACKEND == "sheets":
    from src.sheets_db import get_dest_last_scheduled, update_dest_last_scheduled
else:
    from src.database import get_dest_last_scheduled, update_dest_last_scheduled

logger = logging.getLogger(__name__)


def build_slots_for_dest(dest: dict, count: int) -> list[datetime]:
    """
    Tính danh sách thời điểm đăng cho 1 trang đích.

    Args:
        dest:  dict trang đích (có thể có post_interval_hours)
        count: số bài cần slot

    Returns:
        list datetime UTC, độ dài = count
    """
    interval_hours = float(dest.get("post_interval_hours") or DEFAULT_POST_INTERVAL_HOURS)
    interval       = timedelta(hours=interval_hours)

    last_time_str = get_dest_last_scheduled(dest["id"])
    now           = datetime.now(timezone.utc)

    if last_time_str:
        last_dt = isoparse(last_time_str)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        next_slot = max(last_dt + interval, now + timedelta(minutes=15))
    else:
        next_slot = now + timedelta(minutes=15)

    slots = []
    for _ in range(count):
        slots.append(next_slot)
        next_slot += interval

    return slots


def max_posts_for_dest(dest: dict) -> int:
    """Trả về số bài tối đa mỗi lần chạy cho trang đích."""
    v = dest.get("max_posts_per_run")
    try:
        return max(1, int(v)) if v not in (None, "") else DEFAULT_MAX_POSTS_PER_RUN
    except (ValueError, TypeError):
        return DEFAULT_MAX_POSTS_PER_RUN


def commit_schedule(dest_id: str, slots: list[datetime]):
    """Lưu slot cuối cùng để lần scrape tiếp theo nối tiếp."""
    if slots:
        update_dest_last_scheduled(dest_id, slots[-1].isoformat())
