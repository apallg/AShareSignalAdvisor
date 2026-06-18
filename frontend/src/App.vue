<template>
  <div class="layout">
    <aside class="sidebar" :style="{ width: collapsed ? '60px' : '220px' }">
      <div class="logo" v-if="!collapsed">
        麒麟投研
        <small>AI 驱动 A 股量化分析</small>
      </div>
      <div class="logo" v-else style="text-align:center;padding:12px 0;font-size:20px;">麒</div>
      <nav class="nav">
        <router-link v-for="item in navItems" :key="item.path" :to="item.path">
          <span>{{ item.icon }}</span>
          <span v-if="!collapsed">{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="version">{{ collapsed ? 'v1' : 'v1.0.0' }}</div>
    </aside>
    <main class="main">
      <button @click="collapsed = !collapsed" class="toggle-btn">{{ collapsed ? '›' : '‹' }}</button>
      <router-view />
    </main>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
const collapsed = ref(false)
const route = useRoute()
const navItems = [
  { path: '/market', label: '大盘总览', icon: '📊' },
  { path: '/stock', label: '个股分析', icon: '🔍' },
  { path: '/sectors', label: '板块选股', icon: '🏭' },
  { path: '/portfolio', label: '持仓管理', icon: '📁' },
  { path: '/scan', label: '批量风险扫描', icon: '📋' },
  { path: '/backtest', label: '策略回测', icon: '📊' },
  { path: '/lab', label: '策略实验室', icon: '\u{1F4CA}' },
  { path: '/sentiment', label: '情绪看板', icon: '📊' },
  { path: '/alerts', label: '风险告警', icon: '⚠️' },
]
</script>

