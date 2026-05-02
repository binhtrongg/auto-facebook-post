FROM python:3.11-slim

WORKDIR /app

# Cài dependencies hệ thống (curl cho healthcheck, ffmpeg cho yt-dlp)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy và cài Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ source code
COPY . .

# Mặc định 8501 cho local; Railway sẽ override bằng $PORT
ENV PORT=8501
EXPOSE 8501

# Healthcheck dùng env $PORT (work cho cả local và Railway)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/_stcore/health || exit 1

# Shell form để $PORT được expand bởi shell tại runtime
CMD streamlit run admin/app.py \
    --server.address 0.0.0.0 \
    --server.port ${PORT} \
    --server.headless true \
    --browser.gatherUsageStats false
