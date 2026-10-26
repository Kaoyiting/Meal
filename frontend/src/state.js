import { reactive } from 'vue';
import { addLine, totalOf } from './lib/cart.js';
import { api, clearToken, getToken, setToken } from './lib/api.js';

const themes = ['morning', 'lunch', 'tea', 'soup'];
const symbols = ['早', '飯', '茶', '湯'];

export const state = reactive({
  user: null,
  initialized: false,
  loading: false,
  menus: [],
  carts: {},
  orders: [],
  notice: '',
});

function normalizeMenu(menu, index) {
  return {
    ...menu,
    category: menu.items?.[0]?.category || '今日供應',
    english: 'MEAL FOR TODAY',
    symbol: symbols[index % symbols.length],
    theme: themes[index % themes.length],
    description: '依照今天供應的菜單，挑選喜歡的餐點。',
    items: (menu.items || []).map((item) => ({
      ...item,
      description: item.category,
      options: [],
    })),
  };
}

function statusForUi(status) {
  if (status === 'PENDING' || status === 'INVENTORY_RESERVED') return 'placed';
  if (status === 'ON_CREDIT') return 'preparing';
  if (status === 'COMPLETED') return 'completed';
  if (status === 'CANCELLED') return 'cancelled';
  return 'placed';
}

function normalizeOrder(order) {
  const store = state.menus.find((menu) => menu.id === order.menu_id);
  const createdAt = order.created_at;
  return {
    id: order.id,
    menuId: order.menu_id,
    storeName: store?.name || `菜單 #${order.menu_id}`,
    items: (order.items || []).map((item) => ({
      key: item.id,
      itemId: item.menu_item_id,
      name: item.menu_item_name,
      unitPrice: item.unit_price,
      qty: item.quantity,
      labels: [],
    })),
    total: order.total_amount,
    status: statusForUi(order.status),
    rawStatus: order.status,
    notes: order.notes,
    cancellationReason: order.cancellation_reason,
    createdAt,
    updatedAt: order.updated_at,
    canCancel: order.status === 'PENDING' && Date.now() - new Date(createdAt).getTime() <= 10 * 60 * 1000,
  };
}

export async function refreshMenus() {
  if (!state.user) return;
  const path = state.user.role === 'admin' ? '/admin/menus' : '/menus';
  const menus = await api(path);
  state.menus = menus.map(normalizeMenu);
  for (const menu of state.menus) state.carts[menu.id] ||= [];
}

export async function refreshOrders() {
  if (!state.user || state.user.role !== 'employee') {
    state.orders = [];
    return;
  }
  const result = await api('/orders/history?page=1&page_size=100');
  state.orders = (result.orders || []).map(normalizeOrder)
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
}

async function loadUserData() {
  await refreshMenus();
  await refreshOrders();
}

export async function restoreSession() {
  if (!getToken()) {
    state.initialized = true;
    return;
  }
  state.loading = true;
  try {
    state.user = await api('/auth/me');
    await loadUserData();
  } catch (error) {
    clearToken();
    state.user = null;
    state.notice = error.message;
  } finally {
    state.loading = false;
    state.initialized = true;
  }
}

export async function login(username, password) {
  const result = await api('/auth/login', { method: 'POST', body: { username, password } });
  setToken(result.access_token);
  state.user = result.user;
  state.notice = '';
  await loadUserData();
}

export async function register(username, password) {
  return api('/auth/register', { method: 'POST', body: { username, password } });
}

export function logout() {
  clearToken();
  state.user = null;
  state.menus = [];
  state.orders = [];
  state.carts = {};
  state.notice = '';
}

export function addToCart(menuId, selection, quantity) {
  state.carts[menuId] ||= [];
  addLine(state.carts[menuId], selection, quantity);
}

export function changeQuantity(menuId, key, delta) {
  const cart = state.carts[menuId] || [];
  const index = cart.findIndex((item) => item.key === key);
  if (index < 0) return;
  cart[index].qty = Math.min(10, cart[index].qty + delta);
  if (cart[index].qty <= 0) cart.splice(index, 1);
}

export async function checkout(menu) {
  const cart = state.carts[menu.id] || [];
  if (!cart.length) return null;

  const notes = cart.filter((item) => item.note)
    .map((item) => `${item.name}：${item.note}`)
    .join('\n');
  if (notes.length > 500) throw new Error('餐點備註總長度不可超過 500 字。');
  const quantities = new Map();
  for (const item of cart) quantities.set(item.itemId, (quantities.get(item.itemId) || 0) + item.qty);
  if ([...quantities.values()].some((quantity) => quantity > 99)) {
    throw new Error('同一道餐點的總數不能超過 99 份。');
  }

  const created = await api('/orders', {
    method: 'POST',
    body: {
      menu_id: menu.id,
      items: [...quantities].map(([menuItemId, quantity]) => ({ menu_item_id: menuItemId, quantity })),
      notes: notes || undefined,
    },
  });
  cart.splice(0);
  const order = normalizeOrder(created);
  state.orders.unshift(order);
  await refreshOrders();
  return order;
}

export async function cancelOrder(order) {
  const updated = await api(`/orders/${order.id}/cancel`, {
    method: 'PUT',
    body: { cancellation_reason: '由 Meal 前端取消' },
  });
  const normalized = normalizeOrder(updated);
  const index = state.orders.findIndex((item) => item.id === order.id);
  if (index >= 0) state.orders.splice(index, 1, normalized);
  return true;
}

export function totalForMenu(menuId) {
  return totalOf(state.carts[menuId] || []);
}
