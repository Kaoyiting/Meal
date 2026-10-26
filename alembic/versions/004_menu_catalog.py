"""Add database-backed menus and menu items.

Revision ID: 004_menu_catalog
Revises: 003_users_auth
"""
from alembic import op
import sqlalchemy as sa


revision = "004_menu_catalog"
down_revision = "003_users_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "menus",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("available_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "available_until IS NULL OR available_from IS NULL OR available_until > available_from",
            name="chk_menus_valid_period",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "menu_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("menu_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("available_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("price > 0", name="chk_menu_items_price_positive"),
        sa.CheckConstraint(
            "available_until IS NULL OR available_from IS NULL OR available_until > available_from",
            name="chk_menu_items_valid_period",
        ),
        sa.ForeignKeyConstraint(["menu_id"], ["menus.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("menu_id", "name", name="uq_menu_items_menu_name"),
    )
    op.create_index("idx_menu_items_menu_active", "menu_items", ["menu_id", "is_active"])

    menus = sa.table(
        "menus",
        sa.column("id", sa.BigInteger()),
        sa.column("name", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(menus, [
        {"id": 1, "name": "阿明麵食館", "is_active": True},
        {"id": 2, "name": "小華便當店", "is_active": True},
        {"id": 3, "name": "清心飲料店", "is_active": True},
        {"id": 4, "name": "老王湯麵店", "is_active": True},
    ])

    menu_items = sa.table(
        "menu_items",
        sa.column("id", sa.BigInteger()),
        sa.column("menu_id", sa.BigInteger()),
        sa.column("name", sa.String()),
        sa.column("category", sa.String()),
        sa.column("price", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )
    rows = [
        (101, 1, "牛肉麵", "主食", 125), (102, 1, "陽春麵", "主食", 70),
        (103, 1, "炸醬麵", "主食", 110), (104, 1, "滷蛋", "小菜", 15),
        (105, 1, "滷豆干", "小菜", 20), (106, 1, "泡菜", "小菜", 25),
        (201, 2, "雞腿便當", "主食", 120), (202, 2, "排骨便當", "主食", 110),
        (203, 2, "魚便當", "主食", 100), (204, 2, "可樂", "飲料", 25),
        (205, 2, "雪碧", "飲料", 25), (206, 2, "冰紅茶", "飲料", 30),
        (301, 3, "珍珠奶茶", "飲料", 50), (302, 3, "檸檬綠茶", "飲料", 35),
        (303, 3, "冬瓜茶", "飲料", 30), (304, 3, "芋頭奶茶", "飲料", 55),
        (305, 3, "多多綠茶", "飲料", 40),
        (401, 4, "酸辣湯麵", "主食", 100), (402, 4, "餛飩麵", "主食", 130),
        (403, 4, "紫菜蛋花湯", "湯類", 40), (404, 4, "酸辣湯", "湯類", 50),
        (405, 4, "海帶絲", "小菜", 30), (406, 4, "小黃瓜", "小菜", 25),
    ]
    op.bulk_insert(menu_items, [
        {"id": item_id, "menu_id": menu_id, "name": name,
         "category": category, "price": price, "is_active": True}
        for item_id, menu_id, name, category, price in rows
    ])
    op.execute("SELECT setval(pg_get_serial_sequence('menus', 'id'), (SELECT MAX(id) FROM menus))")
    op.execute("SELECT setval(pg_get_serial_sequence('menu_items', 'id'), (SELECT MAX(id) FROM menu_items))")


def downgrade() -> None:
    op.drop_index("idx_menu_items_menu_active", table_name="menu_items")
    op.drop_table("menu_items")
    op.drop_table("menus")
