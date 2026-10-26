"""Menu read endpoints and admin CRUD routes."""

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.menu_db_service import MenuDatabaseService
from app.schemas import (
    MenuCreate,
    MenuItemCreate,
    MenuItemResponse,
    MenuItemUpdate,
    MenuResponse,
    MenuUpdate,
)


router = APIRouter()


@router.get("/menus", response_model=list[MenuResponse], summary="查詢目前開放的菜單")
async def list_menus(
    _current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await MenuDatabaseService(db).list_available_menus()


@router.get("/menus/{menu_id}", response_model=MenuResponse, summary="查詢目前開放的菜單")
async def get_menu(
    menu_id: int = Path(..., gt=0),
    _current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await MenuDatabaseService(db).get_available_menu(menu_id)


@router.get("/admin/menus", response_model=list[MenuResponse], summary="管理員查詢全部菜單")
async def admin_list_menus(
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await MenuDatabaseService(db).list_all_menus()


@router.get("/admin/menus/{menu_id}", response_model=MenuResponse, summary="管理員查詢菜單")
async def admin_get_menu(
    menu_id: int = Path(..., gt=0),
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await MenuDatabaseService(db).get_menu_for_admin(menu_id)


@router.post(
    "/admin/menus",
    response_model=MenuResponse,
    status_code=status.HTTP_201_CREATED,
    summary="管理員新增菜單",
)
async def create_menu(
    request: MenuCreate,
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await MenuDatabaseService(db).create_menu(request)


@router.patch(
    "/admin/menus/{menu_id}",
    response_model=MenuResponse,
    summary="管理員修改或下架菜單",
)
async def update_menu(
    request: MenuUpdate,
    menu_id: int = Path(..., gt=0),
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await MenuDatabaseService(db).update_menu(menu_id, request)


@router.post(
    "/admin/menus/{menu_id}/items",
    response_model=MenuItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="管理員新增餐點",
)
async def create_menu_item(
    request: MenuItemCreate,
    menu_id: int = Path(..., gt=0),
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await MenuDatabaseService(db).create_menu_item(menu_id, request)


@router.patch(
    "/admin/menus/{menu_id}/items/{item_id}",
    response_model=MenuItemResponse,
    summary="管理員修改餐點或下架餐點",
)
async def update_menu_item(
    request: MenuItemUpdate,
    menu_id: int = Path(..., gt=0),
    item_id: int = Path(..., gt=0),
    _admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await MenuDatabaseService(db).update_menu_item(menu_id, item_id, request)
