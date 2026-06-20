<template>
  <div class="layout">
    <aside class="sidebar" :style="{ width: collapsed ? '60px' : '220px' }">
      <div class="logo" v-if="!collapsed">
        Apallg投研
        <small>AI 驱动 A 股量化分析</small>
      </div>
      <div class="logo" v-else style="text-align:center;padding:12px 0;font-size:20px;">Ap</div>
      <nav class="nav">
        <template v-for="item in navItems" :key="item.path || item.label">
          <template v-if="item.children">
            <div
              class="nav-group-parent"
              :class="{ active: isGroupActive(item) }"
              @click="collapsed ? (collapsed = false) : toggleGroup(item.label)"
            >
              <span>{{ item.icon }}</span>
              <span v-if="!collapsed">{{ item.label }}</span>
              <span v-if="!collapsed" class="arrow">{{ expanded[item.label] ? '▾' : '▸' }}</span>
            </div>
            <router-link
              v-if="!collapsed"
              v-for="child in item.children" :key="child.path"
              :to="child.path"
              class="sub-item"
              :style="{ display: expanded[item.label] ? 'flex' : 'none' }"
            >
              <span class="sub-dot"></span>
              <span>{{ child.label }}</span>
            </router-link>
          </template>
          <router-link v-else :to="item.path">
            <span>{{ item.icon }}</span>
            <span v-if="!collapsed">{{ item.label }}</span>
          </router-link>
        </template>
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
import { ref, reactive } from 'vue'
import { useRoute } from 'vue-router'
const collapsed = ref(false)
const route = useRoute()
const expanded = reactive({ '策略': true })
function toggleGroup(label) { expanded[label] = !expanded[label] }
function isGroupActive(item) { return item.children.some(c => route.path.startsWith(c.path)) }

const navItems = [
  { path: '/market', label: '大盘总览', icon: '📊' },
  { path: '/stock', label: '个股分析', icon: '🔍' },
  { path: '/sectors', label: '板块选股', icon: '🏭' },
  { path: '/sentiment', label: '情绪看板', icon: '📈' },
  { label: '策略', icon: '⚙️', children: [
    { path: '/backtest', label: '策略回测', icon: '' },
    { path: '/lab', label: '策略实验室', icon: '' },
    { path: '/live', label: '策略实盘', icon: '' },
    { path: '/editor', label: '新建策略', icon: '' },
  ]},
  { label: '交易风控', icon: '💰', children: [
    { path: '/trading', label: '交易面板', icon: '' },
    { path: '/portfolio', label: '持仓管理', icon: '' },
    { path: '/scan', label: '批量风险扫描', icon: '' },
    { path: '/alerts', label: '风险告警', icon: '' },
  ]},
]
</script>

