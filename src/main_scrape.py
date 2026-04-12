"""
Entry point cho JOB SCRAPE.
Chạy bởi GitHub Actions mỗi 8 tiếng.

Flow mới (schedule trực tiếp lên Facebook):
  1. Lấy tất cả source pages đang hoạt động (gộp theo group)
  2. Với mỗi group: scrape tất cả source pages qua Apify
  3. Với mỗi bài mới (chưa đăng):
     → Tính thời điểm hẹn giờ cho từng trang đích
     → Upload + hẹn giờ thẳng lên Facebook (Facebook giữ bài, tự đăng)
     → Lưu dedup để tránh đăng lại
  4. KHÔNG cần job post riêng (main_post.py không cần nữa)
"""
import logging
import sys
from datetime import datetime, timezone

from src.config import DB_BACKEND

if DB_BACKEND == "sheets":
    from src.sheets_db import (
        get_active_source_pages,
        get_destination_pages_by_group,
        is_post_exists,
        save_dedup,
        save_log,
        update_source_page_scraped_at,
    )
else:
    from src.database import (
        get_active_source_pages,
        get_destination_pages_by_group,
        is_post_exists,
        save_dedup,
        save_log,
        update_source_page_scraped_at,
    )
from src.apify_scraper import scrape_pages
from src.fb_poster import FacebookPoster
from src.post_scheduler import build_schedule_for_group, commit_schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main_scrape")


def run():
    logger.info("=" * 60)
    logger.info("BẮT ĐẦU JOB SCRAPE + SCHEDULE")
    logger.info("=" * 60)

    all_pages = get_active_source_pages()
    if not all_pages:
        logger.info("Không có source page nào. Thoát.")
        return

    # Gộp pages theo group_id
    groups: dict[str, list[dict]] = {}
    for page in all_pages:
        groups.setdefault(page["group_id"], []).append(page)

    logger.info(f"Tìm thấy {len(all_pages)} trang nguồn trong {len(groups)} nhóm")

    total_new     = 0
    total_errors  = 0

    for group_id, pages in groups.items():
        group_name = pages[0].get("page_groups", {}).get("name", group_id[:8])
        logger.info(f"\n--- Nhóm: {group_name} ({len(pages)} trang) ---")

        page_urls   = [p["fb_page_url"] for p in pages]
        url_to_page = {p["fb_page_url"]: p for p in pages}

        # Scrape
        try:
            scraped = scrape_pages(page_urls)
        except Exception as e:
            logger.error(f"Lỗi scrape group {group_name}: {e}")
            total_errors += 1
            continue

        # Gom tất cả bài mới (chưa tồn tại trong dedup) của group này
        new_posts: list[tuple[dict, dict]] = []  # [(post_data, page), ...]
        for page_url, posts in scraped.items():
            page = url_to_page.get(page_url)
            if not page:
                continue
            for post in posts:
                if not is_post_exists(post["fb_post_id"]):
                    new_posts.append((post, page))

            update_source_page_scraped_at(
                page["id"],
                datetime.now(timezone.utc).isoformat(),
            )

        if not new_posts:
            logger.info("  → Không có bài mới")
            continue

        logger.info(f"  → Tìm thấy {len(new_posts)} bài mới, đang hẹn giờ...")

        # Lấy danh sách trang đích
        destinations = get_destination_pages_by_group(group_id)
        if not destinations:
            logger.warning(f"  → Group {group_name} không có trang đích nào")
            continue

        # Tính lịch: mỗi trang đích nhận đủ len(new_posts) slot
        schedule = build_schedule_for_group(group_id, len(new_posts))

        # Với mỗi bài mới → hẹn giờ trên từng trang đích
        for dest in destinations:
            dest_id      = dest["id"]
            dest_name    = dest.get("fb_page_name", dest_id[:8])
            slots        = schedule.get(dest_id, [])
            scheduled_ok = 0

            for idx, (post, page) in enumerate(new_posts):
                fb_post_id = post["fb_post_id"]
                slot       = slots[idx] if idx < len(slots) else None

                if slot is None:
                    logger.error(f"  Thiếu slot cho bài {idx}, dest {dest_name}")
                    continue

                try:
                    poster = FacebookPoster(
                        page_id      = dest["fb_page_id"],
                        access_token = dest["fb_access_token"],
                    )
                    poster.post(
                        content      = post.get("content") or "",
                        image_urls   = post.get("image_urls") or [],
                        video_url    = post.get("video_url"),
                        scheduled_at = slot,
                    )

                    # Lưu dedup ngay để lần scrape sau không xử lý lại
                    save_dedup(fb_post_id, page["id"], dest_id)
                    save_log(
                        scheduled_post_id   = None,
                        fb_post_id          = fb_post_id,
                        destination_page_id = dest_id,
                        result              = "scheduled",
                    )
                    scheduled_ok += 1

                except Exception as e:
                    logger.error(
                        f"  Lỗi hẹn giờ bài {fb_post_id[:20]}... "
                        f"→ {dest_name}: {e}"
                    )
                    save_log(
                        scheduled_post_id   = None,
                        fb_post_id          = fb_post_id,
                        destination_page_id = dest_id,
                        result              = "failed",
                        error_message       = str(e),
                    )
                    total_errors += 1

            # Lưu slot cuối cùng để lần sau nối tiếp
            commit_schedule(dest_id, slots[:scheduled_ok])

            logger.info(
                f"  {dest_name}: đã hẹn giờ {scheduled_ok}/{len(new_posts)} bài"
            )

        total_new += len(new_posts)

    logger.info("\n" + "=" * 60)
    logger.info(f"KẾT THÚC: +{total_new} bài mới | {total_errors} lỗi")
    logger.info("=" * 60)

    if total_errors > 0 and total_new == 0:
        sys.exit(1)


if __name__ == "__main__":
    run()
