#!/bin/bash
# ============================================================
# Chạy Admin Panel trên mạng nội bộ (local network)
# Truy cập từ bất kỳ thiết bị nào trong cùng WiFi
# ============================================================

set -e

# Màu sắc terminal
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Lấy IP local
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null \
        || ipconfig getifaddr en1 2>/dev/null \
        || hostname -I 2>/dev/null | awk '{print $1}' \
        || echo "localhost")

PORT=8501

echo ""
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo -e "${CYAN}   Auto Facebook Post - Admin Panel${NC}"
echo -e "${CYAN}══════════════════════════════════════════${NC}"

# Kiểm tra .env
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  Chưa có file .env!${NC}"
    echo "   Sao chép từ .env.example và điền thông tin:"
    echo "   cp .env.example .env"
    exit 1
fi

# Cài dependencies nếu chưa có
if ! python -c "import streamlit" 2>/dev/null; then
    echo "📦 Cài đặt dependencies..."
    pip install -r requirements.txt -q
fi

echo ""
echo -e "${GREEN}✅ Truy cập Admin Panel tại:${NC}"
echo ""
echo -e "   Máy này:          ${CYAN}http://localhost:${PORT}${NC}"
echo -e "   Các thiết bị khác: ${CYAN}http://${LOCAL_IP}:${PORT}${NC}"
echo -e "   (điện thoại, máy tính bảng cùng WiFi)"
echo ""
echo "   Nhấn Ctrl+C để dừng"
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo ""

# Chạy Streamlit lắng nghe tất cả interfaces (0.0.0.0)
streamlit run admin/app.py \
    --server.address 0.0.0.0 \
    --server.port $PORT \
    --server.headless true \
    --browser.gatherUsageStats false \
    --theme.primaryColor "#1877F2" \
    --theme.backgroundColor "#ffffff" \
    --theme.secondaryBackgroundColor "#f0f2f6" \
    --theme.textColor "#262730"
