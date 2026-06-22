<template>
  <div>
    <h1 class="page-title">情绪看板</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <LoadingSpinner v-if="loading" />
    <template v-if="!loading">
      <div class="grid-4 mb-2">
        <MetricCard :value="(marketOverview.today.avg_score || 0).toFixed(4)" label="情绪指数" />
        <MetricCard :value="((marketOverview.today.pos_ratio || 0) * 100).toFixed(1) + '%'" label="积极占比" />
        <MetricCard :value="((marketOverview.today.neg_ratio || 0) * 100).toFixed(1) + '%'" label="消极占比" />
        <MetricCard :value="marketOverview.today.total_news || 0" label="新闻总数" />
      </div>
      <div class="card">
        <div class="card-title">全市场情绪趋势</div>
        <div ref="trendChartRef" class="chart-box"></div>
      </div>
      <DataTable title="板块情绪排名" :rows="sectors" :columns="sectorColumns" row-key="code">
        <template #cell-score="{ value }">{{ (value || 0).toFixed(4) }}</template>
      </DataTable>
      <div class="card">
        <div class="card-title">个股情绪查询</div>
        <div class="flex mb-2">
          <input v-model="queryCode" placeholder="输入股票代码" style="flex:1;" />
          <button class="btn" @click="querySentiment">查询</button>
        </div>
        <div ref="stockChartRef" class="chart-box" v-if="stockData.length"></div>
      </div>
    </template>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import api from '../api/index.js'
import MetricCard from '../components/MetricCard.vue'
import DataTable from '../components/DataTable.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import { useChart } from '../composables/useChart.js'

const error = ref('')
const loading = ref(true)
const marketOverview = ref({ today: {}, trend: [] })
const sectors = ref([])
const queryCode = ref('600519')
const stockData = ref([])

const sectorColumns = [
  { key: 'code', label: '板块' },
  { key: 'score', label: '情绪得分' },
]

const { chartRef: trendChartRef, render: renderTrend } = useChart()
const { chartRef: stockChartRef, render: renderStock } = useChart()

async function loadData() {
  try {
    const [ov, se] = await Promise.all([
      api.get('/sentiment/market/overview'),
      api.get('/sentiment/sectors/rank'),
    ])
    marketOverview.value = ov.data || { today: {}, trend: [] }
    sectors.value = se.data || []

    const d = marketOverview.value.trend || []
    if (d.length) {
      await renderTrend(() => ({
        tooltip: { trigger: 'axis' },
        grid: { left: '3%', right: '3%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', data: d.map(p => String(p.date || '').slice(5, 10)) },
        yAxis: { type: 'value', axisLabel: { fontSize: 11 } },
        series: [{ type: 'line', data: d.map(p => p.score), smooth: true, lineStyle: { color: '#e94560', width: 2 }, areaStyle: { color: 'rgba(233,69,96,0.1)' } }],
      }))
    }
  } catch (e) { error.value = e.message }
  loading.value = false
}

async function querySentiment() {
  if (!queryCode.value.trim()) return
  try {
    const r = await api.get('/sentiment/' + queryCode.value + '?days=30')
    stockData.value = r.data || []
    const d = stockData.value
    if (d.length) {
      await renderStock(() => ({
        tooltip: { trigger: 'axis' },
        grid: { left: '3%', right: '3%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', data: d.map(p => String(p.date || '').slice(5, 10)) },
        yAxis: { type: 'value', axisLabel: { fontSize: 11 } },
        series: [{ type: 'bar', data: d.map(p => p.avg_score), itemStyle: { color: '#e94560' } }],
      }))
    }
  } catch (e) { error.value = e.message }
}

onMounted(loadData)
</script>
