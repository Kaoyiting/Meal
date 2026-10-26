"""使用者註冊、登入與管理員帳號建立。"""

from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole
from app.schemas import UserRegisterRequest


password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DUMMY_PASSWORD_HASH = password_context.hash("dummy password for constant-time account lookup")


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_context.verify(password, password_hash)


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_employee(self, request: UserRegisterRequest) -> User:
        existing = await self.db.scalar(select(User).where(User.username == request.username))
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="帳號已存在")

        user = User(
            username=request.username,
            password_hash=hash_password(request.password),
            role=UserRole.EMPLOYEE.value,
        )
        self.db.add(user)
        try:
            await self.db.commit()
            await self.db.refresh(user)
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="帳號已存在") from exc
        return user

    async def authenticate(self, username: str, password: str) -> User:
        user = await self.db.scalar(select(User).where(User.username == username))
        # 對不存在帳號也執行一次 hash verify，讓兩種錯誤的處理時間接近。
        password_matches = verify_password(
            password, user.password_hash if user else DUMMY_PASSWORD_HASH
        )
        if user is None or not user.is_active or not password_matches:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="帳號或密碼錯誤",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    async def create_admin(self, request: UserRegisterRequest) -> User:
        """僅供受信任的管理員建立 CLI 呼叫；公開註冊不接受角色欄位。"""
        existing = await self.db.scalar(select(User).where(User.username == request.username))
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="帳號已存在")
        user = User(
            username=request.username,
            password_hash=hash_password(request.password),
            role=UserRole.ADMIN.value,
        )
        self.db.add(user)
        try:
            await self.db.commit()
            await self.db.refresh(user)
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="帳號已存在") from exc
        return user
