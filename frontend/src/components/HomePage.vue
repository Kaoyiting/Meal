<script setup>
import { state } from '../state.js';
</script>
<template>
 <section id="home-view">
  <div class="intro"><div><p class="eyebrow">YOUR EVERYDAY TABLE</p><h1>今天，想吃點什麼？</h1><p>{{ state.user?.role === 'admin' ? '管理員可以預覽菜單，並從上方進入管理工作台。' : '選一家喜歡的店，把今天照顧好。' }}</p></div></div>
  <div class="section-head"><h2>{{ state.user?.role === 'admin' ? '菜單總覽' : '探索店家' }}</h2><span>{{ state.menus.length }} 份菜單</span></div>
  <div v-if="!state.menus.length" class="empty order">目前沒有開放的菜單。</div>
  <div class="restaurants">
   <RouterLink v-for="store in state.menus" :key="store.id" :to="`/stores/${store.id}`" :class="['restaurant','vue-store-card',store.theme]">
    <div class="store-color"><h2>{{ store.name }}</h2></div>
    <div class="restaurant-body"><p>{{ store.items.length }} 款餐點 · {{ store.category }}</p><div class="restaurant-bottom"><span class="plain-menu-link">{{ store.is_active ? '查看菜單' : '目前已停用' }}</span></div></div>
   </RouterLink>
  </div>
 </section>
</template>
