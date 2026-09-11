"""初始資料庫結構

創建 Order Service 的四個核心資料表：
- orders: 訂單主表
- order_items: 訂單項目明細
- outbox: 事件發布表
- saga_steps: Saga 步驟追蹤表

Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-10-12 15:46:48

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    """升級：創建資料表"""
    
    # 創建 orders 表
    op.create_table('orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='訂單唯一識別碼'),
        sa.Column('user_id', sa.BigInteger(), nullable=False, comment='下單用戶ID'),
        sa.Column('menu_id', sa.BigInteger(), nullable=False, comment='菜單ID'),
        sa.Column('total_amount', sa.Integer(), nullable=False, comment='總金額(元)'),
        sa.Column('status', sa.String(length=20), nullable=False, comment='訂單狀態'),
        sa.Column('notes', sa.Text(), nullable=True, comment='使用者備註'),
        sa.Column('order_date', sa.Date(), nullable=False, comment='訂單日期'),
        sa.Column('saga_id', postgresql.UUID(as_uuid=True), nullable=False, comment='Saga流程追蹤ID'),
        sa.Column('reservation_id', postgresql.UUID(as_uuid=True), nullable=True, comment='庫存預留ID'),
        sa.Column('cancellation_reason', sa.Text(), nullable=True, comment='取消原因'),
        sa.Column('version', sa.Integer(), nullable=False, comment='樂觀鎖版本'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=True, comment='軟刪除標記'),
        sa.CheckConstraint('total_amount > 0', name='chk_total_amount_positive'),
        sa.CheckConstraint("status IN ('PENDING', 'INVENTORY_RESERVED', 'ON_CREDIT', 'COMPLETED', 'CANCELLED')", name='chk_status'),
        sa.CheckConstraint('char_length(notes) <= 500', name='chk_notes_length'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 創建 order_items 表
    op.create_table('order_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='項目唯一識別碼'),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=False, comment='關聯的訂單ID'),
        sa.Column('menu_item_id', sa.BigInteger(), nullable=False, comment='餐點ID'),
        sa.Column('menu_item_name', sa.String(length=100), nullable=False, comment='餐點名稱'),
        sa.Column('quantity', sa.Integer(), nullable=False, comment='數量'),
        sa.Column('unit_price', sa.Integer(), nullable=False, comment='單價(元)'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint('quantity > 0', name='chk_quantity_positive'),
        sa.CheckConstraint('unit_price > 0', name='chk_unit_price_positive'),
        sa.CheckConstraint('char_length(menu_item_name) <= 100', name='chk_menu_item_name_length'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 創建 outbox 表
    op.create_table('outbox',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='事件唯一識別碼'),
        sa.Column('aggregate_id', postgresql.UUID(as_uuid=True), nullable=False, comment='聚合根ID'),
        sa.Column('event_type', sa.String(length=100), nullable=False, comment='事件類型'),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='事件內容'),
        sa.Column('published', sa.Boolean(), nullable=True, comment='是否已發布'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 創建 saga_steps 表
    op.create_table('saga_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='步驟唯一識別碼'),
        sa.Column('saga_id', postgresql.UUID(as_uuid=True), nullable=False, comment='Saga流程ID'),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=True, comment='關聯的訂單ID'),
        sa.Column('step', sa.String(length=50), nullable=False, comment='步驟名稱'),
        sa.Column('state', sa.String(length=20), nullable=False, comment='步驟狀態'),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='步驟資料'),
        sa.Column('retry_count', sa.Integer(), nullable=True, comment='重試次數'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint("state IN ('PENDING', 'DONE', 'COMPENSATED', 'FAILED')", name='chk_state'),
        sa.CheckConstraint('retry_count >= 0', name='chk_retry_count_non_negative'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 創建索引
    op.create_index('idx_orders_user_date', 'orders', ['user_id', 'order_date'], unique=False)
    op.create_index('idx_orders_status', 'orders', ['status'], unique=False)
    op.create_index('idx_orders_saga', 'orders', ['saga_id'], unique=False)
    op.create_index('idx_orders_created_at', 'orders', ['created_at'], unique=False)
    
    op.create_index('idx_order_items_order_id', 'order_items', ['order_id'], unique=False)
    op.create_index('idx_order_items_menu_item', 'order_items', ['menu_item_id'], unique=False)
    
    op.create_index('idx_outbox_unpublished', 'outbox', ['created_at'], unique=False, postgresql_where=sa.text('published = false'))
    op.create_index('idx_outbox_aggregate', 'outbox', ['aggregate_id'], unique=False)
    op.create_index('idx_outbox_event_type', 'outbox', ['event_type'], unique=False)
    
    op.create_index('idx_saga_steps_saga_id', 'saga_steps', ['saga_id', 'step'], unique=False)
    op.create_index('idx_saga_steps_state', 'saga_steps', ['state', 'created_at'], unique=False)
    op.create_index('idx_saga_steps_order_id', 'saga_steps', ['order_id'], unique=False)


def downgrade() -> None:
    """降級：刪除資料表"""
    
    # 刪除索引
    op.drop_index('idx_saga_steps_order_id', table_name='saga_steps')
    op.drop_index('idx_saga_steps_state', table_name='saga_steps')
    op.drop_index('idx_saga_steps_saga_id', table_name='saga_steps')
    
    op.drop_index('idx_outbox_event_type', table_name='outbox')
    op.drop_index('idx_outbox_aggregate', table_name='outbox')
    op.drop_index('idx_outbox_unpublished', table_name='outbox')
    
    op.drop_index('idx_order_items_menu_item', table_name='order_items')
    op.drop_index('idx_order_items_order_id', table_name='order_items')
    
    op.drop_index('idx_orders_created_at', table_name='orders')
    op.drop_index('idx_orders_saga', table_name='orders')
    op.drop_index('idx_orders_status', table_name='orders')
    op.drop_index('idx_orders_user_date', table_name='orders')
    
    # 刪除表格（注意外鍵依賴順序）
    op.drop_table('saga_steps')
    op.drop_table('outbox')
    op.drop_table('order_items')
    op.drop_table('orders')
