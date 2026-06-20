<template>
  <div>
    <h1 class="page-title">批量风险扫描</h1>
    <div v-if="error" class="error">{{ error }}</div>

    <div class="card">
      <div class="card-title">扫描配置</div>
      <div class="flex gap-4 mb-2" style="flex-wrap:wrap;">
        <label v-for="ds in dataSources" :key="ds.key" style="display:flex;align-items:center;gap:4px;font-size:13px;">
          <input type="checkbox" v-model="included[ds.key]" /> {{ ds.label }}
        </label>
      </div>
      <div class="flex mb-2">
        <label style="width:120px;">风险阈值: {{ threshold }}</label>
        <input type="range" v-model.number="threshold" min="1" max="10" style="flex:1;" />
      </div>
      <button class="btn" @click="scan" :disabled="scanning">{{ scanning ? '扫描中...' : '开始扫描' }}</button>
    </div>

    <DataTable
      v-if="results.length"
      :rows="results"
      :columns="columns"
      :title="'扫描结果'"
      :count="results.length"
      row-key="stock_code"
    >
      <template #cell-stock_name="{ row }">{{ row.stock_name }}({{ row.stock_code }})</template>
      <template #cell-risk_level="{ value }">
        <span :class="['tag', value==='高风险'?'tag-high':value==='中风险'?'tag-mid':'tag-low']">{{ value }}</span>
      </template>
      <template #cell-risk_score="{ value }">{{ value }}/10</template>
      <template #cell-risk_detail="{ value }">
        <span style="max-width:200px;font-size:12px;display:block;">{{ (value || '').slice(0, 60) || '--' }}</span>
      </template>
      <template #cell-suggestion="{ value }">
        <span style="max-width:150px;font-size:12px;display:block;">{{ (value || '').slice(0, 30) || '--' }}</span>
      </template>
    </DataTable>
    <div v-else-if="scanned" class="card empty">扫描完成，无风险告警</div>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import api from '../api/index.js'
import DataTable from '../components/DataTable.vue'

const dataSources = [
  { key: 'tech', label: '技术面' }, { key: 'capital', label: '资金面' },
  { key: 'fundamental', label: '基本面' }, { key: 'news', label: '消息面' },
  { key: 'market', label: '大盘环境' },
]
const included = ref({ tech: true, capital: true, fundamental: true, news: true, market: true })
const threshold = ref(5)
const scanning = ref(false)
const scanned = ref(false)
const results = ref([])
const error = ref('')

const columns = [
  { key: 'stock_name', label: '股票' },
  { key: 'risk_level', label: '风险等级' },
  { key: 'risk_score', label: '评分' },
  { key: 'risk_detail', label: '风险点' },
  { key: 'suggestion', label: '建议' },
]

async function scan() {
  scanning.value = true; error.value = ''; results.value = []; scanned.value = false
  try {
    const res = await api.post('/portfolio/scan', { threshold: threshold.value, include: included.value })
    results.value = res.data || []
    scanned.value = true
  } catch (e) {
    error.value = '扫描失败: ' + (e.response?.data?.detail || e.message)
  }
  scanning.value = false
}
</script>
