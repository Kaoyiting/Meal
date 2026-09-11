# Order Service Dockerfile - 兩階段建構
# 第一階段：建構依賴項和編譯環境
FROM python:3.11-slim as builder

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴項（建構時需要）
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴文件
COPY requirements.txt .

# 安裝 Python 依賴項到臨時目錄
RUN pip install --no-cache-dir --user -r requirements.txt

# 第二階段：運行環境
FROM python:3.11-slim

# 建立非 root 使用者
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 設定工作目錄
WORKDIR /app

# 安裝運行時依賴項（僅 PostgreSQL 客戶端）
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 從建構階段複製已安裝的 Python 套件
COPY --from=builder /root/.local /home/appuser/.local

# 確保 Python 套件在 PATH 中
ENV PATH=/home/appuser/.local/bin:$PATH

# 複製應用程式代碼
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# 設定權限
RUN chown -R appuser:appuser /app

# 切換到非 root 使用者
USER appuser

# 設定環境變數
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露埠號
EXPOSE 8000

# 健康檢查
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# 啟動命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]