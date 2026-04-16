# Hướng dẫn lấy Facebook Page ID & Access Token

## Mục lục
1. [Chuẩn bị](#1-chuẩn-bị)
2. [Lấy Page ID](#2-lấy-page-id)
3. [Lấy Long-lived Page Access Token](#3-lấy-long-lived-page-access-token)
4. [Kiểm tra token](#4-kiểm-tra-token)
5. [Cập nhật vào Google Sheet](#5-cập-nhật-vào-google-sheet)
6. [Khi token hết hạn](#6-khi-token-hết-hạn)

---

## 1. Chuẩn bị

Bạn cần có:
- Tài khoản Facebook **quản trị viên** của trang cần thêm
- Đã tạo **Facebook App** tại `developers.facebook.com` (dùng chung app đã có)
- **App ID** và **App Secret**: vào app → **Settings → Basic** → copy 2 giá trị này

---

## 2. Lấy Page ID

**Cách 1: Từ Graph API Explorer (lấy luôn cùng bước 3)**
- Page ID sẽ xuất hiện trong kết quả ở Bước 3 bên dưới (trường `id`)

**Cách 2: Từ trang Facebook**
1. Vào trang Facebook của bạn
2. Click **Giới thiệu** (About)
3. Cuộn xuống → tìm mục **Page ID** (dãy số dài)

**Cách 3: Từ URL trang**
- Nếu trang dùng tên: vào browser gõ `https://graph.facebook.com/TenTrang?fields=id`
- Kết quả trả về `"id": "1234567890"`

---

## 3. Lấy Long-lived Page Access Token

### Bước 3.1 — Lấy Short-lived User Token

1. Vào: `https://developers.facebook.com/tools/explorer`
2. Góc trên phải:
   - **Meta App**: chọn app của bạn
   - **User or Page**: chọn **"Get User Access Token"**
3. Click **"Generate Access Token"**
4. Tích chọn các quyền sau:
   - ✅ `pages_manage_posts`
   - ✅ `pages_read_engagement`
   - ✅ `pages_show_list`
   - ✅ `publish_to_groups` *(nếu cần)*
5. Click **"Generate Access Token"** → đăng nhập Facebook → cho phép
6. **Copy token** hiện ra (token ngắn hạn ~1-2 giờ)

---

### Bước 3.2 — Đổi sang Long-lived User Token (~60 ngày)

Mở browser, dán URL sau (thay thế các giá trị):

```
https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_USER_TOKEN
```

**Ví dụ:**
```
https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=123456789&client_secret=abcdef123456&fb_exchange_token=EAABcde...
```

Kết quả trả về:
```json
{
  "access_token": "EAABxxx...longtoken...",
  "token_type": "bearer",
  "expires_in": 5183944
}
```

Copy giá trị `access_token` — đây là **Long-lived User Token** (~60 ngày).

---

### Bước 3.3 — Lấy Page Token vĩnh viễn (không hết hạn)

Mở browser, dán URL sau:

```
https://graph.facebook.com/v21.0/me/accounts?access_token=LONG_LIVED_USER_TOKEN
```

Kết quả trả về danh sách tất cả pages bạn quản lý:

```json
{
  "data": [
    {
      "access_token": "EAAxxxPAGE_TOKEN_VINH_VIENxxx",
      "category": "News & Media",
      "name": "Tên Trang",
      "id": "714759535606831",
      "tasks": ["ANALYZE", "ADVERTISE", "MODERATE", "CREATE_CONTENT"]
    },
    ...
  ]
}
```

Với **mỗi trang** cần thêm, copy:
- `id` → đây là **Page ID**
- `access_token` → đây là **Page Access Token vĩnh viễn**

> ⚠️ **Lưu ý quan trọng**: `access_token` ở đây là **Page Token**, khác với User Token ở Bước 3.2. Page Token này **không bao giờ hết hạn** miễn là bạn vẫn là quản trị viên của trang.

---

## 4. Kiểm tra token

Luôn kiểm tra trước khi điền vào Sheet:

1. Vào: `https://developers.facebook.com/tools/debug/accesstoken`
2. Paste **Page Token** vào ô → click **"Debug"**
3. Kiểm tra các mục:
   - **App**: phải là app của bạn
   - **Type**: phải là **"Page"**
   - **Expires**: phải là **"Never"**
   - **Scopes**: phải có `pages_manage_posts`, `pages_read_engagement`

Nếu **Expires** không phải "Never" → bạn đang dùng User Token, không phải Page Token. Làm lại Bước 3.3.

---

## 5. Cập nhật vào Google Sheet

Mở Google Sheet → tab **destination_pages** → thêm hàng mới:

| Cột | Giá trị | Ví dụ |
|-----|---------|-------|
| `fb_page_id` | ID số của trang | `714759535606831` |
| `fb_page_name` | Tên trang (để nhận biết) | `Tân Mai News` |
| `fb_access_token` | Page Token vĩnh viễn từ Bước 3.3 | `EAABxxx...` |
| `group_id` | Tên nhóm (phải trùng source pages) | `Công an phường Tân Mai` |
| `max_posts_per_run` | Số bài tối đa mỗi lần chạy | `4` |
| `post_interval_hours` | Khoảng cách giữa 2 bài (giờ) | `2` |

---

## 6. Khi token hết hạn

### Nhận biết token hết hạn
Trong log GitHub Actions sẽ thấy lỗi:
```
400 Bad Request for url 'https://graph.facebook.com/v21.0/PAGE_ID/photos'
Session has expired on ...
```

### Page Token vĩnh viễn có thể bị vô hiệu nếu:
- Bạn **đổi mật khẩu** Facebook
- Bạn **thu hồi quyền** của app
- Facebook **phát hiện hoạt động bất thường**
- Bạn **không còn là quản trị viên** của trang

### Cách lấy lại token mới

Làm lại từ **Bước 3.1** → **Bước 3.3** và cập nhật token mới vào Google Sheet.

> 💡 **Mẹo**: Sau khi lấy token mới, vào `developers.facebook.com/tools/debug/accesstoken` kiểm tra **Expires = Never** trước khi điền vào Sheet.

---

## Tóm tắt nhanh

```
Graph API Explorer
→ Get User Token (short-lived)
→ Exchange → Long-lived User Token (~60 ngày)
→ /me/accounts → Page Token (VĨNH VIỄN) ✅
→ Kiểm tra: Type=Page, Expires=Never
→ Điền vào Google Sheet
```
