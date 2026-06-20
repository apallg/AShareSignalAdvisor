<template>
  <div>
    <h1 class="page-title">大盘总览</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <LoadingSpinner v-if="loading" />
    <template v-if="!loading">
      <div class="grid-4 mb-2">
        <MetricCard v-for="(label, code) in indexMap" :key="code"
          :value="(indices[code] || {}).price || '--'"
          :label="label"
          :delta="(indices[code] || {}).pct_chg || 0" />
      </div>
      <div class="card">
        <div class="card-title">上证指数走势</div>
        <div ref="chartRef" class="chart-box"></div>
      </div>
      <div class="flex gap-4">
        <DataTable title="涨幅榜 TOP20" :rows="gainers" :columns="topColumns" empty-text="暂无数据" />
        <DataTable title="跌幅榜 TOP20" :rows="losers" :columns="topColumns" empty-text="暂无数据" />
      </div>
      <div class="card">
        <div class="card-title">板块热点</div>
        <div v-if="sectors.length" class="flex" style="flex-wrap:wrap;gap:8px;">
          <span v-for="s in sectors.slice(0, 15)" :key="s['板块名称'] || s.name"
            class="tag" :class="(s['涨跌幅'] || s.pct_chg || 0) > 0 ? 'tag-mid' : (s['涨跌幅'] || s.pct_chg || 0) < 0 ? 'tag-low' : ''">
            {{ s['板块名称'] || s.name }}
            {{ ((s['涨跌幅'] || s.pct_chg || 0) >= 0 ? '+' : '') + Number(s['涨跌幅'] || s.pct_chg || 0).toFixed(2) }}%
          </span>
        </div>
        <div v-else class="empty">暂无数据</div>
      </div>
    </template>
  </div>
</template>
<script setup>
import { ref, onMounted, nextTick } from 'vue'
import api from '../api/index.js'
import MetricCard from '../components/MetricCard.vue'
import DataTable from '../components/DataTable.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import { useChart } from '../composables/useChart.js'

const loading = ref(true)
const error = ref('')
const indices = ref({})
const gainers = ref([])
const losers = ref([])
const sectors = ref([])
const indexMap = { '000001': '上证指数', '399001': '深证成指', '399006': '创业板指', '000688': '科创50' }

const { chartRef, render, dispose } = useChart()

const topColumns = [
  { key: 'code', label: '代码' },
  { key: 'name', label: '名称' },
  { key: 'price', label: '最新价', format: v => Number(v || 0).toFixed(2) },
  { key: 'pct_chg', label: '涨跌幅', format: v => ((v || 0) > 0 ? '+' : '') + Number(v || 0).toFixed(2) + '%',
    tdClass: row => (row.pct_chg || 0) > 0 ? 'text-red' : (row.pct_chg || 0) < 0 ? 'text-green' : '' },
]

onMounted(async () => {
  try {
    const [idx, gain, lose, sec, chart] = await Promise.all([
      api.get('/market/indices'),
      api.get('/market/top-gainers?n=20'),
      api.get('/market/top-losers?n=20'),
      api.get('/market/sectors'),
      api.get('/market/index-chart?index_name=' + encodeURIComponent('上证指数') + '&days=120'),
    ])
    indices.value = idx.data || {}
    gainers.value = gain.data || []
    losers.value = lose.data || []
    sectors.value = sec.data || []
    loading.value = false

    if (chart.data && chart.data.length) {
      await render(() => ({
        tooltip: { trigger: 'axis' },
        grid: { left: '3%', right: '3%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', data: chart.data.map(d => String(d.date || '').slice(5, 10)), axisLabel: { fontSize: 11 } },
        yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 11 } },
        series: [{ type: 'line', data: chart.data.map(d => d.close), smooth: true, lineStyle: { color: '#e74c3c', width: 2 }, areaStyle: { color: 'rgba(231,76,60,0.1)' } }],
      }))
    }
  } catch (e) { error.value = e.message; loading.value = false }
})
</script>
