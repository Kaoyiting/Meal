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
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, desc, func
from sqlalchemy.orm import selectinload

from app.models import Order, OrderItem, SagaStep, OrderStatus, SagaStepState
from app.schemas import (
    OrderCreate, OrderResponse, OrderItemResponse, 
    OrderCancelRequest, OrderHistoryResponse, OrderStatistics,
    MonthlySummary, UserOrderHistoryResponse
)
from app.exceptions import (
    BusinessLogicError, 
    InvalidOrderStatusError,
    OrderNotFoundError,
    ValidationError,
    CancellationTimeExpiredError
)
from app.menu_service import menu_service

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
        1. 驗證前端計算的總金額
        2. 建立訂單記錄
        3. 模擬發布庫存扣減事件（日誌）
        4. 建立 Saga 追蹤記錄
        
        Args:
            request: 訂單建立請求
            user_id: 用戶ID (來自 JWT)
            
        Returns:
            OrderResponse: 建立的訂單資訊
            
        Raises:
            ValidationError: 總金額不符
            BusinessLogicError: 業務邏輯錯誤
        """
        # 1. 菜單驗證：驗證菜單ID和所有餐點資訊
        logger.info(f"🔍 開始驗證菜單ID {request.menu_id} 和餐點資訊")
        
        # 驗證菜單ID存在
        if not menu_service.validate_menu_exists(request.menu_id):
            raise ValidationError(f"無效的菜單ID: {request.menu_id}，該菜單不存在")
        
        menu_name = menu_service.get_menu_name(request.menu_id)
        logger.info(f"📋 驗證菜單：{menu_name} (ID: {request.menu_id})")
        
        # 逐項驗證每個餐點
        for item in request.items:
            menu_service.validate_order_item(
                menu_id=request.menu_id,
                menu_item_id=item.menu_item_id,
                menu_item_name=item.menu_item_name,
                unit_price=item.unit_price
            )
        
        logger.info(f"✅ 菜單驗證完成，共驗證 {len(request.items)} 個餐點")
        
        # 2. 計算實際總金額並驗證
        calculated_total = sum(
            item.quantity * item.unit_price for item in request.items
        )
        if calculated_total != request.expected_total:
            raise ValidationError(
                f"總金額驗證失敗：前端計算 {request.expected_total}元，"
                f"後端計算 {calculated_total}元"
            )

        # 建立訂單主記錄
        order_id = uuid.uuid4()
        saga_id = uuid.uuid4()
        
        order = Order(
            id=order_id,
            user_id=user_id,
            menu_id=request.menu_id,
            total_amount=calculated_total,
            status=OrderStatus.PENDING,
            notes=request.notes,
            order_date=date.today(),
            saga_id=saga_id
        )
        
        self.db.add(order)

        # 建立訂單項目
        order_items = []
        for item_req in request.items:
            item = OrderItem(
                id=uuid.uuid4(),
                order_id=order_id,
                menu_item_id=item_req.menu_item_id,
                menu_item_name=item_req.menu_item_name,
                quantity=item_req.quantity,
                unit_price=item_req.unit_price
            )
            order_items.append(item)
            self.db.add(item)

        # 模擬發布庫存扣減事件（用日誌代替實際 RabbitMQ）
        await self._simulate_inventory_reserve_event(order, order_items)
        
        # 建立 Saga 追蹤
        await self._create_saga_step(
            saga_id=saga_id,
            step_name="inventory_reserve",
            state=SagaStepState.PENDING,
            context={"order_id": str(order_id), "action": "reserve_inventory"}
        )

        await self.db.commit()

        # 回傳訂單資訊
        return await self._build_order_response(order, order_items)

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
        order = await self._get_order_by_id(order_id, user_id)
        
        # 檢查訂單是否在 10 分鐘時限內
        current_time = datetime.now(timezone.utc)
        time_limit = order.created_at + timedelta(minutes=10)
        
        if current_time > time_limit:
            raise CancellationTimeExpiredError(
                f"訂單建立已超過 10 分鐘，無法取消。建立時間: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                created_at=order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                time_limit_minutes=10
            )
        
        # 檢查狀態
        if order.status != OrderStatus.PENDING:
            raise InvalidOrderStatusError(
                f"訂單狀態 {order.status.value} 無法取消"
            )

        # 更新訂單狀態
        order.status = OrderStatus.CANCELLED
        order.cancellation_reason = request.cancellation_reason
        order.version += 1  # 樂觀鎖

        # 模擬發布取消事件（用日誌代替實際 RabbitMQ）
        await self._simulate_order_cancelled_event(order)

        # 更新 Saga 步驟狀態
        await self._update_saga_step_status(
            order.saga_id,
            "inventory_reserve",
            SagaStepState.COMPENSATED
        )

        await self.db.commit()

        # 查詢完整訂單資訊回傳
        return await self.get_order_detail(order_id, user_id)

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

    async def _simulate_inventory_reserve_event(
        self, 
        order: Order, 
        items: List[OrderItem]
    ) -> None:
        """模擬發布庫存扣減事件（用日誌代替 RabbitMQ）"""
        event_payload = {
            "order_id": str(order.id),
            "user_id": order.user_id,
            "items": [
                {
                    "menu_item_id": item.menu_item_id,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price
                }
                for item in items
            ]
        }
        
        logger.info(
            f"🔄 模擬事件發布: inventory.reserve.requested | "
            f"訂單: {order.id} | 項目數: {len(items)} | "
            f"總金額: {order.total_amount}元"
        )
        logger.debug(f"事件內容: {event_payload}")

    async def _simulate_order_cancelled_event(self, order: Order) -> None:
        """模擬發布訂單取消事件（用日誌代替 RabbitMQ）"""
        event_payload = {
            "order_id": str(order.id),
            "user_id": order.user_id,
            "cancellation_reason": order.cancellation_reason,
            "cancelled_at": datetime.now().isoformat()
        }
        
        logger.info(
            f"🔄 模擬事件發布: order.cancelled | "
            f"訂單: {order.id} | 原因: {order.cancellation_reason}"
        )
        logger.debug(f"事件內容: {event_payload}")

    async def _create_saga_step(
        self,
        saga_id: uuid.UUID,
        step_name: str,
        state: SagaStepState,
        context: Dict
    ) -> None:
        """建立 Saga 步驟記錄"""
        saga_step = SagaStep(
            id=uuid.uuid4(),
            saga_id=saga_id,
            step=step_name,
            state=state,
            payload=context
        )
        
        self.db.add(saga_step)
        logger.info(f"📝 Saga 步驟記錄: {saga_id} -> {step_name} ({state.value})")

    async def _update_saga_step_status(
        self,
        saga_id: uuid.UUID,
        step_name: str,
        new_state: SagaStepState
    ) -> None:
        """更新 Saga 步驟狀態"""
        stmt = (
            update(SagaStep)
            .where(and_(
                SagaStep.saga_id == saga_id,
                SagaStep.step == step_name
            ))
            .values(state=new_state, updated_at=datetime.now())
        )
        
        await self.db.execute(stmt)
        logger.info(f"📝 Saga 步驟更新: {saga_id} -> {step_name} ({new_state.value})")


class MockEventHandlerService:
    """
    模擬事件處理服務
    
    在實際的 RabbitMQ 整合完成前，用這個類別模擬外部事件回應
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def simulate_inventory_reserved(
        self, 
        order_id: uuid.UUID, 
        success: bool,
        message: Optional[str] = None
    ) -> None:
        """
        模擬庫存扣減完成事件
        
        Args:
            order_id: 訂單ID
            success: 是否成功
            message: 結果訊息
        """
        logger.info(
            f"🎭 模擬外部事件: inventory.reserved | "
            f"訂單: {order_id} | 成功: {success} | 訊息: {message}"
        )
        
        # 查詢訂單
        stmt = select(Order).where(Order.id == order_id)
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()
        
        if not order:
            logger.warning(f"訂單 {order_id} 不存在，忽略事件")
            return

        if success:
            # 庫存扣減成功，確認訂單
            order.status = OrderStatus.INVENTORY_RESERVED
            logger.info(f"✅ 訂單 {order_id} 庫存預留成功")
        else:
            # 庫存不足，取消訂單
            order.status = OrderStatus.CANCELLED
            order.cancellation_reason = message or "庫存不足"
            logger.info(f"❌ 訂單 {order_id} 庫存預留失敗：{message}")

        order.version += 1
        
        # 更新 Saga 步驟狀態
        await self._update_saga_step_status(
            order.saga_id,
            "inventory_reserve",
            SagaStepState.DONE if success else SagaStepState.FAILED
        )

        await self.db.commit()

    async def _update_saga_step_status(
        self,
        saga_id: uuid.UUID,
        step_name: str,
        new_state: SagaStepState
    ) -> None:
        """更新 Saga 步驟狀態"""
        stmt = (
            update(SagaStep)
            .where(and_(
                SagaStep.saga_id == saga_id,
                SagaStep.step == step_name
            ))
            .values(state=new_state, updated_at=datetime.now())
        )
        
        await self.db.execute(stmt)
        logger.info(f"📝 Saga 步驟更新: {saga_id} -> {step_name} ({new_state.value})")