from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from sqlalchemy.dialects import postgresql

from app import services
from app.exceptions import InsufficientInventoryError, InvalidOrderStatusError, ValidationError
from app.inventory_service import InventoryService
from app.models import InventoryMovement, InventoryStock, Menu, MenuItem, Order, OrderItem, OrderStatus
from app.schemas import OrderCancelRequest, OrderCreate


class FakeSession:
    def __init__(
        self, *, update_rowcount=1, inventory_stock=None, inventory_movement_rows=None,
        menu=None, menu_item=None,
    ):
        self.added = []
        self.statements = []
        self.inventory_actions = []
        self.committed = False
        self.rolled_back = False
        self.update_rowcount = update_rowcount
        self.inventory_stock = inventory_stock
        self.inventory_movement_rows = inventory_movement_rows or []
        self.menu = menu
        self.menu_item = menu_item

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        now = datetime.now(timezone.utc)
        for item in self.added:
            if isinstance(item, (Order, OrderItem, InventoryStock, InventoryMovement)):
                if getattr(item, "created_at", None) is None:
                    item.created_at = now
                if isinstance(item, (Order, InventoryStock)) and getattr(item, "updated_at", None) is None:
                    item.updated_at = now

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(
            rowcount=self.update_rowcount,
            scalar_one_or_none=lambda: 101,
            scalar_one=lambda: self.inventory_stock,
            all=lambda: self.inventory_movement_rows,
            scalars=lambda: SimpleNamespace(all=lambda: []),
        )

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.menu

    async def get(self, model, key):
        if model is InventoryStock:
            return self.inventory_stock
        if model is MenuItem:
            return self.menu_item
        return None


class StubInventoryService:
    def __init__(self, db):
        self.db = db

    async def deduct_for_order(self, menu_item_id, quantity, order_id):
        self.db.inventory_actions.append(("deduct", menu_item_id, quantity, order_id))

    async def restore_for_cancelled_order(self, order_id, items):
        self.db.inventory_actions.append(("restore", order_id, [(item.menu_item_id, item.quantity) for item in items]))


@pytest.mark.asyncio
async def test_create_order_uses_database_price_and_persists_price_snapshot(monkeypatch):
    item = MenuItem(id=101, menu_id=1, name="牛肉麵", category="主食", price=125, is_active=True)
    db = FakeSession(menu=Menu(id=1, name="阿明麵食館", is_active=True, items=[item]))
    monkeypatch.setattr(services, "InventoryService", StubInventoryService)
    request = OrderCreate(menu_id=1, items=[{"menu_item_id": 101, "quantity": 2}])

    response = await services.OrderService(db).create_order(request, user_id=8)

    assert response.total_amount == 250
    assert response.items[0].menu_item_name == "牛肉麵"
    assert response.items[0].unit_price == 125
    assert response.items[0].subtotal == 250
    assert db.inventory_actions[0][:3] == ("deduct", 101, 2)
    assert db.committed and not db.rolled_back


@pytest.mark.asyncio
async def test_new_order_uses_latest_database_price(monkeypatch):
    item = MenuItem(id=101, menu_id=1, name="牛肉麵", category="主食", price=140, is_active=True)
    db = FakeSession(menu=Menu(id=1, name="阿明麵食館", is_active=True, items=[item]))
    monkeypatch.setattr(services, "InventoryService", StubInventoryService)
    request = OrderCreate(menu_id=1, items=[{"menu_item_id": 101, "quantity": 2}])

    response = await services.OrderService(db).create_order(request, user_id=8)

    assert response.total_amount == 280
    assert response.items[0].unit_price == 140


@pytest.mark.asyncio
async def test_create_order_invalid_menu_item_creates_nothing(monkeypatch):
    item = MenuItem(id=201, menu_id=2, name="雞腿便當", category="主食", price=120, is_active=True)
    db = FakeSession(menu=Menu(id=1, name="阿明麵食館", is_active=True, items=[]))
    monkeypatch.setattr(services, "InventoryService", StubInventoryService)
    request = OrderCreate(menu_id=1, items=[{"menu_item_id": 201, "quantity": 1}])

    with pytest.raises(ValidationError):
        await services.OrderService(db).create_order(request, user_id=8)

    assert db.added == []
    assert not db.committed


@pytest.mark.asyncio
async def test_create_order_rejects_inactive_database_item(monkeypatch):
    item = MenuItem(id=101, menu_id=1, name="牛肉麵", category="主食", price=125, is_active=False)
    db = FakeSession(menu=Menu(id=1, name="阿明麵食館", is_active=True, items=[item]))
    monkeypatch.setattr(services, "InventoryService", StubInventoryService)
    request = OrderCreate(menu_id=1, items=[{"menu_item_id": 101, "quantity": 1}])

    with pytest.raises(ValidationError, match="未開放"):
        await services.OrderService(db).create_order(request, user_id=8)

    assert db.added == []
    assert not db.committed


def test_order_request_rejects_duplicate_item_ids():
    with pytest.raises(ValueError, match="合併數量"):
        OrderCreate(
            menu_id=1,
            items=[{"menu_item_id": 101, "quantity": 1}, {"menu_item_id": 101, "quantity": 2}],
        )


@pytest.mark.asyncio
async def test_create_order_rolls_back_when_stock_reservation_fails(monkeypatch):
    class InsufficientStockService(StubInventoryService):
        async def deduct_for_order(self, menu_item_id, quantity, order_id):
            raise InsufficientInventoryError(menu_item_id)

    item = MenuItem(id=101, menu_id=1, name="牛肉麵", category="主食", price=125, is_active=True)
    db = FakeSession(menu=Menu(id=1, name="阿明麵食館", is_active=True, items=[item]))
    monkeypatch.setattr(services, "InventoryService", InsufficientStockService)
    request = OrderCreate(menu_id=1, items=[{"menu_item_id": 101, "quantity": 1}])

    with pytest.raises(InsufficientInventoryError):
        await services.OrderService(db).create_order(request, user_id=8)

    assert db.rolled_back
    assert not db.committed


@pytest.mark.asyncio
async def test_cancel_restores_stock_once_and_marks_order_cancelled(monkeypatch):
    db = FakeSession()
    item = OrderItem(
        id=uuid.uuid4(), menu_item_id=101, quantity=2, unit_price=125,
        menu_item_name="牛肉麵", created_at=datetime.now(timezone.utc),
    )
    order = Order(
        id=uuid.uuid4(), user_id=8, menu_id=1, total_amount=250,
        status=OrderStatus.PENDING, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc), order_date=datetime.now().date(),
        saga_id=uuid.uuid4(), version=1, items=[item],
    )
    service = services.OrderService(db)
    cancelled_order = Order(
        id=order.id, user_id=8, menu_id=1, total_amount=250,
        status=OrderStatus.CANCELLED, created_at=order.created_at,
        updated_at=order.updated_at, order_date=order.order_date,
        saga_id=order.saga_id, version=2, items=[OrderItem(
            id=item.id, menu_item_id=item.menu_item_id, quantity=item.quantity,
            unit_price=item.unit_price, menu_item_name=item.menu_item_name,
            created_at=item.created_at,
        )],
        cancellation_reason="test",
    )
    monkeypatch.setattr(
        service,
        "_get_order_by_id_with_items",
        AsyncMock(side_effect=[order, cancelled_order]),
    )
    monkeypatch.setattr(services, "InventoryService", StubInventoryService)

    response = await service.cancel_order(order.id, OrderCancelRequest(cancellation_reason="test"), user_id=8)

    assert response.id == order.id
    assert db.inventory_actions == [("restore", order.id, [(101, 2)])]
    assert db.committed and not db.rolled_back


@pytest.mark.asyncio
async def test_cancel_conflict_rolls_back_stock_restore(monkeypatch):
    db = FakeSession(update_rowcount=0)
    item = OrderItem(menu_item_id=101, quantity=1, unit_price=125, menu_item_name="牛肉麵")
    order = Order(
        id=uuid.uuid4(), user_id=8, menu_id=1, total_amount=125,
        status=OrderStatus.PENDING, created_at=datetime.now(timezone.utc),
        order_date=datetime.now().date(), saga_id=uuid.uuid4(), version=1, items=[item],
    )
    service = services.OrderService(db)
    monkeypatch.setattr(service, "_get_order_by_id_with_items", AsyncMock(return_value=order))
    monkeypatch.setattr(services, "InventoryService", StubInventoryService)

    with pytest.raises(InvalidOrderStatusError):
        await service.cancel_order(order.id, OrderCancelRequest(cancellation_reason="test"), user_id=8)

    assert db.rolled_back and not db.committed


@pytest.mark.asyncio
async def test_admin_completion_changes_pending_order_to_completed():
    order = Order(
        id=uuid.uuid4(), user_id=8, menu_id=1, total_amount=125,
        status=OrderStatus.PENDING, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc), order_date=datetime.now().date(),
        saga_id=uuid.uuid4(), version=1, items=[OrderItem(
            id=uuid.uuid4(), menu_item_id=101, quantity=1, unit_price=125,
            menu_item_name="牛肉麵", created_at=datetime.now(timezone.utc),
        )],
    )

    class CompletionSession(FakeSession):
        async def execute(self, statement):
            self.statements.append(statement)
            if len(self.statements) == 1:
                return SimpleNamespace(scalar_one_or_none=lambda: order)
            return SimpleNamespace(rowcount=1)

    db = CompletionSession()
    response = await services.OrderService(db).complete_order(order.id)

    assert response.status == OrderStatus.COMPLETED
    assert response.version == 2
    assert db.committed and not db.rolled_back


@pytest.mark.asyncio
async def test_inventory_deduction_is_atomic_and_cannot_go_below_zero():
    db = FakeSession()
    await InventoryService(db).deduct_for_order(101, 3, uuid.uuid4())

    sql = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "available_quantity >=" in sql
    assert "available_quantity -" in sql
    assert db.added[0].quantity_delta == -3
    assert db.added[0].reason == "ORDER_PLACED"


@pytest.mark.asyncio
async def test_inventory_deduction_fails_when_stock_update_matches_no_row():
    class NoStockSession(FakeSession):
        async def execute(self, statement):
            self.statements.append(statement)
            return SimpleNamespace(scalar_one_or_none=lambda: None)

    with pytest.raises(InsufficientInventoryError):
        await InventoryService(NoStockSession()).deduct_for_order(101, 1, uuid.uuid4())


@pytest.mark.asyncio
async def test_restock_uses_upsert_and_writes_auditable_movement():
    stock = InventoryStock(menu_item_id=101, available_quantity=7)
    menu_item = MenuItem(id=101, menu_id=1, name="牛肉麵", category="主食", price=125, is_active=True)
    db = FakeSession(inventory_stock=stock, menu_item=menu_item)

    returned = await InventoryService(db).restock(menu_item_id=101, quantity=7)

    sql = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in sql
    assert returned.available_quantity == 7
    movement = next(row for row in db.added if isinstance(row, InventoryMovement))
    assert movement.quantity_delta == 7
    assert movement.reason == "RESTOCK"


@pytest.mark.asyncio
async def test_cancel_restore_requires_matching_stock_reservation_ledger():
    order_id = uuid.uuid4()
    db = FakeSession(inventory_movement_rows=[SimpleNamespace(menu_item_id=101, quantity_delta=-2)])
    item = OrderItem(menu_item_id=101, quantity=2)

    await InventoryService(db).restore_for_cancelled_order(order_id, [item])

    sql = str(db.statements[1].compile(dialect=postgresql.dialect()))
    assert "available_quantity +" in sql
    movement = next(row for row in db.added if isinstance(row, InventoryMovement))
    assert movement.order_id == order_id
    assert movement.quantity_delta == 2
    assert movement.reason == "ORDER_CANCELLED"


@pytest.mark.asyncio
async def test_old_order_without_stock_ledger_does_not_create_stock():
    db = FakeSession()

    await InventoryService(db).restore_for_cancelled_order(
        uuid.uuid4(), [OrderItem(menu_item_id=101, quantity=1)]
    )

    assert len(db.statements) == 1
    assert db.added == []
