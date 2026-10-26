import test from 'node:test';
import assert from 'node:assert/strict';
import { addLine, totalOf, configure } from '../src/lib/cart.js';
import { addToCart, cancelOrder, checkout, state } from '../src/state.js';

test('購物車限制數量並正確計算顯示金額', () => {
  const cart = [];
  const item = { id: 42, name: '測試餐點', price: 95, options: [] };
  const selection = configure(item, {}, '醬料另外放');

  addLine(cart, selection, 2);
  assert.equal(totalOf(cart), 190);
  assert.equal(cart[0].note, '醬料另外放');
  assert.throws(() => addLine(cart, selection, 9), /最多 10 份/);
});

test('下單只送出餐點 ID 與數量，顯示資料採用伺服器回傳的價格', async () => {
  const originalFetch = globalThis.fetch;
  const originalStorage = globalThis.localStorage;
  const tokenStore = new Map([['meal.accessToken', 'test-token']]);
  globalThis.localStorage = {
    getItem: (key) => tokenStore.get(key) ?? null,
    setItem: (key, value) => tokenStore.set(key, value),
    removeItem: (key) => tokenStore.delete(key),
  };

  const createdAt = new Date().toISOString();
  const serverOrder = {
    id: '11111111-1111-4111-8111-111111111111',
    user_id: 8,
    menu_id: 5,
    total_amount: 375,
    status: 'PENDING',
    notes: '牛肉麵：醬料另外放\n牛肉麵：不要香菜',
    order_date: '2026-10-23',
    saga_id: '22222222-2222-4222-8222-222222222222',
    reservation_id: null,
    cancellation_reason: null,
    version: 1,
    created_at: createdAt,
    updated_at: createdAt,
    items: [{
      id: '33333333-3333-4333-8333-333333333333',
      menu_item_id: 101,
      menu_item_name: '牛肉麵',
      quantity: 3,
      unit_price: 125,
      subtotal: 375,
      created_at: createdAt,
    }],
  };
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url: String(url), options });
    if (String(url).includes('/orders/history')) {
      return new Response(JSON.stringify({ orders: [serverOrder], pagination: { total: 1 } }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response(JSON.stringify(serverOrder), {
      status: 201, headers: { 'Content-Type': 'application/json' },
    });
  };

  try {
    const menu = { id: 5, name: '整合測試菜單', items: [] };
    state.user = { id: 8, role: 'employee' };
    state.menus = [menu];
    state.carts = { 5: [] };
    state.orders = [];
    addToCart(5, {
      itemId: 101, name: '牛肉麵', unitPrice: 1, labels: [], note: '醬料另外放', key: 'beef-note',
    }, 2);
    addToCart(5, {
      itemId: 101, name: '牛肉麵', unitPrice: 1, labels: [], note: '不要香菜', key: 'beef-no-coriander',
    }, 1);

    const order = await checkout(menu);
    const body = JSON.parse(requests[0].options.body);
    assert.equal(requests[0].options.method, 'POST');
    assert.deepEqual(body.items, [{ menu_item_id: 101, quantity: 3 }]);
    assert.equal(body.menu_id, 5);
    assert.equal(body.notes, '牛肉麵：醬料另外放\n牛肉麵：不要香菜');
    assert.equal('unit_price' in body.items[0], false);
    assert.equal(order.total, 375);
    assert.equal(order.items[0].unitPrice, 125);
    assert.equal(state.carts[5].length, 0);
    assert.equal(state.orders[0].status, 'placed');

    const cancelledOrder = { ...serverOrder, status: 'CANCELLED', cancellation_reason: '由 Meal 前端取消' };
    globalThis.fetch = async (url) => new Response(JSON.stringify(
      String(url).includes('/cancel') ? cancelledOrder : { orders: [cancelledOrder], pagination: { total: 1 } },
    ), { status: 200, headers: { 'Content-Type': 'application/json' } });
    assert.equal(await cancelOrder(state.orders[0]), true);
    assert.equal(state.orders[0].status, 'cancelled');
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.localStorage = originalStorage;
    state.user = null;
    state.menus = [];
    state.carts = {};
    state.orders = [];
  }
});
