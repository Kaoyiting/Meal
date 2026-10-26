"""
Order Service FastAPI 應用程式

實現核心訂單管理 API：
- 建立訂單 (POST /orders)
- 查詢歷史訂單 (GET /orders/history)  
- 查詢單筆訂單 (GET /orders/{id})
- 取消訂單 (PUT /orders/{id}/cancel)
- 查詢統計 (GET /orders/statistics)
- 健康檢查 (GET /health)

技術特點：
- JWT 認證保護
- 統一錯誤處理
- 依賴注入架構
- 自動 API 文件生成
"""
import uuid
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

# 應用程式模組導入
from app.config import get_settings
from app.database import get_db
from app.auth import (
    auth_service,
    get_current_employee_id,
    get_current_user,
    get_current_user_id,
    require_admin,
)
from app.services import OrderService
from app.schemas import (
    OrderCreate, OrderResponse, OrderHistoryResponse,
    OrderCancelRequest, OrderStatistics, HealthCheckResponse,
    MonthlySummary, UserOrderHistoryResponse, InventoryRestockRequest,
    InventoryStockResponse, InventoryMovementResponse,
    UserRegisterRequest, UserLoginRequest, UserResponse, AuthTokenResponse,
)
from app.exceptions import OrderServiceException
from app.inventory_service import InventoryService
from app.models import MenuItem
from app.user_service import UserService
from app.menu_api import router as menu_router

# 設定日誌
logger = logging.getLogger(__name__)

# === 1. FastAPI 應用程式初始化 ===
settings = get_settings()

app = FastAPI(
    title="Order Service",
    description="訂單服務 API - 處理員工點餐和訂單管理",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {
            "name": "health",
            "description": "系統健康檢查"
        },
        {
            "name": "orders",
            "description": "訂單管理功能"
        },
        {
            "name": "statistics", 
            "description": "統計查詢功能（管理員專用）"
        }
    ]
)
app.include_router(menu_router)

# === 2. 應用程式生命週期事件 ===
@app.on_event("startup")
async def startup_event():
    """應用程式啟動時初始化"""
    from app.database import init_database, init_redis
    
    logger.info("正在啟動 Order Service...")
    try:
        # 初始化資料庫連接
        await init_database()
        logger.info("✅ PostgreSQL 資料庫連接已初始化")
        
        # 初始化 Redis 連接
        await init_redis()
        logger.info("✅ Redis 連接已初始化")
        
        logger.info("🚀 Order Service 啟動完成")
    except Exception as e:
        logger.error(f"❌ 應用程式啟動失敗: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """應用程式關閉時清理資源"""
    from app.database import close_database
    
    logger.info("正在關閉 Order Service...")
    try:
        await close_database()
        logger.info("✅ 資料庫連接已關閉")
        logger.info("👋 Order Service 已安全關閉")
    except Exception as e:
        logger.error(f"❌ 應用程式關閉時發生錯誤: {e}")

# === 3. CORS 中介軟體設定 ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(
        settings.BACKEND_CORS_ORIGINS
        + ([settings.FRONTEND_URL.rstrip("/")] if settings.FRONTEND_URL else [])
    )),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# === 4. 錯誤處理器 ===
@app.exception_handler(OrderServiceException)
async def handle_order_exception(request, exc: OrderServiceException):
    """統一處理所有 Order Service 的業務例外"""
    
    # 根據錯誤類型決定 HTTP 狀態碼
    status_mapping = {
        "VALIDATION_ERROR": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "MENU_VALIDATION_ERROR": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "ORDER_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "INVALID_ORDER_STATUS": status.HTTP_409_CONFLICT,
        "CANCELLATION_TIME_EXPIRED": status.HTTP_409_CONFLICT,
        "INSUFFICIENT_INVENTORY": status.HTTP_409_CONFLICT,
        "INVENTORY_RESERVATION_ERROR": status.HTTP_409_CONFLICT,
        "AUTHENTICATION_ERROR": status.HTTP_401_UNAUTHORIZED,
        "AUTHORIZATION_ERROR": status.HTTP_403_FORBIDDEN,
        "BUSINESS_LOGIC_ERROR": status.HTTP_400_BAD_REQUEST,
        "DATABASE_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "EXTERNAL_SERVICE_ERROR": status.HTTP_503_SERVICE_UNAVAILABLE,
        "SAGA_EXECUTION_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    
    status_code = status_mapping.get(exc.error_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # 記錄錯誤
    logger.warning(f"業務例外: {exc.error_code} - {exc.message}", extra={"details": exc.details})
    
    return JSONResponse(
        status_code=status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# === 5. 健康檢查端點 ===
@app.get(
    "/health",
    response_model=HealthCheckResponse,
    tags=["health"],
    summary="系統健康檢查",
    description="檢查 Order Service 的運行狀態"
)
async def health_check():
    """系統健康檢查端點"""
    # 執行實際的健康檢查
    from app.database import check_database_health
    
    try:
        health_status = await check_database_health()
        overall_status = "healthy" if all(
            check.get("status") == "healthy" 
            for check in health_status.values()
        ) else "unhealthy"
        
        return HealthCheckResponse(
            status=overall_status,
            checks=health_status,
            timestamp=datetime.utcnow()
        )
    except Exception as e:
        return HealthCheckResponse(
            status="unhealthy",
            checks={"error": {"status": "error", "details": str(e)}},
            timestamp=datetime.utcnow()
        )


@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["auth"])
async def register_employee(
    request: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """公開註冊只建立員工；角色不接受用戶端指定。"""
    user = await UserService(db).register_employee(request)
    return UserResponse.model_validate(user)


@app.post("/auth/login", response_model=AuthTokenResponse, tags=["auth"])
async def login(
    request: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await UserService(db).authenticate(request.username, request.password)
    token = auth_service.create_access_token(user.id)
    return AuthTokenResponse(access_token=token, user=UserResponse.model_validate(user))


@app.get("/auth/me", response_model=UserResponse, tags=["auth"])
async def read_current_user(current_user: dict = Depends(get_current_user)):
    """回傳 token 對應的資料庫使用者與角色。"""
    return current_user

# === 6. 核心業務端點 ===

@app.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["orders"],
    summary="建立新訂單",
    description="員工點餐功能 - 建立新的訂單並啟動 Saga 流程"
)
async def create_order(
    request: OrderCreate,
    user_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db)
):
    """
    建立新訂單
    
    - 驗證餐點和價格
    - 啟動 Saga 流程處理庫存和賒帳
    - 支援備註功能
    """
    logger.info(f"🛒 用戶 {user_id} 開始建立訂單")
    logger.info(f"🔍 DEBUG: 收到請求 menu_id={request.menu_id}, items={len(request.items)}")
    
    service = OrderService(db)
    result = await service.create_order(request, user_id)
    
    logger.info(f"✅ 訂單 {result.id} 建立成功")
    return result


@app.get(
    "/orders/history",
    response_model=OrderHistoryResponse,
    tags=["orders"],
    summary="查詢歷史訂單",
    description="查詢用戶的訂單歷史記錄，支援日期範圍和狀態篩選"
)
async def get_order_history(
    from_date: Optional[str] = Query(
        None, 
        description="開始日期 (YYYY-MM-DD)",
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    to_date: Optional[str] = Query(
        None, 
        description="結束日期 (YYYY-MM-DD)",
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    status: Optional[str] = Query(
        None, 
        description="訂單狀態篩選，多值用逗號分隔 (e.g., COMPLETED,ON_CREDIT)"
    ),
    page: int = Query(
        1, 
        ge=1, 
        description="頁碼"
    ),
    page_size: int = Query(
        20, 
        ge=1, 
        le=100, 
        description="每頁筆數 (最大100)"
    ),
    user_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db)
):
    """
    查詢歷史訂單
    
    - 員工只能查詢自己的訂單記錄
    - 支援日期範圍篩選 
    - 支援訂單狀態篩選
    - 支援分頁查詢
    """
    logger.info(f"📚 用戶 {user_id} 查詢歷史訂單 (page={page}, size={page_size})")
    
    service = OrderService(db)
    result = await service.get_order_history(
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
        status=status,
        page=page,
        page_size=page_size
    )

    return result


# === 6. 月底結帳總和 (管理員專用) ===
@app.get(
    "/orders/summary",
    response_model=MonthlySummary,
    tags=["reports"],
    summary="月底結帳總和 API",
    description="提供給報表服務的月度結帳總和資料，支援明細選項"
)
async def get_monthly_summary(
    from_date: Optional[str] = Query(
        None, 
        description="開始日期 (YYYY-MM-DD)",
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    to_date: Optional[str] = Query(
        None, 
        description="結束日期 (YYYY-MM-DD)",
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    include_details: bool = Query(
        False, 
        description="是否包含訂單明細"
    ),
    admin_user: dict = Depends(require_admin),  # 管理員權限檢查
    db: AsyncSession = Depends(get_db)
):
    """
    月底結帳總和 API - 專為報表服務設計
    
    - 僅限管理員使用
    - 查詢指定期間內所有用戶的訂單匯總
    - 支援 includeDetails 參數控制是否回傳明細
    - 包含餐點名稱資訊
    """
    logger.info(f"📊 管理員 {admin_user['user_id']} 查詢月底結帳總和")
    
    service = OrderService(db)
    result = await service.get_monthly_summary(
        from_date=from_date,
        to_date=to_date,
        include_details=include_details
    )
    
    return result


# === 7. 查詢用戶訂單記錄 (報表專用) ===
@app.get(
    "/orders/user/{user_id}",
    response_model=UserOrderHistoryResponse,
    tags=["reports"],
    summary="查詢用戶訂單記錄 API",
    description="提供給報表服務的用戶完整訂單資料，包含消費明細"
)
async def get_user_order_history(
    user_id: int = Path(..., description="用戶ID"),
    from_date: Optional[str] = Query(
        None, 
        description="開始日期 (YYYY-MM-DD)",
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    to_date: Optional[str] = Query(
        None, 
        description="結束日期 (YYYY-MM-DD)",
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    order_status: Optional[str] = Query(
        None, 
        description="訂單狀態篩選，多值用逗號分隔 (e.g., COMPLETED,ON_CREDIT)",
        alias="status"
    ),
    current_user = Depends(get_current_user),  # 獲取完整用戶信息
    db: AsyncSession = Depends(get_db)
):
    """
    查詢用戶訂單記錄 API - 專為報表服務設計
    
    - 員工只能查詢自己的記錄（user_id 必須與 JWT 中的用戶一致）
    - 管理員可查詢任意用戶記錄
    - 回傳完整的消費明細：訂單編號、日期、金額、狀態、項目
    - 支援日期範圍和狀態篩選
    """
    # 權限檢查：員工只能查自己，管理員可查任意用戶
    current_user_id = current_user["user_id"]
    
    is_admin = current_user["role"] == "admin"
    
    if not is_admin and current_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="員工只能查詢自己的訂單記錄"
        )
    
    logger.info(f"📋 查詢用戶 {user_id} 的訂單記錄")
    
    service = OrderService(db)
    result = await service.get_user_order_history_for_report(
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
        status=order_status
    )
    
    return result


@app.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    tags=["orders"],
    summary="查詢單筆訂單",
    description="查詢特定訂單的詳細資訊，包含所有訂單項目"
)
async def get_order_detail(
    order_id: uuid.UUID = Path(..., description="訂單ID"),
    user_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db)
):
    """
    查詢單筆訂單詳情
    
    - 員工只能查詢自己的訂單
    - 回傳完整的訂單資訊和項目明細
    """
    logger.info(f"🔍 用戶 {user_id} 查詢訂單 {order_id}")
    
    service = OrderService(db)
    result = await service.get_order_detail(order_id, user_id)

    return result


@app.put(
    "/orders/{order_id}/cancel",
    response_model=OrderResponse,
    tags=["orders"],
    summary="取消訂單",
    description="取消指定的訂單（需在10分鐘時限內），並啟動補償流程"
)
async def cancel_order(
    request: OrderCancelRequest,
    order_id: uuid.UUID = Path(..., description="訂單ID"),
    user_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db)
):
    """
    取消訂單
    
    - 只能在訂單建立後10分鐘內取消
    - 已完成的訂單無法取消
    - 員工只能取消自己的訂單
    - 會觸發 Saga 補償流程
    """
    logger.info(f"❌ 用戶 {user_id} 嘗試取消訂單 {order_id}")
    
    service = OrderService(db)
    result = await service.cancel_order(order_id, request, user_id)
    
    logger.info(f"✅ 訂單 {order_id} 取消成功")
    return result


@app.get(
    "/orders/statistics",
    response_model=OrderStatistics,
    tags=["statistics"],
    summary="查詢訂單統計",
    description="查詢訂單統計資訊，僅限管理員使用"
)
async def get_order_statistics(
    from_date: Optional[str] = Query(
        None, 
        description="開始日期 (YYYY-MM-DD)",
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    to_date: Optional[str] = Query(
        None, 
        description="結束日期 (YYYY-MM-DD)",
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    group_by: str = Query(
        "day", 
        regex="^(day|week|month)$", 
        description="統計維度"
    ),
    include_items: bool = Query(
        False, 
        description="是否包含熱門餐點統計"
    ),
    admin_user: dict = Depends(require_admin),  # 管理員權限檢查
    db: AsyncSession = Depends(get_db)
):
    """
    查詢訂單統計
    
    - 僅限管理員使用
    - 支援多種時間維度統計 (天/週/月)
    - 可選擇是否包含熱門餐點分析
    """
    logger.info(f"📊 管理員 {admin_user['user_id']} 查詢訂單統計")
    
    service = OrderService(db)
    result = await service.get_order_statistics(
        from_date=from_date,
        to_date=to_date,
        group_by=group_by,
        include_items=include_items
    )
    
    return result


@app.post(
    "/admin/orders/{order_id}/complete",
    response_model=OrderResponse,
    tags=["orders"],
    summary="標記訂單完成",
)
async def complete_order(
    order_id: uuid.UUID = Path(..., description="訂單ID"),
    admin_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    logger.info("管理員 %s 完成訂單 %s", admin_user["user_id"], order_id)
    return await OrderService(db).complete_order(order_id)


@app.get(
    "/inventory/{menu_item_id}",
    response_model=InventoryStockResponse,
    tags=["inventory"],
    summary="查詢餐點庫存",
)
async def get_inventory_stock(
    menu_item_id: int = Path(..., gt=0),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    del user_id  # JWT 驗證即代表此查詢需要登入。
    menu_item = await db.get(MenuItem, menu_item_id)
    if menu_item is None:
        raise HTTPException(status_code=404, detail="餐點不存在")
    stock = await InventoryService(db).get_stock(menu_item_id)
    return InventoryStockResponse(
        menu_item_id=menu_item_id,
        menu_item_name=menu_item.name,
        available_quantity=stock.available_quantity if stock else 0,
        updated_at=stock.updated_at if stock else None,
    )


@app.post(
    "/admin/inventory/{menu_item_id}/restock",
    response_model=InventoryStockResponse,
    status_code=status.HTTP_200_OK,
    tags=["inventory"],
    summary="補充餐點庫存",
)
async def restock_inventory(
    request: InventoryRestockRequest,
    menu_item_id: int = Path(..., gt=0),
    admin_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    menu_item = await db.get(MenuItem, menu_item_id)
    if menu_item is None:
        raise HTTPException(status_code=404, detail="餐點不存在")
    try:
        stock = await InventoryService(db).restock(menu_item_id, request.quantity)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    logger.info("管理員 %s 補貨 item=%s quantity=%s", admin_user["user_id"], menu_item_id, request.quantity)
    return InventoryStockResponse(
        menu_item_id=menu_item_id,
        menu_item_name=menu_item.name,
        available_quantity=stock.available_quantity,
        updated_at=stock.updated_at,
    )


@app.get(
    "/admin/inventory/{menu_item_id}/movements",
    response_model=list[InventoryMovementResponse],
    tags=["inventory"],
    summary="查詢庫存異動紀錄",
)
async def get_inventory_movements(
    menu_item_id: int = Path(..., gt=0),
    limit: int = Query(100, ge=1, le=500),
    admin_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    del admin_user
    menu_item = await db.get(MenuItem, menu_item_id)
    if menu_item is None:
        raise HTTPException(status_code=404, detail="餐點不存在")
    movements = await InventoryService(db).list_movements(menu_item_id, limit)
    return [
        InventoryMovementResponse(
            id=movement.id,
            menu_item_id=movement.menu_item_id,
            menu_item_name=menu_item.name,
            quantity_delta=movement.quantity_delta,
            reason=movement.reason,
            order_id=movement.order_id,
            created_at=movement.created_at,
        )
        for movement in movements
    ]


# === 完成！所有端點已實現 ===
# ✅ GET  /health              - 健康檢查
# ✅ POST /orders              - 建立訂單
# ✅ GET  /orders/{id}         - 查詢單筆訂單
# ✅ GET  /orders/history      - 查詢歷史訂單
# ✅ PUT  /orders/{id}/cancel  - 取消訂單
# ✅ GET  /orders/statistics   - 查詢統計（管理員）
# ✅ GET  /orders/summary      - 月底結帳總和（管理員，報表專用）
# ✅ GET  /orders/user/{userId} - 查詢用戶訂單記錄（報表專用）
# ✅ GET  /inventory/{menu_item_id} - 查詢庫存
# ✅ POST /admin/inventory/{menu_item_id}/restock - 管理員補貨
