<script setup>
import { computed } from 'vue';
import { state,changeQuantity } from '../state.js';
import { money,totalOf } from '../lib/cart.js';
const props=defineProps({store:Object});defineEmits(['checkout']);
const lines=computed(()=>state.carts[props.store.id]);
const count=computed(()=>lines.value.reduce((n,i)=>n+i.qty,0));
const total=computed(()=>totalOf(lines.value));
</script>
<template><aside><div class="basket"><p class="eyebrow">YOUR SELECTION</p><h2>我的餐袋 <span>{{ count }}</span></h2><p class="muted">{{ store.name }}</p><div v-if="!lines.length" class="empty">餐袋還空著。<br>選一道喜歡的餐點吧。</div><div v-for="line in lines" :key="line.key" class="cart-row"><div class="cart-top"><b>{{ line.name }}</b><span>{{ money(line.unitPrice*line.qty) }}</span></div><p class="cart-options">{{ line.labels.join('・') }}<template v-if="line.note"><br>備註：{{ line.note }}</template></p><div class="stepper"><button @click="changeQuantity(store.id,line.key,-1)" :aria-label="`減少${line.name}數量`">−</button><span>{{ line.qty }}</span><button @click="changeQuantity(store.id,line.key,1)" :disabled="line.qty>=10" :aria-label="`增加${line.name}數量`">＋</button></div></div><div class="total"><span>合計</span><strong>{{ money(total) }}</strong></div><button class="primary" :disabled="!count" @click="$emit('checkout')">確認下單 →</button><p class="subtle">各店餐點分開結帳。</p></div></aside></template>
