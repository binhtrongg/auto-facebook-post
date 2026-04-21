"""
Tính toán lịch đăng bài.
- Khoảng cách và số lượng bài được cài per-destination
- Mỗi trang đích có hàng đợi riêng, bài mới nối tiếp sau slot cuối
- Không đăng vào khung giờ yên tĩnh 23:00–05:00 giờ Việt Nam

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

# Múi giờ Việt Nam UTC+7
_VN_OFFSET    = timedelta(hours=7)
# Khung giờ yên tĩnh: 23:00 → 05:00 giờ VN
_QUIET_START  = 23   # giờ VN, tính từ đây trở đi là yên tĩnh
_QUIET_END    = 5    # giờ VN, từ đây trở đi được phép đăng


def _skip_quiet_hours(slot: datetime) -> datetime:
    """
    Nếu slot rơi vào 23:00–05:00 giờ VN, đẩy sang 05:xx sáng gần nhất.
    Giữ nguyên phút để các bài không bị dồn vào đúng 05:00.

    Ví dụ:
        23:05 VN  →  05:05 VN sáng hôm sau
        01:30 VN  →  05:30 VN sáng cùng ngày
        05:00 VN  →  giữ nguyên (không bị đẩy)
    """
    vn_time = slot + _VN_OFFSET
    h = vn_time.hour

    if h >= _QUIET_START or h < _QUIET_END:
        if h >= _QUIET_START:
            # Sau 23:00 → sáng hôm sau
            morning_vn = (vn_time + timedelta(days=1)).replace(
                hour=_QUIET_END, second=0, microsecond=0
            )
        else:
            # Trước 05:00 (00:xx–04:xx) → sáng cùng ngày
            morning_vn = vn_time.replace(
                hour=_QUIET_END, second=0, microsecond=0
            )
        # Giữ nguyên phút, chuyển về UTC
        adjusted = morning_vn - _VN_OFFSET
        logger.debug(
            f"Slot {_fmt_vn(slot)} rơi vào giờ yên tĩnh → dời sang {_fmt_vn(adjusted)}"
        )
        return adjusted

    return slot


def _fmt_vn(dt: datetime) -> str:
    """Format datetime sang giờ VN để log cho dễ đọc."""
    vn = dt + _VN_OFFSET
    return vn.strftime("%H:%M %d/%m")


def build_slots_for_dest(dest: dict, count: int) -> list[datetime]:
    """
    Tính danh sách thời điểm đăng cho 1 trang đích.
    Tự động bỏ qua khung 23:00–05:00 giờ VN.

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

    # Đảm bảo slot đầu tiên cũng không rơi vào giờ yên tĩnh
    next_slot = _skip_quiet_hours(next_slot)

    slots = []
    for _ in range(count):
        slots.append(next_slot)
        # Slot tiếp theo tính từ slot đã điều chỉnh (không phải slot gốc)
        next_slot = _skip_quiet_hours(next_slot + interval)

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
