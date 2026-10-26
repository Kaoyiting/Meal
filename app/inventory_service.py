"""資料庫庫存操作。呼叫端負責包住訂單／庫存的同一個交易。"""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import InsufficientInventoryError, InventoryReservationError, ValidationError
from app.models import InventoryMovement, InventoryStock, MenuItem


class InventoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def restock(self, menu_item_id: int, quantity: int) -> InventoryStock:
        if await self.db.get(MenuItem, menu_item_id) is None:
            raise ValidationError(f"無效的餐點ID: {menu_item_id}")

        stmt = insert(InventoryStock).values(
            menu_item_id=menu_item_id,
            available_quantity=quantity,
        ).on_conflict_do_update(
            index_elements=[InventoryStock.menu_item_id],
            set_={
                "available_quantity": InventoryStock.available_quantity + quantity,
                "updated_at": func.now(),
            },
        ).returning(InventoryStock)
        stock = (await self.db.execute(stmt)).scalar_one()
        self.db.add(InventoryMovement(
            menu_item_id=menu_item_id,
            quantity_delta=quantity,
            reason="RESTOCK",
        ))
        await self.db.flush()
        return stock

    async def deduct_for_order(self, menu_item_id: int, quantity: int, order_id: uuid.UUID) -> None:
        stmt = (
            update(InventoryStock)
            .where(
                InventoryStock.menu_item_id == menu_item_id,
                InventoryStock.available_quantity >= quantity,
            )
            .values(available_quantity=InventoryStock.available_quantity - quantity)
            .returning(InventoryStock.menu_item_id)
        )
        if (await self.db.execute(stmt)).scalar_one_or_none() is None:
            raise InsufficientInventoryError(menu_item_id)
        self.db.add(InventoryMovement(
            menu_item_id=menu_item_id,
            order_id=order_id,
            quantity_delta=-quantity,
            reason="ORDER_PLACED",
        ))

    async def restore_for_cancelled_order(self, order_id: uuid.UUID, items) -> None:
        """回補取消訂單的庫存；需在訂單狀態更新的同一交易內呼叫。"""
        result = await self.db.execute(
            select(InventoryMovement.menu_item_id, InventoryMovement.quantity_delta)
            .where(
                InventoryMovement.order_id == order_id,
                InventoryMovement.reason == "ORDER_PLACED",
            )
        )
        movements = result.all()
        # migration 前的舊訂單沒有實際扣庫存紀錄，取消時不應憑空增加庫存。
        if not movements:
            return
        reserved = {}
        for movement in movements:
            reserved[movement.menu_item_id] = reserved.get(movement.menu_item_id, 0) - movement.quantity_delta
        expected = {item.menu_item_id: item.quantity for item in items}
        if reserved != expected:
            raise InventoryReservationError(str(order_id))

        for item in sorted(items, key=lambda current: current.menu_item_id):
            stmt = (
                update(InventoryStock)
                .where(InventoryStock.menu_item_id == item.menu_item_id)
                .values(available_quantity=InventoryStock.available_quantity + item.quantity)
                .returning(InventoryStock.menu_item_id)
            )
            if (await self.db.execute(stmt)).scalar_one_or_none() is None:
                raise InsufficientInventoryError(item.menu_item_id)
            self.db.add(InventoryMovement(
                menu_item_id=item.menu_item_id,
                order_id=order_id,
                quantity_delta=item.quantity,
                reason="ORDER_CANCELLED",
            ))

    async def get_stock(self, menu_item_id: int) -> InventoryStock | None:
        return await self.db.get(InventoryStock, menu_item_id)

    async def list_movements(self, menu_item_id: int, limit: int = 100):
        stmt = (
            select(InventoryMovement)
            .where(InventoryMovement.menu_item_id == menu_item_id)
            .order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
            .limit(limit)
        )
        return (await self.db.execute(stmt)).scalars().all()
