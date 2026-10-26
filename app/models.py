"""
Order Service SQLAlchemy 資料模型

包含四個核心資料表：
1. Order - 訂單主表
2. OrderItem - 訂單項目明細
3. Outbox - 事件發布表 (Outbox Pattern)
4. SagaStep - Saga 步驟追蹤表
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean, 
    Column,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    CheckConstraint,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped
from sqlalchemy.sql import func

from .database import Base


# 枚舉類型定義
class OrderStatus(str, Enum):
    """訂單狀態枚舉"""
    PENDING = "PENDING"                    # 訂單剛建立，等待庫存檢查
    INVENTORY_RESERVED = "INVENTORY_RESERVED"  # 庫存已預留，準備賒帳處理
    ON_CREDIT = "ON_CREDIT"               # 賒帳已記錄，餐點製作中
    COMPLETED = "COMPLETED"               # 訂單完成，確定扣款
    CANCELLED = "CANCELLED"               # 訂單取消，不扣款


class SagaStepState(str, Enum):
    """Saga 步驟狀態枚舉"""
    PENDING = "PENDING"           # 步驟等待執行
    DONE = "DONE"                # 步驟執行成功
    COMPENSATED = "COMPENSATED"   # 步驟已執行補償動作
    FAILED = "FAILED"            # 步驟執行失敗，無法補償


class UserRole(str, Enum):
    EMPLOYEE = "employee"
    ADMIN = "admin"


class User(Base):
    """可登入的使用者；角色由資料庫決定，不從註冊請求接受。"""
    __tablename__ = "users"

    id: Mapped[int] = Column(BigInteger, Identity(), primary_key=True)
    username: Mapped[str] = Column(String(50), nullable=False)
    password_hash: Mapped[str] = Column(String(255), nullable=False)
    role: Mapped[str] = Column(String(20), nullable=False, default=UserRole.EMPLOYEE.value)
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("role IN ('employee', 'admin')", name="chk_users_role"),
        UniqueConstraint("username", name="uq_users_username"),
        Index("idx_users_role", "role"),
    )


class Menu(Base):
    """菜單資料與有效期間。"""
    __tablename__ = "menus"

    id: Mapped[int] = Column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = Column(String(100), nullable=False)
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True, server_default="true")
    available_from: Mapped[Optional[datetime]] = Column(DateTime(timezone=True), nullable=True)
    available_until: Mapped[Optional[datetime]] = Column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    items: Mapped[List["MenuItem"]] = relationship(
        "MenuItem", back_populates="menu", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "available_until IS NULL OR available_from IS NULL OR available_until > available_from",
            name="chk_menus_valid_period",
        ),
    )


class MenuItem(Base):
    """菜單餐點；下架採軟停用，保留訂單歷史參照。"""
    __tablename__ = "menu_items"

    id: Mapped[int] = Column(BigInteger, Identity(), primary_key=True)
    menu_id: Mapped[int] = Column(
        BigInteger, ForeignKey("menus.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = Column(String(100), nullable=False)
    category: Mapped[str] = Column(String(50), nullable=False)
    price: Mapped[int] = Column(Integer, nullable=False)
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True, server_default="true")
    available_from: Mapped[Optional[datetime]] = Column(DateTime(timezone=True), nullable=True)
    available_until: Mapped[Optional[datetime]] = Column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    menu: Mapped[Menu] = relationship("Menu", back_populates="items")

    __table_args__ = (
        CheckConstraint("price > 0", name="chk_menu_items_price_positive"),
        CheckConstraint(
            "available_until IS NULL OR available_from IS NULL OR available_until > available_from",
            name="chk_menu_items_valid_period",
        ),
        UniqueConstraint("menu_id", "name", name="uq_menu_items_menu_name"),
        Index("idx_menu_items_menu_active", "menu_id", "is_active"),
    )


class Order(Base):
    """
    訂單主表
    
    儲存訂單的基本資訊，是整個訂單處理流程的核心
    """
    __tablename__ = "orders"

    # 主鍵和標識
    id: Mapped[uuid.UUID] = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="訂單唯一識別碼"
    )
    
    # 業務相關欄位
    user_id: Mapped[int] = Column(
        BigInteger, 
        nullable=False,
        comment="下單用戶ID (來自 Auth Service)"
    )
    
    menu_id: Mapped[int] = Column(
        BigInteger, 
        nullable=False,
        comment="菜單ID (來自 Menu Service)"
    )
    
    total_amount: Mapped[int] = Column(
        Integer, 
        nullable=False,
        comment="總金額 (以元為單位，例如：300表示300元)"
    )
    
    status: Mapped[OrderStatus] = Column(
        String(20), 
        nullable=False,
        default=OrderStatus.PENDING,
        comment="訂單狀態"
    )
    
    notes: Mapped[Optional[str]] = Column(
        Text,
        comment="使用者備註 (最多500字元)"
    )
    
    order_date: Mapped[datetime] = Column(
        Date, 
        nullable=False,
        default=func.current_date(),
        comment="訂單日期 (用於報表查詢)"
    )
    
    # 分散式協調相關
    saga_id: Mapped[uuid.UUID] = Column(
        UUID(as_uuid=True), 
        nullable=False,
        default=uuid.uuid4,
        comment="Saga流程追蹤ID"
    )
    
    reservation_id: Mapped[Optional[uuid.UUID]] = Column(
        UUID(as_uuid=True),
        comment="庫存預留ID (對應 Inventory Service)"
    )
    
    cancellation_reason: Mapped[Optional[str]] = Column(
        Text,
        comment="取消原因"
    )
    
    # 併發控制和審計
    version: Mapped[int] = Column(
        Integer, 
        nullable=False, 
        default=1,
        comment="樂觀鎖版本控制"
    )
    
    created_at: Mapped[datetime] = Column(
        DateTime(timezone=True), 
        server_default=func.now(),
        comment="建立時間"
    )
    
    updated_at: Mapped[datetime] = Column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新時間"
    )
    
    is_deleted: Mapped[bool] = Column(
        Boolean, 
        default=False,
        comment="軟刪除標記"
    )
    
    # 關聯關係
    items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem", 
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    saga_steps: Mapped[List["SagaStep"]] = relationship(
        "SagaStep",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="select"
    )

    # 表級約束
    __table_args__ = (
        CheckConstraint('total_amount > 0', name='chk_total_amount_positive'),
        CheckConstraint("status IN ('PENDING', 'INVENTORY_RESERVED', 'ON_CREDIT', 'COMPLETED', 'CANCELLED')", name='chk_status'),
        CheckConstraint('char_length(notes) <= 500', name='chk_notes_length'),
        Index('idx_orders_user_date', 'user_id', 'order_date'),
        Index('idx_orders_status', 'status'),
        Index('idx_orders_saga', 'saga_id'),
        Index('idx_orders_created_at', 'created_at'),
    )

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, user_id={self.user_id}, total_amount={self.total_amount}, status={self.status})>"


class OrderItem(Base):
    """
    訂單項目明細表
    
    儲存訂單中每個餐點的詳細資訊
    """
    __tablename__ = "order_items"

    # 主鍵和外鍵
    id: Mapped[uuid.UUID] = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="項目唯一識別碼"
    )
    
    order_id: Mapped[uuid.UUID] = Column(
        UUID(as_uuid=True), 
        ForeignKey('orders.id', ondelete='CASCADE'), 
        nullable=False,
        comment="關聯的訂單ID"
    )
    
    # 餐點資訊
    menu_item_id: Mapped[int] = Column(
        BigInteger, 
        nullable=False,
        comment="餐點ID (來自 Menu Service)"
    )
    
    menu_item_name: Mapped[str] = Column(
        String(100), 
        nullable=False,
        comment="餐點名稱 (冗餘儲存，提升查詢效能)"
    )
    
    quantity: Mapped[int] = Column(
        Integer, 
        nullable=False,
        comment="數量"
    )
    
    unit_price: Mapped[int] = Column(
        Integer, 
        nullable=False,
        comment="單價 (以元為單位，例如：120表示120元)"
    )
    
    # 計算欄位 - 使用 Python 屬性計算，避免資料庫複雜性
    @property
    def subtotal(self) -> int:
        """小計 = 數量 × 單價"""
        return self.quantity * self.unit_price
    
    created_at: Mapped[datetime] = Column(
        DateTime(timezone=True), 
        server_default=func.now(),
        comment="建立時間"
    )
    
    # 關聯關係
    order: Mapped["Order"] = relationship("Order", back_populates="items")

    # 表級約束
    __table_args__ = (
        CheckConstraint('quantity > 0', name='chk_quantity_positive'),
        CheckConstraint('unit_price > 0', name='chk_unit_price_positive'),
        CheckConstraint('char_length(menu_item_name) <= 100', name='chk_menu_item_name_length'),
        Index('idx_order_items_order_id', 'order_id'),
        Index('idx_order_items_menu_item', 'menu_item_id'),
    )

    def __repr__(self) -> str:
        return f"<OrderItem(id={self.id}, menu_item_name={self.menu_item_name}, quantity={self.quantity}, unit_price={self.unit_price})>"


class Outbox(Base):
    """
    事件發布表 (Outbox Pattern)
    
    實現資料庫操作與事件發布的原子性，確保最終一致性
    """
    __tablename__ = "outbox"

    # 主鍵
    id: Mapped[uuid.UUID] = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="事件唯一識別碼"
    )
    
    # 事件資訊
    aggregate_id: Mapped[uuid.UUID] = Column(
        UUID(as_uuid=True), 
        nullable=False,
        comment="聚合根ID (通常是訂單ID)"
    )
    
    event_type: Mapped[str] = Column(
        String(100), 
        nullable=False,
        comment="事件類型 (如: order.created, inventory.reserve.requested)"
    )
    
    payload: Mapped[dict] = Column(
        JSONB, 
        nullable=False,
        comment="事件內容 (JSON格式)"
    )
    
    published: Mapped[bool] = Column(
        Boolean, 
        default=False,
        comment="是否已發布到訊息佇列"
    )
    
    created_at: Mapped[datetime] = Column(
        DateTime(timezone=True), 
        server_default=func.now(),
        comment="事件建立時間"
    )

    # 表級約束和索引
    __table_args__ = (
        Index('idx_outbox_unpublished', 'created_at', postgresql_where='published = false'),
        Index('idx_outbox_aggregate', 'aggregate_id'),
        Index('idx_outbox_event_type', 'event_type'),
    )

    def __repr__(self) -> str:
        return f"<Outbox(id={self.id}, event_type={self.event_type}, published={self.published})>"


class InventoryStock(Base):
    """目前可售庫存；menu_item_id 由 Menu Service 管理。"""
    __tablename__ = "inventory_stocks"

    menu_item_id: Mapped[int] = Column(BigInteger, primary_key=True)
    available_quantity: Mapped[int] = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("available_quantity >= 0", name="chk_inventory_quantity_non_negative"),
    )


class InventoryMovement(Base):
    """庫存異動帳本；負數為下單扣庫存，正數為補貨或取消回補。"""
    __tablename__ = "inventory_movements"

    id: Mapped[uuid.UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    menu_item_id: Mapped[int] = Column(
        BigInteger, ForeignKey("inventory_stocks.menu_item_id", ondelete="RESTRICT"), nullable=False
    )
    order_id: Mapped[Optional[uuid.UUID]] = Column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    quantity_delta: Mapped[int] = Column(Integer, nullable=False)
    reason: Mapped[str] = Column(String(30), nullable=False)
    created_at: Mapped[datetime] = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("quantity_delta <> 0", name="chk_inventory_movement_nonzero"),
        CheckConstraint(
            "(reason = 'ORDER_PLACED' AND quantity_delta < 0) OR "
            "(reason IN ('RESTOCK', 'ORDER_CANCELLED') AND quantity_delta > 0)",
            name="chk_inventory_movement_reason_sign",
        ),
        Index("idx_inventory_movements_item_created", "menu_item_id", "created_at"),
        Index("idx_inventory_movements_order", "order_id"),
    )


class SagaStep(Base):
    """
    Saga 步驟追蹤表
    
    追蹤 Saga 流程中每個步驟的執行狀態，支援補償機制
    """
    __tablename__ = "saga_steps"

    # 主鍵
    id: Mapped[uuid.UUID] = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="步驟唯一識別碼"
    )
    
    # Saga 流程資訊
    saga_id: Mapped[uuid.UUID] = Column(
        UUID(as_uuid=True), 
        nullable=False,
        comment="Saga 流程ID"
    )
    
    order_id: Mapped[Optional[uuid.UUID]] = Column(
        UUID(as_uuid=True), 
        ForeignKey('orders.id', ondelete='CASCADE'),
        comment="關聯的訂單ID (可選，某些步驟可能不關聯特定訂單)"
    )
    
    # 步驟詳情
    step: Mapped[str] = Column(
        String(50), 
        nullable=False,
        comment="步驟名稱 (如: CREATE_ORDER, RESERVE_INVENTORY)"
    )
    
    state: Mapped[SagaStepState] = Column(
        String(20), 
        nullable=False,
        default=SagaStepState.PENDING,
        comment="步驟狀態"
    )
    
    payload: Mapped[Optional[dict]] = Column(
        JSONB,
        comment="步驟相關資料 (JSON格式)"
    )
    
    retry_count: Mapped[int] = Column(
        Integer, 
        default=0,
        comment="重試次數"
    )
    
    created_at: Mapped[datetime] = Column(
        DateTime(timezone=True), 
        server_default=func.now(),
        comment="建立時間"
    )
    
    updated_at: Mapped[datetime] = Column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新時間"
    )
    
    # 關聯關係
    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="saga_steps")

    # 表級約束
    __table_args__ = (
        CheckConstraint("state IN ('PENDING', 'DONE', 'COMPENSATED', 'FAILED')", name='chk_state'),
        CheckConstraint('retry_count >= 0', name='chk_retry_count_non_negative'),
        Index('idx_saga_steps_saga_id', 'saga_id', 'step'),
        Index('idx_saga_steps_state', 'state', 'created_at'),
        Index('idx_saga_steps_order_id', 'order_id'),
    )

    def __repr__(self) -> str:
        return f"<SagaStep(id={self.id}, saga_id={self.saga_id}, step={self.step}, state={self.state})>"
