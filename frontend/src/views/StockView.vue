<template>
  <div>
    <h1 class="page-title">个股分析</h1>
    <div class="search-box">
      <input v-model="code" placeholder="输入股票代码，如 600519" @keyup.enter="search" />
      <button class="btn" @click="search">查询</button>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="loading" class="loading">加载中...</div>
    <template v-if="stockName">
      <h2 style="margin-bottom:16px">{{ stockName }} ({{ code }})</h2>
      <div class="grid-4 mb-2" v-if="quote.price">
        <div class="card metric"><div class="value">{{ quote.price }}</div><div class="label">最新价</div></div>
        <div class="card metric"><div class="value" :class="(quote.pct_chg||0)>0?'text-red':(quote.pct_chg||0)<0?'text-green':''">{{ ((quote.pct_chg||0)>0?"+":"")+(quote.pct_chg||0)+"%" }}</div><div class="label">涨跌幅</div></div>
        <div class="card metric"><div class="value">{{ quote.volume||"--" }}</div><div class="label">成交量</div></div>
        <div class="card metric"><div class="value">{{ quote.high||"--" }}</div><div class="label">最高</div></div>
      </div>
      <div class="card"><div class="card-title">K 线走势</div><div ref="klineRef" class="chart-box"></div></div>
      <div class="card" v-if="hasIndicators">
        <div class="card-title">技术指标</div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">
          <div v-for="(val,key) in indicators" :key="key" style="padding:8px;background:#f8f9ff;border-radius:6px;text-align:center;">
            <div style="font-size:11px;color:#888;">{{ key }}</div>
            <div style="font-size:15px;font-weight:600;color:#333;margin-top:2px;">{{ val }}</div>
          </div>
        </div>
        <div v-if="signals.length" style="margin-top:8px;padding-top:8px;border-top:1px solid #eee;display:flex;flex-wrap:wrap;gap:4px;">
          <div v-for="(s,idx) in signals" :key="idx" style="display:inline-block;margin:2px;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:500;background:#fff3d6;color:#e67e22;">{{ s[1]||s }}</div>
        </div>
      </div>
      <div class="flex gap-4">
        <div class="card flex-1"><div class="card-title">财务指标</div>
          <table v-if="hasFinancial"><tr v-for="(val,key) in financial" :key="key"><td>{{ key }}</td><td>{{ val }}</td></tr></table>
          <div v-else class="empty">暂无财务数据</div>
        </div>
        <div class="card flex-1" style="flex:2;">
          <div class="card-title">AI 分析</div>
          <div class="flex mb-2">
            <select v-model="mode" style="padding:6px 12px;margin-right:8px;">
              <option value="single">单分析师</option><option value="panel">5 Agent 辩论</option>
            </select>
            <button class="btn" @click="analyze" :disabled="analyzing">{{ analyzing?"分析中...":"开始分析" }}</button>
          </div>
          <!-- Agent 标签页 -->
          <div v-if="agentTabs.length > 0" class="agent-tabs">
            <button v-for="tab in agentTabs" :key="tab.name"
              :class="['tab-btn', { active: currentTab === tab.name }]"
              @click="currentTab = tab.name">
              {{ tab.label }}
              <span v-if="tab.status==='loading'" class="tab-dot loading-dot"></span>
              <span v-else-if="tab.status==='done'" class="tab-dot done-dot"></span>
            </button>
          </div>
          <div v-if="analysis" class="analysis-box" v-html="renderedAnalysis"></div>
          <div v-if="statusMsg" class="status-msg">{{ statusMsg }}</div>
        </div>
      </div>
    </template>
  </div>
</template>
<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, reactive } from "vue"
import api from "../api/index.js"
import * as echarts from "echarts"

const code = ref("600519"); const stockName = ref(""); const quote = ref({}); const financial = ref({})
const klineData = ref([]); const indicators = ref({}); const signals = ref([]); const mode = ref("panel")
const analysis = ref(""); const error = ref(""); const loading = ref(false); const analyzing = ref(false)
const statusMsg = ref(""); const currentTab = ref("")
const klineRef = ref(null); let klineChart = null

const agentTabs = reactive([])
const agentContents = reactive({})

const hasIndicators = computed(() => Object.keys(indicators.value).length>0)
const hasFinancial = computed(() => Object.keys(financial.value).length>0)
const renderedAnalysis = computed(() => {
  let t = currentTab.value ? (agentContents[currentTab.value] || "") : analysis.value
  if (!t) return ""
  let h = t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  h = h.replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>").replace(/\n/g,"<br>")
  return h
})

async function search() {
  if (!code.value.trim()) return; error.value=""; stockName.value=""; loading.value=true
  try {
    const info = await api.get("/stock/"+code.value)
    stockName.value = info.name||code.value
    const [daily, rt, fin, ind] = await Promise.all([
      api.get("/stock/"+code.value+"/daily"), api.get("/stock/"+code.value+"/realtime"),
      api.get("/stock/"+code.value+"/financial"), api.get("/stock/"+code.value+"/indicators").catch(()=>({data:{}}))
    ])
    klineData.value = (daily.data||[]).map(d=>({...d,date:String(d.date||d.trade_date||"").slice(0,10)}))
    quote.value = rt.data||{}; financial.value = fin.data||{}
    const id = ind.data||{}; indicators.value = id.indicators||{}; signals.value = id.signals||[]
    if (klineData.value.length) { await nextTick(); renderChart() }
  } catch(e) { error.value=e.message||"获取数据失败" }
  loading.value = false
}
function renderChart() {
  const el = klineRef.value; if (!el||!klineData.value.length) return
  if (klineChart) { klineChart.dispose(); klineChart = null }
  klineChart = echarts.init(el)
  klineChart.setOption({
    tooltip:{trigger:"axis"}, grid:{left:"5%",right:"5%",bottom:"5%",containLabel:true},
    xAxis:{type:"category", data:klineData.value.map(d=>String(d.date||"").slice(5,10))},
    yAxis:{type:"value",scale:true},
    series:[{type:"candlestick", data:klineData.value.map(d=>[d.open,d.close,d.low,d.high]),
      itemStyle:{color:"#e74c3c",color0:"#27ae60",borderColor:"#e74c3c",borderColor0:"#27ae60"}}]
  })
  window.addEventListener("resize",()=>{ if (klineChart) klineChart.resize() })
}

function resetTabs() {
  agentTabs.length = 0
  for (const k of Object.keys(agentContents)) delete agentContents[k]
  currentTab.value = ""
  statusMsg.value = ""
}
function ensureTab(name, label) {
  let tab = agentTabs.find(t => t.name === name)
  if (!tab) {
    tab = { name, label, status: "loading" }
    agentTabs.push(tab)
  }
  if (!agentContents[name]) agentContents[name] = ""
  return tab
}

async function analyze() {
  analyzing.value=true; analysis.value=""; error.value=""; resetTabs()
  try {
    const resp = await fetch("/api/stock/"+code.value+"/analyze/stream?mode="+mode.value, {method:"POST"})
    if (!resp.ok) { const ed=await resp.json().catch(()=>({})); throw new Error(ed.detail||"分析失败") }
    const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf = ""
    let activeAgent = null

    while (true) {
      const r = await reader.read(); if (r.done) break
      buf += dec.decode(r.value, {stream:true})
      const lines = buf.split("\n"); buf = lines.pop()||""
      for (const ln of lines) {
        if (!ln.startsWith("data: ")) continue
        const d = ln.slice(6)

        // 结构化标记
        if (d.startsWith("[AGENT:")) {
          const name = d.slice(7, -1)
          activeAgent = name
          ensureTab(name, name)
          if (!currentTab.value) currentTab.value = name
        } else if (d.startsWith("[END:")) {
          const name = d.slice(5, -1)
          const tab = agentTabs.find(t => t.name === name)
          if (tab) tab.status = "done"
          activeAgent = null
        } else if (d.startsWith("[STATUS]")) {
          statusMsg.value = d.slice(8)
        } else if (d.startsWith("[ERROR]")) {
          const msg = d.slice(7)
          if (activeAgent) {
            agentContents[activeAgent] += "\n⚠️ " + msg + "\n"
          } else {
            error.value = msg
          }
        } else if (d === "[DONE]") {
          statusMsg.value = "分析完成"
          if (agentTabs.length > 0 && !currentTab.value) {
            currentTab.value = agentTabs[0].name
          }
        } else if (activeAgent) {
          agentContents[activeAgent] += d
        } else {
          // 单分析师模式：直接追加
          analysis.value += d
          if (!currentTab.value) currentTab.value = "__single"
        }
      }
    }
  } catch(e) { error.value="分析失败: "+e.message }
  analyzing.value = false
}
onMounted(search)
onUnmounted(() => { if (klineChart) { klineChart.dispose(); klineChart = null } })
</script>
<style scoped>
.agent-tabs {
  display: flex; flex-wrap: wrap; gap: 4px;
  padding: 8px 0; border-bottom: 1px solid #eee; margin-bottom: 12px;
}
.tab-btn {
  padding: 5px 14px; border: 1px solid #d0d0d0; border-radius: 6px;
  background: #f5f5f5; color: #555; font-size: 13px; cursor: pointer;
  transition: all 0.2s; display: flex; align-items: center; gap: 6px;
}
.tab-btn:hover { background: #e8e8ff; border-color: #9090d0; }
.tab-btn.active { background: #4a4ae0; color: #fff; border-color: #4a4ae0; }
.tab-dot {
  width: 6px; height: 6px; border-radius: 50%; display: inline-block;
}
.loading-dot { background: #f0a030; animation: pulse 1s infinite; }
.done-dot { background: #30c030; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
.analysis-box {
  background:#f8f9ff; border:1px solid #e0e0e0; border-radius:8px;
  padding:20px; max-height:600px; overflow-y:auto;
  font-size:15px; line-height:1.9; color:#222; margin-top:8px;
}
.status-msg {
  color: #888; font-size: 13px; padding: 6px 0;
}
</style>
