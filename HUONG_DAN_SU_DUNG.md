# Hướng dẫn sử dụng — Auto Facebook Post

## Mục lục
1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Cách thức hoạt động](#2-cách-thức-hoạt-động)
3. [Cấu trúc Google Sheet](#3-cấu-trúc-google-sheet)
4. [Thiết lập lần đầu](#4-thiết-lập-lần-đầu)
5. [Thêm trang nguồn mới](#5-thêm-trang-nguồn-mới)
6. [Thêm trang đích mới](#6-thêm-trang-đích-mới)
7. [Chạy thủ công](#7-chạy-thủ-công)
8. [Xem log và kết quả](#8-xem-log-và-kết-quả)
9. [Xử lý sự cố thường gặp](#9-xử-lý-sự-cố-thường-gặp)
10. [GitHub Secrets cần thiết](#10-github-secrets-cần-thiết)

---

## 1. Tổng quan hệ thống

Tool tự động:
1. **Scrape** bài viết từ các Facebook Page nguồn qua Apify
2. **Lọc** bài mới trong 24 giờ qua, ưu tiên bài có tương tác cao
3. **Hẹn giờ** đăng bài lên các Facebook Page đích theo lịch cài đặt
4. **Tự động chạy** 3 lần/ngày lúc 5:00 — 13:00 — 21:00 giờ Việt Nam

```
[Facebook Pages nguồn]
        ↓ (Apify scrape)
[Lọc bài mới + xếp hạng tương tác]
        ↓
[Hẹn giờ lên Facebook Pages đích]
        ↓
[Lưu log + dedup vào Google Sheet]
```

---

## 2. Cách thức hoạt động

### 2.1 Lịch chạy tự động

GitHub Actions chạy theo cron 3 lần/ngày:

| Giờ Việt Nam | Giờ UTC |
|---|---|
| 05:00 | 22:00 (hôm trước) |
| 13:00 | 06:00 |
| 21:00 | 14:00 |

### 2.2 Quy trình mỗi lần chạy

**Bước 1 — Lấy danh sách trang:**
- Đọc tất cả source pages đang active từ Google Sheet
- Gộp theo `group_id`

**Bước 2 — Scrape qua Apify:**
- Gọi Apify `facebook-posts-scraper` với danh sách URL trang nguồn
- Lọc chỉ lấy bài trong **24 giờ** qua
- Tính điểm tương tác: `likes + comments×2 + shares×3`

**Bước 3 — Lọc bài đã đăng:**
- Kiểm tra từng bài với bảng `dedup` trong Sheet
- Bỏ qua bài đã từng được xử lý

**Bước 4 — Sắp xếp & giới hạn:**
- Sắp xếp bài theo điểm tương tác (cao nhất lên đầu)
- Giới hạn số bài theo `max_posts_per_run` của từng trang đích

**Bước 5 — Hẹn giờ lên Facebook:**
- Với mỗi trang đích: tính slot giờ đăng (nối tiếp sau bài cuối)
- Upload ảnh/video lên Facebook
- Đặt lịch `scheduled_publish_time` qua Graph API
- Facebook tự đăng đúng giờ (không cần tool chạy lại)

**Bước 6 — Lưu kết quả:**
- Lưu `dedup` để không đăng lại bài cũ
- Lưu `log` với link bài gốc, trang nguồn, kết quả

### 2.3 Xử lý loại nội dung

| Loại bài | Cách xử lý |
|---|---|
| Chỉ text | Đăng text trực tiếp |
| 1 ảnh | Upload ảnh → đăng kèm caption |
| Nhiều ảnh | Upload từng ảnh unpublished → tạo album |
| Video MP4 | Download → upload lên Facebook |
| Facebook Reel | Download qua yt-dlp → upload như video native |

### 2.4 Quản lý Apify Key

- Mỗi key có giới hạn 500 lần dùng/tháng (free tier)
- Hệ thống tự chọn key còn quota, ưu tiên key ít dùng nhất
- Có thể thêm nhiều key vào Sheet để tăng quota

---

## 3. Cấu trúc Google Sheet

Sheet có **6 tab chính**:

### Tab `source_pages` — Trang nguồn
| Cột | Ý nghĩa |
|---|---|
| `fb_page_url` | URL trang Facebook nguồn (vd: `https://web.facebook.com/mps.gov`) |
| `group_id` | Tên nhóm — dùng để liên kết với trang đích |
| `is_active` | `TRUE`/`FALSE` — bật/tắt trang này |
| `scraped_at` | Tự động cập nhật sau mỗi lần scrape |

### Tab `destination_pages` — Trang đích
| Cột | Ý nghĩa |
|---|---|
| `fb_page_id` | ID số của trang Facebook đích |
| `fb_page_name` | Tên trang (để nhận biết) |
| `fb_access_token` | Page Access Token vĩnh viễn |
| `group_id` | Tên nhóm — phải trùng với source_pages |
| `max_posts_per_run` | Số bài tối đa mỗi lần chạy (vd: `4`) |
| `post_interval_hours` | Khoảng cách giữa 2 bài liên tiếp (giờ, vd: `2`) |
| `last_scheduled_at` | Tự động cập nhật — slot cuối đã lên lịch |

### Tab `dedup` — Chống đăng lại
- Lưu `fb_post_id` của mỗi bài đã xử lý
- Hệ thống tự ghi, không cần chỉnh tay
- Xóa hết dedup: chạy workflow thủ công với option `clear_dedup=true`

### Tab `logs` — Lịch sử
- Ghi lại từng lần đăng: bài gốc, trang nguồn, trang đích, kết quả
- Xem để theo dõi hoạt động hệ thống

### Tab `apify_keys` — Quản lý API key
| Cột | Ý nghĩa |
|---|---|
| `api_key` | Apify API key |
| `usage_count` | Số lần đã dùng tháng này |
| `is_active` | Bật/tắt key này |

### Tab `page_groups` — Nhóm trang
- Quản lý tên nhóm liên kết source ↔ destination
- `group_id` trong source_pages và destination_pages phải trùng nhau

---

## 4. Thiết lập lần đầu

### 4.1 Google Apps Script
1. Mở Google Sheet → **Extensions → Apps Script**
2. Paste nội dung file `google_apps_script/Code.gs` vào editor
3. Click **Deploy → New deployment → Web App**
   - Execute as: **Me**
   - Who has access: **Anyone**
4. Copy URL deployment

### 4.2 GitHub Secrets
Vào repo GitHub → **Settings → Secrets and variables → Actions**

Thêm các secrets sau:

| Secret | Giá trị |
|---|---|
| `GOOGLE_WEBAPP_URL` | URL Web App từ bước 4.1 |
| `WEBAPP_SECRET` | Chuỗi bí mật tự đặt (trùng với Script Properties) |
| `FACEBOOK_COOKIES` | Cookie Facebook (Netscape format) để yt-dlp tải Reels |

### 4.3 Script Properties (Apps Script)
Trong Apps Script editor → **Project Settings → Script Properties**:
- `WEBAPP_SECRET`: giá trị trùng với GitHub Secret `WEBAPP_SECRET`

---

## 5. Thêm trang nguồn mới

1. Mở Google Sheet → tab **`source_pages`**
2. Thêm hàng mới:
   - `fb_page_url`: URL trang Facebook (dùng `web.facebook.com`, không dùng `m.facebook.com`)
   - `group_id`: tên nhóm (phải trùng với trang đích muốn đăng lên)
   - `is_active`: `TRUE`
3. Lưu — tự động có hiệu lực lần chạy tiếp theo

---

## 6. Thêm trang đích mới

**Xem file `HUONG_DAN_FACEBOOK_TOKEN.md`** để lấy Page ID và Access Token.

Sau khi có token:
1. Mở Google Sheet → tab **`destination_pages`**
2. Thêm hàng mới với đầy đủ thông tin
3. Đảm bảo `group_id` trùng với source pages tương ứng
4. Kiểm tra token tại `developers.facebook.com/tools/debug/accesstoken` — **phải là `Type=Page, Expires=Never`**

---

## 7. Chạy thủ công

1. Vào repo GitHub → tab **Actions**
2. Chọn **"Scrape & Schedule Facebook Posts"**
3. Click **"Run workflow"**
4. Tùy chọn:
   - **`clear_dedup=false`** (mặc định): chạy bình thường, bỏ qua bài đã xử lý
   - **`clear_dedup=true`**: xóa toàn bộ lịch sử dedup trước khi chạy → đăng lại tất cả bài cũ

---

## 8. Xem log và kết quả

### Xem trên Google Sheet
- Tab **`logs`**: xem từng bài đã đăng, link bài gốc, kết quả
- Tab **`dedup`**: xem danh sách bài đã xử lý

### Xem trên GitHub Actions
1. Vào repo → tab **Actions**
2. Click vào lần chạy muốn xem
3. Click vào job **"scrape"** → xem từng bước

**Các dòng log quan trọng:**
```
Tìm thấy X trang nguồn trong Y nhóm
→ Z bài mới (đã sắp xếp theo tương tác)
  Bài 1: id=... | imgs=X | video=có/không | ❤️likes 💬comments 🔁shares
Page A: lên lịch X/Y bài (max=4, interval=2h)
KẾT THÚC: +X bài mới | Y lỗi
```

### Xem trên Facebook
- Vào trang đích → **Publishing Tools → Scheduled Posts**
- Thấy danh sách bài đã được hẹn giờ

---

## 9. Xử lý sự cố thường gặp

### Lỗi 400 Bad Request khi đăng ảnh/video
**Nguyên nhân**: Access token hết hạn hoặc sai
**Cách sửa**: Lấy lại token — xem `HUONG_DAN_FACEBOOK_TOKEN.md`

### Không scrape được bài nào
**Nguyên nhân 1**: Trang nguồn không có bài mới trong 24 giờ
**Nguyên nhân 2**: Apify key hết quota (kiểm tra tab `apify_keys` trong Sheet)
**Cách sửa**: Thêm Apify key mới vào Sheet hoặc đợi reset tháng sau

### Workflow không tự chạy theo lịch
**Nguyên nhân**: GitHub cron bị delay hoặc workflow bị disable
**Cách sửa**:
1. Vào Actions → tìm workflow → kiểm tra có nút "Enable workflow" không
2. Nếu không có nút đó (đang enabled): push 1 commit nhỏ lên main để re-register cron

### Reel/video không tải được
**Nguyên nhân**: Facebook cookie hết hạn
**Cách sửa**:
1. Export cookie mới từ trình duyệt (extension "Get cookies.txt LOCALLY")
2. Cập nhật GitHub Secret `FACEBOOK_COOKIES` với cookie mới

### Bài bị đăng lại (đã đăng rồi vẫn đăng tiếp)
**Nguyên nhân**: Dedup bị xóa hoặc `fb_post_id` thay đổi
**Cách sửa**: Kiểm tra tab `dedup` trong Sheet

---

## 10. GitHub Secrets cần thiết

| Secret | Bắt buộc | Mô tả |
|---|---|---|
| `GOOGLE_WEBAPP_URL` | ✅ | URL Google Apps Script Web App |
| `WEBAPP_SECRET` | ✅ | Token bảo mật cho Web App |
| `FACEBOOK_COOKIES` | ✅ | Cookie Facebook để tải Reels qua yt-dlp |

---

## Sơ đồ tóm tắt

```
GitHub Actions (5h / 13h / 21h VN)
│
├── Apify scrape source pages
│   └── Lọc 24h, tính engagement score
│
├── Kiểm tra dedup (Google Sheet)
│   └── Bỏ qua bài đã xử lý
│
├── Sắp xếp theo tương tác
│   └── Top N bài cho mỗi trang đích
│
├── Upload lên Facebook (Graph API)
│   ├── Ảnh → /photos + /feed
│   ├── Video → resumable upload + /videos
│   └── Reel → yt-dlp download → /videos
│
└── Lưu dedup + log (Google Sheet)
```
