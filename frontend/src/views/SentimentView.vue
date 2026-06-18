<template>
  <div>
    <h1 class="page-title">情绪看板</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="loading" class="loading">加载中...</div>
    <template v-if="!loading">
      <!-- 市场总览 -->
      <div class="grid-4 mb-2">
        <div class="card metric"><div class="value">{{ (marketOverview.today.avg_score||0).toFixed(4) }}</div><div class="label"><TermTooltip name="情绪指数">情绪指数</TermTooltip></div></div>
        <div class="card metric"><div class="value">{{ ((marketOverview.today.pos_ratio||0)*100).toFixed(1) }}%</div><div class="label"><TermTooltip name="积极占比">积极占比</TermTooltip></div></div>
        <div class="card metric"><div class="value">{{ ((marketOverview.today.neg_ratio||0)*100).toFixed(1) }}%</div><div class="label"><TermTooltip name="消极占比">消极占比</TermTooltip></div></div>
        <div class="card metric"><div class="value">{{ marketOverview.today.total_news||0 }}</div><div class="label">新闻总数</div></div>
      </div>
      <!-- 情绪趋势图 -->
      <div class="card">
        <div class="card-title">全市场情绪趋势</div>
        <div ref="trendChartRef" class="chart-box"></div>
      </div>
      <!-- 板块情绪排名 -->
      <div class="card">
        <div class="card-title">板块情绪排名</div>
        <table v-if="sectors.length">
          <tr><th>板块</th><th>情绪得分</th></tr>
          <tr v-for="s in sectors" :key="s.code">
            <td>{{ s.code }}</td><td>{{ (s.score||0).toFixed(4) }}</td>
          </tr>
        </table>
        <div v-else class="empty">暂无数据</div>
      </div>
      <!-- 个股情绪查询 -->
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
import { ref, onMounted, onUnmounted, nextTick } from "vue"
import api from "../api/index.js"
import TermTooltip from "../components/TermTooltip.vue"

const error = ref(""); const loading = ref(true)
const marketOverview = ref({today:{},trend:[]}); const sectors = ref([])
const queryCode = ref("600519"); const stockData = ref([])
const trendChartRef = ref(null); const stockChartRef = ref(null)
let trendChartInst = null; let stockChartInst = null

async function loadData() {
  try {
    const [ov, se] = await Promise.all([
      api.get("/sentiment/market/overview"),
      api.get("/sentiment/sectors/rank")
    ])
    marketOverview.value = ov.data || {today:{},trend:[]}
    sectors.value = se.data || []
    await nextTick()
    renderTrendChart()
  } catch(e) { error.value = e.message }
  loading.value = false
}
async function querySentiment() {
  if (!queryCode.value.trim()) return
  try {
    const r = await api.get("/sentiment/"+queryCode.value+"?days=30")
    stockData.value = r.data || []
    await nextTick()
    renderStockChart()
  } catch(e) { error.value = e.message }
}
function renderTrendChart() {
  const el = trendChartRef.value; if (!el) return
  const d = marketOverview.value.trend || []
  try {
    import("echarts").then(m => {
      const ec = m.default
      if (trendChartInst) { trendChartInst.dispose(); trendChartInst = null }
      trendChartInst = ec.init(el)
      trendChartInst.setOption({
        tooltip:{trigger:"axis"}, grid:{left:"3%",right:"3%",bottom:"3%",containLabel:true},
        xAxis:{type:"category", data:d.map(p=>String(p.date||"").slice(5,10))},
        yAxis:{type:"value", axisLabel:{fontSize:11}},
        series:[{type:"line", data:d.map(p=>p.score), smooth:true, lineStyle:{color:"#e94560",width:2}, areaStyle:{color:"rgba(233,69,96,0.1)"}}]
      })
      window.addEventListener("resize",()=>{ if (trendChartInst) trendChartInst.resize() })
    })
  } catch(e) {}
}
function renderStockChart() {
  const el = stockChartRef.value; if (!el||!stockData.value.length) return
  try {
    import("echarts").then(m => {
      const ec = m.default
      if (stockChartInst) { stockChartInst.dispose(); stockChartInst = null }
      stockChartInst = ec.init(el)
      stockChartInst.setOption({
        tooltip:{trigger:"axis"}, grid:{left:"3%",right:"3%",bottom:"3%",containLabel:true},
        xAxis:{type:"category", data:stockData.value.map(p=>String(p.date||"").slice(5,10))},
        yAxis:{type:"value", axisLabel:{fontSize:11}},
        series:[{type:"bar", data:stockData.value.map(p=>p.avg_score), itemStyle:{color:"#e94560"}}]
      })
      window.addEventListener("resize",()=>{ if (stockChartInst) stockChartInst.resize() })
    })
  } catch(e) {}
}
onMounted(loadData)
onUnmounted(() => {
  if (trendChartInst) { trendChartInst.dispose(); trendChartInst = null }
  if (stockChartInst) { stockChartInst.dispose(); stockChartInst = null }
})
</script>


