"""
Order Service Pydantic 資料驗證模型

包含三類模型：
1. 請求模型 (Request Models) - API 請求資料驗證
2. 回應模型 (Response Models) - API 回應資料序列化
3. 內部傳輸模型 (Internal DTOs) - 服務間資料傳輸
"""

import uuid
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from enum import Enum

from pydantic import BaseModel, validator, Field

from .models import OrderStatus, SagaStepState


# ================================
# 基礎模型和枚舉
# ================================

class OrderStatusSchema(str, Enum):
    """訂單狀態枚舉 (對應 SQLAlchemy 模型)"""
    PENDING = "PENDING"
    INVENTORY_RESERVED = "INVENTORY_RESERVED"
    ON_CREDIT = "ON_CREDIT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class SagaStepStateSchema(str, Enum):
    """Saga 步驟狀態枚舉 (對應 SQLAlchemy 模型)"""
    PENDING = "PENDING"
    DONE = "DONE"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


# ================================
# 請求模型 (Request Models)
# ================================

class OrderItemCreate(BaseModel):
    """建立訂單項目的請求模型"""
    menu_item_id: int = Field(..., gt=0, description="餐點ID，必須大於0")
    menu_item_name: str = Field(..., min_length=1, max_length=100, description="餐點名稱")
    unit_price: int = Field(..., gt=0, description="單價(元)")
    quantity: int = Field(..., gt=0, le=99, description="數量，範圍1-99")


class OrderCreate(BaseModel):
    """建立訂單的請求模型"""
    menu_id: int = Field(..., gt=0, description="菜單編號")
    items: List[OrderItemCreate] = Field(..., min_items=1, max_items=20, description="訂購項目清單，最多20項")
    expected_total: int = Field(..., gt=0, description="前端計算的預期總金額(元)")
    notes: Optional[str] = Field(None, max_length=500, description="備註，最多500字元")


class OrderCancelRequest(BaseModel):
    """取消訂單的請求模型"""
    cancellation_reason: str = Field(..., min_length=1, max_length=200, description="取消原因")


# ================================
# 回應模型 (Response Models)
# ================================

class OrderItemResponse(BaseModel):
    """訂單項目回應模型"""
    id: uuid.UUID
    menu_item_id: int
    menu_item_name: str
    quantity: int
    unit_price: int = Field(..., description="單價(元)")
    subtotal: int = Field(..., description="小計(元)")
    created_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    """訂單回應模型 (通用於所有場景)"""
    id: uuid.UUID
    user_id: int
    menu_id: int
    total_amount: int = Field(..., description="總金額(元)")
    status: OrderStatusSchema
    notes: Optional[str] = None
    order_date: date
    saga_id: uuid.UUID
    reservation_id: Optional[uuid.UUID] = None
    cancellation_reason: Optional[str] = None
    version: int
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse] = []

    class Config:
        from_attributes = True


class OrderHistoryResponse(BaseModel):
    """歷史訂單查詢回應模型"""
    orders: List[OrderResponse]
    pagination: Dict[str, Any] = Field(..., description="分頁資訊")

    class Config:
        from_attributes = True


# ================================
# 統計和報表模型
# ================================

class OrderStatistics(BaseModel):
    """訂單統計模型"""
    period: Dict[str, Any] = Field(..., description="統計期間")
    total_orders: int = Field(..., description="總訂單數")
    total_amount: int = Field(..., description="總金額(元)")
    completed_orders: int = Field(..., description="完成訂單數")
    cancelled_orders: int = Field(..., description="取消訂單數")
    avg_order_amount: float = Field(..., description="平均訂單金額")
    popular_items: Optional[List[Dict[str, Any]]] = Field(None, description="熱門餐點")

    class Config:
        schema_extra = {
            "example": {
                "period": {"from": "2025-09-01", "to": "2025-09-30"},
                "total_orders": 150,
                "total_amount": 45000,
                "completed_orders": 142,
                "cancelled_orders": 8,
                "avg_order_amount": 300.0,
                "popular_items": []
            }
        }


class MonthlySummary(BaseModel):
    """月底結帳總和模型 - 專為報表服務設計"""
    period: Dict[str, str] = Field(..., description="結帳期間")
    users: List[Dict[str, Any]] = Field(..., description="用戶匯總資料")
    grand_total: Dict[str, Any] = Field(..., description="總計資訊")

    class Config:
        schema_extra = {
            "example": {
                "period": {"from": "2025-07-01", "to": "2025-07-31"},
                "users": [
                    {
                        "userId": 456,
                        "userName": "王小明",
                        "orderCount": 12,
                        "totalAmount": 1800,
                        "records": []
                    }
                ],
                "grand_total": {
                    "order_count": 120,
                    "total_amount": 17850
                }
            }
        }


class UserOrderHistoryResponse(BaseModel):
    """用戶訂單歷史回應模型 - 專為報表服務設計"""
    user_id: int = Field(..., description="用戶ID")
    period: Optional[Dict[str, str]] = Field(None, description="查詢期間")
    total_count: int = Field(..., description="期間內總訂單數")
    total_amount: int = Field(..., description="期間內總消費金額(元)")
    orders: List[OrderResponse] = Field(..., description="訂單明細")

    class Config:
        schema_extra = {
            "example": {
                "user_id": 456,
                "period": {"from": "2025-05-01", "to": "2025-07-31"},
                "total_count": 25,
                "total_amount": 3750,
                "orders": []
            }
        }


# ================================
# 內部傳輸模型 (Internal DTOs)
# ================================

class SagaStepUpdate(BaseModel):
    """Saga 步驟更新模型"""
    step: str = Field(..., description="步驟名稱")
    state: SagaStepStateSchema
    payload: Optional[Dict[str, Any]] = None
    retry_count: int = Field(0, ge=0, description="重試次數")

    class Config:
        schema_extra = {
            "example": {
                "step": "RESERVE_INVENTORY",
                "state": "DONE",
                "payload": {"reservation_id": "770fa600-g40d-63f6-c938-668877662222"},
                "retry_count": 0
            }
        }


class OutboxEvent(BaseModel):
    """Outbox 事件模型"""
    aggregate_id: uuid.UUID = Field(..., description="聚合根ID")
    event_type: str = Field(..., description="事件類型")
    payload: Dict[str, Any] = Field(..., description="事件內容")

    class Config:
        schema_extra = {
            "example": {
                "aggregate_id": "550e8400-e29b-41d4-a716-446655440000",
                "event_type": "order.created",
                "payload": {
                    "orderId": "550e8400-e29b-41d4-a716-446655440000",
                    "userId": 123,
                    "totalAmount": 300,
                    "items": []
                }
            }
        }


class HealthCheckResponse(BaseModel):
    """健康檢查回應模型"""
    status: str = Field(..., description="整體狀態")
    checks: Dict[str, Any] = Field(..., description="各組件檢查結果")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="檢查時間")

    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "checks": {
                    "database": {"status": "healthy"},
                    "redis": {"status": "healthy"}
                },
                "timestamp": "2025-09-28T10:30:00Z"
            }
        }


# ================================
# 錯誤回應模型
# ================================

class ErrorResponse(BaseModel):
    """標準錯誤回應模型"""
    error_code: str = Field(..., description="錯誤代碼")
    message: str = Field(..., description="錯誤訊息")
    details: Optional[Dict[str, Any]] = Field(None, description="錯誤詳情")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="錯誤時間")

    class Config:
        schema_extra = {
            "example": {
                "error_code": "VALIDATION_ERROR",
                "message": "請求資料驗證失敗",
                "details": {"field": "quantity", "message": "數量必須大於0"},
                "timestamp": "2025-09-28T10:30:00Z"
            }
        }