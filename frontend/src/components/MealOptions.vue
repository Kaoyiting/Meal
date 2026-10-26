<script setup>
import { ref,reactive,computed,onMounted,onBeforeUnmount,watch } from 'vue';
import { configure,money } from '../lib/cart.js';
import { addToCart } from '../state.js';
const props=defineProps({item:Object,storeId:String});const emit=defineEmits(['close']);
const dialog=ref(null),quantity=ref(1),note=ref(''),error=ref('');
const choices=reactive(Object.fromEntries(props.item.options.map(g=>[g.id,g.multiple?[]:0])));
const selection=computed(()=>configure(props.item,choices,note.value));
const total=computed(()=>selection.value.unitPrice*quantity.value);
watch([quantity,note,choices],()=>error.value='');
onMounted(()=>{dialog.value.showModal();document.body.classList.add('modal-open');});
onBeforeUnmount(()=>{dialog.value?.close();document.body.classList.remove('modal-open');});
function submit(){try{addToCart(props.storeId,selection.value,quantity.value);emit('close');}catch(e){error.value=e.message;}}
function backdrop(event){if(event.target!==dialog.value)return;const r=dialog.value.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)emit('close');}
</script>
<template><Teleport to="body"><dialog ref="dialog" aria-labelledby="custom-title" @cancel.prevent="emit('close')" @click="backdrop"><form @submit.prevent="submit"><button type="button" class="modal-close" aria-label="關閉" @click="emit('close')">×</button><h2 id="custom-title">{{ item.name }}</h2><p id="custom-description">{{ item.description }}</p><fieldset v-for="group in item.options" :key="group.id"><legend>{{ group.label }} <small>{{ group.multiple?'可複選':'選一項' }}</small></legend><div class="option-grid"><label v-for="(option,index) in group.options" :key="index" class="option"><input v-if="group.multiple" v-model="choices[group.id]" type="checkbox" :value="index" :name="group.id"><input v-else v-model="choices[group.id]" type="radio" :value="index" :name="group.id"><span>{{ option.label }}</span><small v-if="option.price">+${{ option.price }}</small></label></div></fieldset><label class="notes-label" for="custom-note">備註</label><textarea id="custom-note" v-model="note" maxlength="120" placeholder="例如：醬料另外放（120 字以內）"></textarea><p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="modal-bottom"><div class="stepper"><button type="button" :disabled="quantity===1" aria-label="減少數量" @click="quantity--">−</button><output>{{ quantity }}</output><button type="button" :disabled="quantity===10" aria-label="增加數量" @click="quantity++">＋</button></div><button type="submit" class="primary">加入餐袋 · {{ money(total) }}</button></div></form></dialog></Teleport></template>
