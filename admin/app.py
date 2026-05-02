"""
Web Admin Panel - Auto Facebook Post
Deploy trên Streamlit Community Cloud (miễn phí)
Truy cập từ bất kỳ đâu qua trình duyệt, không cần mở máy local.
"""

import io
import logging
import streamlit as st
from supabase import create_client
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

# ── Page config ────────────────────────────────────────────
st.set_page_config(
    page_title="Auto FB Post - Admin",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Supabase client ────────────────────────────────────────
@st.cache_resource
def get_db():
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        st.error("Thiếu SUPABASE_URL hoặc SUPABASE_KEY trong Secrets!")
        st.stop()
    return create_client(url, key)


# ══════════════════════════════════════════════════════════
# SIDEBAR NAVIGATION
# ══════════════════════════════════════════════════════════
with st.sidebar:
    st.title("📘 Auto FB Post")
    st.markdown("---")
    page = st.radio(
        "Menu",
        [
            "📊 Tổng quan",
            "👥 Nhóm trang",
            "🔍 Trang nguồn",
            "📤 Trang đích",
            "🔑 Apify Keys",
            "🗓️ Lịch đăng",
            "📋 Logs",
            "🚀 Chạy Scrape",
            "⚙️ Cài đặt",
        ],
        label_visibility="collapsed",
    )


# ══════════════════════════════════════════════════════════
# PAGE: TỔNG QUAN
# ══════════════════════════════════════════════════════════
if page == "📊 Tổng quan":
    st.title("📊 Tổng quan hệ thống")

    db = get_db()

    col1, col2, col3, col4 = st.columns(4)

    # Số nhóm
    groups = db.table("page_groups").select("id").eq("is_active", True).execute().data
    col1.metric("Nhóm trang", len(groups))

    # Số nguồn
    sources = db.table("source_pages").select("id").eq("is_active", True).execute().data
    col2.metric("Trang nguồn", len(sources))

    # Số đích
    dests = (
        db.table("destination_pages").select("id").eq("is_active", True).execute().data
    )
    col3.metric("Trang đích", len(dests))

    # Queue pending
    queue = (
        db.table("scheduled_posts").select("id").eq("status", "pending").execute().data
    )
    col4.metric("Bài chờ đăng", len(queue))

    st.markdown("---")
    col_a, col_b = st.columns(2)

    # Lịch đăng sắp tới
    with col_a:
        st.subheader("🗓️ Lịch đăng sắp tới (10 bài)")
        upcoming = (
            db.table("scheduled_posts")
            .select("scheduled_at, destination_pages(fb_page_name), posts(content)")
            .eq("status", "pending")
            .order("scheduled_at")
            .limit(10)
            .execute()
            .data
        )

        if upcoming:
            rows = []
            for item in upcoming:
                rows.append(
                    {
                        "Giờ đăng": item["scheduled_at"][:16].replace("T", " "),
                        "Trang đích": (item.get("destination_pages") or {}).get(
                            "fb_page_name", "?"
                        ),
                        "Nội dung": ((item.get("posts") or {}).get("content") or "")[
                            :80
                        ]
                        + "...",
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("Không có bài nào trong queue")

    # Logs gần đây
    with col_b:
        st.subheader("📋 Logs gần đây (10 dòng)")
        logs = (
            db.table("post_logs")
            .select("created_at, result, error_message")
            .order("created_at", desc=True)
            .limit(10)
            .execute()
            .data
        )

        if logs:
            rows = []
            for log in logs:
                rows.append(
                    {
                        "Thời gian": log["created_at"][:16].replace("T", " "),
                        "Kết quả": "✓ Thành công"
                        if log["result"] in ("success", "scheduled")
                        else "✗ Thất bại",
                        "Lỗi": log.get("error_message") or "",
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("Chưa có log nào")

    # Apify keys status
    st.markdown("---")
    st.subheader("🔑 Trạng thái Apify Keys")
    keys = (
        db.table("apify_keys")
        .select("email, usage_count, monthly_limit, is_active, last_used_at")
        .order("usage_count")
        .execute()
        .data
    )

    if keys:
        for k in keys:
            pct = k["usage_count"] / k["monthly_limit"] * 100
            label = f"{'✓' if k['is_active'] else '✗'}  {k['email'] or 'No email'}  —  {k['usage_count']}/{k['monthly_limit']}"
            color = "normal" if pct < 80 else ("off" if pct >= 100 else "inverse")
            st.progress(min(pct / 100, 1.0), text=label)
    else:
        st.warning("Chưa có Apify key nào. Vào mục 🔑 Apify Keys để thêm.")


# ══════════════════════════════════════════════════════════
# PAGE: NHÓM TRANG
# ══════════════════════════════════════════════════════════
elif page == "👥 Nhóm trang":
    st.title("👥 Quản lý nhóm trang")
    db = get_db()

    # Danh sách nhóm hiện có
    st.subheader("Danh sách nhóm")
    groups = db.table("page_groups").select("*").order("created_at").execute().data

    if groups:
        for g in groups:
            src_count = len(
                db.table("source_pages")
                .select("id")
                .eq("group_id", g["id"])
                .execute()
                .data
            )
            dest_count = len(
                db.table("destination_pages")
                .select("id")
                .eq("group_id", g["id"])
                .execute()
                .data
            )
            pending = len(
                db.table("scheduled_posts")
                .select("id, destination_pages!inner(group_id)")
                .eq("status", "pending")
                .execute()
                .data
            )

            with st.expander(
                f"{'🟢' if g['is_active'] else '🔴'} **{g['name']}** "
                f"— {src_count} nguồn | {dest_count} đích | ID: `{g['id'][:8]}...`"
            ):
                col1, col2, col3 = st.columns(3)
                col1.metric("Trang nguồn", src_count)
                col2.metric("Trang đích", dest_count)

                c1, c2 = st.columns(2)
                if g["is_active"]:
                    if c1.button("🔴 Tắt nhóm", key=f"deact_{g['id']}"):
                        db.table("page_groups").update({"is_active": False}).eq(
                            "id", g["id"]
                        ).execute()
                        st.rerun()
                else:
                    if c1.button("🟢 Bật nhóm", key=f"act_{g['id']}"):
                        db.table("page_groups").update({"is_active": True}).eq(
                            "id", g["id"]
                        ).execute()
                        st.rerun()
    else:
        st.info("Chưa có nhóm nào")

    st.markdown("---")

    # Thêm nhóm mới
    st.subheader("➕ Thêm nhóm mới")
    with st.form("add_group"):
        name = st.text_input("Tên nhóm", placeholder="VD: Nhóm nấu ăn, Nhóm du lịch...")
        submitted = st.form_submit_button("✅ Tạo nhóm", use_container_width=True)
        if submitted:
            if not name.strip():
                st.error("Tên nhóm không được để trống")
            else:
                db.table("page_groups").insert({"name": name.strip()}).execute()
                st.success(f"✅ Đã tạo nhóm: **{name}**")
                st.rerun()


# ══════════════════════════════════════════════════════════
# PAGE: TRANG NGUỒN
# ══════════════════════════════════════════════════════════
elif page == "🔍 Trang nguồn":
    st.title("🔍 Quản lý trang nguồn (scrape từ đây)")
    db = get_db()

    groups = db.table("page_groups").select("*").eq("is_active", True).execute().data
    if not groups:
        st.warning("Chưa có nhóm nào! Vào mục 👥 Nhóm trang để tạo nhóm trước.")
        st.stop()

    # Filter theo nhóm
    group_map = {g["name"]: g["id"] for g in groups}
    sel_group_name = st.selectbox("Lọc theo nhóm", ["Tất cả"] + list(group_map.keys()))

    # Danh sách trang nguồn
    query = db.table("source_pages").select("*, page_groups(name)")
    if sel_group_name != "Tất cả":
        query = query.eq("group_id", group_map[sel_group_name])
    pages = query.order("created_at", desc=True).execute().data

    if pages:
        rows = []
        for p in pages:
            rows.append(
                {
                    "Tên trang": p.get("fb_page_name") or "",
                    "URL": p["fb_page_url"],
                    "Nhóm": (p.get("page_groups") or {}).get("name", "?"),
                    "Trạng thái": "🟢 Hoạt động" if p["is_active"] else "🔴 Tắt",
                    "Lần cuối scrape": (p.get("last_scraped_at") or "Chưa")[
                        :16
                    ].replace("T", " "),
                    "ID": p["id"][:8] + "...",
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)

        # Bật/tắt trang
        page_names = [f"{p.get('fb_page_name') or p['fb_page_url']}" for p in pages]
        sel_page_name = st.selectbox("Chọn trang để bật/tắt", page_names)
        sel_page = next(
            p
            for p in pages
            if (p.get("fb_page_name") or p["fb_page_url"]) == sel_page_name
        )

        c1, c2 = st.columns(2)
        if sel_page["is_active"]:
            if c1.button("🔴 Tắt trang này"):
                db.table("source_pages").update({"is_active": False}).eq(
                    "id", sel_page["id"]
                ).execute()
                st.rerun()
        else:
            if c1.button("🟢 Bật trang này"):
                db.table("source_pages").update({"is_active": True}).eq(
                    "id", sel_page["id"]
                ).execute()
                st.rerun()
        if c2.button("🗑️ Xóa hẳn trang này", type="secondary"):
            db.table("source_pages").delete().eq("id", sel_page["id"]).execute()
            st.success("Đã xóa")
            st.rerun()
    else:
        st.info("Chưa có trang nguồn nào")

    st.markdown("---")

    # Thêm trang nguồn mới
    st.subheader("➕ Thêm trang nguồn mới")
    with st.form("add_source"):
        group_name = st.selectbox("Thuộc nhóm", list(group_map.keys()))
        page_name = st.text_input(
            "Tên trang (ghi chú)", placeholder="VD: Trang nấu ăn ABC"
        )
        page_url = st.text_input(
            "URL Facebook page",
            placeholder="https://www.facebook.com/pagename",
        )
        submitted = st.form_submit_button(
            "✅ Thêm trang nguồn", use_container_width=True
        )
        if submitted:
            if not page_url.startswith("https://www.facebook.com/"):
                st.error("URL phải bắt đầu bằng https://www.facebook.com/")
            else:
                db.table("source_pages").insert(
                    {
                        "group_id": group_map[group_name],
                        "fb_page_url": page_url.strip(),
                        "fb_page_name": page_name.strip() or page_url.strip(),
                    }
                ).execute()
                st.success(f"✅ Đã thêm: **{page_name or page_url}**")
                st.rerun()


# ══════════════════════════════════════════════════════════
# PAGE: TRANG ĐÍCH
# ══════════════════════════════════════════════════════════
elif page == "📤 Trang đích":
    st.title("📤 Quản lý trang đích (đăng bài lên đây)")
    db = get_db()

    groups = db.table("page_groups").select("*").eq("is_active", True).execute().data
    if not groups:
        st.warning("Chưa có nhóm nào! Vào mục 👥 Nhóm trang để tạo nhóm trước.")
        st.stop()

    group_map = {g["name"]: g["id"] for g in groups}

    # Danh sách trang đích
    pages = (
        db.table("destination_pages")
        .select("*, page_groups(name)")
        .order("created_at", desc=True)
        .execute()
        .data
    )

    if pages:
        rows = []
        for p in pages:
            rows.append(
                {
                    "Tên trang": p.get("fb_page_name") or "",
                    "Page ID": p["fb_page_id"],
                    "Nhóm": (p.get("page_groups") or {}).get("name", "?"),
                    "Trạng thái": "🟢 Hoạt động" if p["is_active"] else "🔴 Tắt",
                    "Token (5 ký tự)": p["fb_access_token"][:5] + "...",
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)

        # Bật/tắt hoặc cập nhật token
        page_names = [f"{p.get('fb_page_name') or p['fb_page_id']}" for p in pages]
        sel_name = st.selectbox("Chọn trang để quản lý", page_names)
        sel = next(
            p for p in pages if (p.get("fb_page_name") or p["fb_page_id"]) == sel_name
        )

        c1, c2, c3 = st.columns(3)
        if sel["is_active"]:
            if c1.button("🔴 Tắt trang"):
                db.table("destination_pages").update({"is_active": False}).eq(
                    "id", sel["id"]
                ).execute()
                st.rerun()
        else:
            if c1.button("🟢 Bật trang"):
                db.table("destination_pages").update({"is_active": True}).eq(
                    "id", sel["id"]
                ).execute()
                st.rerun()
        if c3.button("🗑️ Xóa trang", type="secondary"):
            db.table("destination_pages").delete().eq("id", sel["id"]).execute()
            st.rerun()

        # Cập nhật token
        with st.expander("🔄 Cập nhật Access Token cho trang này"):
            new_token = st.text_input("Token mới", type="password", key="new_token")
            if st.button("💾 Lưu token mới"):
                if new_token.strip():
                    db.table("destination_pages").update(
                        {"fb_access_token": new_token.strip()}
                    ).eq("id", sel["id"]).execute()
                    st.success("✅ Đã cập nhật token")
    else:
        st.info("Chưa có trang đích nào")

    st.markdown("---")

    # Thêm trang đích mới
    st.subheader("➕ Thêm trang đích mới")

    with st.expander("ℹ️ Cách lấy Page ID và Access Token", expanded=False):
        st.markdown("""
        **Lấy Page ID:**
        1. Vào trang Facebook của bạn
        2. Click **"Giới thiệu"** → cuộn xuống → thấy **"ID trang"** (dãy số)

        **Lấy Access Token:**
        1. Vào [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer)
        2. Chọn App → Generate Access Token → cấp quyền `pages_manage_posts`
        3. Click **"Get Page Access Token"** → chọn trang → Copy

        **Lưu ý:** Token mặc định hết hạn 1 giờ. Để lấy token dài hạn (60 ngày),
        xem hướng dẫn trong README.
        """)

    with st.form("add_dest"):
        group_name = st.selectbox(
            "Thuộc nhóm", list(group_map.keys()), key="dest_group"
        )
        page_name = st.text_input(
            "Tên trang (ghi chú)", placeholder="VD: Trang Nấu Ăn Của Tôi"
        )
        page_id = st.text_input("Facebook Page ID", placeholder="123456789")
        token = st.text_input("Page Access Token", type="password")
        submitted = st.form_submit_button(
            "✅ Thêm trang đích", use_container_width=True
        )
        if submitted:
            if not page_id.strip().isdigit():
                st.error("Page ID phải là dãy số")
            elif not token.strip():
                st.error("Access Token không được để trống")
            else:
                db.table("destination_pages").insert(
                    {
                        "group_id": group_map[group_name],
                        "fb_page_id": page_id.strip(),
                        "fb_page_name": page_name.strip() or page_id.strip(),
                        "fb_access_token": token.strip(),
                    }
                ).execute()
                st.success(f"✅ Đã thêm: **{page_name or page_id}**")
                st.rerun()


# ══════════════════════════════════════════════════════════
# PAGE: APIFY KEYS
# ══════════════════════════════════════════════════════════
elif page == "🔑 Apify Keys":
    st.title("🔑 Quản lý Apify API Keys")
    db = get_db()

    # Danh sách keys
    st.subheader("Danh sách keys hiện tại")
    keys = db.table("apify_keys").select("*").order("usage_count").execute().data

    if keys:
        for k in keys:
            pct = k["usage_count"] / k["monthly_limit"] * 100
            status_icon = "🟢" if k["is_active"] and pct < 100 else "🔴"

            with st.expander(
                f"{status_icon} **{k['email'] or 'No email'}** — "
                f"{k['usage_count']}/{k['monthly_limit']} ({pct:.0f}%)"
            ):
                st.progress(min(pct / 100, 1.0))
                c1, c2, c3 = st.columns(3)
                c1.metric("Đã dùng", k["usage_count"])
                c2.metric("Giới hạn", k["monthly_limit"])
                c3.metric("Còn lại", max(0, k["monthly_limit"] - k["usage_count"]))

                st.text(f"Key: {k['api_key'][:10]}...{k['api_key'][-5:]}")
                st.text(f"Lần dùng cuối: {(k['last_used_at'] or 'Chưa dùng')[:16]}")
                st.text(f"Reset ngày: {k['reset_at']}")

                col1, col2 = st.columns(2)
                if k["is_active"]:
                    if col1.button("🔴 Tắt key", key=f"off_{k['id']}"):
                        db.table("apify_keys").update({"is_active": False}).eq(
                            "id", k["id"]
                        ).execute()
                        st.rerun()
                else:
                    if col1.button("🟢 Bật key", key=f"on_{k['id']}"):
                        db.table("apify_keys").update({"is_active": True}).eq(
                            "id", k["id"]
                        ).execute()
                        st.rerun()
                if col2.button("🗑️ Xóa key", key=f"del_{k['id']}", type="secondary"):
                    db.table("apify_keys").delete().eq("id", k["id"]).execute()
                    st.rerun()
    else:
        st.warning("Chưa có Apify key nào!")

    st.markdown("---")

    # Thêm key mới
    st.subheader("➕ Thêm Apify API key mới")

    with st.expander("ℹ️ Cách lấy Apify API key miễn phí", expanded=False):
        st.markdown("""
        1. Vào **[apify.com](https://apify.com)** → Sign Up bằng Gmail mới
        2. Sau khi đăng ký: vào **Console → Settings → Integrations**
        3. Copy **Personal API token**
        4. Dán vào form bên dưới

        💡 **Mẹo**: Mỗi tài khoản = $5 credit miễn phí ≈ 450-500 lần scrape/tháng.
        Tạo nhiều tài khoản Gmail khác nhau để có nhiều credit hơn.
        """)

    with st.form("add_apify_key"):
        email = st.text_input("Gmail tạo tài khoản", placeholder="myemail@gmail.com")
        api_key = st.text_input("Apify API Token", placeholder="apify_api_xxxxxxxx")
        limit = st.number_input(
            "Giới hạn an toàn (mặc định 450)", value=450, min_value=100, max_value=500
        )
        submitted = st.form_submit_button("✅ Thêm key", use_container_width=True)
        if submitted:
            if not api_key.strip():
                st.error("API key không được để trống")
            else:
                try:
                    db.table("apify_keys").insert(
                        {
                            "api_key": api_key.strip(),
                            "email": email.strip(),
                            "monthly_limit": int(limit),
                        }
                    ).execute()
                    st.success(f"✅ Đã thêm key cho: **{email}**")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi (có thể key đã tồn tại): {e}")


# ══════════════════════════════════════════════════════════
# PAGE: LỊCH ĐĂNG
# ══════════════════════════════════════════════════════════
elif page == "🗓️ Lịch đăng":
    st.title("🗓️ Lịch đăng bài")
    db = get_db()

    col1, col2 = st.columns([3, 1])
    with col2:
        limit = st.selectbox("Hiển thị", [20, 50, 100], index=0)
        status_filter = st.selectbox(
            "Trạng thái", ["pending", "scheduled", "posted", "failed", "Tất cả"]
        )

    query = db.table("scheduled_posts").select(
        "scheduled_at, status, retry_count, destination_pages(fb_page_name), posts(content, fb_post_id, image_urls, video_url)"
    )

    if status_filter != "Tất cả":
        query = query.eq("status", status_filter)

    items = (
        query.order("scheduled_at", desc=(status_filter in ("posted", "failed")))
        .limit(limit)
        .execute()
        .data
    )

    if items:
        rows = []
        for item in items:
            post = item.get("posts") or {}
            content = (post.get("content") or "")[:80]
            has_img = "🖼️" if post.get("image_urls") else ""
            has_vid = "🎬" if post.get("video_url") else ""
            status_emoji = {
                "pending": "⏳ Chờ",
                "scheduled": "📅 Đã hẹn",
                "posted": "✅ Đã đăng",
                "failed": "❌ Lỗi",
            }.get(item["status"], item["status"])
            rows.append(
                {
                    "Giờ đăng": item["scheduled_at"][:16].replace("T", " "),
                    "Trang đích": (item.get("destination_pages") or {}).get(
                        "fb_page_name", "?"
                    ),
                    "Media": f"{has_img}{has_vid}",
                    "Nội dung": content,
                    "Trạng thái": status_emoji,
                    "Retry": item.get("retry_count", 0),
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption(f"Hiển thị {len(rows)} bài")
    else:
        st.info("Không có bài nào")


# ══════════════════════════════════════════════════════════
# PAGE: LOGS
# ══════════════════════════════════════════════════════════
elif page == "📋 Logs":
    st.title("📋 Logs hệ thống")
    db = get_db()

    col1, col2 = st.columns([3, 1])
    with col2:
        log_limit = st.selectbox("Hiển thị", [50, 100, 200], index=0)
        log_filter = st.selectbox("Kết quả", ["Tất cả", "success", "failed"])

    query = db.table("post_logs").select("*")
    if log_filter != "Tất cả":
        query = query.eq("result", log_filter)

    logs = query.order("created_at", desc=True).limit(log_limit).execute().data

    if logs:
        # Thống kê nhanh
        success_count = sum(1 for l in logs if l["result"] in ("success", "scheduled"))
        fail_count = sum(1 for l in logs if l["result"] == "failed")
        c1, c2, c3 = st.columns(3)
        c1.metric("Tổng", len(logs))
        c2.metric("✓ Thành công", success_count)
        c3.metric("✗ Thất bại", fail_count)

        rows = []
        for log in logs:
            rows.append(
                {
                    "Thời gian": log["created_at"][:16].replace("T", " "),
                    "Kết quả": "✓ OK"
                    if log["result"] in ("success", "scheduled")
                    else "✗ Fail",
                    "Post ID": (log.get("fb_post_id") or "")[:20],
                    "Lỗi": (log.get("error_message") or "")[:80],
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có log nào")


# ══════════════════════════════════════════════════════════
# PAGE: CHẠY SCRAPE
# ══════════════════════════════════════════════════════════
elif page == "🚀 Chạy Scrape":
    st.title("🚀 Chạy Scrape & Đăng bài")

    st.markdown("""
    Bấm nút bên dưới để chạy job scrape + đăng bài ngay lập tức.
    - Scrape bài từ trang nguồn qua Apify
    - Sắp xếp theo tương tác
    - Hẹn giờ đăng lên trang đích
    """)

    clear_dedup = st.selectbox(
        "Xóa dedup trước khi chạy (để đăng lại bài cũ)?",
        ["false", "true"],
        index=0,
    )

    if st.button("▶️ Chạy ngay", type="primary", use_container_width=True):
        db = get_db()

        if clear_dedup == "true":
            with st.spinner("⏳ Đang xóa dedup..."):
                try:
                    db.table("posted_dedup").delete().neq("fb_post_id", "").execute()
                    db.table("posts").delete().in_(
                        "status", ["pending", "scheduled", "posted", "failed"]
                    ).execute()
                    st.success("✅ Đã xóa dedup và lịch cũ")
                except Exception as e:
                    st.warning(f"Không thể xóa dedup: {e}")

        env = os.environ.copy()
        env["DB_BACKEND"] = "supabase"
        env["SUPABASE_URL"] = st.secrets.get("SUPABASE_URL") or os.environ.get(
            "SUPABASE_URL", ""
        )
        env["SUPABASE_KEY"] = st.secrets.get("SUPABASE_KEY") or os.environ.get(
            "SUPABASE_KEY", ""
        )
        env["LOG_LEVEL"] = "INFO"
        env["FORCE_RUN"] = "1"

        status = st.status("⏳ Đang chạy scrape...", expanded=True)
        log_container = st.empty()
        log_lines = []

        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "src.main_scrape"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            )

            for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                log_lines.append(line)
                log_container.code("\n".join(log_lines[-80:]))

            proc.wait()

            if proc.returncode == 0:
                status.update(label="✅ Hoàn tất!", state="complete")
                st.success("Scrape & đăng bài xong!")
            else:
                status.update(label="❌ Có lỗi xảy ra", state="error")
                st.error(f"Job thoát với mã lỗi {proc.returncode}")

        except Exception as e:
            status.update(label="❌ Lỗi", state="error")
            st.error(f"Lỗi: {e}")

        st.button("🔄 Chạy lại", use_container_width=True)


# ══════════════════════════════════════════════════════════
# PAGE: CÀI ĐẶT (auto-run config)
# ══════════════════════════════════════════════════════════
elif page == "⚙️ Cài đặt":
    st.title("⚙️ Cài đặt auto-run")
    db = get_db()

    res = db.table("app_settings").select("*").limit(1).execute().data
    if not res:
        db.table("app_settings").insert(
            {"enabled": False, "interval_minutes": 480}
        ).execute()
        res = db.table("app_settings").select("*").limit(1).execute().data
    s = res[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Trạng thái", "🟢 Bật" if s["enabled"] else "🔴 Tắt")
    col2.metric("Mỗi", f"{s['interval_minutes']} phút")
    last_run = s.get("last_run_at")
    if last_run:
        col3.metric("Lần chạy cuối", last_run[:16].replace("T", " "))
        last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
        next_dt = last_dt + timedelta(minutes=s["interval_minutes"])
        st.info(
            f"⏭️ Lần chạy tiếp theo (sớm nhất): "
            f"{next_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
    else:
        col3.metric("Lần chạy cuối", "Chưa chạy")

    st.markdown("---")

    intervals = [60, 120, 240, 360, 480, 720, 1440]
    interval_labels = {
        60: "1 giờ",
        120: "2 giờ",
        240: "4 giờ",
        360: "6 giờ",
        480: "8 giờ",
        720: "12 giờ",
        1440: "24 giờ",
    }
    cur_interval = s["interval_minutes"]
    if cur_interval not in intervals:
        intervals.append(cur_interval)
        interval_labels[cur_interval] = f"{cur_interval} phút"
        intervals.sort()

    with st.form("settings_form"):
        enabled = st.checkbox("Bật auto-run", value=s["enabled"])
        interval = st.selectbox(
            "Chạy mỗi",
            intervals,
            index=intervals.index(cur_interval),
            format_func=lambda x: interval_labels.get(x, f"{x} phút"),
        )
        c1, c2 = st.columns(2)
        if c1.form_submit_button("💾 Lưu", use_container_width=True):
            db.table("app_settings").update(
                {
                    "enabled": enabled,
                    "interval_minutes": interval,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", s["id"]).execute()
            st.success("✅ Đã lưu")
            st.rerun()
        if c2.form_submit_button(
            "🔄 Reset 'Lần chạy cuối'", use_container_width=True
        ):
            db.table("app_settings").update({"last_run_at": None}).eq(
                "id", s["id"]
            ).execute()
            st.success("✅ Đã reset, lần ping kế tiếp sẽ chạy ngay")
            st.rerun()

    st.markdown("---")
    st.subheader("🚂 Hướng dẫn deploy Railway")

    st.markdown(
        """
    Project đã sẵn sàng cho Railway. Setup 1 lần như sau:

    **1. Tạo project trên [railway.app](https://railway.app)**
    - Login → **New Project** → **Deploy from GitHub repo**
    - Chọn repo `auto-facebook-post` → Railway auto-build từ `Dockerfile`

    **2. Set Variables (Settings → Variables) cho service `web`:**
    ```
    SUPABASE_URL=https://xxx.supabase.co
    SUPABASE_KEY=eyJhbGc...
    DB_BACKEND=supabase
    PORT=8501
    ```

    **3. Tạo cron service (đăng định kỳ):**
    - Trong cùng project → **+ Create** → **GitHub Repo** → chọn lại repo
    - Settings → **Start Command**: `python -m src.main_scrape`
    - Settings → **Cron Schedule**: `*/15 * * * *` (chạy mỗi 15 phút)
    - Settings → **Variables**: copy 3 var trên (hoặc dùng "Reference Variable")
    - **Networking**: tắt public domain (cron không cần expose)

    **4. Cấu hình lịch ngay tại đây ↑**
    - Bật **Auto-run**
    - Chọn interval (vd 8 giờ)
    - Cron service ping mỗi 15 phút, đọc bảng này. Đến giờ thì chạy thật,
      chưa đến thì skip ngay (tốn ~3s mỗi lần check).

    **Lưu ý:**
    - Nút **🚀 Chạy ngay** ở page "Chạy Scrape" set `FORCE_RUN=1` → bypass
      check settings, chạy luôn (dùng để test).
    - `FORCE_RUN=1` còn dùng được khi gọi `python -m src.main_scrape` từ CLI
      hoặc GH Actions workflow_dispatch.
    """
    )
