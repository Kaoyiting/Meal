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
from app.auth import get_current_user_id, require_admin, get_current_user
from app.services import OrderService
from app.schemas import (
    OrderCreate, OrderResponse, OrderHistoryResponse,
    OrderCancelRequest, OrderStatistics, HealthCheckResponse,
    MonthlySummary, UserOrderHistoryResponse
)
from app.exceptions import OrderServiceException

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
    allow_origins=[
        "http://localhost:3000",    # React 開發環境
        "http://localhost:8080",    # Vue 開發環境
        "http://localhost:5173",    # Vite 開發環境
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
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
        "INVALID_ORDER_STATUS": status.HTTP_400_BAD_REQUEST,
        "CANCELLATION_TIME_EXPIRED": status.HTTP_400_BAD_REQUEST,
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
    user_id: int = Depends(get_current_user_id),
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
    user_id: int = Depends(get_current_user_id),
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
    
    # 簡化的管理員檢查：user_id=1 是管理員
    is_admin = (current_user_id == 1)
    
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
    user_id: int = Depends(get_current_user_id),
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
    user_id: int = Depends(get_current_user_id),
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


# === 8. 測試專用端點（無需認證） ===

@app.get(
    "/test/orders/{order_id}",
    tags=["testing"],
    summary="測試用查詢單筆訂單（無需認證）",
    description="僅供測試使用的訂單查詢端點，無需 JWT 認證"
)
async def test_get_order_detail(
    order_id: uuid.UUID = Path(..., description="訂單ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    測試用訂單查詢端點（無需認證）
    
    - 用於測試 API 功能
    - 不檢查用戶權限
    - 回傳完整的訂單資訊
    """
    logger.info(f"🧪 測試查詢訂單 {order_id}")
    
    try:
        # 直接查詢資料庫，不經過 Service 層的用戶權限檢查
        from sqlalchemy import select
        from app.models import Order, OrderItem
        
        # 查詢訂單基本資訊
        stmt = select(Order).where(Order.id == order_id)
        result = await db.execute(stmt)
        order = result.scalar_one_or_none()
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"訂單 {order_id} 不存在"
            )
        
        # 查詢訂單項目
        items_stmt = select(OrderItem).where(OrderItem.order_id == order_id)
        items_result = await db.execute(items_stmt)
        items = items_result.scalars().all()
        
        # 組裝回應資料
        return {
            "order_id": str(order.id),
            "user_id": order.user_id,
            "menu_id": order.menu_id,
            "total_amount": order.total_amount,
            "status": order.status,
            "notes": order.notes,
            "order_date": order.order_date.isoformat() if order.order_date else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
            "items_count": len(items),
            "items": [
                {
                    "item_id": str(item.id),
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "subtotal": item.subtotal
                }
                for item in items
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 測試查詢訂單失敗: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢訂單時發生錯誤: {str(e)}"
        )


# === 完成！所有端點已實現 ===
# ✅ GET  /health              - 健康檢查
# ✅ POST /orders              - 建立訂單
# ✅ GET  /orders/{id}         - 查詢單筆訂單
# ✅ GET  /orders/history      - 查詢歷史訂單
# ✅ PUT  /orders/{id}/cancel  - 取消訂單
# ✅ GET  /orders/statistics   - 查詢統計（管理員）
# ✅ GET  /orders/summary      - 月底結帳總和（管理員，報表專用）
# ✅ GET  /orders/user/{userId} - 查詢用戶訂單記錄（報表專用）
# 🧪 GET  /test/orders/{id}    - 測試用查詢訂單（無認證）