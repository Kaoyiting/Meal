"""End-to-end order and inventory checks against an isolated PostgreSQL DB."""

from sqlalchemy import func, select

import pytest

from app.exceptions import InsufficientInventoryError, InvalidOrderStatusError
from app.inventory_service import InventoryService
from app.models import (
    InventoryMovement,
    InventoryStock,
    Menu,
    MenuItem,
    Order,
    OrderItem,
    OrderStatus,
)
from app.schemas import OrderCancelRequest, OrderCreate
from app.services import OrderService


pytestmark = pytest.mark.integration


async def create_catalog_item(session, *, price=125, stock=0):
    menu = Menu(name="整合測試菜單", is_active=True)
    session.add(menu)
    await session.flush()

    item = MenuItem(
        menu_id=menu.id,
        name="測試餐點",
        category="主食",
        price=price,
        is_active=True,
    )
    session.add(item)
    await session.flush()

    if stock:
        await InventoryService(session).restock(item.id, stock)
        await session.commit()
    return menu, item


def order_request(menu_id, menu_item_id, quantity):
    return OrderCreate(
        menu_id=menu_id,
        items=[{"menu_item_id": menu_item_id, "quantity": quantity}],
    )


@pytest.mark.asyncio
async def test_insufficient_stock_rolls_back_order_item_and_inventory_ledger(postgres_session):
    menu, item = await create_catalog_item(postgres_session, stock=1)
    item_id = item.id

    with pytest.raises(InsufficientInventoryError):
        await OrderService(postgres_session).create_order(
            order_request(menu.id, item.id, 2), user_id=51
        )

    assert await postgres_session.scalar(select(func.count()).select_from(Order)) == 0
    assert await postgres_session.scalar(select(func.count()).select_from(OrderItem)) == 0
    assert await postgres_session.scalar(
        select(InventoryStock.available_quantity).where(InventoryStock.menu_item_id == item_id)
    ) == 1
    assert await postgres_session.scalar(
        select(func.count()).select_from(InventoryMovement).where(
            InventoryMovement.menu_item_id == item_id,
            InventoryMovement.reason == "ORDER_PLACED",
        )
    ) == 0


@pytest.mark.asyncio
async def test_cancellation_restores_stock_once_and_duplicate_cancel_conflicts(postgres_session):
    menu, item = await create_catalog_item(postgres_session, stock=5)
    service = OrderService(postgres_session)
    order = await service.create_order(order_request(menu.id, item.id, 2), user_id=51)

    assert await postgres_session.scalar(
        select(InventoryStock.available_quantity).where(InventoryStock.menu_item_id == item.id)
    ) == 3

    cancelled = await service.cancel_order(
        order.id,
        OrderCancelRequest(cancellation_reason="整合測試取消"),
        user_id=51,
    )
    assert cancelled.status == OrderStatus.CANCELLED
    assert await postgres_session.scalar(
        select(InventoryStock.available_quantity).where(InventoryStock.menu_item_id == item.id)
    ) == 5

    with pytest.raises(InvalidOrderStatusError):
        await service.cancel_order(
            order.id,
            OrderCancelRequest(cancellation_reason="重複取消"),
            user_id=51,
        )

    assert await postgres_session.scalar(
        select(func.count()).select_from(InventoryMovement).where(
            InventoryMovement.order_id == order.id,
            InventoryMovement.reason == "ORDER_CANCELLED",
        )
    ) == 1
    assert await postgres_session.scalar(
        select(InventoryStock.available_quantity).where(InventoryStock.menu_item_id == item.id)
    ) == 5


@pytest.mark.asyncio
async def test_order_keeps_historical_price_and_next_order_uses_updated_price(postgres_session):
    menu, item = await create_catalog_item(postgres_session, price=125, stock=5)
    service = OrderService(postgres_session)

    old_order = await service.create_order(order_request(menu.id, item.id, 1), user_id=51)
    item.price = 140
    await postgres_session.commit()
    new_order = await service.create_order(order_request(menu.id, item.id, 1), user_id=51)

    assert old_order.total_amount == 125
    assert old_order.items[0].unit_price == 125
    assert new_order.total_amount == 140
    assert new_order.items[0].unit_price == 140

    stored_old_item = await postgres_session.scalar(
        select(OrderItem).where(OrderItem.order_id == old_order.id)
    )
    assert stored_old_item.menu_item_name == "測試餐點"
    assert stored_old_item.unit_price == 125
