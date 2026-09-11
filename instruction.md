# Order Service 開發指南

## 專案概述

根據架構文件建立的 Order Service，支援 Saga 模式、事件驅動架構和微服務通訊的訂單服務系統。

## 開發順序說明

### 🎯 總體原則
- **由下而上開發**：從基礎設施到業務邏輯到 API
- **依賴管理**：先建立被依賴的模組，再建立依賴其他模組的部分
- **逐步驗證**：每個階段完成後都要能測試和驗證

---

## 📋 開發階段規劃

### 第一階段：基礎設施建立 (Infrastructure Setup)
**目標**：建立專案運行的基本環境

#### 1.1 配置系統 (Priority: 🔥 最高)
- `app/config.py` - 環境變數設定、日誌配置
- `app/exceptions.py` - 自定義例外類別
- **為什麼先做**：所有其他模組都需要配置和錯誤處理

#### 1.2 資料庫連接 (Priority: 🔥 最高)
- `app/database.py` - PostgreSQL + Redis 連線
- **為什麼先做**：Models 和 Services 都需要資料庫連接

#### 1.3 Docker 環境 (Priority: 🔥 最高)
- `Dockerfile` - 應用程式容器化
- `docker-compose.yml` - 完整開發環境
- **為什麼先做**：提供一致的開發環境

**驗證方式**：
```bash
# 啟動服務並檢查連接
docker-compose up -d postgres redis rabbitmq
# 測試資料庫連接是否正常
```

---

### 第二階段：資料層建立 (Data Layer)
**目標**：建立資料模型和資料庫結構

#### 2.1 SQLAlchemy 模型 (Priority: 🔥 最高)
- `app/models.py` - Order, OrderItem, SagaSteps, Outbox 模型
- **為什麼先做**：業務邏輯需要操作這些資料結構

#### 2.2 Pydantic 模型 (Priority: 🔥 最高)
- `app/schemas.py` - API 請求/回應模型
- **為什麼先做**：API 端點需要這些模型進行資料驗證

#### 2.3 資料庫遷移 (Priority: 🔥 最高)
- `alembic.ini` - Alembic 配置
- `alembic/env.py` - 遷移環境設定
- 初始化遷移檔案
- **為什麼先做**：需要實際的資料庫結構來測試

**驗證方式**：
```bash
# 生成和執行遷移
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
# 檢查資料庫表是否正確建立
```

---

### 第三階段：核心業務邏輯 (Business Logic)
**目標**：實現訂單處理和 Saga 協調邏輯

#### 3.1 基礎服務層 (Priority: 🟠 高)
- `app/services.py` - 訂單 CRUD、Saga 協調邏輯
- **為什麼這時做**：有了資料模型才能實現業務邏輯

#### 3.2 訊息系統 (Priority: 🟠 高)
- `app/messaging.py` - RabbitMQ 發布/消費、Outbox Pattern
- **為什麼這時做**：Saga 流程需要訊息傳遞

#### 3.3 認證授權 (Priority: 🟡 中)
- `app/auth.py` - JWT 驗證、權限控制
- **為什麼這時做**：API 層需要認證機制

**驗證方式**：
```python
# 單元測試業務邏輯
pytest tests/test_services.py
# 測試訊息發布/消費
pytest tests/test_messaging.py
```

---

### 第四階段：API 層建立 (API Layer)
**目標**：提供 HTTP API 介面

#### 4.1 FastAPI 應用程式 (Priority: 🟡 中)
- `app/main.py` - FastAPI 入口、路由配置、7支 API 端點
- **為什麼最後做**：需要所有底層服務都就緒

**API 端點優先順序**：
1. `GET /health` - 健康檢查 (最簡單，用於驗證)
2. `POST /orders` - 建立訂單 (核心功能)
3. `GET /orders/{id}` - 查詢單筆訂單
4. `GET /orders/history` - 查詢歷史訂單
5. `PUT /orders/{id}/cancel` - 取消訂單
6. `GET /orders/statistics` - 查詢統計
7. `GET /orders/summary` - 月底結帳總和
8. `GET /orders/user/{userId}` - 查詢用戶訂單

**驗證方式**：
```bash
# 啟動 API 服務
uvicorn app.main:app --reload
# 測試 API 端點
curl http://localhost:8000/health
curl http://localhost:8000/docs  # 查看 API 文件
```

---

### 第五階段：整合測試 (Integration)
**目標**：確保整個系統協同工作

#### 5.1 端到端測試
- 完整的訂單流程測試
- Saga 流程測試
- 錯誤處理測試

#### 5.2 效能測試
- API 回應時間
- 資料庫查詢效能
- 訊息處理效能

---

## 🔧 技術細節指南

### 依賴關係圖
```
config.py (基礎)
    ↓
database.py (資料庫連接)
    ↓
models.py (資料模型) + schemas.py (API 模型)
    ↓
services.py (業務邏輯) + messaging.py (訊息) + auth.py (認證)
    ↓
main.py (API 層)
```

### 開發環境準備
```bash
# 1. 啟動基礎服務
docker-compose up -d postgres redis rabbitmq

# 2. 安裝 Python 依賴
pip install -r requirements.txt

# 3. 設定環境變數
cp .env.example .env

# 4. 初始化資料庫
alembic upgrade head

# 5. 啟動開發服務
uvicorn app.main:app --reload
```

### 測試策略
- **單元測試**：每個模組獨立測試
- **整合測試**：模組間協作測試
- **端到端測試**：完整業務流程測試

---

## 📝 每階段完成標準

### 第一階段完成標準
- [x] 可以成功啟動 Docker 服務
- [x] 可以連接到 PostgreSQL 和 Redis
- [x] 基本的日誌和錯誤處理正常運作

### 第二階段完成標準
- [x] 資料庫表結構正確建立
- [x] 可以執行基本的 CRUD 操作
- [x] Pydantic 模型驗證正常

### 第三階段完成標準
- [ ] 可以建立和更新訂單
- [ ] Saga 流程可以正確執行
- [ ] 訊息發布和消費正常

### 第四階段完成標準
- [ ] 所有 7 個 API 端點正常回應（先做核心的四個就好）
- [ ] API 文件自動生成
- [ ] 認證和授權正確運作

### 第五階段完成標準
- [ ] 完整的訂單流程測試通過
- [ ] 錯誤情況處理正確
- [ ] 效能符合預期

---

## 🚀 下一步行動

1. **立即開始**：建立 `app/config.py` 和 `app/exceptions.py`
2. **並行開發**：在等待依賴的時候可以準備測試資料和文件
3. **持續整合**：每完成一個階段就進行測試和驗證

---

## 📚 參考資源

- [架構文件](./Doc/Architecture.md)
- [API 需求](./Doc/API_Requirements.md)
- [資料庫設計](./Doc/ERD.md)
- [FastAPI 官方文件](https://fastapi.tiangolo.com/)
- [SQLAlchemy 官方文件](https://docs.sqlalchemy.org/)
- [Alembic 官方文件](https://alembic.sqlalchemy.org/)