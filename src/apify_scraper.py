"""
Scrape bài viết từ Facebook Pages qua Apify API.
- Chạy actor apify/facebook-posts-scraper
- Mỗi item trả về là 1 post (flat format, không lồng)
- Chờ kết quả (synchronous call, timeout 5 phút)
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from dateutil.parser import isoparse

from src.config import APIFY_ACTOR_ID, MAX_POSTS_PER_PAGE, SCRAPE_LOOKBACK_HOURS
from src.key_rotator import get_active_key, increment_key_usage

logger = logging.getLogger(__name__)

APIFY_BASE      = "https://api.apify.com/v2"
TIMEOUT_SECONDS = 300   # 5 phút chờ tối đa
POLL_INTERVAL   = 10    # kiểm tra kết quả mỗi 10 giây


def scrape_pages(page_urls: list[str]) -> dict[str, list[dict]]:
    """
    Scrape nhiều Facebook page cùng lúc trong 1 actor run.

    Returns:
        {page_url: [list of posts]}
        Mỗi post: {fb_post_id, content, image_urls, video_url, post_time}
    """
    api_key = get_active_key()
    if not api_key:
        raise RuntimeError("Không có Apify API key khả dụng")

    logger.info(f"Bắt đầu scrape {len(page_urls)} trang...")

    actor_input = {
        "startUrls": [{"url": url} for url in page_urls],
        "maxPosts":  MAX_POSTS_PER_PAGE,
    }

    run_id, dataset_id = _start_actor_run(api_key, actor_input)
    if not run_id:
        return {}

    success = _wait_for_run(api_key, run_id)
    if not success:
        logger.error(f"Actor run {run_id} thất bại hoặc timeout")
        return {}

    raw_items = _fetch_dataset(api_key, dataset_id)
    increment_key_usage(api_key, count=len(page_urls))

    since = datetime.now(timezone.utc) - timedelta(hours=SCRAPE_LOOKBACK_HOURS)
    return _parse_results(raw_items, page_urls, since)


def _start_actor_run(api_key: str,
                     actor_input: dict) -> tuple[str | None, str | None]:
    url = f"{APIFY_BASE}/acts/{APIFY_ACTOR_ID}/runs"
    try:
        resp = httpx.post(
            url,
            params={"token": api_key},
            json=actor_input,
            timeout=30,
        )
        resp.raise_for_status()
        data       = resp.json()["data"]
        run_id     = data["id"]
        dataset_id = data["defaultDatasetId"]
        logger.info(f"Actor run khởi động: {run_id}")
        return run_id, dataset_id
    except Exception as e:
        logger.error(f"Lỗi khởi chạy Apify actor: {e}")
        return None, None


def _wait_for_run(api_key: str, run_id: str) -> bool:
    url     = f"{APIFY_BASE}/actor-runs/{run_id}"
    elapsed = 0
    while elapsed < TIMEOUT_SECONDS:
        try:
            resp   = httpx.get(url, params={"token": api_key}, timeout=15)
            resp.raise_for_status()
            status = resp.json()["data"]["status"]

            if status == "SUCCEEDED":
                logger.info(f"Actor run hoàn thành sau {elapsed}s")
                return True
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                logger.error(f"Actor run kết thúc: {status}")
                return False

            logger.debug(f"Đang chờ... {status} ({elapsed}s)")
        except Exception as e:
            logger.warning(f"Lỗi poll: {e}")

        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    logger.error(f"Timeout sau {TIMEOUT_SECONDS}s")
    return False


def _fetch_dataset(api_key: str, dataset_id: str) -> list[dict]:
    url = f"{APIFY_BASE}/datasets/{dataset_id}/items"
    try:
        resp = httpx.get(
            url,
            params={"token": api_key, "clean": "true", "limit": 500},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Lỗi lấy dataset: {e}")
        return []


def _parse_results(raw_items: list[dict],
                   requested_urls: list[str],
                   since: datetime | None = None) -> dict[str, list[dict]]:
    """
    Parse kết quả từ facebook-posts-scraper.
    Mỗi item là 1 post (flat), không lồng nhau.

    Fields quan trọng:
      postId         → fb_post_id
      text           → content
      time           → post_time (ISO8601)
      facebookUrl    → page URL
      media          → danh sách media (ảnh/video)
      likesCount     → lượt thích
      commentsCount  → bình luận
      sharesCount    → chia sẻ
    """
    by_page: dict[str, list[dict]] = {}
    skipped_old = 0

    for item in raw_items:
        post_id = str(item.get("postId") or item.get("id") or "").strip()
        if not post_id:
            continue

        page_url  = (item.get("facebookUrl") or item.get("inputUrl") or "").rstrip("/")
        content   = (item.get("text") or "").strip()
        post_time = item.get("time") or item.get("timestamp")

        # Lọc bài quá cũ
        if since and post_time:
            try:
                pt = isoparse(str(post_time))
                if pt.tzinfo is None:
                    pt = pt.replace(tzinfo=timezone.utc)
                if pt < since:
                    skipped_old += 1
                    continue
            except Exception:
                pass  # Nếu parse lỗi thì giữ lại bài

        # Extract media
        image_urls, video_url = _extract_media(item.get("media") or [])

        # Fallback: video/reels ở top-level
        if not video_url:
            video_obj = item.get("video")
            if isinstance(video_obj, dict):
                video_url = (video_obj.get("url") or video_obj.get("hdUrl") or
                             video_obj.get("sdUrl") or video_obj.get("videoUrl"))
            elif isinstance(video_obj, str) and video_obj:
                video_url = video_obj
        if not video_url:
            video_url = (item.get("videoUrl") or item.get("videoHdUrl") or
                         item.get("videoSdUrl") or item.get("video_url") or
                         (item.get("url") if item.get("type") == "video" else None))

        # Debug: log keys của post không có media để tìm field chứa video/reels
        if not image_urls and not video_url:
            all_keys = list(item.keys())
            video_keys = [k for k in all_keys if "video" in k.lower() or "reel" in k.lower() or "attach" in k.lower()]
            if video_keys or item.get("media"):
                logger.debug(f"Post {post_id[:20]} no-media keys: {video_keys}, media={item.get('media')}")
            # Check thêm các field video phổ biến
            raw_video = (item.get("video") or item.get("videoUrl") or
                         item.get("attachments") or item.get("videoHdUrl") or
                         item.get("videoSdUrl"))
            if raw_video and not video_url:
                logger.info(f"Post {post_id[:20]} has raw video field: {str(raw_video)[:150]}")

        if not content and not image_urls and not video_url:
            continue

        # Engagement metrics
        likes    = int(item.get("likesCount")    or item.get("likes")    or 0)
        comments = int(item.get("commentsCount") or item.get("comments") or 0)
        shares   = int(item.get("sharesCount")   or item.get("shares")   or 0)
        engagement_score = likes + comments * 2 + shares * 3

        # Tạo URL trực tiếp đến bài gốc
        post_url = (item.get("url") or item.get("postUrl") or
                    f"https://www.facebook.com/permalink.php?story_fbid={post_id}&id={page_url.split('id=')[-1] if 'id=' in page_url else page_url.split('facebook.com/')[-1].rstrip('/')}")

        post = {
            "fb_post_id":       post_id,
            "post_url":         post_url,
            "content":          content,
            "image_urls":       image_urls,
            "video_url":        video_url,
            "post_time":        str(post_time) if post_time else None,
            "likes":            likes,
            "comments":         comments,
            "shares":           shares,
            "engagement_score": engagement_score,
        }

        matched = _match_url(page_url, requested_urls) or page_url
        by_page.setdefault(matched, []).append(post)

    if skipped_old:
        logger.info(f"  Bỏ qua {skipped_old} bài cũ hơn {SCRAPE_LOOKBACK_HOURS}h")

    for url, posts in by_page.items():
        videos = sum(1 for p in posts if p.get("video_url"))
        imgs   = sum(1 for p in posts if p.get("image_urls"))
        logger.info(f"  {url}: {len(posts)} bài ({imgs} có ảnh, {videos} có video)")

    return by_page


def _extract_media(media_list: list) -> tuple[list[str], str | None]:
    """
    Trích xuất image_urls và video_url từ trường media của Apify.

    Apify facebook-posts-scraper trả về mỗi item trong media[] là 1 ảnh/video:
    - Photo: item.photo_image.uri  hoặc item.thumbnail
    - Video: item.videoUrl / item.browser_native_hd_url / item.browser_native_sd_url
    """
    image_urls: list[str] = []
    video_url:  str | None = None
    seen:       set[str]  = set()

    def _add_image(uri: str):
        if uri and uri not in seen:
            seen.add(uri)
            image_urls.append(uri)

    for item in media_list:
        if not isinstance(item, dict):
            continue

        typename = item.get("__typename", "")

        # ── Video / Reels ─────────────────────────────────────
        is_video = (typename in ("Video", "Reel", "UnifiedVideo") or
                    bool(item.get("videoUrl")) or
                    bool(item.get("browser_native_hd_url")) or
                    bool(item.get("browser_native_sd_url")))
        if is_video:
            vurl = (item.get("videoUrl") or
                    item.get("browser_native_hd_url") or
                    item.get("browser_native_sd_url") or
                    item.get("dashManifestUrl") or
                    item.get("hdUrl") or
                    item.get("sdUrl"))
            if vurl and not video_url:
                video_url = vurl
            continue

        # ── Photo trực tiếp (cấu trúc phổ biến nhất) ────────
        photo_image = item.get("photo_image")
        if isinstance(photo_image, dict) and photo_image.get("uri"):
            _add_image(photo_image["uri"])
            continue

        # ── viewer_image fallback ────────────────────────────
        viewer_image = item.get("viewer_image")
        if isinstance(viewer_image, dict) and viewer_image.get("uri"):
            _add_image(viewer_image["uri"])
            continue

        # ── thumbnail fallback (luôn có) ─────────────────────
        thumbnail = item.get("thumbnail")
        if thumbnail:
            _add_image(thumbnail)

    return image_urls, video_url


def _match_url(scraped_url: str, requested_urls: list[str]) -> str | None:
    s = scraped_url.lower().rstrip("/")
    for url in requested_urls:
        if url.lower().rstrip("/") == s:
            return url
    return None
