-- ============================================================
-- AUTO FACEBOOK POST - Supabase Schema
-- Chạy toàn bộ file này trong Supabase SQL Editor
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. APIFY API KEYS (nhiều account để xoay vòng miễn phí)
-- ============================================================
CREATE TABLE apify_keys (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    api_key         TEXT NOT NULL UNIQUE,
    email           TEXT,                          -- email tạo account Apify
    usage_count     INTEGER DEFAULT 0,             -- số lần đã dùng tháng này
    monthly_limit   INTEGER DEFAULT 450,           -- giới hạn an toàn (500 - buffer)
    is_active       BOOLEAN DEFAULT true,
    last_used_at    TIMESTAMP WITH TIME ZONE,
    reset_at        DATE DEFAULT (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month')::DATE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 2. NHÓM TRANG (gộp nguồn → đích)
-- ============================================================
CREATE TABLE page_groups (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,                     -- VD: "Nhóm nấu ăn", "Nhóm du lịch"
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 3. TRANG NGUỒN (scrape từ đây)
-- ============================================================
CREATE TABLE source_pages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    group_id        UUID REFERENCES page_groups(id) ON DELETE CASCADE,
    fb_page_url     TEXT NOT NULL,                 -- VD: https://www.facebook.com/pagename
    fb_page_name    TEXT,                          -- Tên hiển thị
    is_active       BOOLEAN DEFAULT true,
    last_scraped_at TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 4. TRANG ĐÍCH (đăng bài lên đây)
-- ============================================================
CREATE TABLE destination_pages (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    group_id            UUID REFERENCES page_groups(id) ON DELETE CASCADE,
    fb_page_id          TEXT NOT NULL,                -- Page ID số (VD: 123456789)
    fb_page_name        TEXT,                         -- Tên trang
    fb_access_token     TEXT NOT NULL,                -- Page Access Token
    is_active           BOOLEAN DEFAULT true,
    last_scheduled_at   TIMESTAMP WITH TIME ZONE,     -- Slot cuối đã hẹn trên Facebook
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Nếu đã tạo bảng rồi, chạy migration này:
-- ALTER TABLE destination_pages ADD COLUMN IF NOT EXISTS last_scheduled_at TIMESTAMP WITH TIME ZONE;

-- ============================================================
-- 5. BÀI VIẾT ĐÃ SCRAPE
-- Chú ý: content/images/video sẽ bị XÓA sau khi đăng xong
-- Chỉ giữ lại fb_post_id để dedup
-- ============================================================
CREATE TABLE posts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fb_post_id          TEXT UNIQUE NOT NULL,      -- ID bài gốc trên Facebook (dedup key)
    source_page_id      UUID REFERENCES source_pages(id),
    content             TEXT,                      -- Nội dung bài → XÓA sau đăng
    image_urls          JSONB DEFAULT '[]'::JSONB, -- ["url1","url2"] → XÓA sau đăng
    video_url           TEXT,                      -- URL video → XÓA sau đăng
    original_post_time  TIMESTAMP WITH TIME ZONE,  -- Thời gian đăng gốc
    scraped_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status              TEXT DEFAULT 'pending'
                        CHECK (status IN ('pending','scheduled','posted','failed'))
);

-- ============================================================
-- 6. LỊCH ĐĂNG BÀI (queue)
-- Toàn bộ record sẽ bị XÓA sau khi đăng xong
-- ============================================================
CREATE TABLE scheduled_posts (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    post_id              UUID REFERENCES posts(id) ON DELETE CASCADE,
    destination_page_id  UUID REFERENCES destination_pages(id),
    scheduled_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    status               TEXT DEFAULT 'pending'
                         CHECK (status IN ('pending','posted','failed')),
    retry_count          INTEGER DEFAULT 0,
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 7. DEDUP TABLE (NHỎ GỌN - giữ mãi để tránh đăng trùng)
-- Sau khi đăng xong: xóa content trong posts, xóa scheduled_posts
-- Nhưng GIỮ bảng này để không bao giờ đăng lại bài cũ
-- ============================================================
CREATE TABLE posted_dedup (
    fb_post_id           TEXT PRIMARY KEY,         -- ~50 bytes/record
    source_page_id       UUID,
    destination_page_id  UUID,
    posted_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 8. LOGS (giữ 30 ngày rồi xóa)
-- ============================================================
CREATE TABLE post_logs (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scheduled_post_id    UUID,
    fb_post_id           TEXT,
    destination_page_id  UUID,
    result               TEXT,                     -- 'scheduled' | 'success' | 'failed'
    error_message        TEXT,
    source_page_url      TEXT,
    post_url             TEXT,
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_posts_status         ON posts(status);
CREATE INDEX idx_posts_fb_post_id     ON posts(fb_post_id);
CREATE INDEX idx_sched_scheduled_at   ON scheduled_posts(scheduled_at);
CREATE INDEX idx_sched_status         ON scheduled_posts(status);
CREATE INDEX idx_source_group         ON source_pages(group_id);
CREATE INDEX idx_dest_group           ON destination_pages(group_id);
CREATE INDEX idx_logs_created_at      ON post_logs(created_at);

-- ============================================================
-- TỰ ĐỘNG XÓA LOGS CŨ HƠN 30 NGÀY (chạy hàng ngày)
-- ============================================================
-- Kích hoạt trong Supabase → Database → Extensions → pg_cron (nếu cần)
-- SELECT cron.schedule('cleanup-logs', '0 2 * * *',
--   $$DELETE FROM post_logs WHERE created_at < NOW() - INTERVAL '30 days'$$
-- );
