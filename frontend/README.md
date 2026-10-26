# Meal 前端

Meal 是 Vue 3 + Vite 的員工訂餐介面，已串接 FastAPI 後端。員工可以建立帳號、登入、瀏覽資料庫菜單、建立訂單、查看自己的訂單並在期限內取消；管理員可以建立／停用菜單、管理餐點和價格、補貨並查看庫存異動。

## 啟動

### 1. 啟動 FastAPI 後端

建議先依照[專案說明](../README.md)啟動 PostgreSQL、Redis 和 FastAPI。後端要在 `http://localhost:8000` 可用。

如果使用 Docker Compose，在 `meal_order-main/Order` 執行：

```powershell
Copy-Item .env.example .env
# 編輯 .env，設定 JWT_SECRET_KEY
docker compose up --build -d
```

管理員帳號可在後端目錄執行 `docker compose exec app python create_admin.py` 建立。

### 2. 啟動 Vue 前端

在此目錄執行：

```powershell
npm install
npm run dev
```

在 Vite 顯示的網址開啟介面。開發伺服器會把 `/auth`、`/menus`、`/orders`、`/admin` 和 `/inventory` 請求代理到 `http://127.0.0.1:8000`，不需要另外處理瀏覽器跨來源設定。

若 FastAPI 不在預設位置，可建立 `.env.local`：

```text
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

建置靜態網站時，可設定 `VITE_API_BASE_URL` 指向 API 公開網址；後端需將前端網址加入 `BACKEND_CORS_ORIGINS`。

## 使用流程

1. 新使用者在登入頁建立員工帳號，再登入。
2. 員工瀏覽菜單，選餐點與數量，確認後送出；瀏覽器只傳餐點 ID 和數量，價格由 FastAPI 重新計算。
3. 員工可在「我的訂單」查看歷史訂單；待處理訂單在建立後 10 分鐘內可取消。
4. 管理員登入同一入口後，開啟「菜單與庫存」管理菜單、調價、下架餐點、補貨和查看異動。

管理員建立管理員帳號的方式見後端 README。公開註冊固定建立員工角色。

## 技術檔案

- `src/lib/api.js`：API 請求、Bearer token、錯誤訊息與登入狀態處理。
- `src/state.js`：登入狀態、菜單、餐袋、下單與訂單資料載入。
- `src/components/AuthPage.vue`：員工註冊與登入。
- `src/components/StorePage.vue`、`CartPanel.vue`、`CheckoutConfirm.vue`：瀏覽菜單、管理餐袋和送出訂單。
- `src/components/OrdersPage.vue`、`OrderDetails.vue`：訂單查詢、篩選、取消。
- `src/components/AdminPage.vue`：菜單與庫存管理介面。
- `vite.config.js`：開發期間代理 FastAPI API。

## 測試與建置

```powershell
npm test
npm run build
```

後端價格與庫存交易仍由 FastAPI／PostgreSQL 驗證；前端顯示的購物車小計只供預覽，訂單成功後改用伺服器回傳的正式價格。

## MVP 範圍

目前菜單 API 尚未提供客製化選項、評價、雙語內容與配送狀態，因此前端只送出餐點 ID、數量和訂單備註，並呈現後端現有訂單狀態。這些欄位要先加入後端資料模型和 API，再擴充介面。
