# Order Service 架構設計文件

## 文件資訊

**專案名稱**：訂單服務系統 (Order Service)  
**架構版本**：v1.0  
**建立日期**：2025-09-28  
**適用範圍**：Order Service 模組  

## 一、服務範圍說明

### 1.1 系統服務架構

整個訂餐系統包含 6 個服務：

- **Auth Service**：用戶註冊、登入、授權
- **Menu Service**：菜單管理、餐點資訊維護
- **Order Service**：點餐處理、訂單管理、歷史查詢、賒帳分錄
- **Rating Service**：顧客評價管理
- **Report Service**：報表生成、統計分析、對帳管理
- **Notification Service**：系統通知、郵件推送、事件處理

### 1.2 Order Service 負責什麼

**✅ 我們負責的功能**：
- 處理員工點餐請求
- 管理訂單狀態（從下單到完成）
- 協調其他服務（庫存檢查、記帳）
- 提供訂單歷史查詢
- 處理訂單取消
- 提供基本統計資料

**❌ 我們不負責的功能**：
- 用戶登入驗證（Auth Service 負責）
- 菜單資料管理（Menu Service 負責）
- 實際庫存管理（系統外部或其他服務）
- 複雜報表生成（Report Service 負責）
- 發送通知訊息（Notification Service 負責）

## 二、基本架構設計

### 2.1 支援分散式事務的架構

```
┌─────────────────────────────────────────────────────────┐
│                   Order Service                         │
├─────────────────────────────────────────────────────────┤
│  API 層 (FastAPI)                                       │  ← HTTP 請求處理
│  - 接收請求、驗證參數、回傳結果                         │
├─────────────────────────────────────────────────────────┤
│  業務邏輯層                                             │  ← 核心業務處理
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │訂單管理服務 │  │ Saga協調器  │  │事件處理器   │     │
│  │- 建立訂單   │  │- 流程控制   │  │- 事件消費   │     │
│  │- 狀態更新   │  │- 補償處理   │  │- 狀態同步   │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
├─────────────────────────────────────────────────────────┤
│  資料存取層                                             │  ← 資料庫操作
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │訂單倉儲     │  │事件發布器   │  │Saga倉儲     │     │
│  │- 訂單CRUD   │  │- Outbox模式 │  │- 步驟追蹤   │     │
│  │- 樂觀鎖     │  │- 可靠發布   │  │- 補償記錄   │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────┘
            │                              │
            ▼                              ▼
┌─────────────────────────────────────┐    ┌─────────────────┐
│        PostgreSQL 資料庫            │    │    RabbitMQ     │
│  orders | order_items | outbox     │    │  事件訊息佇列    │
│         | saga_steps               │    │  - 事件發布      │
│                                     │    │  - 事件消費      │
│  🔒 樂觀鎖控制                      │    │  - 重試機制      │
│  📝 Outbox Pattern                  │    └─────────────────┘
│  🔄 Saga 步驟追蹤                   │
└─────────────────────────────────────┘
```

### 2.2 技術選擇

- **後端框架**：FastAPI（Python）
- **資料庫**：PostgreSQL 15
- **快取**：Redis 7.x
- **訊息佇列**：RabbitMQ
- **認證**：JWT Token
- **容器化**：Docker

## 三、API 設計

### 3.1 API 端點列表

```python
# 訂單管理
POST   /orders              # 建立新訂單
GET    /orders/history      # 查詢歷史訂單
GET    /orders/{id}         # 查詢單筆訂單
PUT    /orders/{id}/cancel  # 取消訂單

# 統計查詢
GET    /orders/statistics   # 查詢統計
GET    /orders/summary      # 月底結帳用的總和
GET    /orders/user/{userId} # 查詢特定用戶訂單
```

### 3.2 API 設計原則

#### **RESTful 設計**
- 使用標準 HTTP 方法（GET, POST, PUT, DELETE）
- 資源導向的 URL 設計
- 統一的回應格式和錯誤處理

#### **認證與授權**
- JWT Token 認證
- 角色基礎權限控制（員工/管理員）
- 資源級別權限檢查

#### **API 回應格式**
- 成功：標準 JSON 格式
- 錯誤：包含錯誤碼和詳細訊息
- 分頁：統一的分頁參數和回應格式

> **📋 完整的 API 規格、請求/回應範例、錯誤處理請參考：[API_Requirements.md](./API_Requirements.md)**

## 四、資料庫設計

### 4.1 資料表概覽

Order Service 使用 PostgreSQL 15 作為主要資料庫，包含以下 4 個核心資料表：

1. **orders** - 訂單主表：儲存訂單基本資訊和狀態
2. **order_items** - 訂單項目明細：儲存每個訂單的餐點詳情
3. **outbox** - 事件發布表：實現 Outbox Pattern 確保事件可靠發布
4. **saga_steps** - Saga 步驟追蹤表：追蹤分散式事務的執行狀態

### 4.2 資料表設計原則

- **UUID 主鍵**：所有表使用 UUID 作為主鍵，支援分散式環境
- **樂觀鎖控制**：訂單表使用 version 欄位防止並發衝突
- **軟刪除設計**：使用 is_deleted 欄位，保留歷史資料
- **審計追蹤**：記錄 created_at、updated_at 時間戳
- **微服務友好**：避免跨服務外鍵約束，維持鬆耦合

> **📋 詳細的資料表結構、DDL 語句、索引設計請參考：[ERD.md](./ERD.md)**

## 五、Saga 流程說明

### 5.1 什麼是 Saga？

**用餐廳比喻**：
想像你在餐廳點餐，服務員要做這些事：
1. 確認廚房有食材
2. 記錄你要付多少錢
3. 告訴廚房開始做菜
4. 完成訂單

如果中間任何一步失敗（比如沒食材），就要取消整個訂單，退還已經預留的東西。

**在我們系統中**：
Saga 就是這樣的流程管理員，確保訂單處理的每個步驟都正確完成，失敗時能自動回復。

### 5.2 訂單處理流程

#### **正常流程**：

```
1. 客人下單
   ↓
2. 檢查庫存（發送訊息給庫存系統）
   ↓ 
3. 庫存足夠，預留食材
   ↓
4. 記帳（記錄這個人要付多少錢）
   ↓
5. 確認庫存（告訴廚房可以開始做）
   ↓
6. 訂單完成
```

#### **失敗處理**：

如果步驟 2 失敗（庫存不足）：
```
1. 客人下單 ✓
2. 檢查庫存 ✗ （沒有足夠食材）
3. 取消訂單
4. 通知客人：「抱歉，今天沒有這道菜了」
```

如果步驟 4 失敗（記帳失敗）：
```
1. 客人下單 ✓
2. 檢查庫存 ✓ 
3. 預留食材 ✓
4. 記帳 ✗ （系統錯誤）
5. 退還預留的食材
6. 取消訂單
7. 通知客人：「系統暫時有問題，請稍後再試」
```

### 5.3 技術實現

#### **狀態轉換**：

```python
PENDING → INVENTORY_RESERVED → ON_CREDIT → COMPLETED
   ↓              ↓              ↓
CANCELLED ← CANCELLED ← CANCELLED
```

#### **事件流程**：

```python
# 1. 建立訂單
order_created_event = {
    "eventType": "order.created",
    "orderId": "uuid",
    "userId": 123,
    "items": [...]
}

# 2. 請求預留庫存
inventory_reserve_requested = {
    "eventType": "inventory.reserve.requested", 
    "reservationId": "uuid",
    "items": [...]
}

# 3. 庫存預留成功
inventory_reserved = {
    "eventType": "inventory.reserved",
    "reservationId": "uuid",
    "success": true
}

# 4. 請求記帳
ar_post_requested = {
    "eventType": "ar.post.requested",
    "userId": 123,
    "amount": 150
}
```

## 六、外部整合策略

### 6.1 我們如何跟其他服務溝通？

**問題**：Order Service 需要跟其他服務協作，但不能直接呼叫它們的 API（避免緊耦合）

**解決方案**：使用「訊息傳遞」方式

#### **就像餐廳的工作流程**：

```
服務員（Order Service）不會直接跑到廚房（Inventory Service）
而是透過「傳菜鈴」（RabbitMQ）傳遞訊息：

服務員 → 按鈴 → "請預留牛肉麵的食材"
廚房 → 按鈴 → "牛肉麵食材已預留" 或 "沒有牛肉了"
服務員 → 收到回應後決定下一步
```

### 6.2 訊息類型

#### **我們發送的訊息**：
- `order.created` - 「有新訂單了」
- `inventory.reserve.requested` - 「請預留這些食材」
- `ar.post.requested` - 「請記帳這筆費用」
- `inventory.commit.requested` - 「確認使用這些食材」

#### **我們接收的訊息**：
- `inventory.reserved` - 「食材已預留」
- `inventory.failed` - 「食材不足」
- `ar.posted` - 「記帳完成」
- `ar.failed` - 「記帳失敗」

### 6.3 訊息可靠性

#### **如何確保訊息不會遺失？**

**Outbox Pattern**（保管箱模式）：
```
1. 儲存訂單到資料庫
2. 同時儲存要發送的訊息到 outbox 表
3. 背景程式定期檢查 outbox 表
4. 發送未發送的訊息到 RabbitMQ
5. 標記訊息為「已發送」
```

**為什麼這樣做？**
- 確保資料庫操作和訊息發送要麼都成功，要麼都失敗
- 即使系統當機，重啟後還能繼續發送未發送的訊息

#### **如何處理重複訊息？**

每個訊息都有唯一ID，收到重複訊息時忽略：
```python
if message_already_processed(message_id):
    return  # 忽略重複訊息
    
process_message(message)
mark_as_processed(message_id)
```

## 七、基本安全性

### 7.1 JWT 認證

#### **什麼是 JWT？**
JWT 就像一張「通行證」，證明你是誰、有什麼權限。

#### **認證流程**：

```
1. 用戶登入 → Auth Service 驗證帳密
2. 驗證成功 → 發給用戶一張 JWT「通行證」
3. 用戶請求 Order API → 出示「通行證」
4. Order Service 檢查「通行證」→ 確認身份和權限
5. 通行證有效 → 處理請求
6. 通行證無效/過期 → 拒絕請求
```

#### **實作方式**：

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
import jwt

security = HTTPBearer()

def verify_token(token: str = Depends(security)):
    try:
        # 解析 JWT
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        role = payload.get("role")
        
        if not user_id:
            raise HTTPException(401, "無效的令牌")
            
        return {"user_id": user_id, "role": role}
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "令牌已過期")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "無效的令牌")

# 使用方式
@app.post("/orders")
async def create_order(
    order_data: OrderRequest,
    current_user = Depends(verify_token)
):
    # current_user 包含 user_id 和 role
    pass
```

### 7.2 權限控制

#### **角色定義**：
- **EMPLOYEE**：一般員工，只能操作自己的訂單
- **ADMIN**：管理員，可以查看所有訂單和統計

#### **權限檢查**：

```python
def check_permission(current_user, resource_user_id=None):
    # 管理員可以存取所有資源
    if current_user["role"] == "ADMIN":
        return True
    
    # 員工只能存取自己的資源
    if current_user["role"] == "EMPLOYEE":
        if resource_user_id is None:
            return True  # 不需要檢查特定資源
        return current_user["user_id"] == resource_user_id
    
    return False

# 使用範例
@app.get("/orders/user/{user_id}")
async def get_user_orders(
    user_id: int,
    current_user = Depends(verify_token)
):
    if not check_permission(current_user, user_id):
        raise HTTPException(403, "沒有權限存取此資源")
    
    # 處理請求...
```

## 八、基本監控日誌

### 8.1 我們為什麼需要監控？

**想像餐廳經營**：
- 你想知道今天賣了多少餐
- 哪道菜最受歡迎
- 有沒有客人抱怨
- 廚房有沒有出問題

**在系統中**：
- API 被呼叫了多少次
- 哪些功能最常用
- 有沒有錯誤發生  
- 系統運行是否正常

### 8.2 基本日誌記錄

#### **記錄什麼？**

```python
import logging
from datetime import datetime

# 設定日誌格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

@app.post("/orders")
async def create_order(order_data: OrderRequest, current_user = Depends(verify_token)):
    # 記錄請求開始
    logger.info(f"用戶 {current_user['user_id']} 開始建立訂單")
    
    try:
        # 處理訂單
        order = await order_service.create_order(order_data, current_user['user_id'])
        
        # 記錄成功
        logger.info(f"訂單 {order.id} 建立成功，用戶: {current_user['user_id']}, 金額: {order.total_amount}")
        
        return {"orderId": order.id, "status": "success"}
        
    except Exception as e:
        # 記錄錯誤
        logger.error(f"建立訂單失敗，用戶: {current_user['user_id']}, 錯誤: {str(e)}")
        raise HTTPException(500, "訂單建立失敗")
```

#### **日誌內容**：

```
2025-09-28 10:30:15 - order_service - INFO - 用戶 123 開始建立訂單
2025-09-28 10:30:16 - order_service - INFO - 訂單 550e8400-e29b-41d4-a716-446655440000 建立成功，用戶: 123, 金額: 150
2025-09-28 10:35:22 - order_service - ERROR - 建立訂單失敗，用戶: 456, 錯誤: 庫存不足
```

### 8.3 健康檢查

#### **什麼是健康檢查？**
就像醫生定期檢查身體，我們也要定期檢查系統是否健康。

#### **實作方式**：

```python
@app.get("/health")
async def health_check():
    """檢查系統是否正常運作"""
    checks = {}
    
    # 檢查資料庫連線
    try:
        await database.execute("SELECT 1")
        checks["database"] = "OK"
    except Exception as e:
        checks["database"] = f"ERROR: {str(e)}"
    
    # 檢查 Redis 連線
    try:
        await redis.ping()
        checks["redis"] = "OK"
    except Exception as e:
        checks["redis"] = f"ERROR: {str(e)}"
    
    # 判斷整體狀態
    all_ok = all(status == "OK" for status in checks.values())
    
    return {
        "status": "healthy" if all_ok else "unhealthy",
        "timestamp": datetime.now().isoformat(),
        "checks": checks
    }
```

#### **回應範例**：

```json
{
  "status": "healthy",
  "timestamp": "2025-09-28T10:30:15",
  "checks": {
    "database": "OK",
    "redis": "OK" 
  }
}
```

### 8.4 簡單統計

#### **追蹤基本指標**：

```python
from collections import defaultdict
import time

# 簡單的記數器
stats = {
    "orders_created": 0,
    "orders_cancelled": 0,
    "api_calls": defaultdict(int),
    "errors": 0
}

def track_api_call(endpoint: str):
    """記錄 API 呼叫次數"""
    stats["api_calls"][endpoint] += 1

def track_order_created():
    """記錄訂單建立"""
    stats["orders_created"] += 1

def track_error():
    """記錄錯誤"""
    stats["errors"] += 1

@app.get("/stats")
async def get_stats():
    """取得基本統計"""
    return {
        "orders_created_today": stats["orders_created"],
        "orders_cancelled_today": stats["orders_cancelled"],
        "total_errors": stats["errors"],
        "api_calls": dict(stats["api_calls"])
    }
```

## 九、Docker 部署

### 9.1 Dockerfile

```dockerfile
# 使用 Python 3.11 映像
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 複製需求檔案
COPY requirements.txt .

# 安裝 Python 套件
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式碼
COPY . .

# 設定環境變數
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露 port
EXPOSE 8000

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 啟動應用
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 9.2 Docker Compose

```yaml
version: '3.8'

services:
  # Order Service
  order-service:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://orderuser:orderpass@postgres:5432/orderdb
      - REDIS_URL=redis://redis:6379
      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
      - JWT_SECRET_KEY=your-secret-key-here
    depends_on:
      - postgres
      - redis
      - rabbitmq
    restart: unless-stopped

  # PostgreSQL 資料庫
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=orderdb
      - POSTGRES_USER=orderuser
      - POSTGRES_PASSWORD=orderpass
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    restart: unless-stopped

  # Redis 快取
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

  # RabbitMQ 訊息佇列
  rabbitmq:
    image: rabbitmq:3-management-alpine
    environment:
      - RABBITMQ_DEFAULT_USER=guest
      - RABBITMQ_DEFAULT_PASS=guest
    ports:
      - "5672:5672"   # AMQP port
      - "15672:15672" # Management UI
    restart: unless-stopped

volumes:
  postgres_data:
```

### 9.3 啟動方式

#### **開發環境啟動**：

```bash
# 1. 複製環境變數檔案
cp .env.example .env

# 2. 修改 .env 檔案中的設定

# 3. 啟動所有服務
docker-compose up -d

# 4. 查看日誌
docker-compose logs -f order-service

# 5. 停止服務
docker-compose down
```

#### **環境變數檔案 (.env)**：

```env
# 資料庫設定
DATABASE_URL=postgresql://orderuser:orderpass@localhost:5432/orderdb

# Redis 設定
REDIS_URL=redis://localhost:6379

# RabbitMQ 設定
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# JWT 設定
JWT_SECRET_KEY=your-very-secret-key-change-this-in-production

# 日誌等級
LOG_LEVEL=INFO
```

### 9.4 基本運維指令

```bash
# 查看服務狀態
docker-compose ps

# 重啟特定服務
docker-compose restart order-service

# 查看服務日誌
docker-compose logs order-service

# 進入容器內部
docker-compose exec order-service bash

# 查看資料庫
docker-compose exec postgres psql -U orderuser -d orderdb

# 清理並重新啟動
docker-compose down -v  # 注意：-v 會刪除資料
docker-compose up -d
```

## 十、開發指南

### 10.1 專案結構

初始結構

order-service/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI入口 + 7支API路由
│   ├── models.py         # SQLAlchemy資料模型 (Order, OrderItem, Saga, Outbox)
│   ├── schemas.py        # Pydantic請求/回應模型
│   ├── database.py       # PostgreSQL + Redis 連線和基本操作
│   ├── services.py       # 核心業務邏輯 (訂單處理 + Saga協調)
│   ├── auth.py           # JWT認證和授權
│   ├── messaging.py      # RabbitMQ訊息發布/消費
│   ├── exceptions.py     # 自定義例外類別
│   └── config.py         # 簡單的環境變數設定 + 基本日誌
├── alembic/
│   ├── versions/
│   └── env.py
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── .env.example
├── .gitignore
└── README.md

之後再把它建立成分層結構

order-service/                          ← 專案根目錄
├── app/                                ← Python 應用程式碼目錄
│   ├── __init__.py
│   ├── main.py                         # FastAPI 應用入口
│   ├── models/                         # 資料模型層
│   │   ├── __init__.py
│   │   ├── order.py                    # 訂單相關模型 (orders, order_items)
│   │   ├── saga.py                     # Saga 相關模型 (saga_steps)
│   │   ├── outbox.py                   # 事件發布模型 (outbox)
│   │   └── schemas.py                  # Pydantic 請求/回應模型
│   ├── routers/                        # API 路由層
│   │   ├── __init__.py
│   │   ├── orders.py                   # 訂單相關 API 端點
│   │   └── health.py                   # 健康檢查 API
│   ├── services/                       # 業務邏輯層
│   │   ├── __init__.py
│   │   ├── order_service.py            # 訂單核心業務邏輯
│   │   ├── saga_service.py             # Saga 協調與補償邏輯
│   │   ├── auth_service.py             # JWT 認證與授權邏輯
│   │   └── event_service.py            # 事件發布與消費邏輯
│   ├── repositories/                   # 資料存取層
│   │   ├── __init__.py
│   │   ├── order_repository.py         # 訂單資料庫操作
│   │   ├── saga_repository.py          # Saga 步驟追蹤操作
│   │   └── outbox_repository.py        # 事件發布資料操作
│   └── utils/                          # 工具函數層
│       ├── __init__.py
│       ├── database.py                 # PostgreSQL 連線工具
│       ├── auth.py                     # JWT Token 工具函數
│       ├── rabbitmq.py                 # RabbitMQ 連線工具
│       └── exceptions.py               # 自定義例外處理
├── alembic/                            # 資料庫遷移目錄
│   ├── versions/                       # 遷移版本檔案
│   └── env.py                          # Alembic 環境設定   
├── alembic.ini                     # Alembic 配置檔案
├── docker-compose.yml                  # 🐳 Docker 服務編排
├── Dockerfile                          # 🐳 Docker 映像建構
├── requirements.txt                    # Python 依賴清單
├── .env.example                        # 環境變數範例
├── .gitignore                          # Git 忽略檔案
└── README.md                           # 專案說明文件

**📋 檔案位置說明**：
- **🐳 Docker 檔案**：位於根目錄，管理整個專案的容器化
- **📦 Python 依賴**：`requirements.txt` 在根目錄，供 Dockerfile 使用
- **⚙️ 設定檔案**：`.env.example`, `alembic.ini` 等在根目錄
- **📝 應用程式碼**：在 `app/` 子目錄內，結構清晰分層

### 10.2 啟動開發環境

```bash
# 1. 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 啟動資料庫和相關服務
docker-compose up -d postgres redis rabbitmq

# 4. 執行資料庫遷移
python -m alembic upgrade head

# 5. 啟動開發服務
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 10.3 API 測試

```bash
# 健康檢查
curl http://localhost:8000/health

# 建立訂單 (需要 JWT token)
curl -X POST http://localhost:8000/orders \
  -H "Authorization: Bearer your-jwt-token" \
  -H "Content-Type: application/json" \
  -d '{
    "menuId": 202509,
    "items": [{"menuItemId": 501, "quantity": 2}],
    "notes": "不要辣"
  }'

# 查看 API 文件
# 瀏覽器開啟：http://localhost:8000/docs
```

---

## 文件版本控制

| 版本 | 日期 | 變更內容 | 作者 |
|------|------|----------|------|
| v1.0 | 2025-09-28 | 初始架構設計（簡化版） | 架構師 |

---

**備註**：本架構文件專注於 Order Service 的基本實現，優先確保功能可用性，後續可根據需求逐步優化擴展。