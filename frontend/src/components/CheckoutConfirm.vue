<script setup>
import { ref,computed,onMounted,onBeforeUnmount } from 'vue';
import { state } from '../state.js';
import { money,totalOf } from '../lib/cart.js';
const props=defineProps({store:Object,busy:Boolean,error:String});const emit=defineEmits(['cancel','confirm']);
const dialog=ref(null),cancelButton=ref(null);
const lines=computed(()=>state.carts[props.store.id]);
const total=computed(()=>totalOf(lines.value));
let previousFocus=null;
onMounted(()=>{previousFocus=document.activeElement;dialog.value.showModal();document.body.classList.add('modal-open');cancelButton.value.focus();});
onBeforeUnmount(()=>{dialog.value?.close();document.body.classList.remove('modal-open');if(previousFocus?.isConnected)previousFocus.focus();});
function confirm(){if(props.busy||!lines.value.length)return;emit('confirm');}
function backdrop(event){if(event.target!==dialog.value)return;const r=dialog.value.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)emit('cancel');}
</script>
<template><Teleport to="body"><dialog ref="dialog" class="checkout-dialog" aria-labelledby="checkout-title" aria-describedby="checkout-description" @cancel.prevent="emit('cancel')" @click="backdrop"><button class="modal-close" type="button" aria-label="關閉" @click="emit('cancel')">×</button><h2 id="checkout-title">確定送出訂單？</h2><p id="checkout-description">確認餐點與備註後，送出訂單。</p><h3 class="confirmation-store">{{ store.name }}</h3><div class="confirmation-lines"><div v-for="line in lines" :key="line.key" class="cart-row"><div class="cart-top"><b>{{ line.name }} × {{ line.qty }}</b><span>{{ money(line.unitPrice*line.qty) }}</span></div><p v-if="line.note" class="cart-options">備註：{{ line.note }}</p></div></div><div class="total"><span>預估金額</span><strong>{{ money(total) }}</strong></div><p class="subtle">實際金額以伺服器讀取的菜單價格計算。</p><p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="confirm-actions"><button ref="cancelButton" class="secondary" type="button" :disabled="busy" @click="emit('cancel')">返回修改</button><button class="primary" type="button" :disabled="busy || !lines.length" @click="confirm">{{ busy ? '送出中…' : '確定送出' }}</button></div></dialog></Teleport></template>
