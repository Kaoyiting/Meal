# Order Service API 需求規格書

## 文件資訊

**專案名稱**：訂單服務系統 (Order Service)  
**文件版本**：v1.0  
**建立日期**：2025-09-28  
**作者**：[作者姓名]  
**狀態**：草稿 / 待審核 / 已確認  

## 一、API 總覽

本文件描述 Order Service 的 7 個核心 API 端點，涵蓋訂單的完整生命週期管理，包括建立、查詢、取消以及統計分析功能。

### API 清單

| 序號 | API 端點 | HTTP 方法 | 功能描述 | 使用者角色 |
|------|----------|-----------|----------|------------|
| 1 | `/orders` | POST | 建立新訂單 | 員工 |
| 2 | `/orders/history` | GET | 查詢歷史訂單 | 員工 |
| 3 | `/orders/{id}` | GET | 查詢單筆訂單 | 員工/管理員 |
| 4 | `/orders/{id}/cancel` | PUT | 取消訂單 | 員工/管理員 |
| 5 | `/orders/statistics` | GET | 查詢訂單統計 | 管理員 |
| 6 | `/orders/summary` | GET | 月底結帳總和 | 管理員 |
| 7 | `/orders/user/{userId}` | GET | 查詢用戶訂單 | 員工/管理員 |

## 二、API 詳細規格

### 2.1 建立新訂單

**API 編號**：API-001  
**端點**：`POST /orders`  
**功能描述**：員工下單點餐  
**對應 Use Case**：UC-04 員工點餐  

#### 請求規格

**認證要求**：
- 需要有效的 JWT Token
- 員工角色權限

**Headers**：
```http
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
Idempotency-Key: <unique_key> (可選)
```

**Request Body**：
```json
{
  "menu_id": 123,
  "items": [
    {
      "menu_item_id": 501,
      "menu_item_name": "宮保雞丁",
      "unit_price": 120,
      "quantity": 2
    },
    {
      "menu_item_id": 502,
      "menu_item_name": "白飯",
      "unit_price": 30,
      "quantity": 1
    }
  ],
  "expected_total": 270,
  "notes": "不要辣，飯少一點"
}
```

**欄位說明**：
- `menu_id` (required, integer)：菜單編號，用於訂單查詢和分組
- `items` (required, array)：訂購項目清單，最多20項
  - `menu_item_id` (required, integer)：餐點ID，必須大於0
  - `menu_item_name` (required, string)：餐點名稱，1-100字元
  - `unit_price` (required, integer)：單價(元)，必須大於0
  - `quantity` (required, integer)：數量，範圍1-99
- `expected_total` (required, integer)：前端計算的預期總金額(元)，用於與後端計算驗證
- `notes` (optional, string)：備註，最多 500 字元

#### 回應規格

**成功回應 (201 Created)**：
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": 123,
  "menu_id": 123,
  "total_amount": 270,
  "status": "PENDING",
  "notes": "不要辣，飯少一點",
  "order_date": "2025-09-28",
  "saga_id": "660f9500-f39c-52e5-b827-557766551111",
  "reservation_id": null,
  "cancellation_reason": null,
  "version": 1,
  "created_at": "2025-09-28T10:30:00.000Z",
  "updated_at": "2025-09-28T10:30:00.000Z",
  "items": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440001",
      "menu_item_id": 501,
      "menu_item_name": "宮保雞丁",
      "quantity": 2,
      "unit_price": 120,
      "subtotal": 240,
      "created_at": "2025-09-28T10:30:00.000Z"
    },
    {
      "id": "770e8400-e29b-41d4-a716-446655440002",
      "menu_item_id": 502,
      "menu_item_name": "白飯",
      "quantity": 1,
      "unit_price": 30,
      "subtotal": 30,
      "created_at": "2025-09-28T10:30:00.000Z"
    }
  ]
}
```

**錯誤回應**：
- `400 Bad Request`：請求格式錯誤或參數無效
- `401 Unauthorized`：認證失敗
- `404 Not Found`：菜單或餐點不存在
- `409 Conflict`：重複的 Idempotency-Key
- `422 Unprocessable Entity`：業務邏輯錯誤（如庫存不足、總金額不符）

**422 錯誤回應範例**：
```json
{
  "error": "VALIDATION_ERROR",
  "message": "總金額計算不符，預期: 270，實際: 300",
  "details": {
    "expected_total": 270,
    "calculated_total": 300
  },
  "timestamp": "2025-09-28T10:30:00.000Z"
}

#### 業務規則

1. 系統需驗證 menuId 和 menuItemId 的有效性
2. 數量必須為正整數
3. **總金額驗證**：後端計算總金額並與 `expected_total` 比對，不一致時返回 422 錯誤，確保員工知道實際扣款金額
4. 觸發 Saga 流程進行庫存預留和賒帳處理
5. 支援冪等性操作（透過 Idempotency-Key）

---

### 2.2 查詢歷史訂單

**API 編號**：API-002  
**端點**：`GET /orders/history`  
**功能描述**：員工查詢自己的訂餐歷史  
**對應 Use Case**：UC-05 員工歷史查詢  

#### 請求規格

**認證要求**：
- 需要有效的 JWT Token
- 員工角色權限

**Query Parameters**：
```
?from=2025-07-01&to=2025-07-31&status=COMPLETED,ON_CREDIT&page=1&page_size=20
```

**參數說明**：
- `from` (optional, date)：開始日期 (YYYY-MM-DD)
- `to` (optional, date)：結束日期 (YYYY-MM-DD)，限制：from ≤ to
- `status` (optional, string)：訂單狀態篩選，多值用逗號分隔
- `page` (optional, integer)：頁碼，預設 1
- `page_size` (optional, integer)：每頁筆數，預設 20，最大 100

**訂單狀態說明**：
- `PENDING`：訂單剛建立，等待處理
- `INVENTORY_RESERVED`：庫存已預留，準備賒帳
- `ON_CREDIT`：賒帳記錄已建立 + 餐點製作中/等待取餐（完成後會從薪水扣款）
- `COMPLETED`：賒帳記錄已建立 + 餐點已交付完成（會從薪水扣款）
- `CANCELLED`：訂單已取消（不會扣款）

**財務狀態說明**：
- `ON_CREDIT` 和 `COMPLETED` 都是「應收帳款」狀態
- 交付狀態：`ON_CREDIT` 是「服務進行中」，`COMPLETED` 是「服務已完成」
- 月底結算：`ON_CREDIT` 和 `COMPLETED` 兩種狀態都會從薪水扣款

**常見查詢場景**：
- 查看已取餐的：`status=COMPLETED`
- 查看會扣薪水的：`status=ON_CREDIT,COMPLETED`
- 查看製作中的：`status=ON_CREDIT`
- 查看取消的訂單：`status=CANCELLED`

#### 回應規格

**成功回應 (200 OK)**：
```json
{
  "orders": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "user_id": 123,
      "menu_id": 123,
      "total_amount": 300,
      "status": "COMPLETED",
      "notes": "不要辣",
      "order_date": "2025-09-28",
      "saga_id": "660f9500-f39c-52e5-b827-557766551111",
      "reservation_id": null,
      "cancellation_reason": null,
      "version": 1,
      "created_at": "2025-09-28T10:30:00.000Z",
      "updated_at": "2025-09-28T10:35:00.000Z",
      "items": [
        {
          "id": "770e8400-e29b-41d4-a716-446655440001",
          "menu_item_id": 501,
          "menu_item_name": "牛肉麵",
          "quantity": 2,
          "unit_price": 120,
          "subtotal": 240,
          "created_at": "2025-09-28T10:30:00.000Z"
        }
      ]
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_count": 45,
    "total_pages": 3
  }
}
```

#### 業務規則

1. 員工只能查詢自己的訂單歷史
2. 預設查詢本月記錄
3. 支援多種狀態篩選
4. 按訂單日期降序排列

---

### 2.3 查詢單筆訂單

**API 編號**：API-003  
**端點**：`GET /orders/{id}`  
**功能描述**：查詢特定訂單的詳細資訊  

#### 請求規格

**認證要求**：
- 需要有效的 JWT Token
- 員工/管理員角色權限

**Path Parameters**：
- `id` (required, UUID)：訂單ID

#### 回應規格

**成功回應 (200 OK)**：
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": 123,
  "menu_id": 123,
  "total_amount": 300,
  "status": "COMPLETED",
  "notes": "不要辣",
  "order_date": "2025-09-28",
  "saga_id": "660f9500-f39c-52e5-b827-557766551111",
  "reservation_id": null,
  "cancellation_reason": null,
  "version": 1,
  "created_at": "2025-09-28T10:30:00.000Z",
  "updated_at": "2025-09-28T10:35:00.000Z",
  "items": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440001",
      "menu_item_id": 501,
      "menu_item_name": "牛肉麵",
      "quantity": 2,
      "unit_price": 120,
      "subtotal": 240,
      "created_at": "2025-09-28T10:30:00.000Z"
    },
    {
      "id": "770e8400-e29b-41d4-a716-446655440002",
      "menu_item_id": 502,
      "menu_item_name": "珍珠奶茶",
      "quantity": 1,
      "unit_price": 60,
      "subtotal": 60,
      "created_at": "2025-09-28T10:30:00.000Z"
    }
  ]
}
```

**錯誤回應**：
- `404 Not Found`：訂單不存在
- `403 Forbidden`：無權限查看此訂單

#### 業務規則

1. 員工只能查詢自己的訂單
2. 管理員可以查詢任何訂單
3. 回傳完整的訂單明細資訊

---

### 2.4 取消訂單

**API 編號**：API-004  
**端點**：`PUT /orders/{id}/cancel`  
**功能描述**：取消指定的訂單  

#### 請求規格

**認證要求**：
- 需要有效的 JWT Token
- 員工/管理員角色權限

**Path Parameters**：
- `id` (required, UUID)：訂單ID

**Request Body**：
```json
{
  "cancellation_reason": "不想吃了"
}
```

**欄位說明**：
- `cancellation_reason` (required, string)：取消原因，1-200字元

#### 回應規格

**成功回應 (200 OK)**：
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": 123,
  "menu_id": 123,
  "total_amount": 270,
  "status": "CANCELLED",
  "notes": "不要辣，飯少一點",
  "order_date": "2025-09-28",
  "saga_id": "660f9500-f39c-52e5-b827-557766551111",
  "reservation_id": null,
  "cancellation_reason": "不想吃了",
  "version": 2,
  "created_at": "2025-09-28T10:30:00.000Z",
  "updated_at": "2025-09-28T10:40:00.000Z",
  "items": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440001",
      "menu_item_id": 501,
      "menu_item_name": "宮保雞丁",
      "quantity": 2,
      "unit_price": 120,
      "subtotal": 240,
      "created_at": "2025-09-28T10:30:00.000Z"
    }
  ]
}
```

**錯誤回應**：
- `400 Bad Request`：訂單無法取消（超過時限或狀態不允許）
- `404 Not Found`：訂單不存在
- `403 Forbidden`：無權限取消此訂單

**400 錯誤回應範例（時限過期）**：
```json
{
  "error": "CANCELLATION_TIME_EXPIRED",
  "message": "訂單建立已超過 10 分鐘，無法取消。建立時間: 2025-09-28 10:30:00",
  "details": {
    "created_at": "2025-09-28 10:30:00",
    "time_limit_minutes": 10
  },
  "timestamp": "2025-09-28T10:45:00.000Z"
}
```

**400 錯誤回應範例（狀態不允許）**：
```json
{
  "error": "INVALID_ORDER_STATUS",
  "message": "訂單狀態 COMPLETED 無法取消",
  "details": {
    "current_status": "COMPLETED"
  },
  "timestamp": "2025-09-28T10:45:00.000Z"
}

#### 業務規則

1. **時間限制**：只能在訂單建立後 10 分鐘內取消
   - 以 `created_at` 時間戳為準
   - 使用 UTC 時區進行比較
   - 超過時限回傳 `CANCELLATION_TIME_EXPIRED` 錯誤
2. **狀態限制**：只能取消 `PENDING` 狀態的訂單
   - 已完成的訂單（COMPLETED）無法取消
   - 已取消的訂單（CANCELLED）無法再次取消
3. **補償流程**：取消時觸發 Saga 補償流程
   - 釋放庫存預留
   - 沖銷賒帳記錄
   - 更新 Saga 步驟狀態為 COMPENSATED
4. **權限控制**：員工只能取消自己的訂單，管理員可以取消任何符合條件的訂單
5. **版本控制**：取消成功後訂單 version 欄位會遞增，用於樂觀鎖控制

**時間限制實現**：
```python
# API 層面的時間檢查（Python 程式碼）
current_time = datetime.now(timezone.utc)
time_limit = order.created_at + timedelta(minutes=10)
if current_time > time_limit:
    raise CancellationTimeExpiredError()
```

---

### 2.5 查詢訂單統計

**API 編號**：API-005  
**端點**：`GET /orders/statistics`  
**功能描述**：管理員查詢訂單統計資訊  
**對應 Use Case**：UC-16 管理員統計  

#### 請求規格

**認證要求**：
- 需要有效的 JWT Token
- 管理員角色權限

**Query Parameters**：
```
?from=2025-09-01&to=2025-09-30&group_by=day&include_items=true
```

**參數說明**：
- `from` (optional, date)：開始日期，預設本月第一天
- `to` (optional, date)：結束日期，預設今天
- `group_by` (optional, string)：統計維度 (day/week/month)，預設 day
- `include_items` (optional, boolean)：是否包含熱門餐點統計，預設 false

#### 回應規格

**成功回應 (200 OK)**：
```json
{
  "period": {
    "from": "2025-09-01",
    "to": "2025-09-30"
  },
  "summary": {
    "total_orders": 1250,
    "total_amount": 187500,
    "average_order_value": 150,
    "completed_orders": 1100,
    "cancelled_orders": 150
  },
  "daily_stats": [
    {
      "date": "2025-09-28",
      "order_count": 45,
      "total_amount": 6750,
      "average_amount": 150
    }
  ],
  "popular_items": [
    {
      "menu_item_id": 501,
      "menu_item_name": "牛肉麵",
      "order_count": 89,
      "total_quantity": 134
    }
  ]
}
```

#### 業務規則

1. 僅限管理員使用
2. 支援多種時間維度統計
3. 可選擇是否包含熱門餐點分析
4. 統計數據即時計算

---

### 2.6 月底結帳總和

**API 編號**：API-006  
**端點**：`GET /orders/summary`  
**功能描述**：生成月底結帳報表  

#### 請求規格

**認證要求**：
- 需要有效的 JWT Token
- 管理員角色權限

**Query Parameters**：
```
?month=2025-09&include_details=false&page=1&page_size=50
```

**參數說明**：
- `month` (optional, string)：指定月份 (YYYY-MM)，與 from/to 互斥
- `from` (optional, date)：開始日期 (YYYY-MM-DD)
- `to` (optional, date)：結束日期 (YYYY-MM-DD)，限制：from ≤ to
- `include_details` (optional, boolean)：是否包含明細，預設 false
- `page` (optional, integer)：分頁頁碼，預設 1
- `page_size` (optional, integer)：每頁筆數，預設 50

#### 回應規格

**成功回應 (200 OK)**：
```json
{
  "period": {
    "from": "2025-09-01",
    "to": "2025-09-30"
  },
  "users": [
    {
      "user_id": 456,
      "user_name": "王小明",
      "order_count": 12,
      "total_amount": 1800,
      "records": [
        {
          "order_id": "550e8400-e29b-41d4-a716-446655440000",
          "order_date": "2025-09-03",
          "amount": 150,
          "status": "COMPLETED"
        }
      ]
    }
  ],
  "grand_total": {
    "order_count": 120,
    "total_amount": 17850
  },
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_count": 25
  }
}
```

#### 業務規則

1. 僅限管理員使用
2. 預設查詢本月資料
3. 只統計已完成和賒帳狀態的訂單
4. 支援匯出 CSV/PDF 格式
5. includeDetails=true 時提供詳細明細

---

### 2.7 查詢用戶訂單

**API 編號**：API-007  
**端點**：`GET /orders/user/{userId}`  
**功能描述**：查詢特定用戶的所有訂單記錄  

#### 請求規格

**認證要求**：
- 需要有效的 JWT Token
- 員工/管理員角色權限

**Path Parameters**：
- `user_id` (required, integer)：用戶ID

**Query Parameters**：
```
?from=2025-07-01&to=2025-09-30&status=COMPLETED&page=1&page_size=20
```

**參數說明**：
- `from` (optional, date)：開始日期，預設近 90 天
- `to` (optional, date)：結束日期，限制：from ≤ to
- `status` (optional, string)：狀態篩選，多值用逗號分隔
- `page` (optional, integer)：頁碼，預設 1
- `page_size` (optional, integer)：每頁筆數，預設 20

#### 回應規格

**成功回應 (200 OK)**：
```json
{
  "user_id": 456,
  "user_name": "王小明",
  "period": {
    "from": "2025-07-01",
    "to": "2025-09-30"
  },
  "orders": [
    {
      "order_id": "550e8400-e29b-41d4-a716-446655440000",
      "order_date": "2025-09-28",
      "status": "COMPLETED",
      "total_amount": 150,
      "items": [
        {
          "menu_item_id": 501,
          "menu_item_name": "牛肉麵",
          "quantity": 2,
          "unit_price": 75
        }
      ]
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_count": 15
  }
}
```

#### 業務規則

1. 員工只能查詢自己的記錄（userId 必須是自己）
2. 管理員可以查詢任意用戶的記錄
3. 回傳完整的消費明細
4. 按訂單日期降序排列

## 三、通用規範

### 3.1 認證與授權

- 所有 API 都需要有效的 JWT Token
- Token 在 Authorization header 中以 Bearer 格式提供
- 權限檢查：
  - 員工：只能操作自己的資料
  - 管理員：可以操作所有資料

### 3.2 錯誤處理

**FastAPI 預設錯誤回應格式**：
```json
{
  "detail": "參數驗證失敗"
}
```

**Pydantic 驗證錯誤格式**：
```json
{
  "detail": [
    {
      "loc": ["body", "quantity"],
      "msg": "ensure this value is greater than 0",
      "type": "value_error.number.not_gt"
    }
  ]
}
```

**常見錯誤碼**：
- `INVALID_PARAMETER`：參數錯誤
- `UNAUTHORIZED`：認證失敗
- `FORBIDDEN`：權限不足
- `NOT_FOUND`：資源不存在
- `BUSINESS_RULE_VIOLATION`：業務規則違反
- `INTERNAL_ERROR`：內部錯誤

### 3.3 分頁規範

- 使用 `page` 和 `page_size` 參數
- page 從 1 開始
- page_size 預設 20，最大 100
- 回應包含 pagination 物件

### 3.4 日期時間格式

- 日期：ISO 8601 格式 (YYYY-MM-DD)
- 時間：ISO 8601 格式 (YYYY-MM-DDTHH:mm:ssZ)
- 時區：統一使用 UTC

### 3.5 資料驗證

- 必填欄位不可為空
- 數值範圍驗證
- 字串長度限制
- 日期格式和邏輯驗證

## 四、測試案例

### 4.1 功能測試

1. **正常流程測試**
   - 建立訂單 → 查詢訂單 → 取消訂單
   - 各種查詢條件組合測試

2. **邊界值測試**
   - 取消訂單時間限制（10分鐘）
   - 分頁參數邊界值
   - 日期範圍邊界值

3. **權限測試**
   - 員工存取其他人資料
   - 管理員權限驗證
   - 無效 Token 測試

### 4.2 效能測試

1. **負載測試**
   - 並發下單測試
   - 大量查詢測試

2. **壓力測試**
   - 系統極限測試
   - 資料庫連線池測試

### 4.3 整合測試

1. **微服務整合**
   - 與 Menu Service 整合
   - 與 Auth Service 整合
   - Saga 流程測試

2. **資料一致性測試**
   - 並發修改測試
   - 補償流程測試

## 五、部署要求

### 5.1 環境需求

- FastAPI 框架
- PostgreSQL 15 資料庫
- Redis 7.x 快取
- RabbitMQ 訊息佇列
- Docker 容器化

### 5.2 監控指標

- API 回應時間
- 錯誤率
- 並發處理量
- 資料庫連線數
- Saga 成功率

## 六、文件變更記錄

| 版本 | 日期 | 變更內容 | 作者 |
|------|------|----------|------|
| v1.0 | 2025-09-28 | 初始版本 | [作者姓名] |

---

**備註**：本文件基於 Order Service 需求規格制定，如有變更需求請更新此文件並通知相關開發人員。