<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { api } from '../lib/api.js';
import { money } from '../lib/cart.js';
import { refreshMenus, state } from '../state.js';

const menuName = ref('');
const message = ref('');
const error = ref('');
const busy = ref(false);
const newItem = reactive({ menuId: '', name: '', category: '主食', price: 100 });
const stocks = reactive({});
const restockAmounts = reactive({});
const movements = ref([]);
const movementsFor = ref(null);
const isAdmin = computed(() => state.user?.role === 'admin');

function clearFeedback() {
  message.value = '';
  error.value = '';
}

function showError(cause) {
  error.value = cause.message || '操作失敗，請稍後重試。';
}

async function loadStocks() {
  const items = state.menus.flatMap((menu) => menu.items);
  const results = await Promise.allSettled(items.map((item) => api(`/inventory/${item.id}`)));
  results.forEach((result, index) => {
    if (result.status === 'fulfilled') stocks[items[index].id] = result.value.available_quantity;
  });
}

async function reload() {
  clearFeedback();
  try {
    await refreshMenus();
    await loadStocks();
    message.value = '菜單與庫存已更新。';
  } catch (cause) {
    showError(cause);
  }
}

async function createMenu() {
  clearFeedback();
  busy.value = true;
  try {
    const created = await api('/admin/menus', { method: 'POST', body: { name: menuName.value.trim() } });
    menuName.value = '';
    await refreshMenus();
    newItem.menuId = String(created.id);
    message.value = '菜單已建立。';
  } catch (cause) {
    showError(cause);
  } finally {
    busy.value = false;
  }
}

async function createItem() {
  clearFeedback();
  busy.value = true;
  try {
    await api(`/admin/menus/${newItem.menuId}/items`, {
      method: 'POST',
      body: { name: newItem.name.trim(), category: newItem.category.trim(), price: Number(newItem.price) },
    });
    newItem.name = '';
    await refreshMenus();
    await loadStocks();
    message.value = '餐點已新增。';
  } catch (cause) {
    showError(cause);
  } finally {
    busy.value = false;
  }
}

async function updateMenu(menu) {
  clearFeedback();
  try {
    await api(`/admin/menus/${menu.id}`, { method: 'PATCH', body: { is_active: !menu.is_active } });
    await refreshMenus();
    await loadStocks();
    message.value = `「${menu.name}」已${menu.is_active ? '停用' : '啟用'}。`;
  } catch (cause) {
    showError(cause);
  }
}

async function updateItem(menu, item, patch) {
  clearFeedback();
  try {
    await api(`/admin/menus/${menu.id}/items/${item.id}`, { method: 'PATCH', body: patch });
    await refreshMenus();
    message.value = `「${item.name}」已更新。`;
  } catch (cause) {
    showError(cause);
  }
}

async function restock(item) {
  clearFeedback();
  const quantity = Number(restockAmounts[item.id]);
  if (!Number.isInteger(quantity) || quantity < 1) {
    error.value = '補貨數量請輸入大於 0 的整數。';
    return;
  }
  try {
    const stock = await api(`/admin/inventory/${item.id}/restock`, {
      method: 'POST', body: { quantity },
    });
    stocks[item.id] = stock.available_quantity;
    restockAmounts[item.id] = '';
    message.value = `「${item.name}」目前庫存 ${stock.available_quantity} 份。`;
  } catch (cause) {
    showError(cause);
  }
}

async function showMovements(item) {
  clearFeedback();
  try {
    movements.value = await api(`/admin/inventory/${item.id}/movements?limit=30`);
    movementsFor.value = item.name;
  } catch (cause) {
    showError(cause);
  }
}

onMounted(async () => {
  if (!isAdmin.value) return;
  if (!state.menus.length) await refreshMenus();
  if (!newItem.menuId && state.menus.length) newItem.menuId = String(state.menus[0].id);
  await loadStocks();
});
</script>

<template>
  <section v-if="isAdmin" class="admin-page">
    <div class="admin-heading">
      <div><p class="eyebrow">ADMIN WORKSPACE</p><h1>菜單與庫存</h1><p>維護資料庫菜單、餐點價格與可供應份數。</p></div>
      <button type="button" class="secondary-button" @click="reload">重新載入</button>
    </div>

    <p v-if="error" class="form-error admin-feedback" role="alert">{{ error }}</p>
    <p v-if="message" class="form-success admin-feedback" role="status">{{ message }}</p>

    <div class="admin-forms">
      <form class="admin-form" @submit.prevent="createMenu">
        <p class="eyebrow">MENU</p><h2>新增菜單</h2>
        <label for="menu-name">菜單名稱</label>
        <input id="menu-name" v-model="menuName" maxlength="100" required placeholder="例如：週五午餐">
        <button class="primary" :disabled="busy">建立菜單</button>
      </form>
      <form class="admin-form" @submit.prevent="createItem">
        <p class="eyebrow">MENU ITEM</p><h2>新增餐點</h2>
        <label for="item-menu">加入菜單</label>
        <select id="item-menu" v-model="newItem.menuId" required>
          <option v-for="menu in state.menus" :key="menu.id" :value="String(menu.id)">{{ menu.name }}</option>
        </select>
        <div class="form-row"><label>餐點名稱<input v-model="newItem.name" maxlength="100" required></label><label>分類<input v-model="newItem.category" maxlength="50" required></label></div>
        <label for="item-price">價格（元）</label><input id="item-price" v-model.number="newItem.price" type="number" min="1" step="1" required>
        <button class="primary" :disabled="busy || !state.menus.length">新增餐點</button>
      </form>
    </div>

    <section v-if="!state.menus.length" class="empty admin-empty">目前沒有菜單，先建立一份菜單。</section>
    <section v-for="menu in state.menus" :key="menu.id" class="admin-menu">
      <div class="admin-menu-head"><div><span class="eyebrow">MENU #{{ menu.id }}</span><h2>{{ menu.name }}</h2><span :class="['active-pill', menu.is_active ? 'on' : 'off']">{{ menu.is_active ? '供應中' : '已停用' }}</span></div><button type="button" class="secondary-button" @click="updateMenu(menu)">{{ menu.is_active ? '停用菜單' : '啟用菜單' }}</button></div>
      <div v-if="!menu.items.length" class="admin-empty">這份菜單還沒有餐點。</div>
      <div v-for="item in menu.items" :key="item.id" class="admin-item">
        <div class="admin-item-name"><strong>{{ item.name }}</strong><small>#{{ item.id }} · {{ item.category }} · {{ item.is_active ? '上架' : '已下架' }}</small></div>
        <label class="price-edit">價格<input :value="item.price" type="number" min="1" step="1" :aria-label="`${item.name}價格`" @change="updateItem(menu, item, { price: Number($event.target.value) })"><span>{{ money(item.price) }}</span></label>
        <div class="stock-editor"><span>庫存 <b>{{ stocks[item.id] ?? '…' }}</b></span><input v-model="restockAmounts[item.id]" type="number" min="1" step="1" placeholder="補貨數" :aria-label="`${item.name}補貨數量`"><button type="button" class="small-button" @click="restock(item)">補貨</button></div>
        <div class="admin-item-actions"><button type="button" class="text-button" @click="showMovements(item)">庫存紀錄</button><button type="button" class="text-button" @click="updateItem(menu, item, { is_active: !item.is_active })">{{ item.is_active ? '下架' : '重新上架' }}</button></div>
      </div>
    </section>

    <section v-if="movementsFor" class="movement-panel">
      <div class="section-head"><h2>{{ movementsFor }} · 最近庫存異動</h2><button class="text-button" type="button" @click="movementsFor = null">關閉</button></div>
      <p v-if="!movements.length" class="muted">目前沒有異動紀錄。</p>
      <div v-for="movement in movements" :key="movement.id" class="movement-row"><span>{{ new Date(movement.created_at).toLocaleString('zh-TW') }}</span><b :class="movement.quantity_delta > 0 ? 'stock-in' : 'stock-out'">{{ movement.quantity_delta > 0 ? '+' : '' }}{{ movement.quantity_delta }}</b><small>{{ movement.reason }}</small></div>
    </section>
  </section>
  <section v-else class="empty admin-empty">這個頁面只提供管理員使用。</section>
</template>
