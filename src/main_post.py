"""
Entry point cho JOB POST.
Chạy bởi GitHub Actions mỗi 30 phút.

Flow:
  1. Lấy tất cả bài đã đến giờ đăng (scheduled_at <= now)
  2. Đăng từng bài lên Facebook Page tương ứng
  3. Cleanup: xóa content khỏi Supabase, lưu dedup
"""
import logging
import sys

from src.database import (
    get_due_scheduled_posts,
    mark_scheduled_post_done,
    mark_scheduled_post_failed,
)
from src.fb_poster import FacebookPoster
from src.cleanup import cleanup_after_post

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main_post")

# Số lần retry tối đa trước khi bỏ qua bài
MAX_RETRY = 3


def run():
    logger.info("=" * 60)
    logger.info("BẮT ĐẦU JOB POST")
    logger.info("=" * 60)

    due_posts = get_due_scheduled_posts()

    if not due_posts:
        logger.info("Không có bài nào cần đăng lúc này.")
        return

    logger.info(f"Tìm thấy {len(due_posts)} bài cần đăng")

    success_count = 0
    fail_count    = 0

    for item in due_posts:
        scheduled_post_id   = item["id"]
        post                = item.get("posts") or {}
        dest                = item.get("destination_pages") or {}

        fb_post_id          = post.get("fb_post_id", "")
        content             = post.get("content") or ""
        image_urls          = post.get("image_urls") or []
        video_url           = post.get("video_url")
        source_page_id      = post.get("source_page_id", "")
        destination_page_id = item.get("destination_page_id", "")
        fb_page_id          = dest.get("fb_page_id", "")
        access_token        = dest.get("fb_access_token", "")
        retry_count         = item.get("retry_count", 0)

        # Bỏ qua nếu thiếu thông tin cần thiết
        if not fb_page_id or not access_token:
            logger.error(f"Thiếu page_id hoặc token cho dest {destination_page_id[:8]}...")
            mark_scheduled_post_failed(scheduled_post_id)
            fail_count += 1
            continue

        # Bỏ qua nếu đã retry quá nhiều lần
        if retry_count >= MAX_RETRY:
            logger.warning(f"Bài {fb_post_id[:20]}... đã retry {retry_count} lần, bỏ qua")
            mark_scheduled_post_failed(scheduled_post_id)
            fail_count += 1
            continue

        # Đăng bài
        logger.info(f"Đang đăng: {fb_post_id[:20]}... → Page {fb_page_id}")
        try:
            poster = FacebookPoster(
                page_id      = fb_page_id,
                access_token = access_token,
            )
            new_fb_post_id = poster.post(
                content    = content,
                image_urls = image_urls if isinstance(image_urls, list) else [],
                video_url  = video_url,
            )

            logger.info(f"  ✓ Đăng thành công → FB post ID: {new_fb_post_id}")
            mark_scheduled_post_done(scheduled_post_id)
            cleanup_after_post(
                scheduled_post_id   = scheduled_post_id,
                post_id             = post.get("id", ""),
                fb_post_id          = fb_post_id,
                source_page_id      = source_page_id,
                destination_page_id = destination_page_id,
                success             = True,
            )
            success_count += 1

        except Exception as e:
            error_msg = str(e)
            logger.error(f"  ✗ Đăng thất bại: {error_msg}")
            mark_scheduled_post_failed(scheduled_post_id)
            cleanup_after_post(
                scheduled_post_id   = scheduled_post_id,
                post_id             = post.get("id", ""),
                fb_post_id          = fb_post_id,
                source_page_id      = source_page_id,
                destination_page_id = destination_page_id,
                success             = False,
                error_msg           = error_msg,
            )
            fail_count += 1

    logger.info("\n" + "=" * 60)
    logger.info(f"KẾT THÚC POST: ✓ {success_count} thành công | ✗ {fail_count} thất bại")
    logger.info("=" * 60)

    if fail_count > 0 and success_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    run()
