"""
Dọn dẹp sau khi đăng bài thành công.
- Xóa content/media trong bảng posts (tiết kiệm Supabase storage)
- Xóa scheduled_post record
- Lưu dedup record
"""
import logging
from src.database import (
    clear_post_content,
    delete_scheduled_post,
    save_dedup,
    save_log,
)

logger = logging.getLogger(__name__)


def cleanup_after_post(
    scheduled_post_id: str,
    post_id: str,
    fb_post_id: str,
    source_page_id: str,
    destination_page_id: str,
    success: bool,
    error_msg: str | None = None,
):
    """
    Thực hiện dọn dẹp sau khi đăng bài.

    Args:
        scheduled_post_id:   ID trong bảng scheduled_posts
        post_id:             ID trong bảng posts
        fb_post_id:          Facebook post ID gốc (dedup key)
        source_page_id:      ID trang nguồn
        destination_page_id: ID trang đích
        success:             True nếu đăng thành công
        error_msg:           Thông báo lỗi nếu thất bại
    """
    try:
        if success:
            # 1. Lưu dedup (giữ mãi để không đăng lại)
            save_dedup(fb_post_id, source_page_id, destination_page_id)

            # 2. Xóa content/media trong posts (tiết kiệm storage)
            clear_post_content(post_id)

            # 3. Xóa scheduled_post record (không cần nữa)
            delete_scheduled_post(scheduled_post_id)

            # 4. Log thành công
            save_log(
                scheduled_post_id   = scheduled_post_id,
                fb_post_id          = fb_post_id,
                destination_page_id = destination_page_id,
                result              = "success",
            )
            logger.info(f"Cleanup xong: {fb_post_id[:20]}...")

        else:
            # Đăng thất bại: chỉ log, giữ lại scheduled_post để retry
            save_log(
                scheduled_post_id   = scheduled_post_id,
                fb_post_id          = fb_post_id,
                destination_page_id = destination_page_id,
                result              = "failed",
                error_message       = error_msg,
            )
            logger.warning(f"Đăng thất bại: {fb_post_id[:20]}... | {error_msg}")

    except Exception as e:
        logger.error(f"Lỗi trong cleanup: {e}")
