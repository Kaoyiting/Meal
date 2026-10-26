"""PostgreSQL-backed menu queries and management operations."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Menu, MenuItem
from app.schemas import MenuCreate, MenuItemCreate, MenuItemUpdate, MenuUpdate


def _availability_conditions(model, now: datetime):
    return (
        or_(model.available_from.is_(None), model.available_from <= now),
        or_(model.available_until.is_(None), model.available_until > now),
    )


class MenuDatabaseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_available_menus(self) -> list[Menu]:
        now = datetime.now(timezone.utc)
        item_conditions = _availability_conditions(MenuItem, now)
        menu_conditions = _availability_conditions(Menu, now)
        statement = (
            select(Menu)
            .where(Menu.is_active.is_(True), *menu_conditions)
            .options(selectinload(Menu.items.and_(MenuItem.is_active.is_(True), *item_conditions)))
            .order_by(Menu.id)
        )
        return list((await self.db.scalars(statement)).all())

    async def get_available_menu(self, menu_id: int) -> Menu:
        now = datetime.now(timezone.utc)
        item_conditions = _availability_conditions(MenuItem, now)
        menu_conditions = _availability_conditions(Menu, now)
        statement = (
            select(Menu)
            .where(Menu.id == menu_id, Menu.is_active.is_(True), *menu_conditions)
            .options(selectinload(Menu.items.and_(MenuItem.is_active.is_(True), *item_conditions)))
        )
        menu = await self.db.scalar(statement)
        if menu is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="菜單不存在或目前未開放")
        return menu

    async def list_all_menus(self) -> list[Menu]:
        statement = select(Menu).options(selectinload(Menu.items)).order_by(Menu.id)
        return list((await self.db.scalars(statement)).all())

    async def get_menu_for_admin(self, menu_id: int) -> Menu:
        statement = (
            select(Menu).where(Menu.id == menu_id).options(selectinload(Menu.items))
        )
        menu = await self.db.scalar(statement)
        if menu is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="菜單不存在")
        return menu

    async def create_menu(self, request: MenuCreate) -> Menu:
        menu = Menu(**request.model_dump())
        self.db.add(menu)
        await self.db.commit()
        await self.db.refresh(menu)
        return menu

    async def update_menu(self, menu_id: int, request: MenuUpdate) -> Menu:
        menu = await self.get_menu_for_admin(menu_id)
        changes = request.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(status_code=422, detail="至少提供一個要修改的欄位")
        self._validate_merged_period(menu.available_from, menu.available_until, changes)
        for field, value in changes.items():
            if field in {"name", "is_active"} and value is None:
                raise HTTPException(status_code=422, detail="菜單名稱與狀態不可為空")
            setattr(menu, field, value)
        await self.db.commit()
        await self.db.refresh(menu)
        return menu

    async def create_menu_item(self, menu_id: int, request: MenuItemCreate) -> MenuItem:
        await self.get_menu_for_admin(menu_id)
        item = MenuItem(menu_id=menu_id, **request.model_dump())
        self.db.add(item)
        try:
            await self.db.commit()
            await self.db.refresh(item)
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此菜單已有相同名稱的餐點",
            ) from exc
        return item

    async def update_menu_item(
        self, menu_id: int, item_id: int, request: MenuItemUpdate
    ) -> MenuItem:
        statement = select(MenuItem).where(
            MenuItem.id == item_id, MenuItem.menu_id == menu_id
        )
        item = await self.db.scalar(statement)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="餐點不存在")
        changes = request.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(status_code=422, detail="至少提供一個要修改的欄位")
        if any(
            value is None
            for key, value in changes.items()
            if key in {"name", "category", "price", "is_active"}
        ):
            raise HTTPException(status_code=422, detail="餐點名稱、分類與價格不可為空")
        self._validate_merged_period(item.available_from, item.available_until, changes)
        for field, value in changes.items():
            setattr(item, field, value)
        try:
            await self.db.commit()
            await self.db.refresh(item)
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此菜單已有相同名稱的餐點",
            ) from exc
        return item

    @staticmethod
    def _validate_merged_period(current_from, current_until, changes) -> None:
        available_from = changes.get("available_from", current_from)
        available_until = changes.get("available_until", current_until)
        if available_from and available_until and available_until <= available_from:
            raise HTTPException(status_code=422, detail="available_until 必須晚於 available_from")
