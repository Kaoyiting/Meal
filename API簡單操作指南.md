# 🍜 訂單系統 API 操作指南

## 🏃‍♂️ 快速開始

### 第一步：啟動系統
```bash
# 1. 進入 Order 資料夾
cd Order

# 2. 啟動服務
python -m uvicorn app.main:app --reload

# 3. 看到這個就成功了：
# INFO: Uvicorn running on http://127.0.0.1:8000
```

### 第二步：取得登入證明（Token）
```bash
# 生成測試用的登入 token
python generate_jwt_token.py

# 會得到兩個 token：
# - 一般員工用的
# - 管理員用的
```

---

## 📋 每隻 API 怎麼用

### 1. 🏥 檢查系統是否正常

**做什麼：** 確認系統有沒有掛掉

```bash
GET http://127.0.0.1:8000/health
```

**會得到：**
```json
{
  "status": "healthy",
  "checks": {
    "database": {"status": "healthy"}
  },
  "timestamp": "2025-10-26T10:30:00"
}
```

**什麼時候用：**
- 系統剛啟動時檢查
- 覺得系統怪怪的時候

---

### 2. 🛒 點餐（建立訂單）

**做什麼：** 員工點餐，建立新訂單

```bash
POST http://127.0.0.1:8000/orders
Authorization: Bearer <你的token>
Content-Type: application/json
```

**要送什麼資料：**
```json
{
  "menu_id": 1,
  "items": [
    {
      "menu_item_id": 101,
      "menu_item_name": "牛肉麵",
      "quantity": 2,
      "unit_price": 120
    },
    {
      "menu_item_id": 102,
      "menu_item_name": "滷蛋",
      "quantity": 1,
      "unit_price": 10
    }
  ],
  "expected_total": 250,
  "notes": "不要辣，謝謝"
}
```

**會得到：**
```json
{
  "id": "b7f2b5e9-307b-48db-ac9f-0301ea36abe7",
  "user_id": 1,
  "menu_id": 1,
  "total_amount": 250,
  "status": "PENDING",
  "notes": "不要辣，謝謝",
  "order_date": "2025-10-26",
  "saga_id": "...",
  "created_at": "2025-10-26T10:30:00",
  "items": [...]
}
```

---

### 3. 📚 查看我的訂單歷史

**做什麼：** 看自己過去點過什麼餐

```bash
GET http://127.0.0.1:8000/orders/history
Authorization: Bearer <你的token>
```

**可以加的篩選條件：**
```bash
# 看特定日期範圍
GET http://127.0.0.1:8000/orders/history?from_date=2025-10-01&to_date=2025-10-31

# 只看已完成的訂單
GET http://127.0.0.1:8000/orders/history?status=COMPLETED,ON_CREDIT

# 分頁（每頁10筆，看第2頁）
GET http://127.0.0.1:8000/orders/history?page=2&page_size=10
```

**會得到：**
```json
{
  "total": 25,
  "page": 1,
  "page_size": 20,
  "total_pages": 2,
  "orders": [
    {
      "id": "...",
      "status": "COMPLETED",
      "total_amount": 250,
      "order_date": "2025-10-25",
      "items_count": 2
    }
  ]
}
```

---

### 4. 🔍 查看單筆訂單詳情

**做什麼：** 看某個訂單的完整資訊

```bash
GET http://127.0.0.1:8000/orders/{訂單編號}
Authorization: Bearer <你的token>
```

**例子：**
```bash
GET http://127.0.0.1:8000/orders/b7f2b5e9-307b-48db-ac9f-0301ea36abe7
```

**會得到：**
```json
{
  "id": "b7f2b5e9-307b-48db-ac9f-0301ea36abe7",
  "user_id": 1,
  "status": "COMPLETED",
  "total_amount": 250,
  "notes": "不要辣",
  "order_date": "2025-10-26",
  "items": [
    {
      "id": "...",
      "menu_item_id": 101,
      "menu_item_name": "牛肉麵",
      "quantity": 2,
      "unit_price": 120,
      "subtotal": 240
    }
  ]
}
```

---

### 5. ❌ 取消訂單

**做什麼：** 點錯餐想取消（只能在10分鐘內）

```bash
PUT http://127.0.0.1:8000/orders/{訂單編號}/cancel
Authorization: Bearer <你的token>
Content-Type: application/json
```

**要送什麼資料：**
```json
{
  "cancellation_reason": "點錯餐了"
}
```

**成功會得到：**
```json
{
  "id": "訂單編號",
  "status": "CANCELLED",
  "cancellation_reason": "點錯餐了",
  "updated_at": "2025-10-26T10:35:00"
}
```

**失敗會得到：**
```json
{
  "error": "CANCELLATION_TIME_EXPIRED",
  "message": "訂單建立超過10分鐘，無法取消"
}
```

---

### 6. 📊 查看訂單統計（管理員專用）

**做什麼：** 看整體的訂單統計資料

```bash
GET http://127.0.0.1:8000/orders/statistics
Authorization: Bearer <管理員token>
```

**可以加的參數：**
```bash
# 看10月份的統計
GET http://127.0.0.1:8000/orders/statistics?from_date=2025-10-01&to_date=2025-10-31

# 按週統計
GET http://127.0.0.1:8000/orders/statistics?group_by=week

# 包含熱門餐點統計
GET http://127.0.0.1:8000/orders/statistics?include_items=true
```

**會得到：**
```json
{
  "total_orders": 150,
  "total_amount": 45000,
  "average_amount": 300,
  "period_stats": [
    {
      "period": "2025-10-26",
      "orders": 10,
      "amount": 3000
    }
  ],
  "popular_items": [
    {
      "menu_item_id": 101,
      "menu_item_name": "牛肉麵",
      "order_count": 50
    }
  ]
}
```

---

### 7. 🧪 測試用查訂單（不用登入）

**做什麼：** 測試時快速查看訂單，不用 token

```bash
GET http://127.0.0.1:8000/test/orders/{訂單編號}
```

**例子：**
```bash
GET http://127.0.0.1:8000/test/orders/b7f2b5e9-307b-48db-ac9f-0301ea36abe7
```

**注意：** 這是測試專用端點，正式環境不應該用

---

## 🚨 常見錯誤和解決方法

### 401 Unauthorized（沒權限）
```json
{
  "detail": "Token無效或已過期"
}
```
**解決方法：**
1. 檢查有沒有加 Authorization: Bearer <token>
2. 重新生成 token
3. 確認 token 格式正確

### 404 Not Found（找不到）
```json
{
  "detail": "訂單不存在"
}
```
**解決方法：**
1. 檢查訂單編號是否正確
2. 確認是否為自己的訂單

### 400 Bad Request（請求有問題）
```json
{
  "error": "CANCELLATION_TIME_EXPIRED",
  "message": "超過取消時限"
}
```
**解決方法：**
1. 檢查是否超過10分鐘
2. 確認訂單狀態是否可取消

### 422 Validation Error（資料格式錯誤）
```json
{
  "detail": [
    {
      "loc": ["body", "items"],
      "msg": "ensure this value has at least 1 items",
      "type": "value_error"
    }
  ]
}
```
**解決方法：**
1. 檢查必填欄位
2. 確認資料格式正確
3. 參考範例重新組織資料

---

## 💡 實用小技巧

### 1. 用瀏覽器看 API 文檔
```
http://127.0.0.1:8000/docs
```
有完整的 API 說明和測試介面

### 2. 快速測試所有功能
```bash
python simple_test.py
```

### 3. 檢查資料庫內容
```bash
python check_db.py
```

### 4. 生成新的 token
```bash
python generate_jwt_token.py
```

---

## 🎯 簡單測試流程

1. **啟動系統**：`python -m uvicorn app.main:app --reload`
2. **檢查健康**：訪問 `/health`
3. **生成 token**：執行 `generate_jwt_token.py`
4. **建立訂單**：POST `/orders`
5. **查看訂單**：GET `/orders/history`
6. **取消訂單**：PUT `/orders/{id}/cancel`（10分鐘內）

這樣就完成一個完整的訂單流程了！🎉