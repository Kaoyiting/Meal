# 訂單服務設計文件

## 一、系統總覽

本系統採用微服務架構設計，Order Service 負責訂單處理、狀態管理和歷史查詢功能。

**技術棧概覽**：
- **後端框架**：FastAPI
- **資料庫**：PostgreSQL 15
- **訊息佇列**：RabbitMQ
- **容器化**：Docker + Docker Compose

> **📋 詳細的技術架構設計請參考：[Architecture.md](./Architecture.md)**

## 二、服務模組

* **Auth Service (認證服務)**：用戶註冊、登入、授權
* **Menu Service (菜單服務)**：菜單管理、餐點資訊維護
* **Order Service (訂單服務)**：點餐處理、訂單管理、歷史查詢、賒帳分錄
* **Rating Service (評價服務)**：顧客評價管理
* **Report Service (報表服務)**：報表生成、統計分析、對帳管理（彙總跨服務事件資料，提供管理面報表與對帳日結）
* **Notification Service (通知服務)**：系統通知、郵件推送、事件處理（訂單狀態更新、逾時提醒、對帳結果）

## 三、Order Service 職責

* 處理員工點餐請求
* 訂單狀態管理（Saga Orchestration）
* 訂單歷史查詢
* 訂單取消功能（時限內）
* 訂單統計（管理員）

## 四、Order Service API

* **POST /orders**：建立新訂單（UC-04 員工點餐）
* **GET /orders/history**：查詢歷史訂單（UC-05 員工歷史查詢）
* **GET /orders/{order_id}**：查詢單筆訂單
* **PUT /orders/{order_id}/cancel**：取消訂單（時限內，含補償流程）
* **GET /orders/statistics**：查詢統計（UC-16 管理員統計）
* **GET /orders/summary**：**月底結帳用的總和 API**，輸出每個 `userId` 的訂單合計與該使用者的訂單明細彙整，支援指定月份或日期區間。
* **GET /orders/user/{userId}**：依使用者 ID 查詢該用戶所有訂單紀錄（可加期間條件），回傳完整的消費明細（訂單編號、日期、金額、狀態、項目）。

### 4.1 GET /orders/summary（月底結帳）

**用途**：生成月底結帳報表；管理員使用。

**Query 參數**

* `month`（可選）：`YYYY-MM`，與 `from`/`to` 互斥。若提供則自動展開為該月第一天與最後一天。
* `from` / `to`（可選）：`YYYY-MM-DD`，若未提供則預設為本月。**限制：`from` 必須早於或等於 `to`**。
* `includeDetails`（可選，布林，預設 `false`）：是否回傳每位使用者的訂單清單（僅必要時開啟，避免負載過大）。
* `page`/`pageSize`（可選）：當 `includeDetails=true` 時可分頁細項。

**回應範例**

```json
{
  "period": {"from": "2025-07-01", "to": "2025-07-31"},
  "users": [
    {
      "userId": 456,
      "userName": "王小明",
      "orderCount": 12,
      "totalAmount": 1800,
      "records": [
        {"orderId": "...","orderDate": "2025-07-03","amount": 150,"status": "COMPLETED"}
      ]
    }
  ],
  "grandTotal": {"orderCount": 120, "totalAmount": 17850}
}
```

**SQL（PostgreSQL）**

* 使用期間聚合（僅總表）：

```sql
SELECT user_id,
       COUNT(*) AS order_count,
       COALESCE(SUM(total_amount),0) AS total_amount
FROM orders
WHERE order_date BETWEEN :from AND :to
  AND status IN ('ON_CREDIT','COMPLETED')
GROUP BY user_id
ORDER BY total_amount DESC;
```

* 取得單一使用者明細（配合 includeDetails）：

```sql
SELECT o.id AS order_id, o.user_id, o.order_date, o.total_amount, o.status,
       json_agg(json_build_object('menuItemId', oi.menu_item_id, 'qty', oi.quantity, 'price', oi.unit_price)) AS items
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.order_date BETWEEN :from AND :to
  AND o.status IN ('ON_CREDIT','COMPLETED')
GROUP BY o.id, o.user_id
ORDER BY o.order_date DESC, o.created_at DESC
LIMIT :limit OFFSET :offset;
```

**備註**

* 權限：管理員。
* 索引：`idx_orders_user_date (user_id, order_date)` 已涵蓋查詢；聚合可再加 `order_date` 單欄索引。
* 對帳：可直接輸出 CSV/PDF 給財務；同時可發 `reports.monthly.generated` 事件讓 Report Service 做快取。

### 4.2 GET /orders/user/{userId}

**用途**：查詢特定使用者的所有訂單紀錄；員工查自己、管理員可查任意員工。

**Query 參數**

* `from` / `to`（可選）：`YYYY-MM-DD`；未提供則預設近 90 天。**限制：`from` 必須早於或等於 `to`**。
* `status`（可選）：多值，例如 `status=COMPLETED,ON_CREDIT`。
* `page`/`pageSize`（可選）：分頁。

**回應範例**

```json
{
  "userId": 456,
  "period": {"from": "2025-05-01", "to": "2025-07-31"},
  "orders": [
    {
      "orderId": "...",
      "orderDate": "2025-07-28",
      "status": "COMPLETED",
      "totalAmount": 150,
      "items": [
        {"menuItemId": 501, "quantity": 2, "unitPrice": 75}
      ]
    }
  ]
}
```

**SQL（PostgreSQL）**

```sql
SELECT o.id AS order_id, o.order_date, o.total_amount, o.status,
       json_agg(json_build_object('menuItemId', oi.menu_item_id, 'qty', oi.quantity, 'price', oi.unit_price)) AS items
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.user_id = :user_id
  AND o.order_date BETWEEN :from AND :to
  AND (:status IS NULL OR o.status = ANY(string_to_array(:status, ',')::text[]))
GROUP BY o.id
ORDER BY o.order_date DESC, o.created_at DESC
LIMIT :limit OFFSET :offset;
```

**權限**

* 員工：僅能查 `userId == 自己` 的資料。
* 管理員：可查任意使用者（配合 RBAC）。

## 五、資料模型概覽

Order Service 使用以下核心資料表：

- **orders**：訂單主表，儲存訂單基本資訊和狀態
- **order_items**：訂單項目明細，儲存餐點詳情
- **outbox**：事件發布表，實現 Outbox Pattern
- **saga_steps**：Saga 步驟追蹤表，支援分散式事務

**設計原則**：
- 支援微服務鬆耦合（無跨服務外鍵約束）
- 樂觀鎖控制併發
- 軟刪除保留歷史
- 事件驅動架構

> **📋 詳細的資料表結構、DDL、索引設計請參考：[ERD.md](./ERD.md)**

## 六、Saga 模式與一致性策略

**基本概念**：
- 採用 **Orchestration（指揮型）Saga**：由 Order Service 作為協調器
- 透過事件驅動確保跨服務的最終一致性
- 支援補償機制處理失敗場景

**核心流程**：
1. 建立訂單 → 庫存預留 → 賒帳記錄 → 確認庫存 → 完成訂單
2. 任一步驟失敗時啟動補償流程（釋放庫存、沖銷記錄等）

> **📋 詳細的 Saga 技術實現、事件流程、配置參數請參考：[Architecture.md 第五章](./Architecture.md#五saga-流程說明)**

## 七、庫存驗證策略

* 採用 **預留（Reservation）+ TTL**：

  * Order Service 發 `inventory.reserve.requested`（含 `reservationId`, `ttlSeconds`）。
  * Inventory Service 以 **原子 SQL** 更新預留；所有品項都成功才回 `confirmed`。
  * TTL 到期或取消訂單 → 自動釋放。
* **SQL 原子更新**：

  ```sql
  UPDATE stocks
  SET reserved = reserved + :qty,
      version  = version + 1
  WHERE menu_item_id = :menu_item_id
    AND (on_hand - reserved) >= :qty;
  ```
* **設定建議（Inventory Settings）**：

  * `ttlSeconds`：600（10 分鐘，可依餐廳 SLA 調整）
  * 預留掃描器：每分鐘掃描 `expires_at < now()`，批次釋放 `maxBatch=500`。
  * 併發控制：以 `menu_item_id` 分片處理，避免同品項搶鎖。
  * 釋放策略：逐項回滾已預留的數量，確保不超賣。


## 八、Use Case 對應

### UC-04 員工點餐

* API：POST /orders
* 流程：瀏覽菜單 → 選擇餐點 → 提交 → 系統寫入訂單並發送 `order.created`

### UC-05 員工查詢歷史訂餐紀錄

* API：GET /orders/history
* 條件：登入後可查詢 → 預設顯示本月 → 支援篩選

### UC-16 管理員查詢訂單統計

* API：GET /orders/statistics
* 流程：輸入日期範圍 → 系統計算數量、金額、熱門餐點排行

## 九、訂單取消規則

### 取消條件

* **時間限制**：建立後 10 分鐘內（以 UTC 時間計算）
* **狀態限制**：狀態必須不是 COMPLETED

### API 介面

* **請求**：PUT /orders/{order_id}/cancel
* **驗證**：JWT 認證，必須是訂單擁有者
* **成功回應**：200 OK，返回更新後的訂單資訊
* **錯誤回應**：
  - 400：CANCELLATION_TIME_EXPIRED（超過10分鐘）
  - 404：ORDER_NOT_FOUND（訂單不存在）
  - 403：ACCESS_DENIED（非訂單擁有者）

### 取消流程

1. **驗證權限**：確認用戶為訂單擁有者
2. **檢查時間**：計算訂單建立時間與當前時間差異
3. **更新狀態**：訂單狀態轉為 CANCELLED
4. **發送事件**：
   - `inventory.release.requested`（釋放庫存）
   - 若已過帳 → `ar.reverse.requested`（會計沖銷）

### 時間計算邏輯

```python
# 使用 UTC 時間進行比較
time_diff = datetime.now(timezone.utc) - order.created_at
if time_diff > timedelta(minutes=10):
    raise CancellationTimeExpiredError()
```

## 十、可靠性與觀測性

* **Outbox Pattern**：確保事件與本地交易一致
* **冪等性**：事件消費者以 `sagaId+eventType` 去重；API 端以 `Idempotency-Key`
* **重試與補償**：每步驟支援重試，超過次數走補償
* **死信佇列 (DLQ)**：異常事件集中處理
* **監控**：Prometheus + Grafana，追蹤 Saga 成功率、補償率、延遲；

## 十二、Event-Driven（事件驅動）架構說明

**定義**：以「事件」為一等公民的系統設計；服務只需對「發生了什麼」作出反應，而不必彼此直接呼叫。

**優點**：鬆耦合、可擴充、可觀測（事件即審計軌跡）、對尖峰彈性好。

**在本系統的使用場景**：

* **跨服務工作流**：Order ←→ Inventory ←→ AR 由事件串接（即 Saga）。
* **報表/對帳（Report Service）**：訂閱所有業務事件，做即時彙總（訂單數、營收、熱門餐點），並輸出對帳報表。
* **通知（Notification Service）**：訂閱 `order.*`、`inventory.*`、`ar.*` 事件，推送 Email/訊息（下單成功、預留失敗、逾時釋放、完成/取消）。
* **審計與追蹤**：事件流可直接作為審計證據，配合 `traceId/sagaId` 做端到端追蹤。

**常見處理類型**：

* **Streaming ETL/聚合**：以消費者累加統計、生成 Top-N 排行。
* **時間窗檢測**：TTL/逾時掃描、異常檢測。
* **補償/回滾**：接到失敗事件後啟動反向操作。

**技術建議**：
* Report Service 可維護一個 **read model**（如 ClickHouse/TimescaleDB 或 PostgreSQL 物化檢視），以事件驅動更新；API 直接查 read model，避免重掃交易表。
* Notification Service 採用 **模板化**（如 Jinja2）與 **節流/去重策略**，避免事件風暴時過度通知。

---
