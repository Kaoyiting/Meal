<script setup>
import { computed,ref } from 'vue';
import { state,cancelOrder } from '../state.js';
import { money } from '../lib/cart.js';
import OrderDetails from './OrderDetails.vue';
const statusMap={placed:'已下單',preparing:'製作中',delivered:'已送達',completed:'已完成',cancelled:'已取消'};
const from=ref(''),to=ref(''),selected=ref(null),message=ref('');
const dateText=value=>new Intl.DateTimeFormat('zh-TW',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));
const filtered=computed(()=>state.orders.filter(order=>{
 const time=new Date(order.createdAt).getTime();
 const start=from.value?new Date(`${from.value}T00:00:00`).getTime():-Infinity;
 const end=to.value?new Date(`${to.value}T23:59:59`).getTime():Infinity;
 return time>=start&&time<=end;
}).sort((a,b)=>new Date(b.createdAt)-new Date(a.createdAt)));
const active=computed(()=>filtered.value.filter(o=>['placed','preparing','delivered'].includes(o.status)));
const history=computed(()=>filtered.value.filter(o=>['completed','cancelled'].includes(o.status)));
async function cancel(order){try{await cancelOrder(order);message.value='訂單已取消，庫存已由系統回補。';}catch(error){message.value=error.message;}}
</script>
<template><section v-if="state.user?.role === 'employee'" class="orders-page"><div class="orders-heading"><div><p class="eyebrow">YOUR ORDERS</p><h1>我的訂單</h1><p>訂單記錄由 Meal API 讀取，可依日期篩選。</p></div><div class="date-filter"><label>開始日期<input v-model="from" type="date" :max="to||undefined"></label><span>至</span><label>結束日期<input v-model="to" type="date" :min="from||undefined"></label><button v-if="from||to" type="button" @click="from='';to=''">清除</button></div></div>
<div v-if="!filtered.length" class="empty order"><p>這段期間沒有訂單。</p><button v-if="from||to" class="text-button" @click="from='';to=''">查看全部訂單</button></div>
<section v-if="active.length" class="order-group"><div class="section-head"><h2>進行中</h2><span>{{ active.length }} 筆</span></div><button v-for="order in active" :key="order.id" class="order-card" @click="selected=order"><div><span :class="['order-status',order.status]">{{ statusMap[order.status] }}</span><h3>{{ order.storeName }}</h3><p>訂單 #{{ order.id }} · {{ dateText(order.createdAt) }}</p></div><div class="order-summary"><strong>{{ money(order.total) }}</strong><span>查看明細</span></div></button></section>
<section v-if="history.length" class="order-group"><div class="section-head"><h2>歷史訂單</h2><span>{{ history.length }} 筆</span></div><button v-for="order in history" :key="order.id" class="order-card history-card" @click="selected=order"><div><span :class="['order-status',order.status]">{{ statusMap[order.status] }}</span><h3>{{ order.storeName }}</h3><p>訂單 #{{ order.id }} · {{ dateText(order.createdAt) }}</p></div><div class="order-summary"><strong>{{ money(order.total) }}</strong><span>查看明細</span></div></button></section>
<p v-if="message" role="status" class="order-message">{{ message }}</p><OrderDetails v-if="selected" :order="selected" @close="selected=null" @cancel="cancel(selected)" /></section><section v-else class="empty order">訂單查詢只提供員工帳號使用。</section></template>
