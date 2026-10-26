from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.menu_db_service import MenuDatabaseService
from app.models import Menu, MenuItem
from app.schemas import MenuCreate, MenuItemCreate, MenuItemUpdate, MenuUpdate


class FakeMenuResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeMenuSession:
    def __init__(self, *, menu=None, item=None, menus=None):
        self.menu = menu
        self.item = item
        self.menus = menus or []
        self.added = []
        self.statement = None
        self.committed = False
        self.rolled_back = False

    def add(self, value):
        self.added.append(value)

    async def scalar(self, statement):
        self.statement = statement
        return self.item if isinstance(self.item, MenuItem) else self.menu

    async def scalars(self, statement):
        self.statement = statement
        return FakeMenuResult(self.menus)

    async def commit(self):
        self.committed = True

    async def refresh(self, value):
        now = datetime.now(timezone.utc)
        if value.id is None:
            value.id = 10
        if value.is_active is None:
            value.is_active = True
        if value.created_at is None:
            value.created_at = now
        if value.updated_at is None:
            value.updated_at = now

    async def rollback(self):
        self.rolled_back = True


def test_menu_and_item_schemas_validate_price_and_availability_window():
    with pytest.raises(ValueError):
        MenuItemCreate(name="Tea", category="drink", price=0)

    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="available_until"):
        MenuCreate(name="Lunch", available_from=now, available_until=now)
    with pytest.raises(ValueError, match="時區"):
        MenuCreate(name="Lunch", available_from=datetime(2026, 10, 16, 9, 0))


@pytest.mark.asyncio
async def test_public_menu_query_filters_inactive_and_out_of_window_menus():
    item = MenuItem(
        id=101, menu_id=1, name="Beef noodles", category="main", price=125,
        is_active=True,
    )
    menu = Menu(id=1, name="Lunch", is_active=True, items=[item])
    db = FakeMenuSession(menus=[menu])

    result = await MenuDatabaseService(db).list_available_menus()

    compiled = str(db.statement.compile(dialect=postgresql.dialect()))
    assert result == [menu]
    assert "menus.is_active IS true" in compiled
    assert "available_from" in compiled and "available_until" in compiled


@pytest.mark.asyncio
async def test_admin_can_update_price_and_soft_disable_item():
    item = MenuItem(
        id=101, menu_id=1, name="Beef noodles", category="main", price=125,
        is_active=True,
    )
    db = FakeMenuSession(item=item)

    updated = await MenuDatabaseService(db).update_menu_item(
        1, 101, MenuItemUpdate(price=140, is_active=False)
    )

    assert updated.price == 140
    assert updated.is_active is False
    assert db.committed


@pytest.mark.asyncio
async def test_invalid_menu_period_update_is_rejected_before_commit():
    now = datetime.now(timezone.utc)
    menu = Menu(
        id=1, name="Lunch", is_active=True,
        available_from=now, available_until=now + timedelta(hours=1),
    )
    db = FakeMenuSession(menu=menu)

    with pytest.raises(HTTPException) as error:
        await MenuDatabaseService(db).update_menu(
            1, MenuUpdate(available_from=now + timedelta(hours=2))
        )

    assert error.value.status_code == 422
    assert not db.committed
