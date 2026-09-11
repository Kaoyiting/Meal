"""
Order Service 自定義例外類別

提供結構化的錯誤處理和 HTTP 狀態碼對應
"""

from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class OrderServiceException(Exception):
    """Order Service 基礎例外類別"""
    
    def __init__(
        self,
        message: str,
        error_code: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class BusinessLogicError(OrderServiceException):
    """業務邏輯錯誤"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="BUSINESS_LOGIC_ERROR",
            details=details
        )


class DatabaseError(OrderServiceException):
    """資料庫操作錯誤"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            details=details
        )


class ValidationError(OrderServiceException):
    """資料驗證錯誤"""
    
    def __init__(self, message: str, field: Optional[str] = None):
        details = {"field": field} if field else {}
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details=details
        )


class MenuValidationError(OrderServiceException):
    """菜單驗證錯誤"""
    
    def __init__(self, message: str, menu_id: Optional[int] = None, menu_item_id: Optional[int] = None):
        details = {}
        if menu_id is not None:
            details["menu_id"] = menu_id
        if menu_item_id is not None:
            details["menu_item_id"] = menu_item_id
        super().__init__(
            message=message,
            error_code="MENU_VALIDATION_ERROR",
            details=details
        )


class InvalidMenuError(MenuValidationError):
    """無效菜單錯誤"""
    
    def __init__(self, menu_id: int):
        super().__init__(
            message=f"無效的菜單ID: {menu_id}，該菜單不存在",
            menu_id=menu_id
        )


class InvalidMenuItemError(MenuValidationError):
    """無效餐點錯誤"""
    
    def __init__(self, menu_id: int, menu_item_id: int, correct_menu_id: Optional[int] = None):
        if correct_menu_id:
            message = f"餐點ID {menu_item_id} 不屬於菜單ID {menu_id}，該餐點屬於菜單ID {correct_menu_id}"
        else:
            message = f"無效的餐點ID: {menu_item_id}，該餐點不存在"
        super().__init__(
            message=message,
            menu_id=menu_id,
            menu_item_id=menu_item_id
        )


class MenuItemNameMismatchError(MenuValidationError):
    """餐點名稱不符錯誤"""
    
    def __init__(self, menu_item_id: int, expected_name: str, received_name: str):
        message = f"餐點名稱不符：餐點ID {menu_item_id} 的正確名稱為 '{expected_name}'，但收到 '{received_name}'"
        super().__init__(
            message=message,
            menu_item_id=menu_item_id
        )


class MenuItemPriceMismatchError(MenuValidationError):
    """餐點價格不符錯誤"""
    
    def __init__(self, menu_item_name: str, expected_price: int, received_price: int):
        message = f"餐點價格不符：餐點 '{menu_item_name}' 的正確價格為 {expected_price} 元，但收到 {received_price} 元"
        super().__init__(
            message=message
        )


class AuthenticationError(OrderServiceException):
    """認證錯誤"""
    
    def __init__(self, message: str = "認證失敗"):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR"
        )


class AuthorizationError(OrderServiceException):
    """授權錯誤"""
    
    def __init__(self, message: str = "沒有權限存取此資源"):
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR"
        )


class ResourceNotFoundError(OrderServiceException):
    """資源不存在錯誤"""
    
    def __init__(self, resource_type: str, resource_id: str):
        message = f"{resource_type} {resource_id} 不存在"
        super().__init__(
            message=message,
            error_code="RESOURCE_NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": resource_id}
        )


class ExternalServiceError(OrderServiceException):
    """外部服務錯誤"""
    
    def __init__(self, service_name: str, message: str):
        super().__init__(
            message=f"{service_name} 服務錯誤: {message}",
            error_code="EXTERNAL_SERVICE_ERROR",
            details={"service_name": service_name}
        )


class SagaExecutionError(OrderServiceException):
    """Saga 執行錯誤"""
    
    def __init__(self, saga_id: str, step: str, message: str):
        super().__init__(
            message=f"Saga {saga_id} 在步驟 {step} 執行失敗: {message}",
            error_code="SAGA_EXECUTION_ERROR",
            details={"saga_id": saga_id, "step": step}
        )


class OrderNotFoundError(OrderServiceException):
    """訂單不存在錯誤"""
    
    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="ORDER_NOT_FOUND"
        )


class InvalidOrderStatusError(OrderServiceException):
    """無效的訂單狀態錯誤"""
    
    def __init__(self, message: str, current_status: str = None):
        details = {"current_status": current_status} if current_status else {}
        super().__init__(
            message=message,
            error_code="INVALID_ORDER_STATUS",
            details=details
        )


class CancellationTimeExpiredError(OrderServiceException):
    """取消時限已過錯誤"""
    
    def __init__(self, message: str, created_at: str = None, time_limit_minutes: int = 10):
        details = {
            "created_at": created_at,
            "time_limit_minutes": time_limit_minutes
        } if created_at else {"time_limit_minutes": time_limit_minutes}
        super().__init__(
            message=message,
            error_code="CANCELLATION_TIME_EXPIRED",
            details=details
        )


# HTTP 例外對應
def to_http_exception(error: OrderServiceException) -> HTTPException:
    """將自定義例外轉換為 FastAPI HTTPException"""
    
    status_mapping = {
        "VALIDATION_ERROR": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "AUTHENTICATION_ERROR": status.HTTP_401_UNAUTHORIZED,
        "AUTHORIZATION_ERROR": status.HTTP_403_FORBIDDEN,
        "RESOURCE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "ORDER_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "INVALID_ORDER_STATUS": status.HTTP_400_BAD_REQUEST,
        "CANCELLATION_TIME_EXPIRED": status.HTTP_400_BAD_REQUEST,
        "BUSINESS_LOGIC_ERROR": status.HTTP_400_BAD_REQUEST,
        "DATABASE_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "EXTERNAL_SERVICE_ERROR": status.HTTP_503_SERVICE_UNAVAILABLE,
        "SAGA_EXECUTION_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    
    status_code = status_mapping.get(error.error_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    detail = {
        "error_code": error.error_code,
        "message": error.message,
        "details": error.details
    }
    
    return HTTPException(status_code=status_code, detail=detail)