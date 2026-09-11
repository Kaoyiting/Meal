# 兩隻遺漏 API 需求確認

## 1. GET /orders/summary - 月底結帳總和 API

### 目的
提供給報表服務使用，生成月底結帳報表

### 功能需求
- 查詢指定期間內所有用戶的訂單匯總
- **需要訂單明細彙整**：要知道每個用戶訂購過什麼（簡易的名稱）
- 支援 `includeDetails` 參數來控制是否回傳明細

### 回傳資料結構

```json
{
  "period": {"from": "2025-07-01", "to": "2025-07-31"},
  "users": [
    {
      "userId": 456,
      "userName": "王小明",
      "orderCount": 12,
      "totalAmount": 1800,
      "records": [  // 當 includeDetails=true 時才回傳
        {
          "orderId": "uuid-string",
          "orderDate": "2025-07-03",
          "amount": 150,
          "status": "COMPLETED",
          "items": [
            {"menuItemName": "雞腿便當", "quantity": 1, "unitPrice": 120},
            {"menuItemName": "珍珠奶茶", "quantity": 1, "unitPrice": 30}
          ]
        }
      ]
    }
  ],
  "grandTotal": {"orderCount": 120, "totalAmount": 17850}
}
```

## 2. GET /orders/user/{userId} - 查詢用戶訂單記錄 API

### 目的
提供給報表服務查詢特定用戶的詳細訂單資料

### 功能需求
- 根據 `userId` 查詢該用戶的所有訂單
- **回傳完整的消費明細**：訂單編號、日期、金額、狀態、項目
- 支援日期範圍和狀態篩選

### 回傳資料結構

```json
{
  "userId": 456,
  "period": {"from": "2025-05-01", "to": "2025-07-31"},
  "orders": [
    {
      "orderId": "uuid-string",
      "orderDate": "2025-07-28",
      "status": "COMPLETED",
      "totalAmount": 150,
      "items": [  // 完整的項目明細
        {
          "menuItemId": 501,
          "menuItemName": "雞腿便當",
          "quantity": 2,
          "unitPrice": 75
        }
      ]
    }
  ],
  "totalCount": 25,
  "totalAmount": 3750
}
```

## 重點確認

1. **第一隻 API** 主要是匯總資料，但當 `includeDetails=true` 時會包含每筆訂單的項目明細（簡易名稱）
2. **第二隻 API** 專門提供單一用戶的完整消費明細，包含所有訂單的項目資訊
3. 兩隻 API 都要包含餐點名稱，不只是 ID
4. 資料結構要符合報表服務的需求

## 技術重點

- **餐點名稱**：必須確保 `order_items` 表有 `menu_item_name` 欄位
- **權限控制**：員工只能查自己，管理員可查任意用戶
- **效能考量**：大量訂單時使用分頁機制
- **日期處理**：支援月份和日期範圍查詢