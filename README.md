# Auto Facebook Post — Tự Động Đăng Bài Facebook

> **Auto Facebook Post** — Free, open-source tool to automatically scrape posts from Facebook Pages and schedule them to your own pages via GitHub Actions + Google Sheets. No server required.

[![GitHub Actions](https://img.shields.io/badge/Powered%20by-GitHub%20Actions-blue?logo=github)](https://github.com/features/actions)
[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## Table of Contents / Mục Lục

- [English Guide](#english-guide)
  - [Features](#features)
  - [Architecture](#architecture)
  - [Quick Start](#quick-start)
  - [Step 1 — Get Apify API Key](#step-1--get-apify-api-key)
  - [Step 2 — Set Up Google Sheets Database](#step-2--set-up-google-sheets-database)
  - [Step 3 — Get Facebook Page Access Token](#step-3--get-facebook-page-access-token)
  - [Step 4 — Get Facebook Cookies (for Reels/Videos)](#step-4--get-facebook-cookies-for-reelsvideos)
  - [Step 5 — Configure GitHub Secrets](#step-5--configure-github-secrets)
  - [Step 6 — Add Source & Destination Pages](#step-6--add-source--destination-pages)
  - [FAQ](#faq)
- [Hướng Dẫn Tiếng Việt](#hướng-dẫn-tiếng-việt)

---

## English Guide

### Features

- **Auto scrape** Facebook Pages using [Apify](https://apify.com) (no browser automation needed)
- **Smart scheduling** — posts are spread throughout the day at custom intervals, skipping quiet hours (11 PM–5 AM Vietnam time)
- **Supports all content types**: text, single image, photo album, video, Facebook Reels
- **Deduplication** — never re-posts the same content
- **Engagement ranking** — top-liked posts are scheduled first
- **Free infrastructure** — runs 100% on GitHub Actions + Google Sheets (no VPS, no paid hosting)
- **Multi-key rotation** — manage multiple Apify accounts to maximize free scraping quota
- **Runs 3× per day** automatically: 5:00 AM / 12:00 PM / 7:00 PM Vietnam time

### Architecture

```
[Source Facebook Pages]
        │
        ▼ Apify scraper (facebook-posts-scraper)
[Filter new posts — last 10h, ranked by engagement]
        │
        ▼ Dedup check (Google Sheets)
[Schedule posts via Facebook Graph API]
        │
        ▼
[Facebook publishes at scheduled time ✓]
        │
[Save dedup + logs to Google Sheets]
```

**Stack:**
| Component | Technology | Cost |
|-----------|------------|------|
| Automation runner | GitHub Actions | Free |
| Database | Google Sheets + Apps Script | Free |
| Facebook scraping | Apify (free tier) | Free* |
| Facebook posting | Facebook Graph API | Free |
| Video download | yt-dlp | Free |

> *Apify free tier gives $5 credit/month ≈ 450–500 scrapes. Add multiple accounts to increase quota.

---

### Quick Start

**Prerequisites:**
- GitHub account
- Google account
- Facebook account (admin of at least one Page)
- Apify account (free)
- Facebook Developer App (free)

---

### Step 1 — Get Apify API Key

Apify is used to scrape Facebook Pages without needing a browser or Facebook login.

1. Go to [apify.com](https://apify.com) → **Sign Up** with a Gmail account
2. After registration, go to **Console → Settings → Integrations**
3. Copy your **Personal API Token** (starts with `apify_api_...`)
4. Save it — you'll add it to Google Sheets later

> **Tip:** Each Apify account gets $5 free credit ≈ 450–500 scrapes/month. Create multiple Gmail accounts to get more quota and add all keys to the Sheet.

---

### Step 2 — Set Up Google Sheets Database

The tool uses Google Sheets as a free database via Google Apps Script.

#### 2.1 Create the Google Sheet & Run Setup

1. Go to [sheets.google.com](https://sheets.google.com) → create a new **blank** spreadsheet
2. Open **Extensions → Apps Script**
3. Paste the full content of [`google_apps_script/Code.gs`](google_apps_script/Code.gs) into the editor
4. Click **Save** (💾), then click **Run → `setupSpreadsheet`**
5. Grant permissions when prompted

The `setupSpreadsheet()` function will **automatically create all 7 tabs** with correct headers and sample data rows:

| Tab | Purpose |
|-----|---------|
| `groups` | Page groups (links source ↔ destination) |
| `source_pages` | Facebook pages to scrape from |
| `destination_pages` | Facebook pages to post to |
| `apify_keys` | Apify API key rotation |
| `dedup` | Deduplication log (auto-managed) |
| `logs` | Post history log (auto-managed) |
| `schedule` | Scheduled post slots (auto-managed) |

A popup will confirm: **"✅ Setup hoàn tất! 7 tabs đã được tạo."**

> **Note:** If you already have a Sheet with existing tabs, `setupSpreadsheet()` will skip tabs that already exist — safe to run again.

#### 2.2 Deploy Google Apps Script Web App

1. In the same Apps Script editor: **Deploy → New deployment → Web App**:
   - Execute as: **Me**
   - Who has access: **Anyone**
2. Click **Deploy** → copy the **Web App URL** (format: `https://script.google.com/macros/s/XXXX/exec`)
3. Go to **Project Settings → Script Properties** → add:
   - Key: `WEBAPP_SECRET` — Value: any secret string you choose (e.g., `my_secret_abc123`)

---

### Step 3 — Get Facebook Page Access Token

You need a **permanent Page Access Token** for each destination page.

#### 3.1 Create a Facebook Developer App

1. Go to [developers.facebook.com](https://developers.facebook.com) → **My Apps → Create App**
2. Choose **"Other"** → **"Business"**
3. Note your **App ID** and **App Secret** (Settings → Basic)

#### 3.2 Get Short-lived User Token

1. Go to [Graph API Explorer](https://developers.facebook.com/tools/explorer)
2. Select your **Meta App** (top right)
3. Click **"Generate Access Token"**
4. Grant these permissions:
   - ✅ `pages_manage_posts`
   - ✅ `pages_read_engagement`
   - ✅ `pages_show_list`
5. Copy the generated token

#### 3.3 Exchange for Long-lived User Token (~60 days)

Open your browser and visit:
```
https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=SHORT_USER_TOKEN
```

Copy the `access_token` from the JSON response.

#### 3.4 Get Permanent Page Token

```
https://graph.facebook.com/v21.0/me/accounts?access_token=LONG_LIVED_USER_TOKEN
```

Response:
```json
{
  "data": [
    {
      "access_token": "EAAxxxPERMANENT_PAGE_TOKENxxx",
      "name": "Your Page Name",
      "id": "123456789012345"
    }
  ]
}
```

For each destination page, save:
- `id` → **Page ID**
- `access_token` → **Permanent Page Access Token**

#### 3.5 Verify Token

1. Go to [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken)
2. Paste your Page Token → click **Debug**
3. Check:
   - **Type**: must be `Page`
   - **Expires**: must be `Never`
   - **Scopes**: must include `pages_manage_posts`

> See [`HUONG_DAN_FACEBOOK_TOKEN.md`](HUONG_DAN_FACEBOOK_TOKEN.md) for the full Vietnamese guide.

---

### Step 4 — Get Facebook Cookies (for Reels/Videos)

Facebook Reels and videos require a valid Facebook cookie for yt-dlp to download them. Without cookies, only text and image posts will work.

**Any Facebook account's cookies will work** — it does not need to be an admin of your pages.

#### How to export Facebook cookies (Netscape format):

1. Install browser extension: **"Get cookies.txt LOCALLY"**
   - [Chrome](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - [Firefox](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)
2. Log in to Facebook in your browser
3. Go to `facebook.com`
4. Click the extension icon → **Export** → select **"facebook.com"**
5. Save the downloaded `.txt` file — this is your cookie file in Netscape format

The cookie file looks like:
```
# Netscape HTTP Cookie File
.facebook.com	TRUE	/	TRUE	1999999999	c_user	123456789
.facebook.com	TRUE	/	TRUE	1999999999	xs	AbCdEfXXXXXX
...
```

> **Note:** Facebook cookies expire when you log out, change your password, or Facebook invalidates the session. Refresh them every few months or when you see yt-dlp errors in the logs.

---

### Step 5 — Configure GitHub Secrets

1. Fork or clone this repository
2. Go to your repo → **Settings → Secrets and variables → Actions**
3. Add these secrets:

| Secret Name | Required | Description |
|-------------|----------|-------------|
| `GOOGLE_WEBAPP_URL` | ✅ | Web App URL from Step 2.2 |
| `WEBAPP_SECRET` | ✅ | Secret token from Script Properties (Step 2.2) |
| `FACEBOOK_COOKIES` | ✅ for Reels | Full content of the cookies.txt file (Step 4) |

To add `FACEBOOK_COOKIES`: open the `.txt` cookie file → select all → copy → paste as the secret value.

---

### Step 6 — Add Source & Destination Pages

#### Add a page group

In your Google Sheet → `page_groups` tab, add a row:
```
id: (auto-generate a UUID or use any unique string)
name: Group A
is_active: TRUE
created_at: (current timestamp)
```

The `group_id` links source pages to destination pages. One group = scrape from source pages → post to destination pages in the same group.

#### Add source pages (pages to scrape FROM)

In `source_pages` tab:
```
id: (UUID)
fb_page_url: https://www.facebook.com/source-page-name
fb_page_name: Source Page A
group_id: (same group_id as your group)
is_active: TRUE
```

> Use `www.facebook.com` URLs, not `m.facebook.com`

#### Add destination pages (pages to POST TO)

In `destination_pages` tab:
```
id: (UUID)
fb_page_id: 123456789012345        ← Page ID from Step 3.4
fb_page_name: My Page A
fb_access_token: EAABxxx...        ← Permanent token from Step 3.4
group_id: (same group as source)
is_active: TRUE
max_posts_per_run: 4               ← Max posts per 8-hour run
post_interval_hours: 2             ← Hours between posts
```

#### Add Apify keys

In `apify_keys` tab:
```
id: (UUID)
api_key: apify_api_xxxxxxxx        ← From Step 1
email: youremail@gmail.com
usage_count: 0
monthly_limit: 450
is_active: TRUE
reset_at: (first day of next month)
```

---

### Running the Workflow

The workflow runs automatically 3× per day. To run manually:

1. Go to your repo → **Actions** tab
2. Select **"Scrape & Schedule Facebook Posts"**
3. Click **"Run workflow"**
4. Options:
   - `clear_dedup=false` (default): normal run, skips already-processed posts
   - `clear_dedup=true`: clears dedup history → re-posts all recent content

Check results in:
- GitHub Actions logs (real-time output)
- Google Sheet `logs` tab
- Facebook Page → **Publishing Tools → Scheduled Posts**

---

### FAQ

**Q: Why isn't the workflow running automatically?**
A: GitHub disables cron workflows on inactive repos. Push a small commit to re-enable, or trigger it manually once.

**Q: Reels/videos aren't being downloaded.**
A: Your Facebook cookies have expired. Export fresh cookies (Step 4) and update the `FACEBOOK_COOKIES` secret.

**Q: Posts are being re-published.**
A: The dedup table was cleared. Check the `dedup` tab in your Sheet.

**Q: Apify returns no posts.**
A: Check the `apify_keys` tab — `usage_count` may have hit `monthly_limit`. Add a new Apify account.

**Q: 400 Bad Request error when posting.**
A: Your Page Access Token has expired or was revoked. Follow Step 3 to get a new one and update the Sheet.

---

## Hướng Dẫn Tiếng Việt

### Giới Thiệu

**Auto Facebook Post** là công cụ mã nguồn mở, miễn phí, giúp bạn tự động:
1. **Scrape** bài viết từ các Facebook Page nguồn qua Apify
2. **Lọc** bài mới, xếp hạng theo tương tác (likes, comments, shares)
3. **Hẹn giờ** đăng lên các Facebook Page đích của bạn theo lịch tùy chỉnh
4. **Chạy tự động** 3 lần/ngày: 5:00 — 12:00 — 19:00 giờ Việt Nam

Không cần server, không cần VPS — chạy hoàn toàn miễn phí trên GitHub Actions + Google Sheets.

---

### Bước 1 — Lấy Apify API Key

Apify dùng để scrape Facebook Page mà không cần đăng nhập Facebook.

1. Vào [apify.com](https://apify.com) → **Sign Up** bằng Gmail
2. Sau khi đăng ký: vào **Console → Settings → Integrations**
3. Copy **Personal API Token** (bắt đầu bằng `apify_api_...`)

> **Mẹo:** Mỗi tài khoản Apify có $5 credit/tháng ≈ 450–500 lần scrape. Tạo nhiều tài khoản Gmail để tăng quota, điền tất cả vào Google Sheet.

---

### Bước 2 — Thiết Lập Google Sheet

#### 2.1 Tạo Google Sheet & Chạy Setup Tự Động

1. Vào [sheets.google.com](https://sheets.google.com) → tạo spreadsheet **trống** mới
2. Vào **Extensions → Apps Script**
3. Paste toàn bộ nội dung file [`google_apps_script/Code.gs`](google_apps_script/Code.gs) vào editor
4. Click **Save** (💾), sau đó click **Run → `setupSpreadsheet`**
5. Cho phép quyền khi được hỏi

Hàm `setupSpreadsheet()` sẽ **tự động tạo đủ 7 tabs** với header và dữ liệu mẫu. Sau khi chạy xong sẽ hiện thông báo: **"✅ Setup hoàn tất! 7 tabs đã được tạo."**

#### 2.2 Deploy Google Apps Script

1. Trong Sheet: **Extensions → Apps Script**
2. Paste code từ file [`google_apps_script/Code.gs`](google_apps_script/Code.gs)
3. **Deploy → New deployment → Web App**:
   - Execute as: **Me**
   - Who has access: **Anyone**
4. Copy URL deployment
5. **Project Settings → Script Properties** → thêm:
   - Key: `WEBAPP_SECRET` — Value: chuỗi bí mật tự đặt

---

### Bước 3 — Lấy Facebook Page Access Token

Xem hướng dẫn chi tiết: [`HUONG_DAN_FACEBOOK_TOKEN.md`](HUONG_DAN_FACEBOOK_TOKEN.md)

**Tóm tắt:**
1. Tạo Facebook Developer App tại [developers.facebook.com](https://developers.facebook.com)
2. Lấy **Short-lived User Token** từ Graph API Explorer
3. Đổi sang **Long-lived User Token** (~60 ngày)
4. Lấy **Page Access Token vĩnh viễn** từ `/me/accounts`
5. Kiểm tra: Type=Page, Expires=Never

---

### Bước 4 — Lấy Cookie Facebook (để đăng Reels/Video)

Nếu bạn muốn đăng Reels và video tự động, cần cung cấp cookie Facebook cho yt-dlp tải video về.

**Dùng cookie Facebook bất kỳ** — không cần là admin của trang đích, chỉ cần đăng nhập Facebook là đủ.

#### Cách lấy cookie (định dạng Netscape):

1. Cài extension trình duyệt: **"Get cookies.txt LOCALLY"**
   - [Chrome](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - [Firefox](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)
2. Đăng nhập Facebook trong trình duyệt
3. Vào `facebook.com`
4. Click icon extension → **Export** → chọn **"facebook.com"**
5. Lưu file `.txt` — đây là cookie file

File cookie có dạng:
```
# Netscape HTTP Cookie File
.facebook.com	TRUE	/	TRUE	1999999999	c_user	123456789
.facebook.com	TRUE	/	TRUE	1999999999	xs	AbCdEfXXXXXX
...
```

> **Lưu ý:** Cookie hết hạn khi bạn đăng xuất hoặc đổi mật khẩu. Thay cookie mới mỗi vài tháng nếu thấy lỗi tải video trong log.

---

### Bước 5 — Cấu Hình GitHub Secrets

1. Fork repo này về tài khoản GitHub của bạn
2. Vào repo → **Settings → Secrets and variables → Actions**
3. Thêm các secrets:

| Secret | Bắt buộc | Mô tả |
|--------|----------|-------|
| `GOOGLE_WEBAPP_URL` | ✅ | URL Web App từ Bước 2.2 |
| `WEBAPP_SECRET` | ✅ | Token bí mật từ Script Properties |
| `FACEBOOK_COOKIES` | ✅ để đăng video/Reels | Toàn bộ nội dung file cookie.txt |

Để thêm `FACEBOOK_COOKIES`: mở file `.txt` → chọn tất cả → copy → paste vào ô giá trị secret.

---

### Bước 6 — Thêm Trang Nguồn và Trang Đích

#### Tạo nhóm trang (page group)

Trong Google Sheet → tab `page_groups`, thêm hàng:
- `name`: tên nhóm tùy ý (VD: `Group A`)
- `is_active`: `TRUE`

Nhóm dùng để liên kết trang nguồn ↔ trang đích: scrape từ trang nguồn trong nhóm → đăng lên trang đích trong nhóm.

#### Thêm trang nguồn (scrape từ đây)

Tab `source_pages`:
- `fb_page_url`: URL trang Facebook nguồn (dùng `www.facebook.com`)
- `fb_page_name`: tên ghi chú
- `group_id`: tên nhóm (phải trùng với trang đích)
- `is_active`: `TRUE`

#### Thêm trang đích (đăng bài lên đây)

Tab `destination_pages`:
- `fb_page_id`: Page ID từ Bước 3
- `fb_page_name`: tên ghi chú
- `fb_access_token`: Page Token vĩnh viễn từ Bước 3
- `group_id`: tên nhóm (trùng với trang nguồn)
- `max_posts_per_run`: số bài tối đa mỗi lần chạy (VD: `4`)
- `post_interval_hours`: khoảng cách giữa 2 bài (VD: `2`)

#### Thêm Apify key

Tab `apify_keys`:
- `api_key`: key từ Bước 1
- `email`: Gmail tạo tài khoản Apify
- `usage_count`: `0`
- `monthly_limit`: `450`
- `is_active`: `TRUE`

---

### Chạy Thủ Công

1. Vào repo GitHub → tab **Actions**
2. Chọn **"Scrape & Schedule Facebook Posts"**
3. Click **"Run workflow"**
4. Tùy chọn `clear_dedup`:
   - `false` (mặc định): chạy bình thường
   - `true`: xóa toàn bộ lịch sử dedup → đăng lại tất cả bài cũ

---

### Xem Kết Quả

- **GitHub Actions logs**: xem từng bước trong lần chạy
- **Google Sheet tab `logs`**: lịch sử từng bài đăng
- **Facebook Page → Publishing Tools → Scheduled Posts**: danh sách bài đã hẹn giờ

---

### Xử Lý Sự Cố

| Vấn đề | Nguyên nhân | Cách sửa |
|--------|-------------|----------|
| Workflow không tự chạy | GitHub tắt cron trên repo không hoạt động | Push 1 commit nhỏ hoặc chạy thủ công |
| Không tải được Reel/video | Cookie Facebook hết hạn | Xuất cookie mới, cập nhật secret `FACEBOOK_COOKIES` |
| 400 Bad Request khi đăng | Token hết hạn hoặc bị thu hồi | Lấy lại token (Bước 3), cập nhật Sheet |
| Không scrape được bài | Apify key hết quota | Thêm Apify account mới vào Sheet |
| Bài bị đăng lại | Dedup bị xóa | Kiểm tra tab `dedup` |

---

## License

MIT License — free to use, modify, and distribute.

---

*Keywords: auto facebook post, tự động đăng bài facebook, facebook auto post, facebook page automation, schedule facebook posts, facebook post scheduler, apify facebook scraper, github actions facebook*
