"""
Đăng bài lên Facebook Page qua Graph API.
- Text only
- 1 ảnh
- Nhiều ảnh (album)
- Video (stream upload, không lưu vào Supabase)

Hỗ trợ 2 chế độ:
- Đăng ngay (scheduled_at=None)
- Hẹn giờ (scheduled_at=datetime) → Facebook giữ bài, tự đăng đúng giờ
"""
import json
import logging
import os
import tempfile
from datetime import datetime, timezone

import httpx

from src.config import FB_API_BASE, FB_API_VERSION

logger = logging.getLogger(__name__)

# Giới hạn kích thước tải về (bytes)
MAX_IMAGE_SIZE = 10 * 1024 * 1024    # 10 MB
MAX_VIDEO_SIZE = 1024 * 1024 * 1024  # 1 GB

# Facebook yêu cầu scheduled_publish_time phải cách hiện tại ít nhất 10 phút
MIN_SCHEDULE_AHEAD_SECONDS = 10 * 60


class FacebookPoster:
    def __init__(self, page_id: str, access_token: str):
        self.page_id      = page_id
        self.access_token = access_token
        self.base         = FB_API_BASE

    def post(self, content: str, image_urls: list[str],
             video_url: str | None,
             scheduled_at: datetime | None = None,
             reel_url: str | None = None) -> str:
        """
        Đăng bài lên Page. Trả về Facebook post ID mới tạo.
        Raises exception nếu thất bại.

        Args:
            scheduled_at: Nếu truyền vào, bài sẽ được hẹn giờ trên Facebook
                          (Facebook giữ bài và tự đăng đúng giờ).
                          Phải là timezone-aware datetime (UTC).
            reel_url:     URL của Facebook Reel gốc — yt-dlp tải về rồi
                          upload lên trang như video native.
        """
        scheduled_ts = _to_unix_ts(scheduled_at) if scheduled_at else None

        if reel_url:
            return self._post_reel_as_video(content, reel_url, scheduled_ts)
        elif video_url:
            return self._post_video(content, video_url, scheduled_ts)
        elif len(image_urls) > 1:
            return self._post_multiple_images(content, image_urls, scheduled_ts)
        elif len(image_urls) == 1:
            return self._post_single_image(content, image_urls[0], scheduled_ts)
        else:
            return self._post_text(content, scheduled_ts)

    # ── Reel: download via yt-dlp → upload video ──────────

    def _post_reel_as_video(self, content: str, reel_url: str,
                             scheduled_ts: int | None = None) -> str:
        """Tải Reel về bằng yt-dlp rồi upload lên Facebook như video native."""
        import yt_dlp

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name
        # Xóa file rỗng để yt-dlp không bỏ qua vì "đã tồn tại"
        os.unlink(tmp_path)

        try:
            logger.info(f"yt-dlp tải reel: {reel_url}")
            cookie_file = os.environ.get("FACEBOOK_COOKIE_FILE", "")
            if cookie_file:
                if os.path.exists(cookie_file):
                    size = os.path.getsize(cookie_file)
                    logger.info(f"Cookie file: {cookie_file} ({size} bytes)")
                else:
                    logger.warning(f"Cookie file không tồn tại: {cookie_file}")
            else:
                logger.warning("FACEBOOK_COOKIE_FILE không được set — yt-dlp không có cookies")

            ydl_opts = {
                "format":              "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
                "outtmpl":             tmp_path,
                "merge_output_format": "mp4",
                "no_cache_dir":        True,
                "ignoreerrors":        False,
                "quiet":               True,
                "no_warnings":         False,
            }
            if cookie_file and os.path.exists(cookie_file):
                ydl_opts["cookiefile"] = cookie_file
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ret = ydl.download([reel_url])
                if ret != 0:
                    raise RuntimeError(f"yt-dlp trả về exit code {ret}")

            # yt-dlp có thể đổi tên file (thêm extension)
            actual_path = tmp_path
            for candidate in [tmp_path, tmp_path + ".mp4",
                               tmp_path.replace(".mp4", "") + ".mp4"]:
                if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                    actual_path = candidate
                    break
            else:
                raise RuntimeError("yt-dlp không tạo ra file video nào")

            file_size = os.path.getsize(actual_path)
            if file_size == 0:
                raise RuntimeError("File video tải về rỗng (0 bytes)")
            logger.info(f"Đã tải {file_size/1024/1024:.1f}MB, upload lên Facebook...")

            if file_size < 1024 * 1024:
                return self._post_video_simple(content, actual_path, scheduled_ts)
            else:
                return self._post_video_resumable(content, actual_path, file_size, scheduled_ts)

        finally:
            for path in [tmp_path, tmp_path + ".mp4"]:
                if os.path.exists(path):
                    os.unlink(path)
                    logger.info(f"Đã xóa file tạm: {path}")

    # ── Text only ──────────────────────────────────────────

    def _post_text(self, content: str,
                   scheduled_ts: int | None = None) -> str:
        url  = f"{self.base}/{self.page_id}/feed"
        data = {
            "message":      content,
            "access_token": self.access_token,
        }
        if scheduled_ts:
            data["published"]               = "false"
            data["scheduled_publish_time"]  = str(scheduled_ts)
        resp = httpx.post(url, data=data, timeout=30)
        resp.raise_for_status()
        return resp.json()["id"]

    # ── 1 ảnh ──────────────────────────────────────────────

    def _post_single_image(self, content: str, image_url: str,
                           scheduled_ts: int | None = None) -> str:
        if scheduled_ts:
            # Khi hẹn giờ: phải upload ảnh unpublished trước,
            # rồi tạo scheduled feed post đính kèm ảnh
            photo_id = self._upload_unpublished_photo(image_url)
            return self._post_feed_with_photos([photo_id], content, scheduled_ts)

        # Đăng ngay: Facebook tự fetch URL
        url  = f"{self.base}/{self.page_id}/photos"
        resp = httpx.post(url, data={
            "url":          image_url,
            "caption":      content,
            "access_token": self.access_token,
        }, timeout=60)

        if resp.status_code != 200:
            logger.warning("Không thể dùng URL trực tiếp, thử download binary...")
            return self._post_single_image_binary(content, image_url)

        return resp.json().get("post_id") or resp.json().get("id")

    def _post_single_image_binary(self, content: str,
                                   image_url: str) -> str:
        """Download ảnh → upload binary lên Facebook."""
        image_data = _download_bytes(image_url, MAX_IMAGE_SIZE)
        url  = f"{self.base}/{self.page_id}/photos"
        resp = httpx.post(url, data={
            "caption":      content,
            "access_token": self.access_token,
        }, files={"source": ("image.jpg", image_data, "image/jpeg")},
        timeout=60)
        resp.raise_for_status()
        return resp.json().get("post_id") or resp.json().get("id")

    # ── Nhiều ảnh ──────────────────────────────────────────

    def _post_multiple_images(self, content: str, image_urls: list[str],
                               scheduled_ts: int | None = None) -> str:
        photo_ids = []
        for img_url in image_urls[:10]:   # Facebook giới hạn 10 ảnh/bài
            try:
                pid = self._upload_unpublished_photo(img_url)
                photo_ids.append(pid)
            except Exception as e:
                logger.warning(f"Bỏ qua ảnh lỗi ({img_url[:60]}...): {e}")

        if not photo_ids:
            # Fallback: đăng text-only nếu tất cả ảnh đều lỗi
            return self._post_text(content, scheduled_ts)

        return self._post_feed_with_photos(photo_ids, content, scheduled_ts)

    def _upload_unpublished_photo(self, image_url: str) -> str:
        """Upload ảnh chưa publish, trả về photo_id."""
        url  = f"{self.base}/{self.page_id}/photos"
        logger.info(f"Upload ảnh (URL): {image_url[:80]}...")
        resp = httpx.post(url, data={
            "url":          image_url,
            "published":    "false",
            "access_token": self.access_token,
        }, timeout=60)

        if resp.status_code != 200:
            logger.warning(f"URL upload thất bại ({resp.status_code}): {resp.text[:200]}")
            logger.info("Thử download binary...")
            image_data = _download_bytes(image_url, MAX_IMAGE_SIZE)

            # Tự detect MIME type từ magic bytes
            mime = _detect_mime(image_data)
            ext  = {"image/png": "png", "image/gif": "gif",
                    "image/webp": "webp"}.get(mime, "jpg")
            logger.info(f"Download {len(image_data)/1024:.0f}KB, mime={mime}, upload binary...")

            resp = httpx.post(url, data={
                "published":    "false",
                "access_token": self.access_token,
            }, files={"source": (f"image.{ext}", image_data, mime)},
            timeout=60)
            logger.info(f"Binary upload status: {resp.status_code}")
            if resp.status_code != 200:
                logger.error(f"Binary upload lỗi: {resp.text[:300]}")

        resp.raise_for_status()
        photo_id = resp.json()["id"]
        logger.info(f"Upload ảnh thành công, photo_id={photo_id}")
        return photo_id

    def _post_feed_with_photos(self, photo_ids: list[str], content: str,
                                scheduled_ts: int | None = None) -> str:
        """Tạo bài feed đính kèm danh sách photo_id (hỗ trợ hẹn giờ)."""
        attached = [{"media_fbid": pid} for pid in photo_ids]
        url  = f"{self.base}/{self.page_id}/feed"
        data = {
            "message":        content,
            "attached_media": json.dumps(attached),
            "access_token":   self.access_token,
        }
        if scheduled_ts:
            data["published"]              = "false"
            data["scheduled_publish_time"] = str(scheduled_ts)
        resp = httpx.post(url, data=data, timeout=60)
        resp.raise_for_status()
        return resp.json()["id"]

    # ── Video ──────────────────────────────────────────────

    def _post_video(self, content: str, video_url: str,
                    scheduled_ts: int | None = None) -> str:
        """
        Upload video bằng Facebook Resumable Upload API.
        Video được download vào /tmp của GitHub Actions runner,
        upload xong thì tự xóa.
        """
        logger.info("Đang tải video xuống /tmp...")

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name
            try:
                _stream_download_to_file(video_url, tmp_path, MAX_VIDEO_SIZE)
                file_size = os.path.getsize(tmp_path)

                if file_size < 1024 * 1024:    # < 1MB: upload thông thường
                    return self._post_video_simple(content, tmp_path, scheduled_ts)
                else:
                    return self._post_video_resumable(content, tmp_path,
                                                      file_size, scheduled_ts)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    logger.info("Đã xóa video tạm")

    def _post_video_simple(self, content: str, file_path: str,
                           scheduled_ts: int | None = None) -> str:
        """Upload video nhỏ (<1MB) theo cách thông thường."""
        url  = f"{self.base}/{self.page_id}/videos"
        data = {
            "description":  content,
            "access_token": self.access_token,
        }
        if scheduled_ts:
            data["published"]              = "false"
            data["scheduled_publish_time"] = str(scheduled_ts)
        with open(file_path, "rb") as f:
            resp = httpx.post(url, data=data,
                              files={"source": ("video.mp4", f, "video/mp4")},
                              timeout=300)
        if resp.status_code != 200:
            logger.error(f"Video upload lỗi {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
        return resp.json()["id"]

    def _post_video_resumable(self, content: str, file_path: str,
                               file_size: int,
                               scheduled_ts: int | None = None) -> str:
        """Upload video lớn bằng Facebook Resumable Upload API."""
        upload_url = f"https://graph-video.facebook.com/{FB_API_VERSION}/{self.page_id}/videos"

        # Bước 1: Khởi tạo upload session
        resp = httpx.post(upload_url, data={
            "upload_phase": "start",
            "file_size":    str(file_size),
            "access_token": self.access_token,
        }, timeout=30)
        if resp.status_code != 200:
            logger.error(f"Video upload start lỗi {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
        init_data         = resp.json()
        upload_session_id = init_data["upload_session_id"]
        start_offset      = int(init_data["start_offset"])
        end_offset        = int(init_data["end_offset"])

        # Bước 2: Upload từng chunk
        logger.info(f"Uploading video ({file_size/1024/1024:.1f}MB) theo chunks...")
        with open(file_path, "rb") as f:
            while start_offset < file_size:
                f.seek(start_offset)
                chunk = f.read(end_offset - start_offset)

                resp = httpx.post(upload_url, data={
                    "upload_phase":      "transfer",
                    "upload_session_id": upload_session_id,
                    "start_offset":      str(start_offset),
                    "access_token":      self.access_token,
                }, files={"video_file_chunk": ("chunk", chunk, "application/octet-stream")},
                timeout=120)
                resp.raise_for_status()
                offsets      = resp.json()
                start_offset = int(offsets["start_offset"])
                end_offset   = int(offsets["end_offset"])

        # Bước 3: Publish / Schedule
        finish_data = {
            "upload_phase":      "finish",
            "upload_session_id": upload_session_id,
            "description":       content,
            "access_token":      self.access_token,
        }
        if scheduled_ts:
            finish_data["published"]              = "false"
            finish_data["scheduled_publish_time"] = str(scheduled_ts)

        resp = httpx.post(upload_url, data=finish_data, timeout=60)
        resp.raise_for_status()
        return resp.json().get("video_id") or upload_session_id


# ── Helpers ────────────────────────────────────────────────

def _to_unix_ts(dt: datetime) -> int:
    """Chuyển datetime → Unix timestamp (int). Đảm bảo UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _download_bytes(url: str, max_size: int) -> bytes:
    """Download nội dung URL vào RAM (bytes)."""
    with httpx.stream("GET", url, timeout=60,
                      follow_redirects=True) as resp:
        resp.raise_for_status()
        chunks = []
        total  = 0
        for chunk in resp.iter_bytes(chunk_size=64 * 1024):
            total += len(chunk)
            if total > max_size:
                raise ValueError(f"File quá lớn (>{max_size/1024/1024:.0f}MB)")
            chunks.append(chunk)
        return b"".join(chunks)


def _detect_mime(data: bytes) -> str:
    """Detect MIME type từ magic bytes."""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"  # default


def _stream_download_to_file(url: str, dest_path: str, max_size: int):
    """Stream download URL vào file (cho video lớn)."""
    with httpx.stream("GET", url, timeout=60,
                      follow_redirects=True) as resp:
        resp.raise_for_status()
        total = 0
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1024 * 1024):  # 1MB chunks
                total += len(chunk)
                if total > max_size:
                    raise ValueError(f"Video quá lớn (>{max_size/1024/1024/1024:.0f}GB)")
                f.write(chunk)
    logger.info(f"Đã tải {total/1024/1024:.1f}MB")
