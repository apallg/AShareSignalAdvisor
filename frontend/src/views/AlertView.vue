<template>
  <div>
    <h1 class="page-title">风险告警</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <div class="grid-4 mb-2">
      <MetricCard :value="stats.high" label="高风险" color="up" />
      <MetricCard :value="stats.mid" label="中风险" />
      <MetricCard :value="stats.low" label="低风险" color="down" />
    </div>
    <div class="flex mb-2">
      <select v-model="levelFilter">
        <option value="">全部等级</option>
        <option value="高风险">高风险</option>
        <option value="中风险">中风险</option>
        <option value="低风险">低风险</option>
      </select>
    </div>
    <DataTable
      :rows="filtered"
      :columns="columns"
      row-key="id"
      empty-text="暂无告警记录"
    >
      <template #cell-stock_name="{ row }">{{ row.stock_name }}({{ row.stock_code }})</template>
      <template #cell-risk_level="{ value }">
        <span :class="['tag', value==='高风险'?'tag-high':value==='中风险'?'tag-mid':'tag-low']">{{ value }}</span>
      </template>
      <template #cell-risk_score="{ value }">{{ value }}/10</template>
      <template #cell-created_at="{ value }">
        <span style="white-space:nowrap">{{ value?.slice(0,16) || '--' }}</span>
      </template>
    </DataTable>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api/index.js'
import MetricCard from '../components/MetricCard.vue'
import DataTable from '../components/DataTable.vue'

const alerts = ref([])
const stats = ref({ high: 0, mid: 0, low: 0 })
const levelFilter = ref('')
const error = ref('')

const columns = [
  { key: 'stock_name', label: '股票' },
  { key: 'risk_level', label: '等级' },
  { key: 'risk_score', label: '评分' },
  { key: 'created_at', label: '时间' },
]

const filtered = computed(() =>
  !levelFilter.value ? alerts.value : alerts.value.filter(a => a.risk_level === levelFilter.value)
)

onMounted(async () => {
  try {
    const [a, s] = await Promise.all([
      api.get('/alerts/?limit=100'),
      api.get('/alerts/stats?limit=200'),
    ])
    alerts.value = a.data || []
    stats.value = s.data || { high: 0, mid: 0, low: 0 }
  } catch (e) { error.value = e.message }
})
</script>
