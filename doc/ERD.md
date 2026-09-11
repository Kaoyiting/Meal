# Order Service 資料庫實體關聯圖 (ERD)

## 文件資訊

**專案名稱**：訂單服務系統 (Order Service)  
**文件版本**：v1.0  
**建立日期**：2025-09-28  
**適用範圍**：Order Service 資料庫設計  
**資料庫**：PostgreSQL 15  

## 一、資料庫概覽

Order Service 資料庫包含 4 個核心資料表，支援 Saga 模式、分散式事件驅動架構、Outbox Pattern 與補償機制，確保訂單處理的最終一致性。

### 核心資料表

1. **orders** - 訂單主表
2. **order_items** - 訂單項目明細
3. **outbox** - 事件發布表 (Outbox Pattern)
4. **saga_steps** - Saga 步驟追蹤表  

## 二、實體關聯圖

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Order Service Database                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────┐    1:N     ┌─────────────────────────┐
│        orders           │───────────▶│      order_items        │
│─────────────────────────│            │─────────────────────────│
│ 🔑 id (UUID)            │            │ 🔑 id (UUID)            │
│    user_id (BIGINT)     │            │ 🔗 order_id (UUID) FK   │
│    menu_id (BIGINT)     │            │    menu_item_id (BIGINT)│
│    total_amount (INT)   │            │    menu_item_name (100) │
│    status (TEXT)        │            │    quantity (INT)       │
│    notes (TEXT)         │            │    unit_price (INT)     │
│    order_date (DATE)    │            │    subtotal (INT) ⚡     │
│    saga_id (UUID) 🔄    │            │    created_at (TIMESTAMPTZ) │
│    reservation_id (UUID)│            └─────────────────────────┘
│    cancellation_reason  │
│    version (INT) 🔒     │
│    created_at           │
│    updated_at           │
│    is_deleted (BOOLEAN) │
└─────────────────────────┘

┌─────────────────────────┐            ┌─────────────────────────┐
│        outbox           │            │      saga_steps         │
│─────────────────────────│            │─────────────────────────│
│ 🔑 id (UUID)            │            │ 🔑 id (UUID)            │
│    aggregate_id (UUID)  │            │    saga_id (UUID) 🔄    │
│    event_type (TEXT)    │            │    step (TEXT)          │
│    payload (JSONB) 📝   │            │    state (TEXT)         │
│    published (BOOLEAN)  │            │    payload (JSONB) 📝   │
│    created_at           │            │    retry_count (INT)    │
└─────────────────────────┘            │    created_at           │
                                       │    updated_at           │
                                       └─────────────────────────┘

圖例：
🔑 主鍵 (Primary Key)
🔗 外鍵 (Foreign Key)  
⚡ 計算欄位 (Generated Column)
🔒 樂觀鎖版本
🔄 Saga 流程 ID
📝 JSON 資料
```

## 三、資料表結構詳細說明

### 3.1 orders 表 - 訂單主表

**用途**：儲存訂單的基本資訊，是整個訂單處理流程的核心

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL,           -- 下單用戶ID (來自 Auth Service)
    menu_id BIGINT NOT NULL,           -- 菜單ID (來自 Menu Service)
    total_amount INTEGER NOT NULL,     -- 總金額(以元為單位，例如：120表示120元)
    status TEXT NOT NULL,              -- 訂單狀態
    notes TEXT,                        -- 使用者備註 (最多500字元)
    order_date DATE NOT NULL,          -- 訂單日期 (用於報表查詢)
    saga_id UUID NOT NULL,             -- Saga流程追蹤ID
    reservation_id UUID,               -- 庫存預留ID (對應 Inventory Service)
    cancellation_reason TEXT,          -- 取消原因 (可選)
    version INT NOT NULL DEFAULT 1,    -- 樂觀鎖版本控制
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_deleted BOOLEAN DEFAULT FALSE   -- 軟刪除標記
);

-- 狀態約束檢查
ALTER TABLE orders ADD CONSTRAINT chk_status 
CHECK (status IN ('PENDING','INVENTORY_RESERVED','ON_CREDIT','COMPLETED','CANCELLED'));

-- 金額必須為正數
ALTER TABLE orders ADD CONSTRAINT chk_total_amount_positive
CHECK (total_amount > 0);
```

#### 訂單狀態說明

> **📋 詳細的訂單狀態說明、財務邏輯、常見查詢場景請參考：[API_Requirements.md 第2.2節](./API_Requirements.md#22-查詢歷史訂單)**

**簡要說明：**

| 狀態 | 說明 | 業務意義 |
|------|------|----------|
| `PENDING` | 訂單剛建立 | 等待庫存檢查 |
| `INVENTORY_RESERVED` | 庫存已預留 | 準備進行賒帳處理 |
| `ON_CREDIT` | 賒帳已記錄 | 餐點製作中/等待取餐，會從薪水扣款 |
| `COMPLETED` | 訂單完成 | 餐點已交付，確定從薪水扣款 |
| `CANCELLED` | 訂單取消 | 不會從薪水扣款 |

#### 重要欄位說明

- **saga_id**: 用於追蹤整個分散式交易流程，與 `saga_steps` 表關聯
- **reservation_id**: 庫存預留的唯一識別碼，用於與 Inventory Service 通訊
- **version**: 樂觀鎖版本號，防止並發更新衝突
- **total_amount**: 以元為單位儲存，例如：300表示300元

### 3.2 order_items 表 - 訂單項目明細

**用途**：儲存訂單中每個餐點的詳細資訊

```sql
CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    menu_item_id BIGINT NOT NULL,      -- 餐點ID (來自 Menu Service)
    menu_item_name VARCHAR(100) NOT NULL, -- 餐點名稱 (冗餘儲存，提升查詢性能)
    quantity INT NOT NULL,             -- 數量
    unit_price INTEGER NOT NULL,       -- 單價 (以元為單位，例如：120表示120元)
    -- subtotal 透過應用程式層計算 (quantity * unit_price)，避免資料庫複雜性
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 數量必須為正數
ALTER TABLE order_items ADD CONSTRAINT chk_quantity_positive
CHECK (quantity > 0);

-- 單價必須為正數
ALTER TABLE order_items ADD CONSTRAINT chk_unit_price_positive
CHECK (unit_price > 0);
```

#### 設計特點

- **冗餘儲存餐點名稱**: 避免頻繁跨服務查詢，提升歷史訂單查詢性能
- **應用程式層計算**: `subtotal` 透過 Python 屬性動態計算 (quantity * unit_price)，避免資料庫層複雜性，提升可維護性
- **級聯刪除**: 當訂單被刪除時，相關項目自動刪除

### 3.3 outbox 表 - 事件發布表

**用途**：實現 Outbox Pattern，確保資料庫操作與事件發布的原子性

```sql
CREATE TABLE outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_id UUID NOT NULL,        -- 聚合根ID (通常是 order_id)
    event_type TEXT NOT NULL,          -- 事件類型
    payload JSONB NOT NULL,            -- 事件內容 (JSON格式)
    published BOOLEAN DEFAULT FALSE,   -- 是否已發布到訊息佇列
    created_at TIMESTAMPTZ DEFAULT now()
);
```

#### 常見事件類型

| 事件類型 | 觸發時機 | 事件內容 |
|----------|----------|----------|
| `order.created` | 訂單建立 | 訂單基本資訊 + 項目清單 |
| `inventory.reserve.requested` | 請求預留庫存 | 預留ID + 項目清單 + TTL |
| `ar.post.requested` | 請求賒帳記錄 | 使用者ID + 金額 + 訂單資訊 |
| `inventory.commit.requested` | 確認使用庫存 | 預留ID + 訂單完成確認 |
| `order.cancelled` | 訂單取消 | 訂單ID + 取消原因 |

#### Payload 範例

```json
{
  "eventType": "order.created",
  "timestamp": "2025-09-28T10:30:15Z",
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "userId": 123,
  "sagaId": "660f9500-f39c-52e5-b827-557766551111",
  "items": [
    {
      "menuItemId": 501,
      "quantity": 2,
      "unitPrice": 150
    }
  ],
  "totalAmount": 300,
  "reservationId": "770fa600-g40d-63f6-c938-668877662222"
}
```

**金額說明**：
- `unitPrice: 150` = 150元 (單價)
- `totalAmount: 300` = 300元 (2個×150元 = 300元)

### 3.4 saga_steps 表 - Saga 步驟追蹤

**用途**：追蹤 Saga 流程中每個步驟的執行狀態，支援補償機制

```sql
CREATE TABLE saga_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    saga_id UUID NOT NULL,             -- Saga 流程ID
    step TEXT NOT NULL,                -- 步驟名稱
    state TEXT NOT NULL,               -- 步驟狀態
    payload JSONB,                     -- 步驟相關資料
    retry_count INT DEFAULT 0,         -- 重試次數
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 狀態約束檢查
ALTER TABLE saga_steps ADD CONSTRAINT chk_state 
CHECK (state IN ('PENDING','DONE','COMPENSATED','FAILED'));

-- 重試次數不能為負數
ALTER TABLE saga_steps ADD CONSTRAINT chk_retry_count_non_negative
CHECK (retry_count >= 0);
```

#### Saga 步驟說明

| 步驟名稱 | 說明 | 成功狀態 | 補償動作 |
|----------|------|----------|----------|
| `CREATE_ORDER` | 建立訂單 | `DONE` | 標記為已取消 |
| `RESERVE_INVENTORY` | 預留庫存 | `DONE` | 釋放預留庫存 |
| `POST_AR` | 建立賒帳記錄 | `DONE` | 沖銷賒帳記錄 |
| `COMMIT_INVENTORY` | 確認庫存使用 | `DONE` | 恢復庫存 |
| `COMPLETE_ORDER` | 完成訂單 | `DONE` | 回復為進行中狀態 |

#### 步驟狀態說明

- **PENDING**: 步驟等待執行
- **DONE**: 步驟執行成功
- **COMPENSATED**: 步驟已執行補償動作
- **FAILED**: 步驟執行失敗，無法補償

## 四、索引設計

### 4.1 查詢優化索引

```sql
-- 訂單查詢優化
CREATE INDEX idx_orders_user_date ON orders (user_id, order_date DESC);
CREATE INDEX idx_orders_status ON orders (status);
CREATE INDEX idx_orders_saga ON orders (saga_id);
CREATE INDEX idx_orders_created_at ON orders (created_at DESC);

-- 訂單項目查詢優化
CREATE INDEX idx_order_items_order_id ON order_items (order_id);
CREATE INDEX idx_order_items_menu_item ON order_items (menu_item_id);

-- 事件處理優化
CREATE INDEX idx_outbox_unpublished ON outbox (created_at ASC) 
WHERE published = false;

-- Saga 追蹤優化
CREATE INDEX idx_saga_steps_saga_id ON saga_steps (saga_id, step);
CREATE INDEX idx_saga_steps_state ON saga_steps (state, created_at);
```

### 4.2 索引使用場景

| 索引名稱 | 主要用途 | 對應 API |
|----------|----------|----------|
| `idx_orders_user_date` | 用戶歷史查詢 | `GET /orders/history` |
| `idx_orders_status` | 狀態篩選查詢 | `GET /orders/statistics` |
| `idx_outbox_unpublished` | 事件發布器掃描 | 背景服務 |
| `idx_saga_steps_saga_id` | Saga 流程追蹤 | Saga 協調器 |

## 五、資料一致性保證

### 5.1 ACID 特性保證

#### 原子性 (Atomicity)
- 每個業務操作在單一交易中完成
- 使用 PostgreSQL 的交易機制確保全部成功或全部失敗

#### 一致性 (Consistency)
- 透過約束條件確保資料正確性
- 外鍵約束維護表間關聯完整性
- CHECK 約束驗證業務規則

#### 隔離性 (Isolation)
- 使用樂觀鎖 (`version` 欄位) 處理並發更新
- READ COMMITTED 隔離級別避免髒讀

#### 持久性 (Durability)
- PostgreSQL 的 WAL 日誌確保資料持久化
- 定期備份防止資料遺失

### 5.2 分散式一致性

#### Saga Pattern
```sql
-- 樂觀鎖更新範例
UPDATE orders 
SET status = 'INVENTORY_RESERVED', 
    version = version + 1,
    updated_at = now()
WHERE id = ? AND version = ?;
```

#### Outbox Pattern
```sql
-- 原子性寫入訂單和事件
BEGIN;
  INSERT INTO orders (...) VALUES (...);
  INSERT INTO outbox (aggregate_id, event_type, payload) 
  VALUES (?, 'order.created', ?);
COMMIT;
```

## 六、報表服務整合

### 6.1 基本統計查詢

為支援報表服務 (Report Service)，提供基本的訂單統計查詢功能：

#### 每日訂單統計
```sql
-- 每日訂單數量和平均金額
SELECT 
    order_date,
    COUNT(*) as daily_order_count,
    AVG(total_amount) as average_amount,
    SUM(total_amount) as total_amount
FROM orders 
WHERE status IN ('ON_CREDIT', 'COMPLETED')
  AND order_date >= :start_date 
  AND order_date <= :end_date
GROUP BY order_date
ORDER BY order_date;
```

#### 月度統計匯總
```sql
-- 月度統計，供報表服務使用
SELECT 
    DATE_TRUNC('month', order_date) as month,
    COUNT(*) as monthly_order_count,
    AVG(total_amount) as average_amount,
    SUM(total_amount) as total_amount
FROM orders 
WHERE status IN ('ON_CREDIT', 'COMPLETED')
  AND order_date >= :start_date 
  AND order_date <= :end_date
GROUP BY DATE_TRUNC('month', order_date)
ORDER BY month;
```

### 6.2 事件驅動報表更新

透過事件發布讓報表服務即時更新統計資料：

#### 訂單完成事件
```json
{
  "eventType": "order.completed",
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "userId": 123,
  "orderDate": "2025-09-28",
  "totalAmount": 300,
  "timestamp": "2025-09-28T10:30:15Z"
}
```

#### 訂單取消事件
```json
{
  "eventType": "order.cancelled",
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "userId": 123,
  "orderDate": "2025-09-28",
  "reason": "customer_request",
  "timestamp": "2025-09-28T10:35:20Z"
}
```

**說明**：報表服務可以訂閱這些事件，即時更新統計數據，無需定期查詢 Order Service 資料庫。

---

## 文件版本控制

| 版本 | 日期 | 變更內容 | 作者 |
|------|------|----------|------|
| v1.0 | 2025-09-28 | 初始 ERD 設計 | 架構師 |

---

**備註**：本 ERD 文件基於 PostgreSQL 15 設計，支援 Order Service 的完整業務流程，包括 Saga 模式、Outbox Pattern 和分散式事件驅動架構。