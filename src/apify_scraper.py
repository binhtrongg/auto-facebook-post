"""
Scrape bài viết từ Facebook Pages qua Apify API.
- Chạy actor apify/facebook-posts-scraper
- Mỗi item trả về là 1 post (flat format, không lồng)
- Chờ kết quả (synchronous call, timeout 5 phút)
"""
import logging
import time
import httpx
from src.config import APIFY_ACTOR_ID, MAX_POSTS_PER_PAGE
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

    return _parse_results(raw_items, page_urls)


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
                   requested_urls: list[str]) -> dict[str, list[dict]]:
    """
    Parse kết quả từ facebook-posts-scraper.
    Mỗi item là 1 post (flat), không lồng nhau.

    Fields quan trọng:
      postId       → fb_post_id
      text         → content
      time         → post_time (ISO8601)
      facebookUrl  → page URL
      media        → danh sách media (ảnh/video)
    """
    # Gom posts theo page URL
    by_page: dict[str, list[dict]] = {}

    for item in raw_items:
        post_id = str(item.get("postId") or item.get("id") or "").strip()
        if not post_id:
            continue

        page_url = (item.get("facebookUrl") or item.get("inputUrl") or "").rstrip("/")
        content  = (item.get("text") or "").strip()
        post_time = item.get("time") or item.get("timestamp")

        # Extract image & video URLs từ trường media
        image_urls, video_url = _extract_media(item.get("media") or [])

        if not content and not image_urls and not video_url:
            continue

        post = {
            "fb_post_id":  post_id,
            "content":     content,
            "image_urls":  image_urls,
            "video_url":   video_url,
            "post_time":   str(post_time) if post_time else None,
        }

        matched = _match_url(page_url, requested_urls) or page_url
        by_page.setdefault(matched, []).append(post)

    for url, posts in by_page.items():
        logger.info(f"  {url}: {len(posts)} bài")

    return by_page


def _extract_media(media_list: list) -> tuple[list[str], str | None]:
    """
    Trích xuất image_urls và video_url từ trường media của Apify.

    Cấu trúc media có thể có nhiều dạng:
    - Photo: nodes[].media.viewer_image.uri  (độ phân giải cao nhất)
    - Video: nodes[].media.videoUrl hoặc .dashManifestUrl
    """
    image_urls: list[str] = []
    video_url:  str | None = None
    seen:       set[str]  = set()

    for media_item in media_list:
        if not isinstance(media_item, dict):
            continue

        # Duyệt các loại subattachment (two/three/four/five/frame)
        for key in ("frame_sublayout_subattachments",
                    "two_photos_subattachments",
                    "three_photos_subattachments",
                    "four_photos_subattachments",
                    "five_photos_subattachments"):
            sub = media_item.get(key, {})
            if not isinstance(sub, dict):
                continue
            for node in sub.get("nodes", []):
                m = node.get("media", {})
                if not isinstance(m, dict):
                    continue

                typename = m.get("__typename", "")

                if typename == "Video" or m.get("videoUrl"):
                    # Video
                    vurl = (m.get("videoUrl") or
                            m.get("dashManifestUrl") or
                            m.get("browser_native_hd_url") or
                            m.get("browser_native_sd_url"))
                    if vurl and not video_url:
                        video_url = vurl
                else:
                    # Photo: ưu tiên viewer_image (cao nhất), fallback image
                    vi = m.get("viewer_image") or m.get("image") or {}
                    uri = vi.get("uri") if isinstance(vi, dict) else None
                    if uri and uri not in seen:
                        seen.add(uri)
                        image_urls.append(uri)

    return image_urls, video_url


def _match_url(scraped_url: str, requested_urls: list[str]) -> str | None:
    s = scraped_url.lower().rstrip("/")
    for url in requested_urls:
        if url.lower().rstrip("/") == s:
            return url
    return None
