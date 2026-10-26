<script setup>
import { ref,computed } from 'vue';
import { useRoute,useRouter } from 'vue-router';
import { checkout, state } from '../state.js';
import CheckoutConfirm from './CheckoutConfirm.vue';
import { money } from '../lib/cart.js';
import CartPanel from './CartPanel.vue';
import MealOptions from './MealOptions.vue';
const route=useRoute(),router=useRouter();
const store=computed(()=>state.menus.find(s=>String(s.id)===route.params.id));
const selected=ref(null), confirming=ref(false);let trigger=null;
const checkoutError=ref(''), checkoutBusy=ref(false);
function open(item,event){trigger=event.currentTarget;selected.value=item;}
function close(){selected.value=null;trigger?.focus();}
function requestOrder(){if(state.user?.role!=='employee')return;if(state.carts[store.value.id]?.length){checkoutError.value='';confirming.value=true;}}
async function order(){if(!confirming.value||checkoutBusy.value)return;checkoutBusy.value=true;checkoutError.value='';try{await checkout(store.value);confirming.value=false;router.push('/orders');}catch(error){checkoutError.value=error.message;}finally{checkoutBusy.value=false;}}
</script>
<template>
 <section v-if="store">
  <RouterLink class="back" to="/">← 返回所有菜單</RouterLink>
  <div class="store-intro"><div><p class="eyebrow">{{ store.category }}</p><h1>{{ store.name }}</h1><p>價格與供應狀態由 Meal 後端即時提供。</p></div></div>
  <p v-if="state.user?.role === 'admin'" class="admin-preview-note">管理員預覽模式。員工下單請使用員工帳號登入。</p>
  <div class="layout">
   <section><div class="section-head"><h2>店家菜單</h2><span>{{ store.items.length }} 款餐點</span></div>
    <div v-if="!store.items.length" class="empty order">目前沒有可供應餐點。</div>
    <button v-for="item in store.items" :key="item.id" class="menu-item meal-button" aria-haspopup="dialog" :disabled="state.user?.role !== 'employee'" @click="open(item,$event)">
     <span class="item-copy"><strong>{{ item.name }}</strong><span class="item-description">{{ item.category }}</span><span class="price">{{ money(item.price) }}</span></span><span v-if="state.user?.role === 'employee'" class="customize-link">加入餐袋 ＋</span>
    </button>
   </section>
   <CartPanel v-if="state.user?.role === 'employee'" :store="store" @checkout="requestOrder" />
  </div>
  <MealOptions v-if="selected" :key="selected.id" :item="selected" :store-id="store.id" @close="close" />
  <CheckoutConfirm v-if="confirming" :store="store" :busy="checkoutBusy" :error="checkoutError" @cancel="confirming=false" @confirm="order" />
 </section>
 <section v-else class="empty order"><p>找不到這份菜單，或它目前已不開放。</p><RouterLink class="text-link" to="/">返回菜單總覽</RouterLink></section>
</template>
