"""
Quản lý và xoay vòng Apify API keys.
Hỗ trợ cả Google Sheets và Supabase backend.
"""
import logging
from src.config import APIFY_KEY_SAFE_LIMIT, DB_BACKEND

logger = logging.getLogger(__name__)


def get_active_key() -> str | None:
    """Trả về API key còn quota. Ưu tiên key ít dùng nhất."""
    if DB_BACKEND == "sheets":
        from src.sheets_db import get_active_apify_key
        key = get_active_apify_key(APIFY_KEY_SAFE_LIMIT)
    else:
        key = _supabase_get_active_key()

    if not key:
        logger.error("Không còn Apify key nào khả dụng!")
    return key


def increment_key_usage(api_key: str, count: int = 1):
    """Tăng counter sử dụng cho key."""
    if DB_BACKEND == "sheets":
        from src.sheets_db import increment_apify_key_usage
        increment_apify_key_usage(api_key, count)
    else:
        _supabase_increment_key_usage(api_key, count)


def mark_key_exhausted(api_key: str):
    """Đánh dấu key lỗi/hết quota → hệ thống sẽ chuyển sang key khác."""
    logger.warning(f"Đánh dấu key exhausted: {api_key[:20]}...")
    if DB_BACKEND == "sheets":
        from src.sheets_db import mark_apify_key_exhausted
        mark_apify_key_exhausted(api_key)
    else:
        _supabase_increment_key_usage(api_key, count=500)


# ── Supabase implementation ────────────────────────────────

def _supabase_get_active_key() -> str | None:
    from datetime import date
    from src.database import get_db
    _supabase_reset_monthly_usage()
    db  = get_db()
    res = db.table("apify_keys") \
            .select("*") \
            .eq("is_active", True) \
            .lt("usage_count", APIFY_KEY_SAFE_LIMIT) \
            .order("usage_count") \
            .limit(1).execute()
    if not res.data:
        return None
    return res.data[0]["api_key"]


def _supabase_increment_key_usage(api_key: str, count: int):
    from datetime import datetime, timezone
    from src.database import get_db
    db  = get_db()
    res = db.table("apify_keys").select("usage_count").eq("api_key", api_key).execute()
    if res.data:
        current = res.data[0]["usage_count"]
        db.table("apify_keys").update({
            "usage_count":  current + count,
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }).eq("api_key", api_key).execute()


def _supabase_reset_monthly_usage():
    from datetime import datetime, date
    from dateutil.relativedelta import relativedelta
    from src.database import get_db
    db    = get_db()
    today = date.today().isoformat()
    res   = db.table("apify_keys").select("id").lte("reset_at", today).execute()
    if res.data:
        ids        = [r["id"] for r in res.data]
        next_month = (datetime.today() + relativedelta(months=1)).replace(day=1).date().isoformat()
        for key_id in ids:
            db.table("apify_keys").update({
                "usage_count": 0,
                "reset_at":    next_month,
            }).eq("id", key_id).execute()
        logger.info(f"Reset usage_count cho {len(ids)} keys")
