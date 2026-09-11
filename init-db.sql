-- Order Service 資料庫初始化腳本
-- 建立必要的擴充套件和初始設定

-- 確保資料庫存在
\c order_service;

-- 啟用必要的 PostgreSQL 擴充套件
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- UUID 生成函數
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- 文字相似度搜尋
CREATE EXTENSION IF NOT EXISTS "btree_gin";  -- GIN 索引優化

-- 建立時區設定
SET timezone = 'UTC';

-- 建立基本的 Schema 註解
COMMENT ON DATABASE order_service IS 'Order Service 微服務資料庫';

-- 建立審計觸發器函數（用於追蹤資料變更）
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 建立軟刪除檢查函數
CREATE OR REPLACE FUNCTION check_soft_delete()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.is_deleted = false AND NEW.is_deleted = true THEN
        NEW.deleted_at = CURRENT_TIMESTAMP;
    ELSIF OLD.is_deleted = true AND NEW.is_deleted = false THEN
        NEW.deleted_at = NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 確保使用者權限設定正確
GRANT ALL PRIVILEGES ON DATABASE order_service TO order_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO order_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO order_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO order_user;

-- 設定預設權限（對未來建立的物件）
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO order_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO order_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO order_user;

-- 顯示初始化完成訊息
\echo 'Order Service 資料庫初始化完成'