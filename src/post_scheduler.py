"""
Tính toán lịch đăng bài.
- Mỗi bài cách nhau 30-60 phút (random)
- Mỗi trang đích có hàng đợi riêng
- Bài mới nối tiếp sau slot cuối cùng đã hẹn

Khác với flow cũ: module này chỉ tính thời gian,
không ghi DB. Việc đăng và lưu dedup do main_scrape.py thực hiện.
"""
import logging
import random
from datetime import datetime, timedelta, timezone
from dateutil.parser import isoparse

from src.config import DB_BACKEND

if DB_BACKEND == "sheets":
    from src.sheets_db import (
        get_destination_pages_by_group,
        get_dest_last_scheduled,
        update_dest_last_scheduled,
    )
else:
    from src.database import (
        get_destination_pages_by_group,
        get_dest_last_scheduled,
        update_dest_last_scheduled,
    )
from src.config import POST_INTERVAL_MIN_MINUTES, POST_INTERVAL_MAX_MINUTES

logger = logging.getLogger(__name__)


def build_schedule_for_group(group_id: str,
                              post_count: int) -> dict[str, list[datetime]]:
    """
    Tính danh sách thời điểm đăng cho mỗi trang đích trong group.

    Args:
        group_id:   ID nhóm trang
        post_count: Số bài cần lên lịch

    Returns:
        {destination_page_id: [datetime, datetime, ...]}
        Mỗi list có đúng post_count phần tử theo thứ tự thời gian.
    """
    destinations = get_destination_pages_by_group(group_id)
    schedule: dict[str, list[datetime]] = {}

    for dest in destinations:
        slots = _build_slots(dest, post_count)
        schedule[dest["id"]] = slots

    return schedule


def commit_schedule(dest_id: str, slots: list[datetime]):
    """
    Lưu thời điểm cuối cùng đã lên lịch vào DB
    để lần scrape tiếp theo biết nối tiếp từ đâu.
    """
    if slots:
        update_dest_last_scheduled(dest_id, slots[-1].isoformat())


def _build_slots(dest: dict, count: int) -> list[datetime]:
    """Tính count thời điểm kế tiếp cho 1 trang đích."""
    last_time_str = get_dest_last_scheduled(dest["id"])
    now = datetime.now(timezone.utc)

    if last_time_str:
        last_dt = isoparse(last_time_str)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        # Nếu last đã qua → bắt đầu từ 15 phút sau now
        next_slot = max(last_dt, now + timedelta(minutes=15))
    else:
        # Chưa có lịch nào → bắt đầu từ 15 phút sau now
        next_slot = now + timedelta(minutes=15)

    slots = []
    for _ in range(count):
        slots.append(next_slot)
        next_slot += _random_interval()

    return slots


def _random_interval() -> timedelta:
    """Trả về khoảng thời gian ngẫu nhiên giữa 2 bài đăng."""
    minutes = random.randint(
        POST_INTERVAL_MIN_MINUTES,
        POST_INTERVAL_MAX_MINUTES,
    )
    return timedelta(minutes=minutes)
