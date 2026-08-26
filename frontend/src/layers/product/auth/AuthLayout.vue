<script setup lang="ts">
defineProps<{ activeTab?: 'login' | 'register'; wide?: boolean }>()
defineEmits<{ tab: [value: 'login' | 'register'] }>()
</script>

<template>
  <main class="auth-shell">
    <div class="shell-orb shell-orb-one" aria-hidden="true" />
    <div class="shell-orb shell-orb-two" aria-hidden="true" />
    <header class="app-header">
      <div class="brand-top"><div class="brand-mark" aria-hidden="true"><svg viewBox="0 0 64 64" role="img"><path d="M12 35c10-18 27-22 40-9-5 2-8 6-10 11 7 1 11 4 14 8-17 7-32 3-44-10Zm15-7c2 4 5 6 10 7" /></svg></div><div><strong>ADP</strong><span>养殖运营平台</span></div></div>
      <div class="header-status"><i />系统在线</div>
    </header>
    <section class="auth-stage">
      <div class="auth-card" :class="{ 'auth-card-wide': wide }">
        <div class="auth-card-top"><span class="eyebrow">ADP / AQUACULTURE</span><span class="secure-state"><i />服务在线</span></div>
        <nav v-if="activeTab" class="auth-tabs" aria-label="登录与注册">
          <button type="button" :class="{ active: activeTab === 'login' }" @click="$emit('tab', 'login')">登录</button>
          <button type="button" :class="{ active: activeTab === 'register' }" @click="$emit('tab', 'register')">注册</button>
        </nav>
        <slot />
      </div>
    </section>
    <footer>© 2026 鱼塘养殖喂养日常管理系统　保留所有权利</footer>
  </main>
</template>
