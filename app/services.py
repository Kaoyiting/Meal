"""
Order Service 業務邏輯層

功能範圍:
1. 訂單建立與價格驗證
2. 訂單狀態管理
3. 簡化版 Saga 追蹤（記錄步驟 + 日誌模擬事件）
4. 訂單取消處理
5. 歷史訂單查詢
6. 報表服務專用 API
"""
import uuid
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, desc, func, or_
from sqlalchemy.orm import selectinload

from app.models import Menu, MenuItem, Order, OrderItem, OrderStatus
from app.schemas import (
    OrderCreate, OrderResponse, OrderItemResponse, 
    OrderCancelRequest, OrderHistoryResponse, OrderStatistics,
    MonthlySummary, UserOrderHistoryResponse
)
from app.exceptions import (
    InvalidOrderStatusError,
    OrderNotFoundError,
    ValidationError,
    CancellationTimeExpiredError
)
from app.inventory_service import InventoryService

logger = logging.getLogger(__name__)


class OrderService:
    """訂單服務核心業務邏輯"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def create_order(
        self, 
        request: OrderCreate, 
        user_id: int
    ) -> OrderResponse:
        """
        建立新訂單
        
        流程:
        1. 從資料庫菜單驗證餐點並計算價格
        2. 在同一交易建立訂單與明細
        3. 原子扣減庫存並記錄異動
        4. 任一步驟失敗時回滾整筆交易
        
        Args:
            request: 訂單建立請求
            user_id: 用戶ID (來自 JWT)
            
        Returns:
            OrderResponse: 建立的訂單資訊
            
        Raises:
            ValidationError: 菜單或餐點無效
        """
        # 用資料庫中的有效菜單作為唯一價格來源；request 只提供 ID 和數量。
        now = datetime.now(timezone.utc)
        menu_statement = (
            select(Menu)
            .where(
                Menu.id == request.menu_id,
                Menu.is_active.is_(True),
                or_(Menu.available_from.is_(None), Menu.available_from <= now),
                or_(Menu.available_until.is_(None), Menu.available_until > now),
            )
            .options(selectinload(Menu.items.and_(
                MenuItem.is_active.is_(True),
                or_(MenuItem.available_from.is_(None), MenuItem.available_from <= now),
                or_(MenuItem.available_until.is_(None), MenuItem.available_until > now),
            )))
        )
        menu = await self.db.scalar(menu_statement)
        if menu is None or not self._is_available(menu, now):
            raise ValidationError(f"無效的菜單ID: {request.menu_id}，該菜單不存在")

        menu_items_by_id = {
            item.id: item for item in menu.items if self._is_available(item, now)
        }
        catalog_items = []
        for item_req in request.items:
            menu_item = menu_items_by_id.get(item_req.menu_item_id)
            if menu_item is None:
                raise ValidationError(
                    f"餐點ID {item_req.menu_item_id} 不屬於菜單ID {request.menu_id}，或目前未開放"
                )
            catalog_items.append((item_req, menu_item))

        calculated_total = sum(req.quantity * item.price for req, item in catalog_items)
        order_id = uuid.uuid4()
        order = Order(
            id=order_id,
            user_id=user_id,
            menu_id=request.menu_id,
            total_amount=calculated_total,
            status=OrderStatus.PENDING,
            notes=request.notes,
            order_date=datetime.now(ZoneInfo("Asia/Taipei")).date(),
            saga_id=uuid.uuid4(),
            version=1,
        )
        try:
            self.db.add(order)
            order_items = []
            for item_req, menu_item in catalog_items:
                item = OrderItem(
                    id=uuid.uuid4(),
                    order_id=order_id,
                    menu_item_id=item_req.menu_item_id,
                    menu_item_name=menu_item.name,
                    quantity=item_req.quantity,
                    unit_price=menu_item.price,
                )
                order_items.append(item)
                self.db.add(item)

            await self.db.flush()
            inventory = InventoryService(self.db)
            for item in sorted(order_items, key=lambda current: current.menu_item_id):
                await inventory.deduct_for_order(item.menu_item_id, item.quantity, order_id)
            response = await self._build_order_response(order, order_items)
            await self.db.commit()
            return response
        except Exception:
            await self.db.rollback()
            raise

    @staticmethod
    def _is_available(record, now: datetime) -> bool:
        return (
            record.is_active
            and (record.available_from is None or record.available_from <= now)
            and (record.available_until is None or record.available_until > now)
        )

    async def cancel_order(
        self, 
        order_id: uuid.UUID, 
        request: OrderCancelRequest,
        user_id: int
    ) -> OrderResponse:
        """
        取消訂單
        
        僅允許取消 PENDING 狀態的訂單
        
        Args:
            order_id: 訂單ID
            request: 取消請求
            user_id: 用戶ID
            
        Returns:
            OrderResponse: 更新後的訂單資訊
            
        Raises:
            OrderNotFoundError: 訂單不存在
            InvalidOrderStatusError: 訂單狀態不可取消
        """
        # 查詢訂單
        order = await self._get_order_by_id_with_items(order_id, user_id)
        
        # SQLite 測試資料或舊資料可能回傳 naive datetime，統一視為 UTC。
        current_time = datetime.now(timezone.utc)
        created_at = order.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        time_limit = created_at + timedelta(minutes=10)
        
        if current_time > time_limit:
            raise CancellationTimeExpiredError(
                f"訂單建立已超過 10 分鐘，無法取消。建立時間: {created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                created_at=created_at.strftime('%Y-%m-%d %H:%M:%S'),
                time_limit_minutes=10
            )
        
        # 檢查狀態
        if order.status != OrderStatus.PENDING:
            current_status = getattr(order.status, "value", order.status)
            raise InvalidOrderStatusError(
                f"訂單狀態 {current_status} 無法取消",
                current_status=current_status,
            )

        try:
            await InventoryService(self.db).restore_for_cancelled_order(order_id, order.items)
            result = await self.db.execute(
                update(Order)
                .where(Order.id == order_id, Order.user_id == user_id, Order.status == OrderStatus.PENDING)
                .values(
                    status=OrderStatus.CANCELLED,
                    cancellation_reason=request.cancellation_reason,
                    version=Order.version + 1,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            if result.rowcount != 1:
                raise InvalidOrderStatusError("訂單已被更新，無法重複取消")
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        # 查詢完整訂單資訊回傳
        return await self.get_order_detail(order_id, user_id)

    async def complete_order(self, order_id: uuid.UUID) -> OrderResponse:
        """管理員確認出餐完成；已完成或已取消的訂單不可重複轉換。"""
        stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()
        if order is None:
            raise OrderNotFoundError(f"訂單 {order_id} 不存在")
        if order.status != OrderStatus.PENDING:
            current_status = getattr(order.status, "value", order.status)
            raise InvalidOrderStatusError(
                f"訂單狀態 {current_status} 無法完成",
                current_status=current_status,
            )

        try:
            update_result = await self.db.execute(
                update(Order)
                .where(Order.id == order_id, Order.status == OrderStatus.PENDING)
                .values(
                    status=OrderStatus.COMPLETED,
                    version=Order.version + 1,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            if update_result.rowcount != 1:
                raise InvalidOrderStatusError("訂單已被更新，無法重複完成")
            order.status = OrderStatus.COMPLETED
            order.version += 1
            await self.db.commit()
            return await self._build_order_response(order, order.items)
        except Exception:
            await self.db.rollback()
            raise

    async def get_order_detail(
        self, 
        order_id: uuid.UUID, 
        user_id: int
    ) -> OrderResponse:
        """
        查詢訂單詳情
        
        Args:
            order_id: 訂單ID
            user_id: 用戶ID
            
        Returns:
            OrderResponse: 訂單詳情
            
        Raises:
            OrderNotFoundError: 訂單不存在
        """
        order = await self._get_order_by_id_with_items(order_id, user_id)
        return await self._build_order_response(order, order.items)

    async def get_order_history(
        self, 
        user_id: int,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> OrderHistoryResponse:
        """
        查詢用戶訂單歷史
        
        Args:
            user_id: 用戶ID
            from_date: 開始日期 (YYYY-MM-DD)
            to_date: 結束日期 (YYYY-MM-DD) 
            status: 訂單狀態篩選，多值用逗號分隔
            page: 頁數 (從1開始)
            page_size: 每頁筆數
            
        Returns:
            OrderHistoryResponse: 歷史訂單列表
        """
        offset = (page - 1) * page_size
        
        # 建立查詢條件
        conditions = [Order.user_id == user_id]
        
        # 日期範圍篩選
        if from_date:
            start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
            conditions.append(Order.order_date >= start_date)
            
        if to_date:
            end_date = datetime.strptime(to_date, "%Y-%m-%d").date()
            conditions.append(Order.order_date <= end_date)
            
        # 狀態篩選
        if status:
            status_list = [s.strip() for s in status.split(',')]
            conditions.append(Order.status.in_(status_list))
        
        # 查詢訂單列表 (含項目數)
        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .where(and_(*conditions))
            .order_by(desc(Order.created_at))
            .offset(offset)
            .limit(page_size)
        )
        
        result = await self.db.execute(stmt)
        orders = result.scalars().all()

        # 建立回應
        order_responses = []
        for order in orders:
            response = await self._build_order_response(order, order.items)
            order_responses.append(response)

        # 計算總數 (使用相同的篩選條件)
        count_stmt = (
            select(func.count(Order.id))
            .where(and_(*conditions))
        )
        count_result = await self.db.execute(count_stmt)
        total_count = count_result.scalar()
        
        total_pages = (total_count + page_size - 1) // page_size
        
        return OrderHistoryResponse(
            orders=order_responses,
            pagination={
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "filters": {
                    "from_date": from_date,
                    "to_date": to_date,
                    "status": status
                }
            }
        )

    async def get_order_statistics(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        group_by: str = "day",
        include_items: bool = False
    ) -> OrderStatistics:
        """
        查詢訂單統計
        
        Args:
            from_date: 開始日期 (YYYY-MM-DD)
            to_date: 結束日期 (YYYY-MM-DD)
            group_by: 統計維度 (day/week/month)
            include_items: 是否包含熱門餐點統計
            
        Returns:
            OrderStatistics: 統計資料
        """
        # 建立日期篩選條件
        conditions = []
        if from_date:
            start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
            conditions.append(Order.order_date >= start_date)
        if to_date:
            end_date = datetime.strptime(to_date, "%Y-%m-%d").date()
            conditions.append(Order.order_date <= end_date)

        # 基本統計查詢
        if conditions:
            stmt = select(
                func.count(Order.id).label('total_orders'),
                func.sum(Order.total_amount).label('total_amount'),
                func.count(Order.id).filter(Order.status == OrderStatus.COMPLETED).label('completed_orders'),
                func.count(Order.id).filter(Order.status == OrderStatus.CANCELLED).label('cancelled_orders')
            ).where(and_(*conditions))
        else:
            stmt = select(
                func.count(Order.id).label('total_orders'),
                func.sum(Order.total_amount).label('total_amount'),
                func.count(Order.id).filter(Order.status == OrderStatus.COMPLETED).label('completed_orders'),
                func.count(Order.id).filter(Order.status == OrderStatus.CANCELLED).label('cancelled_orders')
            )

        result = await self.db.execute(stmt)
        stats = result.first()

        total_orders = stats.total_orders or 0
        total_amount = int(stats.total_amount or 0)
        completed_orders = stats.completed_orders or 0
        cancelled_orders = stats.cancelled_orders or 0
        avg_order_amount = (total_amount / total_orders) if total_orders > 0 else 0.0

        # 熱門餐點統計 (可選)
        popular_items = None
        if include_items:
            popular_items = await self._get_popular_items(conditions)

        return OrderStatistics(
            period={
                "from": from_date or "開始",
                "to": to_date or "結束",
                "group_by": group_by
            },
            total_orders=total_orders,
            total_amount=total_amount,
            completed_orders=completed_orders,
            cancelled_orders=cancelled_orders,
            avg_order_amount=avg_order_amount,
            popular_items=popular_items
        )

    # =====================================
    # 報表服務專用方法 (Report Service APIs)
    # =====================================

    async def get_monthly_summary(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        include_details: bool = False
    ) -> MonthlySummary:
        """
        月底結帳總和 API - 專為報表服務設計
        
        Args:
            from_date: 開始日期 (YYYY-MM-DD)
            to_date: 結束日期 (YYYY-MM-DD) 
            include_details: 是否包含訂單明細
            
        Returns:
            MonthlySummary: 月度結帳總和資料
        """
        logger.info(f"📊 查詢月度總和報表: {from_date} ~ {to_date}, 包含明細: {include_details}")
        
        # 建立日期篩選條件
        conditions = []
        if from_date:
            start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
            conditions.append(Order.order_date >= start_date)
        if to_date:
            end_date = datetime.strptime(to_date, "%Y-%m-%d").date()
            conditions.append(Order.order_date <= end_date)

        # 查詢用戶訂單統計
        if conditions:
            stmt = (
                select(
                    Order.user_id,
                    func.count(Order.id).label('order_count'),
                    func.sum(Order.total_amount).label('total_amount')
                )
                .where(and_(*conditions))
                .group_by(Order.user_id)
            )
        else:
            stmt = (
                select(
                    Order.user_id,
                    func.count(Order.id).label('order_count'),
                    func.sum(Order.total_amount).label('total_amount')
                )
                .group_by(Order.user_id)
            )

        result = await self.db.execute(stmt)
        user_stats = result.all()

        # 組裝用戶資料
        users_data = []
        grand_total_orders = 0
        grand_total_amount = 0

        for user_stat in user_stats:
            user_id = user_stat.user_id
            order_count = user_stat.order_count
            total_amount = int(user_stat.total_amount or 0)
            
            user_data = {
                "userId": user_id,
                "userName": f"用戶_{user_id}",  # 實際應從 User Service 取得
                "orderCount": order_count,
                "totalAmount": total_amount
            }

            # 如果需要明細，查詢該用戶的訂單記錄
            if include_details:
                user_orders = await self._get_user_orders_for_report(
                    user_id, from_date, to_date
                )
                user_data["records"] = user_orders

            users_data.append(user_data)
            grand_total_orders += order_count
            grand_total_amount += total_amount

        return MonthlySummary(
            period={
                "from": from_date or "開始",
                "to": to_date or "結束"
            },
            users=users_data,
            grand_total={
                "order_count": grand_total_orders,
                "total_amount": grand_total_amount
            }
        )

    async def get_user_order_history_for_report(
        self,
        user_id: int,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        status: Optional[str] = None
    ) -> UserOrderHistoryResponse:
        """
        查詢用戶訂單記錄 API - 專為報表服務設計
        
        Args:
            user_id: 用戶ID
            from_date: 開始日期 (YYYY-MM-DD)
            to_date: 結束日期 (YYYY-MM-DD) 
            status: 訂單狀態篩選，多值用逗號分隔
            
        Returns:
            UserOrderHistoryResponse: 用戶訂單歷史資料
        """
        logger.info(f"📋 查詢用戶 {user_id} 訂單記錄: {from_date} ~ {to_date}")
        
        # 建立查詢條件
        conditions = [Order.user_id == user_id]
        
        # 日期範圍篩選
        if from_date:
            start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
            conditions.append(Order.order_date >= start_date)
        if to_date:
            end_date = datetime.strptime(to_date, "%Y-%m-%d").date()
            conditions.append(Order.order_date <= end_date)
            
        # 狀態篩選
        if status:
            status_list = [s.strip() for s in status.split(',')]
            conditions.append(Order.status.in_(status_list))

        # 查詢訂單列表（含項目）
        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .where(and_(*conditions))
            .order_by(desc(Order.order_date), desc(Order.created_at))
        )
        
        result = await self.db.execute(stmt)
        orders = result.scalars().all()

        # 建立訂單回應
        order_responses = []
        total_amount = 0
        
        for order in orders:
            response = await self._build_order_response(order, order.items)
            order_responses.append(response)
            total_amount += order.total_amount

        return UserOrderHistoryResponse(
            user_id=user_id,
            period={
                "from": from_date or "開始",
                "to": to_date or "結束"
            } if from_date or to_date else None,
            total_count=len(orders),
            total_amount=total_amount,
            orders=order_responses
        )

    # =====================================
    # 內部輔助方法 (Private Methods)
    # =====================================

    async def _get_order_by_id(
        self, 
        order_id: uuid.UUID, 
        user_id: int
    ) -> Order:
        """根據ID查詢訂單 (不含項目)"""
        stmt = select(Order).where(
            and_(Order.id == order_id, Order.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()
        
        if not order:
            raise OrderNotFoundError(f"訂單 {order_id} 不存在")
        
        return order

    async def _get_order_by_id_with_items(
        self, 
        order_id: uuid.UUID, 
        user_id: int
    ) -> Order:
        """根據ID查詢訂單 (含項目)"""
        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .where(and_(Order.id == order_id, Order.user_id == user_id))
        )
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()
        
        if not order:
            raise OrderNotFoundError(f"訂單 {order_id} 不存在")
        
        return order

    async def _build_order_response(
        self, 
        order: Order, 
        items: List[OrderItem]
    ) -> OrderResponse:
        """建構訂單回應物件"""
        item_responses = [
            OrderItemResponse(
                id=item.id,
                menu_item_id=item.menu_item_id,
                menu_item_name=item.menu_item_name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.subtotal,
                created_at=item.created_at
            )
            for item in items
        ]
        
        return OrderResponse(
            id=order.id,
            user_id=order.user_id,
            menu_id=order.menu_id,
            total_amount=order.total_amount,
            status=order.status,
            notes=order.notes,
            order_date=order.order_date,
            saga_id=order.saga_id,
            reservation_id=order.reservation_id,
            cancellation_reason=order.cancellation_reason,
            version=order.version,
            created_at=order.created_at,
            updated_at=order.updated_at,
            items=item_responses
        )

    async def _get_user_orders_for_report(
        self,
        user_id: int,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """取得用戶訂單明細（報表格式）"""
        conditions = [Order.user_id == user_id]
        
        if from_date:
            start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
            conditions.append(Order.order_date >= start_date)
        if to_date:
            end_date = datetime.strptime(to_date, "%Y-%m-%d").date()
            conditions.append(Order.order_date <= end_date)

        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .where(and_(*conditions))
            .order_by(desc(Order.order_date))
        )
        
        result = await self.db.execute(stmt)
        orders = result.scalars().all()

        records = []
        for order in orders:
            record = {
                "orderId": str(order.id),
                "orderDate": order.order_date.strftime("%Y-%m-%d"),
                "amount": order.total_amount,
                "status": order.status,
                "items": [
                    {
                        "menuItemName": item.menu_item_name,
                        "quantity": item.quantity,
                        "unitPrice": item.unit_price
                    }
                    for item in order.items
                ]
            }
            records.append(record)
            
        return records

    async def _get_popular_items(self, conditions: List) -> List[Dict[str, Any]]:
        """取得熱門餐點統計"""
        # 這裡可以實現熱門餐點的統計邏輯
        # 暫時回傳空列表，實際應根據訂單項目統計
        return []
