"""
Admin CLI - Quản lý hệ thống Auto Facebook Post.
Chạy: python admin/manage.py

Menu:
  1. Xem tổng quan (groups, pages, queue)
  2. Thêm nhóm trang mới
  3. Thêm trang nguồn (scrape từ đây)
  4. Thêm trang đích (đăng lên đây)
  5. Thêm Apify API key
  6. Xem trạng thái Apify keys
  7. Xem lịch đăng sắp tới
  8. Xem logs gần đây
"""
import sys
import os

# Chạy từ thư mục gốc project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.database import get_db
from src.key_rotator import get_all_keys_status, add_key


def clear():
    os.system("clear" if os.name == "posix" else "cls")


def print_header():
    print("\n" + "=" * 55)
    print("   AUTO FACEBOOK POST - Admin Panel")
    print("=" * 55)


def menu():
    print_header()
    print("1. Tổng quan hệ thống")
    print("2. Thêm nhóm trang mới")
    print("3. Thêm trang NGUỒN (scrape từ đây)")
    print("4. Thêm trang ĐÍCH (đăng lên đây)")
    print("5. Thêm Apify API key")
    print("6. Trạng thái Apify keys")
    print("7. Lịch đăng sắp tới")
    print("8. Logs gần đây")
    print("9. Xóa trang nguồn / đích")
    print("0. Thoát")
    print("-" * 55)
    return input("Chọn: ").strip()


# ── 1. Tổng quan ───────────────────────────────────────────

def show_overview():
    db = get_db()
    print("\n── NHÓM TRANG ──")
    groups = db.table("page_groups").select("*").eq("is_active", True).execute().data
    for g in groups:
        src_count  = len(db.table("source_pages").select("id")
                          .eq("group_id", g["id"]).execute().data)
        dest_count = len(db.table("destination_pages").select("id")
                          .eq("group_id", g["id"]).execute().data)
        pending    = len(db.table("scheduled_posts").select("id")
                          .eq("status", "pending").execute().data)
        print(f"  [{g['id'][:8]}] {g['name']}")
        print(f"    Nguồn: {src_count} trang | Đích: {dest_count} trang | Queue: {pending} bài")

    if not groups:
        print("  (Chưa có nhóm nào)")

    print("\n── TỔNG QUEUE ──")
    pending_all = db.table("scheduled_posts").select("id, scheduled_at") \
                    .eq("status", "pending").order("scheduled_at").limit(5).execute().data
    print(f"  Đang chờ đăng: {len(pending_all)} bài (5 bài gần nhất bên dưới)")
    for p in pending_all:
        print(f"  → {p['scheduled_at'][:16].replace('T', ' ')}")

    print("\n── APIFY KEYS ──")
    keys = get_all_keys_status()
    for k in keys:
        bar = "█" * int(k["usage_count"] / k["monthly_limit"] * 20)
        pct = k["usage_count"] / k["monthly_limit"] * 100
        status = "✓" if k["is_active"] else "✗"
        print(f"  {status} {k['email'] or 'No email':<30} "
              f"{k['usage_count']:>3}/{k['monthly_limit']} ({pct:.0f}%) [{bar:<20}]")
    if not keys:
        print("  (Chưa có key nào)")


# ── 2. Thêm nhóm ───────────────────────────────────────────

def add_group():
    print("\n── THÊM NHÓM TRANG MỚI ──")
    name = input("Tên nhóm (VD: Nhóm nấu ăn): ").strip()
    if not name:
        print("Tên không được để trống")
        return
    db = get_db()
    res = db.table("page_groups").insert({"name": name}).execute()
    gid = res.data[0]["id"]
    print(f"✓ Đã tạo nhóm: {name} [ID: {gid[:8]}...]")


# ── 3. Thêm trang nguồn ────────────────────────────────────

def add_source_page():
    print("\n── THÊM TRANG NGUỒN ──")
    db = get_db()

    groups = db.table("page_groups").select("*").eq("is_active", True).execute().data
    if not groups:
        print("Chưa có nhóm nào! Hãy tạo nhóm trước (mục 2).")
        return

    print("Chọn nhóm:")
    for i, g in enumerate(groups, 1):
        print(f"  {i}. {g['name']}")
    try:
        idx = int(input("Số: ")) - 1
        group = groups[idx]
    except (ValueError, IndexError):
        print("Lựa chọn không hợp lệ")
        return

    url = input("URL trang Facebook (VD: https://www.facebook.com/pagename): ").strip()
    if not url.startswith("https://www.facebook.com/"):
        print("URL phải bắt đầu bằng https://www.facebook.com/")
        return

    name = input("Tên trang (để dễ nhận biết): ").strip()

    db.table("source_pages").insert({
        "group_id":     group["id"],
        "fb_page_url":  url,
        "fb_page_name": name or url,
    }).execute()
    print(f"✓ Đã thêm trang nguồn: {name or url}")


# ── 4. Thêm trang đích ─────────────────────────────────────

def add_destination_page():
    print("\n── THÊM TRANG ĐÍCH ──")
    db = get_db()

    groups = db.table("page_groups").select("*").eq("is_active", True).execute().data
    if not groups:
        print("Chưa có nhóm nào! Hãy tạo nhóm trước (mục 2).")
        return

    print("Chọn nhóm:")
    for i, g in enumerate(groups, 1):
        print(f"  {i}. {g['name']}")
    try:
        idx = int(input("Số: ")) - 1
        group = groups[idx]
    except (ValueError, IndexError):
        print("Lựa chọn không hợp lệ")
        return

    page_id = input("Facebook Page ID (số, VD: 123456789): ").strip()
    if not page_id.isdigit():
        print("Page ID phải là số")
        return

    page_name = input("Tên trang: ").strip()
    token     = input("Page Access Token: ").strip()
    if not token:
        print("Token không được để trống")
        return

    db.table("destination_pages").insert({
        "group_id":        group["id"],
        "fb_page_id":      page_id,
        "fb_page_name":    page_name or page_id,
        "fb_access_token": token,
    }).execute()
    print(f"✓ Đã thêm trang đích: {page_name or page_id}")


# ── 5. Thêm Apify key ──────────────────────────────────────

def add_apify_key():
    print("\n── THÊM APIFY API KEY ──")
    print("Lấy key tại: https://console.apify.com/account/integrations")
    api_key = input("API Key: ").strip()
    email   = input("Email tài khoản (để ghi chú): ").strip()
    if not api_key:
        print("Key không được để trống")
        return
    success = add_key(api_key, email)
    if success:
        print("✓ Đã thêm Apify key")


# ── 6. Trạng thái Apify keys ───────────────────────────────

def show_apify_status():
    print("\n── TRẠNG THÁI APIFY KEYS ──")
    keys = get_all_keys_status()
    if not keys:
        print("Chưa có key nào")
        return
    print(f"{'Email':<35} {'Đã dùng':>8} {'Limit':>8} {'%':>5} {'Active':>8}")
    print("-" * 70)
    for k in keys:
        pct    = k["usage_count"] / k["monthly_limit"] * 100
        status = "✓" if k["is_active"] else "✗"
        last   = (k["last_used_at"] or "Chưa dùng")[:10]
        print(f"{k['email'] or 'N/A':<35} {k['usage_count']:>8} "
              f"{k['monthly_limit']:>8} {pct:>4.0f}% {status:>8}  {last}")


# ── 7. Lịch đăng ───────────────────────────────────────────

def show_schedule():
    print("\n── LỊCH ĐĂNG SẮP TỚI (20 bài) ──")
    db = get_db()
    items = db.table("scheduled_posts") \
               .select("scheduled_at, destination_pages(fb_page_name), posts(content)") \
               .eq("status", "pending") \
               .order("scheduled_at") \
               .limit(20).execute().data
    if not items:
        print("Không có bài nào trong queue")
        return
    for item in items:
        time_str  = item["scheduled_at"][:16].replace("T", " ")
        page_name = (item.get("destination_pages") or {}).get("fb_page_name", "?")
        content   = ((item.get("posts") or {}).get("content") or "")[:60]
        print(f"  {time_str}  →  {page_name:<25}  {content}...")


# ── 8. Logs ────────────────────────────────────────────────

def show_logs():
    print("\n── LOGS GẦN ĐÂY (20 dòng) ──")
    db = get_db()
    logs = db.table("post_logs") \
              .select("created_at, result, fb_post_id, error_message") \
              .order("created_at", desc=True) \
              .limit(20).execute().data
    if not logs:
        print("Chưa có log nào")
        return
    for log in logs:
        icon     = "✓" if log["result"] == "success" else "✗"
        time_str = log["created_at"][:16].replace("T", " ")
        err      = f" | {log['error_message'][:50]}" if log.get("error_message") else ""
        print(f"  {icon} {time_str}  {log['fb_post_id'][:20]}...{err}")


# ── 9. Xóa trang ───────────────────────────────────────────

def delete_page():
    print("\n── XÓA TRANG ──")
    print("1. Xóa trang nguồn")
    print("2. Xóa trang đích")
    choice = input("Chọn: ").strip()
    db = get_db()

    if choice == "1":
        pages = db.table("source_pages").select("id, fb_page_name, fb_page_url") \
                   .execute().data
        if not pages:
            print("Không có trang nguồn nào")
            return
        for i, p in enumerate(pages, 1):
            print(f"  {i}. {p['fb_page_name']} ({p['fb_page_url']})")
        try:
            idx = int(input("Số trang cần xóa: ")) - 1
            page = pages[idx]
            confirm = input(f"Xóa '{page['fb_page_name']}'? (y/n): ")
            if confirm.lower() == "y":
                db.table("source_pages").update({"is_active": False}) \
                  .eq("id", page["id"]).execute()
                print("✓ Đã vô hiệu hóa trang nguồn")
        except (ValueError, IndexError):
            print("Lựa chọn không hợp lệ")

    elif choice == "2":
        pages = db.table("destination_pages").select("id, fb_page_name, fb_page_id") \
                   .execute().data
        if not pages:
            print("Không có trang đích nào")
            return
        for i, p in enumerate(pages, 1):
            print(f"  {i}. {p['fb_page_name']} (ID: {p['fb_page_id']})")
        try:
            idx = int(input("Số trang cần xóa: ")) - 1
            page = pages[idx]
            confirm = input(f"Xóa '{page['fb_page_name']}'? (y/n): ")
            if confirm.lower() == "y":
                db.table("destination_pages").update({"is_active": False}) \
                  .eq("id", page["id"]).execute()
                print("✓ Đã vô hiệu hóa trang đích")
        except (ValueError, IndexError):
            print("Lựa chọn không hợp lệ")


# ── Main ───────────────────────────────────────────────────

ACTIONS = {
    "1": show_overview,
    "2": add_group,
    "3": add_source_page,
    "4": add_destination_page,
    "5": add_apify_key,
    "6": show_apify_status,
    "7": show_schedule,
    "8": show_logs,
    "9": delete_page,
}

if __name__ == "__main__":
    while True:
        try:
            choice = menu()
            if choice == "0":
                print("Thoát.")
                break
            action = ACTIONS.get(choice)
            if action:
                action()
            else:
                print("Lựa chọn không hợp lệ")
            input("\nNhấn Enter để tiếp tục...")
        except KeyboardInterrupt:
            print("\nThoát.")
            break
        except Exception as e:
            print(f"\nLỗi: {e}")
            input("Nhấn Enter để tiếp tục...")
