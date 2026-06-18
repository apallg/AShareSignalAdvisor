<template>
  <div class="app-layout">
    <header class="app-header">
      <div class="header-left">
        <span class="logo">麒麟投研</span>
        <nav class="nav-links">
          <router-link to="/">大盘</router-link>
          <router-link to="/stock">个股</router-link>
          <router-link to="/sectors">板块</router-link>
          <router-link to="/portfolio">持仓</router-link>
          <router-link to="/scan">扫描</router-link>
          <router-link to="/alerts">告警</router-link>
          <router-link to="/backtest">回测</router-link>
          <router-link to="/lab">实验室</router-link>
          <router-link to="/sentiment">情绪</router-link>
        </nav>
      </div>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.app-header {
  background: #1a1a2e;
  color: #e0e0e0;
  padding: 0 24px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 32px;
}
.logo {
  font-weight: 700;
  font-size: 16px;
  color: #4fc3f7;
}
.nav-links {
  display: flex;
  gap: 16px;
}
.nav-links a {
  color: #b0b0b0;
  text-decoration: none;
  font-size: 14px;
  transition: color 0.2s;
}
.nav-links a:hover,
.nav-links a.router-link-active {
  color: #4fc3f7;
}
.app-main {
  flex: 1;
  padding: 16px 24px;
  background: #0f0f1a;
}
</style>
