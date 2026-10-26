# Meal 訂餐系統 MVP

包含 FastAPI 後端與 Vue 前端，提供員工登入、管理員菜單維護、下單、訂單查詢／取消及庫存管理。資料使用 PostgreSQL、SQLAlchemy Async 與 Alembic；JWT 負責登入驗證，角色權限由資料庫使用者資料判斷。

## 功能與流程

- 員工註冊、登入、查看目前帳號：`POST /auth/register`、`POST /auth/login`、`GET /auth/me`
- 員工查詢可用菜單並建立自己的訂單。
- 管理員建立／修改菜單與餐點、補貨、完成訂單及查看庫存異動。
- 訂單價格由資料庫菜單決定，訂單明細保存下單當下的餐點名稱與價格。
- 訂單、明細、庫存扣減與異動帳本在同一個 PostgreSQL transaction；不足庫存會回滾。
- 取消待處理訂單會在同一 transaction 回補庫存；重複取消會回傳衝突。

## 技術結構

```text
app/main.py             FastAPI 路由、依賴注入、錯誤處理與啟動流程
app/auth.py             JWT 與登入者／管理員權限依賴
app/models.py           SQLAlchemy 資料表與關聯
app/schemas.py          Pydantic 請求／回應格式
app/services.py         訂單建立、查詢、取消與完成
app/inventory_service.py 庫存原子扣減、補貨、回補與異動帳本
app/menu_db_service.py  菜單資料庫操作
alembic/versions/       資料庫版本遷移
tests/                  單元測試與 PostgreSQL 整合測試
frontend/               Vue 3 + Vite 員工／管理員介面
```

## Render 公開 Demo

本 repo 是 monorepo：FastAPI 位於根目錄，Vue 前端位於 `frontend/`。Render 免費方案適合短期展示；免費 PostgreSQL 會在建立 30 天後到期，API 閒置 15 分鐘會休眠。若要長期保留資料，請在 Render 選擇持續有效的資料庫方案。

1. 在 Render 使用 **New → Blueprint** 連接此 GitHub repo，使用根目錄的 `render.yaml` 建立 API、PostgreSQL 與 Redis。
2. API 部署完成後，記下 FastAPI 的公開 HTTPS 網址。
3. 再建立一個 Blueprint，仍連接同一 repo，Blueprint 檔案指定為 `render-frontend.yaml`。在 `VITE_API_BASE_URL` 欄位填入剛才的 API 網址。
4. 前端部署完成後，將其 HTTPS 網址設為 API 服務的 `FRONTEND_URL` 環境變數，並重新部署 API，讓 CORS 允許前端呼叫。
5. 驗證前端登入、菜單查詢、建立訂單、庫存扣減與取消流程。

Render 的免費 Web Service 不提供 Shell。第一次建立雲端管理員帳號時，可在本機執行 `create_admin.py`，並暫時使用 Render PostgreSQL 的外部連線網址及 IP allowlist；建立後立即移除本機連線環境變數。不要將資料庫網址或密碼提交到 GitHub。

## 啟動方式（Windows PowerShell + Docker Desktop）

先啟動 Docker Desktop，進入本目錄後執行：

```powershell
Copy-Item .env.example .env
```

編輯 `.env`，把 `JWT_SECRET_KEY` 改成隨機長字串。可先產生一組：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

再啟動服務：

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f app
```

Compose 會啟動 PostgreSQL 與 Redis，等待健康檢查通過後，先執行 `alembic upgrade head` 再啟動 FastAPI。看到 app 容器狀態為 `healthy` 後，開啟 [http://localhost:8000/docs](http://localhost:8000/docs)。PostgreSQL 主機連接埠為 `5433`，Redis 為 `6380`。

初次使用需建立管理員：

```powershell
docker compose exec app python create_admin.py
```

程式會提示輸入管理員帳號與密碼。一般員工可由 Swagger 的 `/auth/register` 註冊。完成後以 `/auth/login` 登入，把 `access_token` 貼進 Swagger 的 **Authorize** 欄位；每個角色都要使用各自帳號登入。

停止服務但保留資料：

```powershell
docker compose down
```

## 手動 Demo 流程

1. 以管理員登入 Swagger，執行 `POST /admin/menus` 建立菜單，再用 `POST /admin/menus/{menu_id}/items` 新增餐點。
2. 管理員執行 `POST /admin/inventory/{menu_item_id}/restock` 補庫存。
3. 註冊員工並以員工登入，執行 `GET /menus` 查看可用菜單。
4. 員工執行 `POST /orders` 下單，body 只帶菜單 ID、餐點 ID 與數量，例如：

   ```json
   {
     "menu_id": 1,
     "items": [{"menu_item_id": 101, "quantity": 2}]
   }
   ```

5. 執行 `GET /orders/{order_id}` 和 `GET /inventory/{menu_item_id}` 確認訂單與扣庫存。
6. 取消測試訂單：`PUT /orders/{order_id}/cancel`，body `{"cancellation_reason":"Demo 測試"}`。確認庫存回補，再重複取消一次確認收到 `409 Conflict`。
7. 再建立一筆訂單，將餐點改價後建立下一筆訂單：新單使用新價格，舊單仍保留原價格。
8. 以管理員登入，執行 `GET /admin/inventory/{menu_item_id}/movements` 查看補貨、下單扣除與取消回補紀錄。

現有範例菜單由 `004_menu_catalog` migration 匯入，餐點 ID 為 `101` 至 `406`；新建資料請以 API 回應中的 ID 為準。

## 測試

單元測試不需要啟動服務：

```powershell
python -m pip install -r requirements.txt
python -m pytest -q tests
```

真實 PostgreSQL 整合測試會建立並清空測試 schema，因此只可使用名稱以 `test_` 開頭的專用資料庫。啟動隔離的測試資料庫：

```powershell
docker compose --profile test up -d test-postgres
$env:TEST_DATABASE_URL = "postgresql+asyncpg://test_user:test_password@localhost:5434/test_order_service"
python -m pytest -m integration -q
Remove-Item Env:TEST_DATABASE_URL
```

整合測試會檢查：庫存不足時訂單／明細／扣庫存帳本全部回滾、取消只回補一次，以及調價後新舊訂單分別保存正確價格。執行完整測試時，若未設定 `TEST_DATABASE_URL`，整合測試會標示為 skipped；不會連到一般開發資料庫。

Migration 可獨立檢查：

```powershell
python -m alembic current
python -m alembic upgrade head
```

## 常見問題

- **Docker 無法連線**：先確認 Docker Desktop 已啟動，再執行 `docker version`。
- **app 一直 unhealthy**：執行 `docker compose logs app postgres redis` 查看啟動錯誤；確認 `.env` 有有效的 `JWT_SECRET_KEY`。
- **資料庫 migration 失敗**：確認 PostgreSQL 健康，再看 app log 中 Alembic 回報的 revision 或資料庫錯誤。
- **舊訂單價格不同於目前菜單**：這是預期行為；訂單保留下單時的價格快照。
- **pytest 顯示整合測試 skipped**：啟動 `test-postgres` 並設定 `TEST_DATABASE_URL` 後，再執行 `python -m pytest -m integration -q`。

## 範圍與後續

目前完成的是 Auth／RBAC、資料庫菜單、訂單與庫存核心流程及其測試，也有已串接 FastAPI 的 Vue 員工／管理員介面。需求文件提到的餐點客製化、評價、雙語菜單、月底帳務確認與通知尚未納入此 MVP；後續可依需求優先級擴充 API 與介面。
