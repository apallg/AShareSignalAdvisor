<template>
  <div>
    <h1 class="page-title">大盘总览</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="loading" class="loading">加载中...</div>
    <template v-if="!loading">
      <div class="grid-4 mb-2">
        <div v-for="(label,code) in indexMap" :key="code" class="card metric">
          <div class="value">{{ (indices[code]||{}).price||"--" }}</div>
          <div class="label">{{ label }}</div>
          <div :class="['delta',((indices[code]||{}).pct_chg||0)>0?'up':((indices[code]||{}).pct_chg||0)<0?'down':'']">{{ ((indices[code]||{}).pct_chg||0)>0?'+':'' }}{{ ((indices[code]||{}).pct_chg||0).toFixed(2) }}%</div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">上证指数走势</div>
        <div ref="chartRef" class="chart-box"></div>
      </div>
      <div class="flex gap-4">
        <div class="card flex-1"><div class="card-title">涨幅榜 TOP20</div>
          <table v-if="gainers.length"><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th></tr>
            <tr v-for="g in gainers" :key="g.code"><td>{{ g.code }}</td><td>{{ g.name }}</td><td>{{ Number(g.price||0).toFixed(2) }}</td><td :class="(g.pct_chg||0)>0?'text-red':(g.pct_chg||0)<0?'text-green':''">{{ ((g.pct_chg||0)>0?'+':'')+Number(g.pct_chg||0).toFixed(2)+"%" }}</td></tr>
          </table><div v-else class="empty">暂无数据</div>
        </div>
        <div class="card flex-1"><div class="card-title">跌幅榜 TOP20</div>
          <table v-if="losers.length"><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th></tr>
            <tr v-for="g in losers" :key="g.code"><td>{{ g.code }}</td><td>{{ g.name }}</td><td>{{ Number(g.price||0).toFixed(2) }}</td><td :class="(g.pct_chg||0)>0?'text-red':(g.pct_chg||0)<0?'text-green':''">{{ ((g.pct_chg||0)>0?'+':'')+Number(g.pct_chg||0).toFixed(2)+"%" }}</td></tr>
          </table><div v-else class="empty">暂无数据</div>
        </div>
      </div>
      <div class="card"><div class="card-title">板块热点</div>
        <div v-if="sectors.length" class="flex" style="flex-wrap:wrap;gap:8px;">
          <span v-for="s in sectors.slice(0,15)" :key="s.板块名称||s.name" class="tag" :class="(s.涨跌幅||s.pct_chg||0)>0?'tag-mid':(s.涨跌幅||s.pct_chg||0)<0?'tag-low':''">{{ s.板块名称||s.name }} {{ ((s.涨跌幅||s.pct_chg||0)>=0?'+':'')+Number(s.涨跌幅||s.pct_chg||0).toFixed(2) }}%</span>
        </div><div v-else class="empty">暂无数据</div>
      </div>
    </template>
  </div>
</template>
<script setup>
import { ref, onMounted, onUnmounted, nextTick } from "vue"
import api from "../api/index.js"
import * as echarts from "echarts"
const loading = ref(true); const error = ref(""); const indices = ref({}); const gainers = ref([]); const losers = ref([]); const sectors = ref([])
const chartRef = ref(null)
let marketChart = null
const indexMap = {"000001":"上证指数","399001":"深证成指","399006":"创业板指","000688":"科创50"}

onMounted(async () => {
  try {
    const [idx, gain, lose, sec, chart] = await Promise.all([
      api.get("/market/indices"), api.get("/market/top-gainers?n=20"), api.get("/market/top-losers?n=20"),
      api.get("/market/sectors"), api.get("/market/index-chart?index_name="+encodeURIComponent("上证指数")+"&days=120")
    ])
    indices.value = idx.data||{}; gainers.value = gain.data||[]; losers.value = lose.data||[]; sectors.value = sec.data||[]
    loading.value = false
    await nextTick()
    if (chart.data&&chart.data.length) {
      if (marketChart) { marketChart.dispose(); marketChart = null }
      marketChart = echarts.init(chartRef.value)
      marketChart.setOption({
        tooltip:{trigger:"axis"}, grid:{left:"3%",right:"3%",bottom:"3%",containLabel:true},
        xAxis:{type:"category", data:chart.data.map(d=>String(d.date||"").slice(5,10)), axisLabel:{fontSize:11}},
        yAxis:{type:"value",scale:true, axisLabel:{fontSize:11}},
        series:[{type:"line", data:chart.data.map(d=>d.close), smooth:true, lineStyle:{color:"#e74c3c",width:2}, areaStyle:{color:"rgba(231,76,60,0.1)"}}]
      })
      window.addEventListener("resize",()=>{ if (marketChart) marketChart.resize() })
    }
  } catch(e) { error.value=e.message; loading.value=false }
})
onUnmounted(() => { if (marketChart) { marketChart.dispose(); marketChart = null } })
</script>
