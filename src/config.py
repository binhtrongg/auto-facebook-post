"""
Cấu hình toàn bộ hệ thống.
Đọc từ biến môi trường (.env khi chạy local, GitHub Secrets khi chạy trên Actions).

DB_BACKEND = "sheets"    → dùng Google Sheets (mặc định)
DB_BACKEND = "supabase"  → dùng Supabase
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Backend database ───────────────────────────────────────
DB_BACKEND = os.getenv("DB_BACKEND", "sheets").lower()   # "sheets" hoặc "supabase"

# ── Supabase (chỉ cần nếu DB_BACKEND=supabase) ────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# ── Google Sheets (chỉ cần nếu DB_BACKEND=sheets) ─────────
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "")  # path tới file JSON
GOOGLE_SHEET_ID         = os.getenv("GOOGLE_SHEET_ID", "")           # ID của Spreadsheet

# ── Apify ─────────────────────────────────────────────────
# facebook-posts-scraper trả về mỗi item là 1 post riêng (flat format)
APIFY_ACTOR_ID = "apify~facebook-posts-scraper"

# Số bài tối đa lấy mỗi lần scrape / mỗi trang nguồn
MAX_POSTS_PER_PAGE = 20

# Giới hạn an toàn trước khi đổi key (tránh vượt free tier 500/tháng)
APIFY_KEY_SAFE_LIMIT = 450

# ── Lịch scrape / đăng ────────────────────────────────────
SCRAPE_INTERVAL_HOURS     = 8   # Scrape 3 lần / ngày
POST_INTERVAL_MIN_MINUTES = 30  # Khoảng cách tối thiểu giữa 2 bài đăng
POST_INTERVAL_MAX_MINUTES = 60  # Khoảng cách tối đa

# ── Facebook Graph API ────────────────────────────────────
FB_API_VERSION = "v21.0"
FB_API_BASE    = f"https://graph.facebook.com/{FB_API_VERSION}"

# ── Logging ───────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
