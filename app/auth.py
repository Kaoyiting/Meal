"""
Order Service JWT 認證模組

提供基本的 JWT token 生成、驗證和用戶資訊提取功能
用於 FastAPI 依賴注入系統
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from jose import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole

logger = logging.getLogger(__name__)

# FastAPI HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


class AuthService:
    """JWT 認證服務"""
    
    def __init__(self):
        self.settings = get_settings()
        self.secret_key = self.settings.JWT_SECRET_KEY
        self.algorithm = self.settings.JWT_ALGORITHM
        self.expire_hours = self.settings.JWT_EXPIRE_HOURS

    def create_access_token(
        self, 
        user_id: int, 
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        建立 JWT access token
        
        Args:
            user_id: 用戶ID
            additional_claims: 額外的 claims（可選）
            
        Returns:
            str: JWT token 字串
        """
        # 基本 payload
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": user_id,
            "iat": now,
            "exp": now + timedelta(hours=self.expire_hours),
        }
        
        # 加入額外的 claims
        if additional_claims:
            if {"user_id", "iat", "exp"}.intersection(additional_claims):
                raise ValueError("additional_claims 不可覆寫 user_id、iat 或 exp")
            payload.update(additional_claims)
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        
        logger.info(f"🔑 JWT token 已建立: user_id={user_id}")
        return token

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        驗證 JWT token
        
        Args:
            token: JWT token 字串
            
        Returns:
            Dict: 解碼後的 payload
            
        Raises:
            HTTPException: token 無效或過期
        """
        try:
            payload = jwt.decode(
                token, 
                self.secret_key, 
                algorithms=[self.algorithm]
            )
            
            # 檢查必要欄位
            user_id = payload.get("user_id")
            if not isinstance(user_id, int) or user_id <= 0:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token 的 user_id 無效"
                )
            
            logger.debug(f"🔓 JWT token 驗證成功: user_id={user_id}")
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("🔒 JWT token 已過期")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 已過期"
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"🔒 JWT token 無效: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 無效"
            )

    def get_current_user_id(self, token: str) -> int:
        """
        從 token 中提取用戶ID
        
        Args:
            token: JWT token 字串
            
        Returns:
            int: 用戶ID
        """
        payload = self.verify_token(token)
        return payload["user_id"]


# 全域認證服務實例
auth_service = AuthService()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    FastAPI 依賴注入函式：取得當前用戶資訊
    
    用法:
        @app.get("/protected")
        async def protected_route(user: dict = Depends(get_current_user)):
            return {"user_id": user["user_id"]}
    
    Args:
        credentials: HTTP Bearer credentials
        
    Returns:
        Dict: 包含用戶資訊的字典
        
    Raises:
        HTTPException: 認證失敗
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="請提供 Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = auth_service.verify_token(credentials.credentials)
    except HTTPException:
        raise

    user = await db.scalar(
        select(User).where(
            User.id == payload["user_id"],
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="使用者不存在或已停用",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "id": user.id,
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "token_data": payload,
    }


def get_current_user_id(current_user: Dict[str, Any] = Depends(get_current_user)) -> int:
    """
    FastAPI 依賴注入函式：取得當前用戶ID（簡化版）
    
    用法:
        @app.get("/orders")
        async def get_orders(user_id: int = Depends(get_current_user_id)):
            return await order_service.get_user_orders(user_id)
    
    Args:
        credentials: HTTP Bearer credentials
        
    Returns:
        int: 用戶ID
    """
    return current_user["user_id"]


def create_test_token(user_id: int = 123) -> str:
    """
    建立測試用 token（開發階段使用）
    
    Args:
        user_id: 測試用戶ID
        
    Returns:
        str: 測試 token
    """
    return auth_service.create_access_token(
        user_id=user_id,
        additional_claims={"test": True}
    )


# 可選的權限檢查函式（基本版本）
def require_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    要求管理員權限的依賴注入函式
    
    Args:
        current_user: 當前用戶資訊
        
    Returns:
        Dict: 用戶資訊
        
    Raises:
        HTTPException: 權限不足
    """
    user_id = current_user["user_id"]
    if current_user["role"] != UserRole.ADMIN.value:
        logger.warning("使用者 %s 嘗試存取管理員功能", user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理員權限"
        )
    logger.info("管理員 %s 存取授權", user_id)
    return current_user


def require_employee(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """要求員工角色；管理員 API 則使用 require_admin。"""
    if current_user["role"] != UserRole.EMPLOYEE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此功能僅限員工使用",
        )
    return current_user


def get_current_employee_id(
    employee: Dict[str, Any] = Depends(require_employee),
) -> int:
    return employee["user_id"]


# 工具函式
def decode_token_without_verify(token: str) -> Optional[Dict[str, Any]]:
    """
    解碼 token 但不驗證（用於偵錯）
    
    Args:
        token: JWT token
        
    Returns:
        Dict or None: payload 或 None
    """
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception as e:
        logger.error(f"Token 解碼失敗: {e}")
        return None
