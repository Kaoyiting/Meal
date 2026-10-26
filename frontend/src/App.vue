<script setup>
import { onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { state } from './state.js';
import { logout, restoreSession } from './state.js';
import AuthPage from './components/AuthPage.vue';

const route = useRoute();
function onAuthExpired() {
  logout();
  state.notice = '登入已逾時，請重新登入。';
}
onMounted(() => {
  window.addEventListener('meal:auth-expired', onAuthExpired);
  restoreSession();
});
onBeforeUnmount(() => window.removeEventListener('meal:auth-expired', onAuthExpired));
</script>
<template>
 <header>
  <RouterLink class="brand" to="/"><span class="mark">m.</span>Meal <small>好好吃飯</small></RouterLink>
  <nav v-if="state.user" aria-label="主要導覽">
   <RouterLink to="/">探索菜單</RouterLink>
   <RouterLink v-if="state.user.role === 'employee'" to="/orders">我的訂單 <span>{{ state.orders.length }}</span></RouterLink>
   <RouterLink v-if="state.user.role === 'admin'" to="/admin">菜單與庫存</RouterLink>
  </nav>
  <div v-if="state.user" class="account-bar"><span>{{ state.user.username }}<small>{{ state.user.role === 'admin' ? '管理員' : '員工' }}</small></span><button type="button" @click="logout">登出</button></div>
 </header>
 <main>
  <p v-if="state.notice" class="global-notice" role="status">{{ state.notice }}</p>
  <div v-if="!state.initialized || state.loading" class="loading-state">正在連線到 Meal…</div>
  <AuthPage v-else-if="!state.user" />
  <RouterView v-else :key="route.fullPath" />
 </main>
 <footer>Meal / 好好吃飯 <span>把日常，過得有滋有味。</span></footer>
</template>
