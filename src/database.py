"""
Wrapper cho Supabase client.
Tất cả thao tác DB đi qua module này.
"""
import logging
from supabase import create_client, Client
from src.config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_db() -> Client:
    """Trả về Supabase client (singleton)."""
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ── Source Pages ───────────────────────────────────────────

def get_active_source_pages() -> list[dict]:
    """Lấy tất cả trang nguồn đang hoạt động."""
    db = get_db()
    res = db.table("source_pages").select("*, page_groups(id, name)") \
            .eq("is_active", True).execute()
    return res.data


def update_source_page_scraped_at(page_id: str, scraped_at: str):
    db = get_db()
    db.table("source_pages").update({"last_scraped_at": scraped_at}) \
      .eq("id", page_id).execute()


# ── Destination Pages ──────────────────────────────────────

def get_destination_pages_by_group(group_id: str) -> list[dict]:
    """Lấy trang đích theo group."""
    db = get_db()
    res = db.table("destination_pages") \
            .select("*") \
            .eq("group_id", group_id) \
            .eq("is_active", True).execute()
    return res.data


# ── Posts ──────────────────────────────────────────────────

def is_post_exists(fb_post_id: str) -> bool:
    """Kiểm tra bài đã được scrape hoặc đăng chưa (dedup)."""
    db = get_db()
    # Kiểm tra trong bảng dedup (bài đã đăng)
    res1 = db.table("posted_dedup").select("fb_post_id") \
             .eq("fb_post_id", fb_post_id).execute()
    if res1.data:
        return True
    # Kiểm tra trong bảng posts (bài đang pending/scheduled)
    res2 = db.table("posts").select("id") \
             .eq("fb_post_id", fb_post_id).execute()
    return bool(res2.data)


def save_post(fb_post_id: str, source_page_id: str, content: str,
              image_urls: list, video_url: str | None,
              original_post_time: str | None) -> str | None:
    """
    Lưu bài mới vào DB.
    Trả về post.id nếu thành công, None nếu trùng.
    """
    if is_post_exists(fb_post_id):
        return None

    db = get_db()
    res = db.table("posts").insert({
        "fb_post_id":         fb_post_id,
        "source_page_id":     source_page_id,
        "content":            content,
        "image_urls":         image_urls,
        "video_url":          video_url,
        "original_post_time": original_post_time,
        "status":             "pending",
    }).execute()

    if res.data:
        return res.data[0]["id"]
    return None


def get_post_by_id(post_id: str) -> dict | None:
    db = get_db()
    res = db.table("posts").select("*").eq("id", post_id).execute()
    return res.data[0] if res.data else None


def update_post_status(post_id: str, status: str):
    db = get_db()
    db.table("posts").update({"status": status}).eq("id", post_id).execute()


def clear_post_content(post_id: str):
    """Xóa content/media sau khi đã đăng để tiết kiệm storage."""
    db = get_db()
    db.table("posts").update({
        "content":    None,
        "image_urls": None,
        "video_url":  None,
        "status":     "posted",
    }).eq("id", post_id).execute()


# ── Scheduled Posts ────────────────────────────────────────

def create_scheduled_post(post_id: str, destination_page_id: str,
                          scheduled_at: str) -> str:
    db = get_db()
    res = db.table("scheduled_posts").insert({
        "post_id":              post_id,
        "destination_page_id":  destination_page_id,
        "scheduled_at":         scheduled_at,
        "status":               "pending",
    }).execute()
    return res.data[0]["id"]


def get_due_scheduled_posts() -> list[dict]:
    """Lấy các bài đã đến giờ đăng (scheduled_at <= now)."""
    db = get_db()
    res = db.table("scheduled_posts") \
            .select("*, posts(*), destination_pages(*)") \
            .eq("status", "pending") \
            .lte("scheduled_at", "now()") \
            .order("scheduled_at") \
            .execute()
    return res.data


def get_last_scheduled_time(destination_page_id: str) -> str | None:
    """Lấy scheduled_at mới nhất của trang đích (để nối tiếp lịch)."""
    db = get_db()
    res = db.table("scheduled_posts") \
            .select("scheduled_at") \
            .eq("destination_page_id", destination_page_id) \
            .in_("status", ["pending"]) \
            .order("scheduled_at", desc=True) \
            .limit(1).execute()
    return res.data[0]["scheduled_at"] if res.data else None


def get_dest_last_scheduled(destination_page_id: str) -> str | None:
    """Lấy thời điểm đã hẹn cuối cùng cho trang đích (cột last_scheduled_at)."""
    db = get_db()
    res = db.table("destination_pages") \
            .select("last_scheduled_at") \
            .eq("id", destination_page_id).execute()
    if res.data:
        return res.data[0].get("last_scheduled_at")
    return None


def update_dest_last_scheduled(destination_page_id: str, scheduled_at: str):
    """Cập nhật thời điểm hẹn giờ cuối cùng cho trang đích."""
    db = get_db()
    db.table("destination_pages") \
      .update({"last_scheduled_at": scheduled_at}) \
      .eq("id", destination_page_id).execute()


def mark_scheduled_post_done(scheduled_post_id: str):
    db = get_db()
    db.table("scheduled_posts") \
      .update({"status": "posted"}) \
      .eq("id", scheduled_post_id).execute()


def mark_scheduled_post_failed(scheduled_post_id: str):
    db = get_db()
    res = db.table("scheduled_posts").select("retry_count") \
            .eq("id", scheduled_post_id).execute()
    count = res.data[0]["retry_count"] if res.data else 0
    db.table("scheduled_posts").update({
        "status":      "failed",
        "retry_count": count + 1,
    }).eq("id", scheduled_post_id).execute()


def delete_scheduled_post(scheduled_post_id: str):
    db = get_db()
    db.table("scheduled_posts").delete() \
      .eq("id", scheduled_post_id).execute()


# ── Dedup ──────────────────────────────────────────────────

def save_dedup(fb_post_id: str, source_page_id: str,
               destination_page_id: str):
    """Lưu record dedup sau khi đăng thành công."""
    db = get_db()
    db.table("posted_dedup").upsert({
        "fb_post_id":           fb_post_id,
        "source_page_id":       source_page_id,
        "destination_page_id":  destination_page_id,
    }).execute()


# ── Logs ───────────────────────────────────────────────────

def save_log(scheduled_post_id: str | None, fb_post_id: str,
             destination_page_id: str, result: str,
             error_message: str | None = None):
    db = get_db()
    db.table("post_logs").insert({
        "scheduled_post_id":  scheduled_post_id,
        "fb_post_id":         fb_post_id,
        "destination_page_id": destination_page_id,
        "result":             result,
        "error_message":      error_message,
    }).execute()
