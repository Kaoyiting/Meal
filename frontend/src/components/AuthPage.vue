<script setup>
import { ref } from 'vue';
import { login, register } from '../state.js';

const mode = ref('login');
const username = ref('');
const password = ref('');
const busy = ref(false);
const message = ref('');
const error = ref('');

async function submit() {
  error.value = '';
  message.value = '';
  busy.value = true;
  try {
    if (mode.value === 'register') {
      await register(username.value, password.value);
      message.value = '員工帳號建立完成，請登入。';
      mode.value = 'login';
      password.value = '';
    } else {
      await login(username.value, password.value);
    }
  } catch (cause) {
    error.value = cause.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="auth-shell">
    <div class="auth-copy">
      <p class="eyebrow">MEAL · 好好吃飯</p>
      <h1>把今天的午餐，<br>交給喜歡的味道。</h1>
      <p>登入員工帳號開始點餐。管理員可由同一入口登入，進入菜單與庫存管理。</p>
    </div>
    <form class="auth-card" @submit.prevent="submit">
      <div class="auth-tabs" role="tablist" aria-label="帳號操作">
        <button type="button" :class="{ selected: mode === 'login' }" @click="mode = 'login'; error = ''">登入</button>
        <button type="button" :class="{ selected: mode === 'register' }" @click="mode = 'register'; error = ''">建立員工帳號</button>
      </div>
      <h2>{{ mode === 'login' ? '歡迎回來' : '建立員工帳號' }}</h2>
      <p class="muted">{{ mode === 'login' ? '輸入帳號密碼繼續。' : '新註冊的帳號會使用員工權限。' }}</p>
      <label for="username">帳號</label>
      <input id="username" v-model.trim="username" autocomplete="username" minlength="3" maxlength="50" required>
      <label for="password">密碼</label>
      <input id="password" v-model="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" type="password" minlength="8" maxlength="72" required>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <p v-if="message" class="form-success" role="status">{{ message }}</p>
      <button class="primary" type="submit" :disabled="busy">{{ busy ? '處理中…' : mode === 'login' ? '登入 Meal' : '註冊員工帳號' }}</button>
      <p v-if="mode === 'register'" class="auth-hint">公開註冊只會建立員工帳號；管理員帳號由專案管理員建立。</p>
    </form>
  </section>
</template>
