"""Add stock balances and auditable inventory movements.

Revision ID: 002_inventory
Revises: 001_initial_schema
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "002_inventory"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_stocks",
        sa.Column("menu_item_id", sa.BigInteger(), nullable=False),
        sa.Column("available_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("available_quantity >= 0", name="chk_inventory_quantity_non_negative"),
        sa.PrimaryKeyConstraint("menu_item_id"),
    )
    op.create_table(
        "inventory_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menu_item_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity_delta <> 0", name="chk_inventory_movement_nonzero"),
        sa.CheckConstraint(
            "(reason = 'ORDER_PLACED' AND quantity_delta < 0) OR "
            "(reason IN ('RESTOCK', 'ORDER_CANCELLED') AND quantity_delta > 0)",
            name="chk_inventory_movement_reason_sign",
        ),
        sa.ForeignKeyConstraint(["menu_item_id"], ["inventory_stocks.menu_item_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_inventory_movements_item_created", "inventory_movements", ["menu_item_id", "created_at"])
    op.create_index("idx_inventory_movements_order", "inventory_movements", ["order_id"])


def downgrade() -> None:
    op.drop_index("idx_inventory_movements_order", table_name="inventory_movements")
    op.drop_index("idx_inventory_movements_item_created", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_table("inventory_stocks")
